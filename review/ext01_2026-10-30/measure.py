#!/usr/bin/env python3
"""EXT-01 measurements N1-N4 (see PREREG.md). Each N1/N2 case runs in a fresh subprocess so peak RSS
is per case. Usage: python3 review/ext01_2026-10-30/measure.py [--target REPO_ROOT]"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

CHILD = r'''
import hashlib, json, os, resource, sys, tempfile, time
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from sml.memory import MemoryStore, CapacityError
mb, max_bytes = float(sys.argv[2]), int(sys.argv[3])
P = {"source": "synthetic-ext01", "locator": "n-1", "sha256": hashlib.sha256(b"n").hexdigest()}
value = "a " * int(mb * 1_000_000 / 2)          # 1-character words: the costliest case for split()
with tempfile.TemporaryDirectory() as td:
    m = MemoryStore(Path(td) / "s", create=True, max_bytes=max_bytes, clock=lambda: 1000)
    before = m.path.read_bytes()
    base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    c0, t0 = time.process_time(), time.perf_counter()
    try:
        m.put("k", value, provenance=P)
        outcome = "stored"
    except CapacityError:
        outcome = "CapacityError"
    except Exception as e:
        outcome = type(e).__name__
    cpu, wall = time.process_time() - c0, time.perf_counter() - t0
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    unchanged = m.path.read_bytes() == before
    print(json.dumps({"input_mb": mb, "outcome": outcome, "snapshot_unchanged": unchanged,
                      "peak_rss_growth_mb": round((peak - base) / 1024, 1), "cpu_s": round(cpu, 3), "wall_s": round(wall, 3)}))
'''

LOCK = r'''
import fcntl, hashlib, json, sys, tempfile
sys.path.insert(0, sys.argv[1])
from pathlib import Path
import sml.memory as M
P = {"source": "synthetic-ext01", "locator": "n-1", "sha256": hashlib.sha256(b"n").hexdigest()}
mode = sys.argv[2]
real = fcntl.flock
with tempfile.TemporaryDirectory() as td:
    m = M.MemoryStore(Path(td) / "s", create=True, clock=lambda: 1000)
    before = m.path.read_bytes()
    def fake(fd, op):
        if (mode == "lock_ex" and op == fcntl.LOCK_EX) or (mode == "unlock" and op == fcntl.LOCK_UN):
            raise OSError(37, "No locks available (injected)")
        return real(fd, op)
    M.fcntl.flock = fake
    try:
        r = m.put("k", "v", provenance=P)
        outcome = f"returned id {r}"
    except Exception as e:
        outcome = f"raised {type(e).__name__}"
    M.fcntl.flock = real
    recs = M.MemoryStore(Path(td) / "s").snapshot()["records"]
    print(json.dumps({"inject": mode, "outcome": outcome, "records_on_disk": len(recs),
                      "snapshot_unchanged": m.path.read_bytes() == before}))
'''


def run(code, *args):
    p = subprocess.run([sys.executable, "-c", code, *map(str, args)], capture_output=True, text=True, timeout=900)
    if p.returncode:
        return {"error": p.stderr[-400:]}
    return json.loads(p.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=str(Path(__file__).resolve().parents[2]))
    a = ap.parse_args()
    print(f"target {a.target} | python {sys.version.split()[0]}")
    for mb in (1, 4, 16):
        print("N1", json.dumps(run(CHILD, a.target, mb, 4096)))
    print("N2", json.dumps(run(CHILD, a.target, 4, 16_000_000)))
    print("N3", json.dumps(run(LOCK, a.target, "lock_ex")))
    print("N4", json.dumps(run(LOCK, a.target, "unlock")))


if __name__ == "__main__":
    main()
