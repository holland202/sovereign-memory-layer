# BABEL-001: authentic provenance, false conclusion (outside test, 2026-11-03)

> Published 2026-11-03 with the tester's written approval of the redactions, the provenance wording and his credit line.

**Result:** 10 of 10 registered cases PASS, and the separate mutation control PASS, against SML pinned at
`f4fc1de7c9a1d55b800dbfe09388c66b357b1f0b`. Baseline: 79 tests pass and all 19 fix-removal mutants are killed.
No SML guarantee that the test registered failed.

**What the test was about.** A real document, with its correct SHA-256, can be attached to a claim that the
document contradicts. SML stores that claim and returns it as `KNOWN`, because `KNOWN` means "one uncontradicted
current value was retrieved". It does not mean "verified". This was expected storage behavior, not a defect. At
the pinned commit, SML's docs did not say so; they now do (PR #14).

## Evidence labels

| Claim | Label | Basis |
|---|---|---|
| Test design, freeze, run and results | CONTRIBUTOR REPORTED | The tester's receipts, in `receipts/` |
| Receipts are internally consistent and match the pinned source | VERIFIED FROM SOURCE | `owner_check.py` C1–C6 (below) |
| Baseline output | SELF-TESTED, matches | Regenerated here from `f4fc1de`, byte-identical (C7) |
| The mutation control's mutant | SELF-TESTED, matches | Rebuilt here from the pinned `memory.py`, same SHA-256 (C5) |
| The 10 BABEL cases themselves | NOT RUN here | The cases were not re-executed under the frozen harness on the owner side |

## Timeline (UTC)

| Event | Time | Clock |
|---|---|---|
| Preregistration frozen (`BABEL-001-20261103T162112Z-5056af8278e8`) | 16:21:12 | tester's machine |
| Frozen files present on Google Drive | 16:24–16:25 | Google Drive (third party) |
| Run start / end | 16:28:47 / 16:29:03 | tester's machine |
| Results first reported | 16:32 | LinkedIn message |

## Registered cases (observed values from `receipts/.../BABEL001_RESULTS.json`)

| ID | Class | Observed | Verdict |
|---|---|---|---|
| 01 | Store invariant | KNOWN / CLOSED, evidence [1] | PASS |
| 02 | Boundary | KNOWN / OPEN with the genuine digest of a document that says CLOSED | PASS |
| 03 | Boundary | KNOWN / OPEN with an all-zero digest; provenance unchanged | PASS |
| 04 | Store invariant | UNKNOWN, `contradictory_current_evidence`, evidence [1, 2] | PASS |
| 05 | Store invariant | KNOWN / CLOSED; old record `superseded`, new `current` | PASS |
| 06 | Store invariant | UNKNOWN after revoke; record `revoked`, history kept | PASS |
| 07 | Store invariant | `ValueError: invalid source digest`; store bytes unchanged | PASS |
| 08 | Boundary | KNOWN / OPEN from two real documents; no corroboration implied | PASS |
| 09 | Boundary | Instruction-shaped text returned unchanged; no model run | PASS |
| 10 | Test sensitivity | Constructed `KNOWN` response rejected by the case-04 oracle | PASS |
| Control | Test sensitivity | One-line mutant (contradiction check → `if False`): intact store UNKNOWN, mutant KNOWN / OPEN, oracle rejects the mutant; both pass case 01 | PASS |

Cases 02, 03, 08 and 09 show where SML's trust boundary stops. They are not security certifications.

## Provenance

- **Credit:** Jon Beckman, for human research direction and AI-assisted adversarial scenario design. *(His
  approved wording, 2026-11-03.)* In detail, in his own words: adversarial scenario design, human-in-the-loop
  guidance, review of proposed amendments, and authorization of the preregistration freeze and of execution.
  Credit is not an endorsement of SML.
- **AI orchestration and execution:** ChatGPT 6.1 Terra Ultra (OpenAI; model name as reported by the tester)
  coordinated the workflow, prepared and checked the artifacts, and executed the frozen suite on the tester's
  machine under his authorization.
- **AI reviewers of the test design (tester-run):** Gemma E4B, Ministral 3B, Bonsai 27B. Bonsai synthesized the
  reviews. CONTRIBUTOR REPORTED.
- **Owner-side receipt check:** Claude (Anthropic, Opus 5.5), at Chad Holland's direction, checked the receipts
  and source hashes against the pinned commit, rebuilt the mutant's hash, and regenerated the baseline. Human
  review: summary-level, by Chad Holland. **Not independent of the target:** Claude co-built SML.
- **Disclosure:** ChatGPT also helped attack and harden SML in earlier rounds. The executing AI's model family
  is therefore not fully independent of the code under test. The test design was external, and the store's
  behavior here is deterministic.

This was a human-directed, AI-orchestrated test. It was not an independent human code audit or a security
certification.

## Files

- `receipts/`: the tester's 31 receipt files. Personal paths and the hostname are replaced with `<HOME>` and
  `<HOST>`; there are no other changes. `REDACTION_MAP.md` pairs each file's original SHA-256 (from the tester's
  manifest) with its published SHA-256. 23 files are byte-identical to the originals.
- `REDACTED_SHA256SUMS.txt`: hashes of the published receipts.
- `owner_check.py`: re-runs the owner-side check from any clone of this repo:
  `python3 review/babel001_2026-11-03/owner_check.py --baseline`. In a shallow clone, run
  `git fetch origin f4fc1de7c9a1d55b800dbfe09388c66b357b1f0b` first. It was shown to fail on a one-byte receipt
  change (C1, C6) and on a forged verdict with a re-forged checksum list (C6).

**Limits.** The published checksums can be re-forged together with the receipts. The original hashes recorded by
the tester, and the Drive timestamps, are the outside anchor. Run times come from the tester's clock. The BABEL
cases were not re-executed on the owner side.
