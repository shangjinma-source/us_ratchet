import unittest
from copy import deepcopy
from datetime import date,timedelta
from fractions import Fraction as F
from test_current_quantity_v2_simple253 import fixture
from test_simple253_cost_adapter import common
from backtest.simple253_cost_selector import select_cost_simple253,make_cost_simple_decider
from backtest.simple253_cost_next_open import run_cost_simple253_next_open


class IndependentSimpleCost(unittest.TestCase):
    def test_exact_cash_boundary_and_training_attacks(self):
        w,a,days=fixture();a['fee_bps']='1'
        for units in range(1,12):
            threshold=F(63)*F(10001,10000)*units
            for delta in (-F(1,10**9),F(0),F(1,10**9)):
                a['entered_cash']=str(threshold+delta)
                result=select_cost_simple253(window=w,calendar=days,arguments=a)
                eligible=[(F(row['training_close'][-1])/F(row['training_close'][0]),row['security_id']) for row in w['candidates'] if F(a['prices'][row['security_id']])*F(10001,10000)<=threshold+delta]
                winner=sorted(eligible,key=lambda pair:(-pair[0],pair[1]))[0][1] if eligible else None
                expected={} if winner is None else {winner:int((threshold+delta)//(F(a['prices'][winner])*F(10001,10000)))}
                self.assertEqual(result['selected']['quantities'],expected)
                self.assertGreaterEqual(F(result['selected']['residual_cash']),0)
        for mutation in ('duplicate','identity','scenario'):
            ww=deepcopy(w);aa=deepcopy(a)
            if mutation=='duplicate':ww['training_dates'][1]=ww['training_dates'][0]
            elif mutation=='identity':ww['candidates'][0]['issuer_id']='WRONG'
            else:aa['training_scenarios'][0]['A']='999'
            with self.assertRaises(ValueError):select_cost_simple253(window=ww,calendar=days,arguments=aa)

    def test_real_fill_rations_fee_and_slippage_without_target_lookahead(self):
        w,a,days=fixture();a['fee_bps']='1';c=common(w,a);day=days[-1];later=(date.fromisoformat(day)+timedelta(days=1)).isoformat()
        assembled=dict(session_dates=[day,later],monthly_inputs=[dict(decision_date=day,search_arguments=c['search_arguments'],valuation_quotes=c['valuation_quotes'],source_hashes=c['source_hashes'])],close_prices={s:{day:p,later:p} for s,p in a['prices'].items()},provider_actions=[],actions=[],cash_stock_merger_events=[],fractional_settlements=[],price_source_references=['quote'],distribution_events=[],distribution_fractional_cash_values={})
        bars={s:{d:dict.fromkeys(('open','high','low','close'),p) for d in (day,later)} for s,p in a['prices'].items()}
        params=dict(assembled=assembled,training_windows=[w],initial_cash='126.0126',fee_bps='1',slippage_bps='10')
        r=run_cost_simple253_next_open(ohlc=bars,**params)
        fills=[f for f in r['order_log'] if f['event']=='ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual(len(fills),1);f=fills[0]
        self.assertEqual(f['quantity'],1)
        price=F(63)*F(1001,1000);fee=price/10000
        self.assertEqual(F(f['price']),price);self.assertEqual(F(r['fees']),fee)
        self.assertEqual(F(r['cash']),F('126.0126')-price-fee)
        future=deepcopy(bars);future['B'][later]=dict.fromkeys(('open','high','low','close'),'50')
        cheaper=run_cost_simple253_next_open(ohlc=future,**params)
        self.assertEqual(cheaper['provider_audit'],r['provider_audit'])
        self.assertEqual([f['quantity'] for f in cheaper['order_log'] if f['event']=='ASSUMED_NEXT_OPEN_FILLED'],[2])

    def test_decider_copies_training_and_rejects_duplicate_month(self):
        w,a,_=fixture();a['fee_bps']='1';decide=make_cost_simple_decider(training_windows=[w]);before=decide(**common(w,a,'100'))
        w['candidates'][0]['training_close'][0]='999'
        self.assertEqual(decide(**common(w,a,'100')),before)
        with self.assertRaises(ValueError):make_cost_simple_decider(training_windows=[w,w])

if __name__=='__main__':unittest.main()
