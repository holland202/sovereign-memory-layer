# FLY-002 results — the sha256 check is load-bearing, and this run shows it is what does the work

**Verdict: 3 of 3 registered predictions held; the sabotage control refuted P1 as required.**
**Date:** 2026-11-09. **Registration:** [PREREG.md](PREREG.md), committed before the harness existed.
**Base:** `1eef4a0`. **Container only — NOT RUN on the S25.**
**Self-tested.** Shivashish Jaishy proposed the fsync-lying test. He has not run this, has not
reviewed it, and no part of this result is attributable to him.

## What could have gone wrong, first

[FLY-001](../fly001_2026-11-09/RESULTS.md) is VOID and kept. It modelled the lie as truncation,
which leaves invalid JSON, so the parser objected before the digest was consulted and deleting the
checksum changed nothing. It measured `json.loads`. FLY-002 exists because of that failure, and its
P1 was therefore written to require the error **message** to name the checksum — an `IntegrityError`
alone is exactly what fooled FLY-001.

## Raw output

Registered run:

```
P0  HELD    honest commit -> status='KNOWN' value='one'
P1  HELD    IntegrityError: ValueError: checksum mismatch
P2  HELD    no value returned
P4  OBSERVED not recovered: IntegrityError: ValueError: checksum mismatch
VERDICT 3 of 3 registered predictions held
```

Sabotage run, with `env["sha256"] != digest(s)` neutered:

```
P1  FAILED  no exception; recall('beta') status='KNOWN' value='twX'
P2  FAILED  no exception; recall('beta') status='KNOWN' value='twX'
VERDICT sabotage HELD (P1 failed as required)
```

## What this shows

A storage layer that acknowledges a write and later returns different bytes of the same length
produces a file that parses perfectly and validates against the snapshot schema. The only thing
standing between that file and a confident wrong answer is the digest comparison in `_decode`.

**With the check in place**, the reader refuses, and the refusal names its reason.
**With the check removed**, `recall` returns `status='KNOWN' value='twX'` — the corrupted string,
presented with full confidence, no warning, no degraded status.

That second line is the finding. It is not a defect; the check is there and it works. It is a
measurement of how much that one comparison is carrying, which was previously assumed rather than
shown.

## What this does **not** show

- Nothing about real power loss, lost writes, or reordering.
- Nothing about damage to the envelope's own `sha256` field. If a corrupting storage layer rewrote
  the digest to match the damaged payload, this check would pass. That case is untested and is the
  door this note leaves.
- Nothing about Android. The whole run is x86_64 container, Python 3.13.18. SKR-001 was run on the
  S25; this has not been, and today's work in another repository turned up a platform-dependent
  defect that no container could see. **Treat this as unvalidated on the device.**
- Nothing about the Rust implementation in `rust/`, which has its own `flock` path and was not
  touched.

## P4, recorded as an observation and not a prediction

After the corruption, `cleanup_incomplete()` followed by a reopen still raised
`IntegrityError: checksum mismatch`. The store does not recover and there is no documented path back.

Failing closed on an integrity violation is the right default and nothing here argues otherwise. The
open question is narrower: a store damaged this way is permanently unreadable, and the API offers no
quarantine-and-restart. Whether that is intended, and what an operator is meant to do at that point,
is undecided. No direction was registered, so this counts as neither a pass nor a failure.

## AI provenance

Registered before the harness existed, built, run and judged by Claude (Anthropic) on owner
direction, 2026-11-09. Not independent review. Human validation: not performed. Human
responsibility: Chad Holland. Review level: direction only.
