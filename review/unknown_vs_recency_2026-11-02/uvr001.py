#!/usr/bin/env python3
"""UVR-001 harness: UNKNOWN-on-contradiction (SML recall) vs most-recent-first (MRF), scored on the
committed cases.jsonl. Usage: python3 uvr001.py [--sabotage]
--sabotage loads a copy of sml/memory.py whose contradiction check is disabled; P1 must then fail."""
import hashlib, importlib.util, json, sys, tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CASES = HERE / "cases.jsonl"
EXPECTED_SHA = (HERE / "cases.sha256").read_text().split()[0]
PROV = {"source": "uvr001-synthetic", "locator": "case", "sha256": "a" * 64}
sabotage = "--sabotage" in sys.argv

src = (ROOT / "sml/memory.py").read_text()
if sabotage:
    old = 'if len({r["value"] for r in current}) > 1:  # MUTATION: contradiction'
    assert src.count(old) == 1
    src = src.replace(old, "if False:  # SABOTAGE")
spec = importlib.util.spec_from_loader("sml_memory_uvr", loader=None)
M = importlib.util.module_from_spec(spec)
exec(compile(src, "memory.py", "exec"), M.__dict__)

data = CASES.read_bytes()
assert hashlib.sha256(data).hexdigest() == EXPECTED_SHA, "cases.jsonl changed since it was committed"
cases = [json.loads(l) for l in data.decode().splitlines()]


def mrf(snapshot, key):
    """Most-recent-first, tie-break fixed by Amendment 1: timestamp, then recorded_at, then id."""
    cur = [r for r in snapshot["records"] if M.same_key(r["key"], key) and r["status"] == "current"]
    if not cur:
        return None
    return max(cur, key=lambda r: (r["timestamp"], r["recorded_at"], r["id"]))["value"]


def score(answer, case):
    if answer is None:
        return "abstain"
    return "correct" if answer == case["true"] else "wrong"


tally = Counter()
with tempfile.TemporaryDirectory() as td:
    for n, c in enumerate(cases):
        t = [0.0]
        m = M.MemoryStore(Path(td) / f"s{n}", create=True, max_records=8, clock=lambda: t[0])
        first = None
        for w in c["writes"]:
            t[0] = w["timestamp"]
            value = c[w["value"]]
            if w["how"] == "put":
                i = m.put(c["key"], value, provenance=PROV, timestamp=w["timestamp"])
                first = first or i
            else:
                m.correct(first, value, provenance=PROV, timestamp=w["timestamp"])
        r = m.recall(c["key"])
        sml_answer = r["value"] if r["status"] == "KNOWN" else None
        group = c["block"] if c["block"] != "P1" else f"P1 q={c['q']}"
        tally[(group, "SML", score(sml_answer, c))] += 1
        tally[(group, "MRF", score(mrf(m.snapshot(), c["key"]), c))] += 1

groups = ["P1 q=0.0", "P1 q=0.25", "P1 q=0.5", "P1 q=0.75", "P1 q=1.0", "P2", "P3"]
print(f"cases {len(cases)} sha256 {EXPECTED_SHA[:16]}{' SABOTAGE RUN' if sabotage else ''}")
print(f"{'group':<11} {'policy':<5} {'correct':>7} {'wrong':>5} {'abstain':>7}")
for g in groups:
    for p in ("SML", "MRF"):
        print(f"{g:<11} {p:<5} {tally[(g, p, 'correct')]:>7} {tally[(g, p, 'wrong')]:>5} {tally[(g, p, 'abstain')]:>7}")

q_wrong = {0.0: 0, 0.25: 50, 0.5: 100, 0.75: 150, 1.0: 200}
p1 = all(tally[(f"P1 q={q}", "SML", "wrong")] == 0 and tally[(f"P1 q={q}", "MRF", "wrong")] == w for q, w in q_wrong.items())
p2 = tally[("P2", "SML", "correct")] == 200 and tally[("P2", "MRF", "correct")] == 200
p3 = tally[("P3", "MRF", "wrong")] == 200 and tally[("P3", "SML", "abstain")] == 200
for name, ok, what in [("P1", p1, "SML wrong = 0 on contradictions; MRF wrong = round(q*200) exactly"),
                       ("P2", p2, "legitimate corrections: SML KNOWN with the new value on 200/200, same as MRF"),
                       ("P3", p3, "forged future timestamp: MRF fooled 200/200, SML UNKNOWN 200/200")]:
    print(f"{name}: {'HELD' if ok else 'REFUTED'}  ({what})")
print("P4: OPEN (real-world q not measured; a door, not a claim)")
n = sum([p1, p2, p3])
print(f"VERDICT {n} of 3 testable predictions as registered")
sys.exit(0 if n == 3 else 1)
