# Device run: Rust port on Samsung Galaxy S25 Ultra, Termux (2026-10-30)

**Status: OWNER-RUN on the device.** Chad Holland ran this himself and pasted the output to Claude. It was not independently reproduced.

- **Toolchain:** cargo 1.98.1 (797e8a9bc 2026-08-05), built from a source tarball (Termux package). Target: aarch64 Android.
- **Commit:** `main` as cloned earlier the same day.
- **Command:** `cd ~/sovereign-memory-layer/rust && cargo --version && cargo test --release`

**Result (verbatim summary lines):**

```
    Finished `release` profile [optimized] target(s) in 6.88s
     Running unittests src/lib.rs
test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
     Running tests/store.rs
test deep_nesting_is_integrity_error ... ok
test lock_path_directory_is_integrity_error ... ok
test reentrant_clock_is_refused_not_deadlocked ... ok
test clock_behind_record_still_allows_revoke_with_clamped_time ... ok
test nfc_nfd_keys_are_one_key_and_controls_refused ... ok
test capacity_refusals_leave_bytes_unchanged ... ok
test fault_before_replace_leaves_state_after_replace_poisons ... ok
test result: ok. 7 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.05s
```

## What this shows

The Rust port builds and its 12 tests pass on Android/aarch64. Those tests cover the phone's `flock`, `fsync`, rename, and directory fsync, plus re-entrancy, injected faults at all four commit stages, clock skew and capacity.

## What it does not show

That the phone's Rust and Python write byte-identical files. That needs `tools/differential.py` on the device, with Python 3.12 or newer, which has not been run there yet.
