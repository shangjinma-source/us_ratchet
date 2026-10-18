from copy import deepcopy
import unittest
import test_ndx_registered_scoring_selector_adapter_research as author
from backtest import ndx_registered_scoring_selector_adapter_research as m
from backtest import ndx_full_ndx_multidecision_selector_research as selector


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.args = author.fixture()

    def test_last_missing_is_not_cash_or_partial_winner(self):
        a = deepcopy(self.args)
        original = deepcopy(a)
        out = m.assemble_registered_selector_inputs(**a)
        self.assertEqual(a, original)
        self.assertEqual(out['logical_task_count'], 36)
        last = a['projections'][-1]
        last.update(outcome='UNDISPATCHED', score=None, inspection=None,
                    score_reference=None, inspection_reference=None,
                    error={'reason': 'explicit saved undispatched partition'})
        out = m.assemble_registered_selector_inputs(**a)
        self.assertEqual(out['logical_task_count'], 36)
        self.assertEqual(out['nonrankable_task_count'], 1)
        self.assertIsNone(out['records'][-1]['result'])
        selected = selector.select_full_ndx_lanes(registration=out['registration'], records=out['records'])
        self.assertTrue(all(x['status'] == 'INPUT_INVALID' and x['selected'] is None
                            for x in selected['rows'][-1]['choices']))
        self.assertTrue(all(x['status'] == 'SOURCE_BLOCKED'
                            for x in selected['rows'][0]['choices']))
        a['projections'].pop()
        with self.assertRaises(ValueError): m.assemble_registered_selector_inputs(**a)

    def test_exact_metric_schema_not_arbitrary_seventeen_keys(self):
        a = deepcopy(self.args)
        p = next(x for x in a['projections'] if x['outcome'] == m.SUCCESS)
        metrics = p['score']['metrics']
        key = next(k for k in metrics if k not in m.METRICS)
        metrics['unrelated_metric'] = metrics.pop(key)
        self.assertEqual(len(metrics), 17)
        with self.assertRaises(ValueError): m.assemble_registered_selector_inputs(**a)

    def test_real_locator_causal_boundary_and_authority_types(self):
        for attack in ('journal_span', 'journal_stage', 'last_window', 'audit_flag', 'risk_bool'):
            a = deepcopy(self.args)
            p = next(x for x in a['projections'] if x['source_kind'] == 'JOURNAL')
            if attack == 'journal_span': p['score_reference']['record_locator']['byte_start'] = False
            elif attack == 'journal_stage': p['score_reference']['record_locator']['stage'] = 'RAW_FIT'
            elif attack == 'last_window': p['score']['windows'][-1]['fitted_window_preserved']['evaluation_last_return_end'] = '2026-09-21'
            elif attack == 'audit_flag': p['inspection']['optimized_weights_independently_verified'] = 0
            else: p['score']['windows'][-1]['risk_checks'][m.RISK[-1]] = 1
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                m.assemble_registered_selector_inputs(**a)


if __name__ == '__main__': unittest.main()
