"""Validate isolated identifier fix; never runs a scientific comparison."""
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent


def run_command(args,cwd):
    p=subprocess.run(args,cwd=cwd,text=True,capture_output=True,timeout=30)
    return {'command':args,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}


def main():
    provenance=json.loads((ROOT/'ORIGIN.json').read_text())
    source=(ROOT/'sml/memory.py').read_text()
    if hashlib.sha256(source.encode()).hexdigest()!=provenance['expected_candidate_memory_sha256']:
        raise ValueError('candidate differs from the previously reviewed patch')
    if hashlib.sha256((ROOT/'originals/SML_REVIEW_2026-10-29.zip').read_bytes()).hexdigest()!=provenance['original_archive_sha256']:
        raise ValueError('original archive changed')
    results=[]
    suite=run_command([sys.executable,'-m','unittest','discover','-s','tests','-v'],ROOT)
    if suite['returncode']!=0:raise RuntimeError(suite)
    count=int(re.search(r'Ran (\d+) tests?',suite['stderr']).group(1))
    if count!=51:raise ValueError('expected 42 original plus 9 regression tests')
    results.append({'label':'candidate-complete-suite','tests':count,**suite})
    declaration='    def revoke(self, record_id, *, reason, provenance):\n'
    guard='        if type(record_id) is not int or record_id < 1:\n            raise ValueError("positive integer record ID required")\n'
    target=declaration+guard
    if source.count(target)!=1:raise ValueError('mutation target mismatch')
    mutations=[('remove-revocation-guard',declaration),
               ('accept-boolean-subclass',declaration+'        if not isinstance(record_id, int) or record_id < 1:\n            raise ValueError("positive integer record ID required")\n')]
    for label,replacement in mutations:
        with tempfile.TemporaryDirectory() as td:
            candidate=Path(td)/'candidate'
            shutil.copytree(ROOT,candidate,ignore=shutil.ignore_patterns('__pycache__','evidence','originals'))
            defective=source.replace(target,replacement,1)
            (candidate/'sml/memory.py').write_text(defective)
            probe=run_command([sys.executable,'-m','unittest','discover','-s','tests','-p','test_identifier_regression.py','-v'],candidate)
            if probe['returncode']!=1 or 'FAIL:' not in probe['stderr']:raise RuntimeError(probe)
            results.append({'label':label,'mutant_detected':True,'mutated_source_sha256':hashlib.sha256(defective.encode()).hexdigest(),**probe})
    report={'scope':'ENGINEERING_ONLY_ISOLATED_CANDIDATE','scientific_campaigns_executed':False,
            'original_archive_modified':False,'external_independent_review_completed':False,
            'environment':{'python':sys.version,'platform':platform.platform(),'dependencies':'standard library only'},
            'original_memory_sha256':provenance['original_memory_source_sha256'],
            'candidate_memory_sha256':hashlib.sha256(source.encode()).hexdigest(),'results':results}
    (ROOT/'evidence').mkdir(exist_ok=True)
    (ROOT/'evidence/candidate_validation.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'tests_passed':count,'new_regression_tests':9,'additional_mutants_detected':2,'scientific_campaigns_executed':False}))


if __name__=='__main__':main()
