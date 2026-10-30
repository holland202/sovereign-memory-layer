"""Engineering fault injection only; no comparative-memory workload."""
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from sml.memory import MemoryStore

P = {"source": "synthetic", "locator": "fixture", "sha256": hashlib.sha256(b"synthetic").hexdigest()}
CHILD = '''
import os, signal, sys
from sml.memory import MemoryStore
p = {"source":"synthetic","locator":"fixture","sha256":"''' + P['sha256'] + '''"}
stage = sys.argv[2]
def kill_at(s):
    if s == stage: os.kill(os.getpid(), signal.SIGKILL)
m = MemoryStore(sys.argv[1], clock=lambda:1000, fault=kill_at)
m.put("new.fact", "committed-or-absent", provenance=p)
'''


class CrashTests(unittest.TestCase):
    def test_sigkill_at_four_commit_boundaries(self):
        for stage, new_visible in [("partial_write",False), ("after_file_fsync",False),
                                   ("after_replace",True), ("after_dir_fsync",True)]:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as td:
                path=Path(td)/"store"
                m=MemoryStore(path, create=True, clock=lambda:1000)
                m.put("old.fact", "survives", provenance=P)
                r=subprocess.run([sys.executable,"-c",CHILD,str(path),stage], capture_output=True, timeout=15)
                self.assertEqual(r.returncode, -signal.SIGKILL, r.stderr.decode())
                recovered=MemoryStore(path)
                rs=recovered.snapshot()["records"]
                self.assertEqual([x["key"] for x in rs], ["old.fact","new.fact"] if new_visible else ["old.fact"])
                self.assertEqual(recovered.storage_status()["incomplete_storage_detected"], not new_visible)

    def test_concurrent_cooperative_writers(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"store"
            MemoryStore(path, create=True, max_records=10)
            code='''
import sys
from sml.memory import MemoryStore
m=MemoryStore(sys.argv[1])
m.put("synthetic."+sys.argv[2], "fact", provenance='''+repr(P)+''')
'''
            processes=[subprocess.Popen([sys.executable,"-c",code,str(path),str(i)], stdout=subprocess.PIPE,stderr=subprocess.PIPE) for i in range(4)]
            for proc in processes:
                _,err=proc.communicate(timeout=15)
                self.assertEqual(proc.returncode,0,err.decode())
            self.assertEqual(len(MemoryStore(path).snapshot()["records"]),4)


if __name__ == "__main__":
    unittest.main()
