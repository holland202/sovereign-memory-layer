# Round 2: fixes for ChatGPT's findings (2026-10-30)

**Self-tested.** ChatGPT (OpenAI) found these issues. Claude (Anthropic, Opus 5.5) reproduced them, fixed them and tested the fixes. Both are AI, so none of this is independent or human review. Everything ran in an x86_64 Linux container with Python 3.13.18: **NOT VALIDATED on the S25**.

## What could have gone wrong, first

- **The same AI fixed and judged.** ChatGPT's own scripts are the main outside check: all 14 now exit 0. ChatGPT has not re-run them on this version.
- **The re-entrancy guard is a design choice.** A nested call on the same store, from the same thread, is now refused with `ReentrancyError` rather than allowed. Callbacks therefore cannot read the store.
- **One guard has no test that can reach it.** The commit-side reader-limit check never fires, because validation already bounds `max_bytes` before it runs. It is kept as a second line of defence and has no mutant.
- **The schema-tag rule (M1) is my decision, made under Chad's delegation:** the tag must be exactly integer 1.
- **Not run:** Python 3.10 and 3.14, Termux/Android, symlink and permission edge cases, power loss.

## Findings and fixes

| ID | Finding (ChatGPT) | Reproduced on round 1 | Fix | ChatGPT script now | Mutant |
|---|---|---|---|---|---|
| R2-01 | `recall(None, query=…)` returned another key's KNOWN value | yes (exit 1) | `recall()` requires a non-empty string key | exit 0 | killed |
| R2-02 | `clock()`/`fault()` callbacks that call the store deadlocked | yes (both exit 1) | nested same-thread calls on the same directory raise `ReentrancyError` | both exit 0 | killed |
| R2-03 | `revoke()` accepted control and bidi characters in provenance labels | yes (exit 1) | `revoke()` uses the same new-provenance check as `put()` | exit 0 | killed |
| R2-04 | a legacy NFD key could not be corrected | yes (exit 1) | correction-link validation compares keys by NFC | exit 0 | killed |
| R2-05 | a stored `max_bytes` over 16,000,000 let a store write a file it could not reopen | yes (exit 1) | load refuses `max_bytes` outside 1,024..16,000,000; commit also refuses a file over the reader limit | exit 0 | killed |
| M1 | schema tag `true` or `1.0` accepted | yes (exit 1) | the tag must be exactly integer 1 | exit 0 | killed |

## Checks after the fixes

- `python3 verify_hardened.py`: **69 tests pass, 12 of 12 fix-removal mutants killed, exit 0.** The test count is 42 original, 9 identifier, 9 round-1 and 9 round-2.
- ChatGPT's 14 scripts: 14 of 14 exit 0 (`claude_run_on_round2_fix/`).
- Claude's A1–A15 and E1–E5 (`attack/results/run3_round2fix.txt`, `explore3_round2fix.txt`) give the same outcomes as after round 1, with no regressions. The labels A3 and A11 still read "defect", and A14 is still the known rollback limit, for the reasons given in `attack/RESULTS.md`.

Credit: ChatGPT (OpenAI) found R2-01..R2-05 and M1 in its AI-assisted test review, at Chad Holland's direction.
