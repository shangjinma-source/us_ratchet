import unittest
from copy import deepcopy
from unittest.mock import patch
import pandas as pd
from backtest import ndx_dynamic_frozen_execution_research as candidate
from backtest import ndx_dynamic_frozen_incumbent_control as control


class IncumbentControlTests(unittest.TestCase):
    def fixture(self):
        dates = pd.bdate_range('2024-01-02', periods=4)
        prices = pd.DataFrame(10., index=dates, columns=['A', 'B'])
        targets = {key: dict(ticker=key, issuer_id=key, target_weight=weight)
                   for key, weight in [('A', .96), ('B', .04)]}
        schedule = [dict(decision_date=str(dates[0].date()), execution_date=str(dates[1].date()), targets=targets)]
        return dict(closes=prices, opens=prices.copy(), schedule=schedule,
            risk_chains_by_decision={schedule[0]['decision_date']: {'A': 'a', 'B': 'b'}},
            corporate_actions=[], initial_cash_usd=1000., minimum_cash_buffer_usd=100.,
            valuation_end_date=str(dates[-1].date()), transaction_cost_bps=10.)

    def test_risk_failure_observed_not_gate_or_fake_pass(self):
        args = self.fixture()
        result = control.simulate_dynamic_frozen_incumbent_control(**args)
        self.assertEqual(result['executions'][0]['status'], 'FILLED')
        self.assertFalse(result['executions'][0]['risk']['all_passed'])
        self.assertFalse(result['decisions'][0]['decision_risk']['all_passed'])
        self.assertEqual(result['decisions'][0]['desired_shares'], {'A': 86, 'B': 3})
        self.assertFalse(result['original_target_weights_modified'])
        self.assertEqual(result['decisions'][0]['targets'], args['schedule'][0]['targets'])

    def test_open_cash_rejection_no_resizing_or_retry(self):
        args = self.fixture()
        before = control.simulate_dynamic_frozen_incumbent_control(**args)
        args['opens'].iloc[1] = 1000.
        after = control.simulate_dynamic_frozen_incumbent_control(**args)
        self.assertEqual(before['decisions'], after['decisions'])
        self.assertEqual(after['executions'][0]['failure_reasons'], ['CASH_BUFFER'])
        self.assertEqual(after['trades'], [])
        self.assertEqual(len(after['executions']), 1)

    def test_zero_share_slot_observed_and_no_risk_projection(self):
        args = self.fixture()
        args['closes']['B'] = 1000.
        args['opens']['B'] = 1000.
        result = control.simulate_dynamic_frozen_incumbent_control(**args)
        self.assertEqual(result['executions'][0]['status'], 'FILLED')
        self.assertEqual(result['decisions'][0]['desired_shares']['B'], 0)
        self.assertFalse(result['daily'][-1]['risk']['all_passed'])

    def test_candidate_globals_unchanged_and_fixed_target_guard(self):
        before = dict(candidate.simulate_dynamic_frozen_execution_research.__globals__)
        args = self.fixture()
        control.simulate_dynamic_frozen_incumbent_control(**args)
        self.assertTrue(all(candidate.simulate_dynamic_frozen_execution_research.__globals__[key] is value
                            for key, value in before.items()))
        second = deepcopy(args['schedule'][0]); second['targets']['A']['target_weight'] = .8
        args['schedule'].append(second)
        with self.assertRaisesRegex(ValueError, 'remain fixed'):
            control.simulate_dynamic_frozen_incumbent_control(**args)

    def test_source_guard(self):
        with patch.object(control, '_LOADED_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'source drift'):
                control.simulate_dynamic_frozen_incumbent_control(**self.fixture())

    def test_original_weights_not_renormalized(self):
        args = self.fixture()
        args['schedule'][0]['targets']['A']['target_weight'] = .9600000000000002
        result = control.simulate_dynamic_frozen_incumbent_control(**args)
        self.assertEqual(result['decisions'][0]['targets'], args['schedule'][0]['targets'])
        args['schedule'][0]['targets']['A']['target_weight'] = 2.
        with self.assertRaisesRegex(ValueError, 'already sum to one'):
            control.simulate_dynamic_frozen_incumbent_control(**args)


if __name__ == '__main__':
    unittest.main()
