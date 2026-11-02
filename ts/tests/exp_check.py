#!/usr/bin/env python3
"""SML-TS-001 P5: the port's exp() vs Python's math.exp, bit for bit, on 1,000,000 seeded inputs.
Registered seed 20261102 (ts/PORT_PREREG.md). Usage: python3 ts/tests/exp_check.py [--n N] [--seed S]"""
import argparse, math, platform, random, struct, subprocess, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=1_000_000)
ap.add_argument("--seed", type=int, default=20261102)
a = ap.parse_args()
r = random.Random(a.seed)
hx = lambda x: struct.pack(">d", x).hex()
xs = []
while len(xs) < a.n:
    k = r.random()
    if k < 0.6:  # the store's decay argument: -ln2 * age / half_life
        x = -math.log(2) * r.uniform(0, 1e7) * 10 ** r.uniform(-9, 3) / r.choice([1e-9, 1.0, 3600.0, 2592000.0, 1e308])
    elif k < 0.9:
        x = r.uniform(-746.0, 0.0)
    else:
        x = struct.unpack(">d", struct.pack(">Q", r.getrandbits(64)))[0]
    if math.isfinite(x) and x <= 709.0:
        xs.append(x)
inp = "\n".join(hx(x) for x in xs) + "\n"
res = subprocess.run(["node", str(Path(__file__).with_name("exp_check.ts"))], input=inp, text=True,
                     capture_output=True, check=True).stdout.split()
bad = [(hx(x), hx(math.exp(x)), y) for x, y in zip(xs, res) if hx(math.exp(x)) != y]
print(f"platform {platform.machine()} {platform.libc_ver()} python {sys.version.split()[0]} seed {a.seed}")
print(f"exp inputs {len(xs)} | outputs {len(res)} | mismatches {len(bad)}")
for b in bad[:5]:
    print("  x", b[0], "python", b[1], "ts", b[2])
sys.exit(0 if not bad and len(res) == len(xs) else 1)
