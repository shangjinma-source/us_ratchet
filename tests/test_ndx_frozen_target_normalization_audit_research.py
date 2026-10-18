from copy import deepcopy
import json
from pathlib import Path
import unittest
from backtest import ndx_frozen_target_normalization_audit_research as independent
from backtest.ndx_dynamic_whole_lot_path import _normalise_schedule


class NormalizationTests(unittest.TestCase):
    def test_actual_two_periods_exact_old_normalizer_without_execution(self):
        path=Path(__file__).resolve().parents[1]/'data/cache/research/corrected_explicit_path_20260919_v1/target_path.json'
        schedule=json.loads(path.read_bytes())['result']['schedule'];original=deepcopy(schedule)
        normalized,evidence=independent.normalized_schedule(schedule);legacy=_normalise_schedule(schedule)
        self.assertEqual(schedule,original)
        self.assertEqual([r['targets'] for r in normalized],[r['targets'] for r in legacy])
        self.assertEqual(evidence['periods'][0]['binary_float_weight_sum'],1.)
        self.assertEqual(evidence['periods'][1]['binary_float_weight_sum'],1.0000000000000002)
        self.assertGreater(evidence['periods'][1]['maximum_absolute_binary_float_difference'],0.)

    def test_preserves_iteration_order_and_rejects_non_unit_or_boolean(self):
        schedule=[dict(decision_date='2023-03-31',execution_date='2023-04-03',targets={
            str(i):dict(ticker='T'+str(i),issuer_id='I'+str(i),target_weight=w) for i,w in enumerate([.1,.2,.7])})]
        result,evidence=independent.normalized_schedule(schedule)
        self.assertEqual(evidence['periods'][0]['target_iteration_order'],['0','1','2'])
        for value in (True,0.,-1.,float('nan'),.5):
            bad=deepcopy(schedule);bad[0]['targets']['0']['target_weight']=value
            with self.assertRaises(ValueError): independent.normalized_schedule(bad)


if __name__=='__main__': unittest.main()
