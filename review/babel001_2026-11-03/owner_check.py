#!/usr/bin/env python3
"""BABEL-001 owner-side receipt check. Standard library only; read-only.

Run from the root of a sovereign-memory-layer clone (any branch; pinned objects
are read with `git show`, the working tree is never touched):

    python3 review/babel001_2026-11-03/owner_check.py            # receipts vs pinned commit
    python3 review/babel001_2026-11-03/owner_check.py --baseline # also regenerate the baseline

Checks, each printed as OK or FAIL (exit 1 on any FAIL):
  C1  every published receipt matches REDACTED_SHA256SUMS.txt
  C2  the run names the pinned commit (source-head.txt, integrity report)
  C3  run start is after the recorded preregistration freeze
  C4  the tester's SML source hashes equal `git show f4fc1de:sml/*` here
  C5  rebuilding the one-line contradiction mutant from the pinned memory.py
      gives the mutant SHA-256 the tester's control recorded
  C6  all 10 registered cases and the separate control are PASS; exit codes 0
  C7  (--baseline) manifest check + verify_hardened.py at the pinned commit,
      regenerated here, is byte-identical to the tester's baseline.stdout

C1-C6 check consistency of the tester's receipts with the pinned source; they
do not re-execute the BABEL cases. Times come from the tester's machine clock.
"""
import hashlib, json, pathlib, subprocess, sys, tempfile

PIN = "f4fc1de7c9a1d55b800dbfe09388c66b357b1f0b"
FREEZE_UTC = "2026-11-03T16:21:12"   # from the freeze receipt in receipts/freeze/
HERE = pathlib.Path(__file__).resolve().parent
RUN = HERE / "receipts" / "runs" / "20261103T162847Z"
OLD = b'        if len({r["value"] for r in current}) > 1:  # MUTATION: contradiction\n'
NEW = b'        if False:  # NEGATIVE CONTROL: disabled contradiction gate\n'
failures = []


def check(name, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(name)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args])


def main():
    sums = (HERE / "REDACTED_SHA256SUMS.txt").read_text().splitlines()
    bad = [p for h, p in (l.split("  ", 1) for l in sums) if sha((HERE / p).read_bytes()) != h]
    check("C1 receipts match REDACTED_SHA256SUMS.txt", not bad and len(sums) == 31,
          f"{len(sums)} files" + (f"; mismatched: {bad}" if bad else ""))

    integ = json.loads((RUN / "post_execution_integrity.json").read_text())
    head = (RUN / "source-head.txt").read_text().strip()
    check("C2 run names the pinned commit", head == PIN and integ["head"] == PIN and integ["integrity_ok"] is True)

    start = (RUN / "start_utc.txt").read_text().strip()
    check("C3 run started after the freeze", start > FREEZE_UTC, f"freeze {FREEZE_UTC}Z, start {start}")

    mism = [f for f, v in integ["source"].items() if sha(git("show", f"{PIN}:{f}")) != v["actual"]]
    check("C4 tester's SML source hashes equal the pinned objects here", not mism, ", ".join(integ["source"]))

    control = json.loads((RUN / "CONTROL_RESULTS.json").read_text())["cases"][0]
    src = git("show", f"{PIN}:sml/memory.py")
    rebuilt = sha(src.replace(OLD, NEW))
    check("C5 rebuilt mutant hash equals the control's recorded mutant",
          src.count(OLD) == 1 and rebuilt == control["mutation"]["mutant_sha256"], rebuilt[:16])

    cases = json.loads((RUN / "BABEL001_RESULTS.json").read_text())["cases"]
    exits = [(RUN / f).read_text().strip() for f in ("BABEL001_EXIT.txt", "CONTROL_EXIT.txt", "baseline.exit")]
    check("C6 10/10 cases PASS, control PASS, exit codes 0",
          len(cases) == 10 and all(c["verdict"] == "PASS" for c in cases)
          and control["verdict"] == "PASS" and exits == ["0", "0", "0"],
          " ".join(f'{c["id"][-2:]}:{c["verdict"]}' for c in cases) + f" control:{control['verdict']}")

    if "--baseline" in sys.argv:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(f"git archive {PIN} | tar -x -C {tmp}", shell=True, check=True)
            out = subprocess.run("sha256sum -c MANIFEST_HARDENED.sha256 2>/dev/null || shasum -a 256 -c MANIFEST_HARDENED.sha256;"
                                 f" PYTHONDONTWRITEBYTECODE=1 {sys.executable} verify_hardened.py",
                                 shell=True, cwd=tmp, capture_output=True).stdout
        check("C7 regenerated baseline is byte-identical to the tester's", out == (RUN / "baseline.stdout").read_bytes(),
              sha(out)[:16])

    print("\nRESULT:", "PASS" if not failures else "FAIL " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
