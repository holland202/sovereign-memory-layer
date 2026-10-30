# Rust parity review — 2026-10-30

AI-generated (ChatGPT, OpenAI GPT-6-astra), at Chad Holland's direction.

## Scope and result

**SELF-TESTED / REPRODUCED:** 31 targeted synthetic sequences produced 14 mismatching sequences, grouped into four findings below. Seventeen sequences matched. No store, CLI, CI, existing suite, or historical evidence was edited. This is a test/evidence contribution, not a fix.

Source baseline: `7d5f4169ab768ba2b165a2fbf394b3d17c284fdf`. Code is identical to `9f83a98334791cd685600ad16d8e39380c2a3996`; the intervening change only adds EXT-01 registration. EXT-01's resource-admission and flock work is excluded. The bounded large-value controls below compare behavior, not resource use; no fix or performance measurement overlaps that registration.

Environment: Linux x86_64, CPython 3.12.14 (Unicode 15.0.0), rustc/cargo 1.99.1. Locked Cargo dependencies were used. See [environment.txt](environment.txt), [build.command.txt](build.command.txt), [build.stderr.txt](build.stderr.txt), and [raw/results.json](raw/results.json) for versions, full build output, source hashes and binary hash. Build exited 0; build stdout was empty. These results are specific to this runtime pair.

## Commands and full outputs

From repository root with Cargo available:

```sh
cargo build --release --locked --manifest-path rust/Cargo.toml
python3 review/chatgpt_task2/run_cases.py
```

The local toolchain environment prefix used for the build is preserved verbatim in `build.command.txt`. Probe runner exit: **1**, deliberately signalling the observed parity failures. It does not convert them into passing expected failures. Full stdout:

```text
unicode_cyrillic_tje: MISMATCH
unicode_garay: MISMATCH
unicode_ascii_control: IDENTICAL
unicode_greek_control: IDENTICAL
whitespace_all_python: IDENTICAL
nfc_control: IDENTICAL
option_weight: MISMATCH
option_timestamp: MISMATCH
option_embedding: MISMATCH
option_thermal_state: MISMATCH
option_supersedes: MISMATCH
retrieve_top_k: MISMATCH
retrieve_threshold: MISMATCH
retrieve_qembedding: MISMATCH
timestamp_integer_rounding: MISMATCH
timestamp_zero: IDENTICAL
timestamp_negative_zero: IDENTICAL
timestamp_subnormal: IDENTICAL
timestamp_future_float: IDENTICAL
timestamp_maximum: IDENTICAL
snapshot_future_integer: MISMATCH
snapshot_duplicate_key: IDENTICAL
snapshot_utf8_bom: IDENTICAL
snapshot_lone_surrogate: IDENTICAL
json_duplicate_command: MISMATCH
json_bom_command: MISMATCH
large_value_accepted: IDENTICAL
large_value_refused: IDENTICAL
compact_chain_ties: IDENTICAL
compact_protected_ties: IDENTICAL
float_decimal_neighborhoods: IDENTICAL
TOTAL 31 sequences: 17 identical, 14 mismatches
```

Stderr: empty. Each `raw/<case>/` contains both exact input JSONL streams, full untruncated stdout/stderr, exact command/cwd, and a unified diff. Fixture cases also retain the exact checksummed input snapshot. Full process exits and operation counts are in `raw/results.json`. Both CLI processes exited 0 in every case; an operation-level rejection appears in its JSON response. Temporary store paths in recorded commands identify this run; use the runner to recreate fresh directories for replay.

To isolate any case, for example:

```sh
python3 review/chatgpt_task2/run_cases.py --case snapshot_future_integer --out /tmp/sml-timestamp-review
```

The runner's parity oracle compares all output lines, stderr and process exits, and requires one reply per operation. Its fresh-directory setup avoids cross-case state. All ordinary create operations succeeded in the recorded runs; the explicit BOM-command rejection is a separate case.

Existing baseline command (exit 0):

```sh
python3 tools/differential.py --quick --only D1,D2,D3 --rust-bin rust/target/release/sml-cli
```

Full stdout:

```text
D1: {"sequences": 40, "ops": 1640, "mismatches": 0, "first": []} (5s)
D2: {"values": 20000, "mismatches": 0, "first": []} (0s)
D3: {"cases": 3402, "outcomes_py": {"IntegrityError": 3392, "ok": 10}, "mismatches": 0, "first": []} (2s)
python 3.12.14 | rust bin rust/target/release/sml-cli
VERDICT IDENTICAL
```

Baseline stderr: empty. Thus the existing quick checks selected here pass despite these targeted mismatches; that is a bounded coverage observation, not a claim that every existing test passes.

## Findings

### SML-R3-01 — Unicode-version-dependent embeddings and answers (Medium)

**REPRODUCED:** `unicode_cyrillic_tje` and `unicode_garay`.

Expected under the port's byte-identical-to-CPython-3.12+ claim: identical embeddings, file hashes and recall results for the same operations. Actual: storing U+1C89 as text and querying U+1C8A yields Python `UNKNOWN` and Rust `KNOWN`; U+10D50/U+10D70 does the same. The file hashes differ before retrieval. Uppercase self-queries succeed on both sides, and ASCII/Greek controls agree.

Impact: observable stored-byte and answer divergence across supported runtime versions. This does not mean the Rust lowercase mapping is linguistically wrong; the compatibility promise is too broad for the demonstrated runtime pair. **VERIFIED FROM SOURCE:** Python uses its built-in `str.lower()` and Rust uses `str::to_lowercase()` in `hash_embedding_raw`, without pinning a shared Unicode mapping. `tools/differential.py` uses fixed text lists lacking these characters. A shared mapping or an explicitly tested version compatibility boundary would address the promise; no fix is included.

Replay:

```sh
python3 review/chatgpt_task2/run_cases.py --case unicode_cyrillic_tje --case unicode_garay --out /tmp/sml-unicode-review
```

Full inputs/outputs/diffs: [Cyrillic case](raw/unicode_cyrillic_tje/commands.txt), [Cyrillic diff](raw/unicode_cyrillic_tje/diff.txt), [Garay diff](raw/unicode_garay/diff.txt).

### SML-R3-02 — Integer timestamps lose the future-evidence boundary (Low practical reach; correctness defect)

**REPRODUCED:** `snapshot_future_integer` and `timestamp_integer_rounding`.

Expected: a timestamp of `9007199254740993` is after a clock of `9007199254740992`, so it must not be retrieved at that clock. Actual: the exact same checksummed synthetic snapshot opens successfully in both implementations, but Python returns `UNKNOWN` while Rust returns `KNOWN` with score `1.0`. The file hash remains identical: this is a read interpretation difference, not a checksum failure. The fixture uses integer timestamp `2**53+1`, integer recorded-at `2**53+2`, and a unit embedding. It is handcrafted and schema-accepted, not output from a normal Python `put`, which converts timestamps to floats.

A normal line-protocol put with clock `2**53` and timestamp `2**53+1` is rejected by Python with `ValueError`; Rust accepts it and writes one record. **VERIFIED FROM SOURCE:** Rust converts `Value::Int` to f64 before comparison (`as_number`, `retrieve_from`, and CLI option extraction); Python's int-versus-float comparisons preserve this integer boundary. These integers fit within signed 64 bits, so the declared outside-i64 limitation does not cover this case.

Impact: future evidence can be returned or an out-of-bound timestamp accepted at extreme, non-realistic wall-clock values. No claim is made that contemporary wall-clock dates trigger it. Consider retaining exact comparisons or explicitly restricting timestamp representations/ranges; no fix is included.

Replay:

```sh
python3 review/chatgpt_task2/run_cases.py --case snapshot_future_integer --case timestamp_integer_rounding --out /tmp/sml-time-review
```

Full evidence: [snapshot commands](raw/snapshot_future_integer/commands.txt), [snapshot bytes](raw/snapshot_future_integer/fixture.memory.json), [snapshot diff](raw/snapshot_future_integer/diff.txt), [put diff](raw/timestamp_integer_rounding/diff.txt).

### SML-R3-03 — Malformed CLI options silently become defaults (Medium; CLI adapter)

**REPRODUCED:** `option_weight`, `option_timestamp`, `option_embedding`, `option_thermal_state`, `option_supersedes`, `retrieve_top_k`, `retrieve_threshold`, `retrieve_qembedding`.

Expected: mirror line-protocol adapters reject the same invalid argument types without silently changing the operation. Actual: Python rejects `weight: true`, string timestamp/embedding, numeric thermal_state and boolean supersedes; Rust drops these values and persists a defaulted record. Python also rejects `top_k: 1.0`, `threshold: true`, and string qembedding, while Rust returns retrieval hits using defaults.

Impact: malformed CLI requests can produce writes or answers rather than rejection; the adapters cannot be assumed equivalent when testing validation. **VERIFIED FROM SOURCE:** Rust `f`, `s`, `floats`, `popts` and `ropts` return `None`/defaults on these types, while Python passes these non-null options through for validation. This is an adapter finding, not a claim that Rust's statically typed library accepts a boolean where f64 is required. The existing operation generator supplies valid types for these options and does not explore these substitutions.

Replay each named case with `--case`; for example:

```sh
python3 review/chatgpt_task2/run_cases.py --case option_weight --case retrieve_top_k --out /tmp/sml-option-review
```

Full evidence: every named case's directory under `raw/`, including [weight diff](raw/option_weight/diff.txt), [supersedes diff](raw/option_supersedes/diff.txt), and [top_k diff](raw/retrieve_top_k/diff.txt).

### SML-R3-04 — Command JSON parsers disagree (Low; protocol consistency)

**REPRODUCED:** `json_duplicate_command` and `json_bom_command`.

Expected for mirrored protocol adapters: a documented, consistent handling of duplicate object fields and a leading UTF-8 BOM. Actual: Python accepts a duplicate `value` field, keeps the second value and writes a record; Rust rejects the command with `BadOp: duplicate JSON key ...`. Conversely, a BOM-prefixed create is rejected by Python with `ValueError`, while Rust creates the store.

Impact: command acceptance and resulting state differ. This is not a finding that either snapshot loader accepts duplicate keys: the duplicate-snapshot control is rejected by both. **VERIFIED FROM SOURCE:** Python CLI calls `json.loads` on a string with ordinary duplicate-key handling; Rust CLI reuses its strict byte-oriented snapshot parser, which strips a BOM. `tools/differential.py` emits commands from dictionaries with `json.dumps`, so neither form can be generated there.

Replay:

```sh
python3 review/chatgpt_task2/run_cases.py --case json_duplicate_command --case json_bom_command --out /tmp/sml-json-review
```

Full evidence: [duplicate diff](raw/json_duplicate_command/diff.txt), [BOM diff](raw/json_bom_command/diff.txt), and the corresponding raw input/output files.

## Areas with no discrepancy in these probes

**SELF-TESTED:**

| Area | Inputs and observed result |
| --- | --- |
| Whitespace | All 29 code points recognized by this Python's `isspace()` between `a` and `b`; matching file hash and retrieval. |
| Established case/NFC | ASCII, Greek final sigma, and decomposed café key; matching bytes/results. |
| Numeric formatting | 3,798 distinct finite bit patterns: signed adjacent representable values around powers of ten from 1e-323 to 1e308, signed zeros, minimum subnormal, maximum finite and the retained formatting tie. Exact repr strings match. |
| Float timestamp bounds | Zero, negative zero, minimum subnormal, maximum finite accepted identically; next float above clock 1.0 rejected identically. |
| Snapshot JSON | Duplicate schema key and a lone surrogate refused by both; a UTF-8 BOM snapshot accepted by both. The surrogate fixture is also checksum-inconsistent, so this is only a rejection check, not isolation of the parser's reason. |
| Bounded large values | 65,536-byte value with explicit unit embedding accepted in 200,000-byte capacity and refused in 4,096-byte capacity; matching hashes/status, zero records after refusal. No performance/resource measurements. |
| Compaction ties | Equal-weight correction chain removed as IDs `[1,3]` before later root; protected equal-weight record retained while ID `[2]` removed; impossible target rejected with unchanged hash. |

**NOT RUN:** full non-quick differential, D5 mixed-writer and D6 kill trials, Rust unit/integration suite, other Python/Rust versions, Android/Termux/macOS, exhaustive Unicode or floating-point coverage, external reproduction by Claude. The findings do not depend on those unrun checks. Declared UTF-16/32 and outside-i64 limitations were not presented as new defects. EXT-01 resource/lock hypotheses were not tested or modified.
