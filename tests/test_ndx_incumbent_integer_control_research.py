import copy
import math
import unittest

from backtest.ndx_incumbent_integer_control_research import search_incumbent_integer_control_domain as search


def fixture():
    return dict(prices={'A': 10., 'B': 10.}, target_weights={'A': .5, 'B': .5},
        current_shares={'A': 0, 'B': 0}, current_cash=100., transaction_cost_bps=10.,
        minimum_cash_buffer_usd=10., risk_chain_by_ticker={'A': 'X', 'B': 'Y'},
        constraints=dict(max_single_weight=.45, min_single_weight=.05, top_weight_cap=.8,
                         minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55),
        share_domains={'A': [0, 1, 4, 5], 'B': [0, 1, 4, 5]}, max_evaluations=100)


class IncumbentControlTests(unittest.TestCase):
    def test_original_low_weights_remain_financially_feasible_without_projection(self):
        weights = dict(ASML=.07546880966248519, CDNS=.16892456638295553,
            GOOG=.1425301028856187, MSFT=.2076364461790495, MU=.04305324115213593,
            NVDA=.13267616984661298, TSM=.04670905030960705, TXN=.18300161358153513)
        inputs = fixture()
        inputs.update(prices={t: 1. for t in weights}, target_weights=weights,
            current_shares={t: 0 for t in weights}, current_cash=100100.,
            minimum_cash_buffer_usd=100., transaction_cost_bps=0.,
            risk_chain_by_ticker={t: t for t in weights},
            share_domains={t: [math.floor(100000 * w)] for t, w in weights.items()})
        before = copy.deepcopy(inputs)
        result = search(**inputs)
        self.assertEqual(result['feasible_evaluated'], 1)
        self.assertEqual(result['target_weights'], weights)
        self.assertFalse(result['target_weights_projected'])
        selected = result['selected_tracking_first']
        self.assertIn('WEIGHT_FLOOR', selected['risk_failure_reasons'])
        self.assertLess(selected['security_weights']['MU'], .05)
        self.assertLess(selected['security_weights']['TSM'], .05)
        self.assertFalse(result['candidate_eligibility'])
        self.assertEqual(result['role'], 'INCUMBENT_CONTROL')
        self.assertEqual(inputs, before)

    def test_tracking_selects_deployment_over_fee_minimizing_idle_cash(self):
        result = search(**fixture())
        self.assertGreater(sum(result['selected_tracking_first']['shares'].values()), 0)
        self.assertTrue(any(sum(row['shares'].values()) == 0 for row in result['pareto']))
        self.assertFalse(result['promotion_allowed'])
        self.assertFalse(result['order_generation_allowed'])

    def test_actual_gross_fees_and_cash_conserved_for_sales_and_purchases(self):
        inputs = fixture()
        inputs.update(current_shares={'A': 5, 'B': 0}, share_domains={'A': [2], 'B': [3]})
        selected = search(**inputs)['selected_tracking_first']
        self.assertAlmostEqual(selected['fees_usd'], .06)
        self.assertAlmostEqual(selected['posttrade_cash_usd'], 99.94)
        self.assertAlmostEqual(selected['posttrade_cash_usd'] + 50., 150. - selected['fees_usd'])

    def test_cash_buffer_rejects_financially_impossible_vector(self):
        inputs = fixture()
        inputs['share_domains'] = {'A': [5], 'B': [5]}
        result = search(**inputs)
        self.assertEqual(result['feasible_evaluated'], 0)
        self.assertIsNone(result['selected_tracking_first'])
        self.assertEqual(result['failure_counts']['CASH_BUFFER'], 1)
        self.assertEqual(result['risk_failure_counts'], {})

    def test_zero_shares_all_cash_and_partial_unexamined_are_not_infeasible(self):
        inputs = fixture()
        inputs['max_evaluations'] = 1
        result = search(**inputs)
        self.assertEqual((result['finite_domain_size'], result['evaluated'], result['unexamined']), (16, 1, 15))
        self.assertEqual(result['infeasible_evaluated'], 0)
        self.assertFalse(result['pareto_complete_within_explicit_domain'])
        selected = result['selected_tracking_first']
        self.assertEqual(selected['effective_n'], 0.)
        self.assertIn('NO_INVESTED_EQUITY', selected['risk_failure_reasons'])
        self.assertIn('MINIMUM_ONE_SHARE', selected['risk_failure_reasons'])
        self.assertTrue(math.isfinite(selected['total_tracking_error_including_cash']))
        self.assertFalse(result['global_share_space_exhausted'])

    def test_poisoned_inputs_rejected(self):
        for change in ({'max_evaluations': True}, {'current_cash': float('nan')},
                       {'share_domains': {'A': [True], 'B': [0]}},
                       {'target_weights': {'A': .6, 'B': .6}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                search(**{**fixture(), **change})


if __name__ == '__main__':
    unittest.main()
