"""Independent small-domain financial accounting oracle for incumbent control."""
import itertools
import unittest

from backtest.ndx_incumbent_integer_control_research import search_incumbent_integer_control_domain as search


class IncumbentControlOracleTests(unittest.TestCase):
    def test_cash_fee_tracking_and_pareto_against_direct_equations(self):
        marks = {'A': 7., 'B': 11.}
        initial = {'A': 2, 'B': 1}
        cash, buffer, rate = 40., 5., .01
        target = {'A': .2, 'B': .8}
        risks = dict(max_single_weight=.45, min_single_weight=.05, top_weight_cap=.8,
                     minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55)
        result = search(prices=marks, target_weights=target, current_shares=initial,
            current_cash=cash, minimum_cash_buffer_usd=buffer, transaction_cost_bps=100.,
            risk_chain_by_ticker={'A': 'shared', 'B': 'shared'}, constraints=risks,
            share_domains={'A': list(range(5)), 'B': list(range(5))}, max_evaluations=25)
        valid = []
        initial_equity = cash + 25.
        for a, b in itertools.product(range(5), repeat=2):
            fee = (abs(a-2)*7 + abs(b-1)*11)*rate
            remaining = initial_equity-a*7-b*11-fee
            equity = initial_equity-fee
            if remaining < buffer:
                continue
            error = ((a*7-.2*(equity-buffer))/equity)**2
            error += ((b*11-.8*(equity-buffer))/equity)**2
            error += ((remaining-buffer)/equity)**2
            valid.append(((a, b), error, fee, remaining))
        expected = [r for r in valid if not any(
            other[1] <= r[1] and other[2] <= r[2] and (other[1] < r[1] or other[2] < r[2])
            for other in valid)]
        self.assertEqual(result['feasible_evaluated'], len(valid))
        self.assertEqual({tuple(r['shares'].values()) for r in result['pareto']}, {r[0] for r in expected})
        selected = min(valid, key=lambda r: (r[1], r[2], r[0]))
        actual = result['selected_tracking_first']
        self.assertEqual(tuple(actual['shares'].values()), selected[0])
        self.assertAlmostEqual(actual['total_tracking_error_including_cash'], selected[1])
        self.assertAlmostEqual(actual['fees_usd'], selected[2])
        self.assertAlmostEqual(actual['posttrade_cash_usd'], selected[3])
        # Both securities share a chain: strict candidate risk cannot pass, but
        # that does not erase the original control's financial path.
        self.assertFalse(actual['risk_constraints_passed'])
        self.assertFalse(result['candidate_eligibility'])


if __name__ == '__main__':
    unittest.main()
