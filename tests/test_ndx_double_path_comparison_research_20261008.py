from copy import deepcopy
from fractions import Fraction
from unittest.mock import patch
import unittest
from test_ndx_cash_neighbor_path_comparison_research import fixture as reference_fixture,ref
from backtest import ndx_double_replacement_path_comparison_research as pure
from backtest import ndx_double_replacement_comparison_inspection_research as checker
from backtest import ndx_signed_cash_flow_return_accounting_research as account
from backtest import ndx_signed_cash_flow_account_inspection_research as inspector

def fixture():
    args=reference_fixture()
    for i,case in enumerate(args['cases']):
        holdings={'A':5,'B':5,'Z':0};initial=dict(session=case['calendar'][0],cash_usd='1000',holdings=holdings,close_prices={'A':'10','B':'10','Z':'1'})
        case['input_row']['holdings']=deepcopy(holdings);case['incumbent']['mapping']['original_input_row']=deepcopy(case['input_row']);case['incumbent']['account']['initial']=deepcopy(initial)
        zero=case['zero_trade_control'];zero['accounting_inputs']['initial']=deepcopy(initial)
        for r in zero['account']['rows']:r['holdings_before']=deepcopy(holdings)
        sessions=[dict(session=d,open_prices={'A':'10','B':'10','C':'1','Z':'1'},close_prices={'A':'10','B':'10','C':'1','Z':'1'},cash_injection_usd=case['input_row']['cash_event']['amount_usd']if j==0 else'0',trade_shares={'A':-5,'B':-5,'C':1,'Z':10}if j==0 else{})for j,d in enumerate(case['calendar'][1:])]
        inputs=dict(initial=deepcopy(initial),sessions=sessions,transaction_cost_bps='10');result=account.account_path(**inputs);inspection=inspector.inspect_saved_signed_account(**inputs,saved_result=result)
        case['candidate'].update(status='AVAILABLE_NEW_SIGNED',accounting_inputs=inputs,account=result,account_inspection=inspection,inspection_reference=ref('signed-audit',f'/rows/{i}/inspection'))
    return args

class Tests(unittest.TestCase):
    def test_complete_double_native_labels_three_references_unchanged(self):
        args=fixture();before=deepcopy(args)
        with patch.object(pure.metrics_core,'metrics',wraps=pure.metrics_core.metrics)as call:result=pure.compare_selected_double_replacement_paths(**args)
        self.assertEqual(call.call_count,40);self.assertEqual(args,before)
        with patch.object(pure.metrics_core,'metrics',side_effect=AssertionError('No producer metrics')):report=checker.inspect_comparison(comparison=result,**args)
        self.assertEqual(report['status'],'PASS');self.assertFalse(result['economic_winner_selected']);self.assertEqual(result['schema'],'DOUBLE_REPLACEMENT_SIGNED_REFERENCE_COMPARISON_V1')
        for case,row in zip(args['cases'],result['rows']):
            for role,entry in case['saved_reference_metrics'].items():
                for key,value in entry['metrics'].items():self.assertEqual(row['metrics'][role][key],value)
        #1100 initial+1000 flow, fees (100+11)*.001; n=1 retains initial wealth.
        self.assertEqual(result['rows'][8]['metrics']['candidate']['cumulative_return'],pure.ratio(-Fraction(111,2100000)))
    def test_absence_single_leg_and_resigned_metric_attacks(self):
        args=fixture()
        for case,status in zip(args['cases'],pure.ABSENT):
            c=case['candidate'];c.update(status=status,reason='Synthetic saved absence')
            for key in ('account','account_reference','accounting_inputs','inputs_reference','account_inspection','inspection_reference'):c[key]=None
        result=pure.compare_selected_double_replacement_paths(**args);checker.inspect_comparison(comparison=result,**args)
        self.assertIsNone(result['rows'][0]['metrics']['candidate']);self.assertIsNotNone(result['rows'][0]['metrics']['same_flow_incumbent'])
        result['rows'][-1]['metrics']['candidate']['maximum_drawdown']=pure.ratio(Fraction(1,2))
        with self.assertRaises(ValueError):checker.inspect_comparison(comparison=result,**args)
        args=fixture();c=args['cases'][0]['candidate'];c['accounting_inputs']['sessions'][0]['trade_shares']['B']=0;c['account']=account.account_path(**c['accounting_inputs']);c['account_inspection']=inspector.inspect_saved_signed_account(**c['accounting_inputs'],saved_result=c['account'])
        with self.assertRaises(ValueError):pure.compare_selected_double_replacement_paths(**args)

if __name__=='__main__':unittest.main()
