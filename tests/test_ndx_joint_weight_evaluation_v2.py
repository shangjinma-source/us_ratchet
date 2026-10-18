import unittest
from unittest.mock import patch

from test_ndx_joint_weight_evaluation import fixture
from backtest import ndx_cardinality_discovery as discovery
from backtest import ndx_joint_weight_evaluation as original
from backtest import ndx_joint_weight_evaluation_v2 as revised


class EvaluationV2Tests(unittest.TestCase):
    def test_private_dependency_chain_preserves_original_globals(self):
        projection = discovery.project_concentration_envelope_weights
        shrinkage = discovery.constrained_fixed_shrinkage_weights
        portfolio = original.evaluate_synthetic_portfolio
        task, inputs = fixture()
        result = revised.evaluate_joint_weight_task_v2(task, **inputs)
        self.assertEqual(result['tickers'], task['tickers'])
        self.assertIs(discovery.project_concentration_envelope_weights, projection)
        self.assertIs(discovery.constrained_fixed_shrinkage_weights, shrinkage)
        self.assertIs(original.evaluate_synthetic_portfolio, portfolio)
        self.assertIs(revised._EVALUATE.__globals__['evaluate_synthetic_portfolio'], revised._PORTFOLIO)
        self.assertIs(revised._PORTFOLIO.__globals__['constrained_fixed_shrinkage_weights'], revised._SHRINKAGE)
        self.assertIs(revised._SHRINKAGE.__globals__['project_concentration_envelope_weights'],
                      revised.project_concentration_envelope_weights_v2)

    def test_source_drift_rejected_before_evaluation(self):
        task, inputs = fixture()
        with patch.object(revised, 'source_hashes', return_value={}):
            with self.assertRaisesRegex(ValueError, 'changed since import'):
                revised.evaluate_joint_weight_task_v2(task, **inputs)


if __name__ == '__main__':
    unittest.main()
