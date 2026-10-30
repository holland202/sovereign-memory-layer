#!/usr/bin/env python3
"""P3-01 follow-up (Claude): a store whose counter sits at 2^63-1 receives one more write.

Self-tested. Synthetic stores only. Run from the repo root after building the Rust CLI:
  python3 review/p3_01/counter_exhaustion.py
For each counter (next_id, generation) and each implementation, the script writes a valid store with that
counter at 2^63-1, sends a put, then asks BOTH implementations for status.
Pass: the put is refused with CapacityError, the file is unchanged, and Python and Rust then agree on status.
Exit 0 when every case passes, 1 otherwise.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sml.memory import canonical  # noqa: E402

TOP = 2**63 - 1
PROV = {"source": "synthetic-p3", "locator": "p3-1", "sha256": hashlib.sha256(b"p3").hexdigest()}
PY = [sys.executable, str(ROOT / "tools/py_cli.py"), str(ROOT)]
RS = [str(ROOT / "rust/target/release/sml-cli")]


def call(cmd, op):
    r = subprocess.run(cmd, input=json.dumps(op) + "\n", text=True, capture_output=True, timeout=30)
    return r.stdout.strip() or f"<no output; exit {r.returncode}; stderr {r.stderr.strip()[-200:]!r}>"


def main():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        for counter in ("next_id", "generation"):
            for name, cmd in (("python", PY), ("rust", RS)):
                d = f"{td}/{counter}_{name}"
                print(f"\nCASE {counter}=2^63-1, put via {name}")
                print("  create:", call(PY, {"op": "create", "dir": d, "max_records": 10, "max_bytes": 200000}))
                f = Path(d) / "memory.json"
                payload = json.loads(f.read_text())["payload"]
                payload[counter] = TOP
                f.write_bytes(canonical({"payload": payload, "sha256": hashlib.sha256(canonical(payload)).hexdigest()}) + b"\n")
                before = f.read_bytes()
                put = call(cmd, {"op": "put", "dir": d, "key": "k", "value": "v", "provenance": PROV, "clock": 1000.0})
                after = f.read_bytes()
                st_py = call(PY, {"op": "status", "dir": d})
                st_rs = call(RS, {"op": "status", "dir": d})
                print("  put:", put)
                print("  file unchanged:", before == after)
                print("  status python:", st_py)
                print("  status rust:  ", st_rs)
                good = '"CapacityError"' in put and before == after and st_py == st_rs
                print("  PASS" if good else "  FAIL")
                ok &= good
    print("\nVERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
