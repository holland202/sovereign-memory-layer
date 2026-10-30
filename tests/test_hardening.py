"""SML-ATK-001 regression tests: one per fixed attack. Synthetic engineering fixtures only."""
import hashlib
import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

from sml.memory import IntegrityError, MemoryStore, canonical, digest

P = {"source": "synthetic-hardening", "locator": "h-1", "sha256": hashlib.sha256(b"hardening").hexdigest()}


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "s"
        self.clock = Clock()
        self.m = MemoryStore(self.dir, create=True, clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a1_deeply_nested_file_is_integrity_error(self):
        self.m.path.write_bytes(b"[" * 100_000 + b"]" * 100_000)
        with self.assertRaises(IntegrityError):
            MemoryStore(self.dir)

    def test_a10_lock_path_directory_is_integrity_error(self):
        (self.dir / "memory.lock").unlink()
        (self.dir / "memory.lock").mkdir()
        with self.assertRaises(IntegrityError):
            MemoryStore(self.dir)

    def test_a7_revoke_allowed_when_clock_is_behind_record(self):
        i = self.m.put("k", "v", provenance=P)
        self.clock.t = 500.0
        self.m.revoke(i, reason="withdraw", provenance=P)
        rec = MemoryStore(self.dir, clock=self.clock).snapshot()["records"][0]
        self.assertEqual(rec["status"], "revoked")
        self.assertEqual(rec["revocation"]["at"], 1000.0)  # clamped, never earlier than the record

    def test_a7_correct_still_refused_when_clock_is_behind_and_unchanged(self):
        i = self.m.put("k", "v", provenance=P)
        self.clock.t = 500.0
        before = self.m.path.read_bytes()
        with self.assertRaises(ValueError):
            self.m.correct(i, "v2", provenance=P)
        self.assertEqual(self.m.path.read_bytes(), before)

    def test_a8_future_dated_record_cannot_hide_contradiction(self):
        self.m.put("k", "old", provenance=P, timestamp=400.0)
        self.m.put("k", "new", provenance=P)
        self.clock.t = 500.0
        r = self.m.recall("k", threshold=0.0)
        self.assertEqual((r["status"], r["reason"]), ("UNKNOWN", "contradictory_current_evidence"))

    def test_e1_nfc_and_nfd_keys_are_one_key(self):
        nfc, nfd = unicodedata.normalize("NFC", "café"), unicodedata.normalize("NFD", "café")
        self.m.put(nfc, "open", provenance=P)
        self.m.put(nfd, "closed", provenance=P)
        for k in (nfc, nfd):
            r = self.m.recall(k, threshold=0.0)
            self.assertEqual((r["status"], r["reason"]), ("UNKNOWN", "contradictory_current_evidence"))
        self.assertTrue(all(r["key"] == nfc for r in self.m.snapshot()["records"]))

    def test_e1_existing_non_nfc_key_still_loads_and_matches(self):
        self.m.put("plain", "v", provenance=P, text=unicodedata.normalize("NFC", "café v"))
        env = json.loads(self.m.path.read_bytes())
        s = env["payload"]
        s["records"][0]["key"] = unicodedata.normalize("NFD", "café")
        self.m.path.write_bytes(canonical({"payload": s, "sha256": digest(s)}) + b"\n")
        m = MemoryStore(self.dir, clock=self.clock)
        r = m.recall(unicodedata.normalize("NFC", "café"), threshold=0.0)
        self.assertEqual((r["status"], r["value"]), ("KNOWN", "v"))

    def test_e2_control_and_format_characters_refused_in_identifiers(self):
        before = self.m.path.read_bytes()
        for bad in ("a\x00b", "‮evil", "a​b", "a\nb"):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(ValueError):
                    self.m.put(bad, "v", provenance=P)
                with self.assertRaises(ValueError):
                    self.m.put("k", "v", provenance={**P, "source": bad})
                with self.assertRaises(ValueError):
                    self.m.put("k", "v", provenance={**P, "locator": bad})
        self.assertEqual(self.m.path.read_bytes(), before)

    def test_e2_values_may_still_contain_newlines(self):
        self.m.put("k", "line one\nline two", provenance=P)
        self.assertEqual(self.m.recall("k", threshold=0.0)["value"], "line one\nline two")


if __name__ == "__main__":
    unittest.main()
