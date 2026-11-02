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

## Amendment 1 (2026-11-02, before anything was built or run): the case set and tie-break fixed in advance

Suggested by Shivashish Jaishy (Founder and CEO, Shristyverse), in a public LinkedIn reply on 2026-11-02: fix the contradiction set and the tie-break rule before the first run, so that UNKNOWN and most-recent-first are scored on identical cases. This amendment does that. Nothing has been built or run.

- **One case file, generated and committed before either policy runs.** `cases.jsonl` holds, for each q in {0, 0.25, 0.5, 0.75, 1}, 200 keys (1,000 keys in total). Each key has exactly two current records with different values: one marked true, one marked false. Older timestamp = 1000 + key index; newer = older + 10, so timestamps never tie in P1. Which keys have the *newest* record wrong is decided by `random.Random(20261102)`: shuffle the 200 keys and take the first round(q · 200). The file's sha256 is recorded in the results before any policy output exists.
- **Both policies read the same file**, in the same order, through the real `MemoryStore` (`put` in file order).
- **Most-recent-first tie-break, fixed now:** the latest `timestamp` wins. If that ties, the latest `recorded_at`; if that also ties, the highest `id`. P1 has no ties. For P3, the stored `timestamp` is used as written, so a forged future timestamp wins by design.
- **Scoring per key:** `correct` (the answer equals the true value), `wrong` (an answer that is not the true value), or `abstain` (UNKNOWN). Both policies are scored on every key, and nothing is dropped.
- **P2's case set** is a separate block of 200 keys, also in `cases.jsonl`: the second value is written with `correct()` (supersedes). Every such key has the true value newest.
- **P3's case set** is another 200 keys. The false value is `put` with `timestamp` set 1,000,000 seconds ahead of the store clock. The clock is advanced so the record is current and visible.

Credit: Shivashish Jaishy suggested this procedure, and he agreed publicly to be credited by name. Crediting him implies no endorsement or validation of this work by him.
