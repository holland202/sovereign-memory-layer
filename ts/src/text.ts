// Python string behaviour the store depends on (mirror of rust/src/text.rs).
import { createHash } from "node:crypto";

export const DIM = 384;

/** Python str.isspace(): bidi classes WS/B/S plus category Zs. */
export function pyIsSpace(cp: number): boolean {
  return (
    (cp >= 0x09 && cp <= 0x0d) || (cp >= 0x1c && cp <= 0x20) || cp === 0x85 || cp === 0xa0 || cp === 0x1680 ||
    (cp >= 0x2000 && cp <= 0x200a) || cp === 0x2028 || cp === 0x2029 || cp === 0x202f || cp === 0x205f ||
    cp === 0x3000
  );
}

/** Python `not s.strip()`. */
export function pyBlank(s: string): boolean {
  for (const ch of s) if (!pyIsSpace(ch.codePointAt(0)!)) return false;
  return true;
}

/** Python s.split() with no argument. */
export function pySplit(s: string): string[] {
  const out: string[] = [];
  let cur = "";
  for (const ch of s) {
    if (pyIsSpace(ch.codePointAt(0)!)) {
      if (cur) out.push(cur);
      cur = "";
    } else cur += ch;
  }
  if (cur) out.push(cur);
  return out;
}

/** Python len(s): code points, not UTF-16 units. */
export function pyLen(s: string): number {
  let n = 0;
  for (const _ of s) n++;
  return n;
}

export const nfc = (s: string): string => s.normalize("NFC");

const CONTROL = /[\p{Cc}\p{Cf}\p{Cs}]/u;
export const hasControlOrFormat = (s: string): boolean => CONTROL.test(s);

function modHex(hex: string, m: bigint): number {
  return Number(BigInt("0x" + hex) % m);
}

/** The store's lexical hash embedding (NOT semantic), before normalization. */
export function hashEmbeddingRaw(text: string): number[] {
  const out = new Array<number>(DIM).fill(0.0);
  const words = pySplit(text.toLowerCase());
  for (let i = 0; i < words.length; i++) {
    const raw = Buffer.from(words[i], "utf8");
    out[modHex(createHash("md5").update(raw).digest("hex"), 384n)] += 1 / (i + 1);
    out[modHex(createHash("sha256").update(raw).digest("hex"), 384n)] += 0.5 / (i + 1);
  }
  return out;
}

export const sha256Hex = (b: Uint8Array): string => createHash("sha256").update(b).digest("hex");
