#!/bin/bash
# A1-STACK harness, run as committed. Prints one line per registered case.
P314=$(uv python find 3.14.6 2>/dev/null)
P313=$(command -v python3)
H=$(dirname "$0")
case_() { # label, stack KiB, python, args...
  local label=$1 st=$2 py=$3; shift 3
  out=$(bash -c "ulimit -s $st; exec \"$py\" $*" 2>&1); rc=$?
  [ $rc -ge 128 ] && out="OUTCOME=crash(signal $((rc-128)))"
  echo "$label stack=${st}KiB rc=$rc :: $(echo "$out" | tail -1)"
}
echo "host: $(uname -m) $(uname -s); default ulimit -s: $(ulimit -s)"
case_ P1 8192 "$P314" "$H/probe.py" 100000
case_ P2 512  "$P314" "$H/probe.py" 100000
case_ P3 8192 "$P313" "$H/probe.py" 100000
cd "$H/../.."
out=$("$P314" -m unittest tests.test_hardening.HardeningTests.test_a1_deeply_nested_file_is_integrity_error 2>&1); echo "P4 stack=8192KiB rc=$? :: $(echo "$out" | tail -1)"
out=$(bash -c "ulimit -s 512; exec \"$P314\" verify_hardened.py" 2>&1); rc=$?
echo "P5 stack=512KiB rc=$rc :: A1=$(echo "$out" | grep -o '"A1-recursion-not-caught": "[^"]*"') verdict=$(echo "$out" | grep -o '"verdict": "[A-Z]*"')"
