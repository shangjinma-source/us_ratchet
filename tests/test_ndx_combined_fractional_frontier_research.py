from copy import deepcopy
import hashlib
import json
import unittest

import numpy as np

from backtest import ndx_combined_fractional_frontier_research as frontier
from backtest.ndx_fractional_research_gates import fractional_research_gates


def fixture(count=4):
    coordinate = dict(source_batch='SYNTHETIC', universe_track='strict_technology', selection_date='2024-02-01')
    payload = dict(schema='ndx_dynamic_training_semantics_v1', source_batch=coordinate['source_batch'],
        universe_track=coordinate['universe_track'], decision_data_end='2024-01-31', contract=dict(max_single_weight=1., top_weight_cap=1.,
        risk_chain_top1_cap=1., minimum_effective_n_ratio=.1, minimum_median_dollar_volume_usd=100.))
    signature = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    records = []
    for index in range(count):
        names = 'AMAT;AVGO;CDNS;GOOG' if index == 0 else 'A' + str(index)
        task = dict(coordinate, decision_data_end=payload['decision_data_end'], tickers=names,
            holding_count=len(names.split(';')), weight_spec='equal_weight', job_id=str(index))
        metrics = dict(tickers=names, holding_count=task['holding_count'], weight_spec='equal_weight',
            return_p50=.2, return_p10=.1, max_drawdown_p50=.1, max_drawdown_p90=.2, target_012922_distance=.1,
            issuer_top1=1., weight_top3_max=1., risk_chain_top1=1., effective_n_min=1.,
            portfolio_min_median_dollar_volume_usd=100., declared_max_single_passed=True,
            declared_security_top3_weight_passed=True, declared_risk_chain_top1_weight_passed=True,
            declared_effective_n_passed=True, liquidity_constraint_passed=True,
            **dict(zip(frontier.ECONOMIC_COLUMNS, [.1, .05, -.02, -.01] * 2)))
        records.append(dict(task=task, result=metrics, origin='EQUAL_WEIGHT_BASE', status='EVALUATED',
            training_semantics_sha256=signature, eligibility=fractional_research_gates(metrics=metrics,
                contract=payload['contract'], holding_count=task['holding_count'])))
    return dict(schema='ndx_combined_fractional_date_v1', expected_date=dict(coordinate, expected_task_count=count,
        decision_data_end=payload['decision_data_end'], training_semantics_sha256=signature),
        records=records, training_semantics=dict(payload=payload, training_semantics_sha256=signature),
        counts={origin: dict(planned=count if origin == 'EQUAL_WEIGHT_BASE' else 0,
            observed=count if origin == 'EQUAL_WEIGHT_BASE' else 0, evaluated=count if origin == 'EQUAL_WEIGHT_BASE' else 0)
            for origin in ('EQUAL_WEIGHT_BASE', 'NON_EQUAL_BASE', 'DELTA')},
        economic_inputs_complete=True, technology_scope_status='UNRESOLVED_CURRENT_PURE_TECH_DEFINITION')


class CombinedFrontierTests(unittest.TestCase):
    def test_exact_sweep_matches_independent_all_pairs_oracle_and_ties(self):
        generator = np.random.default_rng(987)
        for count in (0, 1, 10, 90):
            values = generator.integers(-3, 4, size=(count, 8))
            if count > 1:
                values[-1] = values[0]
            expected = [index for index, row in enumerate(values) if not any(
                all(left >= right for left, right in zip(other, row))
                and any(left > right for left, right in zip(other, row)) for other in values)]
            self.assertEqual(frontier.exact_pareto_indices(values), expected)

    def test_ties_order_unknown_scope_and_no_inferred_weights(self):
        date = fixture()
        original = deepcopy(date)
        result = frontier.analyze_combined_date(date)
        self.assertEqual(result['counts']['raw_frontier_count'], 4)
        self.assertEqual(result['counts']['technology_scope_unknown_count'], 4)
        self.assertEqual(result['counts']['dual_benchmark_eight_dimension_pass_count'], 4)
        self.assertEqual(sum(row['expected_task_count'] for row in result['groups']), 4)
        self.assertEqual(date, original)
        date['records'].reverse()
        self.assertEqual(frontier.analyze_combined_date(date), result)
        self.assertFalse(result['promotion_allowed'])
        self.assertFalse(result['execution_performed'])
        self.assertFalse(result['global_optimum_proven'])
        self.assertFalse(result['saved_weights_are_execution_targets'])
        self.assertFalse(result['historical_minimum_single_weight_verified'])
        self.assertFalse(result['current_whole_lot_execution_verified'])
        self.assertEqual(result['whole_lot_status'], 'NOT_EVALUATED')
        self.assertTrue(all('weights' not in row for row in result['raw_frontier']))
        self.assertTrue(all(row['technology_scope_passed'] is None for row in result['raw_frontier']))
        json.dumps(result, allow_nan=False)

    def test_raw_dominance_does_not_use_clipped_deficit_vectors(self):
        date = fixture(2)
        date['records'][1]['result']['return_p50_vs_012922'] = .2
        result = frontier.analyze_combined_date(date)
        self.assertEqual([row['job_id'] for row in result['raw_frontier']], ['1'])
        self.assertEqual([row['job_id'] for row in result['user_preference_references']], ['0'])

    def test_risk_layer_recomputed_and_failed_preference_is_retained(self):
        date = fixture(2)
        record = date['records'][0]
        record['result'].update(portfolio_min_median_dollar_volume_usd=50., liquidity_constraint_passed=False,
                                return_p50_vs_012922=.4)
        record['eligibility'] = fractional_research_gates(metrics=record['result'],
            contract=date['training_semantics']['payload']['contract'], holding_count=4)
        result = frontier.analyze_combined_date(date)
        self.assertEqual([row['job_id'] for row in result['raw_frontier']], ['0'])
        self.assertEqual([row['job_id'] for row in result['risk_liquidity_frontier']], ['1'])
        self.assertFalse(result['user_preference_references'][0]['liquidity_passed'])
        self.assertEqual(result['counts']['fractional_risk_liquidity_count'], 1)

    def test_no_dual_feasible_candidate_and_no_compensating_advantage(self):
        date = fixture(2)
        for record in date['records']:
            record['result'].update(return_p50_vs_012922=1000., paired_drawdown_cost_p90_vs_incumbent=.01)
        result = frontier.analyze_combined_date(date)
        self.assertEqual(result['counts']['dual_benchmark_eight_dimension_pass_count'], 0)
        self.assertEqual(result['counts']['raw_frontier_count'], 2)
        self.assertEqual(result['raw_frontier'][0]['failed_dimensions'], ['paired_drawdown_cost_p90_vs_incumbent'])

    def test_missing_tasks_status_denominators_duplicates_and_mixed_coordinates_reject(self):
        for fault in ('missing', 'status', 'origin', 'count', 'duplicate', 'date', 'batch', 'track', 'cutoff', 'signature'):
            date = fixture()
            record = date['records'][-1]
            if fault == 'missing': date['records'].pop()
            if fault == 'status': record['status'] = 'MISSING_CHECKPOINT'
            if fault == 'origin': record['origin'] = 'UNKNOWN'
            if fault == 'count': date['counts']['EQUAL_WEIGHT_BASE']['planned'] = 3
            if fault == 'duplicate': date['records'][-1] = deepcopy(date['records'][0])
            if fault == 'date': record['task']['selection_date'] = '2024-02-02'
            if fault == 'batch': record['task']['source_batch'] = 'OTHER'
            if fault == 'track': record['task']['universe_track'] = 'OTHER'
            if fault == 'cutoff': record['task']['decision_data_end'] = '2024-01-30'
            if fault == 'signature': record['training_semantics_sha256'] = 'b' * 64
            with self.assertRaises(ValueError, msg=fault): frontier.analyze_combined_date(date)

    def test_nonfinite_boolean_or_missing_coordinate_metrics_reject(self):
        for field in (*frontier.ECONOMIC_COLUMNS, *frontier.DIMENSIONS):
            for value in (True, float('nan'), float('inf'), '0.1', None):
                date = fixture()
                date['records'][0]['result'][field] = value
                with self.assertRaises(ValueError, msg=(field, value)): frontier.analyze_combined_date(date)

    def test_scope_upgrade_gate_forgery_and_semantics_content_change_reject(self):
        for fault in ('true', 'false', 'string', 'gate', 'contract'):
            date = fixture()
            if fault in ('true', 'false', 'string'):
                date['records'][0]['eligibility']['technology_scope_passed'] = {'true': True, 'false': False, 'string': 'UNKNOWN'}[fault]
            if fault == 'gate': date['records'][0]['eligibility']['liquidity_passed'] = False
            if fault == 'contract': date['training_semantics']['payload']['contract']['max_single_weight'] = .5
            with self.assertRaises(ValueError, msg=fault): frontier.analyze_combined_date(date)

    def test_empty_risk_layer(self):
        date = fixture(1)
        record = date['records'][0]
        record['result'].update(portfolio_min_median_dollar_volume_usd=50., liquidity_constraint_passed=False)
        record['eligibility'] = fractional_research_gates(metrics=record['result'],
            contract=date['training_semantics']['payload']['contract'], holding_count=4)
        result = frontier.analyze_combined_date(date)
        self.assertEqual(result['risk_liquidity_frontier'], [])
        self.assertEqual(len(result['user_preference_references']), 1)

    def test_pareto_helper_rejects_implicit_mixed_boolean_coercion(self):
        for values in ([[True, 1., 0., 0., 0., 0., 0., 0.]], np.ones((2, 8), dtype=bool),
                       np.array([[True, 1., 0., 0., 0., 0., 0., 0.]], dtype=object)):
            with self.assertRaises(ValueError): frontier.exact_pareto_indices(values)

    def test_rehashed_semantics_mixed_source_or_track_rejected(self):
        for key in ('source_batch', 'universe_track'):
            date = fixture()
            semantics = date['training_semantics']
            semantics['payload'][key] = 'OTHER'
            digest = hashlib.sha256(json.dumps(semantics['payload'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            semantics['training_semantics_sha256'] = digest
            date['expected_date']['training_semantics_sha256'] = digest
            for record in date['records']:
                record['training_semantics_sha256'] = digest
            with self.assertRaisesRegex(ValueError, 'Training semantics'):
                frontier.analyze_combined_date(date)


if __name__ == '__main__':
    unittest.main()
