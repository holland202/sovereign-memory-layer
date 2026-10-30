# Round-2 confirmation — 2026-10-30

AI-generated (ChatGPT, OpenAI GPT-6-astra), at Chad Holland's direction.

## Evidence boundary

**SELF-TESTED / REPRODUCED:** All 14 original retained round-2 scripts exit 0 against source commit `9f83a98334791cd685600ad16d8e39380c2a3996` (19 unittest cases). No new failure found in this replay. This confirms these specific regression checks on this environment; it does not establish absence of defects or validate the Rust port.

Python 3.12.14; Linux x86_64. Full runtime metadata, source/archive/script SHA-256 values, and exact subprocess arguments are in [raw/results.json](raw/results.json). The original archive's manifest check exits 0; its full output is [raw/manifest.stdout.txt](raw/manifest.stdout.txt). The replay extracts the archive without editing any original script and passes this checkout explicitly via `--target`.

## Command and full output

From repository root:

```sh
python3 review/chatgpt_task1/replay.py
```

Exit: 0. Stdout:

```text
ARCHIVE_MANIFEST exit=0
test_clock_reentry.py: PASS exit=0
test_correction_compact_gap.py: PASS exit=0
test_fault_reentry.py: PASS exit=0
test_file_format_robustness.py: PASS exit=0
test_invalid_capacity_snapshot.py: PASS exit=0
test_large_values.py: PASS exit=0
test_legacy_nfd_correction.py: PASS exit=0
test_missing_key_known.py: PASS exit=0
test_parallel_compaction.py: PASS exit=0
test_retrieval_bounds.py: PASS exit=0
test_revocation_source_labels.py: PASS exit=0
test_round1_regressions.py: PASS exit=0
test_snapshot_schema_type.py: PASS exit=0
test_valid_operation_sequences.py: PASS exit=0
TOTAL 14/14 scripts exit 0
```

Stderr: empty. Each script's complete stdout, stderr, and exact command/cwd are retained under `raw/`; temporary extraction paths in those logs describe this run and are recreated by the replay script on subsequent runs.

| Script | Test cases | Result |
| --- | ---: | --- |
| test_clock_reentry.py | 1 | PASS (exit 0) |
| test_correction_compact_gap.py | 1 | PASS (exit 0) |
| test_fault_reentry.py | 1 | PASS (exit 0) |
| test_file_format_robustness.py | 1 | PASS (exit 0) |
| test_invalid_capacity_snapshot.py | 1 | PASS (exit 0) |
| test_large_values.py | 2 | PASS (exit 0) |
| test_legacy_nfd_correction.py | 1 | PASS (exit 0) |
| test_missing_key_known.py | 1 | PASS (exit 0) |
| test_parallel_compaction.py | 2 | PASS (exit 0) |
| test_retrieval_bounds.py | 2 | PASS (exit 0) |
| test_revocation_source_labels.py | 1 | PASS (exit 0) |
| test_round1_regressions.py | 3 | PASS (exit 0) |
| test_snapshot_schema_type.py | 1 | PASS (exit 0) |
| test_valid_operation_sequences.py | 1 | PASS (exit 0) |

## Expected, actual, impact

Expected: all 14 archived scripts pass on the fixed Python source. Actual: all pass. Severity: no new finding; no observed wrong answer, loss, crash, or hang in this bounded replay. Callback reentry checks finish, invalid snapshot checks reject input, and retained sequence/compaction/large-value checks pass.

**NOT RUN in task 1:** separate `verify_hardened.py` 69-test suite and fix-removal mutants; device runs; other Python versions/operating systems. Existing reports of those runs are not represented as this review's executions. Task 2 has separate scope and evidence.

Only review artifacts are added. No store, CLI, test suite, CI, or historical evidence is modified.

## Main-branch recheck

`git ls-remote origin refs/heads/main` returned:

```text
7d5f4169ab768ba2b165a2fbf394b3d17c284fdf\trefs/heads/main
```

`git diff --stat 9f83a98334791cd685600ad16d8e39380c2a3996 origin/main` showed only `review/ext01_2026-10-30/PREREG.md` (25 insertions). The tested Python source, archive, and all code are unchanged. This branch includes that documentation-only update. The separate EXT-01 resource/lock observations are outside this replay; no work on its implementation or measurements is included.
