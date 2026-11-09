# FLY-002 — storage that returns different bytes than were written. Registration

**Status:** REGISTRATION, written before the harness exists. **Date:** 2026-11-09. **Base:** `1eef4a0`.
**Supersedes:** [FLY-001](../fly001_2026-11-09/RESULTS.md), which is VOID and kept unchanged.
**Origin:** the fsync-lying test proposed by Shivashish Jaishy. **Self-tested; he has not run it.**

## Why a second registration rather than a retune

FLY-001 modelled the lie as truncation. Truncation leaves invalid JSON, so `json.loads` raises
inside `_decode` before the `env["sha256"] != digest(s)` comparison is reached, and both failures
exit through the same `except` clause as `IntegrityError`. The sabotage run proved it: with the
checksum deleted, the verdict did not move. FLY-001 measured the JSON parser.

The failure mode it could not reach is the more dangerous one. A storage layer that acknowledges a
write and later returns **different bytes of the same length** produces a file that parses
perfectly. Nothing but the digest can object.

## Model

Commit normally. Then, outside the process, change one character inside a stored record's `value`
string in `memory.json`, keeping the JSON valid and the snapshot schema intact. `_encode` writes
`{"payload": <state>, "sha256": digest(state)}`, so the payload now disagrees with its recorded
digest while remaining a structurally valid snapshot that `_validate` accepts.

This models silent corruption, not a power cut. It does not model lost writes, reordering, or a
filesystem that also damages the envelope's own `sha256` field.

## Predictions

- **P0 (anti-vacuity).** Honest path, no corruption: commit and recall return the written value. If
  this fails the harness is broken, not SML.
- **P1.** After corruption, the reader raises `IntegrityError` **whose message names the checksum**.
  The message is load-bearing: FLY-001 raised `IntegrityError` for an unrelated reason and that is
  exactly how it fooled itself. An `IntegrityError` carrying a `JSONDecodeError`, or any other
  cause, does **not** satisfy P1.
- **P2.** The corrupted value is never returned. No `KNOWN` answer carries the damaged string.
- **P3 (sabotage, load-bearing).** With the `env["sha256"] != digest(s)` check neutered, **P1 must
  fail**. The expected consequence is that `recall` returns the corrupted value as a confident
  answer. If P1 still passes with the checksum gone, FLY-002 is void exactly as FLY-001 was.
- **P4.** Store usability after the damage is **recorded, not predicted**. FLY-001 observed that
  `cleanup_incomplete()` plus a reopen did not recover a damaged store, but inside a void setup that
  observation carries no weight. Whatever happens here is reported as an observation; no direction
  is registered, so no outcome counts as a failure of SML.

## Refutation criteria

P3 passing voids FLY-002. P1 or P2 failing is a real finding about SML and is kept and reported as
found — not retried with different damage until it passes.

## Not covered

Real power loss. Lost or reordered writes. Damage to the envelope's own digest field. Android
storage — this runs in a container unless and until it runs on the S25. The Rust implementation.

## AI provenance

Registered by Claude (Anthropic) on owner direction, 2026-11-09, before the harness was written.
Proposed originally by Shivashish Jaishy. Not independently reviewed.
