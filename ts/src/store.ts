// Port of sml/memory.py (MemoryStore). Same file format, same refusals, same order of checks.
// Declared limit: no flock in Node, so this port is SINGLE-PROCESS ONLY (see ../PORT_PREREG.md).
import * as fs from "node:fs";
import * as path from "node:path";
import {
  CapacityError, CommitUncertain, IntegrityError, LockError, RuntimeError, ValueError, os,
} from "./errors.ts";
import { PyInt, type Value, canonical, int, isInt, isNumber, isObj, parseBytes, toF } from "./json.ts";
import { exp, pySum } from "./pyfloat.ts";
import { DIM, hasControlOrFormat, hashEmbeddingRaw, nfc, pyBlank, pyLen, sha256Hex } from "./text.ts";

export const METHODS = ["similarity", "recency", "importance", "protected"];
export const READ_LIMIT = 16_000_000;
export const MAX_COUNTER = 2n ** 63n - 1n;
const RECORD_FIELDS = ["id", "key", "value", "text", "provenance", "timestamp", "recorded_at", "weight",
  "protected", "status", "supersedes", "revocation", "embedding"];
const LN2 = Math.LN2; // == math.log(2)

type Obj = Map<string, Value>;
export type Clock = () => Value;

function keysAre(m: Obj, keys: string[]): boolean {
  return m.size === keys.length && keys.every((k) => m.has(k));
}

function deepCopy(v: Value): Value {
  if (Array.isArray(v)) return v.map(deepCopy);
  if (isObj(v)) return new Map([...v].map(([k, x]) => [k, deepCopy(x)]));
  return v;
}

export function digest(v: Value): string {
  return sha256Hex(canonical(v));
}

/** Python number(): int or float (never bool), finite, an int exactly representable, low <= x <= high. */
export function number(x: Value | undefined, name: string, low = 0, high = Infinity): number {
  if (!isNumber(x)) throw new ValueError(`invalid ${name}`);
  const f = toF(x);
  if (!Number.isFinite(f) || (isInt(x) && BigInt(f) !== x.v) || !(low <= f && f <= high)) {
    throw new ValueError(`invalid ${name}`);
  }
  return f;
}

export function nonempty(x: Value | undefined, name: string): string {
  if (typeof x !== "string" || pyBlank(x)) throw new ValueError(`empty ${name}`);
  return x;
}

export function identifier(x: Value | undefined, name: string): string {
  const s = nonempty(x, name);
  if (hasControlOrFormat(s)) throw new ValueError(`${name} contains control, format or surrogate characters`);
  return nfc(s);
}

export function sameKey(a: Value | undefined, b: Value | undefined): boolean {
  return typeof a === "string" && typeof b === "string" && nfc(a) === nfc(b);
}

export function validateProvenance(p: Value | undefined): Obj {
  if (!isObj(p) || !keysAre(p, ["source", "locator", "sha256"])) {
    throw new ValueError("provenance requires source, locator, sha256");
  }
  nonempty(p.get("source"), "source");
  nonempty(p.get("locator"), "locator");
  const d = p.get("sha256");
  if (typeof d !== "string" || pyLen(d) !== 64 || !/^[0-9a-f]*$/.test(d)) throw new ValueError("invalid source digest");
  return deepCopy(p) as Obj;
}

function newProvenance(p: Value | undefined): Obj {
  const q = validateProvenance(p);
  identifier(q.get("source"), "source");
  identifier(q.get("locator"), "locator");
  return q;
}

export function vector(xs: Value | undefined, dim = DIM): number[] {
  if (!Array.isArray(xs) || xs.length !== dim) throw new ValueError("embedding dimension mismatch");
  const v = xs.map((x) => number(x, "embedding", -1e100, 1e100));
  const norm = Math.sqrt(pySum(v.map((x) => x * x)));
  if (!norm) throw new ValueError("zero embedding");
  return v.map((x) => x / norm);
}

export function hashEmbedding(text: Value | undefined): number[] {
  const t = nonempty(text, "text");
  return vector(hashEmbeddingRaw(t));
}

function bump(s: Obj, k: string): void {
  const v = (s.get(k) as PyInt).v;
  if (v >= MAX_COUNTER) throw new CapacityError(`${k} exhausted; no write committed`);
  s.set(k, new PyInt(v + 1n));
}

const getI = (m: Obj, k: string): bigint => (m.get(k) as PyInt).v;
const recs = (s: Obj): Obj[] => s.get("records") as Obj[];

export interface Hit {
  record: Obj;
  score: number;
}

export interface RetrieveOpts {
  method?: Value;
  top_k?: Value;
  threshold?: Value;
  half_life?: Value;
  key?: Value;
  embedding?: Value;
}

export interface PutOpts {
  timestamp?: Value;
  text?: Value;
  weight?: Value;
  protected?: Value;
  supersedes?: Value;
  embedding?: Value;
  thermal_state?: Value;
}

export class MemoryStore {
  readonly directory: string;
  readonly path: string;
  readonly pending: string;
  readonly clock: Clock;

  constructor(directory: string, opts: { create?: boolean; max_records?: Value; max_bytes?: Value; clock: Clock }) {
    this.directory = directory;
    this.path = path.join(directory, "memory.json");
    this.pending = path.join(directory, "memory.pending");
    this.clock = opts.clock;
    if (opts.create) {
      // Only an omitted value takes the default; an explicit null is refused, as in Python (SML-TS-003 F4).
      const mr = opts.max_records === undefined ? int(128) : opts.max_records;
      const mb = opts.max_bytes === undefined ? int(2_000_000) : opts.max_bytes;
      if (!isInt(mr) || !(1n <= mr.v && mr.v <= MAX_COUNTER)) throw new ValueError("invalid max_records");
      if (!isInt(mb) || !(1024n <= mb.v && mb.v <= 16_000_000n)) throw new ValueError("invalid max_bytes");
      os(() => fs.mkdirSync(directory === "" ? "." : directory, { mode: 0o700 }));
      this.lock(() => {
        this.commit(new Map<string, Value>([["schema", int(1)], ["generation", int(0)], ["next_id", int(1)],
          ["max_records", mr], ["max_bytes", mb], ["records", []]]));
      });
    } else if (!isDir(directory === "" ? "." : directory)) {
      throw new IntegrityError("store does not exist; explicit create required");
    }
    this.lock(() => this.load());
  }

  /** Python opens memory.lock ("a+b") and flocks it. Node cannot flock: the file is opened (so a lock
   * path that is a directory still fails as LockError) but NO cross-process exclusion is provided. */
  private lock<T>(f: () => T): T {
    let fd: number;
    try {
      fd = fs.openSync(path.join(this.directory, "memory.lock"), "a+");
    } catch (e) {
      throw new LockError(`cannot open lock file: ${(e as Error).message}`);
    }
    try {
      return f();
    } finally {
      fs.closeSync(fd);
    }
  }

  private encode(state: Value): Buffer {
    const body = canonical(new Map<string, Value>([["payload", state], ["sha256", digest(state)]]));
    return Buffer.concat([body, Buffer.from("\n")]);
  }

  private validate(s: Value): asserts s is Obj {
    if (!isObj(s) || !keysAre(s, ["schema", "generation", "next_id", "max_records", "max_bytes", "records"]) ||
        !isInt(s.get("schema")) || getI(s, "schema") !== 1n) {
      throw new ValueError("invalid snapshot schema");
    }
    for (const k of ["generation", "next_id", "max_records", "max_bytes"]) {
      const v = s.get(k);
      if (!isInt(v) || !((k === "generation" ? 0n : 1n) <= v.v && v.v <= MAX_COUNTER)) {
        throw new ValueError("invalid snapshot counters");
      }
    }
    if (!(1024n <= getI(s, "max_bytes") && getI(s, "max_bytes") <= BigInt(READ_LIMIT))) {
      throw new ValueError("stored max_bytes outside supported range");
    }
    const rs = s.get("records");
    if (!Array.isArray(rs) || BigInt(rs.length) > getI(s, "max_records")) throw new ValueError("record bound violated");
    const ids = new Set<bigint>();
    const byId = new Map<bigint, Obj>();
    for (const r of rs) {
      if (!isObj(r) || !keysAre(r, RECORD_FIELDS)) throw new ValueError("invalid record schema");
      const i = r.get("id");
      if (!isInt(i) || !(0n < i.v && i.v < getI(s, "next_id")) || ids.has(i.v)) throw new ValueError("invalid or duplicate id");
      ids.add(i.v);
      byId.set(i.v, r);
      for (const k of ["key", "value", "text"]) nonempty(r.get(k), k);
      validateProvenance(r.get("provenance"));
      const t = number(r.get("timestamp"), "timestamp");
      number(r.get("recorded_at"), "recorded_at", t);
      number(r.get("weight"), "weight", 0, 1);
      const st = r.get("status");
      if (typeof r.get("protected") !== "boolean" || !(st === "current" || st === "superseded" || st === "revoked")) {
        throw new ValueError("invalid record status");
      }
      vector(r.get("embedding"));
      if (Math.abs(pySum((r.get("embedding") as Value[]).map((x) => toF(x as number) * toF(x as number))) - 1) > 1e-8) {
        throw new ValueError("unnormalized embedding");
      }
      const sup = r.get("supersedes");
      if (sup !== null && (!isInt(sup) || sup.v >= i.v)) throw new ValueError("invalid correction link");
      const rev = r.get("revocation");
      if (st === "revoked") {
        if (!isObj(rev) || !keysAre(rev, ["reason", "provenance", "at"])) throw new ValueError("invalid revocation");
        nonempty(rev.get("reason"), "reason");
        validateProvenance(rev.get("provenance"));
        number(rev.get("at"), "revocation time", t);
      } else if (rev !== null) {
        throw new ValueError("unexpected revocation");
      }
    }
    const referenced = new Set<bigint>();
    for (const r of rs as Obj[]) {
      const target = r.get("supersedes");
      if (target !== null) {
        const tv = (target as PyInt).v;
        const tr = byId.get(tv);
        if (tr === undefined || !sameKey(tr.get("key"), r.get("key")) || referenced.has(tv)) {
          throw new ValueError("missing, cross-key, or forked correction");
        }
        if (tr.get("status") !== "superseded" || toF(tr.get("timestamp") as number) > toF(r.get("timestamp") as number)) {
          throw new ValueError("invalid supersession");
        }
        referenced.add(tv);
      }
    }
    if ((rs as Obj[]).some((r) => r.get("status") === "superseded" && !referenced.has(getI(r, "id")))) {
      throw new ValueError("orphan supersession");
    }
    if (BigInt(this.encode(s).length) > getI(s, "max_bytes")) throw new ValueError("byte bound violated");
  }

  private load(): Obj {
    try {
      if (fs.statSync(this.path).size > READ_LIMIT) throw new ValueError("snapshot exceeds reader hard limit");
      const env = parseBytes(fs.readFileSync(this.path));
      if (!isObj(env) || !keysAre(env, ["payload", "sha256"])) throw new ValueError("invalid envelope");
      const s = env.get("payload")!;
      if (env.get("sha256") !== digest(s)) throw new ValueError("checksum mismatch");
      this.validate(s);
      return s;
    } catch (e) {
      throw new IntegrityError(`${(e as Error).constructor.name}: ${(e as Error).message}`);
    }
  }

  private commit(state: Obj): void {
    this.validate(state);
    const data = this.encode(state);
    if (data.length > READ_LIMIT) throw new CapacityError("snapshot would exceed the reader limit; no write committed");
    let replaced = false;
    try {
      os(() => {
        const fd = fs.openSync(this.pending, "w");
        try {
          fs.fchmodSync(fd, 0o600);
          fs.writeSync(fd, data);
          fs.fsyncSync(fd);
        } finally {
          fs.closeSync(fd);
        }
      });
      os(() => fs.renameSync(this.pending, this.path));
      replaced = true;
      os(() => {
        const dfd = fs.openSync(this.directory === "" ? "." : this.directory, "r");
        try {
          fs.fsyncSync(dfd);
        } finally {
          fs.closeSync(dfd);
        }
      });
    } catch (e) {
      if (replaced) throw new CommitUncertain("replaced but acknowledgement failed");
      throw e;
    }
  }

  snapshot(): Obj {
    return this.lock(() => deepCopy(this.load()) as Obj);
  }

  storageStatus(): Obj {
    return this.lock(() => {
      const s = this.load();
      return new Map<string, Value>([
        ["generation", s.get("generation")!], ["records", int(recs(s).length)],
        ["bytes", int(os(() => fs.statSync(this.path).size))],
        ["max_records", s.get("max_records")!], ["max_bytes", s.get("max_bytes")!],
        ["incomplete_storage_detected", fs.existsSync(this.pending)],
      ]);
    });
  }

  cleanupIncomplete(): void {
    this.lock(() => {
      this.load();
      os(() => fs.rmSync(this.pending, { force: true }));
    });
  }

  put(key: Value, value: Value, provenance: Value | undefined, o: PutOpts = {}): bigint {
    const thermal = o.thermal_state ?? "NOMINAL";
    if (!(thermal === "NOMINAL" || thermal === "THROTTLE" || thermal === "SCAR_LOCK")) {
      throw new ValueError("unknown resource state");
    }
    if (thermal === "SCAR_LOCK") throw new RuntimeError("resource gate closed, including protected writes");
    const k = identifier(key, "key");
    const val = nonempty(value, "value");
    const p = newProvenance(provenance);
    const w = number(o.weight ?? 1.0, "weight", 0, 1);
    const prot = o.protected ?? false;
    if (typeof prot !== "boolean") throw new ValueError("protected must be boolean");
    const now = number(this.clock(), "clock");
    const ts = o.timestamp === undefined || o.timestamp === null ? now : number(o.timestamp, "timestamp", 0, now);
    const txt = nonempty(o.text !== undefined && o.text !== null ? o.text : `${k} ${val}`, "text");
    let emb = o.embedding === undefined || o.embedding === null ? null : vector(o.embedding);
    const floor = pyLen(k) + pyLen(val) + pyLen(txt);
    if (floor > READ_LIMIT) throw new CapacityError("record cannot fit in any store; no write committed");
    const sup = o.supersedes ?? null;
    const checkTarget = (s: Obj): Obj | null => {
      if (sup === null) return null;
      const targets = recs(s).filter((r) => pyEq(r.get("id")!, sup));
      if (targets.length === 0 || !isInt(sup)) throw new ValueError("unknown correction target");
      const old = targets[0];
      if (old.get("status") !== "current" || !sameKey(old.get("key"), k) || toF(old.get("timestamp") as number) > ts) {
        throw new ValueError("correction requires current same-key predecessor");
      }
      return old;
    };
    this.lock(() => {
      const s = this.load();
      if (BigInt(recs(s).length) >= getI(s, "max_records")) throw new CapacityError("record capacity exhausted; no write committed");
      checkTarget(s);
      if (this.encode(s).length + floor > Number(getI(s, "max_bytes"))) {
        throw new CapacityError("byte capacity exhausted; no write committed");
      }
    });
    if (emb === null) emb = hashEmbedding(txt);
    const embedding = emb;
    return this.lock(() => {
      const s = this.load();
      if (BigInt(recs(s).length) >= getI(s, "max_records")) throw new CapacityError("record capacity exhausted; no write committed");
      const old = checkTarget(s);
      if (old !== null) old.set("status", "superseded");
      const i = getI(s, "next_id");
      recs(s).push(new Map<string, Value>([
        ["id", new PyInt(i)], ["key", k], ["value", val], ["text", txt], ["provenance", p], ["timestamp", ts],
        ["recorded_at", now], ["weight", w], ["protected", prot], ["status", "current"], ["supersedes", sup],
        ["revocation", null], ["embedding", embedding],
      ]));
      bump(s, "next_id");
      bump(s, "generation");
      if (BigInt(this.encode(s).length) > getI(s, "max_bytes")) throw new CapacityError("byte capacity exhausted; no write committed");
      this.commit(s);
      return i;
    });
  }

  correct(recordId: Value, value: Value, provenance: Value | undefined, o: PutOpts = {}): bigint {
    if (!isInt(recordId) || recordId.v < 1n) throw new ValueError("positive integer record ID required");
    const s = this.snapshot();
    const target = recs(s).find((r) => getI(r, "id") === recordId.v);
    if (target === undefined) throw new ValueError("unknown correction target");
    return this.put(target.get("key")!, value, provenance, { ...o, supersedes: recordId });
  }

  revoke(recordId: Value, reason: Value, provenance: Value | undefined): void {
    if (!isInt(recordId) || recordId.v < 1n) throw new ValueError("positive integer record ID required");
    const why = nonempty(reason, "reason");
    const p = newProvenance(provenance);
    this.lock(() => {
      const s = this.load();
      const r = recs(s).find((x) => getI(x, "id") === recordId.v);
      if (r === undefined || r.get("status") !== "current") throw new ValueError("revocation requires a current record");
      r.set("status", "revoked");
      const now = number(this.clock(), "clock");
      // Python max(now, r["timestamp"]) returns the stored object itself when it is larger, so an int
      // timestamp stays an int (SML-TS-002; found by D7 after ChatGPT's report).
      const ts = r.get("timestamp")!;
      r.set("revocation", new Map<string, Value>([["reason", why], ["provenance", p], ["at", toF(ts as number) > now ? ts : now]]));
      bump(s, "generation");
      if (BigInt(this.encode(s).length) > getI(s, "max_bytes")) throw new CapacityError("revocation does not fit; original unchanged");
      this.commit(s);
    });
  }

  compact(target: Value): bigint[] {
    if (!isInt(target) || target.v < 0n) throw new ValueError("invalid target_records");
    return this.lock(() => {
      const s = this.load();
      const groups = new Map<bigint, Obj[]>();
      const roots = new Map<bigint, bigint>();
      for (const r of [...recs(s)].sort((a, b) => cmpBig(getI(a, "id"), getI(b, "id")))) {
        const sup = r.get("supersedes");
        const root = sup !== null ? roots.get((sup as PyInt).v)! : getI(r, "id");
        roots.set(getI(r, "id"), root);
        if (!groups.has(root)) groups.set(root, []);
        groups.get(root)!.push(r);
      }
      // Weights may be ints in a valid file (SML-TS-002): compare numerically, never as objects.
      const maxW = (g: Obj[]) => g.reduce((m, r) => { const w = toF(r.get("weight") as number); return w > m ? w : m; }, -Infinity);
      const removable = [...groups.values()].filter((g) => !g.some((r) => r.get("protected") === true))
        .sort((a, b) => maxW(a) - maxW(b) || cmpBig(getI(a[0], "id"), getI(b[0], "id")));
      const removed: bigint[] = [];
      let count = BigInt(recs(s).length);
      for (const g of removable) {
        if (count <= target.v) break;
        removed.push(...g.map((r) => getI(r, "id")));
        count -= BigInt(g.length);
      }
      if (count > target.v) throw new CapacityError("protected chains prevent compaction; unchanged");
      if (removed.length) {
        const gone = new Set(removed);
        s.set("records", recs(s).filter((r) => !gone.has(getI(r, "id"))));
        bump(s, "generation");
        this.commit(s);
      }
      return removed;
    });
  }

  retrieve(query: Value, o: RetrieveOpts = {}): Hit[] {
    return this.retrieveFrom(this.snapshot(), query, o);
  }

  retrieveFrom(snapshot: Obj, query: Value, o: RetrieveOpts = {}): Hit[] {
    const method = o.method !== undefined ? o.method : "similarity";
    if (typeof method !== "string" || !METHODS.includes(method)) throw new ValueError("unknown retrieval method");
    const topK = o.top_k !== undefined ? o.top_k : int(5);
    if (!isInt(topK) || !(1n <= topK.v && topK.v <= 100n)) throw new ValueError("invalid top_k");
    const threshold = number(o.threshold !== undefined ? o.threshold : 0.15, "threshold", 0, 1);
    const halfLife = number(o.half_life !== undefined ? o.half_life : int(30 * 86400), "half_life", 1e-9);
    const now = number(this.clock(), "clock");
    const q = o.embedding === undefined || o.embedding === null ? hashEmbedding(query) : vector(o.embedding);
    const key = o.key !== undefined ? o.key : null;
    const out: Hit[] = [];
    for (const r of recs(snapshot)) {
      if (r.get("status") !== "current") continue;
      if ((key !== null && !sameKey(r.get("key"), key)) || toF(r.get("timestamp") as number) > now) continue;
      const e = r.get("embedding") as Value[];
      const dot = pySum(q.map((x, j) => x * toF(e[j] as number)));
      const lo = dot < 1.0 ? dot : 1.0; // Python min(1.0, dot)
      const sim = lo > -1.0 ? lo : -1.0; // Python max(-1.0, lo)
      const age = now - toF(r.get("timestamp") as number);
      // PDX-001: a protected record is exempt from the decay factor, so age cannot hide it.
      const decay = r.get("protected") === true ? 1.0 : exp((-LN2 * age) / halfLife);
      const w = toF(r.get("weight") as number);
      let score = sim;
      if (method !== "similarity") score *= decay;
      if (method === "importance" || method === "protected") score *= w;
      if (score > threshold) out.push({ record: r, score });
    }
    out.sort((a, b) => (b.score > a.score ? 1 : b.score < a.score ? -1 : cmpBig(getI(a.record, "id"), getI(b.record, "id"))));
    return out.slice(0, Number(topK.v));
  }

  recall(key: Value, query: Value | undefined, o: RetrieveOpts = {}):
      { status: string; reason?: string; value?: string; evidence_ids: bigint[]; retrieval?: Hit[] } {
    if (typeof key !== "string" || pyBlank(key)) throw new ValueError("recall requires a non-empty string key");
    const s = this.snapshot();
    const current = recs(s).filter((r) => sameKey(r.get("key"), key) && r.get("status") === "current");
    if (new Set(current.map((r) => r.get("value") as string)).size > 1) {
      return { status: "UNKNOWN", reason: "contradictory_current_evidence", evidence_ids: current.map((r) => getI(r, "id")) };
    }
    const q = pyTruthy(query) ? (query as Value) : key; // Python: query or key (SML-TS-003 F5)
    const hits = this.retrieveFrom(s, q, { ...o, key });
    if (hits.length === 0) {
      // PDX-001: stored current evidence that retrieval did not return is not "no evidence".
      if (current.length > 0) {
        return { status: "UNKNOWN", reason: "current_evidence_not_retrieved", evidence_ids: current.map((r) => getI(r, "id")) };
      }
      return { status: "UNKNOWN", reason: "insufficient_evidence", evidence_ids: [] };
    }
    return { status: "KNOWN", value: hits[0].record.get("value") as string,
      evidence_ids: hits.map((h) => getI(h.record, "id")), retrieval: hits };
  }
}

function isDir(p: string): boolean {
  try {
    return fs.statSync(p).isDirectory();
  } catch {
    return false;
  }
}

function cmpBig(a: bigint, b: bigint): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/** Python ==, for a stored int id against a supplied value (bool counts as int, as in Python). Exact:
 * ints are compared as BigInt, never through a double (SML-TS-003 F2, found by ChatGPT: ids above 2^53
 * collided with their neighbours). */
function pyEq(a: Value, b: Value): boolean {
  const big = (x: Value): bigint | number | null =>
    typeof x === "boolean" ? (x ? 1n : 0n) : isInt(x) ? x.v : typeof x === "number" ? (Number.isInteger(x) ? BigInt(x) : x) : null;
  const x = big(a);
  const y = big(b);
  if (x === null || y === null) return false;
  if (typeof x === "bigint" && typeof y === "bigint") return x === y;
  return Number(x) === Number(y); // a non-integral float equals no int
}

/** Python truthiness (for `query or key`; SML-TS-003 F5). */
function pyTruthy(v: Value | undefined): boolean {
  if (v === undefined || v === null || v === false) return false;
  if (v === true) return true;
  if (isInt(v)) return v.v !== 0n;
  if (typeof v === "number") return v !== 0;
  if (typeof v === "string" || Array.isArray(v)) return v.length > 0;
  if (isObj(v)) return v.size > 0;
  return true;
}
