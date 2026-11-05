import unittest
from copy import deepcopy
from fractions import Fraction as F
from datetime import date,timedelta
from unittest.mock import patch
from docs.candidates.downside_account_selection_20261105 import decide_observed_for_account,apply_downside_selection,REQUIRED_PINS,original_rerank,exact_hash
from docs.candidates import qqq_risk_budget_account_runner as kernel
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter

PINS={p:'a'*64 for p in (*REQUIRED_PINS,'backtest/return_priority_fresh_cash_quantity_search.py','quote')}
RESEARCH={'research.py':'b'*64}


def fixture(day='2020-01-30',cash='110',shares=None,daily=F('0.001'),reference=F('-0.01')):
    dates=[(date.fromisoformat(day)-timedelta(days=i)).isoformat() for i in range(251,-1,-1)]
    returns={'A':dict.fromkeys(dates,daily)};qqq=dict.fromkeys(dates,reference)
    args=dict(prices={'A':'10'},metadata={'A':dict(ticker='A',issuer_id='A')},entered_cash='999999',fee_bps='0',minimum_cash_buffer='0',
        training_scenarios=[{'A':(1+daily)**21} for _ in range(12)],scenario_dates=dates[20::21],decision_date=day,
        max_objective_evaluations=128,fixed_seed='fixed',quote_as_of=day,price_basis='CURRENT_SHARE_USD')
    capital=dict(decision_date=day,account_state=dict(asof=day,revision=day+cash,cash=cash,shares=shares or {},reserved_cash='0'),
        valuation_quotes=[dict(security_id='A',price='10',as_of=day,price_basis='CURRENT_SHARE_USD',source_references=['quote'])],search_arguments=args,source_hashes=PINS)
    return capital,returns,qqq


def run(capital,returns,qqq):
    return decide_observed_for_account(stock_returns=returns,qqq_reference=qqq,research_source_hashes=RESEARCH,guard=lambda:None,**capital)


def apply(raw,side,returns,qqq):
    return apply_downside_selection(raw=raw,sidecar=side,stock_returns=returns,qqq_reference=qqq,research_source_hashes=RESEARCH)


class DownsideAccountTests(unittest.TestCase):
    def test_dynamic_capital_and_incumbent_tie(self):
        cap,r,q=fixture();raw,side=run(cap,r,q)
        self.assertEqual(raw['binding']['search_arguments']['entered_cash'],'110')
        selected=apply(raw,side,r,q)
        self.assertEqual(selected['target_quantities'],original_rerank(raw)['target_quantities'])
        cap2,r2,q2=fixture(cash='200',shares={'A':2});other,side2=run(cap2,r2,q2)
        self.assertEqual(other['binding']['search_arguments']['entered_cash'],'220')
        self.assertNotEqual(side['evidence_binding'],side2['evidence_binding'])
        self.assertGreater(apply(other,side2,r2,q2)['target_quantities']['A'],selected['target_quantities']['A'])
        with self.assertRaisesRegex(ValueError,'INTEGRITY|ACCOUNT_OR_COORDINATE'):apply(other,side,r2,q2)

    def test_cross_month_coordinate_and_mutated_quantity_score_rejected(self):
        cap,r,q=fixture();raw,side=run(cap,r,q)
        for field,value in (('exact_product',F(123)),('target_quantities',{'A':4})):
            changed=deepcopy(side);changed['eligible_best_by_k']['1'][field]=value
            with self.assertRaisesRegex(ValueError,'INTEGRITY'):apply(raw,changed,r,q)
            # Even an accidental refreshed envelope cannot make a false score valid.
            changed['integrity_sha256']=exact_hash({k:v for k,v in changed.items() if k!='integrity_sha256'})
            with self.assertRaisesRegex(ValueError,'INTEGRITY'):apply(raw,changed,r,q)
            rebound=deepcopy(raw);rebound['downside_sidecar_sha256']=changed['integrity_sha256']
            with self.assertRaisesRegex(ValueError,'SCORE'):apply(rebound,changed,r,q)
        other,side2=run(*fixture(day='2020-02-28'))
        with self.assertRaisesRegex(ValueError,'INTEGRITY|ACCOUNT_OR_COORDINATE'):apply(other,side,r,q)
        altered=deepcopy(q);altered[next(iter(altered))]=F('-0.02')
        with self.assertRaisesRegex(ValueError,'ACCOUNT_OR_COORDINATE'):apply(raw,side,r,altered)

    def test_risky_incumbent_replaced_with_cash(self):
        cap,r,q=fixture(reference=F(0))
        # Positive growth with negative days: wealth scorer buys, zero-downside gate refuses any stock.
        for i,d in enumerate(r['A']):r['A'][d]=F('-0.01') if i%21==0 else F('0.002')
        cap['search_arguments']['training_scenarios']=[{'A':F('0.99')*F('1.002')**20} for _ in range(12)]
        raw,side=run(cap,r,q);self.assertTrue(original_rerank(raw)['target_quantities'])
        selected=apply(raw,side,r,q)
        self.assertFalse(selected['downside_audit']['incumbent_admitted']);self.assertEqual(selected['target_quantities'],{})

    def test_real_book_dividend_equity_exit_and_next_open(self):
        days=['2020-01-30','2020-01-31','2020-02-03','2020-02-04','2020-02-05','2020-02-06','2020-02-07']
        closes=dict(zip(days,['10','10','10','10','10','7','8']))
        plans=[]
        for d in (days[0],days[4]):
            cap,_,_=fixture(day=d);plans.append({k:cap[k] for k in ('decision_date','search_arguments','valuation_quotes','source_hashes')})
        assembled=dict(session_dates=days,monthly_inputs=plans,close_prices={'A':closes},provider_actions=[],actions=[],cash_stock_merger_events=[],fractional_settlements={},price_source_references={},distribution_events=[],distribution_fractional_cash_values={})
        bars={'A':{d:dict(open=v,high=v,low=v,close=v) for d,v in closes.items()}}
        evidence={};observed_equity=[]
        def choose(**kw):
            _,r,q=fixture(day=kw['decision_date']);raw,side=run(kw,r,q);evidence[raw['decision_id']]=(side,r,q);observed_equity.append(F(raw['investable_equity']));return raw
        def rerank(raw):
            side,r,q=evidence[raw['decision_id']];return apply(raw,side,r,q)
        event=dict(event_id='fixture-dividend',security_id='A',ex_date=days[2],payment_date=days[3],amount_per_share='100',withholding_rate='0',assumption='synthetic',currency='USD')
        with patch.object(kernel,'decide_continuous_guided_for_account',side_effect=choose),patch.object(kernel,'rerank',side_effect=rerank):
            book=kernel.run_frontier_capped_next_open(assembled=assembled,ohlc=bars,initial_cash='110',fee_bps='0',slippage_bps='5',risk=MonthlyExitCoreResearchAdapter(),max_new_searches=2,dividend_events=[event])
        self.assertEqual(book['status'],'COMPLETE',book.get('reason'))
        self.assertEqual(observed_equity,[F(110),F('609.975')])
        fills=[r for r in book['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual([(r['date'],r['side'],r['quantity']) for r in fills],[(days[1],'BUY',5),(days[5],'BUY',25),(days[6],'SELL',30)])
        self.assertEqual(F(book['daily_ledger'][1]['dividend_receivable']),500)
        self.assertEqual(book['provider_audit'][5]['target_shares'],{'A':0})


if __name__=='__main__':unittest.main()
