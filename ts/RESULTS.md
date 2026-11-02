# SML-TS-001 results (2026-11-02)

## What could have gone wrong, first

- **Self-tested.** Claude (Anthropic, Opus 5.5) wrote the port, its tests and the harness changes, and judged the results. Agreement among AI-written implementations is not independent validation. An independent review by ChatGPT (OpenAI) is planned, against the frozen commit named below.
- **One platform.** x86_64 Linux container, glibc 2.39, CPython 3.13.18, Node 22.23.4. The `exp` match is claimed for this glibc FMA build only. **macOS, Android/Termux and CPUs without FMA are NOT VALIDATED.** Recency and importance scores there may differ in the last bit.
- **No file lock.** The port is single-process only (declared before running). D5 (concurrent writers) was not run.
- **Debugging before the registered run** used `--dev-seed` runs only:
  - one quick development run (dev seed 1), which was already IDENTICAL, so no fix followed;
  - an exploration of `repr` and `exp` on 40,016 values with seed 99, disclosed below.
  The registered seeds were used once, for the runs below.
- **The exploration before registration:** Node's `Math.exp` differed from glibc in 6,082 of 300,000 inputs. That is why the port carries its own `exp`.
- **One design detail was decided after registration but before any registered run:** the `exp` port reproduces glibc's x86_64 **FMA** variant, `__ieee754_exp_fma`. Its operation order was read from the disassembly of the function CPython actually calls on this machine. The fused multiply-adds are computed exactly with BigInt. The 256-entry table was copied byte for byte from this machine's `libm.so.6`.

## Raw output

`results/p5_exp.txt`:
```
platform x86_64 ('glibc', '2.39') python 3.13.18 seed 20261102
exp inputs 1000000 | outputs 1000000 | mismatches 0
```

`results/differential_full.txt` (registered seeds, full size):
```
D1: {"sequences": 400, "ops": 24400, "mismatches": 0, "first": []} (101s)
D2: {"values": 200000, "mismatches": 0, "first": []} (2s)
D3: {"cases": 3402, "outcomes_py": {"IntegrityError": 3392, "ok": 10}, "mismatches": 0, "first": []} (5s)
D6: {"trials": 100, "acked_total": 780, "unacked_extra_total": 0, "mismatches": 0, "first": []} (43s)
python 3.13.18 | ts port node /home/claude/sovereign-memory-layer/ts/src/cli.ts
VERDICT IDENTICAL
exit=0
```

`results/differential_sabotage.txt` (naive sum in place of Neumaier): D1 found 50 mismatching sequences, the first after a `put`, with differing file hashes. Ending:
```
SABOTAGE CAUGHT
exit=0
```

## Predictions

| ID | Prediction | Result |
|---|---|---|
| P1 | D1 + D4: 0 mismatches over 24,400 ops, with cross-opening | HELD |
| P2 | D2: 0 mismatches over 200,000 float reprs | HELD |
| P3 | D3: same outcome class on 3,402 corrupted files | HELD |
| P4 | D6: 100 kills, no acknowledged write lost, at most 1 extra | HELD (0 extras) |
| P5 | `exp` bit-identical to `math.exp` on 1,000,000 inputs | HELD |
| P6 | sabotaged port caught by D1 | HELD (50 sequences) |

**6 of 6 as registered.** These were predictions of agreement, so "6 of 6" here means the three implementations agreed on everything tested on this machine. It does not mean the port is correct in general.

## What this shows and does not show

- **Shows (implementation, this machine):** on 24,400 random operations, the TypeScript port writes files byte-identical to Python's. Each opens the other's files, they give the same answers and error classes, they refuse the same corrupted files, and the port loses no acknowledged write under SIGKILL. Byte identity includes float formatting and compensated summation. It also includes glibc's `exp` down to the last bit, which `Math.exp` does not give.
- **Does not show:**
  - concurrent use. There is no lock, so the port must not share a store with another writer;
  - other platforms' libm;
  - Unicode characters newer than the engines agree on;
  - anything about real-world use.

## Open

- ChatGPT's independent review against this commit.
- Run on the S25: `pkg install nodejs`, then `python3 ts/tests/exp_check.py`. Bionic's libm may differ from glibc, which would make it a useful negative.
- A cross-process lock for Node: a native `flock` addon, or Deno.

Provenance: Claude (Anthropic, Opus 5.5), at Chad Holland's direction (2026-11-02, direction only) → human validation: not performed → human responsibility: Chad Holland. SELF-TESTED.

## Correction (appended 2026-11-02): see ROUND2_RESULTS.md

These tests used only files that an implementation wrote. ChatGPT's independent review reported, and D7 confirmed, that on **valid files holding integers where floats are usual**, the port compacted the wrong records. Fixed in SML-TS-002 ([ROUND2_RESULTS.md](ROUND2_RESULTS.md)). The "6 of 6" above stands for what it tested, and that scope was too narrow.
