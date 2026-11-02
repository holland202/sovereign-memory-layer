# SML in TypeScript (third implementation)

The same store as `sml/memory.py`, in TypeScript with no dependencies. It runs on Node 22.18 or newer with its built-in type stripping: `node ts/src/cli.ts`. It reads and writes the same file format, and the differential test holds it to byte identity with the Python reference:

```bash
python3 tools/differential.py --port ts --quick   # Python vs TypeScript
python3 ts/tests/exp_check.py                       # exp() vs Python's math.exp
```

## Status (honest)

- **Self-tested.** 6 of 6 as registered on x86_64 Linux ([RESULTS.md](RESULTS.md)). Then **ChatGPT's independent review found a real bug** this did not test for: integer fields in valid files broke compaction. It is fixed and tested in round 2 ([ROUND2_RESULTS.md](ROUND2_RESULTS.md)). Reconciling the rest of ChatGPT's findings is still open.
- **Single-process only.** Node has no `flock`, so never let this port share a store with another writer. That includes Python and Rust.
- **Byte identity with glibc only.** Python uses each platform's math library. This port reproduces glibc's x86_64 FMA `exp`, so on macOS or Android the recency and importance scores may differ in the last bit.
- **Not ported:** `OrthoProjection` and `policies.admit`.

Written by Claude (Anthropic, Opus 5.5) at Chad Holland's direction. Human validation: not performed.
