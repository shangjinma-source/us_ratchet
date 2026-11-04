import unittest
from copy import deepcopy
from fractions import Fraction
from unittest.mock import patch
from docs.candidates.split_identity_monthly_risk_adapter import SplitIdentityMonthlyRiskAdapter


def event(day='2024-10-02'):
    return dict(type='split_identity', date=day, security_id='old', new_security_id='new',
                old_shares='1', new_shares='10', source_references=['reviewed-fixture'])


def adjustment(e):
    return dict(date=e['date'], security_id='old', new_security_id='new', target_after=20)


class RiskTests(unittest.TestCase):
    def started(self, e):
        r=SplitIdentityMonthlyRiskAdapter([e])
        r.apply(day='2024-09-30',month='2024-09-30',target={'old':2},closes={'old':'100'})
        return r

    def test_in_month_identity_peak_target_and_threshold(self):
        e=event();r=self.started(e)
        target,out=r.apply(day=e['date'],month='2024-09-30',target={'new':20},closes={'new':'9'},adjustments=[adjustment(e)])
        self.assertEqual(target,{'new':20});self.assertEqual(r.state['peaks'],{'new':'10'})
        self.assertEqual(len(out['identity_split_migrations']),1)
        self.assertEqual(r.apply(day='2024-10-03',month='2024-09-30',target={'new':20},closes={'new':'8'})[0],{'new':0})

    def test_sold_risk_exit_latch_survives_identity(self):
        e=event();r=self.started(e)
        r.apply(day='2024-10-01',month='2024-09-30',target={'old':2},closes={'old':'79'})
        # A zero actual position must not release a monthly risk latch.
        target,_=r.apply(day=e['date'],month='2024-09-30',target={'new':20},closes={'new':'11'},adjustments=[adjustment(e)])
        self.assertEqual(target,{'new':0});self.assertEqual(r.state['exited'],['new'])

    def test_month_reset_does_not_carry_peak(self):
        e=event('2024-10-31');r=self.started(e)
        target,out=r.apply(day=e['date'],month=e['date'],target={'new':20},closes={'new':'7'},adjustments=[adjustment(e)])
        self.assertEqual(target,{'new':20});self.assertEqual(r.state['peaks'],{'new':'7'})
        self.assertEqual(out['identity_split_migrations'],[])

    def test_bad_evidence_atomic_rejection(self):
        for mutation in ('missing','duplicate','wrong_successor','bool_ratio','negative_ratio','collision'):
            e=event();r=self.started(e);change=adjustment(e)
            if mutation=='missing':r.actions[0]['source_references']=[]
            if mutation=='duplicate':r.actions.append(deepcopy(e))
            if mutation=='wrong_successor':change['new_security_id']='other'
            if mutation=='bool_ratio':r.actions[0]['new_shares']=True
            if mutation=='negative_ratio':r.actions[0]['new_shares']='-1'
            if mutation=='collision':
                for key in ('peaks','last_closes','unit_ids'):r.state[key]['new']=r.state[key]['old']
            before=deepcopy(r.__dict__)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                r.apply(day=e['date'],month='2024-09-30',target={'new':20},closes={'new':'9'},adjustments=[change])
            self.assertEqual(r.__dict__,before)


class BookTests(unittest.TestCase):
    def run_book(self, *, flat_before=False, month_reset=False, sold_before_event=False):
        from backtest import historical_dividend_frontier_research as runner
        days=['2024-09-27','2024-09-30','2024-10-01','2024-10-02','2024-10-03']
        e=event(days[2]);prices={'old':{days[0]:'100',days[1]:'100'},'new':{d:p for d,p in zip(days[2:],['9','8','8'])}}
        if sold_before_event:
            e=event(days[3]);prices['old'][days[2]]='100';prices['new'].pop(days[2])
        plan_days=[days[0]]+([days[1]] if flat_before else [])+([days[2]] if month_reset else [])
        plans=[dict(decision_date=d,search_arguments={'fee_bps':'0'},valuation_quotes=[dict(security_id='old' if d<days[2] else 'new',price=prices['old' if d<days[2] else 'new'][d])],source_hashes={}) for d in plan_days]
        assembled=dict(session_dates=days,monthly_inputs=plans,close_prices=prices,actions=[e],provider_actions=[e],cash_stock_merger_events=[],distribution_events=[],fractional_settlements={},price_source_references={},distribution_fractional_cash_values={})
        bars={s:{d:dict(open=p,high=p,low=p,close=p) for d,p in rows.items()} for s,rows in prices.items()}
        risk=SplitIdentityMonthlyRiskAdapter([e])
        def choose(**kw):
            d=kw['decision_date'];a=kw['account_state'];q={} if flat_before and d==days[1] else {'old':2} if d<days[2] else {'new':20}
            equity=Fraction(a['cash'])+sum(n*Fraction(prices[s][d]) for s,n in a['shares'].items() if n)
            return dict(target_quantities=q,investable_equity=str(equity))
        with patch.object(runner,'decide_continuous_guided_for_account',side_effect=choose),patch.object(runner,'rerank',side_effect=lambda x:x):
            book=runner.run_frontier_capped_next_open(assembled=assembled,ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='5',risk=risk,max_new_searches=len(plans))
        self.assertEqual(book['status'],'COMPLETE',book.get('reason'))
        return book,risk

    def test_real_book_continuous_holding_and_next_open_exit(self):
        book,risk=self.run_book()
        fills=[r for r in book['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual([(r['date'],r['side'],r['quantity']) for r in fills],[('2024-09-30','BUY',2),('2024-10-03','SELL',20)])
        self.assertEqual(book['daily_ledger'][1]['shares'],{'old':0,'new':20})
        self.assertEqual(risk.state['peaks'],{'new':'10'})

    def test_real_book_old_sid_sold_on_split_open_no_resurrection(self):
        book,risk=self.run_book(flat_before=True)
        fills=[r for r in book['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual([(r['side'],r['quantity']) for r in fills],[('BUY',2),('SELL',20)])
        self.assertEqual(book['daily_ledger'][1]['shares'],{'old':0,'new':0})
        self.assertIsNone(risk.state)

    def test_real_book_already_flat_before_identity(self):
        book,risk=self.run_book(flat_before=True,sold_before_event=True)
        fills=[r for r in book['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual([(r['side'],r['quantity']) for r in fills],[('BUY',2),('SELL',2)])
        self.assertTrue(all(not q for q in book['daily_ledger'][-1]['shares'].values()))
        self.assertIsNone(risk.state)

    def test_real_provider_reset_day_identity(self):
        book,risk=self.run_book(month_reset=True)
        self.assertEqual(risk.state['peaks'],{'new':'9'})
        self.assertFalse(risk.state['exited'])
        self.assertEqual(book['provider_audit'][2]['target_shares'],{'new':20})

if __name__=='__main__':unittest.main()
