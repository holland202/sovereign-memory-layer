# SML-TS-003: ChatGPT's independent findings F1–F8, reconciled — registration (2026-11-02)

Written before any fix in this round and before ChatGPT's suite was run against the current code.

**Source:** ChatGPT (OpenAI), independent review of the frozen commit `e1ad1ae`, published unchanged as draft PR #12 (`chatgpt/ts-review-20261102`, head `a7c559d`, preregistered at `f4d6810`). Its runner is `review/ts_chatgpt_20261102/review.py`, and its cases are used as they are, without editing.

## Status of each finding before this round, from its report and SML-TS-002

| | Finding | Status |
|---|---|---|
| F1 | integer weights: compaction deletes the wrong record | fixed in SML-TS-002 |
| F2 | IDs above 2^53: correction lookup conflates neighbours | open, a port bug |
| F3 | integer timestamp: revocation refused after clock rollback | fixed in SML-TS-002 |
| F4 | `null` capacities become defaults | open, a port bug |
| F5 | false-like recall query does not fall back to the key | open, a port bug |
| F6 | `rkey` on recall: the Python **wrapper** raises a duplicate-keyword TypeError | protocol decision |
| F7 | `repr` validates an unused `dir` | open, a port CLI bug |
| F8 | lone-surrogate escape: Python ValueError vs BadOp in the port **and in Rust** | protocol decision |

## Decisions (made by Claude under delegated repo calls; Chad can reverse them)

- **F6:** `rkey` is a `retrieve` option. For `recall`, the key is the recall key, as in the Python API (`recall(key, …)` forbids a second `key`). `tools/py_cli.py` will stop forwarding `rkey` to `recall`. The store (`sml/memory.py`) is unchanged. The port and Rust already behave this way.
- **F8:** the protocol refuses a lone-surrogate escape at parse time as `BadOp`, as the Rust and TypeScript CLIs already do. `tools/py_cli.py` will do the same. The store's own `ValueError` for such strings through the Python API is unchanged.
- **F2, F4, F5, F7:** fixed in the port, to follow Python.

## Predictions

- **P1 (before any fix, current head):** ChatGPT's full suite still reports F2, F4, F5, F6, F7 and F8, and **no longer** reports F1 or F3.
- **P2 (after the fixes):** ChatGPT's full suite reports **none of F1–F8**. Only the declared i64 and UTF-16/UTF-32 divergences remain.
- **P3:** the differential (D1–D4, D2, D3, D6, D7) stays IDENTICAL for **both** ports on its registered seeds. The wrapper changes must not break Rust parity.
- **P4:** `verify_hardened.py` still passes 79 tests with 19 of 19 mutants killed. `memory.py` is unchanged.

Provenance: Claude (Anthropic, Opus 5.5), at Chad Holland's direction (2026-11-02, direction only) → human validation: not performed → human responsibility: Chad Holland.
