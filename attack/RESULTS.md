# SML-ATK-001: results (Claude's break-it pass, 2026-10-30)

**Self-tested.** Claude (Anthropic, Opus 5.5) wrote the plan, the attacks, the fixes and the tests, and judged the outcomes, at Chad Holland's direction. None of this is independent. ChatGPT's attack comes next, and people after that. Everything ran in an x86_64 Linux container, Python 3.13.18: **NOT VALIDATED on the S25.**

## What could have gone wrong, first

- **The attacks only reach what the code reading suggested.** A different attacker will try different things; that is why the next step is ChatGPT, then people.
- **Untested:**
  - real power loss and a hostile filesystem;
  - Termux/Android's filesystem and `flock`;
  - long soak runs;
  - inputs larger than a few MB.
- **Two of my own rules were wrong:**
  - A3 predicted that every truncation fails. Cutting only the final newline still loads the identical payload, which is harmless, so A3 is REFUTED as written and kept.
  - A11's harness marks "defect" because its pass rule wrongly treated an allowed revocation at the record cap as a failure. Revoking adds no record, so allowing it is correct. The raw output is unchanged.
- **E1–E5 were added after run 1.** They are exploratory, not registered.
- **The fixes change behaviour** (details below). In particular, keys are now NFC-normalized, and new keys or provenance with control or format characters are refused. Existing stores still load.

## Registered predictions vs. what happened (run 1, unchanged candidate)

| ID | Prediction | Run 1 | After fixes (run 2) |
|---|---|---|---|
| A1 | deep JSON nesting leaks `RecursionError` (defect predicted) | **HELD**: `RecursionError` escaped | `IntegrityError` |
| A2 | 3,000 byte flips: never a different accepted payload | **HELD**: 2,996 rejected, 4 identical, 0 different | same |
| A3 | every truncation is rejected | **REFUTED**: 398 rejected; 1 accepted (final newline only, identical payload, harmless) | same |
| A4 | hand-made bad files all give `IntegrityError` | **HELD**: 10/10 | same |
| A5 | 150 SIGKILLs during writes lose no acknowledged write | **HELD**: 150/150 reopened; 5,641 acknowledged, 0 lost; 5 unacknowledged extras, at most 1 per trial | same (5,629 acknowledged) |
| A6 | 8 processes × 40 puts give 320 unique records | **HELD**: 3/3 rounds | same |
| A7 | a clock behind a record blocks revoke and correct (defect predicted) | **HELD**: both refused | revoke **fixed**; correct still refused (by decision, below) |
| A8 | clock skew hides a contradiction (defect predicted) | **HELD**: UNKNOWN became KNOWN "old" | UNKNOWN (contradiction) |
| A9 | odd Unicode gives a clean `ValueError`, store unchanged | **HELD**: no crashes; NUL and bidi characters were accepted in keys and provenance (see E2) | keys and provenance now refuse them |
| A10 | a lock path that is a directory gives a raw `OSError` (partial defect predicted) | **HELD**: `IsADirectoryError` | `IntegrityError` |
| A11 | writes at the record and byte caps are refused, unchanged | **HELD** for put/correct/compact; revoke allowed (correct: it adds no record); the file stays within `max_bytes`. The harness label is wrong, see above | same |
| A12 | 300 random 40-operation sequences match a reference model | **HELD**: 12,000 ops, 0 mismatches | same |
| A13 | extreme embeddings never produce an unreadable store | **HELD** | same |
| A14 | rollback to an older valid file is accepted (known limit) | **HELD**: accepted | unchanged (documented limit) |
| A15 | `force_scar` under `SCAR_LOCK` | observed: not stored | same. A documented, deliberate deviation from the June spec (`MATHEMATICAL_AUDIT.md`) |

**Anti-vacuity** (`results/antivacuity_mutants.txt`):
- A2 caught a planted checksum bypass (28 different payloads accepted).
- A12 caught a planted supersession bug (104 mismatches).
- A6 caught a no-op lock (corrupted stores, lost writes).
- A3 cannot see a checksum bypass, because truncation always breaks the JSON. That is recorded here, not hidden.

## Exploratory (after run 1)

| ID | Found | After fixes |
|---|---|---|
| E1 | The same visible key in NFC and NFD forms was two keys, so a contradiction could be hidden: KNOWN "open" while "closed" also existed | one key; UNKNOWN (contradiction) |
| E2 | Keys and provenance accepted NUL, bidi override (U+202E), zero-width space and newlines. These spoof what an explanation displays | refused in keys, source and locator; values may still contain newlines |
| E3 | Errors injected at each commit stage | clean before and after: state unchanged before replace; `CommitUncertain` and a poisoned instance after |
| E4 | 8 threads × 40 puts on one instance | clean: 320 unique |
| E5 | Storage cost: about 2,146 bytes per record (the 384-number embedding). The default limit is 128 records | observation; not changed |

## Fixes (all in `sml/memory.py`, each pinned by a test and by a mutant that must fail)

1. **A1:** `RecursionError` while reading becomes `IntegrityError`.
2. **A10:** a lock file that cannot be opened becomes `IntegrityError`.
3. **A7:** revocation is never blocked by a clock that is behind. Its time is clamped to the record's own timestamp, never earlier. **Correction under a behind clock is still refused,** because the new record would be dated before the one it corrects. The workaround is to revoke, then put. This is a decision for the owner.
4. **A8:** contradiction checks count every current record of the key, including ones the clock calls "future".
5. **E1:** keys are NFC-normalized on write and compared NFC-to-NFC on read. Old stores with non-NFC keys still load and match.
6. **E2:** new keys and provenance source/locator refuse control (Cc), format (Cf) and surrogate (Cs) characters.

`python3 verify_hardened.py`:
- 60 tests pass (42 original, 9 identifier, 9 hardening);
- all 6 fix-removal mutants are killed;
- exit 0.

`verify_candidate.py` is kept unchanged and now refuses this tree, because it pins the earlier candidate's source hash. That is intended.

## Known limits that remain (not fixed)

- **Rollback and replay:** a copied-back older valid file is accepted (A14). The checksum detects accidents, not tampering.
- **No power-loss test.** After `mkdir` at creation, the parent directory is not fsynced.
- **Cooperative writers only:** anyone who can write the folder can replace files. No encryption.
- **Retrieval:** a lexical hash, not semantic understanding. Exact string values, so "Blue" and "blue" contradict.
- **Weighting:** the importance weighting has not been shown to beat recency. That is the separate SML comparison, still blocked.
