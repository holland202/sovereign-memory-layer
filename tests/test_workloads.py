import copy
import unittest
from workloads import development_cases,oracle


class OracleTests(unittest.TestCase):
    def setUp(self):self.cases={c['family']:c for c in development_cases()}

    def test_exposed_cases_cover_all_eight_families(self):
        self.assertEqual(len(self.cases),8)
        self.assertTrue(all(c['split']=='development' and c['participant_seen'] for c in self.cases.values()))

    def test_exact_update_oracle(self):
        r=oracle(self.cases['updates'])
        self.assertEqual((r['status'],r['value'],r['gold_ids']),('KNOWN','green',['m2']))

    def test_conflict_absence_and_corruption_oracles(self):
        self.assertEqual(oracle(self.cases['contradictions'])['status'],'UNKNOWN')
        self.assertEqual(oracle(self.cases['absent_evidence'])['status'],'UNKNOWN')
        self.assertEqual(oracle(self.cases['corrupt_storage'])['status'],'STORAGE_ERROR')

    def test_restart_does_not_change_reference_world(self):
        self.assertEqual(oracle(self.cases['multisession_exact'])['value'],'SYNTH-041')

    def test_revocation_and_invalid_correction(self):
        c=self.cases['updates'];c['events'].append({'op':'revoke','target':'m2'})
        self.assertEqual(oracle(c)['status'],'UNKNOWN')
        c=self.cases['earlier_failures'];c['events'][1]['supersedes']='m1'
        with self.assertRaises(ValueError):oracle(c)

    def test_primary_cannot_be_silently_generated_or_scored(self):
        c=self.cases['updates'];c['split']='heldout';c['participant_seen']=False
        with self.assertRaises(ValueError):oracle(c)
