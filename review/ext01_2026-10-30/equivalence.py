#!/usr/bin/env python3
"""EXT-01 N5: the EXT-01 change alters nothing except refusing earlier.

  python3 review/ext01_2026-10-30/equivalence.py --old PATH_TO_PRE_FIX_TREE

(a) 20,000 random texts: hash_embedding identical (bit for bit) in the old and new code.
(b) 300 random operation sequences (tools/differential.py's generator, plus near-limit writes) run
    on the old and the new Python store: every output line and file must be identical, except a
    refusal whose class changed because the early check now runs before argument checks that come
    later in put(); each such case is printed for inspection.
"""
import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

NEW = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NEW / "tools"))
import differential as D  # noqa: E402


def load(root, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, Path(root) / "sml" / "memory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    a = ap.parse_args()
    old, new = load(a.old, "sml_old"), load(NEW, "sml_new")
    rng = random.Random(5150)
    alphabet = ["a", "b", " ", "\t", "\n", "\x1c", "　", " ", "Σ", "ς", "İ", "é", "🙂", "Z", " ", "x y"]
    diff_emb = 0
    for _ in range(20000):
        t = "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 40)))
        if not t.strip():
            continue
        if old.hash_embedding(t) != new.hash_embedding(t):
            diff_emb += 1
    print(f"(a) embeddings differing old vs new: {diff_emb} of 20000 random texts")

    py_old = D.Side([sys.executable, str(Path(a.old) / "tools/py_cli.py"), a.old])
    py_new = D.Side([sys.executable, str(NEW / "tools/py_cli.py"), str(NEW)])
    mism, class_changes, ops = [], [], 0
    with tempfile.TemporaryDirectory() as td:
        for sq in range(300):
            seq = D.gen_ops(rng, "@", 50)
            for _ in range(5):  # near-limit writes: big values against small stores
                seq.insert(rng.randrange(1, len(seq)), {"op": "put", "key": "big", "value": "v " * rng.choice([500, 1500, 3000, 6000]),
                                                        "provenance": D.PROV, "clock": 5000.0,
                                                        **({"embedding": [0.0] * 384} if rng.random() < 0.3 else {})})
            for op in seq:
                x = py_old({**op, "dir": f"{td}/o{sq}"})
                y = py_new({**op, "dir": f"{td}/n{sq}"})
                ops += 1
                if x != y:
                    jx, jy = json.loads(x), json.loads(y)
                    if not jx["ok"] and not jy["ok"] and op["op"] == "put":
                        class_changes.append({"old": jx["error"], "new": jy["error"], "value_len": len(op.get("value", "")),
                                              "embedding_supplied": "embedding" in op})
                        continue
                    mism.append({"seq": sq, "op": op["op"], "old": x[:150], "new": y[:150]})
                    break
                fx, fy = py_old({"op": "file", "dir": f"{td}/o{sq}"}), py_new({"op": "file", "dir": f"{td}/n{sq}"})
                if fx != fy:
                    mism.append({"seq": sq, "after": op["op"], "file_differs": True})
                    break
    py_old.close()
    py_new.close()
    kinds = {}
    for c in class_changes:
        k = f"{c['old']} -> {c['new']} (embedding supplied: {c['embedding_supplied']})"
        kinds[k] = kinds.get(k, 0) + 1
    print(f"(b) {ops} operations; mismatches other than refusal-class changes: {len(mism)} {mism[:3]}")
    print(f"    refusal-class changes: {len(class_changes)} {kinds}")
    sys.exit(0 if diff_emb == 0 and not mism else 1)


if __name__ == "__main__":
    main()
