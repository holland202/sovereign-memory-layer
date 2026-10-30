"""Strict public identifier contract. Exposed synthetic engineering fixtures."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from sml.memory import MemoryStore


P={'source':'synthetic-identifier-regression','locator':'fixture-1',
   'sha256':hashlib.sha256(b'synthetic-identifier-regression').hexdigest()}


class IdentifierRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.directory=Path(self.tmp.name)/'memory'
        self.m=MemoryStore(self.directory,create=True,clock=lambda:1000)
        self.i=self.m.put('fixture.color','blue',provenance=P,protected=True)

    def tearDown(self):self.tmp.cleanup()

    def reject_without_mutation(self,identifiers):
        for identifier in identifiers:
            for operation in ('correct','revoke'):
                with self.subTest(identifier=repr(identifier),operation=operation):
                    before=self.m.path.read_bytes()
                    with self.assertRaises(ValueError):
                        if operation=='correct':self.m.correct(identifier,'green',provenance=P)
                        else:self.m.revoke(identifier,reason='synthetic withdrawal',provenance=P)
                    self.assertEqual(self.m.path.read_bytes(),before)
                    self.assertEqual(self.m.snapshot()['records'][0]['status'],'current')
                    self.assertFalse(self.m.storage_status()['incomplete_storage_detected'])

    def test_boolean_identifiers_rejected(self):
        self.reject_without_mutation([True,False])

    def test_float_and_nonfinite_identifiers_rejected(self):
        self.reject_without_mutation([1.0,0.0,-1.0,float('nan'),float('inf'),float('-inf')])

    def test_string_none_and_complex_identifiers_rejected(self):
        self.reject_without_mutation(['1','01','',None,1+0j])

    def test_int_subclasses_rejected_by_exact_integer_contract(self):
        class Alias(int):pass
        self.reject_without_mutation([Alias(1)])

    def test_nonpositive_integer_identifiers_rejected(self):
        self.reject_without_mutation([0,-1,-100])

    def test_valid_integer_correction_preserves_protected_history(self):
        new=self.m.correct(self.i,'green',provenance=P)
        records=MemoryStore(self.directory).snapshot()['records']
        self.assertEqual(new,2)
        self.assertEqual((records[0]['value'],records[0]['status'],records[0]['protected']),('blue','superseded',True))
        self.assertEqual((records[1]['value'],records[1]['supersedes']),('green',1))

    def test_valid_integer_revocation_preserves_original_record(self):
        self.m.revoke(self.i,reason='synthetic withdrawal',provenance=P)
        record=MemoryStore(self.directory).snapshot()['records'][0]
        self.assertEqual((record['id'],record['value'],record['status'],record['protected']),(1,'blue','revoked',True))
        self.assertEqual(record['revocation']['provenance'],P)

    def test_unknown_positive_identifier_does_not_mutate_state(self):
        self.reject_without_mutation([999])

    def test_successful_revocation_cannot_be_repeated(self):
        self.m.revoke(self.i,reason='synthetic withdrawal',provenance=P)
        before=self.m.path.read_bytes()
        with self.assertRaises(ValueError):self.m.revoke(self.i,reason='again',provenance=P)
        self.assertEqual(before,self.m.path.read_bytes())


if __name__=='__main__':unittest.main()
