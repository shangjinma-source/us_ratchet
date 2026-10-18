import unittest
from backtest.ndx_legacy_close_accounting_oracle_research import account


def contract(**changes):
    return dict(dict(portfolio_cash_usd=1000.,minimum_cash_buffer_usd=100.,transaction_cost_bps=0.,
        max_single_weight=1.,min_single_weight=0.,top_weight_cap=1.,minimum_effective_n_ratio=0.,risk_chain_top1_cap=1.),**changes)


class DecimalAccountingTests(unittest.TestCase):
    def test_hand_account_cash_shares_gain_drawdown(self):
        r=account(dates=['2020-01-01','2020-01-02','2020-01-03'],prices={'A':[100.,110.,90.]},
            schedule={'2020-01-01':{'A':1.}},risk_chains={'A':'x'},contract=contract())
        self.assertEqual(r['daily'][0]['shares'],{'A':9})
        self.assertEqual(r['daily'][1]['value'],1090.)
        self.assertEqual(r['summary']['whole_lot_terminal_value_usd'],910.)
        self.assertAlmostEqual(r['summary']['whole_lot_path_max_drawdown'],180/1090)

    def test_fees_trim_highest_price_then_ticker_to_preserve_buffer(self):
        r=account(dates=['2020-01-01'],prices={'A':[100.],'B':[100.]},schedule={'2020-01-01':{'A':.5,'B':.5}},
            risk_chains={'A':'x','B':'y'},contract=contract(portfolio_cash_usd=1100.,transaction_cost_bps=100.))
        self.assertEqual(r['trades'][0]['fee_buffer_trimmed_tickers'],['B'])
        self.assertEqual(r['daily'][0]['shares'],{'A':5,'B':4})
        self.assertEqual(r['daily'][0]['cash'],191.)
        self.assertEqual(r['summary']['whole_lot_total_transaction_cost_usd'],9.)
        self.assertEqual(r['summary']['whole_lot_path_max_drawdown'],0.)

    def test_constraint_failure_does_not_cancel_legacy_trade_and_stock_denominator_excludes_cash(self):
        r=account(dates=['2020-01-01','2020-01-02'],prices={'A':[100.,100.],'B':[100.,200.]},
            schedule={'2020-01-01':{'A':.5,'B':.5}},risk_chains={'A':'same','B':'same'},
            contract=contract(max_single_weight=.6,risk_chain_top1_cap=.55))
        self.assertFalse(r['summary']['whole_lot_constraints_preserved_all_days'])
        self.assertEqual(r['daily'][0]['shares'],{'A':4,'B':4})
        self.assertAlmostEqual(r['daily'][1]['risk']['top1'],2/3)
        self.assertEqual(r['daily'][1]['risk']['risk_chain_top1'],1.)

    def test_sales_and_buys_both_pay_fees(self):
        r=account(dates=['2020-01-01','2020-01-02'],prices={'A':[10.,20.],'B':[10.,10.]},
            schedule={'2020-01-01':{'A':.5,'B':.5},'2020-01-02':{'A':.1,'B':.9}},risk_chains={'A':'a','B':'b'},
            contract=contract(transaction_cost_bps=100.))
        trade=r['trades'][1];previous=r['daily'][0]
        total=abs(trade['shares']['A']-previous['shares']['A'])*20+abs(trade['shares']['B']-previous['shares']['B'])*10
        self.assertAlmostEqual(trade['fees'],total*.01)
        self.assertGreater(trade['shares']['B'],previous['shares']['B'])
        self.assertLess(trade['shares']['A'],previous['shares']['A'])


if __name__=='__main__':unittest.main()
