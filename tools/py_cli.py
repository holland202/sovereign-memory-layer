#!/usr/bin/env python3
"""Python side of the differential line protocol (mirror of rust/src/bin/sml-cli.rs).

One JSON op per stdin line; one canonical JSON result per stdout line. Every op reopens the
store with the clock fixed to the op's "clock". Usage: python3 tools/py_cli.py [REPO_ROOT]
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent)))
from sml import memory as M  # noqa: E402

CLASSES = [("ReentrancyError", M.ReentrancyError), ("CommitUncertain", M.CommitUncertain),
           ("CapacityError", M.CapacityError), ("IntegrityError", M.IntegrityError), ("ValueError", ValueError),
           ("OSError", OSError), ("RuntimeError", RuntimeError)]


def hits(hs):
    return [[h["record"]["id"], repr(h["score"])] for h in hs]


def ropts(op):
    o = {}
    for k in ("method", "top_k", "threshold", "half_life"):
        if k in op:
            o[k] = op[k]
    if "rkey" in op:
        o["key"] = op["rkey"]
    if op.get("qembedding") is not None:
        o["embedding"] = op["qembedding"]
    return o


def popts(op):
    o = {}
    for k in ("timestamp", "text", "weight", "embedding", "thermal_state"):
        if op.get(k) is not None:
            o[k] = op[k]
    o["protected"] = op.get("protected") is True
    if op.get("supersedes") is not None:
        o["supersedes"] = op["supersedes"]
    return o


def run(op):
    d, t, name = op.get("dir", ""), op.get("clock", 1000.0), op.get("op")
    clock = lambda: t  # noqa: E731
    if name == "create":
        M.MemoryStore(d, create=True, max_records=op.get("max_records", 0), max_bytes=op.get("max_bytes", 0), clock=clock)
        return None
    if name == "repr":
        import struct
        return [repr(struct.unpack("<d", bytes.fromhex(h)[::-1])[0]) for h in op["bits"]]
    if name == "file":
        p = Path(d) / "memory.json"
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    m = M.MemoryStore(d, clock=clock)
    prov = op.get("provenance")
    if name == "put":
        return m.put(op.get("key", ""), op.get("value", ""), provenance=prov, **popts(op))
    if name == "correct":
        o = popts(op)
        o.pop("supersedes", None)
        return m.correct(op.get("id", 0), op.get("value", ""), provenance=prov, **o)
    if name == "revoke":
        m.revoke(op.get("id", 0), reason=op.get("reason", ""), provenance=prov)
        return None
    if name == "compact":
        return m.compact(op.get("target", 0))
    if name == "retrieve":
        return hits(m.retrieve(op.get("query", ""), **ropts(op)))
    if name == "recall":
        # SML-TS-003 F6 (found by ChatGPT): rkey is a retrieve option; recall's key is the recall key, as the
        # Rust and TypeScript CLIs already treat it. Forwarding it raised a duplicate-keyword TypeError.
        r = m.recall(op.get("key", ""), op.get("query"), **{k: v for k, v in ropts(op).items() if k != "key"})
        out = {"status": r["status"], "evidence_ids": r["evidence_ids"]}
        if r["status"] == "KNOWN":
            out.update(value=r["value"], hits=hits(r["retrieval"]))
        else:
            out["reason"] = r["reason"]
        return out
    if name == "status":
        return m.storage_status()
    if name == "cleanup":
        m.cleanup_incomplete()
        return None
    raise ValueError("unknown op")


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate field")
        out[k] = v
    return out


def _has_lone_surrogate(x):
    if isinstance(x, str):
        return any("\ud800" <= ch <= "\udfff" for ch in x)
    if isinstance(x, list):
        return any(_has_lone_surrogate(v) for v in x)
    if isinstance(x, dict):
        return any(_has_lone_surrogate(k) or _has_lone_surrogate(v) for k, v in x.items())
    return False


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            try:
                op = json.loads(line, object_pairs_hook=_no_duplicates)
                # SML-TS-003 F8 (found by ChatGPT): a lone-surrogate escape is refused at parse time, as the
                # Rust and TypeScript CLIs do. The store's own ValueError for such strings is unchanged.
                if _has_lone_surrogate(op):
                    raise ValueError("lone surrogate in request")
            except ValueError:  # bad JSON, duplicate fields or a BOM (R3-04): same as the Rust side
                res = {"ok": False, "error": "BadOp"}
            else:
                res = {"ok": True, "result": run(op)}
        except Exception as e:  # noqa: BLE001
            cls = next((n for n, c in CLASSES if isinstance(e, c)), type(e).__name__)
            res = {"ok": False, "error": cls}
        sys.stdout.write(json.dumps(res, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
