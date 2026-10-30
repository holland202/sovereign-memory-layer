"""Round-3 regression (ChatGPT finding SML-R3-02): integers a float cannot hold exactly are refused."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import sml.memory as M

P = {"source": "synthetic-r3", "locator": "r3-1", "sha256": hashlib.sha256(b"r3").hexdigest()}


class Round3Tests(unittest.TestCase):
    def test_r3_02_inexact_integer_timestamp_refused_on_put(self):
        with tempfile.TemporaryDirectory() as td:
            m = M.MemoryStore(Path(td) / "s", create=True, clock=lambda: 2**53)
            before = m.path.read_bytes()
            with self.assertRaises(ValueError):
                m.put("k", "v", provenance=P, timestamp=2**53 + 1)  # after the clock, but rounds to it
            self.assertEqual(m.path.read_bytes(), before)
            self.assertEqual(m.put("k", "v", provenance=P, timestamp=2**53), 1)  # exact integers still fine

    def test_r3_02_inexact_integer_in_stored_file_is_integrity_error(self):
        with tempfile.TemporaryDirectory() as td:
            m = M.MemoryStore(Path(td) / "s", create=True, clock=lambda: 1000)
            m.put("k", "v", provenance=P)
            s = json.loads(m.path.read_bytes())["payload"]
            s["records"][0]["timestamp"] = 2**53 + 1
            s["records"][0]["recorded_at"] = 2**53 + 1
            m.path.write_bytes(M.canonical({"payload": s, "sha256": M.digest(s)}) + b"\n")
            with self.assertRaises(M.IntegrityError):
                M.MemoryStore(Path(td) / "s")

    def test_huge_integer_is_value_error_not_overflow(self):
        with self.assertRaises(ValueError):
            M.number(10**400, "x")


if __name__ == "__main__":
    unittest.main()
