# EXT-01: resource admission and lock-error handling (registration, nothing measured yet)

**Source:** an external reviewer on LinkedIn, 2026-10-30, sent two observations from **reading** the code with an AI coding agent. They did not run it. They are paraphrased here, not quoted, because the message was private. The reviewer is not named until they agree to be credited. Status of the observations: **CONTRIBUTOR REPORTED, not reproduced.**

1. `put()` builds the hash embedding (lower-casing, splitting and hashing every word) before it takes the lock and checks capacity. It then serializes the whole proposed snapshot before refusing an oversized write. So a large input costs CPU and memory even when it will be refused. The reviewer suggested an early input-size check that keeps the final check under the lock.
2. In `_lock()`, failing to open the lock file becomes `IntegrityError`, but an error from `fcntl.flock()` escapes as a raw `OSError`.

Claude (Anthropic, Opus 5.5) registered this at Chad Holland's direction, 2026-10-30. **Self-tested** from here on.

## Pre-mortem

How this could mislead:
- **Container numbers.** Peak memory and timing measured in Claude's container are not the phone's numbers.
- **Unknown proof of harm.** "It costs resources" is only a problem if the cost is large compared with the input. So the prediction is about the ratio.
- **A new lock-failure path.** A fix could reject writes the old code accepted. N5 checks for that.

## Predictions (on current `main` before any change, then after the fix)

| ID | Check | Before the fix (predicted) | After the fix (predicted) |
|---|---|---|---|
| N1 | A store with `max_bytes=4096`; refused `put()` of 1, 4 and 16 MB values made of 1-character words, each in a fresh subprocess. Measure peak RSS growth, CPU time, and whether the snapshot bytes are unchanged | All refused with `CapacityError`, snapshot unchanged. Peak RSS growth **at least 5×** the input size at 16 MB (one Python object per word) | Refused before any embedding work. Peak RSS growth **at most 3×** the input size, and CPU time **at least 10× lower** at 16 MB. Still `CapacityError`, snapshot unchanged |
| N2 | An **accepted** put of a 4 MB value made of 1-character words into a 16 MB store | Peak RSS growth at least 5× the input | Lower than before (the split no longer builds a word list). The embedding is bit-identical (N5) |
| N3 | `fcntl.flock(LOCK_EX)` made to raise `OSError` during `put()` | A raw `OSError` escapes; snapshot unchanged | `IntegrityError`; snapshot unchanged |
| N4 | `fcntl.flock(LOCK_UN)` made to raise **after** a successful commit | **Defect predicted:** `put()` raises, although the record was committed | `put()` returns the new ID. Closing the file releases the lock anyway |
| N5 | Equivalence: no behaviour changes except earlier refusals | — | The 69 tests and 12 mutants pass; Claude's A1–A15 are unchanged. The Python vs Rust differential stays IDENTICAL after porting the same change. 20,000 random texts give bit-identical embeddings with streaming and list-based splitting. Whenever the early check refuses, the final check would also have refused, shown on 2,000 random cases |
