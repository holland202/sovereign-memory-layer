#!/usr/bin/env python3
"""AI-generated ChatGPT test. Valid Python-created SML files vs Rust reader.

Run from a checked-out, current SML repo after building Rust:
  cargo build --release --manifest-path rust/Cargo.toml
  python3 /path/to/test_large_counter_interop.py --root .

Exit: 0 equal behavior; 1 mismatch; 2 required executable missing/setup failure.
No source under test is modified; temporary synthetic stores are deleted.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile


def call(cmd, op, cwd):
    run = subprocess.run(cmd, input=json.dumps(op, separators=(",", ":"), ensure_ascii=False) + "\n",
                         text=True, capture_output=True, cwd=cwd, timeout=30)
    out = run.stdout.strip()
    print("COMMAND:", " ".join(map(str, cmd)))
    print("INPUT:", json.dumps(op, sort_keys=True, ensure_ascii=False))
    print("EXIT:", run.returncode)
    print("STDOUT:", repr(run.stdout))
    print("STDERR:", repr(run.stderr))
    try:
        response = json.loads(out)
    except (ValueError, TypeError):
        raise RuntimeError("missing or invalid one-line JSON result")
    return response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("."))
    parser.add_argument("--rust-bin", type=pathlib.Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    pycli = root / "tools" / "py_cli.py"
    rustbin = (args.rust_bin or root / "rust" / "target" / "release" / "sml-cli").resolve()
    print("AI-GENERATED: ChatGPT; not an independent human review")
    print("PYTHON:", sys.version.replace("\n", " "))
    print("REPO:", root)
    if not pycli.is_file():
        print("NOT RUN: Python line-protocol script absent:", pycli)
        return 2
    if not rustbin.is_file():
        print("NOT RUN: Rust CLI absent; build it with cargo build --release --manifest-path rust/Cargo.toml:", rustbin)
        return 2
    failed = False
    with tempfile.TemporaryDirectory(prefix="sml-chatgpt-counter-") as tmp:
        for cap in (2**63 - 1, 2**63):
            store = pathlib.Path(tmp) / f"cap_{cap}"
            print("\nCASE max_records =", cap)
            create = {"op": "create", "dir": str(store), "max_records": cap,
                      "max_bytes": 2_000_000, "clock": 1000.0}
            py_create = call([sys.executable, str(pycli), str(root)], create, root)
            if py_create != {"ok": True, "result": None}:
                print("UNEXPECTED Python create result:", py_create)
                failed = True
                continue
            raw = (store / "memory.json").read_bytes()
            print("FILE_SHA256_BEFORE:", hashlib.sha256(raw).hexdigest())
            status = {"op": "status", "dir": str(store), "clock": 1000.0}
            py_status = call([sys.executable, str(pycli), str(root)], status, root)
            rs_status = call([str(rustbin)], status, root)
            print("PYTHON_RESULT:", json.dumps(py_status, sort_keys=True))
            print("RUST_RESULT:", json.dumps(rs_status, sort_keys=True))
            if py_status != rs_status:
                print("MISMATCH: Python and Rust disagree on Python-created valid snapshot")
                failed = True
            else:
                print("MATCH")
            after = (store / "memory.json").read_bytes()
            print("FILE_UNCHANGED:", raw == after)
            if raw != after:
                failed = True
    print("VERDICT:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
