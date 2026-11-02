# SML-TS-002: valid snapshots that no implementation writes — registration (2026-11-02)

Written before the new test was built or run. Nothing below has been run.

## Why

ChatGPT (OpenAI) reviewed SML-TS-001 independently on 2026-11-02. It reported 8 compatibility findings across 34 cases, including incorrect compaction and refused corrections and revocations on *valid* snapshots. Chad Holland relayed the summary. The evidence bundle has not reached Claude yet, so those findings are **CONTRIBUTOR REPORTED**: not reproduced, and their exact cases unseen.

The gap they point at is real in the design of SML-TS-001's tests. D1 to D6 only use files that an implementation wrote, and every implementation writes floats (`1000.0`). A valid file can hold integers where floats are usual: `timestamp`, `recorded_at`, `weight`, the revocation `at`, embedding entries. It can also hold keys that are not NFC, and other key orders and whitespace. Python accepts all of these, since `number()` takes `int` and `float`. Claude's port casts several of these fields straight to a JavaScript number, which is wrong for an integer.

## Design: D7, valid hand-shaped snapshots

1. **Generate.** Python builds a random store through the real API, using puts, corrections and revocations. It then rewrites the payload into a *valid* variant:
   - integral floats become ints, field by field at random: `timestamp`, `recorded_at`, `weight`, revocation `at` and embedding entries;
   - a random key becomes its NFD form;
   - the JSON is written with shuffled key order and extra whitespace;
   - `sha256` is recomputed with Python's own `canonical`.

   **Python must open the result.** A variant Python refuses is discarded and counted, never used.
2. **Act.** Python and the port each get an identical copy, then the same 12 operations: `status`; `recall` and `retrieve` with all four methods; `compact` to several targets; `correct`; `revoke`; `put`. The answer and the file hash are compared after every operation.
3. **Ports.** `--port ts`, and the same D7 against the Rust port (`--port rust`), which was never tested this way either.

## Predictions

- **P1 (before any fix):** D7 finds **at least one** Python vs TypeScript mismatch. This prediction rests on ChatGPT's report and on reading the port: `compact` compares weights with `>`, and `revoke` takes `max` of a raw timestamp. Both are wrong for an integer.
- **P2 (after fixes):** on the **registered seed 20261102**, used once, D7 with 300 snapshots finds **0** Python vs TypeScript mismatches. Debugging uses `--dev-seed` only.
- **P3:** D1 to D6 for TypeScript remain IDENTICAL after the fixes, on their registered seeds.
- **P4 (Rust, no prediction of the direction):** D7 against Rust, 300 snapshots, registered seed. Recorded as found. If it mismatches, that is a Rust finding, reported and fixed in its own round.
- **P5 (anti-vacuity):** D7 must report mismatches against the **pre-fix** port, which is P1 itself, so the instrument can see this class of bug.

## Limits

- Self-designed and self-run. ChatGPT's 34 cases have not been seen; matching them is a separate step once its bundle arrives.
- "Valid" means "Python accepts it". Python's acceptance is the specification here.

Provenance: Claude (Anthropic, Opus 5.5), at Chad Holland's direction (2026-11-02, direction only) → human validation: not performed → human responsibility: Chad Holland.
