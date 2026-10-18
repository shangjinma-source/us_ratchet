from copy import deepcopy
from decimal import localcontext, Inexact
from fractions import Fraction
from unittest.mock import patch
import unittest
from test_ndx_cash_neighbor_path_comparison_research import fixture as reference_fixture, ref
from backtest import ndx_single_replacement_path_comparison_research as m
from backtest import ndx_signed_cash_flow_return_accounting_research as account
from backtest import ndx_signed_cash_flow_account_inspection_research as inspection


def fixture():
    args=reference_fixture()
    for i,case in enumerate(args['cases']):
        c=case['candidate'];initial=deepcopy(c['accounting_inputs']['initial'])
        sessions=[dict(session=day,open_prices={'A':'10','Z':'1'},close_prices={'A':'10','Z':'1'},cash_injection_usd=case['input_row']['cash_event']['amount_usd'] if j==0 else '0',trade_shares={'A':-10,'Z':10} if j==0 else {})for j,day in enumerate(case['calendar'][1:])]
        inputs=dict(initial=initial,sessions=sessions,transaction_cost_bps='10')
        result=account.account_path(**inputs)
        report=inspection.inspect_saved_signed_account(**inputs,saved_result=result)
        c.update(status='AVAILABLE_NEW_SIGNED',accounting_inputs=inputs,account=result,account_inspection=report,inspection_reference=ref('signed-audit',f'/rows/{i}/inspection'))
    return args


class Tests(unittest.TestCase):
    def test_real_signed_account_and_inspector_all_forty(self):
        args=fixture();before=deepcopy(args)
        with patch.object(m.metrics_core,'metrics',wraps=m.metrics_core.metrics)as metrics:
            out=m.compare_selected_single_replacement_paths(**args)
        self.assertEqual(metrics.call_count,40);self.assertEqual(args,before)
        self.assertEqual(out['scenario_count'],40);self.assertEqual(out['candidate_status_counts']['AVAILABLE_NEW_SIGNED'],40)
        for original,row in zip(args['cases'],out['rows']):
            for role in original['saved_reference_metrics']:
                for key,value in original['saved_reference_metrics'][role]['metrics'].items():self.assertEqual(row['metrics'][role][key],value)
        self.assertFalse(out['formal_dual_benchmark_admission']);self.assertFalse(out['source_bytes_authenticated'])
        self.assertEqual(out['rows'][0]['metrics']['fund_012922_cny_nav_reference']['currency_label'],'CNY')

    def test_n1_initial_point_retains_both_side_fee(self):
        args=fixture()
        with localcontext()as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True
            out=m.compare_selected_single_replacement_paths(**args)
        metric=out['rows'][8]['metrics']['candidate']
        # Initial 1100, injection1000, sold100+bought10, fee.11: TWR=-.11/2100.
        loss=Fraction(11,210000)
        self.assertEqual(metric['interval_count'],1)
        self.assertEqual(metric['cumulative_return'],m.ratio(-loss))
        self.assertEqual(metric['maximum_drawdown'],m.ratio(loss))
        self.assertEqual(metric['wealth'][0]['normalized_wealth'],m.ratio(Fraction(1)))

    def test_missing_states_keep_all_reference_slots(self):
        args=fixture()
        for case,status in zip(args['cases'],m.ABSENT):
            c=case['candidate'];c.update(status=status,reason='explicit caller declaration')
            for key in ('account','account_reference','accounting_inputs','inputs_reference','account_inspection','inspection_reference'):c[key]=None
        out=m.compare_selected_single_replacement_paths(**args)
        self.assertEqual(len(out['rows']),40)
        for row,status in zip(out['rows'],m.ABSENT):
            self.assertEqual(row['candidate_status'],status);self.assertIsNone(row['metrics']['candidate']);self.assertIsNotNone(row['metrics']['same_flow_incumbent'])
        self.assertTrue(out['technical_statuses_are_caller_declarations']);self.assertFalse(out['actual_failed_source_chain_supported'])

    def test_signed_identity_calendar_mapping_and_inspection_gates(self):
        original=fixture()
        for attack in ('buyonly','missing_negative','calendar','mapping','inspection','permission','reuse','fee','zero_key','different_capital'):
            args=deepcopy(original);case=args['cases'][0];c=case['candidate']
            if attack=='buyonly':c['account']['schema']='BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1'
            elif attack=='missing_negative':
                c['accounting_inputs']['sessions'][0]['trade_shares']['A']=0
                c['account']=account.account_path(**c['accounting_inputs'])
                c['account_inspection']=inspection.inspect_saved_signed_account(**c['accounting_inputs'],saved_result=c['account'])
            elif attack=='different_capital':
                other=deepcopy(c['accounting_inputs']);other['initial']['cash_usd']='2000'
                c['account']=account.account_path(**other)
                c['account_inspection']=inspection.inspect_saved_signed_account(**other,saved_result=c['account'])
            elif attack=='calendar':c['accounting_inputs']['sessions'].pop(1)
            elif attack=='mapping':case['incumbent']['mapping']['scenario_id']='other'
            elif attack=='inspection':c['account_inspection']['saved_result_content_sha256']='0'*64
            elif attack=='permission':c['account_inspection']['point_in_time_verified']=0
            elif attack=='reuse':c['status']='AVAILABLE_REUSED'
            elif attack=='fee':c['account']['rows'][0]['fees_usd']='0'
            else:c['accounting_inputs']['sessions'][0]['trade_shares']['FOREIGN']=0
            with self.subTest(attack=attack),self.assertRaises((ValueError,KeyError)):
                m.compare_selected_single_replacement_paths(**args)
        args=deepcopy(original);args['cases'].pop()
        with self.assertRaises(ValueError):m.compare_selected_single_replacement_paths(**args)

if __name__=='__main__':unittest.main()
