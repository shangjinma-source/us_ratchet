import copy
import hashlib
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_bad_tail_five_input_projection_20260923 as module


class ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = {}
        for role, (relative, digest) in module.BOUND.items():
            raw = (module.BASE / relative).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest: raise ValueError('Hard fixture source differs')
            cls.docs[role] = json.loads(raw)

    def test_exact_subset_and_no_parent_mutation(self):
        before = copy.deepcopy(self.docs)
        result = module.project(self.docs)
        self.assertEqual(self.docs, before)
        self.assertEqual(result['security_count'], 5)
        self.assertEqual(len(result['calendar']), 107)
        self.assertEqual(len(result['saved_lane_choices']), 6)
        self.assertEqual(result['price_projection']['price_cell_count'], 1070)
        for kind in ('open', 'close'):
            for day, values in result['price_projection']['matrices'][kind].items():
                for ticker, value in values.items(): self.assertEqual(value, self.docs['price']['matrices'][kind][day][ticker])
        self.assertTrue(all(result[key] is False for key in module.FALSE))
        self.assertFalse(result['identity_projection']['parent_schedule_binding_reused_as_bad_tail_admission'])
        result['identity_projection']['rows'][0]['ticker'] = 'CHANGED'
        self.assertEqual(self.docs, before)

    def test_wrong_clock_and_missing_price_day_rejected(self):
        for change in ('clock', 'price'):
            docs = copy.deepcopy(self.docs)
            if change == 'clock': docs['lane_prepare']['decisions'][0]['execution_date'] = '2023-04-04'
            else: docs['price']['matrices']['open'].pop('2023-04-03')
            with self.subTest(change=change), self.assertRaises(ValueError): module.project(docs)

    def test_selected_may_map_does_not_claim_complete_execution_chains(self):
        result = module.project(self.docs)
        ftnt = 'security:0001262039:34959E109'
        self.assertIn(ftnt, result['selected_risk_chains_by_decision']['2023-03-31'])
        self.assertNotIn(ftnt, result['selected_risk_chains_by_decision']['2023-04-28'])
        self.assertNotIn('risk_chains_by_decision', result)
        self.assertIs(result['execution_risk_chain_union_verified'], False)

    def test_risk_chain_and_issuer_tamper_rejected(self):
        for field in ('risk_chain', 'issuer_id'):
            docs = copy.deepcopy(self.docs)
            row = next(iter(docs['lane_prepare']['decisions'][0]['lanes']['BAD_TAIL'][0]['selected'].values()))
            row[field] = 'WRONG'
            with self.subTest(field=field), self.assertRaises(ValueError): module.project(docs)

    def test_parent_window_or_permission_upgrade_rejected(self):
        for change in ('window', 'permission', 'target'):
            docs = copy.deepcopy(self.docs)
            if change == 'window': docs['identity']['conditional_window']['end'] = '2023-10-01'
            elif change == 'permission': docs['identity']['promotion_allowed'] = True
            else: docs['lane_prepare']['continuous_target_schedule_built'] = True
            with self.subTest(change=change), self.assertRaises(ValueError): module.project(docs)

    def test_duplicate_choice_and_non_decimal_price_rejected(self):
        for change in ('choice', 'number'):
            docs = copy.deepcopy(self.docs)
            if change == 'choice': docs['lane_prepare']['decisions'][0]['lanes']['BAD_TAIL'] *= 2
            else: docs['price']['matrices']['open']['2023-03-31']['AMAT'] = 1.0
            with self.subTest(change=change), self.assertRaises(ValueError): module.project(docs)

    def test_publish_existing_namespace_stops_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(module, 'OUTPUT', Path(directory) / 'projection.json'), patch.object(module, 'build') as build:
                with self.assertRaises(ValueError): module.publish()
                build.assert_not_called()


if __name__ == '__main__': unittest.main()
