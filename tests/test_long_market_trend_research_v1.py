import calendar
import unittest
from copy import deepcopy
from unittest.mock import patch
from backtest import historical_dividend_frontier_research as frontier
from backtest.long_market_trend_research_v1 import run_trend, signal_proof
from backtest.long_market_trend_independent_review_v1 import review, review_trend_decision
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter


class TrendTests(unittest.TestCase):
    def fixture(self):
        day='2024-09-30'
        months=[(2023,12)]+[(2024,m) for m in range(1,10)]
        record=dict(decision_date=day,completed_month_end_prices=[dict(date=f'{y}-{m:02d}-{calendar.monthrange(y,m)[1]}',close='100',source='qqq') for y,m in months])
        plan=dict(decision_date=day,active_date='2024-10-01',search_arguments={'fee_bps':'0'},valuation_quotes=[],source_hashes={'qqq':'pinned'})
        assembled=dict(session_dates=[day,'2024-10-01'],monthly_inputs=[plan],close_prices={},provider_actions=[],actions=[],distribution_events=[],cash_stock_merger_events=[],fractional_settlements={},price_source_references={},distribution_fractional_cash_values={})
        return {day:record},assembled

    def test_off_real_kernel_and_independent_account_review(self):
        signals,domain=self.fixture();callbacks=[]
        with patch.object(frontier,'decide_continuous_guided_for_account',side_effect=AssertionError('optimizer called')):
            book=run_trend(signal_source_hashes={'qqq':'pinned'},signals=signals,assembled=domain,ohlc={},initial_cash='1000',fee_bps='0',slippage_bps='5',max_new_searches=1,risk=MonthlyExitCoreResearchAdapter(),decision_callback=lambda args,result:callbacks.append((args,result)))
        self.assertEqual(book['status'],'COMPLETE',book.get('reason'))
        self.assertEqual(book['trend_diagnostics']['on_optimizer_calls'],0)
        self.assertEqual(len(callbacks),1)
        result=review(book,domain,{},initial_cash='1000',dividend_events=[],signals=signals,signal_source_hashes={'qqq':'pinned'},verify_selections=True,verify_risk_provider=True,expected_fee_bps='0',expected_slippage_bps='5')
        self.assertTrue(result['selection_proof_checked'])
        altered=deepcopy(callbacks[0][0]);altered['account_state']['cash']='999'
        with self.assertRaisesRegex(ValueError,'OFF_ARGUMENT_BINDING'):review_trend_decision(callbacks[0][1],arguments=altered,signal_input=signals['2024-09-30'],signal_source_hashes={'qqq':'pinned'})

    def test_callback_failure_restores_hooks(self):
        signals,domain=self.fixture();before=(frontier.decide_continuous_guided_for_account,frontier.rerank)
        def fail(*args):raise ValueError('GATE_BLOCK')
        book=run_trend(signal_source_hashes={'qqq':'pinned'},signals=signals,assembled=domain,ohlc={},initial_cash='1000',fee_bps='0',slippage_bps='5',max_new_searches=1,risk=MonthlyExitCoreResearchAdapter(),decision_callback=fail)
        self.assertEqual(book['status'],'BLOCKED')
        self.assertEqual(before,(frontier.decide_continuous_guided_for_account,frontier.rerank))

    def test_positive_and_equal_rule(self):
        signals,_=self.fixture();record=signals['2024-09-30'];self.assertFalse(signal_proof(record)['risk_on'])
        record['completed_month_end_prices'][-1]['close']='101';self.assertTrue(signal_proof(record)['risk_on'])

    def test_missing_month_rejected(self):
        signals,_=self.fixture();record=signals['2024-09-30'];record['completed_month_end_prices'][0]['date']='2023-11-30'
        with self.assertRaisesRegex(ValueError,'CONSECUTIVE'):signal_proof(record)

    def test_on_retains_real_saved_candidate_proof(self):
        # Synthetic saved candidate fixture; real reranker, account binding,
        # provider, risk, execution and independent selection proof.
        from test_capped_frontier_independent_review import inputs, raw_fixture
        domain,bars=inputs();day=domain['monthly_inputs'][0]['decision_date']
        months=[(2024,m) for m in range(4,13)]+[(2025,1)]
        rows=[dict(date=f'{y}-{m:02d}-{calendar.monthrange(y,m)[1]}',close='100',source='qqq') for y,m in months]
        rows[-1].update(date=day,close='101')
        signals={day:dict(decision_date=day,completed_month_end_prices=rows)}
        # Signal hashes remain separate from unchanged V27 source pins.
        book=run_trend(signal_source_hashes={'qqq':'pinned'},signals=signals,assembled=domain,ohlc=bars,initial_cash='20000',fee_bps='1',slippage_bps='10',max_new_searches=1,risk=MonthlyExitCoreResearchAdapter(),selector=lambda **args:raw_fixture(args))
        self.assertEqual(book['status'],'COMPLETE',book.get('reason'))
        proof=review(book,domain,bars,initial_cash='20000',dividend_events=[],signals=signals,signal_source_hashes={'qqq':'pinned'},verify_selections=True,verify_risk_provider=True,expected_fee_bps='1',expected_slippage_bps='10')
        self.assertEqual(proof['selection_proofs_checked'],1)

    def test_on_off_on_uses_changed_branch_account(self):
        from fractions import Fraction as F
        decisions=['2024-09-30','2024-10-31','2024-11-29']
        sessions=['2024-09-30','2024-10-01','2024-10-31','2024-11-01','2024-11-29','2024-12-02']
        signals={}
        for i,day in enumerate(decisions):
            endmonth=9+i; months=[(2023,12)]+[(2024,m) for m in range(1,12)]
            months=months[i:i+10]
            rows=[dict(date=f'{y}-{m:02d}-{calendar.monthrange(y,m)[1]}',close='100',source='qqq') for y,m in months]
            rows[-1].update(date=day,close='99' if i==1 else '101')
            signals[day]=dict(decision_date=day,completed_month_end_prices=rows)
        plans=[dict(decision_date=day,active_date=sessions[sessions.index(day)+1],search_arguments={'fee_bps':'0'},valuation_quotes=[dict(security_id='A',price='100')],source_hashes={}) for day in decisions]
        domain=dict(session_dates=sessions,monthly_inputs=plans,close_prices={'A':{d:'100' for d in sessions}},provider_actions=[],actions=[],distribution_events=[],cash_stock_merger_events=[],fractional_settlements={},price_source_references={},distribution_fractional_cash_values={})
        bars={'A':{d:dict(open='100',high='100',low='100',close='100') for d in sessions}}
        calls=[]
        def select(**args):
            calls.append(deepcopy(args));a=args['account_state']
            return dict(decision_date=args['decision_date'],target_quantities={'A':1},investable_equity=str(F(a['cash'])+sum(a['shares'].values())*100))
        with patch.object(frontier,'rerank',side_effect=lambda value:value):
            book=run_trend(signals=signals,signal_source_hashes={'qqq':'pinned'},assembled=domain,ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='5',max_new_searches=3,risk=MonthlyExitCoreResearchAdapter(),selector=select)
        self.assertEqual(book['status'],'COMPLETE',book.get('reason'))
        self.assertEqual(len(calls),2)
        self.assertEqual(F(calls[-1]['account_state']['cash']),F('999.9'))
        self.assertEqual(sum(calls[-1]['account_state']['shares'].values()),0)
        self.assertNotEqual(calls[0]['account_state'],calls[-1]['account_state'])
        self.assertEqual(book['trend_diagnostics']['off_decisions'],1)

    def test_on_signal_tamper_rejected(self):
        signals,_=self.fixture();record=signals['2024-09-30'];record['completed_month_end_prices'][-1]['close']='101'
        selection=dict(trend_signal=signal_proof(record),trend_signal_source_hashes={'qqq':'pinned'})
        selection['trend_signal']['risk_on']=False
        with self.assertRaisesRegex(ValueError,'ON_SIGNAL_PROOF'):
            review_trend_decision(selection,arguments={'decision_date':'2024-09-30'},signal_input=record,signal_source_hashes={'qqq':'pinned'})

    def test_on_signal_pin_tamper_rejected(self):
        signals,_=self.fixture();record=signals['2024-09-30'];record['completed_month_end_prices'][-1]['close']='101'
        selection=dict(trend_signal=signal_proof(record),trend_signal_source_hashes={'qqq':'wrong'})
        with self.assertRaisesRegex(ValueError,'ON_SIGNAL_PROOF'):
            review_trend_decision(selection,arguments={'decision_date':'2024-09-30'},signal_input=record,signal_source_hashes={'qqq':'pinned'})


if __name__=='__main__':unittest.main()
