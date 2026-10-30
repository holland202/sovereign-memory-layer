#!/usr/bin/env python3
"""Verify the SML-ATK-001 hardening. Standard library only; never runs a scientific comparison.

1. The full suite passes: 51 earlier tests (42 original + 9 identifier) + 9 round-1 hardening tests
   + 9 round-2 tests + 4 EXT-01 tests + 3 round-3 tests + 3 P3-01 tests = 79.
2. Each fix is load-bearing: removing it (one mutant per fix) makes the hardening tests fail.
   (The commit-side READ_LIMIT guard is defence in depth: _commit validates first, and validation already
   bounds max_bytes, so no test can reach it and it has no mutant.)
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
    "R2-01-recall-key-unchecked": ("if not isinstance(key, str) or not key.strip():  # R2-01",
                                   "if False:  # R2-01"),
    "R2-02-no-reentrancy-guard": ("if me in held:  # R2-02", "if False:  # R2-02"),
    "R2-03-revoke-old-provenance-check": ("p = new_provenance(provenance)  # R2-03",
                                          "p = validate_provenance(provenance)  # R2-03"),
    "R2-04-exact-key-link-check": ('not same_key(by_id[target]["key"], r["key"]) or target in referenced',
                                   'by_id[target]["key"] != r["key"] or target in referenced'),
    "R2-05-no-stored-max-bytes-range": ('if not 1024 <= s["max_bytes"] <= READ_LIMIT:  # R2-05', 'if False:  # R2-05'),
    "M1-schema-type-unchecked": ('or type(s["schema"]) is not int or s["schema"] != 1:  # M1', 'or s["schema"] != 1:  # M1'),
    "EXT01-N1-no-early-byte-refusal": ('if len(self._encode(s)) + floor > s["max_bytes"]:  # EXT-01: early byte refusal',
                                       'if False:  # EXT-01: early byte refusal'),
    "EXT01-N3-flock-error-unwrapped": ("            except OSError as e:  # EXT-01 N3", "            except ZeroDivisionError as e:  # EXT-01 N3"),
    "R3-02-inexact-integers-accepted": ("(type(x) is int and f != x) or not low", "False or not low"),
    "EXT01-N4-unlock-error-escapes": ("                except OSError:  # EXT-01 N4", "                except ZeroDivisionError:  # EXT-01 N4"),
    "P3-01-create-unbounded": ("not 1 <= max_records <= MAX_COUNTER:  # P3-01", "max_records < 1:  # P3-01"),
    "P3-01-read-unbounded": ('not (0 if k == "generation" else 1) <= s[k] <= MAX_COUNTER:  # P3-01',
                             's[k] < (0 if k == "generation" else 1):  # P3-01'),
    "P3-01-bump-unchecked": ("    if s[k] >= MAX_COUNTER:\n", "    if False:\n"),
}


def run(args, cwd):
    p = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=120)
    return p.returncode, p.stdout + p.stderr


def deep_nesting_raises_recursion():
    """A1's defect needs json to raise RecursionError on deep nesting. Some interpreters do not
    (CPython 3.14.9 on GitHub's runners, found by CI 2026-10-30; but 3.14.6 on Termux/Android does),
    so this is probed at run time; where it cannot happen the A1 mutant cannot be killed: n/a."""
    import json as _json
    try:
        _json.loads("[" * 100_000 + "]" * 100_000)
    except RecursionError:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


def main():
    code, out = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], ROOT)
    count = int(re.search(r"Ran (\d+) tests?", out).group(1))
    ok_suite = code == 0 and count == 79
    src = (ROOT / "sml" / "memory.py").read_text()
    mutants = {}
    for name, (old, new) in MUTANTS.items():
        if src.count(old) != 1:
            mutants[name] = "TARGET_NOT_FOUND"
            continue
        with tempfile.TemporaryDirectory() as td:
            copy = Path(td) / "c"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns("__pycache__", ".git", "attack", "target"))
            (copy / "sml" / "memory.py").write_text(src.replace(old, new, 1))
            c, o = run([sys.executable, "-m", "unittest", "tests.test_hardening", "tests.test_hardening_round2",
                         "tests.test_ext01", "tests.test_round3", "tests.test_p3_01"], copy)
            mutants[name] = "killed" if c != 0 and ("FAIL:" in o or "ERROR:" in o) else "SURVIVED"
    if not deep_nesting_raises_recursion() and mutants.get("A1-recursion-not-caught") == "SURVIVED":
        mutants["A1-recursion-not-caught"] = f"n/a on Python {sys.version.split()[0]} (json does not raise RecursionError)"
    ok_mut = all(v == "killed" or v.startswith("n/a") for v in mutants.values())
    print(json.dumps({"suite_tests": count, "suite_ok": ok_suite, "mutants": mutants,
                      "verdict": "PASS" if ok_suite and ok_mut else "FAIL"}, indent=1))
    sys.exit(0 if ok_suite and ok_mut else 1)


if __name__ == "__main__":
    main()
