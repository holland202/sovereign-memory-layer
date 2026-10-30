# Round 2 review (ChatGPT, AI-assisted) and Claude's reproduction

- `TEST_REVIEW_FINDINGS.md` (sha256 1c86005c…68e0) and `SML_ROUND2_TEST_REVIEW_EVIDENCE_2026-10-30.zip` (sha256 899949ec…ba82) are kept **verbatim** as received from Chad's Drive. Their sizes and hashes match ChatGPT's SHA256SUMS file, and the zip's internal `MANIFEST_REVIEW.sha256` checks 100% OK.
- `claude_reproduction_on_round1/` holds Claude's run of all 14 ChatGPT scripts against a fresh extraction of `SML_HARDENED_ROUND1.zip` (`memory.py` 507baf59…). Same result as ChatGPT: **7 exit 1** (clock_reentry, fault_reentry, invalid_capacity_snapshot, legacy_nfd_correction, missing_key_known, revocation_source_labels, snapshot_schema_type) and **7 exit 0**.
- Status: R2-01 to R2-05 and M1 are **REPRODUCED (by Claude; AI, not independent)**.

## Fix plan (written before any fix)

| Finding | Fix | Check that must hold afterwards |
|---|---|---|
| R2-01 | `recall()` requires a non-empty string key | ChatGPT's `test_missing_key_known.py` exits 0; a new regression test |
| R2-02 | A same-thread nested store call on the same directory is refused with `ReentrancyError` instead of waiting forever. Other threads still wait their turn | both re-entry scripts exit 0; A6/E4 concurrency stays clean |
| R2-03 | `revoke()` applies the same source/locator character rule as `put()` | `test_revocation_source_labels.py` exits 0 |
| R2-04 | snapshot validation compares correction-link keys with the same NFC rule | `test_legacy_nfd_correction.py` exits 0 |
| R2-05 | load refuses `max_bytes` outside 1,024..16,000,000; commit refuses a file over the reader limit | `test_invalid_capacity_snapshot.py` exits 0 |
| M1 | **Decision (Claude, delegated by Chad):** `schema` must be exactly integer 1, the same exact-integer policy as IDs | `test_snapshot_schema_type.py` exits 0 |

All 14 ChatGPT scripts must exit 0 afterwards. The 60 earlier tests, Claude's A1–A15 and E1–E5 must not regress, and each new fix gets a fix-removal mutant that must be killed.
