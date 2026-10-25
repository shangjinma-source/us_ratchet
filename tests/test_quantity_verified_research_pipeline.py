from copy import deepcopy
from fractions import Fraction as F
import json
import unittest
from unittest.mock import patch

from backtest import quantity_verified_research_pipeline as pipeline
from backtest import quantity_continuous_anchor_bound as continuous
from test_quantity_anchor_coupled_completion import fixture


def request(**options):
    sources, optimum = fixture(**options)
    base = json.loads(sources['base_raw'])
    inherited = [{}]
    return dict(inputs=base['inputs'], anchor=base['anchor'], inherited_candidates=inherited,
                expected_inputs_sha256=sources['expected_inputs_sha256'],
                expected_anchor_sha256=sources['expected_anchor_sha256'],
                expected_inherited_sha256=continuous.digest(inherited)), optimum


class PipelineTests(unittest.TestCase):
    def test_all_three_routes_with_full_source_bindings(self):
        cases = [(dict(), 10000, 'SMALL_TAIL'), (dict(), 1, 'COUPLED'),
                 (dict(symmetric=True), 1, 'INTEGER_PARTITION')]
        for options, tail_cap, route in cases:
            sources, optimum = request(**options)
            before = deepcopy(sources)
            with patch('scipy.optimize.minimize', side_effect=AssertionError('NO_OPTIMIZER')):
                result = pipeline.build(**sources, max_tail_points=tail_cap)
                pipeline.verify(result, **sources)
            self.assertEqual(result['route'], route)
            self.assertTrue(result['objective_value_covered'])
            self.assertEqual(F(result['lower_product']), optimum)
            self.assertFalse(result['production_ready'])
            self.assertFalse(result['tie_break_optimality_established'])
            self.assertEqual(sources, before)

    def test_budget_stop_retains_frontier_and_continuation_closes(self):
        sources, optimum = request(symmetric=True)
        stopped = pipeline.build(**sources, max_tail_points=1, node_budget=1, max_segments=1)
        self.assertEqual(stopped['status'], 'BUDGET_STOPPED_UNRESOLVED')
        self.assertTrue(stopped['stages']['segments'][-1]['pending'])
        self.assertLessEqual(F(stopped['lower_product']), optimum)
        self.assertGreaterEqual(F(stopped['upper_product']), optimum)
        completed = pipeline.build(**sources, max_tail_points=1, node_budget=1, max_segments=100)
        self.assertTrue(completed['objective_value_covered'])
        self.assertEqual(F(completed['lower_product']), optimum)
        pipeline.verify(completed, **sources)

    def test_inputs_cash_and_inherited_provenance_cannot_be_reused(self):
        sources, _ = request()
        for name in ['expected_inputs_sha256', 'expected_anchor_sha256', 'expected_inherited_sha256']:
            with self.assertRaises(ValueError):
                pipeline.build(**dict(sources, **{name: '0' * 64}))
        changed = deepcopy(sources)
        changed['inputs']['entered_cash'] = '3'
        changed['expected_inputs_sha256'] = continuous.digest(changed['inputs'])
        with self.assertRaisesRegex(ValueError, 'ANCHOR_INPUT_MISMATCH'):
            pipeline.build(**changed)

    def test_false_completion_removed_proof_and_budgets_rejected(self):
        sources, _ = request(symmetric=True)
        result = pipeline.build(**sources, max_tail_points=1, node_budget=1, max_segments=1)
        for key, value in [('objective_value_covered', True), ('stages', {}), ('production_ready', True)]:
            bad = deepcopy(result)
            bad[key] = value
            with self.assertRaisesRegex(ValueError, 'PIPELINE_CERTIFICATE_CHANGED'):
                pipeline.verify(bad, **sources)
        for budgets in [dict(node_budget=True), dict(max_segments=0), dict(max_segments=101), dict(objective_budget=501)]:
            with self.assertRaisesRegex(ValueError, 'PIPELINE_FIXED_BUDGET_REQUIRED'):
                pipeline.build(**sources, **budgets)


if __name__ == '__main__':
    unittest.main()
