# UVR-001: is answering UNKNOWN on contradiction worth it, compared with "most recent first"? — registration (2026-11-02)

Written before anything was built or run. **Nothing has been built or run.** This is a registration only; it is not frozen for execution until Chad Holland reviews it.

**Origin.** A LinkedIn commenter on the SML outside-testing post (2026-11-01) asked for "a small benchmark against 'most recent first' on contradictory facts". The commenter is not named until they consent. The README already lists this as open: "Not shown to retrieve better than 'most recent first'".

## First, what a synthetic benchmark cannot decide

On a key holding contradictory current values, call the two policies SML and MRF:
- **SML** answers `UNKNOWN`.
- **MRF** answers the value with the latest timestamp.

Let q be the fraction of such contradictions in which the newest value is wrong. Then, on those queries:
- MRF is wrong at rate q and right at rate 1 − q.
- SML is never wrong and never right; it abstains.

On keys with no contradiction, the two are identical. So **on any benchmark whose contradictions we write ourselves, the result is fixed by the q we chose.** A synthetic benchmark that reports "SML wins" or "MRF wins" would be vacuous: the designer set the answer.

The policy question therefore reduces to a cost inequality:

> UNKNOWN is worth it on a workload exactly when q · cost(wrong answer) > (1 − q) · cost(abstaining).

This is arithmetic, not a finding. The experiment below tests only what can actually fail.

## What can fail (predictions)

- **P1 (implementation matches the derivation):** on a generated workload with known q in {0, 0.25, 0.5, 0.75, 1}, SML's wrong-answer count on contradictory keys is exactly 0. MRF's is exactly round(q · n). Both must match to the record.
- **P2 (legitimate updates are not penalised):** when a newer value is written with `correct()` (supersedes) rather than a second `put`, SML answers KNOWN with the new value. Its answers then equal MRF's on every such key. If this fails, SML abstains on ordinary updates, which would be a real cost.
- **P3 (the adversarial case):** a record put with a future timestamp, the ATK A8 shape. MRF returns the attacker's value on 100% of such keys. SML returns `UNKNOWN` on 100%. This is where q is set by an adversary, not by chance.
- **P4 (the real-world q is not measured):** no data set available to this project gives q for real agent memory. The FEB-30 artefacts were unverified as of 2026-10-31. P4 is registered as a door, not a claim.

## Anti-vacuity control

`--sabotage` makes SML's contradiction check always false, so SML falls back to retrieval. P1 must then fail for q > 0: SML gives a nonzero wrong count.

## Design notes for the build (not yet built)

- Real `MemoryStore` and `recall`. MRF is about 10 lines over `snapshot()`: the newest `timestamp` among current records for the key.
- n = 200 contradictory keys per q, seeded. One correct value and one wrong value per key. The order of the true value is set by q.
- No retrieval ranking or embeddings are evaluated.

## Limits

This cannot say whether UNKNOWN is worth it for anyone's actual agent. Only P4, a measured q from real use, could say that. The strongest claim UVR-001 can support: SML never answers wrong on contradictions and is not fooled by forged future timestamps, at a coverage cost equal to the share of contradictions where the newest value is right.

Provenance: Claude (Anthropic, Opus 5.5), at Chad Holland's direction (2026-11-02, direction only) → human validation: not performed → human responsibility: Chad Holland. Self-designed.
