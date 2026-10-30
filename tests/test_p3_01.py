"""P3-01 regression (ChatGPT candidate, reproduced by Claude): counters stay inside the signed 64-bit range.

Before the fix, Python created and wrote stores the Rust port refuses (max_records = 2^63, or a counter
bumped past 2^63-1)."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import sml.memory as M

P = {"source": "synthetic-p3", "locator": "p3-1", "sha256": hashlib.sha256(b"p3").hexdigest()}
TOP = 2**63 - 1


def rewrite(m, **counters):
    s = json.loads(m.path.read_bytes())["payload"]
    s.update(counters)
    m.path.write_bytes(M.canonical({"payload": s, "sha256": M.digest(s)}) + b"\n")


class P301Tests(unittest.TestCase):
    def test_max_records_bound_on_create(self):
        with tempfile.TemporaryDirectory() as td:
            M.MemoryStore(Path(td) / "a", create=True, max_records=TOP)  # the top value is allowed
            with self.assertRaises(ValueError):
                M.MemoryStore(Path(td) / "b", create=True, max_records=TOP + 1)
            self.assertFalse((Path(td) / "b").exists())

    def test_counter_above_bound_in_file_is_integrity_error(self):
        for k in ("generation", "next_id", "max_records"):
            with tempfile.TemporaryDirectory() as td:
                m = M.MemoryStore(Path(td) / "s", create=True)
                rewrite(m, **{k: TOP + 1})
                with self.assertRaises(M.IntegrityError, msg=k):
                    M.MemoryStore(Path(td) / "s")

    def test_counter_at_bound_refuses_put_revoke_compact_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            m = M.MemoryStore(Path(td) / "s", create=True, clock=lambda: 1000)
            rid = m.put("k", "v", provenance=P)
            m.put("k2", "v", provenance=P)
            rewrite(m, next_id=TOP)
            before = m.path.read_bytes()
            with self.assertRaises(M.CapacityError):
                m.put("k3", "v", provenance=P)
            self.assertEqual(m.path.read_bytes(), before)
            rewrite(m, generation=TOP)
            before = m.path.read_bytes()
            with self.assertRaises(M.CapacityError):
                m.revoke(rid, reason="r", provenance=P)
            with self.assertRaises(M.CapacityError):
                m.compact(1)
            self.assertEqual(m.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
