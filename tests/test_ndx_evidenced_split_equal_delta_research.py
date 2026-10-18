from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts import ndx_evidenced_split_equal_delta_research as delta
from test_ndx_joint_weight_evaluation import fixture


class EvidencedSplitDeltaTests(unittest.TestCase):
    def test_three_synthetic_cells_same_evaluator_and_no_unlisted_mutation(self):
        _,inputs=fixture();names=sorted(inputs['universe'].ticker)[:3]
        inputs['contract']['window_days']=len(inputs['returns'])-inputs['contract']['fit_days']
        cells=[]
        for ticker,position,value in zip(names,(64,64,2),(-.025,-.024,.019)):
            day=inputs['returns'].index[position];inputs['returns'].at[day,ticker]=0.
            cells.append(dict(ticker=ticker,session=str(day.date()),old_value=0.,new_value=value))
        original=deepcopy(inputs);changed=delta.apply_cells(inputs,cells)
        self.assertEqual(delta.helper.typed_digest(inputs),delta.helper.typed_digest(original))
        arguments=lambda values:{key:values[key] for key in ('universe','returns','target_returns','incumbent_weights','contract')}
        combos=[(name,) for name in names]
        before=delta.helper.evaluator.evaluate_equal_weight_fractional_batch(combinations=combos,**arguments(inputs))
        after=delta.helper.evaluator.evaluate_equal_weight_fractional_batch(combinations=combos,**arguments(changed))
        windows=delta.coverage(inputs,cells)
        self.assertEqual([row['forward_affected'] for row in windows],[True,True,False])
        delta.verify_records(before['records'],after['records'],windows)
        self.assertEqual(before['records'][2]['fractional_metrics']['return_p10'],after['records'][2]['fractional_metrics']['return_p10'])
        tampered=deepcopy(after['records']);tampered[2]['fractional_metrics']['return_p10']+=.1
        with self.assertRaises(ValueError):delta.verify_records(before['records'],tampered,windows)
        with self.assertRaisesRegex(ValueError,'unique'):delta.apply_cells(inputs,cells+cells[:1])


class RealBoundPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.prepared=delta.prepare_date('2023-04-03')

    def test_real_preparation_denominator_runtime_and_cell_limits(self):
        windows=delta.validate_prepared(self.prepared)
        self.assertEqual(self.prepared['audit']['record_count'],24575)
        self.assertEqual([row['ticker'] for row in windows if row['forward_affected']],['GOOG','GOOGL'])
        self.assertEqual(self.prepared['audit']['original_context_runtime'],delta.helper.runtime())
        self.assertEqual(self.prepared['audit']['cells'],delta.CELLS)

    def test_mutated_affected_flag_rejected_without_real_evaluation(self):
        changed=deepcopy(self.prepared);changed['audit']['forward_affected']=False
        with patch.object(delta.helper.evaluator,'evaluate_equal_weight_fractional_batch',side_effect=AssertionError('no true batch')):
            with self.assertRaisesRegex(ValueError,'forward coverage'):delta.evaluate_prepared(changed)

    def test_mutated_saved_baseline_rejected_without_real_evaluation(self):
        changed=deepcopy(self.prepared)
        changed['previous']['evaluation']['records'][0]['fractional_metrics']['return_p50']+=.1
        with patch.object(delta.helper.evaluator,'evaluate_equal_weight_fractional_batch',side_effect=AssertionError('no true batch')):
            with self.assertRaisesRegex(ValueError,'original report'):delta.evaluate_prepared(changed)

    def test_same_affected_other_date_rejected(self):
        changed=deepcopy(self.prepared);changed['coordinate']['selection_date']='2023-05-01'
        with patch.object(delta.helper.evaluator,'evaluate_equal_weight_fractional_batch',side_effect=AssertionError('no true batch')):
            with self.assertRaisesRegex(ValueError,'coordinate'):delta.evaluate_prepared(changed)


if __name__=='__main__':unittest.main()
