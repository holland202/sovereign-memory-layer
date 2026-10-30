#!/usr/bin/env python3
"""Verify the SML-ATK-001 hardening. Standard library only; never runs a scientific comparison.

1. The full suite passes: 51 earlier tests (42 original + 9 identifier) + 9 hardening tests = 60.
2. Each fix is load-bearing: removing it (one mutant per fix) makes tests/test_hardening.py fail.
Exit 0 only if both hold. (verify_candidate.py is kept unchanged; it pins the earlier candidate
source and so refuses this hardened version by design.)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MUTANTS = {
    "A1-recursion-not-caught": (", RecursionError) as e:  # ATK A1", ") as e:  # ATK A1"),
    "A10-lock-open-unwrapped": ("        except OSError as e:  # ATK A10", "        except ZeroDivisionError as e:  # ATK A10"),
    "A7-revoke-clock-unclamped": ('"at": max(number(self.clock(), "clock"), r["timestamp"])}',
                                  '"at": number(self.clock(), "clock", r["timestamp"])}'),
    "A8-future-records-ignored": ('if same_key(r["key"], key) and r["status"] == "current"]',
                                  'if same_key(r["key"], key) and r["status"] == "current"\n'
                                  '                   and r["timestamp"] <= self.clock()]'),
    "E1-no-nfc": ('return unicodedata.normalize("NFC", x)\n', "return x\n"),
    "E2-no-control-check": ('if any(unicodedata.category(ch) in ("Cc", "Cf", "Cs") for ch in x):',
                            "if False:"),
}


def run(args, cwd):
    p = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=120)
    return p.returncode, p.stdout + p.stderr


def main():
    code, out = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], ROOT)
    count = int(re.search(r"Ran (\d+) tests?", out).group(1))
    ok_suite = code == 0 and count == 60
    src = (ROOT / "sml" / "memory.py").read_text()
    mutants = {}
    for name, (old, new) in MUTANTS.items():
        if src.count(old) != 1:
            mutants[name] = "TARGET_NOT_FOUND"
            continue
        with tempfile.TemporaryDirectory() as td:
            copy = Path(td) / "c"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns("__pycache__", ".git", "attack"))
            (copy / "sml" / "memory.py").write_text(src.replace(old, new, 1))
            c, o = run([sys.executable, "-m", "unittest", "tests.test_hardening"], copy)
            mutants[name] = "killed" if c != 0 and ("FAIL:" in o or "ERROR:" in o) else "SURVIVED"
    ok_mut = all(v == "killed" for v in mutants.values())
    print(json.dumps({"suite_tests": count, "suite_ok": ok_suite, "mutants": mutants,
                      "verdict": "PASS" if ok_suite and ok_mut else "FAIL"}, indent=1))
    sys.exit(0 if ok_suite and ok_mut else 1)


if __name__ == "__main__":
    main()
