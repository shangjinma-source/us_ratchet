import copy
import unittest

import pandas as pd

from backtest.ndx_integer_rebalance_research import simulate_integer_rebalance_research as simulate


def fixture():
    dates=pd.date_range('2020-01-01',periods=3)
    names=['A','B','C','D']
    return dict(prices=pd.DataFrame({t:[10.,10.,10.] for t in names},index=dates),
        schedule=[(dates[0],{t:.25 for t in names}),(dates[2],{t:.25 for t in names})],
        initial_cash=1000.,initial_shares={t:0 for t in names},minimum_cash_buffer_usd=100.,
        transaction_cost_bps=10.,risk_chain_by_ticker={t:t for t in names},
        constraints=dict(max_single_weight=.5,min_single_weight=.1,top_weight_cap=.9,
                         minimum_effective_n_ratio=.5,risk_chain_top1_cap=.5),
        domain_radius=1,max_evaluations_per_rebalance=10000,selection_policy='TRACKING_FIRST')


class IntegerRebalanceResearchTests(unittest.TestCase):
    def test_self_financing_no_implicit_daily_trade_and_fee_drawdown(self):
        inputs=fixture();before=copy.deepcopy(inputs)
        result=simulate(**inputs)
        self.assertFalse(result['any_partial_search'])
        self.assertFalse(result['any_unresolved_rebalance'])
        self.assertEqual(result['daily'][0]['shares'],result['daily'][1]['shares'])
        self.assertEqual(result['daily'][0]['cash_usd'],result['daily'][1]['cash_usd'])
        self.assertGreaterEqual(result['path_max_drawdown'],result['rebalances'][0]['fees_usd']/result['initial_equity_usd']-1e-12)
        for row in result['rebalances']:
            marks=inputs['prices'].loc[row['date']]
            traded=sum(abs(row['selected_shares'][t]-row['previous_shares'][t])*marks[t] for t in marks.index)
            self.assertAlmostEqual(row['fees_usd'],traded*.001)
            equity=row['posttrade_cash_usd']+sum(row['selected_shares'][t]*marks[t] for t in marks.index)
            self.assertAlmostEqual(equity,row['pretrade_equity_usd']-row['fees_usd'])
        pd.testing.assert_frame_equal(inputs['prices'],before['prices'])
        self.assertEqual(inputs['initial_shares'],before['initial_shares'])

    def test_future_prices_and_future_targets_do_not_change_earlier_actions(self):
        original=fixture();first=simulate(**original)
        revised=copy.deepcopy(original)
        revised['prices'].iloc[-1]=[30.,20.,8.,12.]
        revised['schedule'][-1]=(revised['prices'].index[-1],{'A':.4,'B':.2,'C':.2,'D':.2})
        second=simulate(**revised)
        self.assertEqual(first['rebalances'][0],second['rebalances'][0])
        self.assertEqual(first['daily'][:2],second['daily'][:2])
        self.assertFalse(second['signal_timing_verified'])

    def test_unresolved_and_partial_do_not_claim_complete(self):
        inputs=fixture();inputs.update(initial_cash=1.,domain_radius=0)
        inputs['prices'][:]=1000.
        result=simulate(**inputs)
        self.assertEqual(result['status'],'UNRESOLVED')
        self.assertTrue(result['any_unresolved_rebalance'])
        self.assertEqual(result['terminal_cash_usd'],1.)
        self.assertEqual(result['total_fees_usd'],0.)
        self.assertFalse(result['all_days_constraints_passed'])
        inputs=fixture();inputs.update(initial_shares={t:1 for t in inputs['prices']},
            initial_cash=400.,domain_radius=0,max_evaluations_per_rebalance=1)
        result=simulate(**inputs)
        self.assertTrue(result['any_partial_search'])
        self.assertEqual(result['rebalances'][0]['status'],'BEST_OBSERVED_PARTIAL_DOMAIN')
        self.assertFalse(result['rebalances'][0]['finite_domain_complete'])

    def test_initial_shares_count_toward_equity_and_policy_is_explicit(self):
        inputs=fixture();inputs.update(initial_shares={t:1 for t in inputs['prices']},selection_policy='FEES_FIRST')
        result=simulate(**inputs)
        self.assertEqual(result['initial_equity_usd'],1040.)
        self.assertFalse(result['global_allocation_optimality_claim_allowed'])
        inputs['selection_policy']='OPTIMIZE_FUTURE_RETURNS'
        with self.assertRaises(ValueError):simulate(**inputs)

    def test_bad_calendar_values_and_changing_ticker_set_fail(self):
        mutations=[lambda x:x.update(prices=x['prices'].iloc[::-1]),
            lambda x:x.update(schedule=[x['schedule'][0],x['schedule'][0]]),
            lambda x:x['prices'].iloc.__setitem__((1,0),float('nan')),
            lambda x:x['schedule'][0][1].pop('A'),lambda x:x.update(domain_radius=True)]
        for mutation in mutations:
            inputs=fixture();mutation(inputs)
            with self.assertRaises(ValueError):simulate(**inputs)


if __name__=='__main__':
    unittest.main()
