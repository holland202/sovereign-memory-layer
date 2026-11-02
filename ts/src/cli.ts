// TypeScript side of the differential line protocol (mirror of tools/py_cli.py and rust/src/bin/sml-cli.rs).
// One JSON op per stdin line; one canonical JSON result per stdout line. Usage: node ts/src/cli.ts
import * as fs from "node:fs";
import * as path from "node:path";
import { createInterface } from "node:readline";
import { ValueError, classify } from "./errors.ts";
import { PyInt, type Value, canonicalString, int, isObj, parseString } from "./json.ts";
import { fromBits, pyFloatRepr } from "./pyfloat.ts";
import { type Hit, MemoryStore, type PutOpts, type RetrieveOpts } from "./store.ts";
import { pyBlank, sha256Hex } from "./text.ts";

type Obj = Map<string, Value>;
const get = (op: Obj, k: string, d: Value): Value => (op.has(k) ? op.get(k)! : d);
const opt = (op: Obj, k: string): Value | undefined => (op.has(k) ? op.get(k)! : undefined);
const notNone = (op: Obj, k: string): Value | undefined => {
  const v = op.get(k);
  return v === undefined || v === null ? undefined : v;
};

const hits = (hs: Hit[]): Value => hs.map((h) => [h.record.get("id")!, pyFloatRepr(h.score)]);

function ropts(op: Obj): RetrieveOpts {
  const o: RetrieveOpts = {};
  for (const k of ["method", "top_k", "threshold", "half_life"] as const) if (op.has(k)) o[k] = op.get(k)!;
  if (op.has("rkey")) o.key = op.get("rkey")!;
  const q = notNone(op, "qembedding");
  if (q !== undefined) o.embedding = q;
  return o;
}

function popts(op: Obj): PutOpts {
  const o: PutOpts = {};
  for (const k of ["timestamp", "text", "weight", "embedding", "thermal_state"] as const) {
    const v = notNone(op, k);
    if (v !== undefined) o[k] = v;
  }
  o.protected = op.get("protected") === true;
  const s = notNone(op, "supersedes");
  if (s !== undefined) o.supersedes = s;
  return o;
}

const asDir = (d: Value): string => {
  if (typeof d !== "string") throw new TypeError("expected str, bytes or os.PathLike object");
  return d;
};

function run(op: Obj): Value {
  const t = get(op, "clock", 1000.0);
  const name = op.get("op");
  const clock = () => t;
  if (name === "repr") {
    // repr never uses the directory, so it is not validated first (SML-TS-003 F7).
    return (op.get("bits") as string[]).map((h) => pyFloatRepr(fromBits(BigInt("0x" + h))));
  }
  const d = asDir(get(op, "dir", ""));
  if (name === "create") {
    new MemoryStore(d, { create: true, max_records: get(op, "max_records", int(0)), max_bytes: get(op, "max_bytes", int(0)), clock });
    return null;
  }
  if (name === "file") {
    const p = path.join(d, "memory.json");
    let isFile = false;
    try {
      isFile = fs.statSync(p).isFile();
    } catch { /* missing */ }
    return isFile ? sha256Hex(fs.readFileSync(p)) : null;
  }
  const m = new MemoryStore(d, { clock });
  const prov = opt(op, "provenance") ?? null;
  if (name === "put") return new PyInt(m.put(get(op, "key", ""), get(op, "value", ""), prov, popts(op)));
  if (name === "correct") {
    const o = popts(op);
    delete o.supersedes;
    return new PyInt(m.correct(get(op, "id", int(0)), get(op, "value", ""), prov, o));
  }
  if (name === "revoke") {
    m.revoke(get(op, "id", int(0)), get(op, "reason", ""), prov);
    return null;
  }
  if (name === "compact") return m.compact(get(op, "target", int(0))).map((i) => new PyInt(i));
  if (name === "retrieve") return hits(m.retrieve(get(op, "query", ""), ropts(op)));
  if (name === "recall") {
    const r = m.recall(get(op, "key", ""), opt(op, "query") ?? null, ropts(op));
    const out = new Map<string, Value>([["status", r.status], ["evidence_ids", r.evidence_ids.map((i) => new PyInt(i))]]);
    if (r.status === "KNOWN") {
      out.set("value", r.value!);
      out.set("hits", hits(r.retrieval!));
    } else out.set("reason", r.reason!);
    return out;
  }
  if (name === "status") return m.storageStatus();
  if (name === "cleanup") {
    m.cleanupIncomplete();
    return null;
  }
  throw new ValueError("unknown op");
}

function handle(line: string): string {
  let res: Obj;
  try {
    let op: Value;
    try {
      op = parseString(line);
    } catch {
      // bad JSON, duplicate fields or a BOM (R3-04): same as the Python and Rust sides
      return canonicalString(new Map<string, Value>([["error", "BadOp"], ["ok", false]]));
    }
    if (!isObj(op)) throw Object.assign(new Error("'list' object has no attribute 'get'"), { name: "AttributeError" });
    res = new Map<string, Value>([["ok", true], ["result", run(op)]]);
  } catch (e) {
    const cls = e instanceof Error && e.name === "AttributeError" ? "AttributeError" : classify(e);
    res = new Map<string, Value>([["error", cls], ["ok", false]]);
  }
  return canonicalString(res);
}

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity, terminal: false });
rl.on("line", (line) => {
  if (pyBlank(line)) return;
  fs.writeSync(1, handle(line) + "\n");
});
