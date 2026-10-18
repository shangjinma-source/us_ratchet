from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts import ndx_combined_fractional_date as combined


def fixture():
    coordinate = dict(source_batch='SYNTHETIC', universe_track='strict_technology', selection_date='2024-02-01')
    signature = 'a' * 64
    cutoff = '2024-01-31'
    semantics = dict(training_semantics_sha256=signature, payload=dict(decision_data_end=cutoff,
        contract=dict(max_single_weight=1, top_weight_cap=1, risk_chain_top1_cap=1,
                      minimum_effective_n_ratio=.1, minimum_median_dollar_volume_usd=1)))

    def task(names, spec, job):
        return dict(coordinate, decision_data_end=cutoff, tickers=names, holding_count=len(names.split(';')),
                    weight_spec=spec, job_id=job)

    def metrics(identity):
        return dict(tickers=identity['tickers'], holding_count=identity['holding_count'],
                    weight_spec=identity['weight_spec'], return_p50=.2, return_p10=.1,
                    max_drawdown_p50=.1, max_drawdown_p90=.2, target_012922_distance=.1,
                    issuer_top1=.5, weight_top3_max=1., risk_chain_top1=1., effective_n_min=2.,
                    portfolio_min_median_dollar_volume_usd=100., declared_max_single_passed=True,
                    declared_security_top3_weight_passed=True, declared_risk_chain_top1_weight_passed=True,
                    declared_effective_n_passed=True, liquidity_constraint_passed=True)
    eq_task = task('AMAT;AVGO;CDNS;GOOG', 'equal_weight', 'equal')
    risk = metrics(eq_task)
    equal = dict(coordinate=coordinate, training_semantics=semantics,
                 input_summary=dict(equal_weight_base_count=1, all_base_count=2, delta_count=1),
                 evaluation=dict(records=[dict(tickers=eq_task['tickers'], holding_count=4,
                     weight_spec='equal_weight', fractional_metrics={}, risk_liquidity_metrics=risk)]))
    ne_task = task('A;B', 'constrained_fixed_shrinkage', 'base')
    non_equal = dict(context=dict(coordinate, training_semantics=deepcopy(semantics), planned=1, tasks=[ne_task]),
                     planned=1, records=[dict(task=ne_task, result=dict(result=metrics(ne_task)))])
    d_task = task('A;B;C', 'constrained_fixed_shrinkage_turnover_anchor', 'delta')
    delta = dict(expected_date=dict(coordinate, expected_task_count=1, decision_data_end=cutoff,
                                   training_semantics_sha256=signature),
                 records=[dict(task=d_task, result=metrics(d_task), status='EVALUATED',
                               training_semantics_sha256=signature)])
    return dict(equal=equal, non_equal=non_equal, delta=delta)


class CombinedFractionalDateTests(unittest.TestCase):
    def test_complete_all_classes_unknown_scope_and_preference(self):
        inputs = fixture()
        inputs['delta']['records'][0]['result'].update(whole_lot_return_p50=99,
                                                     declared_constraints_passed=False)
        result = combined._combine(**inputs, policy_role='RETURN')
        self.assertEqual(result['expected_date']['expected_task_count'], 3)
        self.assertEqual(len(result['records']), 3)
        self.assertTrue(result['economic_inputs_complete'])
        self.assertEqual(result['selection']['rows'][0]['status'], 'NO_ELIGIBLE_CANDIDATE')
        self.assertTrue(all(r['eligibility']['technology_scope_passed'] is None for r in result['records']))
        self.assertNotIn('whole_lot_return_p50', result['records'][-1]['result'])
        self.assertNotIn('declared_constraints_passed', result['records'][-1]['result'])
        reference = combined._combine(**inputs, policy_role='USER_PREFERENCE')
        self.assertEqual(reference['selection']['rows'][0]['selected']['origin'], 'EQUAL_WEIGHT_BASE')
        self.assertFalse(reference['promotion_allowed'])

    def test_missing_base_or_delta_invalidates_whole_date_even_preference(self):
        for missing in ('non_equal', 'delta'):
            inputs = fixture(); inputs[missing]['records'] = []
            result = combined._combine(**inputs, policy_role='USER_PREFERENCE')
            self.assertEqual(result['selection']['rows'][0]['status'], 'INPUT_INVALID')
            self.assertIsNone(result['selection']['rows'][0]['selected'])
            self.assertFalse(result['economic_inputs_complete'])

    def test_semantics_cutoff_denominator_and_duplicate_fail_closed(self):
        for fault in ('semantics', 'cutoff', 'count', 'duplicate'):
            inputs = fixture()
            if fault == 'semantics': inputs['non_equal']['context']['training_semantics']['payload']['contract']['max_single_weight'] = .9
            if fault == 'cutoff': inputs['delta']['expected_date']['decision_data_end'] = '2024-01-30'
            if fault == 'count': inputs['equal']['input_summary']['all_base_count'] = 3
            if fault == 'duplicate':
                task = inputs['delta']['records'][0]['task']
                task.update(tickers='B;A', holding_count=2, weight_spec='constrained_fixed_shrinkage')
            with self.assertRaises(ValueError, msg=fault): combined._combine(**inputs, policy_role='RETURN')

    def test_recomputed_gates_reject_bad_numeric_and_no_partial_winner(self):
        inputs = fixture()
        inputs['delta']['records'][0]['result']['issuer_top1'] = float('nan')
        result = combined._combine(**inputs, policy_role='USER_PREFERENCE')
        self.assertEqual(result['selection']['rows'][0]['status'], 'INPUT_INVALID')
        self.assertIsNone(result['selection']['rows'][0]['selected'])

    def test_public_binding_and_conflicting_source(self):
        inputs = fixture()
        for value in inputs.values(): value['source_hashes'] = {}
        with patch.object(combined.equal_report, 'load_report', return_value=inputs['equal']) as eq, \
             patch.object(combined.non_equal_readback, 'read_context', return_value=inputs['non_equal']) as ne, \
             patch.object(combined.delta_date, 'prepare_date_v2', return_value=inputs['delta']), \
             patch.object(combined, '_check_sources') as guard:
            result = combined.prepare_combined_date(equal_report_path='synthetic.json', equal_report_sha256='b'*64,
                non_equal_context_path='context.json', non_equal_context_sha256='c'*64,
                **inputs['equal']['coordinate'])
            eq.assert_called_once_with('synthetic.json', expected_sha256='b'*64)
            ne.assert_called_once_with(context_path='context.json', expected_context_sha256='c'*64)
            self.assertEqual(guard.call_count, 3)
            self.assertIn(str(combined.Path('synthetic.json').resolve()), result['source_hashes'])
        with self.assertRaises(ValueError): combined._merge_sources({'x':'a'}, {'x':'b'})


if __name__ == '__main__': unittest.main()
