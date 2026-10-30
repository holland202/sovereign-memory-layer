# Device run: Python vs Rust differential on Samsung Galaxy S25 Ultra, Termux (2026-10-30)

**Status: OWNER-RUN on the device.** Chad Holland ran this himself and pasted the output to Claude. It was not independently reproduced.

- **Python:** 3.14.6 (Termux). **Rust:** cargo 1.98.1, the build from `cargo test --release` (`2026-10-30_S25_termux_rust.md`).
- **Command:** `cd ~/sovereign-memory-layer && python3 tools/differential.py --quick --rust-bin rust/target/release/sml-cli`

**Output (verbatim):**

```
D1: {"sequences": 40, "ops": 1640, "mismatches": 0, "first": []} (11s)
D2: {"values": 20000, "mismatches": 0, "first": []} (1s)
D3: {"cases": 3402, "outcomes_py": {"IntegrityError": 3392, "ok": 10}, "mismatches": 0, "first": []} (2s)
D5: {"records": 240, "expected": 240, "exit_codes": [0, 0, 0, 0, 0, 0, 0, 0], "rust_reopen_ok": true, "mismatches": 0} (19s)
D6: {"trials": 20, "acked_total": 526, "unacked_extra_total": 0, "mismatches": 0, "first": []} (6s)
python 3.14.6 | rust bin rust/target/release/sml-cli
VERDICT IDENTICAL
```

## What this shows

On the phone, Python 3.14.6 and the Rust port behaved identically:
- 1,640 random operations, with byte-identical store files after every one;
- 20,000 numbers formatted the same way;
- 3,402 damaged files handled the same way;
- 4 Python and 4 Rust writers on one store at once, all 240 records kept;
- 20 hard kills of the Rust writer, no acknowledged write lost.

This is the quick mode; the full run (400 sequences) has run only in Claude's container.

## Correction to an earlier statement

`verify_hardened.py` and `rust/RESULTS.md` said "Python 3.14 does not raise `RecursionError` on deep JSON". That came from CPython 3.14.9 on GitHub's runners. On this phone, Python 3.14.6 **does** raise it: the A1 mutant was killed in the device run (`2026-10-30_S25_termux_python.md`). The behaviour depends on the build and platform, not just the version. The verifier was already written to decide this at run time by probing, so its logic is unaffected; only the wording was wrong.
