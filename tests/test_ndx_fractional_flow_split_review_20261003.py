"""Independent small cash equations and causal-input rejection examples."""
import copy
import unittest
import pandas as pd
from backtest import ndx_dynamic_fractional_flow_split_research as core


def inputs():
    days = ['2026-03-31', '2026-04-01', '2026-04-02', '2026-04-03']
    frame = pd.DataFrame({'AAA': [10.] * 4, 'BBB': [20.] * 4}, index=pd.to_datetime(days))
    return dict(closes=frame, opens=frame.copy(), schedule=[dict(decision_date=days[0],
        execution_date=days[1], targets={'SID_A': dict(ticker='AAA', issuer_id='ISS_A', target_weight=1.)})],
        corporate_actions=[], external_flows=[], initial_cash_usd=110., minimum_cash_buffer_usd=10.,
        transaction_cost_bps=10., valuation_end_date=days[-1])


class Review(unittest.TestCase):
    def test_fee_cash_equations_and_no_input_mutation(self):
        a = inputs()
        original = copy.deepcopy(a)
        result = core.simulate_dynamic_fractional_flow_split_research(**a)
        # One buy: x + .001*x + buffer = initial capital.
        notional = 100. / 1.001
        self.assertAlmostEqual(result['summary']['total_fees_usd'], notional * .001, places=11)
        self.assertAlmostEqual(result['daily'][-1]['cash_usd'], 10., places=11)
        self.assertAlmostEqual(result['summary']['chained_twr'], -notional * .001 / 110., places=13)
        self.assertAlmostEqual(result['summary']['max_drawdown_twr'], notional * .001 / 110., places=13)
        pd.testing.assert_frame_equal(a['closes'], original['closes'])
        self.assertEqual(a['schedule'], original['schedule'])
        second = core.simulate_dynamic_fractional_flow_split_research(**a)
        result['daily'][-1]['holdings']['SID_A']['shares'] = 999.
        self.assertNotEqual(second['daily'][-1]['holdings']['SID_A']['shares'], 999.)

    def test_each_decision_requires_saved_close_and_no_unbridged_rename(self):
        a = inputs()
        a['closes'] = a['closes'].drop(pd.Timestamp('2026-04-02'))
        a['opens'] = a['opens'].drop(pd.Timestamp('2026-04-02'))
        a['schedule'].append(dict(decision_date='2026-04-02', execution_date='2026-04-03',
            targets=copy.deepcopy(a['schedule'][0]['targets'])))
        with self.assertRaises(ValueError):
            core.simulate_dynamic_fractional_flow_split_research(**a)
        a = inputs()
        # Equal prices deliberately prevent a conservation error masking identity acceptance.
        a['closes']['BBB'] = 10.; a['opens']['BBB'] = 10.
        targets = copy.deepcopy(a['schedule'][0]['targets'])
        targets['SID_A']['ticker'] = 'BBB'
        a['schedule'].append(dict(decision_date='2026-04-02', execution_date='2026-04-03', targets=targets))
        with self.assertRaises(ValueError):
            core.simulate_dynamic_fractional_flow_split_research(**a)

    def test_malformed_cash_events_and_bool_prices_rejected(self):
        event = dict(session='2026-04-02', amount_usd=0., timing='BEFORE_OPEN', currency='USD',
            source_reference=dict(path='E:/synthetic/receipt.json', sha256='b' * 64))
        for key, value in [('amount_usd', True), ('amount_usd', -1.), ('amount_usd', float('inf')),
                           ('currency', 'CNY'), ('timing', 'AFTER_CLOSE'), ('session', '2026-04-04')]:
            with self.subTest(key=key, value=value):
                a = inputs(); e = copy.deepcopy(event); e[key] = value; a['external_flows'] = [e]
                with self.assertRaises(ValueError): core.simulate_dynamic_fractional_flow_split_research(**a)
        a = inputs(); a['external_flows'] = [event, copy.deepcopy(event)]
        with self.assertRaises(ValueError): core.simulate_dynamic_fractional_flow_split_research(**a)
        a = inputs(); a['opens'] = a['opens'].astype(object); a['opens'].iloc[1, 0] = True
        with self.assertRaises(ValueError): core.simulate_dynamic_fractional_flow_split_research(**a)


if __name__ == '__main__': unittest.main()
