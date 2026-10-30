#!/usr/bin/env python3
"""SML-RS-001 differential tests: Python reference vs Rust port (see rust/PORT_PREREG.md).

Usage:
  python3 tools/differential.py [--quick] [--only D1,D2] [--sabotage]
Builds rust/ (cargo build --release) unless --rust-bin is given. Exit 0 only if every check
selected found no mismatch (or, with --sabotage, only if the sabotaged port WAS caught).
"""
import argparse
import hashlib
import json
import os
import random
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHA = hashlib.sha256(b"diff").hexdigest()
PROV = {"source": "synthetic-diff", "locator": "d-1", "sha256": SHA}


class Side:
    def __init__(self, cmd):
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def __call__(self, op):
        self.p.stdin.write(json.dumps(op, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError(f"side died on {op.get('op')}")
        return line.rstrip("\n")

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=30)


KEYS = ["alpha", "beta", unicodedata.normalize("NFC", "café"), unicodedata.normalize("NFD", "café"), "ΟΔΟΣ", "İstanbul",
        "k x", "", "  ", "a​b", "a\x00b", "emoji🙂key"]
VALUES = ["x", "y", "blue", "line\nbreak", "ΣΑΣ", "  padded  ", "", "\t"]
TEXTS = [None, None, None, "a\x1cb c　d", "ΟΔΟΣ ΟΔΟΣ", "İ i ı I", "word " * 40, "🙂 🙂", "", "MiXeD CaSe words"]
QUERIES = ["alpha", "blue", "café", "ΟΔΟΣ", "line break", "x y", "unrelated words", "İstanbul"]


def gen_ops(rng, d, length):
    clock = 1000.0 + rng.randrange(0, 1000)
    ops = [{"op": "create", "dir": d, "max_records": rng.choice([3, 5, 8, 20]),
            "max_bytes": rng.choice([4096, 12000, 60000, 2_000_000]), "clock": clock}]
    for _ in range(length):
        r = rng.random()
        clock += rng.choice([0.0, 0.5, 1.0, 3.25, 100.0]) if r > 0.08 else -rng.choice([1.0, 500.0])
        op = {"dir": d, "clock": clock}
        kind = rng.choice(["put"] * 5 + ["correct"] * 2 + ["revoke"] * 2 + ["compact", "recall", "recall", "retrieve",
                                                                            "status", "cleanup", "file"])
        op["op"] = kind
        prov = dict(PROV)
        if rng.random() < 0.06:
            prov[rng.choice(["source", "locator"])] = rng.choice(["", "a\nb", "‮evil"])
        if rng.random() < 0.03:
            prov["sha256"] = "ABC"
        if kind == "put":
            op.update(key=rng.choice(KEYS), value=rng.choice(VALUES), provenance=prov)
            if rng.random() < 0.3:
                op["weight"] = rng.choice([0.1, 0.5, 0.9, 1.0, 1.5, -0.1])
            if rng.random() < 0.3:
                op["protected"] = True
            if rng.random() < 0.2:
                op["timestamp"] = clock - rng.choice([0.0, 10.0, -5.0])
            t = rng.choice(TEXTS)
            if t is not None:
                op["text"] = t
            if rng.random() < 0.1:
                op["embedding"] = rng.choice([[rng.uniform(-1, 1) for _ in range(384)], [0.0] * 384, [1.0] * 3,
                                              [rng.choice([1e-150, 3e10, -7.5]) for _ in range(384)]])
            if rng.random() < 0.03:
                op["thermal_state"] = rng.choice(["SCAR_LOCK", "bogus", "THROTTLE"])
        elif kind == "correct":
            op.update(id=rng.randrange(-1, 12), value=rng.choice(VALUES), provenance=prov)
            if rng.random() < 0.15:
                op["timestamp"] = clock - rng.choice([0.0, 50.0])
        elif kind == "revoke":
            op.update(id=rng.randrange(-1, 12), reason=rng.choice(["withdrawn", "", "a\nb"]), provenance=prov)
        elif kind == "compact":
            op["target"] = rng.randrange(-1, 10)
        elif kind in ("recall", "retrieve"):
            if kind == "recall":
                op["key"] = rng.choice(KEYS)
                if rng.random() < 0.5:
                    op["query"] = rng.choice(QUERIES)
            else:
                op["query"] = rng.choice(QUERIES + [""])
                if rng.random() < 0.3:
                    op["rkey"] = rng.choice(KEYS[:7])
            op["method"] = rng.choice(["similarity", "recency", "importance", "protected", "bogus"])
            if rng.random() < 0.7:
                op["threshold"] = rng.choice([0.0, 0.05, 0.15, 0.5, 1.0, 1.5])
            if rng.random() < 0.3:
                op["top_k"] = rng.choice([0, 1, 3, 100, 101])
            if rng.random() < 0.3:
                op["half_life"] = rng.choice([1e-9, 1.0, 3600.0, 1e308, 0.0])
            if rng.random() < 0.05:
                op["qembedding"] = [rng.uniform(-1, 1) for _ in range(384)]
        ops.append(op)
    return ops


def d1_d4(py, rs, n, length, seed, base):
    rng = random.Random(seed)
    mismatches, ops_total = [], 0
    for sq in range(n):
        dp, dr = str(base / f"p{sq}"), str(base / f"r{sq}")
        ops = gen_ops(rng, "@", length)
        for op in ops:
            a = py({**op, "dir": dp})
            b = rs({**op, "dir": dr})
            ops_total += 1
            if a != b:
                mismatches.append({"seq": sq, "op": op["op"], "py": a[:200], "rs": b[:200], "detail": json.dumps(op)[:300]})
                break
            fa, fb = py({"op": "file", "dir": dp}), rs({"op": "file", "dir": dr})
            if fa != fb:
                mismatches.append({"seq": sq, "after": op["op"], "file_py": fa, "file_rs": fb})
                break
        else:
            for q in ("alpha", "café", "ΟΔΟΣ"):  # D4: cross-open
                x = py({"op": "recall", "dir": dr, "key": q, "clock": 1e7, "threshold": 0.0})
                y = rs({"op": "recall", "dir": dp, "key": q, "clock": 1e7, "threshold": 0.0})
                if x != y:
                    mismatches.append({"seq": sq, "cross_open": q, "py_on_rs": x[:200], "rs_on_py": y[:200]})
                    break
    return {"sequences": n, "ops": ops_total, "mismatches": len(mismatches), "first": mismatches[:3]}


def d2(py, rs, n, seed):
    rng = random.Random(seed)
    edge = [0.0, -0.0, 5e-324, 1e-5, 1e-4, 1e16, 1e15, 9999999999999998.0, 1.7976931348623157e308, 2.2250738585072014e-308,
            0.1, 1 / 3, 123456789.123, 1e22, 1e-7]
    vals = [struct.unpack("<Q", struct.pack("<d", x))[0] for x in edge]
    while len(vals) < n:
        b = rng.getrandbits(64)
        if (b >> 52) & 0x7FF != 0x7FF:  # finite only
            vals.append(b)
    bad = 0
    first = []
    for i in range(0, len(vals), 2000):
        chunk = [format(v, "016x") for v in vals[i:i + 2000]]
        a, b = py({"op": "repr", "bits": chunk}), rs({"op": "repr", "bits": chunk})
        if a != b:
            la, lb = json.loads(a)["result"], json.loads(b)["result"]
            for h, x, y in zip(chunk, la, lb):
                if x != y:
                    bad += 1
                    first.append((h, x, y))
    return {"values": len(vals), "mismatches": bad, "first": first[:3]}


def d3(py, rs, seed, base):
    rng = random.Random(seed)
    src = base / "src"
    py({"op": "create", "dir": str(src), "max_records": 20, "max_bytes": 200000, "clock": 1000})
    for i in range(6):
        py({"op": "put", "dir": str(src), "key": f"k{i % 3}", "value": f"v{i}", "provenance": PROV, "clock": 1001 + i,
            "protected": i == 0})
    py({"op": "revoke", "dir": str(src), "id": 2, "reason": "r", "provenance": PROV, "clock": 1010})
    py({"op": "correct", "dir": str(src), "id": 3, "value": "fixed", "provenance": PROV, "clock": 1011})
    good = (src / "memory.json").read_bytes()
    cases = []
    for _ in range(3000):
        b = bytearray(good)
        i = rng.randrange(len(b))
        b[i] = (b[i] + rng.randrange(1, 256)) % 256
        cases.append(bytes(b))
    cases += [good[:rng.randrange(len(good))] for _ in range(400)] + [good[:-1], b"\xef\xbb\xbf" + good]
    bad, classes = [], {}
    for n, data in enumerate(cases):
        for side, name in ((py, "p"), (rs, "r")):
            d = base / f"c_{name}"
            d.mkdir(exist_ok=True)
            (d / "memory.json").write_bytes(data)
        a = py({"op": "status", "dir": str(base / "c_p"), "clock": 2000})
        b = rs({"op": "status", "dir": str(base / "c_r"), "clock": 2000})
        k = json.loads(a).get("error", "ok")
        classes[k] = classes.get(k, 0) + 1
        if a != b:
            bad.append({"case": n, "py": a[:160], "rs": b[:160]})
    return {"cases": len(cases), "outcomes_py": classes, "mismatches": len(bad), "first": bad[:3]}


PY_WRITER = r'''
import sys, json
sys.path.insert(0, sys.argv[1])
from sml.memory import MemoryStore
m = MemoryStore(sys.argv[2])
p = json.loads(sys.argv[4])
for i in range(int(sys.argv[5])):
    m.put(f"py{sys.argv[3]}.{i}", "v", provenance=p)
'''


def d5(rs_bin, base, procs=4, each=30):
    d = base / "conc"
    subprocess.run([sys.executable, str(ROOT / "tools/py_cli.py"), str(ROOT)], input=json.dumps(
        {"op": "create", "dir": str(d), "max_records": 1000, "max_bytes": 16_000_000, "clock": 1000}) + "\n",
        text=True, capture_output=True, check=True)
    ps = [subprocess.Popen([sys.executable, "-c", PY_WRITER, str(ROOT), str(d), str(k), json.dumps(PROV), str(each)])
          for k in range(procs)]
    for k in range(procs):
        lines = "".join(json.dumps({"op": "put", "dir": str(d), "key": f"rs{k}.{i}", "value": "v", "provenance": PROV,
                                    "clock": 1000 + i}) + "\n" for i in range(each))
        ps.append(subprocess.Popen([rs_bin], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True))
        ps[-1].stdin.write(lines)
        ps[-1].stdin.close()
    codes = [p.wait(timeout=600) for p in ps]
    sys.path.insert(0, str(ROOT))
    from sml.memory import MemoryStore
    recs = MemoryStore(d).snapshot()["records"]
    ids = [r["id"] for r in recs]
    rs_status = json.loads(subprocess.run([rs_bin], input=json.dumps({"op": "status", "dir": str(d), "clock": 2000}) + "\n",
                                          text=True, capture_output=True).stdout)
    ok = (codes == [0] * len(codes) and len(ids) == 2 * procs * each and sorted(ids) == list(range(1, 2 * procs * each + 1))
          and rs_status.get("ok") and rs_status["result"]["records"] == 2 * procs * each)
    return {"records": len(ids), "expected": 2 * procs * each, "exit_codes": codes, "rust_reopen_ok": rs_status.get("ok"),
            "mismatches": 0 if ok else 1}


def d6(rs_bin, base, trials=100, seed=5):
    rng = random.Random(seed)
    sys.path.insert(0, str(ROOT))
    from sml.memory import MemoryStore
    problems = []
    acked_total = extra_total = 0
    for t in range(trials):
        d = base / f"kill{t}"
        MemoryStore(d, create=True, max_records=100000, max_bytes=16_000_000)
        p = subprocess.Popen([rs_bin], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        acked = []
        deadline = time.time() + rng.uniform(0.05, 0.4)
        i = 0
        while time.time() < deadline:
            p.stdin.write(json.dumps({"op": "put", "dir": str(d), "key": f"w{i}", "value": "v", "provenance": PROV,
                                      "clock": 1000}) + "\n")
            p.stdin.flush()
            line = p.stdout.readline()
            if json.loads(line).get("ok"):
                acked.append(f"w{i}")
            i += 1
        p.stdin.write(json.dumps({"op": "put", "dir": str(d), "key": f"w{i}", "value": "v", "provenance": PROV,
                                  "clock": 1000}) + "\n")
        p.stdin.flush()
        time.sleep(rng.uniform(0, 0.003))
        p.send_signal(signal.SIGKILL)
        p.wait()
        try:
            keys = {r["key"] for r in MemoryStore(d).snapshot()["records"]}
        except Exception as e:  # noqa: BLE001
            problems.append({"trial": t, "python_reopen": type(e).__name__})
            continue
        r = json.loads(subprocess.run([rs_bin], input=json.dumps({"op": "status", "dir": str(d), "clock": 2000}) + "\n",
                                      text=True, capture_output=True).stdout)
        missing = set(acked) - keys
        extra = keys - set(acked)
        acked_total += len(acked)
        extra_total += len(extra)
        if missing or len(extra) > 1 or not r.get("ok"):
            problems.append({"trial": t, "missing": len(missing), "extra": len(extra), "rust_reopen": r.get("ok")})
    return {"trials": trials, "acked_total": acked_total, "unacked_extra_total": extra_total,
            "mismatches": len(problems), "first": problems[:3]}


def build(rust_dir):
    r = subprocess.run(["cargo", "build", "--release", "--quiet"], cwd=rust_dir, capture_output=True, text=True)
    if r.returncode:
        sys.exit("cargo build failed:\n" + r.stderr[-2000:])
    return str(rust_dir / "target/release/sml-cli")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--sabotage", action="store_true")
    ap.add_argument("--rust-bin")
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    work = Path(tempfile.mkdtemp(prefix="sml-diff-"))
    try:
        if a.sabotage:
            copy = work / "rust-sabotaged"
            shutil.copytree(ROOT / "rust", copy, ignore=shutil.ignore_patterns("target"))
            t = (copy / "src/text.rs").read_text()
            old = "    if c != 0.0 && c.is_finite() {\n        f += c;\n    }"
            assert t.count(old) == 1
            (copy / "src/text.rs").write_text(t.replace(old, "    let _ = c; // SABOTAGE: naive sum"))
            rs_bin = build(copy)
            only = {"D1"}
        else:
            rs_bin = a.rust_bin or build(ROOT / "rust")
        py = Side([sys.executable, str(ROOT / "tools/py_cli.py"), str(ROOT)])
        rs = Side([rs_bin])
        n, length = (40, 40) if a.quick else (400, 60)
        results = {}
        plan = [("D1", lambda: d1_d4(py, rs, n, length, 20261030, work / "d1")),
                ("D2", lambda: d2(py, rs, 20000 if a.quick else 200000, 7)),
                ("D3", lambda: d3(py, rs, 11, work / "d3")),
                ("D5", lambda: d5(rs_bin, work / "d5")),
                ("D6", lambda: d6(rs_bin, work / "d6", 20 if a.quick else 100))]
        for name, fn in plan:
            if only and name not in only:
                continue
            (work / name.lower()).mkdir(exist_ok=True)
            t0 = time.time()
            results[name] = fn()
            print(f"{name}: {json.dumps(results[name], ensure_ascii=False)[:900]} ({time.time() - t0:.0f}s)", flush=True)
        py.close()
        rs.close()
        total = sum(r["mismatches"] for r in results.values())
        print(f"python {sys.version.split()[0]} | rust bin {rs_bin}")
        if a.sabotage:
            print("SABOTAGE CAUGHT" if total else "SABOTAGE NOT CAUGHT: D1 cannot see last-bit float differences")
            sys.exit(0 if total else 1)
        print("VERDICT", "IDENTICAL" if total == 0 else f"{total} MISMATCH GROUP(S)")
        sys.exit(0 if total == 0 else 1)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
