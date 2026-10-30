# SML-ATK-001: break-it attack plan (registered before any attack runs)

**Target:** `sml/memory.py` at the identifier-fix candidate (`f0f8fb55…bae82`), imported verbatim in this repository's first commit. `sml/policies.py` is included.
**Who:** Claude (Anthropic, Opus 5.5), at Chad Holland's direction, 2026-10-30. **Self-tested**: Claude designs, runs and judges these attacks. They are not independent, and ChatGPT's attack comes next.
**Rule:** every attack runs first against this unchanged code, and its outcome is kept. Fixes come in later commits; this file is never edited.

## Pre-mortem

How this attack could fail to find real defects:
- it tests only what the code reading suggested;
- it runs in an x86_64 container, not the S25;
- it has no real power loss, no hostile filesystem and no long soak;
- every fuzz seed is chosen by Claude.

## Predictions

A prediction is **HELD** when the stated outcome is observed exactly. "Defect predicted" rows say I expect to find a defect.

| ID | Attack | Predicted outcome |
|---|---|---|
| A1 | `memory.json` replaced by deeply nested JSON (100,000 levels, under the 16 MB cap) | **Defect predicted:** `RecursionError` escapes instead of `IntegrityError` |
| A2 | 3,000 seeded single-byte flips of a valid `memory.json` | Every load either raises `IntegrityError` or returns a payload identical to the original. Never a different accepted payload, never another exception |
| A3 | Truncation at 400 seeded offsets, plus 0 bytes and length−1 | Every load raises `IntegrityError` |
| A4 | Hand-made bad files: duplicate key, `NaN`, 5,000-digit integer, wrong types, extra fields, missing envelope, invalid UTF-8, empty file | All give `IntegrityError` |
| A5 | 150 trials: a child process doing puts is killed with SIGKILL at a random delay | After every kill the store reopens valid. Every acknowledged write is present, at most one unacknowledged write is extra, and IDs are unique |
| A6 | 8 processes × 40 puts concurrently | 320 records, IDs 1..320 unique, valid on reopen |
| A7 | The clock moves backwards to before an existing record's timestamp | **Defect predicted:** `revoke()` and `correct()` of that record are refused, so a fact cannot be withdrawn |
| A8 | Same clock skew; `recall()` of a key with a record that is now "in the future" | **Defect predicted:** that record is ignored, so a contradiction can be hidden and KNOWN returned |
| A9 | Lone surrogates and other odd Unicode in key/value/text/provenance/reason | A clean `ValueError`, snapshot bytes unchanged |
| A10 | `memory.lock` or `memory.json` replaced by a directory; `memory.json` missing | **Partial defect predicted:** a lock path that is a directory raises a raw `OSError`, not `IntegrityError`. The other cases give `IntegrityError` |
| A11 | Fill to `max_records` / `max_bytes` with protected records, then put / correct / revoke / compact | `CapacityError` or `ValueError`, snapshot bytes unchanged |
| A12 | 300 seeded random sequences of 40 operations (put / correct / revoke / compact / recall), checked against a small reference model | Store state and `recall()` status/value always match the model |
| A13 | Embedding extremes: 1e-200 entries, mixed 1e100 and 1e-100, ±0, a single nonzero | A clean `ValueError` or a valid store; never a written-but-unreadable store |
| A14 | Rollback: copy an older valid `memory.json` over the current one | **Known limit predicted:** accepted silently (documented "not rollback") |
| A15 | `policies.admit` with `force_scar=True` under `SCAR_LOCK`, checked against the spec line in `docs/SPEC_CONFORMANCE` (original package) | Report what the code does; no prediction about the spec |

## Anti-vacuity

- **A2 and A3 must catch a planted checksum bypass.** Run them against a copy with the `# MUTATION: checksum` line disabled; at least one accepted-different-payload must appear.
- **A12 must catch a planted defect.** Run it against a copy with the `# MUTATION: supersession` line disabled; at least one model mismatch must appear.
- **A5 and A6 must catch a planted defect.** Run them against a copy whose lock is a no-op; lost or duplicate writes must appear in at least one run. If they don't, record that the attack cannot see lock bugs on this machine.
