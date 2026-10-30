# SML — second reliability and correctness review

October 30, 2026 · Chad Holland · **AI-assisted / AI-generated: ChatGPT**

**Result: five reproducible failure groups and one minor format-policy observation. No target code was edited and no fix was applied.** The original 60-test baseline passes. The added review has 14 separate scripts containing 19 unittest methods: seven scripts exit 0 and seven exit 1. Two failing scripts exercise the same re-entrancy problem; one failing script concerns the lower-priority schema-tag observation. These counts are engineering checks, not independent samples or scientific validation.

This is a separate AI-assisted technical review, not independent human review or a security certification. All runtime checks used synthetic data and temporary local files; the tests make no network calls. The importance-weighting comparison and all scientific campaigns remain unrun.

## Input identity and required setup

| Item | Observed value |
|---|---|
| Supplied ZIP | `SML_HARDENED_ROUND1.zip`, 348,410 bytes |
| ZIP SHA-256 | `34fda35ecc4afa49fee1e12f553db96f56e3d9503531bd75b4bf58c001be4728` |
| `sml/memory.py` SHA-256 | `507baf59d474f399b8b662926968109d6e7630fc15e6498aacf9ae1af5564b18` |
| `MANIFEST_HARDENED.sha256` SHA-256 | `6f1ce9b96f5e5a1b8c2e4e57b7359f16c51baaaaddd0517df0a960b510be5538` |
| Python | 3.12.14, Clang 22.1.3 |
| OS | Linux 6.18.57 x86_64, glibc 2.39 |
| Filesystem observed | overlayfs for workspace and `/tmp` |
| Required manifest check | **34/34 lines OK**, exit 0, before review and after all checks |
| Required baseline | `python3 verify_hardened.py`: **exit 0; 60 tests; six fix-removal mutants reported killed; PASS** |

`ENVIRONMENT.json` records the full interpreter/platform strings and exact commands. `raw/00_manifest.*`, `raw/01_baseline.*`, and `raw/99_manifest_after.*` preserve the complete setup/final-check outputs. The original ZIP and every manifest-covered supplied file remain unchanged. Python cache files created by ordinary execution are not source edits.

Use a fresh extraction of the original ZIP. Each test below lives outside the target, accepts `--target /absolute/path/to/sml-hardening`, and fails with exit **1** on this version where indicated. The appendix includes the exact commands actually run and their entire stdout/stderr. No finding depends on a scientific task battery.

## R2-01 — an absent `None` key returns another key's KNOWN value

**Impact: wrong answer. Priority: high.**

Check: `scripts/test_missing_key_known.py` — **exit 1**.

Expected: a missing/invalid key must be rejected explicitly or return UNKNOWN. No record exists for `None`.

Observed: after storing `synthetic.alpha → alpha-value` and `synthetic.beta → beta-value`, `recall(None, query='synthetic missing key', embedding=E)` returns **KNOWN `alpha-value`**, with evidence IDs `[1, 2]`. Positive controls show valid-key recall works and an absent string key returns UNKNOWN.

Cause visible in the pinned source: `recall()` does not validate its key, while `_retrieve_from(..., key=None)` uses None to disable key filtering. Supplying a query or explicit embedding reaches this path. This is a missing-argument case; no malicious callback or file edit is needed. It does **not** demonstrate contradictory valid string keys escaping the contradiction guard.

Suggested direction, not an applied fix: validate the recall key before taking the snapshot or invoking retrieval. Retain the None/explicit-query and None/embedding regressions, valid-key controls, and absent-string UNKNOWN behavior.

## R2-02 — callbacks can self-deadlock in the store lock

**Impact: crash / hang.**

Checks: `scripts/test_clock_reentry.py` and `scripts/test_fault_reentry.py` — **both exit 1**.

Expected review rule: a callback reading the store should complete, or re-entrancy should be rejected with an explicit error. The API currently supplies no enforced non-re-entrancy restriction. An indefinite lock wait is not an explicit rejection.

Observed:

- A `clock()` callback calling `m.snapshot()` during `m.revoke(...)` blocks.
- A `fault()` callback calling `m.snapshot()` at `partial_write` blocks.
- The same callback at `after_replace` also blocks.

Each child prints that it entered the callback. A traceback dumped after two seconds shows it waiting in `_lock` at the `flock` call; the parent kills the child after five seconds. The appendix preserves the complete child tracebacks, not just a timeout label. The tests accept successful completion or a documented explicit rejection, and do not treat import failures as success.

The clock/fault callback runs while the outer operation holds the store lock, then opens the lock again through `snapshot()`. This reproduces a lock cycle on the tested filesystem. The five-second cutoff bounds the test; no five-second production latency guarantee is being invented.

Recovery controls: the previously acknowledged record survived. At `partial_write`, only the old record is present; at `after_replace`, the unacknowledged new record is also present. **No acknowledged-record loss was demonstrated by these cases.**

Suggested direction: choose and enforce a re-entrancy policy, preferably a clear rejection before attempting the nested lock. Simply enabling nested writes would require additional transaction/pending-file analysis. Earlier timeout-only versions of these checks and their outputs are preserved under `exploration/callback_v1/`; the final versions add stack evidence and stricter rejection controls.

## R2-03 — withdrawal bypasses the new source-label character rule

**Impact: cosmetic / provenance correctness; forbidden source labels persist.**

Check: `scripts/test_revocation_source_labels.py` — **exit 1**, eight failing subcases.

Expected: newly supplied provenance source/locator labels with control or format characters are rejected without changing the store.

Observed: `revoke()` accepts LF U+000A, NUL U+0000, bidi override U+202E and zero-width space U+200B in **both** `source` and `locator`. It stores those labels and changes the record to `revoked`. The identical bad provenance passed to `put()` is rejected in each case.

This is a missed **withdrawal path through the repaired rule**, not a re-report of Claude's original `put()` acceptance bug. `revoke()` calls `validate_provenance()` but omits the new identifier-character checks used by `put()`. No cryptographic provenance or identity guarantee is claimed here.

Suggested direction: apply the new-label validation consistently to every write path, with an explicit decision about loading historical records that previously allowed those labels. Do not silently rewrite historical provenance.

## R2-04 — a loaded legacy NFD key cannot be corrected

**Impact: crash / unexpected ValueError from a valid history operation.**

Check: `scripts/test_legacy_nfd_correction.py` — **exit 1**.

Precondition: an older schema-1 record has an NFD key. The supplied round-1 report explicitly says old non-NFC keys still load and match. The test constructs that synthetic compatibility fixture, including its correct checksum; it does not edit the supplied code.

Expected: the loaded current record can be corrected through its matching normalized key, retaining the protected predecessor as superseded.

Observed: opening the fixture succeeds and NFC lookup returns **KNOWN old**. `correct(id, 'new', ...)` then raises **`ValueError('missing, cross-key, or forked correction')`**. The snapshot remains unchanged.

`put()` normalizes the successor key and accepts its same-key predecessor using `same_key`; `_validate()` checks the correction link with exact string inequality instead. The two checks disagree on the same legacy key. This is a correction compatibility failure, not a recurrence of the original NFC/NFD hidden-contradiction bug.

Suggested direction: make link validation consistent with the declared key-equivalence rule while preserving the historical record bytes and correction history. Keep a real legacy-format fixture in the regression suite.

## R2-05 — malformed capacity is accepted, then an acknowledged store cannot reopen

**Impact: crash / loss of API access to acknowledged data. The bytes remain on disk; irreversible data loss was not demonstrated.**

Check: `scripts/test_invalid_capacity_snapshot.py` — **exit 1**.

Precondition: a synthetic, internally checksummed snapshot declares `max_bytes=20_000_000`. The constructor permits at most 16,000,000, and the reader always refuses files above 16,000,000. This is a **malformed-format validation test**, not a tamper-resistance claim and not an ordinary API-created snapshot. No guarantee against someone controlling the folder is inferred.

Expected: loading this unsupported configuration raises IntegrityError before any write is allowed.

Observed: the small malformed snapshot opens. A normal `put()` of a 16,000,000-character synthetic value is acknowledged as record **2**, producing **16,003,958 bytes**. Reopening then raises **`IntegrityError: ValueError: snapshot exceeds reader hard limit`**. Subsequent store operations likewise cannot load that file.

The loader checks that capacity counters are positive integers but does not apply the constructor's upper bound. Commit validation follows the larger stored limit; the reader follows its fixed limit. The test makes both the malformed-input precondition and the resulting acknowledged write visible.

Suggested direction: validate stored capacity bounds on load and defensively enforce the reader hard limit on commit. Preserve this exact lifecycle as a regression, without relabeling it as a failure from a normally created store.

## M1 — lower-priority schema-tag acceptance needs a format decision

**Impact: cosmetic / format ambiguity. Observed acceptance is reproduced; the intended strictness needs confirmation.**

Check: `scripts/test_snapshot_schema_type.py` — **exit 1**, two subcases.

A correctly checksummed payload with `schema=true` or `schema=1.0` loads and retains that bool/float tag. The writer emits integer `schema=1`; the check uses Python equality with 1. This test assumes an exact integer version tag. That strict type requirement is not stated as explicitly in the prose as the record-ID rule, so this is **not promoted to a sixth high-confidence contract failure**. Decide whether to reject these tags or document compatible representations. No wrong fact or record loss is shown.

## Areas with no additional failure observed — exact attempts

These are bounded passing checks, not proof of correctness for every input or schedule. Their complete commands/stdout/stderr are in `raw/` and listed in `ALL_CHECK_RESULTS.json`.

| Area / script | What was actually tried and observed |
|---|---|
| Prior fixes — `test_round1_regressions.py` | Behind-clock revocation succeeds with clamped time; a future-dated conflicting current record still forces UNKNOWN; NFC/NFD duplicates force UNKNOWN; `put()` rejects five control/format/surrogate characters in keys and ten provenance cases; 12 invalid-ID operations reject without changing bytes; 3,000-level nesting and a directory at the lock path both raise IntegrityError. The incomplete withdrawal rule is R2-03. |
| Parallel corrections/compaction — `test_parallel_compaction.py` | Three runs, each with four correction processes and one compactor: 48 acknowledged corrections, four protected roots retained, 20 unprotected records actually removed, 52 final records, no duplicate/missing protected-chain IDs. Six additional thread handles produce 90 unique retained records. The first exploratory target of 100 records could not prune these stores and was excluded from the final passing claim; the strengthened check requires 20 real removals. |
| Forced correction/compaction gap — `test_correction_compact_gap.py` | A cross-process barrier forces compaction after `correct()` captures the predecessor but before its `put()` revalidation. Unprotected predecessor removal yields a clean correction refusal; protected compaction refuses and correction succeeds with both history records. |
| Large values — `test_large_values.py` | A protected 10,000,000-byte ASCII value saves/reopens/recalls; file size 10,002,069 bytes. Additional 10 MB and 16 MB values are refused at the byte cap with identical file bytes. Protected compaction refuses unchanged. Filling a custom 256-record cap makes further put/correct refuse unchanged. Observed first 10 MB save ≈0.173 s; 256 sequential writes ≈16.72 s; process peak RSS 111,660 KiB. These are single-environment engineering observations, not performance guarantees or comparative results. |
| Retrieval bounds — `test_retrieval_bounds.py` | Accepts top_k 1/5/100; thresholds 0/.15/1 with strict cutoff behavior; half-lives 1e-9, 1e-8, 1, 2,592,000 and 1e308. Twenty invalid type/range/nonfinite cases reject. Scores remain finite in these cases. |
| Projection — same script | Rank-1/rank-2, dimension-3 bases: cross terms 0, 1e-12 and 9e-10 accepted with unit outputs and repeated-projection drift <2e-9; 1.1e-9 and 1e-6 rejected. An orthogonal vector produces no projection. Full high-rank/384-dimensional numerical conditioning was not exhaustively tested. |
| File robustness — `test_file_format_robustness.py` | 23 malformed byte/schema cases raise IntegrityError: invalid UTF-8, wrong envelope types, trailing garbage, oversized raw input, duplicate fields, five truncations, checksum mismatch, malformed IDs/links/history/embedding/counters. Pretty JSON and removal of only the final newline preserve the identical payload and are correctly accepted. The additional capacity/schema observations are reported separately. |
| Valid-key operation sequences — `test_valid_operation_sequences.py` | Seeds 71000–71011, 60 steps each: **720** put/correct/revoke/compact/recall steps, **2,880** key queries against a separate simple fact-state model, and 143 explicit record removals. No model mismatch or wrong KNOWN for valid string keys in those cases. These exposed synthetic development checks are not scientific memory-comparison tasks. |

## Unverified and excluded

- Python 3.10 and 3.14 were not available on PATH and were **not run**. Termux/Android/phone storage was **not available and not tested**. These remain UNKNOWN, not passes.
- No real power loss, hostile folder writer, rollback resistance, encryption, or semantic-retrieval advantage is claimed. Symlink/hard-link manipulation and permission changes were not tested in this round; they must not be listed as clean areas. The documented folder-writer limit remains in force.
- Concurrency checks cover the recorded schedules and forced gap, not all possible interleavings or long soaks. Callback self-deadlocks are a separate reproduced limitation.
- No normally created store lost acknowledged records in the recorded bounded tests. R2-05 concerns a malformed but checksummed capacity fixture and API unreadability, not erased disk bytes.

## Recommendation to Claude

Reproduce R2-01 through R2-05 against the pinned source before fixing anything. Fix confirmed cases in a **new** source version with one regression per path; retain this archive and every failed output. Decide M1's format policy explicitly. Keep the 60-test baseline, added negative cases, history/protection controls and failure exit codes. Repeat the portable checks on the intended Python versions and phone before making platform claims. No human-review acceptance or scientific execution authorization is supplied by this review.

## Exact commands and full outputs

The generated appendix below is copied verbatim from each failing check's captured stdout/stderr, including its exact interpreter, paths, child commands, tracebacks and return code. Paths, PIDs, timings and thread addresses will differ on another run; the semantic failure should reproduce. The raw files in the bundle remain the archival evidence.

### test_clock_reentry — exit 1

Exact working directory: `/workspace/scratch/9c0778153f23/sml_round2_2026-10-30`

```bash
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_clock_reentry.py --target /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening
```

**stdout (complete):**

```text
{"acknowledged_records_after_kill": [{"embedding": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "id": 1, "key": "synthetic.key", "protected": true, "provenance": {"locator": "fixture:1", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "round2-synthetic"}, "recorded_at": 1000.0, "revocation": null, "status": "current", "supersedes": null, "text": "synthetic.key old", "timestamp": 1000.0, "value": "old", "weight": 1.0}], "child_command": ["/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3", "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_clock_reentry.py", "--target", "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening", "--child", "/tmp/tmpyhyfp42t/store"], "child_stderr": "Timeout (0:00:02)!\nThread 0x00007f4a4ecf9740 (most recent call first):\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py\", line 174 in _lock\n  File \"/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/contextlib.py\", line 137 in __enter__\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py\", line 293 in snapshot\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_clock_reentry.py\", line 19 in clock\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py\", line 378 in revoke\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_clock_reentry.py\", line 24 in child\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_clock_reentry.py\", line 53 in <module>\n", "child_stdout": "{\"event\": \"clock callback entered; requesting snapshot\"}\n", "timeout_seconds": 5}
```

**stderr (complete):**

```text
test_reentrant_clock_completes_or_rejects_explicitly (__main__.ClockReentry.test_reentrant_clock_completes_or_rejects_explicitly) ... FAIL

======================================================================
FAIL: test_reentrant_clock_completes_or_rejects_explicitly (__main__.ClockReentry.test_reentrant_clock_completes_or_rejects_explicitly)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_clock_reentry.py", line 35, in test_reentrant_clock_completes_or_rejects_explicitly
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/subprocess.py", line 550, in run
    stdout, stderr = process.communicate(input, timeout=timeout)
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/subprocess.py", line 1209, in communicate
    stdout, stderr = self._communicate(input, endtime, timeout)
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/subprocess.py", line 2116, in _communicate
    self._check_timeout(endtime, orig_timeout, stdout, stderr)
  File "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/subprocess.py", line 1253, in _check_timeout
    raise TimeoutExpired(
subprocess.TimeoutExpired: Command '['/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3', '/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_clock_reentry.py', '--target', '/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening', '--child', '/tmp/tmpyhyfp42t/store']' timed out after 5 seconds

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_clock_reentry.py", line 42, in test_reentrant_clock_completes_or_rejects_explicitly
    self.assertNotIn('clock callback entered', stdout or '',
AssertionError: 'clock callback entered' unexpectedly found in '{"event": "clock callback entered; requesting snapshot"}\n' : callback entered store.snapshot() and deadlocked inside revoke

----------------------------------------------------------------------
Ran 1 test in 5.008s

FAILED (failures=1)
```


### test_fault_reentry — exit 1

Exact working directory: `/workspace/scratch/9c0778153f23/sml_round2_2026-10-30`

```bash
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py --target /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening
```

**stdout (complete):**

```text
{"child_command": ["/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3", "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py", "--target", "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening", "--child", "/tmp/tmppkso6954/store", "partial_write"], "child_stderr": "Timeout (0:00:02)!\nThread 0x00007f865143f740 (most recent call first):\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py\", line 174 in _lock\n  File \"/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/contextlib.py\", line 137 in __enter__\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py\", line 293 in snapshot\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py\", line 20 in fault\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py\", line 272 in _commit\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py\", line 350 in put\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/_support.py\", line 29 in put\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py\", line 24 in child\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py\", line 55 in <module>\n", "child_stdout": "{\"event\": \"fault callback entered; requesting snapshot\", \"stage\": \"partial_write\"}\n", "recovered_keys": ["synthetic.acknowledged"], "stage": "partial_write", "timeout_seconds": 5}
{"child_command": ["/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3", "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py", "--target", "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening", "--child", "/tmp/tmp509l6ty3/store", "after_replace"], "child_stderr": "Timeout (0:00:02)!\nThread 0x00007f079f76d740 (most recent call first):\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py\", line 174 in _lock\n  File \"/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/contextlib.py\", line 137 in __enter__\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py\", line 293 in snapshot\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py\", line 20 in fault\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py\", line 279 in _commit\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py\", line 350 in put\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/_support.py\", line 29 in put\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py\", line 24 in child\n  File \"/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py\", line 55 in <module>\n", "child_stdout": "{\"event\": \"fault callback entered; requesting snapshot\", \"stage\": \"after_replace\"}\n", "recovered_keys": ["synthetic.acknowledged", "synthetic.new"], "stage": "after_replace", "timeout_seconds": 5}
```

**stderr (complete):**

```text
test_reentrant_fault_completes_or_rejects_explicitly (__main__.FaultReentry.test_reentrant_fault_completes_or_rejects_explicitly) ... 
  test_reentrant_fault_completes_or_rejects_explicitly (__main__.FaultReentry.test_reentrant_fault_completes_or_rejects_explicitly) (stage='partial_write') ... FAIL
  test_reentrant_fault_completes_or_rejects_explicitly (__main__.FaultReentry.test_reentrant_fault_completes_or_rejects_explicitly) (stage='after_replace') ... FAIL

======================================================================
FAIL: test_reentrant_fault_completes_or_rejects_explicitly (__main__.FaultReentry.test_reentrant_fault_completes_or_rejects_explicitly) (stage='partial_write')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py", line 37, in test_reentrant_fault_completes_or_rejects_explicitly
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/subprocess.py", line 550, in run
    stdout, stderr = process.communicate(input, timeout=timeout)
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/subprocess.py", line 1209, in communicate
    stdout, stderr = self._communicate(input, endtime, timeout)
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/subprocess.py", line 2116, in _communicate
    self._check_timeout(endtime, orig_timeout, stdout, stderr)
  File "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/subprocess.py", line 1253, in _check_timeout
    raise TimeoutExpired(
subprocess.TimeoutExpired: Command '['/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3', '/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py', '--target', '/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening', '--child', '/tmp/tmppkso6954/store', 'partial_write']' timed out after 5 seconds

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py", line 44, in test_reentrant_fault_completes_or_rejects_explicitly
    self.assertNotIn('fault callback entered', stdout or '',
AssertionError: 'fault callback entered' unexpectedly found in '{"event": "fault callback entered; requesting snapshot", "stage": "partial_write"}\n' : fault callback deadlocked in snapshot while store lock is held

======================================================================
FAIL: test_reentrant_fault_completes_or_rejects_explicitly (__main__.FaultReentry.test_reentrant_fault_completes_or_rejects_explicitly) (stage='after_replace')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py", line 37, in test_reentrant_fault_completes_or_rejects_explicitly
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/subprocess.py", line 550, in run
    stdout, stderr = process.communicate(input, timeout=timeout)
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/subprocess.py", line 1209, in communicate
    stdout, stderr = self._communicate(input, endtime, timeout)
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/subprocess.py", line 2116, in _communicate
    self._check_timeout(endtime, orig_timeout, stdout, stderr)
  File "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/subprocess.py", line 1253, in _check_timeout
    raise TimeoutExpired(
subprocess.TimeoutExpired: Command '['/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3', '/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py', '--target', '/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening', '--child', '/tmp/tmp509l6ty3/store', 'after_replace']' timed out after 5 seconds

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_fault_reentry.py", line 44, in test_reentrant_fault_completes_or_rejects_explicitly
    self.assertNotIn('fault callback entered', stdout or '',
AssertionError: 'fault callback entered' unexpectedly found in '{"event": "fault callback entered; requesting snapshot", "stage": "after_replace"}\n' : fault callback deadlocked in snapshot while store lock is held

----------------------------------------------------------------------
Ran 1 test in 10.014s

FAILED (failures=2)
```


### test_invalid_capacity_snapshot — exit 1

Exact working directory: `/workspace/scratch/9c0778153f23/sml_round2_2026-10-30`

```bash
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_invalid_capacity_snapshot.py --target /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening
```

**stdout (complete):**

```text
{"configured_max_bytes": 20000000, "invalid_capacity_refused": false}
{"acknowledged_record_id": 2, "committed_file_bytes": 16003958, "reader_hard_limit": 16000000, "reopening": "IntegrityError: ValueError: snapshot exceeds reader hard limit"}
```

**stderr (complete):**

```text
test_reader_rejects_limit_above_its_own_hard_cap (__main__.InvalidCapacity.test_reader_rejects_limit_above_its_own_hard_cap) ... FAIL

======================================================================
FAIL: test_reader_rejects_limit_above_its_own_hard_cap (__main__.InvalidCapacity.test_reader_rejects_limit_above_its_own_hard_cap)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_invalid_capacity_snapshot.py", line 44, in test_reader_rejects_limit_above_its_own_hard_cap
    self.fail('malformed limit was accepted and an acknowledged write made the store unreadable')
AssertionError: malformed limit was accepted and an acknowledged write made the store unreadable

----------------------------------------------------------------------
Ran 1 test in 0.281s

FAILED (failures=1)
```


### test_legacy_nfd_correction — exit 1

Exact working directory: `/workspace/scratch/9c0778153f23/sml_round2_2026-10-30`

```bash
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_legacy_nfd_correction.py --target /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening
```

**stdout (complete):**

```text
{"accepted_legacy_snapshot": true, "correction_exception": "ValueError", "message": "missing, cross-key, or forked correction", "nfc_lookup_before": "KNOWN old", "snapshot_unchanged": true}
```

**stderr (complete):**

```text
test_correct_accepted_nfd_predecessor (__main__.LegacyCorrection.test_correct_accepted_nfd_predecessor) ... FAIL

======================================================================
FAIL: test_correct_accepted_nfd_predecessor (__main__.LegacyCorrection.test_correct_accepted_nfd_predecessor)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_legacy_nfd_correction.py", line 29, in test_correct_accepted_nfd_predecessor
    new_id = m.correct(rid, 'new', provenance=P, embedding=E)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py", line 361, in correct
    return self.put(target["key"], value, provenance=provenance,
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py", line 350, in put
    self._commit(s)
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py", line 264, in _commit
    self._validate(state)
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening/sml/memory.py", line 231, in _validate
    raise ValueError("missing, cross-key, or forked correction")
ValueError: missing, cross-key, or forked correction

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_legacy_nfd_correction.py", line 34, in test_correct_accepted_nfd_predecessor
    self.fail('correction of a loaded, matching legacy key failed: '+repr(exc))
AssertionError: correction of a loaded, matching legacy key failed: ValueError('missing, cross-key, or forked correction')

----------------------------------------------------------------------
Ran 1 test in 0.008s

FAILED (failures=1)
```


### test_missing_key_known — exit 1

Exact working directory: `/workspace/scratch/9c0778153f23/sml_round2_2026-10-30`

```bash
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_missing_key_known.py --target /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening
```

**stdout (complete):**

```text
{"answer": {"evidence_ids": [1, 2], "retrieval": [{"explanation": {"age_seconds": 0.0, "decay_factor": 1, "importance_factor": 1, "method": "similarity", "projection_sha256": null, "provenance": {"locator": "fixture:1", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "round2-synthetic"}, "similarity": 1.0, "threshold": 0.15}, "record": {"embedding": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "id": 1, "key": "synthetic.alpha", "protected": false, "provenance": {"locator": "fixture:1", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "round2-synthetic"}, "recorded_at": 1000.0, "revocation": null, "status": "current", "supersedes": null, "text": "synthetic.alpha alpha-value", "timestamp": 1000.0, "value": "alpha-value", "weight": 1.0}, "score": 1.0}, {"explanation": {"age_seconds": 0.0, "decay_factor": 1, "importance_factor": 1, "method": "similarity", "projection_sha256": null, "provenance": {"locator": "fixture:1", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "round2-synthetic"}, "similarity": 1.0, "threshold": 0.15}, "record": {"embedding": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "id": 2, "key": "synthetic.beta", "protected": false, "provenance": {"locator": "fixture:1", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "round2-synthetic"}, "recorded_at": 1000.0, "revocation": null, "status": "current", "supersedes": null, "text": "synthetic.beta beta-value", "timestamp": 1000.0, "value": "beta-value", "weight": 1.0}, "score": 1.0}], "status": "KNOWN", "value": "alpha-value"}, "case": "None key", "stored_keys": ["synthetic.alpha", "synthetic.beta"]}
```

**stderr (complete):**

```text
test_none_does_not_remove_recall_key_filter (__main__.MissingKey.test_none_does_not_remove_recall_key_filter) ... FAIL

======================================================================
FAIL: test_none_does_not_remove_recall_key_filter (__main__.MissingKey.test_none_does_not_remove_recall_key_filter)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_missing_key_known.py", line 25, in test_none_does_not_remove_recall_key_filter
    self.assertEqual(answer['status'], 'UNKNOWN',
AssertionError: 'KNOWN' != 'UNKNOWN'
- KNOWN
+ UNKNOWN
? ++
 : no evidence exists for None: returning an unrelated value is wrong

----------------------------------------------------------------------
Ran 1 test in 0.012s

FAILED (failures=1)
```


### test_revocation_source_labels — exit 1

Exact working directory: `/workspace/scratch/9c0778153f23/sml_round2_2026-10-30`

```bash
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_revocation_source_labels.py --target /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening
```

**stdout (complete):**

```text
{"codepoint": "U+000A", "field": "source", "rejected": false, "snapshot_changed": true, "status": "revoked", "stored_provenance": {"locator": "fixture:1", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "label\nforged"}}
{"codepoint": "U+0000", "field": "source", "rejected": false, "snapshot_changed": true, "status": "revoked", "stored_provenance": {"locator": "fixture:1", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "label\u0000forged"}}
{"codepoint": "U+202E", "field": "source", "rejected": false, "snapshot_changed": true, "status": "revoked", "stored_provenance": {"locator": "fixture:1", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "label\u202eforged"}}
{"codepoint": "U+200B", "field": "source", "rejected": false, "snapshot_changed": true, "status": "revoked", "stored_provenance": {"locator": "fixture:1", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "label\u200bforged"}}
{"codepoint": "U+000A", "field": "locator", "rejected": false, "snapshot_changed": true, "status": "revoked", "stored_provenance": {"locator": "label\nforged", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "round2-synthetic"}}
{"codepoint": "U+0000", "field": "locator", "rejected": false, "snapshot_changed": true, "status": "revoked", "stored_provenance": {"locator": "label\u0000forged", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "round2-synthetic"}}
{"codepoint": "U+202E", "field": "locator", "rejected": false, "snapshot_changed": true, "status": "revoked", "stored_provenance": {"locator": "label\u202eforged", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "round2-synthetic"}}
{"codepoint": "U+200B", "field": "locator", "rejected": false, "snapshot_changed": true, "status": "revoked", "stored_provenance": {"locator": "label\u200bforged", "sha256": "3ab3933d6c00eaa18ebc64abe7117574a112832424acfb95ffa4d9963f221a74", "source": "round2-synthetic"}}
```

**stderr (complete):**

```text
test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) ... 
  test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='source', codepoint='U+000A') ... FAIL
  test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='source', codepoint='U+0000') ... FAIL
  test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='source', codepoint='U+202E') ... FAIL
  test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='source', codepoint='U+200B') ... FAIL
  test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='locator', codepoint='U+000A') ... FAIL
  test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='locator', codepoint='U+0000') ... FAIL
  test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='locator', codepoint='U+202E') ... FAIL
  test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='locator', codepoint='U+200B') ... FAIL

======================================================================
FAIL: test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='source', codepoint='U+000A')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_revocation_source_labels.py", line 35, in test_controls_rejected_without_revocation
    self.fail('new revocation source label accepted a forbidden character')
AssertionError: new revocation source label accepted a forbidden character

======================================================================
FAIL: test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='source', codepoint='U+0000')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_revocation_source_labels.py", line 35, in test_controls_rejected_without_revocation
    self.fail('new revocation source label accepted a forbidden character')
AssertionError: new revocation source label accepted a forbidden character

======================================================================
FAIL: test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='source', codepoint='U+202E')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_revocation_source_labels.py", line 35, in test_controls_rejected_without_revocation
    self.fail('new revocation source label accepted a forbidden character')
AssertionError: new revocation source label accepted a forbidden character

======================================================================
FAIL: test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='source', codepoint='U+200B')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_revocation_source_labels.py", line 35, in test_controls_rejected_without_revocation
    self.fail('new revocation source label accepted a forbidden character')
AssertionError: new revocation source label accepted a forbidden character

======================================================================
FAIL: test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='locator', codepoint='U+000A')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_revocation_source_labels.py", line 35, in test_controls_rejected_without_revocation
    self.fail('new revocation source label accepted a forbidden character')
AssertionError: new revocation source label accepted a forbidden character

======================================================================
FAIL: test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='locator', codepoint='U+0000')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_revocation_source_labels.py", line 35, in test_controls_rejected_without_revocation
    self.fail('new revocation source label accepted a forbidden character')
AssertionError: new revocation source label accepted a forbidden character

======================================================================
FAIL: test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='locator', codepoint='U+202E')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_revocation_source_labels.py", line 35, in test_controls_rejected_without_revocation
    self.fail('new revocation source label accepted a forbidden character')
AssertionError: new revocation source label accepted a forbidden character

======================================================================
FAIL: test_controls_rejected_without_revocation (__main__.RevocationLabels.test_controls_rejected_without_revocation) (field='locator', codepoint='U+200B')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_revocation_source_labels.py", line 35, in test_controls_rejected_without_revocation
    self.fail('new revocation source label accepted a forbidden character')
AssertionError: new revocation source label accepted a forbidden character

----------------------------------------------------------------------
Ran 1 test in 0.044s

FAILED (failures=8)
```


### test_snapshot_schema_type — exit 1

Exact working directory: `/workspace/scratch/9c0778153f23/sml_round2_2026-10-30`

```bash
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_snapshot_schema_type.py --target /workspace/scratch/9c0778153f23/sml_round2_2026-10-30/target/sml-hardening
```

**stdout (complete):**

```text
{"input_schema": true, "loaded_schema": true, "loaded_type": "bool", "rejected": false}
{"input_schema": 1.0, "loaded_schema": 1.0, "loaded_type": "float", "rejected": false}
```

**stderr (complete):**

```text
test_noninteger_schema_is_refused (__main__.SchemaType.test_noninteger_schema_is_refused) ... 
  test_noninteger_schema_is_refused (__main__.SchemaType.test_noninteger_schema_is_refused) (schema='True') ... FAIL
  test_noninteger_schema_is_refused (__main__.SchemaType.test_noninteger_schema_is_refused) (schema='1.0') ... FAIL

======================================================================
FAIL: test_noninteger_schema_is_refused (__main__.SchemaType.test_noninteger_schema_is_refused) (schema='True')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_snapshot_schema_type.py", line 22, in test_noninteger_schema_is_refused
    self.fail('noninteger schema identifier was accepted as schema 1')
AssertionError: noninteger schema identifier was accepted as schema 1

======================================================================
FAIL: test_noninteger_schema_is_refused (__main__.SchemaType.test_noninteger_schema_is_refused) (schema='1.0')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/scratch/9c0778153f23/sml_round2_2026-10-30/scripts/test_snapshot_schema_type.py", line 22, in test_noninteger_schema_is_refused
    self.fail('noninteger schema identifier was accepted as schema 1')
AssertionError: noninteger schema identifier was accepted as schema 1

----------------------------------------------------------------------
Ran 1 test in 0.004s

FAILED (failures=2)
```

