"""Independent return equations and causal whole-lot scheduling tests."""
from copy import deepcopy
from fractions import Fraction
import unittest
from backtest import ndx_dynamic_frozen_flow_split_research as core
from test_ndx_dynamic_frozen_flow_split_research import fixture, flow, split


class Review(unittest.TestCase):
    def test_open_flow_boundary_has_two_distinct_return_segments(self):
        a = fixture(); day = str(a['closes'].index[2].date())
        a['external_flows'] = [flow(day, 1000.)]
        a['opens'].iloc[2, 0] = 12.
        a['closes'].iloc[2:, 0] = 11.
        a['opens'].iloc[3:, 0] = 11.
        out = core.simulate_dynamic_frozen_flow_split_research(**a)
        # Old state cash100 + 90shares: overnight1180; after1000receipt,
        # intraday Close2090. Neither 109% capital growth nor 9% total PNL is TWR.
        expected = Fraction(1180, 1000) * Fraction(2090, 2180) - 1
        self.assertAlmostEqual(out['summary']['chained_twr'], float(expected), places=13)
        self.assertEqual(out['summary']['terminal_value_usd'], 2090.)
        self.assertEqual(out['summary']['net_dollar_pnl_excluding_injections_usd'], 90.)
        self.assertEqual(len(out['trades']), 1)

    def test_receipt_can_affect_later_close_only_and_failed_open_no_resize(self):
        a = fixture(); initial = core.simulate_dynamic_frozen_flow_split_research(**a)
        execution = a['schedule'][0]['execution_date']
        a['external_flows'] = [flow(execution)]
        # After credit at first execution, next Close may plan with that cash.
        decision = str(a['closes'].index[2].date()); next_open = str(a['closes'].index[3].date())
        a['schedule'].append({**deepcopy(a['schedule'][0]), 'decision_date': decision, 'execution_date': next_open})
        a['risk_chains_by_decision'][decision] = {'A': 'chain'}
        out = core.simulate_dynamic_frozen_flow_split_research(**a)
        self.assertEqual(out['decisions'][0], initial['decisions'][0])
        self.assertEqual(out['decisions'][1]['desired_shares'], {'A': 190})
        self.assertEqual(out['daily'][-1]['shares'], {'A': 190})
        a['opens'].iloc[3, 0] = 100.
        rejected = core.simulate_dynamic_frozen_flow_split_research(**a)
        self.assertEqual(rejected['executions'][-1]['status'], 'REJECTED')
        self.assertEqual(rejected['daily'][-1]['shares'], {'A': 90})
        self.assertEqual(rejected['daily'][-1]['cash_usd'], 1100.)
        self.assertEqual(len(rejected['trades']), 1)

    def test_event_identity_and_fractional_reverse_entitlement_fail_closed(self):
        a = fixture(); day = str(a['closes'].index[2].date())
        e = flow(day, 1.); a['external_flows'] = [e, {**e, 'amount_usd': 2.}]
        with self.assertRaises(ValueError): core.simulate_dynamic_frozen_flow_split_research(**a)
        for v in (True, float('nan'), '1000'):
            with self.subTest(value=v):
                a = fixture(); a['external_flows'] = [flow(day, v)]
                with self.assertRaises(ValueError): core.simulate_dynamic_frozen_flow_split_research(**a)
        a = fixture(); e = split(day); e.update(new_shares=1, old_shares=7)
        a['corporate_actions'] = [e]
        with self.assertRaises(ValueError): core.simulate_dynamic_frozen_flow_split_research(**a)


if __name__ == '__main__': unittest.main()
