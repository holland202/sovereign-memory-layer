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

- The full (non-quick) differential was not re-run for this change. *(Update: run in a second session, below; IDENTICAL.)*
- Not run on the S25.
- The Rust CLI's `BadOp` for integers outside `i64` is declared, not removed.
- **No recovery path for old stores.** A store the pre-fix Python already wrote with a counter above 2^63−1 cannot be opened by either program now. Details below.

## Second session: rerun and one new gap (2026-10-30)

**Who:** Claude (Anthropic, Opus 5.5), in a separate session from the fix. It is the same model that wrote the fix, so this is **SELF-TESTED**, not independent review. Done at Chad Holland's direction. Environment: x86_64 container, Python 3.13.18, rustc 1.97.0. **NOT VALIDATED on the S25.**

**Predictions written before running:**
1. At `f86c8e6`, the control matches and the `2^63` case mismatches. The probe exits 1.
2. At `4b4bda1`, Python refuses the create and the probe still exits 1, as described above.

Both held.

What was run, with the raw output in `rerun_2026-10-30/`:
- **ChatGPT's probe**, checked to be the same file (same sha256 `b17ae480…ec3e`), on fresh release builds of both commits.
  - `probe_before_f86c8e6.txt`: MISMATCH at `2^63`. Python answers `ok`, Rust answers `IntegrityError`.
  - `probe_after_4b4bda1.txt`: MATCH at `2^63−1`. At `2^63`, Python refuses with `ValueError`.
- **Cross-check of ChatGPT's own numbers.** The store the pre-fix Python writes has sha256 `7afb95cc…3eea`. That is byte-for-byte the hash ChatGPT reported from its older archive.
- **Suites at `4b4bda1`.** `verify_hardened.py` reports 79 tests and 19 of 19 mutants killed. `cargo test` passes 14 tests. Both match the numbers above.
- **Full differential**, `tools/differential.py` without `--quick`, in `differential_full_4b4bda1.txt`. **VERDICT IDENTICAL**:
  - D1: 400 sequences, 24,400 ops, 0 mismatches.
  - D2: 200,000 values, 0 mismatches.
  - D3: 3,402 cases, 0 mismatches.
  - D5: 240 of 240 records.
  - D6: 100 trials, 0 unacked extras.
  - D4 has no line of its own. It runs inside D1's loop.

**New gap: old stores** (`legacy_store_4b4bda1.txt`). This is the migration question ChatGPT raised. The fix does not answer it, and no document mentioned it.
- The test created a `max_records = 2^63` store with the pre-fix Python, then opened it with the fixed code.
- Python and Rust now **both** answer `IntegrityError`, so the two programs agree.
- The file is unchanged (same sha256 before and after). Nothing is lost, and the store fails closed.
- But the store's owner cannot open it with either program. No tool or instruction exists to recover it.
- Reachability is the same as the original finding: only someone who asked for `2^63`, or who made 2^63 writes, can have such a file.

**Owner decision, not made here:**
- (a) keep it fail-closed and document it; or
- (b) add a one-off migration tool that lowers an out-of-range counter to 2^63−1 and re-signs the file.

Option (b) changes stored data, so it needs its own tests and review.


## Full differential (appended 2026-10-30, after `4b4bda1`)

`python3 tools/differential.py` at `4b4bda1` gave **VERDICT IDENTICAL**:
- D1: 400 sequences, 24,400 operations;
- D2: 200,000 floats;
- D3: 3,402 corrupt files;
- D5: mixed writers;
- D6: 100 kills, 2,307 acknowledged writes, none lost.

All have 0 mismatches. The output is in `differential_full.txt`. This closes the first "Still open" item above. The S25 run and the declared CLI difference are still open.

*Note, appended 2026-10-30:* the section above is a third run. It was made without knowing about the second session's run (`9474d2d`), and its numbers agree with that run. When it says "Still open", it missed the old-store gap the second session found.

## Decision on the old-store gap (2026-10-30)

**(a) Fail closed and document it.** No migration tool will be added.
- Only a store created with `max_records ≥ 2^63`, or one that took 2^63 writes, is affected. Only code from before `4b4bda1` could write one, and the repository went public on 2026-10-30. No tester has reported such a file.
- A migration tool would rewrite stored data. That is a larger risk than a store which fails closed and loses nothing.
- If anyone does report such a file, the recovery is to rewrite `max_records` (or the counter) to 2^63−1 and re-sign the file. That would be done as its own change, with tests.

Made by Claude (Anthropic, Opus 5.5) under the repo-work calls Chad Holland delegated on 2026-10-30. Chad can reverse it.
