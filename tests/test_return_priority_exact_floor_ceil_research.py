"""Small artificial price vectors only; never rerun the saved actual64 case."""
from fractions import Fraction
import unittest

from backtest.return_priority_exact_floor_ceil_research import project_exact_floor_ceil, ProjectionInputError


def arguments(exposure='1', equal_prices=False):
    securities = [f'S{index}' for index in range(6)]
    ratio = Fraction(exposure)
    capacity = 4890
    prices = dict(zip(securities, [100] * 6 if equal_prices else [1000, 700, 300, 100, 250, 500]))
    if not equal_prices:
        prices = {security: float(price * ratio) for security, price in prices.items()}
    floor = {security: int(Fraction(capacity) * ratio / 6 // Fraction(str(prices[security]))) for security in securities}
    return dict(candidate={
        'method_rule_id': 'SYNTHETIC', 'status': 'LEGAL_INDICATIVE_ONLY' if equal_prices else 'BLOCKED',
        'blocked_reasons': [] if equal_prices else ['ZERO_QUANTITY_REQUESTED_MEMBER'],
        'requested_k': 6, 'security_ids': securities,
        'target_weights': {security: str(ratio / 6) for security in securities},
        'stock_internal_profile_weights': {security: '1/6' for security in securities},
        'sizing_capacity': str(capacity), 'indicative_quantities': floor,
    }, prices=prices,
        metadata={security: {'ticker': security, 'issuer_id': security, 'risk_chain': security} for security in securities},
        risk_parameters=dict(min_single_weight='0.05', max_single_weight='0.45', top_three_cap='0.8',
                             min_neff_ratio='0.7', chain_cap='0.55'),
        entered_cash=5000, fee_bps=10, minimum_cash_buffer=100, max_evaluations=64)


class ExactProjectionTests(unittest.TestCase):
    def test_three_exposures_exact_neighborhood_and_full_cash_identity(self):
        for exposure in ('1/2', '3/4', '1'):
            with self.subTest(exposure=exposure):
                values = arguments(exposure)
                result = project_exact_floor_ceil(**values)
                self.assertEqual(result['status'], 'FEASIBLE')
                self.assertTrue(result['search_complete'])
                self.assertEqual(result['neighborhood_evaluations'], 64)
                self.assertEqual(result['candidate_evaluations'], 64)
                projected = result['projection']
                self.assertEqual(projected['actual_k'], 6)
                self.assertTrue(projected['risk']['all_passed'])
                self.assertEqual(sum(Fraction(projected[key]) for key in ('buy_notional', 'buy_fee', 'residual_cash')), 5000)
                self.assertGreaterEqual(Fraction(projected['residual_cash']), 100)
                self.assertEqual(Fraction(projected['target_buy_notional']), 4890 * Fraction(exposure))
                self.assertLessEqual(Fraction(projected['buy_notional']), Fraction(projected['target_buy_notional']))
                self.assertTrue(projected['frozen_stock_budget_passed'])
                for security, quantity in projected['quantities'].items():
                    raw = Fraction(4890) * Fraction(values['candidate']['target_weights'][security]) / Fraction(str(values['prices'][security]))
                    self.assertIn(quantity, {raw.numerator // raw.denominator, -(-raw.numerator // raw.denominator)})

    def test_legal_original_floor_unchanged_without_search(self):
        values = arguments(equal_prices=True)
        result = project_exact_floor_ceil(**values)
        self.assertEqual(result['status'], 'FEASIBLE')
        self.assertEqual(result['projection']['quantities'], values['candidate']['indicative_quantities'])
        self.assertEqual(result['neighborhood_evaluations'], 0)
        self.assertEqual(result['candidate_evaluations'], 1)
        self.assertFalse(result['search_complete'])

    def test_budget_exhaustion_never_returns_partial_or_infeasibility(self):
        values = arguments()
        values['max_evaluations'] = 63
        result = project_exact_floor_ceil(**values)
        self.assertEqual(result['status'], 'SEARCH_BUDGET_EXHAUSTED')
        self.assertEqual(result['search_space_size'], 64)
        self.assertEqual(result['neighborhood_evaluations'], 0)
        self.assertFalse(result['search_complete'])
        self.assertIsNone(result['projection'])
        self.assertFalse(result['full_integer_infeasibility_claimed'])

    def test_profile_failure_capacity_tamper_and_duplicate_issuer_rejected(self):
        values = arguments()
        values['risk_parameters']['chain_cap'] = '0.1'
        with self.assertRaises(ProjectionInputError):
            project_exact_floor_ceil(**values)
        values = arguments()
        values['candidate']['sizing_capacity'] = '4900'
        with self.assertRaises(ProjectionInputError):
            project_exact_floor_ceil(**values)
        values = arguments()
        values['metadata']['S1']['issuer_id'] = 'S0'
        with self.assertRaises(ProjectionInputError):
            project_exact_floor_ceil(**values)

    def test_complete_infeasible_neighborhood_is_not_global_infeasibility(self):
        values = arguments()
        values['prices'] = {security: 10000 for security in values['prices']}
        values['candidate']['indicative_quantities'] = {security: 0 for security in values['prices']}
        result = project_exact_floor_ceil(**values)
        self.assertEqual(result['status'], 'NO_FEASIBLE_IN_NEIGHBORHOOD')
        self.assertEqual(result['neighborhood_evaluations'], 64)
        self.assertEqual(result['candidate_evaluations'], 64)
        self.assertTrue(result['search_complete'])
        self.assertEqual(result['feasible_candidates'], 0)
        self.assertIsNone(result['projection'])
        self.assertFalse(result['full_integer_infeasibility_claimed'])

    def test_half_stock_allocation_cannot_borrow_frozen_strategic_cash(self):
        values = arguments()
        securities = ['S0', 'S1', 'S2', 'S3']
        values['candidate'].update(requested_k=4, security_ids=securities, sizing_capacity='100',
                                   target_weights={security: '1/8' for security in securities},
                                   stock_internal_profile_weights={security: '1/4' for security in securities},
                                   indicative_quantities={security: 0 for security in securities})
        values.update(entered_cash=100, fee_bps=0, minimum_cash_buffer=0,
                      prices={security: 20 for security in securities}, max_evaluations=16)
        result = project_exact_floor_ceil(**values)
        self.assertEqual(result['status'], 'NO_FEASIBLE_IN_NEIGHBORHOOD')
        self.assertEqual(result['neighborhood_evaluations'], 16)
        self.assertIsNone(result['projection'])


if __name__ == '__main__':
    unittest.main()
