import unittest
from copy import deepcopy
from datetime import date,timedelta
from fractions import Fraction as F
from unittest.mock import patch
from docs.candidates import qqq_risk_budget_account_runner as runner
from docs.candidates.qqq_risk_budget_selection import apply_risk_budget_selection
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter


def risk_input(day):
    dates=[];d=date.fromisoformat(day)
    while len(dates)<63:
        if d.weekday()<5:dates.append(d.isoformat())
        d-=timedelta(days=1)
    dates.reverse()
    return dict(status='CONDITIONAL_INPUT_READY',decision_date=day,source_binding={'fixture':'only'},arguments=dict(
        decision_date=day,target_quantities={'A':999},decision_prices={'A':'999'},tradable_equity='999999',
        stock_gross_returns={'A':{d:str(1+F(1,25)*(1 if i%2 else -1)) for i,d in enumerate(dates)}},
        qqq_gross_returns={d:str(1+F(1,100)*(1 if i%2 else -1)) for i,d in enumerate(dates)}))


class Tests(unittest.TestCase):
    def test_real_book_cash_dividend_dynamic_wealth_next_open_exit(self):
        days=['2020-01-30','2020-01-31','2020-02-03','2020-02-04','2020-02-05','2020-02-06','2020-02-07']
        values=['10','10','10','10','10','7','8'];closes=dict(zip(days,values))
        plans=[dict(decision_date=d,search_arguments={'fee_bps':'0'},valuation_quotes=[dict(security_id='A',price=closes[d])],source_hashes={}) for d in (days[0],days[4])]
        assembled=dict(session_dates=days,monthly_inputs=plans,close_prices={'A':closes},provider_actions=[],actions=[],cash_stock_merger_events=[],fractional_settlements={},price_source_references={},distribution_events=[],distribution_fractional_cash_values={})
        bars={'A':{d:dict(open=p,high=p,low=p,close=p) for d,p in closes.items()}}
        calls={};adjusted=[]
        def choose(**kw):
            a=kw['account_state'];eq=F(a['cash'])+a['shares'].get('A',0)*F(closes[kw['decision_date']]);calls[kw['decision_date']]=deepcopy(kw)
            return dict(decision_date=kw['decision_date'],target_quantities={'A':int(eq/11)},investable_equity=str(eq))
        def transform(selected):
            r=apply_risk_budget_selection(selected=selected,arguments=calls[selected['decision_date']],risk_input=risk_input(selected['decision_date']));adjusted.append(r);return r
        event=dict(event_id='synthetic-dividend',security_id='A',ex_date=days[2],payment_date=days[3],amount_per_share='100',withholding_rate='0',assumption='synthetic accounting fixture',currency='USD')
        with patch.object(runner,'decide_continuous_guided_for_account',side_effect=choose),patch.object(runner,'rerank',side_effect=transform):
            book=runner.run_frontier_capped_next_open(assembled=assembled,ohlc=bars,initial_cash='110',fee_bps='0',slippage_bps='5',risk=MonthlyExitCoreResearchAdapter(),max_new_searches=2,dividend_events=[event])
        self.assertEqual(book['status'],'COMPLETE',book.get('reason'))
        self.assertEqual([r['target_quantities'] for r in adjusted],[{'A':2},{'A':7}])
        self.assertEqual([r['risk_budget_original_selection']['target_quantities'] for r in adjusted],[{'A':10},{'A':28}])
        self.assertEqual(F(book['daily_ledger'][0]['cash']),F('89.99'))
        self.assertEqual(F(book['daily_ledger'][1]['dividend_receivable']),200)
        self.assertEqual(F(calls[days[4]]['account_state']['cash']),F('289.99'))
        self.assertEqual(book['provider_audit'][0]['monthly_ceiling'],{'A':2})
        self.assertEqual(book['provider_audit'][4]['monthly_ceiling'],{'A':7})
        fills=[r for r in book['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual([(r['date'],r['side'],r['quantity']) for r in fills],[(days[1],'BUY',2),(days[5],'BUY',5),(days[6],'SELL',7)])
        self.assertEqual(book['provider_audit'][5]['target_shares'],{'A':0})

    def test_dynamic_new_security_blocks_and_current_wealth_required(self):
        day='2020-01-30';args=dict(decision_date=day,account_state=dict(cash='100',shares={}),valuation_quotes=[dict(security_id='B',price='10')])
        selected=dict(target_quantities={'B':5},investable_equity='100')
        with self.assertRaisesRegex(ValueError,'DYNAMIC_TARGET_RISK_COVERAGE'):apply_risk_budget_selection(selected=selected,arguments=args,risk_input=risk_input(day))
        args['valuation_quotes'][0]['security_id']='A';selected['target_quantities']={'A':5};selected['investable_equity']='999'
        with self.assertRaisesRegex(ValueError,'BRANCH_TRADABLE_EQUITY_MISMATCH'):apply_risk_budget_selection(selected=selected,arguments=args,risk_input=risk_input(day))

    def test_zero_target_without_gross_preserves_domain(self):
        day='2020-01-30'
        args=dict(decision_date=day,account_state=dict(cash='100',shares={}),valuation_quotes=[dict(security_id='A',price='10')])
        selected=dict(target_quantities={'A':5,'ZERO':0},investable_equity='100')
        result=apply_risk_budget_selection(selected=selected,arguments=args,risk_input=risk_input(day))
        self.assertEqual(result['target_quantities'],{'A':2,'ZERO':0})
        self.assertEqual(result['risk_budget']['zero_target_securities_excluded_from_covariance'],['ZERO'])
        selected['target_quantities']['ZERO']=1
        with self.assertRaisesRegex(ValueError,'DYNAMIC_TARGET_RISK_COVERAGE'):apply_risk_budget_selection(selected=selected,arguments=args,risk_input=risk_input(day))

if __name__=='__main__':unittest.main()
