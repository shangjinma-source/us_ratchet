from copy import deepcopy
import unittest
from scripts import ndx_goog_equal_single_cell_delta_research as delta
from test_ndx_joint_weight_evaluation import fixture


class SingleCellDeltaTests(unittest.TestCase):
    def test_synthetic_same_frozen_engine_preserves_risk_fees_and_nonselected_candidate(self):
        _,inputs=fixture()
        inputs['contract']['window_days']=len(inputs['returns'])-inputs['contract']['fit_days']
        ticker=sorted(inputs['incumbent_weights'])[0]
        other=next(name for name in sorted(inputs['universe'].ticker) if name!=ticker)
        day=inputs['returns'].index[64]
        inputs['returns'].at[day,ticker]=0.
        before=deepcopy(inputs)
        updated=delta.correct_one_cell(inputs,day=str(day.date()),ticker=ticker)
        combinations=[(ticker,),(other,)]
        arguments=lambda values:{key:values[key] for key in ('universe','returns','target_returns','incumbent_weights','contract')}
        old=delta.evaluator.evaluate_equal_weight_fractional_batch(combinations=combinations,**arguments(inputs))
        new=delta.evaluator.evaluate_equal_weight_fractional_batch(combinations=combinations,**arguments(updated))
        delta.verify_record_invariants(old['records'],new['records'],corrected_ticker=ticker)
        self.assertEqual(delta.typed_digest(inputs),delta.typed_digest(before))
        self.assertNotEqual(old['records'][0]['fractional_metrics'],new['records'][0]['fractional_metrics'])
        for field in ('return_p50','return_p10','max_drawdown_p50','max_drawdown_p90'):
            self.assertEqual(old['records'][1]['fractional_metrics'][field],new['records'][1]['fractional_metrics'][field])
        self.assertNotEqual(old['records'][1]['fractional_metrics']['paired_return_p10_vs_incumbent'],
                            new['records'][1]['fractional_metrics']['paired_return_p10_vs_incumbent'])
        tampered=deepcopy(new['records']);tampered[0]['fractional_metrics']['initial_transaction_cost']+=.1
        with self.assertRaisesRegex(ValueError,'initial fee'):delta.verify_record_invariants(old['records'],tampered,corrected_ticker=ticker)
        with self.assertRaisesRegex(ValueError,'denominator'):delta.verify_record_invariants(old['records'],new['records'][:1])

    def test_fit_only_cell_has_exactly_identical_complete_equal_output(self):
        _,inputs=fixture();ticker=sorted(inputs['incumbent_weights'])[0];day=inputs['returns'].index[2]
        inputs['returns'].at[day,ticker]=0.
        updated=delta.correct_one_cell(inputs,day=str(day.date()),ticker=ticker)
        arguments=lambda values:{key:values[key] for key in ('universe','returns','target_returns','incumbent_weights','contract')}
        old=delta.evaluator.evaluate_equal_weight_fractional_batch(combinations=[(ticker,)],**arguments(inputs))
        new=delta.evaluator.evaluate_equal_weight_fractional_batch(combinations=[(ticker,)],**arguments(updated))
        self.assertEqual(old,new)

    def test_nonzero_old_cell_rejected(self):
        _,inputs=fixture();ticker=sorted(inputs['incumbent_weights'])[0];day=inputs['returns'].index[64]
        with self.assertRaisesRegex(ValueError,'old cell'):
            delta.correct_one_cell(inputs,day=str(day.date()),ticker=ticker)
        for key in ('old_value','new_value'):
            with self.assertRaisesRegex(ValueError,'nonboolean'):
                delta.correct_one_cell(inputs,day=str(day.date()),ticker=ticker,**{key:True})

    def test_prepared_affected_flag_is_recomputed_before_evaluation(self):
        from unittest.mock import patch
        _,inputs=fixture()
        inputs['returns'].index=__import__('pandas').date_range('2022-04-01',periods=len(inputs['returns']),freq='B')
        windows=delta.window_coverage(inputs)
        self.assertTrue(any(row['contains_corrected_cell'] for row in windows))
        prepared=dict(source_hashes=delta.LOADED,inputs=inputs,coordinate=dict(selection_date='2023-04-03'),
            audit=dict(window_coverage=windows,forward_affected=False))
        with patch.object(delta.evaluator,'evaluate_equal_weight_fractional_batch',side_effect=AssertionError('no execution')):
            with self.assertRaisesRegex(ValueError,'forward coverage'):delta.evaluate_prepared(prepared)


if __name__=='__main__':unittest.main()
