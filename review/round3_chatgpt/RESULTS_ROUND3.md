# Round 3: ChatGPT's Rust parity review, reproduced and fixed (2026-10-30)

**Who:**
- ChatGPT (OpenAI) wrote 31 targeted sequences and reported 14 mismatches between the Python reference and the Rust port. Its branches are PRs #1 and #2, published by Claude from ChatGPT's git bundles with the commits unchanged.
- Claude (Anthropic, Opus 5.5) reproduced them on current `main`, which includes EXT-01: **14 of 14 REPRODUCED**. Claude then fixed 12 and declared the other 2 a limit.

Both are AI; this is not independent review. Container: Python 3.13.18, Rust 1.97.0.

## What could have gone wrong, first

- **Two mismatches remain, by decision rather than fix:** `unicode_cyrillic_tje` and `unicode_garay` (SML-R3-01). Rust's lower-casing follows a newer Unicode version than CPython 3.12/3.13. Characters assigned in recent Unicode releases (for example U+1C89, and the Garay script) lower-case in Rust but not in Python. That changes their embeddings and can change a recall answer.
  - Different Python versions disagree with each other the same way, so no single "right" answer exists for these characters.
  - The compatibility claim is narrowed in `rust/README.md` and `rust/RESULTS.md` to text without characters newer than the running Python's Unicode version.
- **Most findings were in the Rust test CLI, not the store.** R3-03 and R3-04 were adapter bugs: `sml-cli` silently replaced malformed options with defaults. They mattered because they made the differential test less able to see validation differences. The store library itself did not have them.
- **R3-02 changes Python behaviour:** integers above 2^53 that a float cannot hold exactly are now refused everywhere a number is checked, in both languages. No realistic clock value is affected.

## Findings

| ID (ChatGPT) | Severity (ChatGPT) | Reproduced on main | Fix | After |
|---|---|---|---|---|
| R3-01 Unicode-version case mapping | Medium | yes (2 cases) | **Declared limit**, documented; not fixable without pinning one Unicode version in both languages | still 2 mismatches |
| R3-02 integer timestamps beyond 2^53 cross the future-evidence boundary | Low reach, correctness | yes (2 cases) | `number()` in both stores refuses integers that do not convert to float exactly. Python's `number()` also turned a huge integer's `OverflowError` into `ValueError` (found while fixing) | identical |
| R3-03 malformed CLI options became defaults in Rust | Medium (CLI) | yes (8 cases) | `sml-cli` types every option exactly as the Python adapter does: wrong type is `ValueError`; a non-string `rkey` matches nothing; recall's `query or key` | identical |
| R3-04 duplicate fields / BOM in protocol lines | Low (CLI) | yes (2 cases) | both CLIs answer `BadOp` for bad JSON, duplicate fields or a BOM | identical |

ChatGPT's runner after the fixes: **29 identical, 2 mismatches** (the declared Unicode pair), down from 17 identical and 14 mismatches.

Also re-run:
- `verify_hardened.py`: 76 tests, 16 of 16 fix-removal mutants killed;
- `cargo test`: 5 unit and 8 integration tests;
- full differential: **IDENTICAL**;
- sabotage: **caught**.

ChatGPT's task 1 (PR #1) independently replayed its 14 round-2 scripts on `main`, and all 14 passed. That is ChatGPT confirming its own earlier findings are fixed.
