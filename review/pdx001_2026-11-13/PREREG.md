# PDX-001: protected records exempt from retrieval decay; recall says when current evidence was not retrieved

**Status:** REGISTERED before any source change. The pre-fix measurement (`before_6262dbe.txt`) was taken first,
on `6262dbe`; it reproduces an earlier outside-arm result, as disclosed below. Results go in `RESULTS.md`. This file
is not edited afterwards; corrections are appended with a date.

**Authorization.** Chad Holland approved this source change on 2026-11-13, after the MEM-DECAY-001 S1 result was
reported to him.

## Why

[MEM-DECAY-001 S1](https://github.com/holland202/principia-artificialis/blob/main/experiments/mem_decay_001/RESULTS_S1.md)
(Principia Artificialis, run against this repository at `6262dbe` through the public API) found two things:

- **An old protected record is never returned under the three decaying retrieval methods.** It was found 0/50 times
  by `retrieve` with `recency`, `importance` or `protected`. `protected` shields a record from `compact()`, not from
  the decay factor.
- **`recall(key, method=...)` on such a record answers UNKNOWN with `insufficient_evidence`**, while the record is
  stored, current and protected.

`before_6262dbe.txt` reproduces this here. Over 20 cases:

- `retrieve` and `recall` find the old protected record 20/20 under `similarity`, and 0/20 under each decaying method.
- A current unprotected record decayed below the threshold gets
  `{'status': 'UNKNOWN', 'reason': 'insufficient_evidence', 'evidence_ids': []}`, the same answer as a key whose only
  record is revoked.

## The change (Python reference, Rust port and TypeScript port, identically)

1. **The decay factor is 1 for protected records.** In `_retrieve_from` (Rust `retrieve_from`, TS `retrieveFrom`), a
   record with `protected: true` gets decay factor 1 under `recency`, `importance` and `protected`. `similarity` is
   unchanged; it never applied decay. Unprotected records are untouched. The explanation's `decay_factor`
   (Rust `Hit.decay`) reports 1 for protected records under decaying methods.
2. **`recall` distinguishes "not retrieved" from "no evidence".** When the key has at least one `current` record, no
   contradiction, and retrieval returns no hit, `recall` returns:

   ```
   {"status": "UNKNOWN", "reason": "current_evidence_not_retrieved", "evidence_ids": [ids of the key's current records]}
   ```

   - The status stays UNKNOWN, so no value is returned (fail-closed).
   - `insufficient_evidence` with `[]` is kept for keys with no current record.
   - The id list is the same `current` list the contradiction check already uses, in file order.

This changes behaviour for callers that use a decaying method on protected records, or that read the UNKNOWN reason.
It does not change the file format.

## Registered predictions (judged on `pdx001.py` and the repository's own checks after the fix)

| ID | Prediction |
|---|---|
| A1 | `retrieve` finds the old protected record 20/20 under each of `recency`, `importance` and `protected`, and 20/20 under `similarity` (unchanged) |
| A2 | `recall` answers KNOWN 20/20 under every method |
| A3 | **Unprotected scores are unchanged.** The digest over all 872 scores given to unprotected records equals the pre-fix digest `cf4b9f1dc8ff9ebe8fbbacad4460268726ac515f4115adfedbfecba37a263f62` |
| A4 | A current unprotected record decayed below the threshold gives `current_evidence_not_retrieved` with its id `[1]` |
| A5 | A key whose only record is revoked still gives `insufficient_evidence` with `[]` |
| A6 | `verify_hardened.py` passes, with two new fix-removal mutants (PDX-1: exemption removed; PDX-2: reason removed) both killed by new tests |
| A7 | `cargo test` passes, and `tools/differential.py --quick` finds 0 mismatches for the Rust port and for the TS port. Each port's `--sabotage` run is still caught |
| A8 | The two recorded expectations of `insufficient_evidence` still hold: `review/ts_chatgpt_20261102/review.py` case 8 and BABEL-06. Both occur after a revoke, when no current record exists |

## What would make this wrong

- Something already relies on old protected records being down-ranked under `recency`. Nothing in this repository's
  tests or reviews was found to; A6 and A7 check it.
- The new reason breaks a caller that string-matches `insufficient_evidence` on keys that do have current records.
  That is a behaviour change, and it is stated in the README.

## Provenance

Claude (Anthropic, Opus 5.5) wrote this at Chad Holland's direction, 2026-11-13 (direction only). Claude co-built SML,
so every result here is SELF-TESTED. Human validation: not performed. Human responsibility: Chad Holland.
