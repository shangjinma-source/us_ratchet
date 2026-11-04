import unittest
from unittest.mock import patch
from fractions import Fraction
from docs.candidates.ema20_market_adapter import Ema20MarketAdapter
from backtest import historical_dividend_frontier_research as runner


class MarketIntegration(unittest.TestCase):
    days=['2021-01-28','2021-01-29','2021-02-01','2021-02-02','2021-02-03','2021-02-04']

    def signals(self):
        return {day:dict(close=str(11 if on else 9),ema='10',on=on)
                for day,on in zip(self.days,[True,False,True,True,True,True])}

    def test_real_book_reentry_preserves_target_and_next_open(self):
        days=self.days
        prices={'A':dict.fromkeys(days,'10')}
        plans=[dict(decision_date=d,search_arguments={'fee_bps':'0'},
                    valuation_quotes=[dict(security_id='A',price='10')],source_hashes={})
               for d in days[:2]]
        assembled=dict(session_dates=days,monthly_inputs=plans,close_prices=prices,
            provider_actions=[],actions=[],cash_stock_merger_events=[],fractional_settlements=None,
            price_source_references={},distribution_events=[],distribution_fractional_cash_values=None)
        bars={'A':{d:dict(open='10',high='10',low='10',close='10') for d in days}}
        results={}
        def select(**kwargs):
            state=kwargs['account_state']
            return dict(target_quantities={'A':5},investable_equity=str(Fraction(state['cash'])+10*state['shares'].get('A',0)))
        for mode in ('daily','monthly_reentry'):
            adapter=Ema20MarketAdapter(signals=self.signals(),month_ends=[days[1]],mode=mode)
            with patch.object(runner,'decide_continuous_guided_for_account',side_effect=select),patch.object(runner,'rerank',side_effect=lambda x:x):
                result=runner.run_frontier_capped_next_open(assembled=assembled,ohlc=bars,
                    initial_cash='100',fee_bps='0',slippage_bps='5',max_new_searches=2,risk=adapter)
            self.assertEqual(result['status'],'COMPLETE',str(result))
            rows={r['date']:r for r in result['daily_ledger']}
            self.assertEqual(rows[days[1]]['shares'].get('A',0),5)
            self.assertEqual(rows[days[2]]['shares'].get('A',0),0)
            self.assertEqual(rows[days[3]]['shares'].get('A',0),5 if mode=='daily' else 0)
            self.assertTrue(all(r['monthly_ceiling']=={'A':5} for r in adapter.market_audit))
            self.assertGreaterEqual(Fraction(result['cash']),0)
            results[mode]=result
        self.assertNotEqual(results['daily']['shares'],results['monthly_reentry']['shares'])

    def test_market_reentry_never_unlocks_original_exit(self):
        adapter=Ema20MarketAdapter(signals=self.signals(),month_ends=[self.days[1]],mode='daily')
        adapter.apply(day=self.days[0],month=self.days[0],target={'A':5},closes={'A':'100'})
        adapter.apply(day=self.days[1],month=self.days[0],target={'A':5},closes={'A':'70'})
        target,_=adapter.apply(day=self.days[2],month=self.days[0],target={'A':5},closes={'A':'110'})
        self.assertEqual(target,{'A':0})

    def test_monthly_off_carries_to_later_month_end(self):
        adapter=Ema20MarketAdapter(signals=self.signals(),month_ends=[self.days[1],self.days[4]],mode='monthly_reentry')
        for day in self.days[:4]:
            target,_=adapter.apply(day=day,month=self.days[0] if day<self.days[1] else self.days[1],target={'A':5},closes={'A':'10'})
        self.assertEqual(target,{'A':0})
        target,_=adapter.apply(day=self.days[4],month=self.days[4],target={'A':5},closes={'A':'10'})
        self.assertEqual(target,{'A':5})

    def test_missing_or_wrong_signal_does_not_mutate(self):
        adapter=Ema20MarketAdapter(signals={},month_ends=[],mode='daily')
        with self.assertRaisesRegex(ValueError,'SIGNAL_REQUIRED'):
            adapter.apply(day=self.days[0],month=self.days[0],target={'A':5},closes={'A':'10'})
        self.assertIsNone(adapter.state)
        self.assertIsNone(adapter.market_on)

    def test_invalid_signals_and_equality(self):
        day=self.days[0]
        for signal in (dict(close='NaN',ema='10',on=False),dict(close='11',ema='10',on=False)):
            adapter=Ema20MarketAdapter(signals={day:signal},month_ends=[day],mode='daily')
            with self.assertRaises(ValueError):
                adapter.apply(day=day,month=day,target={'A':5},closes={'A':'10'})
            self.assertIsNone(adapter.state)
        adapter=Ema20MarketAdapter(signals={day:dict(close='10',ema='10',on=False)},month_ends=[day],mode='daily')
        target,_=adapter.apply(day=day,month=day,target={'A':5},closes={'A':'10'})
        self.assertEqual(target,{'A':0})

if __name__=='__main__':unittest.main()

