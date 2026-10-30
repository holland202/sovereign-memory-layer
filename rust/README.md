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
- **Unicode version (found by ChatGPT, R3-01):** Rust's lower-casing follows a newer Unicode version than CPython 3.12/3.13. Text containing characters assigned in recent Unicode releases can get different embeddings, and so different recall answers. Different Python versions also disagree with each other on such characters. Byte-identical behaviour is claimed only for text without them.
- **Not yet built or run on Android/Termux.** It should build with `pkg install rust` then `cargo build --release`. Unverified.
- Linux and macOS only (POSIX file locking).
