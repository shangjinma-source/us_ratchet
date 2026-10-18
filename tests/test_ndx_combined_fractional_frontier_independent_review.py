"""Independent all-pairs and directional counterexamples for research frontier."""
from copy import deepcopy
from itertools import product
import unittest

import numpy as np

from backtest import ndx_combined_fractional_frontier_research as frontier
from backtest.ndx_fractional_research_gates import fractional_research_gates
from test_ndx_combined_fractional_frontier_research import fixture


class IndependentFrontierReviewTests(unittest.TestCase):
    def test_grid_extremes_ties_and_adjacent_floats_match_all_pairs(self):
        grid = np.array([list(item) + [0.] * 5 for item in product((-1., 0., 1.), repeat=3)])
        rng = np.random.default_rng(20260912)
        for count in (2, 9, 80, 180):
            random = rng.normal(size=(count, 8))
            random[-1] = random[0]
            for matrix in (grid, random, np.vstack([random, np.nextafter(random[0], np.inf)])):
                expected = [index for index, candidate in enumerate(matrix)
                            if not any(np.all(other >= candidate) and np.any(other > candidate)
                                       for other in matrix)]
                self.assertEqual(frontier.exact_pareto_indices(matrix), expected)

    def test_each_of_eight_directions_independently_changes_dominance(self):
        maximize = {'return_p50_vs_012922', 'return_p10_vs_012922',
                    'paired_return_p50_vs_incumbent', 'paired_return_p10_vs_incumbent'}
        for column in frontier.ECONOMIC_COLUMNS:
            cohort = fixture(2)
            # Improvements are small enough to preserve paired quantile order.
            original = cohort['records'][1]['result'][column]
            cohort['records'][1]['result'][column] = float(np.nextafter(
                original, np.inf if column in maximize else -np.inf))
            report = frontier.analyze_combined_date(cohort)
            self.assertEqual([row['job_id'] for row in report['raw_frontier']], ['1'], column)

    def test_all_eight_zero_boundaries_reject_even_subnormal_disadvantage(self):
        maximize = {'return_p50_vs_012922', 'return_p10_vs_012922',
                    'paired_return_p50_vs_incumbent', 'paired_return_p10_vs_incumbent'}
        for column in frontier.ECONOMIC_COLUMNS:
            cohort = fixture(1)
            metrics = cohort['records'][0]['result']
            metrics[column] = float(np.nextafter(0., -np.inf if column in maximize else np.inf))
            expected_failures = {column}
            # The two constrained quantiles require the other tail to follow.
            if column == 'paired_return_p50_vs_incumbent':
                metrics['paired_return_p10_vs_incumbent'] = metrics[column]
                expected_failures.add('paired_return_p10_vs_incumbent')
            if column == 'paired_drawdown_cost_p50_vs_incumbent':
                metrics['paired_drawdown_cost_p90_vs_incumbent'] = metrics[column]
                expected_failures.add('paired_drawdown_cost_p90_vs_incumbent')
            report = frontier.analyze_combined_date(cohort)
            row = report['raw_frontier'][0]
            self.assertEqual(set(row['failed_dimensions']), expected_failures)
            self.assertFalse(row['dual_benchmark_eight_dimension_passed'])

    def test_group_counts_account_for_all_origins_k_and_risk_failures(self):
        cohort = fixture(4)
        for index, (origin, specification) in enumerate((
                ('EQUAL_WEIGHT_BASE', 'equal_weight'),
                ('NON_EQUAL_BASE', 'constrained_fixed_shrinkage'),
                ('DELTA', 'equal_weight'),
                ('DELTA', 'constrained_fixed_shrinkage_turnover_anchor'))):
            record = cohort['records'][index]
            record['origin'] = origin
            record['task']['weight_spec'] = specification
            record['result']['weight_spec'] = specification
        failed = cohort['records'][2]
        failed['result'].update(portfolio_min_median_dollar_volume_usd=50., liquidity_constraint_passed=False)
        failed['eligibility'] = fractional_research_gates(metrics=failed['result'],
            contract=cohort['training_semantics']['payload']['contract'], holding_count=1)
        cohort['counts'] = {origin: dict(planned=count, observed=count, evaluated=count)
                            for origin, count in (('EQUAL_WEIGHT_BASE', 1), ('NON_EQUAL_BASE', 1), ('DELTA', 2))}
        before = deepcopy(cohort)
        report = frontier.analyze_combined_date(cohort)
        self.assertEqual(cohort, before)
        self.assertEqual(len(report['raw_frontier']), 4)
        self.assertEqual(len(report['risk_liquidity_frontier']), 3)
        self.assertEqual(sum(row['expected_task_count'] for row in report['groups']), 4)
        self.assertEqual(sum(row['fractional_risk_liquidity_count'] for row in report['groups']), 3)
        self.assertEqual(sum(row['technology_scope_unknown_count'] for row in report['groups']), 4)
        self.assertEqual({row['holding_count'] for row in report['groups']}, {1, 4})
        self.assertFalse(report['historical_minimum_single_weight_verified'])
        self.assertFalse(report['current_whole_lot_execution_verified'])
        self.assertFalse(report['promotion_allowed'])


if __name__ == '__main__':
    unittest.main()
