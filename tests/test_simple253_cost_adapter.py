from copy import deepcopy
from datetime import date,timedelta
from fractions import Fraction as F
import unittest
from test_current_quantity_v2_simple253 import fixture
from backtest.current_quantity_v2_simple253 import select_simple253
from backtest.simple253_cost_selector import select_cost_simple253,make_cost_simple_decider
from backtest.simple253_cost_next_open import run_cost_simple253_next_open


def common(w,a,cash='100',shares=None):
    day=a['decision_date']
    return dict(decision_date=day,account_state=dict(asof=day,revision='test',cash=cash,shares=shares or {},reserved_cash='0'),
        valuation_quotes=[dict(security_id=s,price=p,as_of=day,price_basis='TEST',source_references=['quote']) for s,p in a['prices'].items()],
        search_arguments=dict(a,quote_as_of=day,price_basis='TEST'),source_hashes={'quote':'a'*64,'backtest/return_priority_fresh_cash_quantity_search.py':'b'*64})


class SimpleCostTests(unittest.TestCase):
    def test_zero_fee_exact_selection_equivalence(self):
        w,a,days=fixture()
        for cash in ('59','60','63','100','126','10000'):
            a['entered_cash']=cash
            old=select_simple253(window=w,calendar=days,arguments=a)
            new=select_cost_simple253(window=w,calendar=days,arguments=a)
            self.assertEqual(old['selected'],new['selected'])
            self.assertEqual(old['winner'],new['winner'])

    def test_fee_inclusive_affordability_fallback_and_exact_floor(self):
        w,a,days=fixture();a.update(fee_bps='1',entered_cash='63')
        r=select_cost_simple253(window=w,calendar=days,arguments=a)
        self.assertEqual(r['winner'],'A')
        self.assertEqual(F(r['selected']['fees']),F(60,10000))
        a['entered_cash']='126';r=select_cost_simple253(window=w,calendar=days,arguments=a)
        self.assertEqual(r['selected']['quantities'],{'B':1})
        a['entered_cash']='126.0126'
        self.assertEqual(select_cost_simple253(window=w,calendar=days,arguments=a)['selected']['quantities'],{'B':2})
        a['entered_cash']='60'
        self.assertEqual(select_cost_simple253(window=w,calendar=days,arguments=a)['selected']['quantities'],{})

    def test_own_capital_not_entered_cash_or_other_arm(self):
        w,a,days=fixture();a['fee_bps']='1'
        decide=make_cost_simple_decider(training_windows=[w])
        rich=decide(**common(w,a,'10',{'A':2}))
        poor=decide(**common(w,a,'10'))
        self.assertEqual(F(rich['investable_equity']),130)
        self.assertEqual(rich['target_quantities'],{'B':2})
        self.assertEqual(poor['target_quantities'],{})
        self.assertEqual(F(rich['search_result']['selected']['fees']),F(126,10000))

    def test_strict_training_and_cost_rejection(self):
        w,a,days=fixture()
        for bad in (True,'2','-1'):
            aa=deepcopy(a);aa['fee_bps']=bad
            with self.assertRaises(ValueError):select_cost_simple253(window=w,calendar=days,arguments=aa)
        w['training_dates'][-1]='2099-01-01'
        with self.assertRaises(ValueError):select_cost_simple253(window=w,calendar=days,arguments=a)

    def test_real_book_fill_cost_and_future_open_rationing(self):
        w,a,days=fixture();a['fee_bps']='1';c=common(w,a)
        day=days[-1];nextday=(date.fromisoformat(day)+timedelta(days=1)).isoformat()
        assembled=dict(session_dates=[day,nextday],monthly_inputs=[dict(decision_date=day,search_arguments=c['search_arguments'],valuation_quotes=c['valuation_quotes'],source_hashes=c['source_hashes'])],
            close_prices={s:{day:p,nextday:p} for s,p in a['prices'].items()},provider_actions=[],actions=[],cash_stock_merger_events=[],fractional_settlements=[],price_source_references=['quote'],distribution_events=[],distribution_fractional_cash_values={})
        bars={s:{d:dict.fromkeys(('open','high','low','close'),p) for d in (day,nextday)} for s,p in a['prices'].items()}
        kw=dict(assembled=assembled,training_windows=[w],initial_cash='200',fee_bps='1',slippage_bps='10')
        r=run_cost_simple253_next_open(ohlc=bars,**kw)
        self.assertEqual(r['status'],'COMPLETE')
        fills=[x for x in r['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual(len(fills),1)
        self.assertEqual(F(fills[0]['price']),F(63)*F(1001,1000))
        self.assertEqual(F(r['fees']),fills[0]['quantity']*F(fills[0]['price'])/10000)
        future=deepcopy(bars);future['B'][nextday]=dict.fromkeys(('open','high','low','close'),'1000')
        q=run_cost_simple253_next_open(ohlc=future,**kw)
        self.assertEqual(q['provider_audit'],r['provider_audit'])
        self.assertEqual(q['status'],'COMPLETE');self.assertEqual(F(q['fees']),0)
        self.assertGreaterEqual(F(q['cash']),0)
        self.assertTrue(any(x['event']=='UNFILLED_CASH_RATIONED_INTEGER_FLOOR' for x in q['order_log']))
        bad=deepcopy(assembled);bad['monthly_inputs'][0]['search_arguments']['fee_bps']='0'
        with self.assertRaisesRegex(ValueError,'MONTHLY_EXECUTION_FEE_MISMATCH'):
            run_cost_simple253_next_open(ohlc=bars,**dict(kw,assembled=bad))

    def test_two_month_books_sell_first_and_reselect_with_own_capital(self):
        w,a,days=fixture();a['fee_bps']='1';c=common(w,a)
        sessions=[days[-1]]+[(date.fromisoformat(days[-1])+timedelta(days=i)).isoformat() for i in (1,2,3)]
        w2=deepcopy(w);w2['decision_cutoff']=sessions[2];w2['training_dates']=days[2:]+sessions[1:3]
        a2=deepcopy(a);a2.update(decision_date=sessions[2],scenario_dates=w2['training_dates'][21::21])
        for row in w2['candidates']:
            sid=row['security_id'];mark='80' if sid=='A' else '50'
            row['training_close']=row['training_close'][2:]+[row['training_close'][-1],mark]
            row['decision_cost']=mark;a2['prices'][sid]=mark
        a2['training_scenarios']=[{row['security_id']:str(F(row['training_close'][i+21])/F(row['training_close'][i])) for row in w2['candidates']} for i in range(0,252,21)]
        c2=common(w2,a2)
        plans=[dict(decision_date=x['decision_date'],search_arguments=x['search_arguments'],valuation_quotes=x['valuation_quotes'],source_hashes=x['source_hashes']) for x in (c,c2)]
        prices={sid:{day:(a['prices'][sid] if j<2 else a2['prices'][sid]) for j,day in enumerate(sessions)} for sid in a['prices']}
        bars={sid:{d:dict.fromkeys(('open','high','low','close'),v) for d,v in series.items()} for sid,series in prices.items()}
        assembled=dict(session_dates=sessions,monthly_inputs=plans,close_prices=prices,provider_actions=[],actions=[],cash_stock_merger_events=[],fractional_settlements=[],price_source_references=['quote'],distribution_events=[],distribution_fractional_cash_values={})
        results=[]
        for cash in ('200','400'):
            r=run_cost_simple253_next_open(assembled=assembled,training_windows=[w,w2],ohlc=bars,initial_cash=cash,fee_bps='1',slippage_bps='10')
            self.assertEqual(r['status'],'COMPLETE');results.append(r)
            state=r['selection_account_states'][1]['account_state']
            ledger=next(x for x in r['daily_ledger'] if x['date']==sessions[2])
            self.assertEqual((state['cash'],state['shares']),(ledger['cash'],ledger['shares']))
            sel=next(x['selection'] for x in r['provider_audit'] if x.get('selection') and x['selection']['decision_date']==sessions[2])
            equity=F(state['cash'])+sum(q*F(prices[sid][sessions[2]]) for sid,q in state['shares'].items())
            self.assertEqual(F(sel['investable_equity']),equity)
            fills=[x for x in r['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED' and x['date']==sessions[3]]
            self.assertEqual([x['side'] for x in fills],['SELL','BUY'])
            self.assertEqual([x['security_id'] for x in fills],['B','A'])
            for x in fills:
                mult=F(999,1000) if x['side']=='SELL' else F(1001,1000)
                self.assertEqual(F(x['price']),F(bars[x['security_id']][sessions[3]]['open'])*mult)
                self.assertEqual(F(x['fee']),x['quantity']*F(x['price'])/10000)
                self.assertGreaterEqual(F(x['cash_after']),0)
        self.assertNotEqual(results[0]['selection_account_states'][1]['account_state'],results[1]['selection_account_states'][1]['account_state'])

if __name__=='__main__':unittest.main()
