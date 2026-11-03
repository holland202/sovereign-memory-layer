# FUTURE ONLY: run in a fresh bash shell after final approval and recorded freeze.
set -euo pipefail
# In this fresh shell, remove inherited Git path/config overrides. Use Git's
# optional-lock suppression so read-only inspection does not refresh the index.
for var in ${!GIT_@}; do unset "$var"; done
export GIT_OPTIONAL_LOCKS=0
git_read() { git --no-optional-locks --no-replace-objects --no-lazy-fetch -c core.fsmonitor=false "$@"; }
ROOT="$HOME/Research/SML-BABEL001"
REPO="$ROOT/sovereign-memory-layer"
CANDIDATE="$ROOT/freezes/BABEL-001-20261103T162112Z-5056af8278e8"
MANIFEST="$CANDIDATE/CANDIDATE_SHA256SUMS.txt"
PIN=f4fc1de7c9a1d55b800dbfe09388c66b357b1f0b
APPROVED_MANIFEST_SHA256='5056af8278e8acc25ee61f01827e412dffe2494f8e67d83a66632aad52e085ac'
RUN="$(mktemp -d "$ROOT/BABEL001-run.XXXXXXXX")" || { printf 'Cannot create run receipt directory\n' >&2; exit 1; }

not_run() {
  trap - EXIT
  python3 - "$RUN/NOT_RUN.json" "$1" <<'PY'
import json, sys
path, reason = sys.argv[1:]
cases = [{'id': f'BABEL-{i:02}', 'verdict': 'NOT RUN', 'reason': reason}
         for i in range(1, 11)]
cases.append({'id': 'INDEPENDENT-CONTRADICTION-CONTROL',
              'verdict': 'NOT RUN', 'reason': reason})
with open(path, 'x', encoding='utf-8') as out:
    json.dump({'cases': cases}, out, indent=2)
    out.write('\n')
PY
  printf '%s\n' "$1" >&2
  exit 1
}
incomplete() {
  # Preserve any completed per-case receipts; overall validity is unresolved.
  python3 - "$RUN" "$1" <<'PY'
import json, pathlib, sys
root, reason = pathlib.Path(sys.argv[1]), sys.argv[2]
def read_json(name):
    try:
        return json.loads((root / name).read_text())
    except (OSError, ValueError):
        return None
case_report = read_json('BABEL001_RESULTS.json') or read_json('BABEL001_STDOUT.txt')
control_report = (read_json('CONTROL_RESULTS.json') or read_json('CONTROL_NOT_RUN.json')
                  or read_json('CONTROL_STDOUT.txt'))
cases = case_report.get('cases') if isinstance(case_report, dict) else None
if not isinstance(cases, list) or len(cases) != 10:
    cases = [{'id': f'BABEL-{i:02}', 'verdict': 'NOT RUN',
              'reason': 'No complete case receipt available'} for i in range(1, 11)]
control = None
if isinstance(control_report, dict):
    control = (control_report.get('cases') or [control_report])[0]
if not isinstance(control, dict) or control.get('verdict') not in ('PASS', 'FAIL', 'NOT RUN'):
    control = {'id': 'INDEPENDENT-CONTRADICTION-CONTROL', 'verdict': 'NOT RUN',
               'reason': 'No complete control receipt available'}
with open(root / 'EXECUTION_INCOMPLETE.json', 'x', encoding='utf-8') as out:
    json.dump({'overall_validity': 'NOT RUN', 'reason': reason,
               'prior_case_observations': cases, 'prior_control_observation': control}, out, indent=2)
    out.write('\n')
PY
}
stage=before_babel
trap 'code=$?; trap - EXIT; if [[ "$code" -ne 0 ]]; then if [[ "$stage" == before_babel ]]; then not_run "Pre-BABEL execution incomplete (exit $code)"; else incomplete "Execution or final checks incomplete (exit $code); prior observations require adjudication"; fi; fi' EXIT
mkdir "$RUN/tmp" "$RUN/baseline-checkout" "$RUN/source-checks"

# Verify the approved manifest identity and every listed file before importing
# candidate helpers. This candidate's current manifest is NOT an approval.
cp "$MANIFEST" "$RUN/approved_manifest.sha256"
printf '%s\n' "$APPROVED_MANIFEST_SHA256" >"$RUN/expected-manifest.sha256"
[[ "$APPROVED_MANIFEST_SHA256" =~ ^[0-9a-f]{64}$ ]] || not_run 'Missing approved freeze digest'
ACTUAL_MANIFEST_SHA256="$(shasum -a 256 "$MANIFEST" | awk '{print $1}')" || not_run 'Cannot hash manifest'
printf '%s\n' "$ACTUAL_MANIFEST_SHA256" >"$RUN/observed-manifest.sha256"
[[ "$ACTUAL_MANIFEST_SHA256" == "$APPROVED_MANIFEST_SHA256" ]] || not_run 'Approved manifest digest mismatch'
cp "$CANDIDATE/RUN_COMMANDS.md" "$RUN/approved_commands.md"
(cd "$CANDIDATE" && shasum -a 256 -c "$MANIFEST") >"$RUN/candidate-check.stdout" 2>"$RUN/candidate-check.stderr" || not_run 'Candidate input checksum mismatch'

# Record environment and verify the exact target revision and source bytes.
date -u '+%Y-%m-%dT%H:%M:%SZ' >"$RUN/start_utc.txt"
python3 --version >"$RUN/python-version.txt" 2>&1
uname -a >"$RUN/platform.txt"
git_read -C "$REPO" rev-parse HEAD >"$RUN/source-head.txt" || not_run 'Cannot read source revision'
[[ "$(cat "$RUN/source-head.txt")" == "$PIN" ]] || not_run 'Wrong source revision'
git_read -C "$REPO" status --porcelain=v1 --untracked-files=all >"$RUN/source-status-before.txt" || not_run 'Cannot inspect source status'
[[ ! -s "$RUN/source-status-before.txt" ]] || not_run 'Source checkout is not clean'
for file in sml/__init__.py sml/memory.py sml/policies.py; do
  name="${file//\//_}"
  git_read -C "$REPO" show "$PIN:$file" >"$RUN/source-checks/$name" || not_run "Cannot inspect pinned $file"
  cmp -s "$REPO/$file" "$RUN/source-checks/$name" || not_run "Source bytes differ: $file"
done
shasum -a 256 "$RUN"/source-checks/* >"$RUN/source-checks.sha256"

# Owner baseline: a clean archive, not the original working tree.
git_read -C "$REPO" archive "$PIN" | tar -x -C "$RUN/baseline-checkout" || not_run 'Cannot create pinned baseline copy'
PYTHONHOME= PYTHONPATH= python3 -m venv --without-pip "$RUN/baseline-venv" || not_run 'Cannot create isolated baseline environment'
BASEPY="$RUN/baseline-venv/bin/python"
# Reject a global package shadowing the baseline's tests namespace.
(cd "$RUN/baseline-checkout" &&
 PYTHONHOME= PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONPATH= "$BASEPY" - <<'PY'
import importlib.util, pathlib
root = pathlib.Path.cwd().resolve()
for name in ('tests.test_hardening', 'tests.test_hardening_round2', 'tests.test_ext01',
             'tests.test_round3', 'tests.test_p3_01'):
    spec = importlib.util.find_spec(name)
    expected = root / (name.replace('.', '/') + '.py')
    if spec is None or spec.origin is None or pathlib.Path(spec.origin).resolve() != expected:
        raise SystemExit(f'unexpected test import for {name}: {spec}')
    print(name, spec.origin)
PY
) >"$RUN/baseline-imports.stdout" 2>"$RUN/baseline-imports.stderr" || not_run 'Baseline test import provenance failed'
if (cd "$RUN/baseline-checkout" &&
    shasum -a 256 -c MANIFEST_HARDENED.sha256 &&
    TMPDIR="$RUN/tmp" PYTHONHOME= PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONPATH= "$BASEPY" verify_hardened.py
   ) >"$RUN/baseline.stdout" 2>"$RUN/baseline.stderr"; then
  printf '0\n' >"$RUN/baseline.exit"
else
  code=$?
  printf '%s\n' "$code" >"$RUN/baseline.exit"
  not_run 'Baseline or baseline manifest check failed; BABEL and control not run'
fi

# Ten cases, then the separate control. Both recheck the manifest, source,
# import identity and final source state. Output names must not already exist.
stage=babel_or_later
set +e
TMPDIR="$RUN/tmp" python3 -I -S -B "$CANDIDATE/babel001_run.py" \
  --repo "$REPO" --manifest "$MANIFEST" --manifest-sha256 "$APPROVED_MANIFEST_SHA256" \
  --output "$RUN/BABEL001_RESULTS.json" >"$RUN/BABEL001_STDOUT.txt" 2>"$RUN/BABEL001_STDERR.txt"
babel_exit=$?
if [[ "$babel_exit" -eq 130 ]]; then
  python3 - "$RUN/CONTROL_NOT_RUN.json" <<'PY'
import json, sys
with open(sys.argv[1], 'x', encoding='utf-8') as out:
    json.dump({'id': 'INDEPENDENT-CONTRADICTION-CONTROL', 'verdict': 'NOT RUN',
               'reason': 'BABEL execution was interrupted'}, out, indent=2)
    out.write('\n')
PY
  control_report_exit=$?
  if [[ "$control_report_exit" -ne 0 ]]; then printf 'Could not record interrupted control status\n' >&2; set -e; false; fi
  control_exit=130
else
  TMPDIR="$RUN/tmp" python3 -I -S -B "$CANDIDATE/negative_control.py" \
    --repo "$REPO" --manifest "$MANIFEST" --manifest-sha256 "$APPROVED_MANIFEST_SHA256" \
    --output "$RUN/CONTROL_RESULTS.json" >"$RUN/CONTROL_STDOUT.txt" 2>"$RUN/CONTROL_STDERR.txt"
  control_exit=$?
fi
set -e
printf '%s\n' "$babel_exit" >"$RUN/BABEL001_EXIT.txt"
printf '%s\n' "$control_exit" >"$RUN/CONTROL_EXIT.txt"
git_read -C "$REPO" status --porcelain=v1 --untracked-files=all >"$RUN/source-status-after.txt"
[[ ! -s "$RUN/source-status-after.txt" ]] || { printf 'Target checkout changed; run is incomplete\n' >&2; false; }
date -u '+%Y-%m-%dT%H:%M:%SZ' >"$RUN/end_utc.txt"
printf 'Raw receipts: %s\n' "$RUN"
trap - EXIT
if [[ "$babel_exit" -ne 0 || "$control_exit" -ne 0 ]]; then exit 1; fi
