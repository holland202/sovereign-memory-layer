# SML-TS-002 results (2026-11-02)

## What could have gone wrong, first

- **The port was wrong, and SML-TS-001's tests could not see it.** D1 to D6 only fed the port files that an implementation had written, and those always hold floats. On a valid file with integer weights, the TypeScript port **compacted the wrong records**:

  ```
  compact target=4: Python removed [5], the port removed [1, 4]
  ```

  On such files it would also have written a revocation time as a float where Python keeps the int. SML-TS-001's "6 of 6 as registered" was true of what it tested, and that scope was too narrow. Its record is kept unchanged.
- **Who found it:** ChatGPT (OpenAI), in an independent review on 2026-11-02. It reported 8 findings across 34 cases, including incorrect compaction, which Chad Holland relayed in summary. **Its bundle has not reached Claude.** D7 is Claude's own test, built from the description, and its cases are not ChatGPT's. Whether all 8 of ChatGPT's findings are covered is **UNKNOWN** until its cases are run, in particular the refused corrections and revocations it mentions. D7 did not reproduce a refusal.
- **Self-tested.** Claude designed D7, fixed the port and ran the tests.

## Raw output

P1, the pre-fix port, on a development seed (`results/round2/p1_prefix_dev1.txt`):
```
D7: {"snapshots_used": 60, "discarded_invalid": 0, "int_fields_injected": 398, "nfd_keys": 29, "ops": 792, "mismatches": 12, ...
  {"snapshot": 5, "op": "{\"op\": \"compact\", \"target\": 4, ...}", "py": "{\"ok\":true,\"result\":[5]}", "port": "{\"ok\":true,\"result\":[1,4]}", "file_equal": false}
VERDICT 12 MISMATCH GROUP(S)
```
P2, the fixed port, on the registered seed, run once (`p2_d7_registered.txt`):
```
D7: {"snapshots_used": 300, "discarded_invalid": 0, "int_fields_injected": 2154, "nfd_keys": 138, "ops": 4200, "mismatches": 0, "first": []}
VERDICT IDENTICAL
```
P3, D1 to D6 re-run (`p3_d1_d6.txt`): D1 24,400 ops, D2 200,000 values, D3 3,402 cases and D6 100 kills, all with 0 mismatches. VERDICT IDENTICAL.

P4, Rust, D7 on the registered seed (`p4_rust_d7.txt`): 300 snapshots, 4,200 ops, 0 mismatches. VERDICT IDENTICAL.

Development runs before P2 (disclosed): dev seed 1, 60 snapshots, 0 mismatches after the fix; dev seed 2, 300 snapshots, 0 mismatches.

## Predictions

| ID | Prediction | Result |
|---|---|---|
| P1 | D7 finds at least one mismatch in the pre-fix port | HELD: 12 snapshots, compaction |
| P2 | fixed port, registered seed: 0 mismatches | HELD |
| P3 | D1 to D6 still IDENTICAL | HELD |
| P4 | Rust under D7: recorded as found | 0 mismatches |
| P5 | D7 can see this bug class | HELD (it is P1) |

## The fix

Two places treated a field that can hold an int as a JavaScript number:
- `compact` compared weights with `>` against the integer object;
- `revoke` took `max(now, timestamp)` on the raw value and stored `now` instead of the int.

Both now follow Python. Every other read of these fields already went through `toF`.

## Open

- **Run ChatGPT's 34 cases** once its bundle arrives, and reconcile all 8 findings one by one.
- D7 is now part of the default differential for both ports, and CI runs it.

Provenance: Claude (Anthropic, Opus 5.5), at Chad Holland's direction (2026-11-02, direction only) → human validation: not performed → human responsibility: Chad Holland. Finding first reported by ChatGPT (OpenAI). SELF-TESTED.
