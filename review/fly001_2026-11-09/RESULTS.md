# FLY-001 results — **VOID**. The sabotage control refuted the experiment, not the software.

**Verdict: VOID by this experiment's own refutation criterion.** No claim about SML follows from it.
**Date:** 2026-11-09. **Registration:** [PREREG.md](PREREG.md), written before the harness existed.
**Base:** `1eef4a0`. **Self-tested.** Shivashish Jaishy proposed the fsync-lying test; he did not run
this and no part of this result is attributable to him.

## What went wrong, first

The registration said: with the sha256 check removed, P2 **must** fail. It did not. Both runs gave
the identical verdict.

```
registered run   P1/P2  HELD   IntegrityError: JSONDecodeError: Expecting ',' delimiter: line 1 column 1316
SABOTAGE run     P1/P2  HELD   IntegrityError: JSONDecodeError: Expecting ',' delimiter: line 1 column 1316
```

**The checksum was never what caught the tear.** Truncating the pending file leaves invalid JSON, so
`json.loads` raises inside `_decode` before the `env["sha256"] != digest(s)` comparison is ever
reached. Both failures are wrapped into `IntegrityError` by the same `except` clause, so from the
outside the two runs are indistinguishable.

The experiment claimed to test SML's integrity check. It tested that Python's JSON parser rejects
half an object. Those are different properties and only the sabotage run separates them.

By the refutation criteria in PREREG.md — "P4 passing voids the experiment" — FLY-001 is void. It is
kept rather than retuned, because retuning a registered test until it passes is the move the method
exists to prevent.

## Observed, explicitly NOT claimed

Inside a void setup these cannot be distinguished from artefacts of the model:

- **The store did not recover.** After the tear, `cleanup_incomplete()` followed by a reopen still
  raised `IntegrityError`; P3 read FAILED. Whether that is a real durability property or a
  consequence of how this harness damaged the file is undetermined. [FLY-002](../fly002_2026-11-09/)
  re-registers it.
- P0 held: with fsync honest and no truncation the same path commits and recalls normally. That only
  shows the harness drives the real code.

## Why this is worth keeping

Without the sabotage control this would have been written up as "SML fails closed under a lying
fsync, verified." That sentence would have been true in its outcome and wrong in its reason, and
nothing in the passing run would have revealed it. The control cost one extra execution and it is
the only reason the write-up is not an overclaim.

The successor is [FLY-002](../fly002_2026-11-09/PREREG.md), which models silent corruption instead:
damage that leaves **valid** JSON, so the parser is satisfied and only the digest can object.

## AI provenance

Registered, built, run and judged VOID by Claude (Anthropic) on owner direction, 2026-11-09. Not
independent review. Human validation: not performed. Human responsibility: Chad Holland.
