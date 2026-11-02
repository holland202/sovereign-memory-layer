# SKR-001: same-key writers racing, one killed between write and rename — registration (2026-11-02)

Written before anything below was built or run. Nothing has been built or run yet.

**Origin.** The test idea came from a LinkedIn comment on the SML outside-testing post (2026-11-01): two writers racing on the same key, with a `kill -9` timed between write and rename. The commenter is not named here until they consent to credit. Existing tests cover kills at the four commit points with **one** writer (`tests/test_crash.py`), and concurrent writers on **different** keys with no kill. This combination is untested.

## Question

When several processes write the same key at once and one is SIGKILLed at a commit boundary, does the store lose an acknowledged write, show a write that was never acknowledged, break its id sequence, or become unusable?

## Design (W3)

- Real code: `sml.memory.MemoryStore`, imported, not copied. The kill uses the store's own `fault` hook. The victim sends SIGKILL to itself inside the hook, so the kill lands exactly at the named stage.
- **Writers:** K = 4 processes. Each makes M = 25 `put` calls on the **same key** `race.k`, with distinct values `w<i>.<n>`. A writer prints an ACK line (`id`, `value`) and flushes it only after `put` returns.
- **Victim:** one writer per trial is chosen by a seeded RNG. It kills itself at its c-th commit, c drawn uniformly from 1..M, at one stage.
- **Stages:** `partial_write`, `after_file_fsync` (between write and rename: the commenter's case) and `after_replace` (rename done, directory not yet fsynced).
- **Trials:** 8 per stage, 24 in total, seeds 0..23. Store limits: `max_records = 200`, default `max_bytes`.
- **Stand-ins:** synthetic keys and values, a fixed embedding, a local ext4/overlay filesystem, and a self-sent SIGKILL rather than an external timer.

## Predictions (checked per trial; all 24 trials must hold)

- **P1 (opens):** after all writers end, `MemoryStore(path)` opens and `snapshot()` succeeds. No `IntegrityError`.
- **P2 (no acknowledged write lost):** every ACKed `(id, value)` from every writer, the victim's earlier ACKs included, is in the snapshot with that id and value.
- **P3 (nothing unacknowledged appears):** at stages `partial_write` and `after_file_fsync`, the snapshot holds no record that was not ACKed. At stage `after_replace`, at most one record was never ACKed: the victim's in-flight write, committed by the rename before the kill.
- **P4 (ids intact):** record ids are exactly 1..N with no gaps or duplicates, where N is the record count.
- **P5 (store still usable):** a fresh process can `put` one more record afterwards, and it gets id N + 1.
- **P6 (contradiction answered honestly):** `recall("race.k")` returns `UNKNOWN`, reason `contradictory_current_evidence`, and its `evidence_ids` equal the set of current record ids for the key.

## Anti-vacuity control (M3)

`--sabotage` runs the same trials with the store's file lock replaced by a no-op, in the writers only. Without the lock, concurrent read-modify-write must lose updates or corrupt the file. **Pass criterion for the instrument:** under sabotage, at least one of P1, P2 or P4 fails in at least one trial, and the harness exits 1. If sabotage passes everything, the harness cannot see the failure it claims to rule out, and the main result counts for nothing.

## Simplest rival (M14)

The store may hold up only because the writers rarely overlap. The harness records, per trial, how many writer commits overlapped in time (one writer's lock wait started while another held the lock), using wall-clock stamps. Interpretation: if overlap is 0 in most trials, the result shows only "kills are safe", not "races are safe".

## Verdict code (C-BUILD)

One HELD or REFUTED line per prediction, then `VERDICT n of 6 as registered`. Interleavings are not deterministic, so no digest of ids is pinned. Only the six verdicts are compared across runs.

## Limits

- One machine, one filesystem, x86_64 container. NOT VALIDATED on the S25.
- Real power loss, and filesystems that lie about fsync (the commenter's second idea), are out of scope.
- Self-tested: Claude (Anthropic, Opus 5.5) designed this and will run it. This is not independent review.

## Unrun next step

Run on the S25 (Android flock and fsync), and with K = 8 writers.

Provenance: Claude (Anthropic, Opus 5.5), at Chad Holland's direction (2026-11-02, direction only) → human validation: not performed → human responsibility: Chad Holland.
