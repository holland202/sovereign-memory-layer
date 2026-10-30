import copy
import json
import unittest
from pathlib import Path
from evaluation import validate,readiness

ROOT=Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.p=json.loads((ROOT/'protocol.draft.json').read_text())

    def test_draft_valid_but_blocked(self):
        self.assertTrue(validate(self.p))
        self.assertFalse(readiness(self.p)['comparison_ready'])
        self.assertFalse(readiness(self.p)['scientific_execution_authorized'])

    def test_missing_comparator_rejected(self):
        self.p['arms'].pop()
        with self.assertRaises(ValueError):validate(self.p)

    def test_split_reuse_rejected(self):
        self.p['splits']['heldout']['ids']=self.p['splits']['development']['ids'][:1]
        with self.assertRaises(ValueError):validate(self.p)

    def test_exposed_primary_rejected(self):
        self.p['splits']['heldout']['exposed']=True
        with self.assertRaises(ValueError):validate(self.p)

    def test_heldout_projection_fit_rejected(self):
        self.p['projection']['fit_split']='heldout'
        with self.assertRaises(ValueError):validate(self.p)

    def test_invalid_resource_budgets_rejected(self):
        self.p['budgets']['max_records']=0
        with self.assertRaises(ValueError):validate(self.p)

    def test_scientific_execution_cannot_be_granted_in_file(self):
        self.p['scientific_execution_authorized']=True
        with self.assertRaises(ValueError):validate(self.p)


if __name__=='__main__':unittest.main()
