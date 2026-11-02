# UVR-001 results (2026-11-02)

## What could have gone wrong, first

- **The headline comparison is fixed by construction, as the registration said it would be.** On these cases, how often the newest value is wrong (q) decides who wins. Most-recent-first (MRF) is wrong exactly q · 200 times. SML is never wrong and **never right** on a contradiction: it abstains on all of them. That outcome is arithmetic. The results check that the implementation matches it; they do not show that UNKNOWN is "better". Whether it is worth it depends on the real q of a workload (P4), which nobody has measured.
- **One design detail not fixed in the registration:** each case gets its own store, so 1,400 stores with two writes each. Recall uses the default settings (similarity, threshold 0.15). Neither choice was tuned, and no case was dropped.
- **Self-tested.** Claude designed, built and ran this. The case set and tie-break were fixed in advance at Shivashish Jaishy's suggestion (Amendment 1); he has not run it.

## Order of record

1. Registration and Amendment 1, with nothing built.
2. `cases.jsonl` committed, sha256 `0742d3f8b489e86329a0b042e9e11e757acdded695b726344aa09c84237808c5`, before either policy ran. The harness refuses to run if the file changes.
3. The harness committed as it was run.
4. The runs below.

## Raw output (`run.txt`)

```
cases 1400 sha256 0742d3f8b489e863
group       policy correct wrong abstain
P1 q=0.0    SML         0     0     200
P1 q=0.0    MRF       200     0       0
P1 q=0.25   SML         0     0     200
P1 q=0.25   MRF       150    50       0
P1 q=0.5    SML         0     0     200
P1 q=0.5    MRF       100   100       0
P1 q=0.75   SML         0     0     200
P1 q=0.75   MRF        50   150       0
P1 q=1.0    SML         0     0     200
P1 q=1.0    MRF         0   200       0
P2          SML       200     0       0
P2          MRF       200     0       0
P3          SML         0     0     200
P3          MRF         0   200       0
P1: HELD  (SML wrong = 0 on contradictions; MRF wrong = round(q*200) exactly)
P2: HELD  (legitimate corrections: SML KNOWN with the new value on 200/200, same as MRF)
P3: HELD  (forged future timestamp: MRF fooled 200/200, SML UNKNOWN 200/200)
P4: OPEN (real-world q not measured; a door, not a claim)
VERDICT 3 of 3 testable predictions as registered
exit=0
```

Sabotage (`run_sabotage.txt`): with SML's contradiction check disabled, P1 and P3 are **REFUTED** and the harness exits 1. SML then answered on contradictions and was wrong 199, 147, 102, 53 and 5 times out of 200 across the five rates, plus 3 of 200 in P3. Retrieval ranks the two values equally and breaks the tie by the lower id, so it falls back to roughly "oldest first". The instrument can see the check fail.

## What this shows and does not show

- **Shows (implementation):**
  - On contradictory current values, SML never gave a wrong answer; MRF gave exactly the expected number.
  - **Legitimate updates cost nothing:** when the new value is written with `correct()`, SML answers it on 200 of 200, the same as MRF.
  - **A forged future timestamp fooled MRF on 200 of 200 and SML on 0.** MRF trusts the timestamp field. SML refuses to choose between two current values.
- **Does not show:**
  - that UNKNOWN is better for any real agent. That depends on q, and on what a wrong answer costs compared with an abstention: UNKNOWN pays off when q · cost(wrong) > (1 − q) · cost(abstain);
  - anything about retrieval quality;
  - real data.
- **Practical reading:** SML's UNKNOWN is safe to rely on **if writers use `correct()` for updates**. Two plain `put`s of different values for one key are read as a contradiction, by design.

## Open (P4)

Measure q, and how often plain `put` is used instead of `correct()`, on a real agent's memory traffic. FEB-30 (arXiv 2610.22209) may provide such trajectories if its artefacts are released.

Credit: the benchmark was proposed and its fixed-case procedure suggested by Shivashish Jaishy (Founder and CEO, Shristyverse), who agreed publicly to be credited. This implies no endorsement by him.

Provenance: Claude (Anthropic, Opus 5.5), at Chad Holland's direction (2026-11-02, direction only) → human validation: not performed → human responsibility: Chad Holland. SELF-TESTED.
