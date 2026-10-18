import unittest
from copy import deepcopy
from fractions import Fraction
from unittest.mock import Mock,patch
from scripts import ndx_old_holding_topup_paired_account_20261002 as m
from backtest.ndx_cash_flow_return_accounting_research import account_path
from test_ndx_old_holding_topup_paired_account_20261002 import pair_fixture,document_fixture

class IndependentTests(unittest.TestCase):
    def test_initial_close_not_execution_mark_and_flow_not_profit(self):
        row,plan,days,p,c,refs=pair_fixture()
        p['matrices']['close'][days[0]]['A']='5';c['A'][days[0]][1]['nominal_close']=5.0
        out=m.calculate_pair(row,plan,days,p,'',c,refs,account_path)
        a=out['paths']['candidate']['account'];b=out['paths']['same_flow_zero_trade_control']['account']
        self.assertEqual(a['initial_equity_usd'],'150');self.assertEqual(b['initial_equity_usd'],'150')
        self.assertEqual(a['rows'][0]['pre_flow_open_equity_usd'],'300')
        self.assertEqual(a['rows'][0]['post_flow_pre_fee_open_equity_usd'],'1300')
        self.assertEqual(m.from_ratio(b['chained_twr']),1)
        self.assertEqual(m.from_ratio(a['chained_twr']),2*Fraction(12999,13000)-1)
        self.assertEqual(m.from_ratio(out['candidate_minus_control']['chained_twr_difference']),Fraction(-1,6500))
        self.assertFalse(out['equal_horizons_across_decision_dates_claimed'])
    def test_saved_float_type_and_currency_and_zero_initial_key(self):
        for mutation in ('float','currency','zero'):
            row,plan,days,p,c,refs=pair_fixture()
            if mutation=='float':c['A'][days[0]][1]['nominal_close']='10.0'
            elif mutation=='currency':c['C'][days[0]][1]['currency']='CNY'
            else:del p['matrices']['close'][days[0]]['C']
            with self.subTest(mutation=mutation),self.assertRaises((ValueError,KeyError)):
                m.calculate_pair(row,plan,days,p,'',c,refs,Mock())
    def test_source_flags_and_full_context_not_upgraded(self):
        docs,refs=document_fixture();docs['control']['price_identity_binding_verified']=True
        with self.assertRaisesRegex(ValueError,'authority'):m.assemble(docs,refs,Mock())
        docs,refs=document_fixture();before=deepcopy(docs)
        with patch.object(m,'calculate_pair',return_value={'synthetic_only':True}):out=m.assemble(docs,refs,Mock())
        self.assertEqual(docs,before);self.assertEqual(out['rows'][0]['input_row']['gaps'],['synthetic unresolved'])
        self.assertFalse(out['continuous_forty_scenario_strategy_claimed']);self.assertFalse(out['formal_dual_benchmark_comparison'])
        self.assertNotIn('execution',out['incumbent_price_metadata_without_old_execution_or_quote_rows'])
    def test_different_window_or_zero_key_plan_rejected(self):
        row,plan,days,p,c,refs=pair_fixture();row['cash_event']['decision_date']='2023-07-31'
        with self.assertRaises((ValueError,KeyError)):m.calculate_pair(row,plan,days,p,'',c,refs,Mock())
        docs,refs=document_fixture();r=docs['topups']['rows'][0];del r['evaluation']['branches'][0]['evaluated_plans'][0]['buy_shares']['C']
        with self.assertRaisesRegex(ValueError,'Complete buy domain'):m.selected_plan(r,docs['inputs']['rows'][0])

if __name__=='__main__':unittest.main()
