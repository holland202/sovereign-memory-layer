# A1-STACK results (2026-10-31)

## What could have gone wrong, first

- **The registered hypothesis is refuted.** P1 predicted `OK` on 3.14.6 with an 8 MiB stack. The run gave `RecursionError`, the same as the phone. Stack size does not explain the phone/CI difference here, so the rival, a change between 3.14.6 and 3.14.9 (H-VERSION), is still open.
- **H-VERSION was not tested directly.** 3.14.9 is not available through `uv` in this container, so it remains an untested candidate, not a finding.
- **P5 held, but it is weaker than registered.** The A1 mutant is killed at 512 KiB, but it is also killed at 8 MiB (P1), so P5 does not show that the verifier can produce its `n/a` answer here.
- **The probe can print `OK`.** An unregistered exploration, disclosed under C-EXPLORE, shows this: `explore_D100.txt`. On 3.14.6 at 8 MiB, the outcome was `OK` up to D = 10,000 and `RecursionError` at 50,000.
- **Self-tested.** Claude registered, ran and judged this. Environment: an x86_64 container, Linux, python-build-standalone 3.14.6 and 3.13.18. It is not GitHub's runner and not the phone.

## Raw output (`run.txt`)

```
host: x86_64 Linux; default ulimit -s: 8192
P1 stack=8192KiB rc=0 :: python=3.14.6 D=100000 OUTCOME=RecursionError
P2 stack=512KiB rc=0 :: python=3.14.6 D=100000 OUTCOME=RecursionError
P3 stack=8192KiB rc=0 :: python=3.13.18 D=100000 OUTCOME=RecursionError
P4 stack=8192KiB rc=0 :: OK
P5 stack=512KiB rc=0 :: A1="A1-recursion-not-caught": "killed" verdict="verdict": "PASS"
```

Exploration (`explore_D100.txt`):
```
python=3.14.6 D=100 OUTCOME=OK
python=3.14.6 D=1000 OUTCOME=OK
python=3.14.6 D=10000 OUTCOME=OK
python=3.14.6 D=50000 OUTCOME=RecursionError
```

## Predictions

| ID | Prediction | Result |
|---|---|---|
| P1 | 3.14.6, 8 MiB, D = 100k → `OK` | **REFUTED**: `RecursionError` |
| P2 | 3.14.6, 512 KiB → `RecursionError`, no crash | HELD |
| P3 | 3.13.18 control → `RecursionError` | HELD |
| P4 | the SML deep-nesting test passes on 3.14.6 | HELD |
| P5 | the A1 mutant is killed at 512 KiB | HELD, but it does not discriminate (see above) |

## What this shows

- Python 3.14.6 raises `RecursionError` on 100,000-deep JSON on x86_64 Linux, as it does on the phone. The difference from GitHub's runners therefore follows the version (3.14.6 versus 3.14.9), or something else about those runners, not this container's stack.
- SML fails closed on the deep file on 3.14.6 (P4), and CI shows it also passes on 3.14.9. So the store's safety does not depend on which behaviour the interpreter has. Only the A1 mutant's killability does, and the verifier already probes for that at run time.

## Open

- Run `probe.py 100000` under CPython 3.14.9 itself, for example in a CI step, to confirm H-VERSION directly.
- Find the change between 3.14.6 and 3.14.9 that explains it. One web search did not find it.

Provenance: Claude (Anthropic, Opus 5.5), at Chad Holland's direction (2026-10-31, direction only) → human validation: not performed → human responsibility: Chad Holland. SELF-TESTED.
