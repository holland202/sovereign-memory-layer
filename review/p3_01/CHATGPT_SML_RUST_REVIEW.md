# SML Rust interoperability: source-pinned review and reproducibility candidate

**Date:** 2026-10-30. **Author:** ChatGPT (OpenAI), AI-generated at the owner's direction. **Status:** VERIFIED FROM SOURCE + SELF-TESTED on the supplied older Python code; **NOT RUN** against the current Rust executable. Not independent human review.

## Target identity and issue candidate

Public repository: https://github.com/holland202/sovereign-memory-layer

`main` commit obtained through GitHub reference lookup: `9f83a98334791cd685600ad16d8e39380c2a3996` (at lookup time). During this review `main` advanced to `7d5f4169ab768ba2b165a2fbf394b3d17c284fdf`; GitHub compare showed one added `review/ext01_2026-10-30/PREREG.md`, no changes to the inspected implementation files. Relevant blobs inspected:

- `sml/memory.py`: Git blob `54ba8a7c3a20034ebf13991c9252e691755e72c5`.
- `rust/src/json.rs`: Git blob `276f35cdff723c1a01f2f111e37a66d827f81cd6`.
- `rust/src/store.rs`: Git blob `b725b9f08f209f506f35c011fcdc8f02283bb49a`.
- `tools/py_cli.py`: Git blob `6d2cf6336d70f11fa3746ccf844101f12cbec5da`.
- `rust/src/bin/sml-cli.rs`: Git blob `61e81e7e973016081a1ef0cd929c0cfeff674729`.

**Candidate P3-01 (interoperability / data inaccessible from Rust).** The Python constructor accepts any exact positive `max_records` integer; it does not impose a 64-bit upper bound. Python's JSON encoder/decoder can encode an integer larger than `i64::MAX`. The Rust on-disk JSON parser uses `Value::Int(i64)` and explicitly refuses any integer outside `i64`. Therefore an otherwise valid Python-created SML store with `max_records=9223372036854775808` should reopen with Python but be refused by Rust. This has not yet been executed using the actual current Rust binary, so it is a **source-supported candidate, not a reproduced cross-language finding**. No irreversible data loss is alleged; the Python store remains readable.

The tested boundary is intentionally extreme; it is a format-compatibility contract gap, not a typical operational setting. A fix could either impose a matching Python creation bound (with explicit migration handling for existing files) or define/implement a wider common integer representation in Rust, but no fix is included here.

## Independent probe, exact commands

From a fresh checkout of the target commit (not a different branch):

```sh
cargo build --release --manifest-path rust/Cargo.toml
python3 test_large_counter_interop.py --root .
```

The script uses only synthetic, freshly-created stores. It sends a `create` operation with `max_records=9223372036854775807` (control) and then `9223372036854775808` (candidate) through Python's documented `tools/py_cli.py` line protocol. It then sends the exact same `status` operation to Python and Rust CLI programs; it prints complete input/output, snapshots hashes and comparison verdict. Expected shared-format behavior is matching `status` responses. The predicted actual result is Python `ok:true` but Rust `ok:false,error:IntegrityError` for the larger integer. The probe exits 1 when mismatches are observed.

## Direct Python control, already run on supplied older archive

Input: `SML_HARDENED_ROUND1.zip` (not the current repository revision), extracted to a fresh local working tree. Python 3.13.5, Linux. The Python API successfully created and reopened the store with `max_records=2**63` and `max_bytes=2_000_000`:

```
CREATE {'generation': 0, 'records': 0, 'bytes': 195, 'max_records': 9223372036854775808, 'max_bytes': 2000000, 'incomplete_storage_detected': False}
REOPEN {'generation': 0, 'records': 0, 'bytes': 195, 'max_records': 9223372036854775808, 'max_bytes': 2000000, 'incomplete_storage_detected': False}
SHA256 7afb95cc6bb42d18a6b87a8ab0ff0561b42e26afa1ee6073f51d6b6c922c3eea
FILE {"payload":{"generation":0,"max_bytes":2000000,"max_records":9223372036854775808,"next_id":1,"records":[],"schema":1},"sha256":"a7758eb8fc45505dde0bc538b05cc9f5c441aaeb7c014de0f547f8b329523094"}
```

The current Python constructor in GitHub still has the same unbounded-positive `max_records` validation, but it has not been executed in this environment. The current Rust port was read in source form only; `rustc`/`cargo` are not installed in this sandbox.

## Round-two status and work limitations

Claude's `review/round2_chatgpt/RESULTS_ROUND2.md` claims all 14 scripts passed after six fixes, and a 69-test/12-mutant baseline; I read those reports and confirmed the current repository contains them. **Not independently re-run:** the 14 scripts, the 69-test suite, Rust tests, the differential harness or Termux runs on current main. Never promote Claude's run as ChatGPT's. Existing defects R2-01 through R2-05 and M1 are **not re-reported as new**.

**GitHub write blocker:** `mcp__GitHub__create_branch` requested `chatgpt/rust-i64-capacity-interop-20261030` at pinned main `9f83a98334791cd685600ad16d8e39380c2a3996` and returned HTTP 403: `Resource not accessible by integration`. No branch, file, draft PR, merge or repository-setting change was made. The attached script and report are prepared for a future `chatgpt/` findings-only PR after permission is restored.

## Decision

Keep **P3-01: NOT RUN / candidate supported by source** pending execution of the exact differential probe on a fresh current main checkout with a compiled Rust CLI. If the probe passes, record a refutation and close this candidate. If it mismatches, retain the raw output, exact HEAD and hashes and submit a separate tests-only draft PR. No store implementation changes belong in that PR.
