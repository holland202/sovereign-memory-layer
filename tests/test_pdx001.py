"""PDX-001 regression tests (review/pdx001_2026-11-13/PREREG.md). SELF-TESTED: written by Claude Opus 5.5, 2026-11-13.

1. A protected record is exempt from the retrieval decay factor, so an old protected record is still returned.
2. Unprotected records still decay (the exemption is not over-broad).
3. recall reports current_evidence_not_retrieved, with ids and no value, when current evidence exists but is not
   retrieved; and insufficient_evidence with [] when the key has no current record.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path

from sml.memory import DIM, MemoryStore

P = {"source": "pdx001-test", "locator": "row-1", "sha256": hashlib.sha256(b"pdx001-test").hexdigest()}
DAY = 86400.0
NOW = 2_000_000_000.0


def axis(i):
    return [float(j == i) for j in range(DIM)]


class PDX001Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.m = MemoryStore(Path(self.temp.name) / "store", create=True, max_records=10, clock=lambda: NOW)

    def tearDown(self):
        self.temp.cleanup()

    def test_old_protected_record_is_not_decayed_away(self):
        rid = self.m.put("allergy", "peanuts", provenance=P, protected=True, timestamp=NOW - 300 * DAY,
                         embedding=axis(0))
        for method in ("recency", "importance", "protected"):
            hits = self.m.retrieve("allergy", method=method, embedding=axis(0))
            self.assertEqual([h["record"]["id"] for h in hits], [rid], method)
            self.assertEqual(hits[0]["explanation"]["decay_factor"], 1.0, method)
            r = self.m.recall("allergy", method=method, embedding=axis(0))
            self.assertEqual((r["status"], r["value"]), ("KNOWN", "peanuts"), method)

    def test_unprotected_records_still_decay(self):
        old = self.m.put("note", "old", provenance=P, timestamp=NOW - 300 * DAY, embedding=axis(1))
        hits = self.m.retrieve("note", method="recency", threshold=0, embedding=axis(1))
        self.assertEqual([h["record"]["id"] for h in hits], [old])
        self.assertLess(hits[0]["explanation"]["decay_factor"], 0.001)
        self.assertEqual(self.m.retrieve("note", method="recency", embedding=axis(1)), [])

    def test_recall_names_current_evidence_that_was_not_retrieved(self):
        old = self.m.put("note", "old", provenance=P, timestamp=NOW - 300 * DAY, embedding=axis(1))
        r = self.m.recall("note", method="recency", embedding=axis(1))
        self.assertEqual(r, {"status": "UNKNOWN", "reason": "current_evidence_not_retrieved", "evidence_ids": [old]})
        self.assertNotIn("value", r)

    def test_recall_without_current_evidence_is_unchanged(self):
        rid = self.m.put("gone", "x", provenance=P, timestamp=NOW - DAY, embedding=axis(2))
        self.m.revoke(rid, reason="withdrawn", provenance=P)
        self.assertEqual(self.m.recall("gone", embedding=axis(2)),
                         {"status": "UNKNOWN", "reason": "insufficient_evidence", "evidence_ids": []})
        self.assertEqual(self.m.recall("never-stored", embedding=axis(2)),
                         {"status": "UNKNOWN", "reason": "insufficient_evidence", "evidence_ids": []})


if __name__ == "__main__":
    unittest.main()
