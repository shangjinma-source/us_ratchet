from copy import deepcopy
import itertools
import unittest
from unittest.mock import patch
import numpy as np
from backtest import ndx_equal_weight_fractional_batch as batch
from backtest import ndx_cardinality_discovery as legacy
from test_ndx_joint_weight_evaluation import fixture


class EqualFractionalBatchTests(unittest.TestCase):
    def inputs(self):
        _,inputs=fixture();inputs.pop('nominal_prices');return inputs

    def test_same_input_overlap_all_combos_k1_to5(self):
        inputs=self.inputs();names=sorted(inputs['universe'].drop_duplicates('issuer_id').ticker)[:5]
        combos=[combo for k in range(1,6) for combo in itertools.combinations(names,k)]
        result=batch.evaluate_equal_weight_fractional_batch(combinations=combos,**inputs,batch_size=7)
        maximum=0.
        with patch.object(legacy,'simulate_continuous_whole_lot_rebalance',side_effect=AssertionError('No whole-lot simulator')):
            for combo,row in zip(combos,result['records']):
                expected=legacy.evaluate_synthetic_portfolio(combo,inputs['universe'],inputs['returns'],
                    inputs['target_returns'],sorted(inputs['incumbent_weights']),weight_spec='equal_weight',
                    incumbent_weights=inputs['incumbent_weights'],execution_prices=None,**inputs['contract'])
                for field,value in row['fractional_metrics'].items():
                    maximum=max(maximum,abs(value-expected[field]))
                    self.assertAlmostEqual(value,expected[field],delta=1e-12,msg=field)
                for field,value in row['risk_liquidity_metrics'].items():
                    if field in expected:self.assertAlmostEqual(value,expected[field],delta=1e-12,msg=field)
                self.assertEqual(row['whole_lot_status'],'NOT_EVALUATED')
                self.assertNotIn('declared_constraints_passed',row)
        self.assertLess(maximum,1e-12)

    def test_chunking_identical_and_first_nav_loss(self):
        inputs=self.inputs();names=sorted(inputs['universe'].drop_duplicates('issuer_id').ticker)[:2];combos=[(names[0],),tuple(names)]
        inputs['returns'].iloc[:]=0.;inputs['target_returns'].iloc[:]=0.
        first=batch.evaluate_equal_weight_fractional_batch(combinations=combos,**inputs,batch_size=1)
        other=batch.evaluate_equal_weight_fractional_batch(combinations=combos,**inputs,batch_size=10)
        self.assertEqual(first,other)
        self.assertGreater(first['records'][0]['fractional_metrics']['initial_transaction_cost'],0)
        self.assertGreater(first['records'][0]['fractional_metrics']['max_drawdown_p90'],0)
        self.assertEqual(first['records'][0]['fractional_metrics']['ongoing_rebalance_turnover_p50'],0.)

    def test_boolean_calendar_duplicate_combo_and_issuer_rejected(self):
        inputs=self.inputs();name=inputs['universe'].ticker.iloc[0];inputs['returns'][name]=True
        with self.assertRaises(ValueError):batch.evaluate_equal_weight_fractional_batch(combinations=[(name,)],**inputs)
        inputs=self.inputs();names=sorted(inputs['universe'].ticker)[:2]
        with self.assertRaises(ValueError):batch.evaluate_equal_weight_fractional_batch(combinations=[(names[0],)]*2,**inputs)
        inputs['universe'].loc[inputs['universe'].ticker.isin(names),'issuer_id']='one'
        with self.assertRaises(ValueError):batch.evaluate_equal_weight_fractional_batch(combinations=[tuple(names)],**inputs)

    def test_no_input_mutation_or_false_whole_lot_claim(self):
        inputs=self.inputs();before=deepcopy(inputs);name=sorted(inputs['universe'].ticker)[0]
        result=batch.evaluate_equal_weight_fractional_batch(combinations=[(name,)],**inputs)
        self.assertTrue(before['returns'].equals(inputs['returns']))
        self.assertEqual(result['whole_lot_status'],'NOT_EVALUATED')
        self.assertFalse(result['full_legacy_result_compatible'])


if __name__=='__main__':unittest.main()
