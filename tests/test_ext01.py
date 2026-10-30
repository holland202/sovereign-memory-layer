"""EXT-01 regression tests (external reviewer's observations, reproduced and fixed). Synthetic fixtures."""
import fcntl
import hashlib
import tempfile
import unittest
from pathlib import Path

import sml.memory as M

P = {"source": "synthetic-ext01", "locator": "t-1", "sha256": hashlib.sha256(b"t").hexdigest()}


class Ext01Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = M.MemoryStore(Path(self.tmp.name) / "s", create=True, max_bytes=4096, clock=lambda: 1000)
        self.real_flock, self.real_embed = M.fcntl.flock, M.hash_embedding

    def tearDown(self):
        M.fcntl.flock, M.hash_embedding = self.real_flock, self.real_embed
        self.tmp.cleanup()

    def test_n1_oversized_write_refused_before_embedding_work(self):
        def no_embedding(_):
            raise AssertionError("embedding computed for a write that cannot fit")
        M.hash_embedding = no_embedding
        before = self.m.path.read_bytes()
        with self.assertRaises(M.CapacityError):
            self.m.put("k", "a " * 500_000, provenance=P)
        self.assertEqual(self.m.path.read_bytes(), before)

    def test_n3_flock_failure_is_lock_error_and_unchanged(self):
        def fail(fd, op):
            if op == fcntl.LOCK_EX:
                raise OSError(37, "No locks available (injected)")
            return self.real_flock(fd, op)
        before = self.m.path.read_bytes()
        M.fcntl.flock = fail
        with self.assertRaises(M.LockError):
            self.m.put("k", "v", provenance=P)
        self.assertTrue(issubclass(M.LockError, M.IntegrityError))
        self.assertEqual(self.m.path.read_bytes(), before)

    def test_n4_unlock_failure_never_masks_a_committed_write(self):
        def fail(fd, op):
            if op == fcntl.LOCK_UN:
                raise OSError(37, "No locks available (injected)")
            return self.real_flock(fd, op)
        M.fcntl.flock = fail
        i = self.m.put("k", "v", provenance=P)
        M.fcntl.flock = self.real_flock
        self.assertEqual([r["id"] for r in self.m.snapshot()["records"]], [i])

    def test_refusal_order_unchanged_invalid_target_beats_full_bytes(self):
        i = self.m.put("k", "v" * 200, provenance=P)
        self.m.revoke(i, reason="r", provenance=P)
        with self.assertRaises(ValueError) as cm:  # not CapacityError: the target is no longer current
            self.m.correct(i, "w" * 3000, provenance=P)
        self.assertNotIsInstance(cm.exception, M.CapacityError)


if __name__ == "__main__":
    unittest.main()
