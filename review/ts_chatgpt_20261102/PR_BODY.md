The frozen TypeScript port agrees with the existing full differential, but independent cases expose incorrect compaction with integer weights, correction refusals at supported large IDs, revocation refusal for integer timestamps after clock rollback, and several defaulting/protocol differences.

This review is pinned to `e1ad1ae03aab8feb924b53365b4e943750026487`. The preregistration commit precedes execution. All additions are under `review/ts_chatgpt_20261102/`; no production code or existing evidence was changed. See `REPORT.md` for eight distinct findings across 34 cases, minimal reproduction commands, isolated repetitions, raw streams, fixtures, snapshot bytes, and limitations.

Validation: full differential (24,400 ops, 200,000 reprs, 3,402 file cases, 100 SIGKILL trials) and 1M exp checks pass using fresh development seeds. Independent positive control passes; the existing naive-sum sabotage and an independent wrong-ID mutant are both caught. The attack runner exits 1 for reproduced differences. Rust direct comparison, macOS and Android are NOT TESTED.

This draft depends on PR #9 and should target `claude/ts-port` while that PR is open. After #9 merges, retarget to main and check that the review diff still contains only this directory. Fixes are separate; do not merge this review or change readiness labels automatically.

ChatGPT (OpenAI) designed and ran this review → human validation: not performed → human responsibility: Chad Holland.
