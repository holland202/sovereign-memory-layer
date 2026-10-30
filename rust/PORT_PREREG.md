# SML-RS-001: Rust port, differential test registration

**Written before the differential harness exists or has run.** Only one 10-operation smoke test has run. It produced identical outputs and a byte-identical store file, and it is disclosed here because it ran before this registration. Claude (Anthropic, Opus 5.5), at Chad Holland's direction, 2026-10-30. **Self-tested.**

## Question

Does the Rust port behave exactly like the Python reference on the same inputs: the same results, the same error classes, and byte-identical store files?

## Design

The Python reference (`sml/memory.py`) and the port (`rust/`) each get a line-protocol CLI: `tools/py_cli.py` and `rust/src/bin/sml-cli.rs`. A seeded driver, `tools/differential.py`, sends the same operation stream to both and compares every output line and the SHA-256 of `memory.json` after every operation. The Python side runs on Python 3.13 (Neumaier `sum()`).

## Predictions

| ID | Check | Prediction |
|---|---|---|
| D1 | 400 seeded sequences of 60 random operations: put, correct, revoke, compact, recall, retrieve, status and cleanup, with valid and invalid arguments, odd Unicode, clock jumps, small caps and supplied embeddings | every output line identical and every file byte-identical |
| D2 | 200,000 random f64 bit patterns plus edge values, formatted by both | identical to Python `repr()` |
| D3 | 3,000 byte flips and 400 truncations of valid files, opened by both | identical outcome class, and identical `status` when opened |
| D4 | cross-open: each side opens and recalls from the other's store after every D1 sequence | identical |
| D5 | 4 Python and 4 Rust processes writing 30 records each to one store at the same time | 240 unique records, valid when opened by both |
| D6 | 100 SIGKILLs of a Rust writer mid-stream; Python then Rust reopen | always valid; every acknowledged write present; at most 1 unacknowledged extra |

## Anti-vacuity

`--sabotage` builds a copy of the port with naive summation in place of CPython's compensated `sum()`. The D1 differential must report at least one mismatch against it. If it does not, D1 cannot see last-bit float differences, and that is recorded.

## Known, declared divergences (not counted as failures if hit)

- Integers outside ±2^63 in a store file: Python accepts, Rust refuses (`IntegrityError`).
- UTF-16/32 encoded store files: Python auto-detects them, Rust refuses.
- `OrthoProjection` and `policies.admit` are not ported.
- Unicode version: NFC and categories come from the `unicode-normalization` and `unicode-general-category` crates, which may differ from Python's `unicodedata` version on newly assigned characters.
