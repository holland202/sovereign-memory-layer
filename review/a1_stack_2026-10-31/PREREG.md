# A1-STACK: why deep JSON raises RecursionError on one Python 3.14 and not another — registration (2026-10-31)

Written before anything below was run. Nothing has been built or run yet.

## Question

The A1 mutant (`RecursionError` removed from the `except` that turns a bad file into `IntegrityError`) is killed on the S25's Python 3.14.6 but cannot be killed on CPython 3.14.9 on GitHub's runners. On those runners, `json.loads` on 100,000-deep nesting does not raise `RecursionError`. Is the difference the Python version, or the platform's stack?

## Hypothesis (H-STACK)

CPython 3.14 changed how C code such as the `json` decoder checks recursion: the check now looks at how much machine stack is left instead of counting calls. If that is right, whether 100,000-deep JSON raises depends on the stack available (Linux 8 MiB by default; Android may give less), not on 3.14.6 versus 3.14.9.

**Rival (H-VERSION):** a change between 3.14.6 and 3.14.9 causes it.

## Design

- Interpreter: CPython 3.14.6 from python-build-standalone (via `uv`), x86_64 Linux, which is the same version as the phone. Container's 3.13.18 as a control.
- Input: `"[" * D + "]" * D` for D = 100,000, the same input as the verifier's probe.
- Stack: the container's default (`ulimit -s` = 8192 KiB), and a reduced stack (`ulimit -s 512`) in a fresh process.
- Outcome per run: one of `OK` (loaded), `RecursionError`, `other:<type>`, or `crash` (killed by a signal).

## Predictions

- **P1:** 3.14.6, default 8 MiB stack, D = 100,000 → `OK`. If H-VERSION is right this would be `RecursionError`, as on the phone.
- **P2:** 3.14.6, 512 KiB stack, D = 100,000 → `RecursionError`, not `crash`.
- **P3 (control):** 3.13.18, default stack, D = 100,000 → `RecursionError`. 3.13 still counts calls.
- **P4 (does the store still fail closed):** on 3.14.6 with the default stack, SML's own `tests/test_hardening.py` deep-nesting test passes. The store answers `IntegrityError` for the deeply nested file even when `json` does not raise.
- **P5 (anti-vacuity):** on 3.14.6 with the 512 KiB stack, the A1 mutant is killed by `verify_hardened.py`. This shows the instrument can return the other answer in this container.

If P1 is `RecursionError`, H-STACK is refuted as the explanation of the phone/CI difference, and H-VERSION stays open. No result here says anything about the phone's actual stack size; that would need a run on the device.

## Limits

- The container is not GitHub's runner and not the phone.
- 3.14.9 is not available through `uv` here, so 3.14.6 versus 3.14.9 is not compared directly.

Provenance: Claude (Anthropic, Opus 5.5) wrote this registration under repo-work calls delegated by Chad Holland (2026-10-31, direction only). It is self-designed and will be self-run: SELF-TESTED, not independent.
