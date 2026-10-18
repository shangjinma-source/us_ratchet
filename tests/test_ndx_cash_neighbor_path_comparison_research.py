from copy import deepcopy
from datetime import date,timedelta
from decimal import localcontext,Inexact
from fractions import Fraction
from unittest.mock import patch
import unittest
from backtest import ndx_cash_neighbor_path_comparison_research as m


def ref(name,pointer):return dict(path=name,sha256='a'*64,json_pointer=pointer)

def fixture():
    cases=[];scope=dict(orders_executed=False,point_in_time_verified=False,promotion_allowed=False,dividends_modelled=False,corporate_actions_modelled=False)
    for li,lane in enumerate(m.LANES):
        for di,(decision,execution,n)in enumerate(m.CLOCKS):
            for ai,amount in enumerate(('1000','10000')):
                i=len(cases);sid=f'case-{i}';pathid=decision+'|'+amount;pi=di*2+ai
                days=[execution]+[(date(2023,9,1)-timedelta(days=j)).isoformat()for j in range(n-2,-1,-1)]if n>1 else [execution];calendar=[decision]+days
                row=dict(scenario_id=sid,lane=lane,holdings={'A':10,'Z':0},starting_cash_usd='1000',transaction_cost_bps='10',cash_event=dict(decision_date=decision,execution_date=execution,amount_usd=amount),**{k:False for k in ('orders_executed','point_in_time_verified','promotion_allowed')});ir=ref('original',f'/rows/{i}')
                initial=dict(session=decision,cash_usd='1000',holdings={'A':10,'Z':0},close_prices={'A':'10','Z':'1'})
                daily=[dict(session=d,cash_injection_usd=amount if j==0 else '0',cumulative_twr=m.ratio(Fraction(0)),holdings_before=deepcopy(initial['holdings']),buy_shares={},fees_usd='0',gross_buy_usd='0')for j,d in enumerate(days)]
                acc=dict(schema='BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1',rows=daily,chained_twr=m.ratio(Fraction(0)),total_cash_injection_usd=amount,transaction_cost_bps='10',cash_event_timing='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES',**scope)
                inputs=dict(initial=initial,transaction_cost_bps='10',sessions=[dict(session=d,buy_shares={},cash_injection_usd=amount if j==0 else '0')for j,d in enumerate(days)]);zero=dict(account=deepcopy(acc),account_reference=ref('old-paired',f'/rows/{i}/paths/zero/account'),accounting_inputs=deepcopy(inputs),inputs_reference=ref('old-paired',f'/rows/{i}/paths/zero/accounting_inputs'),evidence_reference=ref('old-audit',f'/rows/{i}'))
                incacc=dict(acc,schema='SIGNED_FLOW_FROZEN_INCUMBENT_OPEN_ACCOUNT_V1',initial=deepcopy(initial),daily=deepcopy(daily),cash_event_timing='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES',flow_policy='FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN',risk_is_order_gate=False);del incacc['rows']
                inc=dict(account=incacc,account_reference=ref('incumbent',f'/paths/{pi}/account'),evidence_reference=ref('inc-audit',f'/paths/{pi}'),mapping=dict(scenario_id=sid,path_id=pathid,original_input_row=deepcopy(row),input_reference=ir),mapping_reference=ref('incumbent',f'/scenario_mappings/{pi*4+li}'))
                candidate=dict(status='AVAILABLE_NEW',reason=None,account=acc,account_reference=ref('new-raw',f'/rows/{i}/account'),accounting_inputs=inputs,inputs_reference=ref('new-request',f'/rows/{i}/accounting_request'),evidence_reference=ref('new-audit',f'/cases/{i}'))
                baseline=m.metrics_core.metrics(calendar,[Fraction(1)]*len(calendar));saved={role:dict(metrics=deepcopy(baseline),reference=ref('old-comparison',f'/rows/{i}/{role}'),evidence_reference=ref('comparison-audit',f'/rows/{i}'))for role in ('same_flow_zero_trade_control','same_flow_incumbent','fund_012922_cny_nav_reference')}
                cases.append(dict(scenario_id=sid,input_row=row,input_reference=ir,selection_reference=ref('selection',f'/cases/{i}'),calendar=calendar,calendar_reference=ref('original-calendar',f'/windows/{di}'),candidate=candidate,zero_trade_control=zero,incumbent=inc,nav_rows=[dict(session=d,nav_date=d,value='1',reference=ref('nav',f'/rows/{j}'))for j,d in enumerate(calendar)],nav_evidence_reference=ref('nav-audit','/report'),saved_reference_metrics=saved))
    return dict(cases=cases,expected_scenario_ids=[c['scenario_id']for c in cases])


class Tests(unittest.TestCase):
    def test_saved_reference_metrics_only_candidate_computed_and_immutable(self):
        a=fixture();before=deepcopy(a)
        with patch.object(m.metrics_core,'metrics',wraps=m.metrics_core.metrics)as fn:out=m.compare_selected_cash_paths(**a)
        self.assertEqual(fn.call_count,40);self.assertEqual(a,before);self.assertEqual(out['incumbent_path_count'],10);self.assertEqual(out['candidate_status_counts']['AVAILABLE_NEW'],40);self.assertEqual(out['rows'][0]['metrics']['fund_012922_cny_nav_reference']['currency_label'],'CNY');self.assertFalse(out['currency_fx_equivalence_verified'])
        self.assertEqual(out['rows'][0]['original_case_evidence']['candidate']['account_reference']['path'],'new-raw')

    def test_twr_drawdown_absolute_distance_and_n1_hostile_context(self):
        a=fixture();first=a['cases'][0]['candidate']['account'];first['rows'][0]['cumulative_twr']=m.ratio(Fraction(1,5));first['rows'][-1]['cumulative_twr']=m.ratio(Fraction(1,10));first['chained_twr']=m.ratio(Fraction(1,10))
        # All intermediate wealth is 1, giving drawdown 1 - 1/1.2 = 1/6.
        with localcontext()as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True;out=m.compare_selected_cash_paths(**a)
        self.assertEqual(out['rows'][0]['metrics']['candidate']['maximum_drawdown'],m.ratio(Fraction(1,6)));self.assertEqual(out['rows'][0]['candidate_minus_incumbent_nav_distance']['maximum_drawdown_absolute_distance_difference'],m.ratio(Fraction(1,6)));self.assertEqual(out['rows'][8]['metrics']['candidate']['interval_count'],1)

    def test_absent_is_not_zero_cash_and_no_reference_recompute(self):
        a=fixture();c=a['cases'][0]['candidate'];c.update(status='TECHNICAL_FAILURE',reason='saved failure',account=None,account_reference=None,accounting_inputs=None,inputs_reference=None)
        with patch.object(m.metrics_core,'metrics',wraps=m.metrics_core.metrics)as fn:out=m.compare_selected_cash_paths(**a)
        self.assertEqual(fn.call_count,39);self.assertIsNone(out['rows'][0]['metrics']['candidate']);self.assertIsNone(out['rows'][0]['candidate_minus_references']);self.assertEqual(out['rows'][1]['metrics']['candidate']['cumulative_return'],m.ratio(Fraction(0)))

    def test_saved_markdown_audit_is_not_fake_json_pointer(self):
        a=fixture();c=a['cases'][0];report=dict(path='saved-review.md',sha256='a'*64,document_scope='WHOLE_MARKDOWN_REPORT')
        c['nav_evidence_reference']=deepcopy(report);c['saved_reference_metrics']['same_flow_incumbent']['evidence_reference']=deepcopy(report)
        out=m.compare_selected_cash_paths(**a);self.assertEqual(out['rows'][0]['original_case_evidence']['nav_evidence_reference'],report)
        c['nav_evidence_reference']['document_scope']='ASSUMED_JSON_REPORT'
        with self.assertRaises(ValueError):m.compare_selected_cash_paths(**a)

    def test_calendar_flow_source_and_saved_reference_conflicts(self):
        for mode in ('missing','future','navconflict','flow','initial','mapping','reference','saved','order','bool','input_buy','input_flow','first_holdings','zero_fee'):
            a=fixture();c=a['cases'][0]
            if mode=='missing':c['candidate']['account']['rows'].pop(1)
            elif mode=='future':c['nav_rows'][0]['nav_date']='2023-04-29'
            elif mode=='navconflict':c['nav_rows'][1].update(nav_date=c['nav_rows'][0]['nav_date'],value='2')
            elif mode=='flow':c['incumbent']['account']['daily'][1]['cash_injection_usd']='1'
            elif mode=='initial':c['candidate']['accounting_inputs']['initial']['holdings']['Z']=1
            elif mode=='mapping':c['incumbent']['mapping']['scenario_id']='foreign'
            elif mode=='reference':c['candidate']['account_reference']['json_pointer']=''
            elif mode=='saved':c['saved_reference_metrics']['same_flow_incumbent']['metrics']['wealth'][-1]['normalized_wealth']=m.ratio(Fraction(2))
            elif mode=='order':a['expected_scenario_ids'].reverse()
            elif mode=='input_buy':c['candidate']['accounting_inputs']['sessions'][0]['buy_shares']={'A':1}
            elif mode=='input_flow':c['candidate']['accounting_inputs']['sessions'][0]['cash_injection_usd']='2'
            elif mode=='first_holdings':c['candidate']['account']['rows'][0]['holdings_before']['Z']=1
            elif mode=='zero_fee':c['zero_trade_control']['accounting_inputs']['transaction_cost_bps']='0'
            else:c['candidate']['account']['point_in_time_verified']=0
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.compare_selected_cash_paths(**a)

if __name__=='__main__':unittest.main()
