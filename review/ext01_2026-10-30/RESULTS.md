# EXT-01: results (2026-10-30)

**Source:** two code-reading observations from an external reviewer, who is not yet named because their consent to credit is pending. **The reviewer's two observations are reproduced** by Claude (Anthropic, Opus 5.5) and fixed. Self-tested, in an x86_64 container with Python 3.13.18. **NOT VALIDATED on the S25.**

## What could have gone wrong, first

- **N2 was REFUTED as registered.** An accepted 4 MB write of one-character words used 26.9 MB of peak memory after the fix, against 23.0 MB before, not less. One-character strings are cached by CPython, so that input never built a costly word list. An exploratory check afterwards, on 4.5 MB of *distinct* words, showed what streaming saves: 5.7 MB of peak memory with the old `split()` against 0.0 MB with streaming. Streaming is kept: it is bit-identical (N5a) and helps real text, but N2 stays REFUTED.
- **The first equivalence run found a behaviour change, and it was fixed before results.** The early check initially ran before the correction-target and supplied-embedding checks, so 282 doubly-invalid writes changed their refusal from `ValueError` to `CapacityError`. The early check now repeats those cheap checks in the original order, and the rerun shows 0 changes.
- **A new error type.** Lock failures now raise `LockError`. It is a subclass of `IntegrityError`, so existing handlers still catch it. Whether lock failure belongs under integrity at all is a fair design question; ChatGPT raised it. A subclass keeps both readings possible.
- **Not run:** the phone, memory pressure alongside local inference, and Rust lock-failure injection (Rust has no seam for injecting it).

## Measurements (`before.txt` vs `after.txt`, same script)

| Check | Before | After |
|---|---|---|
| N1 refused 1 MB write into a 4 KB store | 0.868 s CPU, 5.8 MB peak growth | 0.001 s, 2.0 MB |
| N1 refused 4 MB | 3.432 s, 23.0 MB | 0.005 s, 7.6 MB |
| N1 refused 16 MB | **14.037 s, 151.5 MB** | **0.025 s, 30.5 MB** |
| N2 accepted 4 MB (1-char words) | 3.574 s, 23.0 MB | 4.333 s, 26.9 MB (**REFUTED**, see above) |
| N3 `flock(LOCK_EX)` fails | raw `OSError`, file unchanged | `LockError`, file unchanged |
| N4 `flock(LOCK_UN)` fails after commit | **`put()` raised, though the record was saved** | returns the ID; record saved |

Predictions:
- **N1 HELD:** before, at least 5× input (151.5 MB for 16 MB); after, at most 3× (30.5 MB = 1.9×) and at least 10× lower CPU (≈560×).
- **N3 HELD.**
- **N4 HELD.** This is a real defect: a caller would have retried a write that had already succeeded.

## N5 equivalence (`equivalence.py`, old tree vs new)

- (a) 0 of 20,000 random texts give a different embedding.
- (b) 16,800 operations, including near-limit writes: 0 differences in output or file bytes, and 0 changes in refusal reason.

Also:
- `verify_hardened.py`: 73 tests pass, and 15 of 15 fix-removal mutants are killed (three new ones for N1, N3 and N4).
- Claude's A1–A15 attacks: unchanged.
- The Rust port got the same early check and lock-error mapping, plus streaming words. Full differential (400 sequences, 200k floats, 3,402 corrupt files, mixed writers, 100 kills): **IDENTICAL**. The Rust unlock path already ignored errors.
