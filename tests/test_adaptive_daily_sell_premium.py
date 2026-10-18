import unittest
from copy import deepcopy
from fractions import Fraction as F
from backtest.adaptive_daily_sell_premium import run_adaptive_daily_premium

class AdaptiveTests(unittest.TestCase):
    def test_new_month_receives_own_real_cash_holdings_without_cached_targets(self):
        dates=['2026-01-29','2026-01-30','2026-02-02','2026-02-03'];seen=[];progress=[]
        def fake(**kw):
            st=kw['account_state'];seen.append(deepcopy(st));equity=F(st['cash'])+sum(q*F('10') for q in st['shares'].values())
            return dict(target_quantities={'A':10 if len(seen)==1 else 7},investable_equity=str(equity))
        assembled=dict(session_dates=dates,monthly_inputs=[dict(decision_date=d,search_arguments={'fee_bps':'0'},valuation_quotes=[{'security_id':'A','price':'10'}],source_hashes={}) for d in [dates[0],dates[2]]],close_prices={'A':{d:'10' for d in dates}},provider_actions=[],actions=[],cash_stock_merger_events=[],fractional_settlements={},price_source_references={'A':['synthetic']},distribution_events=[],distribution_fractional_cash_values={})
        bars={'A':{d:dict(open='15',high='15',low='10',close='10') for d in dates}}
        result=run_adaptive_daily_premium(assembled=assembled,ohlc=bars,initial_cash='100',fee_bps='0',slippage_bps='0',decide=fake,progress=progress.append)
        self.assertEqual(result['status'],'COMPLETE');self.assertEqual(len(seen),2)
        self.assertEqual(seen[1]['cash'],'10');self.assertEqual(seen[1]['shares'],{'A':6})
        self.assertEqual(result['provider_audit'][-1]['selection']['target_quantities'],{'A':7})
        self.assertEqual([x['event'] for x in progress if 'event' in x],['MONTHLY_SEARCH_STARTED','MONTHLY_SEARCH_FINISHED']*2)
    def test_nonzero_costs_rejected_before_decide(self):
        with self.assertRaisesRegex(ValueError,'ZERO_COST'):
            run_adaptive_daily_premium(assembled={},ohlc={},initial_cash='100',fee_bps='1',slippage_bps='0',decide=lambda **kw:self.fail())

if __name__=='__main__':unittest.main()
