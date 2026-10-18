"""Analytical account examples independent of the implementation's ledger formulas."""
import unittest
import pandas as pd
from backtest.ndx_dynamic_fractional_flow_split_research import simulate_dynamic_fractional_flow_split_research


class IndependentCashAndSplit(unittest.TestCase):
    def run_account(self, rebalance_on_split):
        days = ['2026-03-31','2026-04-01','2026-04-02']
        prices = pd.DataFrame({'AAA':[10.,10.,6.]}, index=pd.to_datetime(days))
        target = {'SEC_A':dict(ticker='AAA',issuer_id='ISS_A',target_weight=1.)}
        schedule = [dict(decision_date=days[0],execution_date=days[1],targets=target)]
        if rebalance_on_split:
            schedule.append(dict(decision_date=days[1],execution_date=days[2],targets=target))
        return simulate_dynamic_fractional_flow_split_research(closes=prices,opens=prices,
            schedule=schedule,corporate_actions=[dict(security_id='SEC_A',session=days[2],
                new_shares=2,old_shares=1,source_url='https://example.com/synthetic-split',evidence_sha256='a'*64)],
            external_flows=[dict(session=days[2],amount_usd=120.,timing='BEFORE_OPEN',currency='USD',
                source_reference=dict(path='/synthetic/cash-receipt',sha256='b'*64))],
            initial_cash_usd=100.,minimum_cash_buffer_usd=0.,transaction_cost_bps=0.,valuation_end_date=days[2])

    def test_nonscheduled_injection_remains_cash_and_excludes_itself_from_return(self):
        result = self.run_account(False)
        final = result['daily'][-1]
        # Ten old shares become twenty. At $6 they earn $20; $120 is contributed cash.
        self.assertAlmostEqual(final['holdings']['SEC_A']['shares'],20.)
        self.assertAlmostEqual(final['cash_usd'],120.)
        self.assertAlmostEqual(final['close_equity_usd'],240.)
        self.assertAlmostEqual(result['summary']['chained_twr'],.2)
        self.assertAlmostEqual(result['summary']['net_dollar_pnl_excluding_injections_usd'],20.)
        self.assertEqual(len(result['trades']),1)

    def test_split_precedes_new_purchases_and_never_doubles_new_shares(self):
        result = self.run_account(True)
        final = result['daily'][-1]
        # Twenty old post-split shares plus twenty new shares bought with the injection.
        self.assertAlmostEqual(final['holdings']['SEC_A']['shares'],40.)
        self.assertAlmostEqual(final['cash_usd'],0.)
        self.assertAlmostEqual(final['close_equity_usd'],240.)
        self.assertAlmostEqual(result['summary']['chained_twr'],.2)
        self.assertEqual(result['corporate_actions'][0]['shares_before'],10.)
        self.assertEqual(result['corporate_actions'][0]['shares_after'],20.)
        self.assertAlmostEqual(result['trades'][-1]['share_delta'],20.)


if __name__ == '__main__': unittest.main()
