# Independent TypeScript port review — preregistration

Date: 2026-11-02. Owner: Chad Holland. Reviewer: ChatGPT (OpenAI).

## Frozen target and execution boundary

- Repository: `holland202/sovereign-memory-layer`, PR #9, `claude/ts-port`.
- Reviewed target: `e1ad1ae03aab8feb924b53365b4e943750026487`.
- Original registration: `8eae03bc0aee9bc47d0ec0feb2933b3614cde279`, `ts/PORT_PREREG.md`.
- Port/harness-as-run: `3f98bf5f64236112ad1f5b9b0e1cb4be0fd0b910`.
- Python and, if available, Rust references come from the same frozen target.
- Work goes only on `chatgpt/ts-review-20261102`, under this review directory. Do not modify `ts/src`, main, or Claude's branch. Any mutant is a temporary copy or separate wrapper. Submit a draft review PR; no merge. No UVR-001 work.
- This registration is committed before any port operation, attack, random test, or mutation is executed. Source inspection and environment discovery have occurred; this is source-informed independent review, not a blind review. No human validation is claimed.
- Observed environment before registration: CPython 3.12.14, Node 24.22.1, Linux x86_64, glibc 2.39, CPU flag FMA. No npm install. Other operating systems and non-FMA CPUs are NOT TESTED unless actually obtained.

## Oracle, labels, and defect rule

For supported inputs, compare each raw protocol response, success/failure class, and `memory.json` bytes after every operation against the frozen Python reference. Independently assert the positive and negative controls rather than inferring success from zero differences. Save input JSONL, stdout/stderr, process exit codes, snapshot hashes, and complete mismatch details. Cross-opening must preserve the exact bytes. Distinguish protocol/wrapper defects from data integrity defects and reference-side failures.

`VERIFIED` means the stated check was executed and its criterion held. `FAILED` means an executed, reproducible contract violation, including a supported operation refusing a valid input or producing different stored bytes. `UNKNOWN` means evidence is inconclusive. `NOT TESTED` (and explicit `NOT RUN` for unexecuted commands) means no execution evidence. A matching error alone is not evidence that a success path works. Record shared failures without promoting agreement into correctness.

Declared divergences are not new findings: single-process only/no file lock/D5 excluded; x86_64 glibc 2.39 FMA exp identity only; integers outside signed i64; UTF-16/32 files; Unicode-version differences; omitted OrthoProjection and policies.admit. Inputs outside i64 and newer Unicode mappings will be classified separately, even when they produce different outcome classes. The exact signed i64 limits are -2^63 and 2^63-1.

## Registered attacks and predictions

| ID | Cases to implement independently | Expected behavior / defect criterion |
| --- | --- | --- |
| C0 | Valid create, put with explicit unit embedding, recall/retrieve, correction, revocation, protected-chain compaction refusal, reopen | All sides must succeed or refuse exactly as the Python contract specifies; hashes agree. The runner must fail its own control if an expected success is missing. |
| C1 | Deliberately broken TS response wrapper changes an acknowledged successful put ID; additionally run the existing naive-sum sabotage on a temporary copy | The independent comparator must detect the changed ID while C0 agrees on the unmodified port; existing harness must print `SABOTAGE CAUGHT`. Failure to catch is a review/harness failure, not a port pass. |
| A1 | Astral/BMP characters in keys, values, text, provenance, queries and correction chains; NFC/NFD; whitespace; escaped surrogate pairs; invalid lone-surrogate tokens separately | Valid strings preserve code points and byte-identical canonical files. Invalid identifiers refuse without file change. Surrogate/parser-only differences must be reported at their correct layer. |
| A2 | Canonical key ordering using mixed BMP/astral keys through exported JSON encoder; Python code-point order and nested objects | Canonical UTF-8 bytes must agree, including keys whose UTF-16 and code-point orders differ. |
| A3 | Raw JSON spellings -0, -0.0, 1E5, exponent under/overflow, near 2^53 and both i64 endpoints, >i64 integers and long digit strings; use numeric fields, record IDs, embedding entries, and unused protocol fields | Supported numbers retain int/float distinction and correct formatting, bounds and refusal classes. Out-of-i64 cases remain declared divergences. Rejected writes leave bytes unchanged. Nonfinite/invalid JSON differences are distinguished from valid JSON defects. |
| A4 | true/false, integral floats, strings, null, omitted fields in integer-only capacities, IDs, top_k, compact target; boolean numerics in clock/weight/threshold/embeddings | Exact Python validation, no bool-as-int acceptance; omission and null are compared individually, not assumed equivalent. |
| A5 | Greek final sigma with punctuation/combining characters, Turkish I, sharp s, Deseret astral casing, Unicode whitespace; only mappings known to both runtimes count as supported | Hash embeddings and retrieval bytes agree. New Unicode-version differences are declared, not new defects. |
| A6 | Missing/null/false/0/empty list/empty object/empty string in protocol optional fields, especially recall query, create capacities and retrieval options; explicit rkey in recall | Match the Python protocol's defaulting and keyword binding. Report API/wrapper mismatches separately, including accidental reference errors. |
| A7 | Multiple simultaneous errors: absent/corrupt store plus invalid inputs, full capacity plus invalid supersedes/resource state, invalid dir plus invalid create capacities, repr/file plus irrelevant dir/clock; lock-path and pending-path errors | Same first error class and unchanged snapshot on refusal. Error-order-only failures are identified as such. No concurrent writers. |
| A8 | Checksummed snapshots with counters/IDs at 2^53 and i64 boundaries, adjacent IDs and correction targets, ints/floats in embeddings/weights, negative zero, syntactically alternate numeric spellings; invalid schema/counters/checksum/UTF-8 | Supported valid files open and cross-open consistently; documented invalid files return IntegrityError and stay unchanged. Writes at exhausted counters refuse with CapacityError without changing bytes. |
| A9 | If Rust build/runtime is available, drive Rust vs TS directly on C0 and A1/A3/A4/A5/A6/A8 supported cases | Compare direct responses and snapshot bytes; do not substitute two separate Python comparisons for direct evidence. If unavailable, save attempted setup command/output and label NOT TESTED/NOT RUN. |
| B1 | Existing quick and full Python/TS differential, using fresh `--dev-seed 11022026` (not author's registered seeds); full includes D1/D4, D2, D3, D6 | No mismatches. Save complete stdout/stderr and exit status. The quick and full runs are independent review repetitions, not new confirmatory results under Claude's registration. |
| B2 | Existing million-input exp check with fresh `--seed 1102202601`; include finite boundary values in independent numeric checks | Zero bit differences on this platform. Save raw checker output; do not claim other platforms. |

## Execution and analysis plan

Implement a bounded standard-library Python runner and small TS adapter under this directory. Use a new temporary store per independent case and sequential processes per store. Preserve all operation inputs and responses even on mismatches; a discovered mismatch must not hide later checks. Set finite process/operation deadlines; a runner error is UNKNOWN until resolved and disclosed. Minimal reproductions may be extracted from registered failing cases without inventing a new attack after seeing outputs. New attack families require a committed addendum before execution. Repetitions after a runner repair are exploratory repetitions and preserve earlier raw output.

Record target blob hashes before and after execution and refresh PR #9 at completion. Report any post-freeze change under `ts/src` with exact commits; docs/manifest-only merges do not alter the frozen target. Commit scripts, raw evidence, a checksum manifest, and the review report after execution. The draft PR will target `claude/ts-port` so its diff consists only of the independent review; if the port merges first, target main without changing production source.

Provenance line: ChatGPT (OpenAI) designed and ran this review → human validation: not performed → human responsibility: Chad Holland.
