// A JSON model that reproduces Python's `json` where the store depends on it (mirror of rust/src/json.rs):
// json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) and a strict
// json.loads (duplicate keys refused). Python's int and float are kept apart: an int is a PyInt.
import { pyFloatRepr } from "./pyfloat.ts";
import { ValueError } from "./errors.ts";

export class PyInt {
  readonly v: bigint;
  constructor(v: bigint) {
    this.v = v;
  }
}
export type Value = null | boolean | number | string | PyInt | Value[] | Map<string, Value>;

export const int = (n: number | bigint): PyInt => new PyInt(BigInt(n));
export const isInt = (x: unknown): x is PyInt => x instanceof PyInt;
export const isObj = (x: unknown): x is Map<string, Value> => x instanceof Map;
/** Python `type(x) in (int, float)` (never bool). */
export const isNumber = (x: unknown): x is PyInt | number => x instanceof PyInt || typeof x === "number";
export const toF = (x: PyInt | number): number => (x instanceof PyInt ? Number(x.v) : x);

export class JsonError extends ValueError {}

const I64_MIN = -(2n ** 63n);
const I64_MAX = 2n ** 63n - 1n;

// ------------------------------------------------------------------ encoding
function cmpCodePoints(a: string, b: string): number {
  // Python sorts str keys by code point; JS compares UTF-16 units. Equal for BMP-only keys,
  // so compare by code points explicitly.
  const A = Array.from(a, (c) => c.codePointAt(0)!);
  const B = Array.from(b, (c) => c.codePointAt(0)!);
  for (let i = 0; i < Math.min(A.length, B.length); i++) if (A[i] !== B[i]) return A[i] - B[i];
  return A.length - B.length;
}

function encodeStr(s: string): string {
  let out = '"';
  for (const ch of s) {
    const c = ch.codePointAt(0)!;
    if (ch === '"') out += '\\"';
    else if (ch === "\\") out += "\\\\";
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else if (c === 0x08) out += "\\b";
    else if (c === 0x0c) out += "\\f";
    else if (c < 0x20) out += "\\u" + c.toString(16).padStart(4, "0");
    else if (c >= 0xd800 && c <= 0xdfff) throw new JsonError("surrogates not allowed");
    else out += ch;
  }
  return out + '"';
}

function encode(v: Value): string {
  if (v === null) return "null";
  if (v === true) return "true";
  if (v === false) return "false";
  if (v instanceof PyInt) return v.v.toString();
  if (typeof v === "number") {
    if (!Number.isFinite(v)) throw new JsonError("Out of range float values are not JSON compliant");
    return pyFloatRepr(v);
  }
  if (typeof v === "string") return encodeStr(v);
  if (Array.isArray(v)) return "[" + v.map(encode).join(",") + "]";
  const keys = [...v.keys()].sort(cmpCodePoints);
  return "{" + keys.map((k) => encodeStr(k) + ":" + encode(v.get(k)!)).join(",") + "}";
}

/** The canonical byte form (UTF-8). Throws JsonError (a ValueError in Python) on non-finite floats. */
export function canonical(v: Value): Buffer {
  return Buffer.from(encode(v), "utf8");
}
export function canonicalString(v: Value): string {
  return encode(v);
}

// ------------------------------------------------------------------ decoding
const MAX_DEPTH = 512;

class Parser {
  s: string;
  i = 0;
  constructor(s: string) {
    this.s = s;
  }
  fail(m: string): never {
    throw new JsonError(`${m} at ${this.i}`);
  }
  ws(): void {
    while (this.i < this.s.length) {
      const c = this.s[this.i];
      if (c === " " || c === "\t" || c === "\n" || c === "\r") this.i++;
      else break;
    }
  }
  value(depth: number): Value {
    if (depth > MAX_DEPTH) this.fail("maximum nesting depth exceeded");
    this.ws();
    const c = this.s[this.i];
    if (c === undefined) this.fail("unexpected end");
    if (c === "{") {
      this.i++;
      const m = new Map<string, Value>();
      this.ws();
      if (this.s[this.i] === "}") {
        this.i++;
        return m;
      }
      for (;;) {
        this.ws();
        if (this.s[this.i] !== '"') this.fail("expected string key");
        const k = this.string();
        this.ws();
        if (this.s[this.i] !== ":") this.fail("expected ':'");
        this.i++;
        const v = this.value(depth + 1);
        if (m.has(k)) this.fail("duplicate JSON key");
        m.set(k, v);
        this.ws();
        const d = this.s[this.i];
        if (d === ",") this.i++;
        else if (d === "}") {
          this.i++;
          return m;
        } else this.fail("expected ',' or '}'");
      }
    }
    if (c === "[") {
      this.i++;
      const a: Value[] = [];
      this.ws();
      if (this.s[this.i] === "]") {
        this.i++;
        return a;
      }
      for (;;) {
        a.push(this.value(depth + 1));
        this.ws();
        const d = this.s[this.i];
        if (d === ",") this.i++;
        else if (d === "]") {
          this.i++;
          return a;
        } else this.fail("expected ',' or ']'");
      }
    }
    if (c === '"') return this.string();
    if (this.s.startsWith("true", this.i)) {
      this.i += 4;
      return true;
    }
    if (this.s.startsWith("false", this.i)) {
      this.i += 5;
      return false;
    }
    if (this.s.startsWith("null", this.i)) {
      this.i += 4;
      return null;
    }
    // Python accepts NaN/Infinity here and then refuses them (allow_nan=False in the checksum);
    // refusing at parse time gives the same outcome, as in the Rust port.
    if (c === "-" || (c >= "0" && c <= "9")) return this.number();
    this.fail("unexpected character");
  }
  number(): Value {
    const start = this.i;
    const s = this.s;
    const digit = (k: number) => k < s.length && s[k] >= "0" && s[k] <= "9";
    if (s[this.i] === "-") this.i++;
    if (s[this.i] === "0") this.i++;
    else if (digit(this.i)) while (digit(this.i)) this.i++;
    else this.fail("invalid number");
    let isFloat = false;
    if (s[this.i] === "." && digit(this.i + 1)) {
      isFloat = true;
      this.i++;
      while (digit(this.i)) this.i++;
    }
    if (s[this.i] === "e" || s[this.i] === "E") {
      const save = this.i;
      this.i++;
      if (s[this.i] === "+" || s[this.i] === "-") this.i++;
      if (digit(this.i)) {
        isFloat = true;
        while (digit(this.i)) this.i++;
      } else this.i = save;
    }
    const text = s.slice(start, this.i);
    if (isFloat) return Number(text);
    const b = BigInt(text);
    // Python accepts integers up to 4300 digits; this port, like the Rust one, refuses anything outside i64.
    if (b < I64_MIN || b > I64_MAX) this.fail("integer out of supported range");
    return new PyInt(b);
  }
  hex4(): number {
    const h = this.s.slice(this.i, this.i + 4);
    if (h.length < 4 || !/^[0-9a-fA-F]{4}$/.test(h)) this.fail("invalid \\u escape");
    this.i += 4;
    return parseInt(h, 16);
  }
  string(): string {
    this.i++; // opening quote
    let out = "";
    for (;;) {
      const start = this.i;
      while (this.i < this.s.length) {
        const c = this.s.charCodeAt(this.i);
        if (c === 0x22 || c === 0x5c || c < 0x20) break;
        this.i++;
      }
      out += this.s.slice(start, this.i);
      if (this.i >= this.s.length) this.fail("unterminated string");
      const c = this.s[this.i];
      if (c === '"') {
        this.i++;
        return out;
      }
      if (c === "\\") {
        this.i++;
        const e = this.s[this.i];
        if (e === undefined) this.fail("truncated escape");
        this.i++;
        switch (e) {
          case '"': out += '"'; break;
          case "\\": out += "\\"; break;
          case "/": out += "/"; break;
          case "b": out += "\b"; break;
          case "f": out += "\f"; break;
          case "n": out += "\n"; break;
          case "r": out += "\r"; break;
          case "t": out += "\t"; break;
          case "u": {
            const u = this.hex4();
            if (u >= 0xd800 && u < 0xdc00) {
              if (this.s.startsWith("\\u", this.i)) {
                this.i += 2;
                const l = this.hex4();
                if (!(l >= 0xdc00 && l < 0xe000)) this.fail("lone surrogate in string");
                out += String.fromCodePoint(0x10000 + ((u - 0xd800) << 10) + (l - 0xdc00));
              } else this.fail("lone surrogate in string");
            } else if (u >= 0xdc00 && u < 0xe000) this.fail("lone surrogate in string");
            else out += String.fromCodePoint(u);
            break;
          }
          default:
            this.fail("invalid escape");
        }
        continue;
      }
      this.fail("invalid control character in string");
    }
  }
}

const UTF8 = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });

/** Strict json.loads(bytes): UTF-8 only (a leading UTF-8 BOM skipped, as Python does). */
export function parseBytes(b: Uint8Array): Value {
  let body = b;
  if (b.length >= 3 && b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf) body = b.subarray(3);
  let s: string;
  try {
    s = UTF8.decode(body);
  } catch {
    throw new JsonError("invalid UTF-8");
  }
  return parseString(s);
}

/** Strict json.loads(str): no BOM allowed (Python refuses one in a str). */
export function parseString(s: string): Value {
  if (s.startsWith("﻿")) throw new JsonError("Unexpected UTF-8 BOM");
  const p = new Parser(s);
  const v = p.value(0);
  p.ws();
  if (p.i !== s.length) p.fail("extra data");
  return v;
}
