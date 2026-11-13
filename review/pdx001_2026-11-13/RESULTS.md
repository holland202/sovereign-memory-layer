# PDX-001 results (2026-11-13)

**Status:** fixed in the Python reference, the Rust port and the TypeScript port, as registered at `b4f5c23`
([PREREG.md](PREREG.md)). SELF-TESTED: Claude co-built SML and wrote this change. **8 of 8 registered predictions
held** (A8 partly by an equivalent test, see below).

## What is weaker than it looks

- **A8 was only partly rerun.** `review/ts_chatgpt_20261102/review.py` was rerun in full: 337 cases, 0 failed,
  including its case 8 expectation of `insufficient_evidence` after a revoke. BABEL-06 was **not** rerun; its receipts
  are an outside party's run and stay as recorded. The same situation (revoke, then recall) is covered by the new test
  `test_recall_without_current_evidence_is_unchanged`.
- **The fix was not measured on real workloads.** That includes how often callers use the decaying methods, and
  whether exempting protected records crowds out newer facts when many old records are protected. The pre-mortem in
  PREREG.md names this; it is a door.
- **One reproduction step rewrote a recorded artifact.** Running `review/chatgpt_task3/test_contracts.py` rewrote
  `review/chatgpt_task3/raw/contracts.protocol.jsonl`. Only working-directory paths changed. The file was restored and
  is not part of this change.

## Predictions

| ID | Registered | Observed ([before](before_6262dbe.txt) → [after](after_fix.txt)) | Verdict |
|---|---|---|---|
| A1 | Old protected record found 20/20 under each decaying method; `similarity` unchanged | `recency`, `importance`, `protected`: 0/20 → 20/20. `similarity`: 20/20 → 20/20 | HELD |
| A2 | `recall` KNOWN 20/20 under every method | 0/20 → 20/20 under the three decaying methods; 20/20 under `similarity` | HELD |
| A3 | Unprotected scores byte-identical | 872 scores, digest `cf4b9f1d…3f62` before and after | HELD |
| A4 | Current record decayed below threshold → `current_evidence_not_retrieved`, ids `[1]` | `{'status': 'UNKNOWN', 'reason': 'current_evidence_not_retrieved', 'evidence_ids': [1]}` | HELD |
| A5 | Revoked-only key → `insufficient_evidence`, `[]` | Unchanged | HELD |
| A6 | `verify_hardened.py` passes; PDX-1 and PDX-2 killed | 83 tests OK; 21 of 21 mutants killed, including both new ones ([output](verify_hardened_after.txt)) | HELD |
| A7 | `cargo test` passes; differential 0 mismatches for both ports; sabotage still caught | `cargo test`: all pass (one test is `#[ignore]` in source, as before). Rust and TS: `VERDICT IDENTICAL`; both `SABOTAGE CAUGHT` | HELD |
| A8 | Recorded `insufficient_evidence` expectations still hold | TS review: 337 cases, 0 failed. BABEL-06: equivalent test, see above | HELD (partly by an equivalent test) |

## Does the differential cover the new code? (unregistered check, kept)

Each port was broken on purpose, and the quick differential was rerun against it:

| Port broken | Result | Output |
|---|---|---|
| Rust, decay exemption removed | `VERDICT 11 MISMATCH GROUP(S)` | [differential_rust_without_exemption.txt](differential_rust_without_exemption.txt) |
| TypeScript, new reason removed | `VERDICT 41 MISMATCH GROUP(S)` | [differential_ts_without_reason.txt](differential_ts_without_reason.txt) |

So `IDENTICAL` on the fixed ports is evidence of parity on these paths, not a check that cannot fail. Both ports were
restored before the recorded runs.

## The change

- `sml/memory.py` `_retrieve_from`, Rust `retrieve_from`, TS `retrieveFrom`: a record with `protected: true` gets
  decay factor 1 under the decaying methods.
- `recall` in all three: when there is no hit but the key has current records, it returns
  `{"status": "UNKNOWN", "reason": "current_evidence_not_retrieved", "evidence_ids": [...]}`. No value is returned.
- `tests/test_pdx001.py`: 4 tests. `verify_hardened.py`: 79 → 83 tests, plus mutants PDX-1 and PDX-2.
- `MANIFEST_HARDENED.sha256`: updated for the changed files, with the new test added. README: the behaviour change
  stated under limits and history.
- **No file-format change.**

## Doors, unrun

- When many records are protected, does the exemption push newer, relevant, unprotected facts out of the top-k?
- Should `recall` list only current records that could have been scored (excluding future-timestamped ones)? Today
  it lists every current record for the key, the same list the contradiction check uses.
- An outside party running `pdx001.py` and the differential against this commit.

## Provenance

Claude (Anthropic, Opus 5.5) found the issue in an outside-arm test (MEM-DECAY-001 S1, Principia Artificialis). It
then registered, fixed, ported and tested the change, at Chad Holland's direction on 2026-11-13 (direction only).
Human validation: not performed. Human responsibility: Chad Holland.
