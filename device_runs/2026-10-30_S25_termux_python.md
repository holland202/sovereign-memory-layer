# Device run: Samsung Galaxy S25 Ultra, Termux (2026-10-30)

**Status: OWNER-RUN on the device.** Chad Holland ran this himself on his phone and pasted the output to Claude. It was not independently reproduced, and the phone's Python version was not captured in this run.

**Commit tested:** a fresh `git clone` of `main` at `38f5f46`, the head at the time.

**Command:**

```
cd ~ && git clone https://github.com/holland202/sovereign-memory-layer && cd sovereign-memory-layer && python3 verify_hardened.py
```

**Output (verbatim, the verifier's lines only):**

```
{
 "suite_tests": 69,
 "suite_ok": true,
 "mutants": {
  "A1-recursion-not-caught": "killed",
  "A10-lock-open-unwrapped": "killed",
  "A7-revoke-clock-unclamped": "killed",
  "A8-future-records-ignored": "killed",
  "E1-no-nfc": "killed",
  "E2-no-control-check": "killed",
  "R2-01-recall-key-unchecked": "killed",
  "R2-02-no-reentrancy-guard": "killed",
  "R2-03-revoke-old-provenance-check": "killed",
  "R2-04-exact-key-link-check": "killed",
  "R2-05-no-stored-max-bytes-range": "killed",
  "M1-schema-type-unchecked": "killed"
 },
 "verdict": "PASS"
}
```

## What this shows

- **The full Python suite passes on Android/Termux:** 69 tests, all 12 fix-removal mutants killed. That includes the kill-mid-write crash tests and the multi-process lock tests, run on the phone's own filesystem and `flock`.
- **The A1 mutant was killed here.** So this phone's Python still raises `RecursionError` on 100,000-deep JSON, unlike CPython 3.14.9 on GitHub's runners. The interpreter version should be recorded next (`python3 --version`).

## What it does not show

- Behaviour under real power loss, or when Android kills the app.
- Anything about the Rust port on the phone; that has not been run there yet.
