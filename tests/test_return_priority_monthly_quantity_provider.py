import unittest
from backtest.return_priority_monthly_quantity_provider import build_monthly_quantity_provider

D=['2024-01-31','2024-02-01','2024-02-29','2024-03-01']
class MonthlyQuantityTests(unittest.TestCase):
    def make(self, decide):
        inputs=[dict(decision_date=d, valuation_quotes=[dict(security_id=s,price='10') for s in ('a','b')],search_arguments={'fee_bps':0},source_hashes={}) for d in (D[0],D[2])]
        return build_monthly_quantity_provider(session_dates=D,monthly_inputs=inputs,close_prices={s:{d:'10' for d in D} for s in ('a','b')},decide=decide)
    def test_actual_equity_integer_target_roll_and_cash_wait(self):
        calls=[]
        def decide(**kw):
            st=kw['account_state']; equity=int(st['cash'])+sum(st['shares'].values())*10;calls.append(equity)
            return dict(investable_equity=str(equity),target_quantities={'b':equity//10})
        p=self.make(decide)
        r=p(decision_date=D[0],active_date=D[1],state=dict(asof=D[0],cash='0',shares={'a':10}))
        self.assertEqual(r['target_shares'],{'b':10});self.assertEqual([o['side'] for o in r['orders']],['SELL']);self.assertEqual(len(r['wait_cash']),1)
        r=p(decision_date=D[1],active_date=D[2],state=dict(asof=D[1],cash='100',shares={}))
        self.assertEqual(r['orders'][0]['quantity'],10);self.assertEqual(calls,[100])
        r=p(decision_date=D[2],active_date=D[3],state=dict(asof=D[2],cash='30',shares={'b':11}))
        self.assertEqual(calls,[100,140]);self.assertEqual(r['target_shares'],{'b':14})
    def test_incomplete_search_not_repeated(self):
        calls=[]
        def decide(**kw): calls.append(1);return {'target_quantities':None}
        p=self.make(decide);args=dict(decision_date=D[0],active_date=D[1],state=dict(asof=D[0],cash='100',shares={}))
        self.assertEqual(p(**args)['status'],'BLOCKED');self.assertEqual(p(**args)['reason'],'MONTHLY_SELECTION_ALREADY_ATTEMPTED');self.assertEqual(len(calls),1)
    def test_selected_missing_price_blocks_does_not_replace(self):
        calls=[]
        selected=dict(investable_equity='100',target_quantities={'outside':1},search_result={'audit':'preserve'})
        def decide(**kw): calls.append(1);return selected
        provider=self.make(decide)
        args=dict(decision_date=D[0],active_date=D[1],state=dict(asof=D[0],cash='100',shares={}))
        r=provider(**args)
        self.assertEqual(r['status'],'BLOCKED');self.assertEqual(r['orders'],[])
        self.assertEqual(r['selection'],selected);self.assertEqual(r['investable_equity_at_reset'],'100')
        self.assertEqual(r['target_shares'],{})
        self.assertEqual(provider(**args)['reason'],'MONTHLY_SELECTION_ALREADY_ATTEMPTED');self.assertEqual(len(calls),1)

    def test_default_capital_real_tiny_core_and_execution(self):
        from backtest.return_priority_limit_book import run_limit_book
        from fractions import Fraction
        days=['2026-10-13','2026-10-14','2026-10-15']
        args=dict(prices={'A':'10','B':'20'},metadata={'A':{'ticker':'AAA','issuer_id':'IA'},'B':{'ticker':'BBB','issuer_id':'IB'}},entered_cash='20000',fee_bps='0',minimum_cash_buffer='0',training_scenarios=[{'A':'1.1','B':'1.2'}],scenario_dates=[days[0]],decision_date=days[0],max_objective_evaluations=12,fixed_seed='synthetic',quote_as_of=days[0],price_basis='CURRENT_SHARE_USD')
        quotes=[dict(security_id=s,price=p,as_of=days[0],price_basis='CURRENT_SHARE_USD',source_references=['quote']) for s,p in args['prices'].items()]
        provider=build_monthly_quantity_provider(session_dates=days,monthly_inputs=[dict(decision_date=days[0],valuation_quotes=quotes,search_arguments=args,source_hashes={'quote':'a'*64,'backtest/return_priority_fresh_cash_quantity_search.py':'b'*64})],close_prices={s:{d:p for d in days} for s,p in args['prices'].items()})
        audit=[]
        def callback(**kw):
            r=provider(**kw);audit.append(r);return r
        bars={s:{d:dict(open=p,high=p,low=p,close=p) for d in days} for s,p in args['prices'].items()}
        result=run_limit_book(session_dates=days,ohlc=bars,initial_cash='100',order_provider=callback)
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(audit[0]['selection']['core_calls'],1)
        self.assertEqual(audit[0]['selection']['investable_equity'],'100')
        self.assertIsNone(audit[1]['selection'])
        self.assertEqual(Fraction(result['cash'])+sum(q*Fraction(args['prices'][sid]) for sid,q in result['shares'].items()),100)
        self.assertEqual({s:q for s,q in result['shares'].items() if q},audit[0]['target_shares'])

if __name__=='__main__':unittest.main()
