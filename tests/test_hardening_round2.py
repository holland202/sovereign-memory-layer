"""Round-2 regression tests: one per ChatGPT finding (R2-01..R2-05, M1). Synthetic fixtures only."""
import hashlib
import json
import tempfile
import threading
import unicodedata
import unittest
from pathlib import Path

from sml.memory import (CapacityError, IntegrityError, MemoryStore, ReentrancyError, canonical,
                        digest)

P = {"source": "synthetic-r2", "locator": "r2-1", "sha256": hashlib.sha256(b"r2").hexdigest()}


def rewrite(m, edit):
    """Write a correctly checksummed snapshot after `edit(payload)`: a malformed-format fixture."""
    s = json.loads(m.path.read_bytes())["payload"]
    edit(s)
    m.path.write_bytes(canonical({"payload": s, "sha256": digest(s)}) + b"\n")


def bounded(fn, seconds=5.0):
    """Run fn in a daemon thread; a hang becomes a test failure instead of a stuck suite."""
    box = {}

    def target():
        try:
            box["result"] = fn()
        except BaseException as e:  # noqa: BLE001
            box["error"] = e
    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise AssertionError(f"call did not finish within {seconds}s (deadlock)")
    if "error" in box:
        raise box["error"]
    return box.get("result")


class Round2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "s"
        self.m = MemoryStore(self.dir, create=True, clock=lambda: 1000)

    def tearDown(self):
        self.tmp.cleanup()

    def test_r2_01_recall_refuses_none_and_empty_keys(self):
        self.m.put("synthetic.alpha", "alpha-value", provenance=P)
        for bad in (None, "", "   ", 7):
            with self.subTest(key=repr(bad)), self.assertRaises(ValueError):
                self.m.recall(bad, query="synthetic missing key")

    def test_r2_02_reentrant_clock_is_refused_not_deadlocked(self):
        i = self.m.put("k", "v", provenance=P)
        box = {}

        def clock():
            if box.get("store"):
                box["store"].snapshot()
            return 1000.0
        m2 = MemoryStore(self.dir, clock=clock)
        box["store"] = m2
        before = m2.path.read_bytes()
        with self.assertRaises(ReentrancyError):
            bounded(lambda: m2.revoke(i, reason="r", provenance=P))
        self.assertEqual(m2.path.read_bytes(), before)

    def test_r2_02_reentrant_fault_before_replace_leaves_state(self):
        box = {}

        def fault(stage):
            if stage == "partial_write":
                box["store"].snapshot()
        m2 = MemoryStore(self.dir, clock=lambda: 1000, fault=fault)
        box["store"] = m2
        with self.assertRaises(ReentrancyError):
            bounded(lambda: m2.put("k", "v", provenance=P))
        self.assertEqual(MemoryStore(self.dir).snapshot()["records"], [])

    def test_r2_02_sequential_calls_still_work(self):
        self.m.put("a", "1", provenance=P)
        self.m.put("b", "2", provenance=P)
        self.assertEqual(len(self.m.snapshot()["records"]), 2)

    def test_r2_03_revoke_refuses_forbidden_label_characters(self):
        i = self.m.put("k", "v", provenance=P)
        before = self.m.path.read_bytes()
        for bad in ("a\nb", "a\x00b", "‮evil", "a​b"):
            for field in ("source", "locator"):
                with self.subTest(field=field, bad=repr(bad)), self.assertRaises(ValueError):
                    self.m.revoke(i, reason="r", provenance={**P, field: bad})
        self.assertEqual(self.m.path.read_bytes(), before)

    def test_r2_04_legacy_nfd_key_can_be_corrected(self):
        nfc, nfd = unicodedata.normalize("NFC", "café"), unicodedata.normalize("NFD", "café")
        i = self.m.put("placeholder", "old", provenance=P, protected=True, text=nfc + " old")
        rewrite(self.m, lambda s: s["records"][0].__setitem__("key", nfd))
        m = MemoryStore(self.dir, clock=lambda: 1001)
        j = m.correct(i, "new", provenance=P)
        recs = MemoryStore(self.dir).snapshot()["records"]
        self.assertEqual([(r["id"], r["status"]) for r in recs], [(i, "superseded"), (j, "current")])
        self.assertEqual(recs[0]["key"], nfd)  # historical bytes not rewritten

    def test_r2_05_out_of_range_stored_max_bytes_refused_on_load(self):
        rewrite(self.m, lambda s: s.__setitem__("max_bytes", 20_000_000))
        with self.assertRaises(IntegrityError):
            MemoryStore(self.dir)

    def test_r2_05_commit_never_exceeds_reader_limit(self):
        m = MemoryStore(Path(self.tmp.name) / "big", create=True, max_bytes=16_000_000, clock=lambda: 1000)
        before = m.path.read_bytes()
        with self.assertRaises(CapacityError):
            m.put("big", "x" * 16_000_000, provenance=P)
        self.assertEqual(m.path.read_bytes(), before)
        MemoryStore(m.directory)  # still opens

    def test_m1_schema_tag_must_be_exact_integer(self):
        for tag in (True, 1.0):
            with self.subTest(tag=tag):
                rewrite(self.m, lambda s, t=tag: s.__setitem__("schema", t))
                with self.assertRaises(IntegrityError):
                    MemoryStore(self.dir)


if __name__ == "__main__":
    unittest.main()
