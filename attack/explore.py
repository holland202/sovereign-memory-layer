#!/usr/bin/env python3
"""SML-ATK-001 EXPLORATORY attacks, added after run 1 (not in the registered plan; C-EXPLORE).

E1  Unicode normalization: the same visible key in NFC and NFD forms. Can a contradiction be hidden?
E2  Control and bidi-format characters in keys and provenance (display spoofing in explanations).
E3  Exceptions (not kills) injected at each commit stage: state unchanged before replace,
    CommitUncertain and a poisoned instance after replace.
E4  8 threads x 40 puts on ONE MemoryStore instance.
E5  Storage cost: bytes per record at the default max_bytes (embedding stored as 384 floats).
Usage: python3 attack/explore.py --target DIR
"""
import argparse
import hashlib
import json
import sys
import tempfile
import threading
import unicodedata
from pathlib import Path

P = {"source": "synthetic-atk", "locator": "atk-1", "sha256": hashlib.sha256(b"atk").hexdigest()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.target).resolve()))
    import sml.memory as M
    out = {}

    with tempfile.TemporaryDirectory() as td:  # E1
        m = M.MemoryStore(Path(td) / "s", create=True, clock=lambda: 1000)
        nfc, nfd = unicodedata.normalize("NFC", "café"), unicodedata.normalize("NFD", "café")
        try:
            m.put(nfc, "open", provenance=P)
            m.put(nfd, "closed", provenance=P)
            r = m.recall(nfc, threshold=0.0)
            out["E1"] = {"keys_differ_bytewise": nfc != nfd, "recall_nfc": r["status"] + ":" + str(r.get("value", r.get("reason"))),
                         "outcome": "defect_contradiction_hidden" if r["status"] == "KNOWN" else "clean"}
        except ValueError as e:
            out["E1"] = {"outcome": "clean_rejected", "detail": str(e)}

    with tempfile.TemporaryDirectory() as td:  # E2
        m = M.MemoryStore(Path(td) / "s", create=True, clock=lambda: 1000)
        res = {}
        for label, s in {"nul": "a\x00b", "bidi_override": "‮evil", "zero_width": "a​b", "newline": "a\nb"}.items():
            for field in ("key", "source", "locator"):
                try:
                    if field == "key":
                        m.put(s, "v", provenance=P)
                    else:
                        m.put("k", "v", provenance={**P, field: s})
                    res[f"{field}:{label}"] = "accepted"
                except ValueError:
                    res[f"{field}:{label}"] = "rejected"
        out["E2"] = {"results": res, "outcome": "accepts_invisible_or_control" if "accepted" in res.values() else "clean"}

    stages = ["partial_write", "after_file_fsync", "after_replace", "after_dir_fsync"]
    e3 = {}
    for stage in stages:  # E3
        with tempfile.TemporaryDirectory() as td:
            def fault(s, stage=stage):
                if s == stage:
                    raise OSError(28, "No space left on device (injected)")
            path = Path(td) / "s"
            M.MemoryStore(path, create=True, clock=lambda: 1000).put("old", "v", provenance=P)
            m = M.MemoryStore(path, clock=lambda: 1000, fault=fault)
            before = m.path.read_bytes()
            try:
                m.put("new", "v", provenance=P)
                got = "no_error"
            except M.CommitUncertain:
                got = "CommitUncertain"
            except OSError:
                got = "OSError"
            changed = m.path.read_bytes() != before
            try:
                m.snapshot()
                poisoned = False
            except M.CommitUncertain:
                poisoned = True
            reopened = [r["key"] for r in M.MemoryStore(path).snapshot()["records"]]
            e3[stage] = {"raised": got, "file_changed": changed, "instance_poisoned": poisoned, "reopened_keys": reopened}
    ok = all((v["raised"] == "OSError" and not v["file_changed"] and not v["instance_poisoned"])
             if s in stages[:2] else (v["raised"] == "CommitUncertain" and v["instance_poisoned"]) for s, v in e3.items())
    out["E3"] = {"stages": e3, "outcome": "clean" if ok else "defect"}

    with tempfile.TemporaryDirectory() as td:  # E4
        m = M.MemoryStore(Path(td) / "s", create=True, max_records=1000, clock=lambda: 1000)
        errors = []

        def work(k):
            try:
                for i in range(40):
                    m.put(f"t{k}.{i}", "v", provenance=P)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{type(e).__name__}: {e}")
        ts = [threading.Thread(target=work, args=(k,)) for k in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        ids = [r["id"] for r in M.MemoryStore(Path(td) / "s").snapshot()["records"]]
        out["E4"] = {"records": len(ids), "unique": len(set(ids)), "errors": errors[:2],
                     "outcome": "clean" if len(ids) == 320 == len(set(ids)) and not errors else "defect"}

    with tempfile.TemporaryDirectory() as td:  # E5
        m = M.MemoryStore(Path(td) / "s", create=True, clock=lambda: 1000)
        n = 0
        try:
            while n < 5000:
                m.put(f"fact.{n}", f"a typical short value number {n}", provenance=P)
                n += 1
        except M.CapacityError:
            pass
        out["E5"] = {"records_at_default_caps": n, "bytes": m.path.stat().st_size,
                     "bytes_per_record": round(m.path.stat().st_size / max(n, 1)), "outcome": "observed"}

    for k, v in out.items():
        print(f"{k}: {v['outcome']} {json.dumps({x: y for x, y in v.items() if x != 'outcome'}, default=str)[:700]}")


if __name__ == "__main__":
    main()
