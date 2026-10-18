import copy
import hashlib
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_return_eight_conditional_identity_20260923 as reader


class IndependentIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = {}
        for role, (relative, expected) in reader.BOUND.items():
            raw = (reader.BASE / relative).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError('Hard source differs')
            cls.docs[role] = json.loads(raw)

    def test_real_eight_securities_seven_issuers_and_no_admission(self):
        value = reader.assemble(self.docs)
        self.assertEqual((value['security_count'], value['distinct_issuer_count']), (8, 7))
        for flag in ('early_evidence_availability_inferred', 'continuous_identity_interval_verified',
                     'provider_price_binding_verified', 'order_generation_allowed', 'promotion_allowed'):
            self.assertIs(value[flag], False)

    def test_class_swap_rejected(self):
        docs = copy.deepcopy(self.docs)
        row = next(r for r in docs['new']['rows'] if r['ticker'] == 'GOOGL')
        row['parsed_original_cover']['security_class_title'] = 'Class C Capital Stock'
        with self.assertRaises(ValueError): reader.assemble(docs)

    def test_same_issuer_two_classes_in_one_decision_rejected(self):
        docs = copy.deepcopy(self.docs)
        source = next(d for d in docs['schedule']['schedule'] if any(v['ticker'] == 'GOOGL' for v in d['targets'].values()))
        sid, target = next((s, t) for s, t in source['targets'].items() if t['ticker'] == 'GOOGL')
        destination = next(d for d in docs['schedule']['schedule'] if any(v['ticker'] == 'GOOG' for v in d['targets'].values()))
        destination['targets'][sid] = copy.deepcopy(target)
        with self.assertRaises(ValueError): reader.assemble(docs)

    def test_old_window_or_permission_upgrade_rejected(self):
        for change in ('window', 'permission'):
            docs = copy.deepcopy(self.docs)
            if change == 'window': docs['seven']['conditional_window']['end'] = '2023-09-01'
            else: docs['new']['promotion_allowed'] = True
            with self.subTest(change=change), self.assertRaises(ValueError): reader.assemble(docs)

    def test_shifted_decision_outside_new_window_rejected(self):
        docs = copy.deepcopy(self.docs)
        docs['schedule']['schedule'][-1]['execution_date'] = '2023-09-05'
        with self.assertRaises(ValueError): reader.assemble(docs)

    def test_drift_fails_before_assembly(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for role, (relative, _) in reader.BOUND.items():
                path = base / relative; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((reader.BASE / relative).read_bytes() + b' ')
            with patch.object(reader, 'BASE', base), self.assertRaises(ValueError): reader.build()


if __name__ == '__main__': unittest.main()
