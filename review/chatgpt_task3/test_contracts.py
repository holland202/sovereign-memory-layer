"""AI-generated (ChatGPT). Synthetic contract oracles, pinned review; no store fixes.
Run: python3 review/chatgpt_task3/test_contracts.py -v
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import sml.memory as M

TOP = 2**63 - 1
P = {'source': 'synthetic-task3', 'locator': 'original', 'sha256': hashlib.sha256(b'original').hexdigest()}
P2 = {'source': 'synthetic-task3', 'locator': 'correction', 'sha256': hashlib.sha256(b'correction').hexdigest()}
E = [1.0] + [0.0] * 383
COMMANDS = {'python': ['python3', 'tools/py_cli.py', '.'], 'rust': ['rust/target/release/sml-cli']}
RAW = Path(__file__).parent / 'raw'
RAW.mkdir(exist_ok=True)
PROTOCOL = RAW / 'contracts.protocol.jsonl'


def snapshot(d):
    return json.loads((d / 'memory.json').read_bytes())['payload']


def rewrite(d, payload):
    # Fixture envelope uses standard-library JSON, not either implementation's digest helper.
    canonical = lambda x: json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    digest = hashlib.sha256(canonical(payload)).hexdigest()
    (d / 'memory.json').write_bytes(canonical({'payload': payload, 'sha256': digest}) + b'\n')


class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sml-task3-')
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, side, d, op, **kw):
        request = dict(op=op, dir=str(d), clock=1000, **kw)
        p = subprocess.run(COMMANDS[side], cwd=ROOT, input=json.dumps(request)+'\n',
                           text=True, capture_output=True, timeout=15)
        with PROTOCOL.open('a') as f:
            f.write(json.dumps(dict(test=self.id(), side=side, command=COMMANDS[side], cwd=str(ROOT),
                                   input=request, exit=p.returncode, stdout=p.stdout, stderr=p.stderr))+'\n')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, '')
        return json.loads(p.stdout)

    def ok(self, side, d, op, **kw):
        r = self.call(side, d, op, **kw)
        self.assertTrue(r['ok'], r)
        return r['result']

    def fresh(self, side, suffix='', **kw):
        d = self.base / (side+suffix)
        self.ok(side, d, 'create', max_records=kw.get('max_records', 20), max_bytes=kw.get('max_bytes', 200000))
        return d

    def put(self, side, d, **kw):
        opts = dict(key='k', value='old', text='evidence', provenance=P, embedding=E, protected=True)
        opts.update(kw)
        return self.ok(side, d, 'put', **opts)

    def reject_unchanged(self, side, d, op, error='CapacityError', **kw):
        before = (d/'memory.json').read_bytes()
        r = self.call(side, d, op, **kw)
        self.assertEqual(r, {'ok': False, 'error': error})
        self.assertEqual((d/'memory.json').read_bytes(), before)
        self.assertFalse((d/'memory.pending').exists())

    def test_p301_create_and_persisted_counter_bounds(self):
        for side in COMMANDS:
            with self.subTest(side=side):
                d = self.fresh(side, max_records=TOP)
                self.assertEqual(self.ok(side, d, 'status')['max_records'], TOP)
                denied = self.base/(side+'-denied')
                r = self.call(side, denied, 'create', max_records=TOP+1, max_bytes=200000)
                self.assertFalse(r['ok'])
                self.assertEqual(r['error'], 'ValueError') if side=='python' else self.assertTrue(r['error'].startswith('BadOp'))
                self.assertFalse(denied.exists())
                original = snapshot(d)
                for key in ['next_id', 'generation', 'max_records', 'max_bytes']:
                    with self.subTest(counter=key):
                        state=copy.deepcopy(original);state[key]=TOP+1;rewrite(d,state)
                        self.assertEqual(self.call(side,d,'status'), {'ok':False,'error':'IntegrityError'})
                rewrite(d,original)

    def test_p301_all_mutators_at_counter_limit(self):
        # Generation covers every mutation; next_id covers both insertion paths.
        for side in COMMANDS:
            for counter, operations in [('generation', ['put','correct','revoke','compact']),
                                        ('next_id', ['put','correct'])]:
                for op in operations:
                    with self.subTest(side=side,counter=counter,op=op):
                        d=self.fresh(side,'-'+counter+'-'+op)
                        self.put(side,d,protected=False)
                        s=snapshot(d);s[counter]=TOP;rewrite(d,s)
                        args={'put':dict(key='new',value='v',provenance=P),
                              'correct':dict(id=1,value='new',provenance=P2),
                              'revoke':dict(id=1,reason='withdraw',provenance=P2),
                              'compact':dict(target=0)}[op]
                        self.reject_unchanged(side,d,op,**args)
                        for reader in COMMANDS:
                            self.assertEqual(self.ok(reader,d,'status')['records'],1)

    def test_p301_last_permitted_increment_then_refusal(self):
        for side in COMMANDS:
            with self.subTest(side=side):
                d=self.fresh(side)
                state=snapshot(d);state.update(next_id=TOP-1,generation=TOP-1);rewrite(d,state)
                self.assertEqual(self.put(side,d),TOP-1)
                state=snapshot(d)
                self.assertEqual((state['next_id'],state['generation']),(TOP,TOP))
                self.reject_unchanged(side,d,'put',key='another',value='v',provenance=P)
                for reader in COMMANDS:self.assertEqual(self.ok(reader,d,'status')['records'],1)

    def test_history_every_original_field_and_new_provenance(self):
        for side in COMMANDS:
            with self.subTest(side=side):
                d=self.fresh(side)
                self.put(side,d,timestamp=900,weight=0.25)
                original=copy.deepcopy(snapshot(d)['records'][0])
                self.assertEqual(original['timestamp'],900)
                self.assertEqual(original['provenance'],P)
                self.ok(side,d,'correct',id=1,value='new',text='new evidence',provenance=P2,embedding=E)
                expected=copy.deepcopy(original);expected['status']='superseded'
                records=snapshot(d)['records']
                self.assertEqual(records[0],expected)
                current=copy.deepcopy(records[1]);self.assertEqual(current['provenance'],P2)
                self.ok(side,d,'revoke',id=2,reason='withdraw',provenance=P)
                current.update(status='revoked',revocation=dict(at=1000.0,reason='withdraw',provenance=P))
                self.assertEqual(snapshot(d)['records'],[expected,current])
                self.assertEqual(self.ok(side,d,'recall',key='k',qembedding=E)['status'],'UNKNOWN')
                self.reject_unchanged(side,d,'compact',target=0)
                self.assertEqual(snapshot(d)['records'],[expected,current])

    def test_revoke_source_and_locator_controls(self):
        for side in COMMANDS:
            d=self.fresh(side);self.put(side,d)
            for field in ['source','locator']:
                for bad in ['a\x00b','a\nb','a\u202eb','a\u200bb']:
                    with self.subTest(side=side,field=field,bad=repr(bad)):
                        self.reject_unchanged(side,d,'revoke',error='ValueError',id=1,reason='r',provenance={**P,field:bad})

    def test_cli_exact_positive_identifiers(self):
        for side in COMMANDS:
            d=self.fresh(side);self.put(side,d)
            for invalid in [True,False,1.0,'1',None,0,-1]:
                for op in ['correct','revoke']:
                    with self.subTest(side=side,invalid=repr(invalid),op=op):
                        extra=dict(value='new') if op=='correct' else dict(reason='r')
                        self.reject_unchanged(side,d,op,error='ValueError',id=invalid,provenance=P,**extra)

    def test_checksummed_semantic_invalidity_is_integrity_error(self):
        for side in COMMANDS:
            d=self.fresh(side);self.put(side,d)
            original=snapshot(d)
            cases={'schema_bool':lambda s:s.update(schema=True),
                   'schema_float':lambda s:s.update(schema=1.0),
                   'id_bool':lambda s:s['records'][0].update(id=True),
                   'id_zero':lambda s:s['records'][0].update(id=0),
                   'bad_status':lambda s:s['records'][0].update(status='impossible'),
                   'zero_vector':lambda s:s['records'][0].update(embedding=[0.0]*384),
                   'orphan':lambda s:s['records'][0].update(status='superseded'),
                   'duplicate':lambda s:s['records'].append(copy.deepcopy(s['records'][0])),
                   'future_revocation':lambda s:s['records'][0].update(status='revoked',revocation=dict(at=0,reason='r',provenance=P))}
            for name,mutate in cases.items():
                with self.subTest(side=side,fixture=name):
                    s=copy.deepcopy(original);mutate(s);rewrite(d,s)
                    self.assertEqual(self.call(side,d,'status'),{'ok':False,'error':'IntegrityError'})
            rewrite(d,original);self.assertEqual(self.ok(side,d,'status')['records'],1)

    def test_contradiction_survives_topk_similarity_and_clock_filtering(self):
        for side in COMMANDS:
            d=self.fresh(side)
            self.put(side,d,timestamp=100)
            self.put(side,d,value='different',embedding=[0.0,1.0]+[0.0]*382,weight=0)
            # CLI clock is supplied via a direct request to avoid duplicate keyword arguments.
            req=dict(op='recall',dir=str(d),clock=500,key='k',qembedding=E,top_k=1,threshold=0.5)
            p=subprocess.run(COMMANDS[side],cwd=ROOT,input=json.dumps(req)+'\n',text=True,capture_output=True,timeout=15)
            with PROTOCOL.open('a') as f:f.write(json.dumps(dict(test=self.id(),side=side,command=COMMANDS[side],input=req,exit=p.returncode,stdout=p.stdout,stderr=p.stderr))+'\n')
            self.assertEqual(p.returncode,0,p.stderr)
            result=json.loads(p.stdout)
            self.assertEqual(result,{'ok':True,'result':dict(status='UNKNOWN',reason='contradictory_current_evidence',evidence_ids=[1,2])})

    def test_exact_byte_boundary_all_write_paths(self):
        for side in COMMANDS:
            for op in ['put','correct','revoke']:
                for spare in [0,-1]:
                    with self.subTest(side=side,op=op,spare=spare):
                        d=self.fresh(side,'-'+op+str(spare));self.put(side,d,protected=False)
                        original=snapshot(d)
                        args={'put':dict(key='another',value='new',provenance=P2,embedding=E),
                              'correct':dict(id=1,value='new',provenance=P2,embedding=E),
                              'revoke':dict(id=1,reason='r'*256,provenance=P2)}[op]
                        self.ok(side,d,op,**args)
                        proposed=snapshot(d)
                        # Solve the byte cap for this complete envelope; four-digit cap is stable.
                        cap=4096
                        for _ in range(4):
                            proposed['max_bytes']=cap;rewrite(d,proposed);cap=len((d/'memory.json').read_bytes())
                        cap+=spare
                        original['max_bytes']=cap;rewrite(d,original)
                        before=(d/'memory.json').read_bytes()
                        r=self.call(side,d,op,**args)
                        if spare==0:
                            self.assertTrue(r['ok'],r)
                            self.assertEqual((d/'memory.json').stat().st_size,cap)
                        else:
                            self.assertEqual(r,{'ok':False,'error':'CapacityError'})
                            self.assertEqual((d/'memory.json').read_bytes(),before)
                        print(json.dumps(dict(check='byte_boundary',side=side,op=op,spare=spare,cap=cap,result=r)),flush=True)

    def test_python_sigkill_other_mutators_at_commit_boundaries(self):
        for op in ['correct','revoke','compact']:
            for stage, new in [('partial_write',False),('after_file_fsync',False),('after_replace',True),('after_dir_fsync',True)]:
                with self.subTest(op=op,stage=stage):
                    d=self.base/(op+'-'+stage)
                    m=M.MemoryStore(d,create=True,clock=lambda:1000)
                    m.put('k','old',provenance=P,embedding=E)
                    before=m.path.read_bytes()
                    expected_dir=self.base/(op+'-'+stage+'-expected')
                    expected_dir.mkdir();(expected_dir/'memory.json').write_bytes(before)
                    expected=M.MemoryStore(expected_dir,clock=lambda:1000)
                    mutate=lambda store: (store.correct(1,'new',provenance=P2,embedding=E) if op=='correct' else
                                          store.revoke(1,reason='withdraw',provenance=P2) if op=='revoke' else store.compact(0))
                    mutate(expected);after=expected.path.read_bytes()
                    script="""
import os,signal,sys,json
from sml.memory import MemoryStore
stage,op=sys.argv[2:4]
def fault(s):
 if s==stage:os.kill(os.getpid(),signal.SIGKILL)
m=MemoryStore(sys.argv[1],clock=lambda:1000,fault=fault)
p=json.loads(sys.argv[4]);e=[1.0]+[0.0]*383
if op=='correct':m.correct(1,'new',provenance=p,embedding=e)
elif op=='revoke':m.revoke(1,reason='withdraw',provenance=p)
else:m.compact(0)
"""
                    r=subprocess.run(['python3','-c',script,str(d),stage,op,json.dumps(P2)],cwd=ROOT,capture_output=True,timeout=15)
                    self.assertEqual(r.returncode,-signal.SIGKILL,r.stderr)
                    self.assertEqual(m.path.read_bytes(),after if new else before)
                    M.MemoryStore(d).snapshot()
                    print(json.dumps(dict(check='python_kill',op=op,stage=stage,exit=r.returncode,new_visible=new,
                                          file_sha256=hashlib.sha256(m.path.read_bytes()).hexdigest())),flush=True)


if __name__=='__main__':
    PROTOCOL.write_text('')
    unittest.main()
