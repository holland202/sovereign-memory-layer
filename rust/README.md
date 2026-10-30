# SML in Rust (port of the Python reference)

The same store as `sml/memory.py`, in Rust. The two read and write **the same file format**: a store written by one opens in the other, and given the same operations they write byte-identical files.

```bash
cargo test --release                      # unit + integration tests
python3 ../tools/differential.py --quick  # Python vs Rust on the same random operations
```

As a library: `sml::store::MemoryStore` (`create`, `open`, `put`, `correct`, `revoke`, `compact`, `retrieve`, `recall`, `snapshot`, `storage_status`, `cleanup_incomplete`). `src/bin/sml-cli.rs` is the line-protocol tool the differential tests drive.

## Status (honest)

- **Self-tested.** Claude (Anthropic) wrote the port and its tests at Chad Holland's direction. Results are in [RESULTS.md](RESULTS.md).
- **Bit-identical to CPython 3.12 and newer.** Python 3.12 changed `sum()` to compensated summation, and this port copies that. Stores written by Python 3.10/3.11 still open, but retrieval scores can differ in the last bits.
- **Not ported:** `OrthoProjection` and `policies.admit`.
- **Declared divergences:** integers outside ±2^63 in a file, and UTF-16/32 encoded files, are refused here but accepted by Python.
- **Not yet built or run on Android/Termux.** It should build with `pkg install rust` then `cargo build --release`. Unverified.
- Linux and macOS only (POSIX file locking).
