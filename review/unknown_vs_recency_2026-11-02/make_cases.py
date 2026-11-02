#!/usr/bin/env python3
"""UVR-001: write cases.jsonl exactly as Amendment 1 fixes it, before either policy runs.
One line per key: block, key, true value, false value, and the write plan. No policy output here."""
import json, random, sys
from pathlib import Path

rng = random.Random(20261102)
out = []
for q in (0.0, 0.25, 0.5, 0.75, 1.0):
    keys = [f"q{int(q * 100):03d}.k{i:03d}" for i in range(200)]
    order = keys[:]
    rng.shuffle(order)
    newest_wrong = set(order[:round(q * 200)])
    for i, k in enumerate(keys):
        older = 1000.0 + i
        newer = older + 10.0
        wrong_new = k in newest_wrong
        out.append({"block": "P1", "q": q, "key": k, "true": f"true.{k}", "false": f"false.{k}",
                    "writes": [{"how": "put", "value": "true" if wrong_new else "false", "timestamp": older},
                               {"how": "put", "value": "false" if wrong_new else "true", "timestamp": newer}]})
for i in range(200):
    k = f"p2.k{i:03d}"
    out.append({"block": "P2", "q": None, "key": k, "true": f"true.{k}", "false": f"false.{k}",
                "writes": [{"how": "put", "value": "false", "timestamp": 1000.0 + i},
                           {"how": "correct", "value": "true", "timestamp": 1010.0 + i}]})
for i in range(200):
    k = f"p3.k{i:03d}"
    out.append({"block": "P3", "q": None, "key": k, "true": f"true.{k}", "false": f"false.{k}",
                "writes": [{"how": "put", "value": "true", "timestamp": 1000.0 + i},
                           {"how": "put", "value": "false", "timestamp": 1000.0 + i + 1_000_000.0}]})
Path(sys.argv[1] if len(sys.argv) > 1 else "cases.jsonl").write_text(
    "".join(json.dumps(c, sort_keys=True) + "\n" for c in out))
print(len(out), "cases")
