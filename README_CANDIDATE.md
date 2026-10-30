# SML identifier fix — isolated candidate

October 29, 2026. This candidate applies only the previously proposed four-line identifier-validation patch to a copy of the pinned SML implementation. The original source, historical specification, original/review reports and their failure evidence remain unchanged. Nothing is merged, published or scientifically executed.

Correction and revocation now require an exact built-in positive integer record ID. Booleans, floating-point aliases, integer subclasses, strings, missing values and nonpositive integers are rejected. Rejection preserves the exact snapshot bytes. Valid corrections/revocations retain protected historical content and provenance. Weighting formulas, retrieval scoring, capacity policy and geometry are unchanged.

Run from this folder:

```bash
sha256sum -c MANIFEST.sha256
python3 verify_candidate.py
```

Python standard library only. The complete candidate suite contains the 42 unchanged original tests plus nine new regression tests. Two additional deliberate revocation-guard defects must be detected with nonzero test exits. Exact command output, environment and source hashes are in evidence/candidate_validation.json. This is local engineering validation, not external independent review or scientific improvement.

ORIGIN.json maps copied files to their original hashes and pins the proposed source hash from the preceding review. originals/ contains the byte-identical original archive and patch. The original's reports and logs inside that ZIP remain the authoritative record of the earlier unpatched version.

Recommendation: include this candidate in the independent SML review. Do not silently replace the previously delivered version or frozen registrations. Scientific comparisons still need genuine external task/key custody, accepted review, a completed freeze and separate owner authorization. GROWTH's real baseline and human-review prerequisites remain unfilled; no person or role has been simulated.
