# Frozen TypeScript port: independent review

**Verdict: FAILED — Python/TypeScript equivalence does not hold for all supported cases.** The existing full differential and million-input exp check pass on the claimed platform, while the independent attacks reproduce eight distinct compatibility findings in 34 cases. Three findings concern operations on valid persisted snapshots; the others concern validation and protocol behavior. No fixes were applied.

## Identity and provenance

- Target: [PR #9](https://github.com/holland202/sovereign-memory-layer/pull/9), frozen commit `e1ad1ae03aab8feb924b53365b4e943750026487`.
- The final [PR snapshot](raw/pr9_snapshot.json) still names that exact head. No post-freeze branch change, including any change under `ts/src`, was observed.
- Original preregistration: `8eae03bc0aee9bc47d0ec0feb2933b3614cde279`; port/harness as run: `3f98bf5f64236112ad1f5b9b0e1cb4be0fd0b910`.
- Independent preregistration: `f4d6810bcd9b75de180b9b82ae7e12ee824413bf`, committed before the first test. It was committed locally; GitHub writes were refused. The Git bundle preserves that commit and its ordering.
- Work branch: `chatgpt/ts-review-20261102`. All additions are in this directory. Production source, main, and Claude's branch were not edited. Temporary mutants were isolated copies/wrappers.
- Environment: CPython 3.12.14, Node 24.22.1, Linux x86_64, glibc 2.39, FMA present. Python Unicode 15.0.0; Node Unicode 17.0. Selected Unicode cases use established mappings shared by both. Exact environment and source identities: [environment output](raw/environment.stdout), [frozen-source check](raw/frozen_target_check.stdout).
- This is source-informed review by a different AI provider, not a blind review or human validation. The supplied attack ideas were starting points; the independent cases and runner were written here. Rerunning Claude's harness is reported separately from the independent cases.

ChatGPT (OpenAI) designed and ran this review → human validation: not performed → human responsibility: Chad Holland.

## Executed checks

All commands below run from the repository root. Each `raw/<label>.command.json` records the exact arguments, working directory, exit code and duration; adjacent `.stdout` and `.stderr` files preserve both raw streams.

| Check | Reproduction command | Observed result | Label / raw evidence |
| --- | --- | --- | --- |
| Positive control | `python3 review/ts_chatgpt_20261102/review.py --case C0_control --out /tmp/sml-ts-c0-fresh` | Create/put/retrieve/recall/correct/revoke, protected-chain refusal and reopen agree with independently asserted expected outputs; exit 0 | VERIFIED; [control](raw/control/summary.json) |
| Independent broken-port control | `python3 review/ts_chatgpt_20261102/review.py --mutant --case C0_control --out /tmp/sml-ts-mutant-fresh` | Wrapper changes a successful put ID. Comparator and explicit success assertion catch it; `SABOTAGE CAUGHT`, exit 0 | VERIFIED; [mutant](raw/independent_sabotage/summary.json) |
| Quick differential | `python3 tools/differential.py --port ts --quick --dev-seed 11022026` | D1: 1,640 ops; D2: 20,000 reprs; D3: 3,402 files; D6: 20 kills; 0 mismatch groups, exit 0 | VERIFIED; [stdout](raw/differential_quick.stdout) |
| Full differential | `python3 tools/differential.py --port ts --dev-seed 11022026` | D1/D4: 400 sequences, 24,400 ops; D2: 200,000 reprs; D3: 3,402 files; D6: 100 kills, 287 acknowledged writes, 0 missing/extra writes; 0 mismatch groups, exit 0 | VERIFIED; [stdout](raw/differential_full.stdout) |
| Existing naive-sum sabotage | `python3 tools/differential.py --port ts --sabotage --dev-seed 11022026` | 49 mismatching sequences; `SABOTAGE CAUGHT`, exit 0 | VERIFIED; [stdout](raw/differential_sabotage.stdout) |
| exp million | `python3 ts/tests/exp_check.py --seed 1102202601` | 1,000,000 inputs, 1,000,000 outputs, 0 bit mismatches; exit 0 | VERIFIED; [stdout](raw/exp_million.stdout) |
| Independent attacks | `python3 review/ts_chatgpt_20261102/review.py --out /tmp/sml-ts-attacks-fresh` | 337 cases / 796 operation steps; 34 cases with undeclared differences, plus 20 cases demonstrating declared divergences; exit 1 as expected for defects | FAILED; [summary](raw/attacks/summary.json), [all events](raw/attacks/events.jsonl) |
| Helper checks / cross-opening | Included in independent attacks | 3 canonical key-order cases, 5 hash-embedding cases, 13 exp boundaries: all agree. 598 cross-opening comparisons: no differences or changes to opened bytes | VERIFIED for those checks; [events](raw/attacks/events.jsonl) |

The fresh development seeds differ from the author's registered seeds. These are independent review repetitions, not additional confirmatory runs under Claude's registration. The quick and full harness runs share the stated development seed. The two long harness processes ran concurrently on disjoint temporary stores; crash acknowledgment counts and elapsed times depend on scheduling. No two writers shared a store.

The runner writes one raw request and response stream per implementation, stderr and child exit codes, plus an event per operation with pre/post snapshot hashes. On differences it saves the resulting snapshots. It also saves every synthetic input fixture. The failing stored-snapshot fixtures were accepted initially by **both** implementations; they are not corrupt envelopes. Each representative below was repeated in isolation and again exited 1 with the same difference. Original and isolated outputs are both retained.

## Findings

### F1 — integer weights change which record compaction deletes

**FAILED, storage behavior, 2 cases.** A valid snapshot has two unprotected records: ID 1 with JSON integer weight `1`, ID 2 with weight `0` (integer or float). Both readers accept it. Compacting to one record should remove ID 2. Python returns `[2]`; TypeScript returns `[1]` and commits that deletion. The resulting TS snapshot remains loadable, so checking only successful reopen would miss the wrong choice.

Repro: `python3 review/ts_chatgpt_20261102/review.py --case A8_weight_types_int_int --out /tmp/sml-ts-f1-fresh`

Raw evidence: [isolated events](raw/repro_F1/events.jsonl), [input fixture](raw/repro_F1/fixtures/A8_weight_types_int_int.bin), [command and exit](raw/repro_F1.command.json). Source reading identifies `ts/src/store.ts:409`: a type assertion treats `PyInt` as a JavaScript number without converting it. Relational comparison then misses the integer weight. The float/float control agrees; integer/float storage variants expose the defect. This concerns schema-valid file representations; normal new writes convert weights to floats.

### F2 — large, supported integer IDs collide during correction lookup

**FAILED, valid-operation refusal, 8 cases.** Checksummed snapshots contain adjacent IDs `9007199254740992` and `9007199254740993`, with `next_id = 9007199254740994`. Both readers accept them. Correcting the second record succeeds in Python with ID `9007199254740994`; TypeScript returns `ValueError` and leaves its original snapshot unchanged. Direct put-with-supersedes has the same issue. Cases near the upper signed-i64 boundary reproduce it too.

Repro: `python3 review/ts_chatgpt_20261102/review.py --case A8_highid_9007199254740992_True_correct --out /tmp/sml-ts-f2-fresh`

Raw evidence: [events](raw/repro_F2/events.jsonl), [fixture](raw/repro_F2/fixtures/A8_highid_9007199254740992_True_correct.bin), [command](raw/repro_F2.command.json). Source: `store.ts:333` and `:493–497`. `pyEq` converts integer IDs to binary64 before equality, conflating distinct `PyInt` values. **All tested IDs and counters are inside signed i64.** This is not the declared out-of-range integer divergence. The synthetic fixtures reach these states without billions of writes. No successful wrong-target correction or silent corruption was observed in these cases.

### F3 — revocation refuses a valid integer-timestamp record after clock rollback

**FAILED, valid-operation refusal, 1 case.** A valid stored timestamp is JSON integer `1000`; the revocation clock is `900`. The documented behavior clamps the revocation time to the record's timestamp. Python succeeds and persists `at = 1000`; TypeScript returns `ValueError` without committing. The otherwise identical float-timestamp control succeeds.

Repro: `python3 review/ts_chatgpt_20261102/review.py --case A8_revoke_timestamp_int --out /tmp/sml-ts-f3-fresh`

Raw evidence: [events](raw/repro_F3/events.jsonl), [fixture](raw/repro_F3/fixtures/A8_revoke_timestamp_int.bin), [command](raw/repro_F3.command.json). Source: `store.ts:388–389` compares a parsed `PyInt` object with `now` without `toF`, so the intended clamp fails; subsequent validation prevents committing the invalid time. This is a refusal defect, not an observed malformed committed snapshot.

### F4 — explicit null capacities silently become defaults

**FAILED, input validation / side effect, 2 cases.** `create` with `max_records: null` or `max_bytes: null` is refused with `ValueError` by Python. TypeScript reports success and creates a store, substituting its constructor default. Explicit null differs from an omitted field: the CLI supplies zero for omission and both ports refuse it.

Repro: `python3 review/ts_chatgpt_20261102/review.py --case A4_max_records_null --out /tmp/sml-ts-f4-fresh`

Raw evidence: [events](raw/repro_F4/events.jsonl), [resulting TS store](raw/repro_F4/snapshots/A4_max_records_null/0_ts.json), [command](raw/repro_F4.command.json). Source: `store.ts:137–138` uses `??`, which substitutes for null as well as undefined. The created snapshot uses `max_records = 128` in the representative case.

### F5 — false-like recall queries do not follow Python's fallback

**FAILED, protocol/API behavior, 4 cases.** A recall query of `false`, `0`, `[]` or `{}` falls back to the key in Python (`query or key`). TypeScript only falls back for null/undefined/empty string, then rejects these values with `ValueError`. In the saved representative Python returns a successful `UNKNOWN/insufficient_evidence`; TS raises instead. This fixture intentionally uses an explicit unit embedding for storage, so no claim is made that the fallback must return KNOWN.

Repro: `python3 review/ts_chatgpt_20261102/review.py --case A6_recall_query_02 --out /tmp/sml-ts-f5-fresh`

Raw evidence: [events](raw/repro_F5/events.jsonl), [command](raw/repro_F5.command.json). Source: `store.ts:472` and Python `memory.py`'s `query or key`. No mutation occurs on either side.

### F6 — recall with rkey exposes a Python wrapper error

**FAILED for exact protocol parity; reference-side issue, 6 cases.** The Python CLI forwards `rkey` as keyword `key`, while `recall` also supplies `key=key`, producing a duplicate-keyword `TypeError`. TS supplies one effective key and returns a normal recall result. It would be inappropriate to fix TS merely by reproducing this accidental Python exception; define the protocol and repair the reference wrapper separately.

Repro: `python3 review/ts_chatgpt_20261102/review.py --case A6_recall_rkey_null --out /tmp/sml-ts-f6-fresh`

Raw evidence: [events](raw/repro_F6/events.jsonl), [command](raw/repro_F6.command.json). Source: `tools/py_cli.py`'s `ropts`, `memory.py`'s `recall`, and `ts/src/cli.ts`'s `ropts`. This is not evidence of a TS storage-integrity failure.

### F7 — repr validates an irrelevant directory in TS

**FAILED for exact protocol parity; validation-order issue, 5 cases.** `{"op":"repr","dir":null,"bits":["3ff0000000000000"]}` returns `["1.0"]` from Python, which never uses the directory for repr. TS returns `TypeError` before dispatch because `asDir` runs first. False, zero, list and object directory values behave similarly.

Repro: `python3 review/ts_chatgpt_20261102/review.py --case A7_repr_dir_null --out /tmp/sml-ts-f7-fresh`

Raw evidence: [events](raw/repro_F7/events.jsonl), [command](raw/repro_F7.command.json). Source: `ts/src/cli.ts:49` precedes the repr branch at `:57`. This has no store side effect.

### F8 — lone-surrogate rejection occurs at a different protocol layer

**FAILED for exact refusal-class parity; parser-only, 6 cases.** An escaped lone high or low surrogate in key, value or text receives `ValueError` from Python and `BadOp` from TS. Both refuse and preserve the snapshot. This is a classification difference on invalid Unicode input, not acceptance of malformed evidence or a Unicode-version mapping difference.

Repro: `python3 review/ts_chatgpt_20261102/review.py --case A1_invalid_3_key --out /tmp/sml-ts-f8-fresh`

Raw evidence: [events](raw/repro_F8/events.jsonl), [command](raw/repro_F8.command.json). Source: `ts/src/json.ts`'s escaped-surrogate parser and `ts/src/cli.ts`'s parse-error-to-BadOp handling. Whether the public protocol should intentionally classify these at parse time needs an explicit contract decision; no fix was made.

## Declared differences and unexecuted coverage

- **VERIFIED declared divergences:** 18 numeric cases outside signed i64 and two UTF-16/UTF-32 files produce differences. They are separately tagged in the raw summary and are not included in the eight findings. The 4,301-digit token cases agree on rejection; not every declared-limit input differs.
- **NOT TESTED / NOT RUN:** direct Rust–TS execution. `cargo` and `rustc` are absent ([setup attempt](raw/rust_setup.stdout), exit 127). No Rust build was run. The independent runner accepts `--rust-bin` and drives all three CLIs directly; future command: `cargo build --release --manifest-path rust/Cargo.toml`, then `python3 review/ts_chatgpt_20261102/review.py --rust-bin rust/target/release/sml-cli --out /tmp/sml-three-way-fresh`. This future command is NOT RUN and must not be cited as a result.
- **NOT TESTED / NOT RUN:** macOS, Android/bionic, non-FMA CPUs, new Unicode-version mapping differences, concurrent writers/D5, OrthoProjection, policies.admit, hardware power loss, UVR-001. Single-process and platform limits remain as originally declared.
- The independent suite does not exhaust every combination in the attack ideas. Its exact implemented cases, inputs and outcomes are saved; unimplemented combinations have no claimed result.

## Review decision

Hold a general supported-input parity claim until F1–F5 are fixed and independently checked. Resolve F6–F8 as explicit protocol decisions, preserving the current failures as regression evidence. Do not erase the passing baseline or the declared limitations. Fixes belong on a separate branch; this review only supplies evidence. GitHub publication is blocked by integration 403 and missing CLI credentials, so no draft review PR has been created. The accompanying handoff provides a bundle and concrete publication commands.
