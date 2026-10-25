from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from data.strategy_continuous32_target_decision import (
    decide_target, validate_result, REQUIRED_PINS, PROFILE_ID, VERSION,
)
from backtest.continuous_guided_account_decision import enhanced_search
from test_strategy_account_target_inputs import setup

ROOT = Path(__file__).resolve().parents[1]


class ContinuousTargetTests(unittest.TestCase):
    def arguments(self, folder):
        args = setup(folder)
        package = args['source_package']
        for path in REQUIRED_PINS:
            raw = (ROOT / path).read_bytes()
            package['files'][path] = raw
            package['source_hashes'][path] = sha256(raw).hexdigest()
        return args

    def test_tiny_actual_selector_identity_capital_and_no_mutation(self):
        with TemporaryDirectory() as folder:
            args = self.arguments(folder)
            before = deepcopy(args)
            with patch('data.strategy_continuous32_target_decision.enhanced_search',
                       wraps=enhanced_search) as selector:
                result = decide_target(**args)
            self.assertEqual(selector.call_count, 1)
            payload = result['payload']
            binding = payload['input_binding']
            self.assertEqual(binding['selector_profile'], PROFILE_ID)
            self.assertEqual(binding['selection_method'], VERSION)
            self.assertEqual(binding['strategy_equity'], '140')
            self.assertEqual(binding['strategy_shares'], {'A': 2})
            self.assertEqual(binding['continuous_iterations'], 32)
            self.assertEqual(sha256(canonical(payload)).hexdigest(), result['decision_id'])
            self.assertEqual(sha256(canonical(binding)).hexdigest(), payload['input_id'])
            self.assertEqual(payload['search_result']['continuous_comparison']
                             ['additional_generation']['iterations_requested'], 32)
            self.assertEqual(args, before)

    def test_tampered_profile_comparison_and_arithmetic_rejected(self):
        with TemporaryDirectory() as folder:
            result = decide_target(**self.arguments(folder))
            payload = result['payload']
            for mode in ('method', 'cash', 'iteration', 'selected', 'provenance', 'budget'):
                with self.subTest(mode=mode):
                    bad = deepcopy(payload['search_result'])
                    if mode == 'method': bad['method_version'] = 'EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2'
                    if mode == 'cash': bad['selected']['residual_cash'] = '999'
                    if mode == 'iteration': bad['continuous_comparison']['additional_generation']['iterations_requested'] = 31
                    if mode == 'selected': bad['selected']['quantities'] = {'UNKNOWN': 1}
                    if mode == 'provenance': bad['continuous_comparison']['binding']['provenance'] = 'SAVED'
                    if mode == 'budget': bad['objective_evaluations_scope'] = '8192_TOTAL'
                    with self.assertRaises(ValueError):
                        validate_result(bad, payload['input_binding']['search_arguments'])

    def test_pin_change_rejected_before_selection(self):
        with TemporaryDirectory() as folder:
            args = self.arguments(folder)
            path = 'backtest/continuous_guided_account_decision.py'
            package = args['source_package']
            package['files'][path] += b'\n'
            package['source_hashes'][path] = sha256(package['files'][path]).hexdigest()
            with patch('data.strategy_continuous32_target_decision.enhanced_search') as selector:
                with self.assertRaisesRegex(ValueError, 'CONTINUOUS32_RUNTIME_SOURCE_CHANGED'):
                    decide_target(**args)
                selector.assert_not_called()

    def test_insufficient_budget_remains_incomplete(self):
        # Two inexpensive synthetic securities need more than one mandatory
        # evaluation. This checks the real stop branch, not a historical search.
        arguments = dict(prices={'A': '1', 'B': '1'},
            metadata={'A': {'issuer_id': 'A', 'ticker': 'A'},
                      'B': {'issuer_id': 'B', 'ticker': 'B'}},
            entered_cash='10', fee_bps='0', minimum_cash_buffer='0',
            training_scenarios=[{'A': '1.1', 'B': '1.2'}],
            scenario_dates=['2026-01-01'], decision_date='2026-01-02',
            max_objective_evaluations=1, fixed_seed='tiny-incomplete')
        result = enhanced_search(**arguments)
        self.assertIsNone(result['selected'])
        self.assertIsNone(validate_result(result, arguments))
        bad = deepcopy(result)
        bad['additional_candidate_status'] = 'COMPLETE'
        with self.assertRaises(ValueError):
            validate_result(bad, arguments)


if __name__ == '__main__':
    unittest.main()
