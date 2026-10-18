import ast
from copy import deepcopy
from decimal import localcontext,Inexact
from pathlib import Path
import unittest
from test_ndx_multidecision_path_comparison_research import fixture
from backtest import ndx_multidecision_path_comparison_research as producer
from backtest import ndx_multidecision_path_comparison_inspection_research as independent


def sample():
    args=fixture()
    for slot in args['candidate_slots'][8:]:
        daily=slot['result']['daily'];daily[1]['normalized_twr']=.5
        daily[-1]['normalized_twr']=1.125;slot['result']['summary']['chained_twr']=.125
        daily[1]['close_equity_usd']=900000.;daily[1]['total_value_usd']=900000.
    saved=producer.compare_multidecision_paths(**args)
    return args,saved


class Tests(unittest.TestCase):
    def test_full_saved_arithmetic_all_pairs_and_hostile_context(self):
        args,saved=sample();before=deepcopy((args,saved))
        with localcontext() as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True
            r=independent.inspect_multidecision_comparison(saved_comparison=saved,**args)
        self.assertEqual(r['track_count'],16);self.assertEqual(r['account_metric_count'],24);self.assertEqual((args,saved),before)
        self.assertEqual(saved['rows'][8]['candidate']['metrics']['maximum_drawdown'],{'numerator':'1','denominator':'2'})
        self.assertFalse(r['source_bytes_authenticated']);self.assertFalse(r['formal_comparison_passed'])
    def test_modified_metrics_projection_and_false_authority_rejected(self):
        for attack in ('annual','dd','wealth','count','slot','mode','formal','pointer','distance','evidence'):
            args,saved=sample()
            if attack=='annual':saved['rows'][8]['candidate']['metrics']['annualized_return_diagnostic_decimal']='1'
            elif attack=='dd':saved['rows'][8]['candidate']['metrics']['maximum_drawdown']['numerator']='0'
            elif attack=='wealth':saved['rows'][8]['candidate']['metrics']['wealth'][1]['normalized_wealth']['numerator']='5'
            elif attack=='count':saved['counts']['candidate_metrics']=16
            elif attack=='slot':saved['rows'].pop()
            elif attack=='mode':saved['rows'][8]['nav_mode']='STRICT_SAME_SESSION_FX'
            elif attack=='formal':saved['formal_comparison_passed']=True
            elif attack=='pointer':saved['source_references']['nav_metrics']['json_pointer']='/foreign'
            elif attack=='distance':saved['rows'][8]['distances']['candidate_minus_control_absolute_distance']['maximum_drawdown']='0'
            else:saved['rows'][8]['candidate']['audit_evidence']['reference']['path']='foreign'
            with self.subTest(attack=attack),self.assertRaises(ValueError):independent.inspect_multidecision_comparison(saved_comparison=saved,**args)
    def test_missing_account_or_nav_no_zero_path_substitution(self):
        args,saved=sample()
        mode=args['nav_metrics']['modes']['STRICT_SAME_SESSION_FX'];mode.update(status='BLOCKED_MISSING_REFERENCE_INPUT',metrics=None,missing_sessions=[saved['calendar'][3]]);mode['observations'][3]['saved_value_exact']=None
        slot=args['candidate_slots'][8];slot.update(outcome='NUMERICAL_EXCEPTION',result=None,result_reference=None,audit_evidence=None,reason='Original exception')
        saved=producer.compare_multidecision_paths(**args);r=independent.inspect_multidecision_comparison(saved_comparison=saved,**args)
        self.assertEqual(r['account_metric_count'],23)
        saved['rows'][8]['candidate']['metrics']=deepcopy(saved['rows'][9]['control']['metrics'])
        with self.assertRaises(ValueError):independent.inspect_multidecision_comparison(saved_comparison=saved,**args)
    def test_no_production_imports_and_saved_nav_metric_corruption(self):
        tree=ast.parse(Path(independent.__file__).read_text(encoding='utf-8-sig'))
        modules=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):modules.extend(a.name for a in node.names)
            if isinstance(node,ast.ImportFrom):modules.append(node.module)
        self.assertFalse(any(n.startswith(('backtest','scripts')) for n in modules))
        args,saved=sample();args['nav_metrics']['modes']['BACKWARD_LATEST_VALID_FX']['metrics']['annualized_return_diagnostic_decimal']='9'
        saved=producer.compare_multidecision_paths(**args)
        with self.assertRaisesRegex(ValueError,'NAV metrics'):independent.inspect_multidecision_comparison(saved_comparison=saved,**args)

if __name__=='__main__':unittest.main()
