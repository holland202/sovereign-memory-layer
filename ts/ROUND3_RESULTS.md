# SML-TS-003 results: ChatGPT's F1–F8 reconciled (2026-11-02)

## What could have gone wrong, first

- **ChatGPT's independent review found real bugs that Claude's two earlier rounds missed:**
  - **F2:** correction lookup conflated record IDs above 2^53, so a valid correction was refused;
  - **F4:** an explicit `null` capacity silently became the default;
  - **F5:** a recall query such as `false` or `0` did not fall back to the key, as Python's `query or key` does;
  - **F7:** `repr` validated a directory it never uses.

  SML-TS-001 claimed "6 of 6" and SML-TS-002 found only part of the problem. Both records stand unchanged; the bugs were real.
- **Two findings were in the reference *test wrapper*, not in the port** (F6: `rkey` on recall; F8: lone-surrogate escapes). They were settled by a protocol decision recorded in `ROUND3_PREREG.md` *before* the fix. The Python wrapper now follows the behaviour the Rust and TypeScript CLIs already had. `sml/memory.py` is unchanged. Chad Holland can reverse these decisions.
- **Self-tested fixes, independent test cases.** ChatGPT wrote the 337 cases; Claude wrote the fixes and ran the suite. ChatGPT has not re-run its suite on the fixed code. Until it does, this is not an independent confirmation.
- **A wrong label inside ChatGPT's runner:** its summary's `target` field is hard-coded to `e1ad1ae`. The runs below were made on `claude/ts-port` at the commits named here, not at `e1ad1ae`.

## How it was run

ChatGPT's runner and cases came from its branch (`chatgpt/ts-review-20261102`, `a7c559d`, draft PR #12). They were copied unchanged into a checkout of `claude/ts-port` and run from the repository root:

```
python3 review/ts_chatgpt_20261102/review.py --out <dir>
```

The copy was removed afterwards; the runner lives on ChatGPT's branch.

## Results

| | Prediction | Result |
|---|---|---|
| P1 | before any fix (`611d8ee`): F2, F4, F5, F6, F7, F8 still reported; F1 and F3 gone | **HELD**: 31 failing cases (F8 6, F4 2, F5 4, F6 6, F7 5, F2 8); none from F1 or F3 (`results/round3/p1_*`) |
| P2 | after the fixes: none of F1–F8 | **HELD**: 337 cases, 796 steps, **0 failing**. Only the 20 declared differences remain: 18 numbers outside signed i64, plus UTF-16 and UTF-32 (`p2_*`) |
| P3 | differential IDENTICAL for both ports | **HELD**: TS D1, D2, D3, D6, D7 and Rust D1, D2, D3, D5, D6, D7, all 0 mismatches (`p3_*`) |
| P4 | `verify_hardened.py` still passes | **HELD**: 79 tests, PASS (`p4_verify.txt`) |
| Control | ChatGPT's own `--mutant` run must fail | caught: exit 1, 70 failing cases (`chatgpt_mutant_control.txt`) |

## The fixes

- `ts/src/store.ts`:
  - `pyEq` compares integers exactly (BigInt), never through a double. **(F2)**
  - Only an *omitted* capacity takes the default; `null` is refused. **(F4)**
  - Recall uses Python's truthiness for `query or key`. **(F5)**
- `ts/src/cli.ts`: `repr` is answered before the directory is checked. **(F7)**
- `tools/py_cli.py`, the reference wrapper only:
  - `rkey` is no longer forwarded to `recall`. **(F6)**
  - A lone-surrogate escape in a request is `BadOp`. **(F8)**

## Open

- **ChatGPT should re-run its suite on the fixed head** to confirm independently.
- Run its prepared three-way command (Python, TypeScript and Rust) now that Rust is available here.
- Platforms other than glibc x86_64 have still not been tested.

Credit: findings F1–F8 by ChatGPT (OpenAI), whose independent review was run at Chad Holland's direction.

Provenance: fixes and runs by Claude (Anthropic, Opus 5.5), at Chad Holland's direction (2026-11-02, direction only) → human validation: not performed → human responsibility: Chad Holland.
