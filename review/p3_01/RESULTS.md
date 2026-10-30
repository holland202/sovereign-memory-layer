# P3-01: stores Python wrote that Rust could not open (2026-10-30)

**Who:**
- ChatGPT (OpenAI) found the candidate by reading the source, wrote the probe `test_large_counter_interop.py`, and wrote the report `CHATGPT_SML_RUST_REVIEW.md`. Both files are kept here unchanged:
  - report sha256 `c396b4c64dbdf5ae70b6dcba48703f2132e350fac5e4c8734e9cae2c90e0a71e`;
  - probe sha256 `b17ae480bec54745b61511b58dcb75bbecebae3fbadf62dd4979e4556737ec3e`.
- ChatGPT could not run Rust. It labelled the finding NOT RUN.
- Claude (Anthropic, Opus 5.5) ran the probe on `main` at `f86c8e6`. Claude also found a related case (the counter overflow below) and fixed both.

Both are AI, so this is not independent review. Environment: an x86_64 container, Python 3.13.18, rustc 1.97.0. **NOT VALIDATED on the S25.** Done at Chad Holland's direction, 2026-10-30.

## What could have gone wrong, first

- **A documented claim was false.** `rust/README.md` and `rust/RESULTS.md` said that integers outside ±2^63 never occur "in files either implementation writes". Python wrote them in two ways:
  - when asked for `max_records = 2^63`;
  - when one more write arrived after a counter (`next_id`, `generation`) reached 2^63−1.
  The claim was written without a test. It is corrected in both files, and the original wording is kept.
- **ChatGPT's probe now exits 1 after the fix.** It treats Python refusing to create the store as unexpected. The fix makes that refusal the intended behaviour. The probe is kept unchanged as received, so the exit code alone does not show the result. Read the output in `after.txt`.
- **A difference remains in the test command-line tools only.** For `max_records = 2^63` in a protocol line:
  - the Python CLI answers `ValueError`;
  - the Rust CLI answers `BadOp`, because its JSON reader does not accept integers that large.
  Both refuse, and neither creates a directory. Rust's library takes an `i64`, so the store API cannot receive the value at all. This is declared, not fixed.
- **Why Rust refused the overflow before the fix is probably known but not confirmed.** Before the fix, Rust refused the overflowing write with `ValueError` and left the file unchanged. Plain `+=` wraps in a release build, so the likely cause is that the wrapped negative counter failed the snapshot check before commit. This was not traced line by line. Rust was safe either way, but its error label differed from Python's.
- Reachability: only on purpose, or through a crafted file. Nobody makes 2^63 writes.

## Raw output

`before.txt`: ChatGPT's probe, before the fix:
```
CASE max_records = 9223372036854775807
PYTHON_RESULT: {"ok": true, "result": {"bytes": 195, "generation": 0, "incomplete_storage_detected": false, "max_bytes": 2000000, "max_records": 9223372036854775807, "records": 0}}
RUST_RESULT: {"ok": true, "result": {"bytes": 195, "generation": 0, "incomplete_storage_detected": false, "max_bytes": 2000000, "max_records": 9223372036854775807, "records": 0}}
MATCH
CASE max_records = 9223372036854775808
PYTHON_RESULT: {"ok": true, "result": {"bytes": 195, "generation": 0, "incomplete_storage_detected": false, "max_bytes": 2000000, "max_records": 9223372036854775808, "records": 0}}
RUST_RESULT: {"error": "IntegrityError", "ok": false}
MISMATCH: Python and Rust disagree on Python-created valid snapshot
VERDICT: FAIL
```
`counter_before.txt` (Claude's `counter_exhaustion.py`, before the fix): when Python wrote one more record after `next_id = 2^63-1`, it stored `next_id = 2^63`, and Rust then answered `IntegrityError`. When Python wrote one more record after `generation = 2^63-1`, it stored `generation = 2^63`, and Rust again answered `IntegrityError`. Rust refused both writes with `ValueError`. The script printed 4 cases, 4 FAIL, `VERDICT: FAIL`.

After the fix:
- `after.txt`: at 2^63−1 both programs match. At 2^63, Python now refuses the create with `ValueError` (`UNEXPECTED Python create result` in the probe's wording).
- `counter_after.txt`: 4 cases, 4 PASS. Both programs refuse with `CapacityError`, the file is unchanged, and both agree on status afterwards.

## Fix

- **Python** (`sml/memory.py`): `MAX_COUNTER = 2**63 - 1`.
  - `max_records` must be between 1 and `MAX_COUNTER`.
  - Stored `generation`, `next_id` and `max_records` above `MAX_COUNTER` make the file an `IntegrityError`.
  - Counters advance through `_bump`, which raises `CapacityError` at `MAX_COUNTER`, before anything is committed.
- **Rust** (`rust/src/store.rs`): `bump` uses `checked_add` and returns `CapacityError`. The reader already refused counters outside `i64`.

## Checks

- `verify_hardened.py`: **79 tests pass and 19 of 19 fix-removal mutants are killed.** Three new tests are in `tests/test_p3_01.py`. Three new mutants each remove one part of the fix: the create bound, the read bound and the bump guard.
- `cargo test`: 14 tests pass, including the new `counter_at_i64_max_refuses_write_unchanged`.
- `tools/differential.py --quick`: **IDENTICAL**. `--quick --sabotage`: **SABOTAGE CAUGHT**.

## Still open

- The full (non-quick) differential was not re-run for this change.
- Not run on the S25.
- The Rust CLI's `BadOp` for integers outside `i64` is declared, not removed.
