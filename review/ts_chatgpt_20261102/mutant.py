#!/usr/bin/env python3
"""Deliberately broken port wrapper: lie about every successful put ID."""
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
p = subprocess.Popen(["node", str(root / "ts/src/cli.ts")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     text=True, bufsize=1)
for line in sys.stdin:
    p.stdin.write(line)
    p.stdin.flush()
    response = p.stdout.readline()
    if not response:
        raise RuntimeError("underlying TypeScript port died")
    op = json.loads(line)
    value = json.loads(response)
    if op.get("op") == "put" and value.get("ok"):
        value["result"] += 1
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False), flush=True)
p.stdin.close()
sys.exit(p.wait(timeout=10))
