# SML Task 3: promise coverage and P3-01 confirmation

AI-generated (ChatGPT, OpenAI), at Chad Holland's direction. Review date: 2026-10-30 (America/New_York). Branch identifier uses the requested `20261031` suffix.

**Baseline:** `4b4bda1064c85500e898505032327b0364f43a29`.
**Branch:** `chatgpt/blind-spots-20261031`.
**Scope:** synthetic engineering tests and review evidence only. No implementation, historical evidence, README, TESTING, canonical method, manifest or CI edits. No push, PR, merge or scientific evaluation performed.

## Decision

**SELF-TESTED / REPRODUCED: P3-01 is confirmed fixed for the tested boundary cases.** Python refuses `max_records=2**63` before creating a directory. Both readers open the permitted `2**63-1` store; both reject above-limit snapshot counters. At counter exhaustion, the mutators tested return `CapacityError` and leave the file byte-for-byte unchanged. A last permitted increment succeeds and produces a file both readers accept.

The retained original probe exits **1**, as predicted in the update, because it assumes the oversized Python create must succeed. Its full output shows the intended new `ValueError`, not a remaining interop defect. The original report and probe hashes match the retained P3-01 record; neither file was changed.

The declared CLI error-label difference is reproduced: Python returns `ValueError`, Rust returns `BadOp` for an out-of-i64 protocol integer, and neither creates a directory. No claim of identical error labels is made.

**Task 3 result:** every headline behavioral promise has at least some existing test coverage. This is not exhaustive coverage. Narrower scenarios lack targeted tests, especially on Rust. This branch adds 10 Python-driven test methods (most exercise both CLIs against explicit contract assertions) and two substantive native Rust tests. All pass. The Rust subprocess helper is intentionally ignored as a standalone test and invoked 16 times by its parent. **No new runtime defect was reproduced.** Two stale documentation statements are recorded below without edits.

## What counts as coverage

**VERIFIED FROM SOURCE** means the named test and its assertions were inspected at the pinned commit; it does not mean its historical result was rerun. **SELF-TESTED** means executed in this review, with full raw output. **REPRODUCED** is used for the observed P3-01 behavior. **NOT RUN** marks unexecuted environments or suites.

A parity test is weaker than an explicit contract oracle: two implementations can agree on the same mistake. D1/D4 compare outputs and file hashes and exercise cross-reading; D3 compares responses to byte mutations/truncations; D5 checks mixed-process record count and IDs; D6 checks acknowledged puts under process kills. None proves every documented property for every input. A named generated operation is not described below as a guaranteed targeted regression case.

Inspected scope: `README.md` / What it does; all of `TESTING.md`; `tests/`; `rust/tests/store.rs`; `tools/differential.py`; Python/Rust store source; `attack/attack.py` and `attack/explore.py`; retained round-2 scripts and task-2 probes. The round-2 archive already covers Python separate-handle threads and a forced correction/compaction gap, so those are not claimed as new gaps.

## Every README / What it does promise

Test names below are the tests present at the baseline, before this branch. `MemoryTests.*` is in `tests/test_memory.py`; `HardeningTests.*` in `tests/test_hardening.py`; `IdentifierRegressionTests.*` in `tests/test_identifier_regression.py`; Rust unqualified test names refer to `rust/tests/store.rs`.

| ID | Promise | Python check at baseline | Rust check at baseline | Limit of existing coverage |
| --- | --- | --- | --- | --- |
| R1 | Keeps facts with a timestamp and a source | `MemoryTests.test_persistent_exact_fact_and_provenance` checks recalled value, provenance and stored timestamp after reopen | `tools/differential.py:d1_d4` compares persisted hashes and recalls | Rust has no dedicated timestamp/provenance golden assertion; new G1 adds one |
| R2 | Correct or withdraw a fact without erasing what was there before | `test_correct_preserves_protected_original`, `test_revocation_returns_unknown_and_retains_evidence`; identifier regression valid correction/revocation tests | D1/D4 exercises both operations and compares bytes; `clock_behind_record_still_allows_revoke_with_clamped_time` checks revocation time | No all-original-fields, distinct-old/new-provenance sentinel on either side; G1 |
| R3 | Hard limits on count and file size; over-limit writes refused; protected records never silently dropped | `test_bound_refuses_protected_overflow_without_partial_correction`, `test_byte_capacity_includes_text_and_metadata`, `test_compaction_cannot_drop_protected_chain`; round-2 hard-limit tests | `capacity_refusals_leave_bytes_unchanged`; generated D1/D4; retained task-2 large-value and compaction cases | No exact-fit versus one-byte-too-small check for put/correct/revoke; G2. Rust protected corrected/revoked chain gets explicit oracle in G1 |
| R4 | Survives being killed mid-write and refuses damaged files | `CrashTests.test_sigkill_at_four_commit_boundaries`, `MemoryTests.test_corruption_is_not_empty_memory`, checksum/semantic validation tests; A2/A3/A5 | `fault_before_replace_leaves_state_after_replace_poisons`; D6 kills puts; D3 mutates files; `deep_nesting_is_integrity_error` | Deterministic real SIGKILL is missing for non-put mutations in Python and all operation boundaries in Rust; G3/G4. Checksum-correct invalid Rust schemas are sparse; G5 |
| R5 | Answers UNKNOWN for missing or contradictory evidence | `test_missing_or_unrelated_fact_abstains`, `test_conflict_cannot_be_hidden_below_topk`, `HardeningTests.test_a8_future_dated_record_cannot_hide_contradiction` | `nfc_nfd_keys_are_one_key_and_controls_refused` asserts UNKNOWN on contradiction; D1/D4 compares generated recalls | No explicit Rust top-k + orthogonal/zero-weight + future-record contradiction case; G6 |

## Every TESTING / What it promises item

| ID | Promise (including all clauses) | Python check at baseline | Rust check at baseline | Gap or qualification |
| --- | --- | --- | --- | --- |
| T1 | Save completes fully or leaves previous state, even if killed | `tests/test_crash.py:CrashTests.test_sigkill_at_four_commit_boundaries`; A5; `MemoryTests.test_failed_write_does_not_report_success`, `test_post_replace_failure_is_explicitly_uncertain` | Fault-stage test plus D6 | G3/G4 add operation-specific boundary kills. Post-replace acknowledgement failures are explicitly uncertain; a process kill is not power loss |
| T2 | Damaged/invalid file is refused with IntegrityError, never wrongly loaded or leaking another error | `test_corruption_is_not_empty_memory`, `test_checksum_detects_valid_json_bit_edit`, `test_semantic_integrity_even_with_recomputed_digest`, `test_duplicate_json_and_nonfinite_payload_rejected`; hardening A1/A10; round-2 M1/R2-05; A2/A3/A4 | D3; deep nesting, lock path, inexact timestamp tests; counter probe | G5 adds checksum-correct semantic fixtures so checksum failure cannot make the validator test pass vacuously. Finite cases cannot prove the universal claim |
| T3 | Protected records never dropped; over-size save refused with nothing changed | Memory count/byte/protected-chain tests listed at R3; A11 | Capacity unit test, D1/D4; retained task-2 cases | G1/G2 add exact assertions; explicit pruning of unprotected chains is an existing API behavior, not a promise to preserve them under compaction |
| T4 | Corrections and withdrawals keep earlier history | Memory and identifier tests listed at R2; round-2 legacy NFD correction | D1/D4 and clamped-revocation test | G1 checks every original field, changing only status/revocation metadata as required, and uses distinct provenance for correction |
| T5 | UNKNOWN when missing/contradictory; never select one value while a different current value exists for that key | Memory missing/top-k conflict tests, hardening future-conflict test, workload conflict oracle | Rust NFC conflict assertion and D1/D4 | G6 explicitly exercises Rust masking conditions together; missing key already generated in D1/D4 |
| T6 | IDs exact positive integers; keys Unicode-normalized; keys and source labels refuse controls | Identifier regression type/nonpositive tests; hardening E1/E2; round-2 R2-03 revocation labels | Rust NFC/key-control unit test; D1 generates invalid integer IDs and bad labels on put | G7 tests malformed CLI ID types; G8 tests source/locator controls specifically on revoke. Rust typed i64 API cannot receive booleans/floats; CLI is separate |
| T7 | Several processes or threads saving concurrently do not lose/duplicate records | Crash concurrent writers; A6; E4 (same-instance threads); retained round-2 parallel compaction/thread tests | D5 mixed Python/Rust processes checks exact IDs/count | **none** for native Rust thread writers in `rust/tests/` or `tools/differential.py`; G9 adds separate-handle threads with exact key and ID sets |

### Other statements in TESTING.md

These are included so limitations and process statements are not mistaken for untested behavioral guarantees.

| Statement | Evidence/check | Disposition |
| --- | --- | --- |
| Manifest command succeeds; verifier gives PASS/exit 0 | `sha256sum -c MANIFEST_HARDENED.sha256`; `python3 verify_hardened.py` | SELF-TESTED, both exit 0; full logs included |
| Python 3.10+, stdlib only; Linux/macOS; Windows unsupported due to POSIX locking | `.github/workflows/ci.yml` declares Python 3.10–3.14 on Linux/macOS; source imports inspected | Source support exists; this run only verifies CPython 3.12.14/Linux. Other platforms/versions NOT RUN; no Windows support is promised |
| Nobody has run Android/Termux yet | Contradicted by checked-in `device_runs/` and the current README's owner-run account | Low-severity documentation finding D1 below; this reviewer did not run the device |
| Copied-back older file accepted, no rollback protection | `attack/attack.py:a14`; historical results | Documented limitation, not a security guarantee; NOT RUN anew |
| No encryption / no protection against someone who can write the folder | Readable JSON writer and checksum code; attack A14 | Source-consistent limitation. No hostile-filesystem protection is tested or claimed here |
| Not tested on real power loss | No such run in this review | NOT RUN; SIGKILL is not a substitute |
| Word hashing, not semantic retrieval | `MemoryTests.test_hash_is_deterministic_lexical_fallback`; `hash_embedding` / Rust hash source | Baseline test executed by verifier; no semantic quality claim inferred |
| Importance not shown to beat most-recent-first | Comparison remains unvalidated; `evaluation.py` protocol gates and evaluation tests | No performance-superiority promise to test; scientific comparisons NOT RUN |
| Testing/reporting free under license; reporting template; passing/failing results get credit; human run desired | LICENSE/COMMERCIAL references and `.github/ISSUE_TEMPLATE/test-report.md` are source records | Policy and review-process statements, not executable store contracts. No legal review or test of future human behavior performed |

## Specific missing checks added (the “none” inventory)

Here “none” means no targeted test of the stated narrow scenario was found at the baseline. It does **not** mean the parent promise lacked all coverage. Broader/parity coverage is named above rather than discarded.

All `Contracts.*` tests live in `review/chatgpt_task3/test_contracts.py`. They invoke both native CLIs, inspect persisted records/bytes, and assert explicit expected errors or fields, not merely equality of two outputs.

| Gap | Baseline targeted check | Added test | Result |
| --- | --- | --- | --- |
| G1 Every original field retained across correction + withdrawal with changed provenance, and protected chain retained | none for that full-field/distinct-provenance combination on either side; selected fields already checked in Python | `test_history_every_original_field_and_new_provenance` | PASS both implementations |
| G2 Exact byte-cap boundary on all put/correct/revoke paths | none for exact fit and one byte below (ordinary overflow already covered) | `test_exact_byte_boundary_all_write_paths` | PASS: 12 side/operation/boundary cases |
| G3 Real SIGKILL at four boundaries for Python correct/revoke/compact | none (put boundaries covered) | `test_python_sigkill_other_mutators_at_commit_boundaries` | PASS: 12 kills; complete old/new snapshot bytes checked |
| G4 Real SIGKILL at four boundaries for Rust put/correct/revoke/compact | none deterministic (fault exceptions and random-time put kills covered) | `rust/tests/chatgpt_blind_spots.rs:sigkill_all_mutators_at_four_boundaries_matches_complete_snapshot` | PASS: 16 kills; signal 9 and complete bytes checked |
| G5 Rust checksum-correct invalid schema bool/float, bad/duplicate IDs, status, vector, orphan and revocation time | none for this explicit semantic fixture set in Rust tests/differential; Python covers several members | `test_checksummed_semantic_invalidity_is_integrity_error` | PASS: nine malformed fixtures per side plus valid restore control |
| G6 Rust conflict obscured jointly by top-k, orthogonal embedding, zero weight and future time | none targeted; generated D1 covers related inputs | `test_contradiction_survives_topk_similarity_and_clock_filtering` | PASS both; UNKNOWN with both evidence IDs |
| G7 Rust CLI rejects boolean/float/string/null record IDs atomically | none in Rust unit/differential for this explicit type set; integer invalid IDs generated | `test_cli_exact_positive_identifiers` | PASS: 28 side/type/operation cases |
| G8 Rust revoke rejects controls in source and locator labels | none in Rust unit/differential specifically on revoke; put labels generated | `test_revoke_source_and_locator_controls` | PASS: 16 side/field/control cases |
| G9 Rust native concurrent threads preserve exact written keys and IDs | none; D5 uses processes | `rust/tests/chatgpt_blind_spots.rs:threads_with_separate_handles_preserve_exact_keys_and_ids` | PASS: six threads, 12 writes each, 72 exact keys/IDs |

G7 case count: 2 implementations × 7 invalid values × 2 operations = **28**. G8: 2 × 2 × 4 = **16**. Subcases are not extra unittest methods.

Python review tests are deliberately outside `tests/`: the existing verifier asserts exactly 79 tests and is untouched. Their explicit command must be run to reproduce this review. New native Rust tests are discovered by ordinary `cargo test`; their standalone SIGKILL child helper is ignored in normal discovery, but is exercised by its parent. No claim is made that new Python probes have been added to CI.

## P3-01 checks authored and executed in this review

- `test_p301_create_and_persisted_counter_bounds`: permitted max create, refused oversized create with no directory, above-limit generation/next_id/max_records/max_bytes load rejection; both implementations.
- `test_p301_all_mutators_at_counter_limit`: generation exhaustion for put/correct/revoke/compact and next_id exhaustion for put/correct; 12 side/counter/operation cases. Each requires CapacityError, unchanged bytes, no pending file, and successful cross-reader reopening.
- `test_p301_last_permitted_increment_then_refusal`: counters starting at MAX−1 can advance once to MAX; the following put is refused atomically and both readers still open the file.

These controls distinguish correct refusal from a store that simply refuses every write. `next_id` is bumped only for insertion/correction, so its exhaustion is not asserted to prevent an operation that does not allocate an ID.

## Findings and limits

- **No new runtime failure:** all new contract tests passed on this pinned commit in this environment. This does not demonstrate bug-freedom.
- **Coverage findings (Low/test infrastructure):** G1–G9 above are specific absent targeted checks. They are now supplied and executed; generated parity coverage alone is not a proof of the contracts.
- **D1 (Low/documentation):** TESTING.md says nobody has run Termux; the repository contains owner-run Termux records and README says they exist. This is a source inconsistency, not this review validating the phone runs. Documentation is preserved unchanged.
- **D2 (Low/documentation, adjacent to requested README section):** README's Run it comment says 69 tests + 12 mutants; the current verifier runs 79 tests and 19 mutants. This review executed those 79/19 successfully. The CI step label also retains 69. No count documentation is changed.
- The original probe's exit 1 is an obsolete expectation, not a new store failure. It remains unchanged and its output is retained in full.
- **NOT RUN:** physical power cuts; hostile writers/filesystems; Windows; macOS; Android/Termux; other Python/Rust versions; scientific memory-quality comparisons; long soaks; exhaustive inputs; full non-quick differential; fresh sabotage campaign. Native Rust MemoryStore is not shared across threads in G9: each thread owns its own handle, matching its non-Send callback types.
- Expected/actual/impact for passing tests: explicit contract assertion matched; no observed lost records, partial committed snapshot, wrong recall answer, crash or hang in the tested cases. D1/D2 affect documentation accuracy, not demonstrated storage behavior.

## Commands and raw evidence

Execute from repository root. Every command has corresponding `raw/<name>.command.txt`, `.exit.txt`, `.stdout.txt`, `.stderr.txt`. These are full outputs, not truncated excerpts. CLI requests and complete subprocess replies for the contract tests are also in `raw/contracts.protocol.jsonl`. Temporary paths identify this run; rerunning the test creates fresh synthetic stores.

| Evidence stem | Exact command | Observed exit |
| --- | --- | ---: |
| manifest | `sha256sum -c MANIFEST_HARDENED.sha256` | 0 |
| build | `cargo build --release --locked --manifest-path rust/Cargo.toml` | 0 |
| original_probe | `python3 review/p3_01/test_large_counter_interop.py --root .` | 1 (intended refusal violates old probe expectation) |
| counter_exhaustion | `python3 review/p3_01/counter_exhaustion.py` | 0 |
| baseline_python | `python3 verify_hardened.py` | 0: 79 tests, 19 killed mutants |
| baseline_rust | `cargo test --release --locked --manifest-path rust/Cargo.toml` | 0: baseline 5 unit + 9 integration tests |
| contracts | `python3 review/chatgpt_task3/test_contracts.py -v` | 0: 10 methods |
| rust_gaps | `cargo test --release --locked --manifest-path rust/Cargo.toml --test chatgpt_blind_spots -- --nocapture --test-threads=1` | 0: 2 passed; 1 child helper ignored standalone |
| differential | `python3 tools/differential.py --quick --rust-bin rust/target/release/sml-cli` | 0: IDENTICAL; D1/D2/D3/D5/D6 |

Baseline Python/Rust tests were executed before adding the new Rust integration test. `raw/environment.json` records CPython, platform, Unicode, rustc verbose version, local toolchain environment, pinned source hashes and preserved original probe/report hashes. Cargo commands used the recorded `CARGO_HOME` and `RUSTUP_HOME` with `<CARGO_HOME>/bin` prepended to PATH. No installation or toolchain files are committed.

### Full quick-differential stdout

```text
D1: {"sequences": 40, "ops": 1640, "mismatches": 0, "first": []} (5s)
D2: {"values": 20000, "mismatches": 0, "first": []} (0s)
D3: {"cases": 3402, "outcomes_py": {"IntegrityError": 3392, "ok": 10}, "mismatches": 0, "first": []} (2s)
D5: {"records": 240, "expected": 240, "exit_codes": [0, 0, 0, 0, 0, 0, 0, 0], "rust_reopen_ok": true, "mismatches": 0} (21s)
D6: {"trials": 20, "acked_total": 538, "unacked_extra_total": 0, "mismatches": 0, "first": []} (5s)
python 3.12.14 | rust bin rust/target/release/sml-cli
VERDICT IDENTICAL
```

Stderr: empty. D5 includes 240 mixed-process writes; D6 includes 20 process-kill trials. These are bounded checks, not device or power-loss validation.

### Full new-test outputs

`python3 review/chatgpt_task3/test_contracts.py -v` — stdout:

```text
{"check": "byte_boundary", "side": "python", "op": "put", "spare": 0, "cap": 3917, "result": {"ok": true, "result": 2}}
{"check": "byte_boundary", "side": "python", "op": "put", "spare": -1, "cap": 3916, "result": {"error": "CapacityError", "ok": false}}
{"check": "byte_boundary", "side": "python", "op": "correct", "spare": 0, "cap": 3905, "result": {"ok": true, "result": 2}}
{"check": "byte_boundary", "side": "python", "op": "correct", "spare": -1, "cap": 3904, "result": {"error": "CapacityError", "ok": false}}
{"check": "byte_boundary", "side": "python", "op": "revoke", "spare": 0, "cap": 2458, "result": {"ok": true, "result": null}}
{"check": "byte_boundary", "side": "python", "op": "revoke", "spare": -1, "cap": 2457, "result": {"error": "CapacityError", "ok": false}}
{"check": "byte_boundary", "side": "rust", "op": "put", "spare": 0, "cap": 3917, "result": {"ok": true, "result": 2}}
{"check": "byte_boundary", "side": "rust", "op": "put", "spare": -1, "cap": 3916, "result": {"error": "CapacityError", "ok": false}}
{"check": "byte_boundary", "side": "rust", "op": "correct", "spare": 0, "cap": 3905, "result": {"ok": true, "result": 2}}
{"check": "byte_boundary", "side": "rust", "op": "correct", "spare": -1, "cap": 3904, "result": {"error": "CapacityError", "ok": false}}
{"check": "byte_boundary", "side": "rust", "op": "revoke", "spare": 0, "cap": 2458, "result": {"ok": true, "result": null}}
{"check": "byte_boundary", "side": "rust", "op": "revoke", "spare": -1, "cap": 2457, "result": {"error": "CapacityError", "ok": false}}
{"check": "python_kill", "op": "correct", "stage": "partial_write", "exit": -9, "new_visible": false, "file_sha256": "3ed3f95d23487eac0f6dd52366b8f29527f40d5c80e6b35739c0c8dd76222c44"}
{"check": "python_kill", "op": "correct", "stage": "after_file_fsync", "exit": -9, "new_visible": false, "file_sha256": "3ed3f95d23487eac0f6dd52366b8f29527f40d5c80e6b35739c0c8dd76222c44"}
{"check": "python_kill", "op": "correct", "stage": "after_replace", "exit": -9, "new_visible": true, "file_sha256": "f092e58e01440ee27779ffd078fd89d5e889eadc863c34a010a9fd533785fb8c"}
{"check": "python_kill", "op": "correct", "stage": "after_dir_fsync", "exit": -9, "new_visible": true, "file_sha256": "f092e58e01440ee27779ffd078fd89d5e889eadc863c34a010a9fd533785fb8c"}
{"check": "python_kill", "op": "revoke", "stage": "partial_write", "exit": -9, "new_visible": false, "file_sha256": "3ed3f95d23487eac0f6dd52366b8f29527f40d5c80e6b35739c0c8dd76222c44"}
{"check": "python_kill", "op": "revoke", "stage": "after_file_fsync", "exit": -9, "new_visible": false, "file_sha256": "3ed3f95d23487eac0f6dd52366b8f29527f40d5c80e6b35739c0c8dd76222c44"}
{"check": "python_kill", "op": "revoke", "stage": "after_replace", "exit": -9, "new_visible": true, "file_sha256": "08cf6db12ae42774d269c0d20a1952708b10b5a17eb03c03d61ba0e806ed215d"}
{"check": "python_kill", "op": "revoke", "stage": "after_dir_fsync", "exit": -9, "new_visible": true, "file_sha256": "08cf6db12ae42774d269c0d20a1952708b10b5a17eb03c03d61ba0e806ed215d"}
{"check": "python_kill", "op": "compact", "stage": "partial_write", "exit": -9, "new_visible": false, "file_sha256": "3ed3f95d23487eac0f6dd52366b8f29527f40d5c80e6b35739c0c8dd76222c44"}
{"check": "python_kill", "op": "compact", "stage": "after_file_fsync", "exit": -9, "new_visible": false, "file_sha256": "3ed3f95d23487eac0f6dd52366b8f29527f40d5c80e6b35739c0c8dd76222c44"}
{"check": "python_kill", "op": "compact", "stage": "after_replace", "exit": -9, "new_visible": true, "file_sha256": "b8fbb44268fbb059557e551a74fba814d261ab81cdd49abdc27e55ad06fbc0a3"}
{"check": "python_kill", "op": "compact", "stage": "after_dir_fsync", "exit": -9, "new_visible": true, "file_sha256": "b8fbb44268fbb059557e551a74fba814d261ab81cdd49abdc27e55ad06fbc0a3"}
```

Stderr (unittest reporting):

```text
test_checksummed_semantic_invalidity_is_integrity_error (__main__.Contracts.test_checksummed_semantic_invalidity_is_integrity_error) ... ok
test_cli_exact_positive_identifiers (__main__.Contracts.test_cli_exact_positive_identifiers) ... ok
test_contradiction_survives_topk_similarity_and_clock_filtering (__main__.Contracts.test_contradiction_survives_topk_similarity_and_clock_filtering) ... ok
test_exact_byte_boundary_all_write_paths (__main__.Contracts.test_exact_byte_boundary_all_write_paths) ... ok
test_history_every_original_field_and_new_provenance (__main__.Contracts.test_history_every_original_field_and_new_provenance) ... ok
test_p301_all_mutators_at_counter_limit (__main__.Contracts.test_p301_all_mutators_at_counter_limit) ... ok
test_p301_create_and_persisted_counter_bounds (__main__.Contracts.test_p301_create_and_persisted_counter_bounds) ... ok
test_p301_last_permitted_increment_then_refusal (__main__.Contracts.test_p301_last_permitted_increment_then_refusal) ... ok
test_python_sigkill_other_mutators_at_commit_boundaries (__main__.Contracts.test_python_sigkill_other_mutators_at_commit_boundaries) ... ok
test_revoke_source_and_locator_controls (__main__.Contracts.test_revoke_source_and_locator_controls) ... ok

----------------------------------------------------------------------
Ran 10 tests in 3.898s

OK
```

Native Rust gap-test stdout:

```text

running 3 tests
test sigkill_all_mutators_at_four_boundaries_matches_complete_snapshot ... op=put stage=partial_write signal=9 complete_new_visible=false PASS
op=put stage=after_file_fsync signal=9 complete_new_visible=false PASS
op=put stage=after_replace signal=9 complete_new_visible=true PASS
op=put stage=after_dir_fsync signal=9 complete_new_visible=true PASS
op=correct stage=partial_write signal=9 complete_new_visible=false PASS
op=correct stage=after_file_fsync signal=9 complete_new_visible=false PASS
op=correct stage=after_replace signal=9 complete_new_visible=true PASS
op=correct stage=after_dir_fsync signal=9 complete_new_visible=true PASS
op=revoke stage=partial_write signal=9 complete_new_visible=false PASS
op=revoke stage=after_file_fsync signal=9 complete_new_visible=false PASS
op=revoke stage=after_replace signal=9 complete_new_visible=true PASS
op=revoke stage=after_dir_fsync signal=9 complete_new_visible=true PASS
op=compact stage=partial_write signal=9 complete_new_visible=false PASS
op=compact stage=after_file_fsync signal=9 complete_new_visible=false PASS
op=compact stage=after_replace signal=9 complete_new_visible=true PASS
op=compact stage=after_dir_fsync signal=9 complete_new_visible=true PASS
ok
test task3_kill_worker ... ignored, SIGKILL child helper; invoked only by parent test with fixture environment
test threads_with_separate_handles_preserve_exact_keys_and_ids ... threads=6 writes_each=12 acknowledged=72 exact_keys=72 ids=1..72 PASS
ok

test result: ok. 2 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 1.02s

```

Native Rust gap-test stderr:

```text
   Compiling sml v0.1.0 (/workspace/scratch/023a3d579cb0/sml-review/rust)
    Finished `release` profile [optimized] target(s) in 0.53s
     Running tests/chatgpt_blind_spots.rs (rust/target/release/deps/chatgpt_blind_spots-f52ed60da657ad8c)
```

### Scope verification

The retained P3-01 probe SHA-256 is `b17ae480bec54745b61511b58dcb75bbecebae3fbadf62dd4979e4556737ec3e`; its report SHA-256 is `c396b4c64dbdf5ae70b6dcba48703f2132e350fac5e4c8734e9cae2c90e0a71e`. Both match the original record. The baseline manifest still passes after adding these unlisted review tests. No original file is edited; the only new locations are `review/chatgpt_task3/` and `rust/tests/chatgpt_blind_spots.rs`. Final scope commands/results are retained in `raw/final_scope.txt`.

Whitespace check qualification: `git diff --check` reports trailing blank lines in the two raw Cargo stdout files. Those bytes are retained as emitted. The check excluding raw evidence passes; this is not a source-code whitespace failure. Exact output and exits are in `raw/final_scope.txt`.
