# SML-RS-001: results (Rust port vs Python reference, 2026-10-30)

**Self-tested.** Claude (Anthropic, Opus 5.5) wrote the port, the harness and the checks, and judged them, at Chad Holland's direction. Registration: [PORT_PREREG.md](PORT_PREREG.md), committed before the harness existed. Everything ran in an x86_64 Linux container with Python 3.13.18 and Rust 1.97.0: **NOT VALIDATED on the S25 or Termux.**

## What could have gone wrong, first

- **The quick run found a real mismatch before the registered full run.** The run came after registration, but it was not the registered run. 1 of 20,000 floats was formatted differently: `1059438285926254.25` lies exactly halfway between two 17-digit strings. Python rounds half to even and printed `…254.2`; Rust's shortest formatter rounds half up and printed `…254.3`. Because the checksum covers these exact bytes, Python would have refused a Rust-written file containing such a number, and the reverse. The fix: Rust now supplies only the digit count, and the exact decimal expansion is rounded half to even. A unit test pins this value. The full registered run then found 0 mismatches.
- **CI found a platform difference in the Python verifier, not in SML.** On Python 3.14, `json` no longer raises `RecursionError` on 100,000-deep nesting, so the A1 fix-removal mutant cannot fail there. `verify_hardened.py` now marks that mutant "n/a" only when the running Python cannot raise the error. On 3.13 and earlier it is still required to be killed.
- **Same model throughout.** The port and the tests share an author, so a misunderstanding of the Python code could be repeated on both sides. The differential test compares behaviour against the real Python code, not against a description of it, which limits this risk.
- **Not covered:** callbacks in the CLI (the Rust integration tests cover them instead), `OrthoProjection`, Termux/Android, Python 3.10/3.11 bit-parity (by design, see README).

## Registered checks (full run: `results/differential_full.txt`)

| ID | Check | Result |
|---|---|---|
| D1 | 400 seeded sequences, 24,400 operations: outputs and file SHA-256 after every op | **HELD**: 0 mismatches. Every output line identical; every store file byte-identical |
| D2 | 200,000 random f64 values plus edge values, formatted like Python `repr()` | **HELD** after the fix above: 0 mismatches. The quick pre-run found 1 of 20,000 before the fix |
| D3 | 3,402 corrupted or truncated files opened by both | **HELD**: 0 mismatches (3,392 `IntegrityError`, 10 accepted with identical status, e.g. trailing-newline cut or UTF-8 BOM) |
| D4 | each side recalls from the other's store after every sequence | **HELD** (part of D1): 0 mismatches |
| D5 | 4 Python and 4 Rust processes writing 30 records each to one store at once | **HELD**: 240/240 unique records; both reopen it |
| D6 | 100 SIGKILLs of a Rust writer mid-stream | **HELD**: 3,498 acknowledged writes, 0 lost, 0 unacknowledged extras; Python and Rust both reopen every store |

**Anti-vacuity** (`results/differential_sabotage.txt`): a copy of the port using naive summation in place of CPython's compensated `sum()` was caught. 50 of 400 D1 sequences diverged in store bytes. D1 can therefore see last-bit float differences.

**Rust-only tests** (`cargo test`): 5 unit and 7 integration tests, all passing. They cover:
- deep nesting and a lock path that is a directory both give `IntegrityError`;
- a re-entrant clock call is refused rather than deadlocking;
- injected faults at all four commit stages (state unchanged before replace; `CommitUncertain` and a poisoned instance after);
- clamped revocation under a behind clock;
- NFC/NFD contradiction and control-character refusal;
- capacity refusals that leave the bytes unchanged.

`cargo clippy` reports 6 style suggestions and no correctness warnings.

## Declared divergences (by design, not failures)

- Integers outside ±2^63 in a store file, and UTF-16/32 encoded store files: refused by Rust, accepted by Python. Neither occurs in files either implementation writes.
- Unicode tables come from crates, and may differ from Python's `unicodedata` version on characters assigned in the newest Unicode releases.
