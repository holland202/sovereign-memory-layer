# SML-TS-001: a TypeScript port, held to byte identity with the Python reference — registration (2026-11-02)

Written before the port was built. **Nothing below has been built or run**, except one disclosed exploration (C-EXPLORE, below).

## Why

Chad Holland wants work in more languages, but only where the work is checkable. Most AI-agent tooling runs on Node and TypeScript. A third implementation is held to the same differential test as the Rust port (`tools/differential.py`), so the result is either IDENTICAL or it is not.

## Design

- `ts/src/*.ts` hold a port of `sml/memory.py`, with no dependencies. It is run with Node's built-in TypeScript type stripping (`node ts/src/cli.ts`). The CLI speaks the same line protocol as `tools/py_cli.py` and `rust/src/bin/sml-cli.rs`.
- **Python's `int` and `float` are kept apart**, as the Rust port does. A dependency-free JSON parser and encoder keeps the int/float distinction, refuses duplicate keys, and writes floats the way Python's `repr` does (shortest round-trip, ties rounded half to even, decided with exact BigInt arithmetic).
- **Compensated `sum()`:** the Neumaier summation of CPython 3.12 and later.
- **Words and case:** Python's `str.isspace` set, `str.lower` through `toLowerCase`, and NFC through `normalize`. Lengths are counted in code points, not UTF-16 units.
- **`math.exp`:** see the exploration below. The port carries its own `exp` and does not use `Math.exp`.
- `tools/differential.py` gets a `--port ts` option, which runs D1–D4, D2, D3 and D6 against the TS CLI.

## Disclosed exploration, before this registration (C-EXPLORE)

On this container (x86_64, glibc 2.39), Node's `Math.exp` disagreed with Python's `math.exp` (glibc) in the last bit for **6,082 of 300,000** inputs drawn like the store's decay arguments. Using `Math.exp` would therefore break byte identity in recency and importance scores. The port will instead implement the algorithm glibc uses: the table-driven `exp` from ARM's optimized-routines, with its 2^(k/128) table reconstructed and checked. That exploration is the only result seen before this registration.

## Predictions

- **P1 (D1 + D4):** `differential.py --port ts`, full size: 400 random sequences of 60 ops, then cross-opening each store with the other implementation. **0 mismatches.**
- **P2 (D2):** Python `repr` vs the TS float encoder on 200,000 doubles, the edge list included. **0 mismatches.**
- **P3 (D3):** 3,402 corrupted or truncated files. **The same outcome class from both, every case.**
- **P4 (D6):** 100 SIGKILLs of the TS CLI during writes. **No acknowledged write lost, at most 1 unacknowledged write present, and the store reopens.**
- **P5 (exp):** the port's `exp` equals Python's `math.exp` bit for bit on 1,000,000 seeded inputs, on this container's glibc. **0 mismatches.** If P5 fails, P1 is expected to fail in the recency and importance hits, and both stay recorded.
- **P6 (anti-vacuity):** `--port ts --sabotage` replaces the compensated sum with a naive sum, as the Rust sabotage does. **D1 must report mismatches** (exit 0 only when caught).

## Declared limits, before running

- **No file lock.** Node has no `flock`. The TS port is **single-process only**: running it at the same time as Python, Rust or another TS process on the same store is unsafe. D5 (concurrent writers) is not run for TS. A future fix could use a native addon or Deno's `flock`.
- **The exp match is claimed for glibc only.** Python uses each platform's libm: glibc, macOS libm, Android bionic. The port can match only one algorithm. Decay scores on macOS or Android may differ in the last bit. P5 is claimed only where it is run.
- **Same declared divergences as the Rust port:** integers outside ±2^63 are refused at parse; UTF-16 and UTF-32 files are refused; Unicode-version differences in lower-casing are possible.
- **Not ported:** `OrthoProjection` and `policies.admit`, as in Rust.
- **Self-tested.** Claude (Anthropic, Opus 5.5) writes the port and runs the tests. A pass is self-tested, not independent.

## Unrun next step

Run on the S25 under Termux. Node from `pkg install nodejs` uses bionic's libm through Python, so P5 and P1's decay scores there are an open question.

Provenance: Claude (Anthropic, Opus 5.5), at Chad Holland's direction (2026-11-02, direction only) → human validation: not performed → human responsibility: Chad Holland.
