from copy import deepcopy
from decimal import localcontext, Inexact
from unittest.mock import patch
import unittest
from test_ndx_single_replacement_path_comparison_research import fixture
from backtest import ndx_single_replacement_path_comparison_research as producer
from backtest import ndx_single_replacement_comparison_inspection_research as inspector


def sample():
    args=fixture()
    return args, producer.compare_selected_single_replacement_paths(**args)

class Tests(unittest.TestCase):
    def test_real_signed_forty_independent_arithmetic_and_hostile_context(self):
        args,saved=sample();before=deepcopy((args,saved))
        with patch.object(producer,'compare_selected_single_replacement_paths',side_effect=AssertionError('producer forbidden')),patch.object(producer.metrics_core,'metrics',side_effect=AssertionError('metrics forbidden')):
            with localcontext() as ctx:
                ctx.prec=1;ctx.traps[Inexact]=True
                result=inspector.inspect_comparison(**args,comparison=saved)
        self.assertEqual(result['status'],'PASS');self.assertEqual(len(result['rows']),40)
        self.assertEqual((args,saved),before)
        self.assertFalse(result['signed_cash_ledger_replayed'])

    def test_wrong_numeric_fields_and_complete_schema(self):
        args,saved=sample()
        for attack in ('annual','dd','wealth','distance','reference','extra','bool','order'):
            bad=deepcopy(saved);row=bad['rows'][8]
            if attack=='annual':row['metrics']['candidate']['annualized_return_diagnostic_decimal']='0'
            elif attack=='dd':row['metrics']['candidate']['maximum_drawdown']={'numerator':'0','denominator':'1'}
            elif attack=='wealth':row['metrics']['candidate']['wealth'][0]['normalized_wealth']['numerator']='2'
            elif attack=='distance':row['candidate_minus_incumbent_nav_distance']['formal_noninferiority']=True
            elif attack=='reference':row['metrics']['same_flow_incumbent']['annualized_return_diagnostic_decimal']='99'
            elif attack=='extra':row['metrics']['candidate']['verified']=True
            elif attack=='bool':bad['scenario_count']=True
            else:bad['rows'][0],bad['rows'][1]=bad['rows'][1],bad['rows'][0]
            with self.subTest(attack=attack),self.assertRaises(ValueError):inspector.inspect_comparison(**args,comparison=bad)

    def test_re_signed_context_cannot_drop_negative_leg_or_forge_audit(self):
        args,saved=sample()
        for attack in ('negative','audit','fee','flow','capital','clock'):
            a=deepcopy(args);b=deepcopy(saved);c=a['cases'][0]['candidate']
            if attack=='negative':c['accounting_inputs']['sessions'][0]['trade_shares']['A']=0
            elif attack=='audit':c['account_inspection']['saved_result_content_sha256']='0'*64
            elif attack=='fee':c['account']['rows'][0]['fees_usd']='0'
            elif attack=='flow':c['accounting_inputs']['sessions'][1]['cash_injection_usd']='1'
            elif attack=='capital':c['accounting_inputs']['initial']['cash_usd']='1001'
            else:c['account_inspection']['session_count']=True
            b['rows'][0]['original_case_evidence']=deepcopy(a['cases'][0])
            with self.subTest(attack=attack),self.assertRaises(ValueError):inspector.inspect_comparison(**a,comparison=b)

    def test_missing_all_forty_keeps_three_references(self):
        args=fixture()
        for case in args['cases']:
            c=case['candidate'];c.update(status='NO_FEASIBLE',reason='saved no feasible point')
            for key in ('account','account_reference','accounting_inputs','inputs_reference','account_inspection','inspection_reference'):c[key]=None
        saved=producer.compare_selected_single_replacement_paths(**args)
        result=inspector.inspect_comparison(**args,comparison=saved)
        self.assertEqual(result['candidate_status_counts']['NO_FEASIBLE'],40)
        self.assertTrue(all(not row['candidate_metrics_reconstructed'] for row in result['rows']))

if __name__=='__main__':unittest.main()
