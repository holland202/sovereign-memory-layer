#!/usr/bin/env python3
"""PDX-001: does retrieval decay bury protected records, and what does recall report? (see PREREG.md)

Runs against the SML in this repository (Python reference). Standard library only.
  python3 review/pdx001_2026-11-13/pdx001.py
Prints, for 20 seeded cases:
  - how often an old protected record is found by retrieve() and recall() under each method
  - recall()'s reason when a key has current evidence that is not retrieved, and when it has none
  - a digest of every score given to UNPROTECTED records (must not change with the fix)
Exit 0 always after printing (the verdicts are judged against PREREG.md in RESULTS.md); 2 if SML cannot load.
Written by Claude (Anthropic, Opus 5.5), 2026-11-13. SELF-TESTED.
"""
import hashlib
import json
import math
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
try:
    from sml.memory import DIM, MemoryStore
except Exception as exc:  # noqa: BLE001
    print(f"COULD NOT RUN: {exc}")
    sys.exit(2)

CASES, SEED, DAY, NOW = 20, 20261113, 86400.0, 2_000_000_000.0
METHODS = ("similarity", "recency", "importance", "protected")
P = {"source": "pdx001", "locator": "synthetic", "sha256": hashlib.sha256(b"pdx001").hexdigest()}


def unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def near(rng, base, s):
    return unit([b + s * rng.gauss(0, 1) / math.sqrt(DIM) for b in base])


def store(tmp, name):
    return MemoryStore(Path(tmp) / name, create=True, max_records=64, max_bytes=4_000_000, clock=lambda: NOW)


def main():
    rng = random.Random(SEED)
    found = {f"{call}/{m}": 0 for call in ("retrieve", "recall_known") for m in METHODS}
    reasons = {}
    unprotected_scores = []
    with tempfile.TemporaryDirectory() as tmp:
        for c in range(CASES):
            kv = unit([rng.gauss(0, 1) for _ in range(DIM)])
            q = near(rng, kv, 0.6)
            m = store(tmp, f"case{c}")
            crit = m.put("critical", "constraint", provenance=P, protected=True, weight=1.0,
                         timestamp=NOW - rng.uniform(220, 365) * DAY, embedding=near(rng, q, 0.25))
            for j in range(6):
                m.put(f"competitor{j}", f"v{j}", provenance=P, weight=1.0,
                      timestamp=NOW - rng.uniform(0, 30) * DAY, embedding=near(rng, q, 0.45))
            for j in range(10):
                m.put(f"filler{j}", f"f{j}", provenance=P, timestamp=NOW - rng.uniform(0, 365) * DAY,
                      embedding=unit([rng.gauss(0, 1) for _ in range(DIM)]))
            for meth in METHODS:
                top = m.retrieve("critical", method=meth, top_k=5, embedding=q)
                found[f"retrieve/{meth}"] += crit in [h["record"]["id"] for h in top]
                found[f"recall_known/{meth}"] += m.recall("critical", method=meth, top_k=5, embedding=q)["status"] == "KNOWN"
                unprotected_scores += [(c, meth, h["record"]["id"], repr(h["score"]))
                                       for h in m.retrieve("x", method=meth, top_k=100, threshold=0, embedding=q)
                                       if not h["record"]["protected"]]
        # Reason cases: (a) a current, old, UNPROTECTED record decayed below threshold; (b) only a revoked record.
        a = store(tmp, "reason_a")
        rid = a.put("stale", "old", provenance=P, timestamp=NOW - 300 * DAY, embedding=unit([1.0] + [0.0] * (DIM - 1)))
        reasons["current record decayed below threshold"] = {
            k: v for k, v in a.recall("stale", method="recency", embedding=unit([1.0] + [0.0] * (DIM - 1))).items()
            if k in ("status", "reason", "evidence_ids")}
        reasons["  (its id)"] = rid
        b = store(tmp, "reason_b")
        bid = b.put("gone", "x", provenance=P, timestamp=NOW - DAY, embedding=unit([1.0] + [0.0] * (DIM - 1)))
        b.revoke(bid, reason="withdrawn", provenance=P)
        reasons["only a revoked record"] = {
            k: v for k, v in b.recall("gone", embedding=unit([1.0] + [0.0] * (DIM - 1))).items()
            if k in ("status", "reason", "evidence_ids")}
    print(f"PDX-001 | {CASES} cases | python {sys.version.split()[0]}")
    print("old protected record (220-365 d) among 6 newer competitors; defaults half_life 30 d, threshold 0.15, top_k 5")
    for k, v in found.items():
        print(f"  {k:24} {v:>2}/{CASES}")
    for k, v in reasons.items():
        print(f"  {k}: {v}")
    dg = hashlib.sha256(json.dumps(unprotected_scores).encode()).hexdigest()
    print(f"UNPROTECTED_SCORES {len(unprotected_scores)} digest {dg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
