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
        r = m.recall(op.get("key", ""), op.get("query"), **ropts(op))
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


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            res = {"ok": True, "result": run(json.loads(line))}
        except Exception as e:  # noqa: BLE001
            cls = next((n for n, c in CLASSES if isinstance(e, c)), type(e).__name__)
            res = {"ok": False, "error": cls}
        sys.stdout.write(json.dumps(res, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
