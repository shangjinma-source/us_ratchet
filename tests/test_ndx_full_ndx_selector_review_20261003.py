from copy import deepcopy
import unittest
from test_ndx_full_ndx_multidecision_selector_research import fixture
from backtest import ndx_full_ndx_multidecision_selector_research as m

class Review(unittest.TestCase):
    def test_registered_ids_cannot_double_count_same_semantic_task(self):
        reg,records=fixture();duplicate=deepcopy(records[0]);duplicate['task']['job_id']=records[1]['task']['job_id'];records[1]=duplicate
        out=m.select_full_ndx_lanes(registration=reg,records=records)
        self.assertTrue(all(x['status']=='INPUT_INVALID' and x['selected'] is None for x in out['rows'][0]['choices']))
        self.assertTrue(all(x['selected'] is not None for x in out['rows'][1]['choices']))

    def test_impossible_negative_drawdown_or_distance_not_winner(self):
        for metric in ('max_drawdown_p50','max_drawdown_p90','target_012922_distance'):
            reg,records=fixture();records[0]['result'][metric]=-1
            with self.subTest(metric=metric):
                out=m.select_full_ndx_lanes(registration=reg,records=records)
                self.assertTrue(all(x['selected'] is None for x in out['rows'][0]['choices']))

    def test_order_invariant_ties_full_issuer_domain_and_causal_boundary(self):
        reg,records=fixture()
        for record in records:
            for metric in m.METRICS:record['result'][metric]=.1
        before=deepcopy(records)
        out=m.select_full_ndx_lanes(registration=reg,records=list(reversed(records)))
        self.assertEqual(records,before)
        self.assertEqual([x['combination_count'] for x in out['all_k_denominators_preserved']],[4,5,2])
        self.assertTrue(all(c['selected']['record_preserved']['task']['tickers']=='AAA' for r in out['rows'] for c in r['choices']))
        records[0]['scoring_windows'][-1]['evaluation_last_return_end']='2026-04-01'
        out=m.select_full_ndx_lanes(registration=reg,records=records)
        self.assertTrue(all(c['selected'] is None for c in out['rows'][0]['choices']))
        self.assertFalse(out['execution_authorized'])

if __name__=='__main__':unittest.main()
