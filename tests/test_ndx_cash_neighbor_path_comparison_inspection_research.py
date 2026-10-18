import copy,importlib.util,sys,unittest
from pathlib import Path
from fractions import Fraction
from decimal import localcontext,Inexact
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_cash_neighbor_path_comparison_inspection_research as m
from backtest import ndx_cash_neighbor_path_comparison_research as producer
spec=importlib.util.spec_from_file_location('cash_comparison_fixture',ROOT/'tests/test_ndx_cash_neighbor_path_comparison_research.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def fixture():
 a=f.fixture();acc=a['cases'][0]['candidate']['account'];acc['rows'][0]['cumulative_twr']=producer.ratio(Fraction(1,5));acc['rows'][-1]['cumulative_twr']=producer.ratio(Fraction(1,10));acc['chained_twr']=producer.ratio(Fraction(1,10))
 n1=a['cases'][8]['candidate']['account'];n1['rows'][0]['cumulative_twr']=producer.ratio(Fraction(1,100));n1['chained_twr']=producer.ratio(Fraction(1,100))
 return a,producer.compare_selected_cash_paths(**a)

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.args,cls.output=fixture()
 def test_complete_forty_independent_numeric_and_no_mutation(self):
  a,out=copy.deepcopy((self.args,self.output));before=copy.deepcopy((a,out))
  with localcontext()as ctx:
   ctx.prec=2;ctx.traps[Inexact]=True;r=m.inspect_comparison(**a,comparison=out)
  self.assertEqual((a,out),before);self.assertEqual(r['scenario_count'],40);self.assertEqual(r['rows'][8]['interval_count'],1);self.assertFalse(r['source_bytes_authenticated'])
 def test_candidate_and_comparison_mutations_rejected(self):
  for mode in ('dd','annual','wealth','diff','distance','scope','refs','bool'):
   a,out=copy.deepcopy((self.args,self.output));row=out['rows'][0]
   if mode=='dd':row['metrics']['candidate']['maximum_drawdown']=m.ratio(Fraction(0))
   elif mode=='annual':row['metrics']['candidate']['annualized_return_diagnostic_decimal']='0'
   elif mode=='wealth':row['metrics']['candidate']['wealth'][1]['normalized_wealth']=m.ratio(Fraction(1))
   elif mode=='diff':row['candidate_minus_references']['same_flow_incumbent']['cumulative_return']=m.ratio(Fraction(-1,10))
   elif mode=='distance':row['candidate_minus_incumbent_nav_distance']['maximum_drawdown_absolute_distance_difference']=m.ratio(Fraction(-1,6))
   elif mode=='scope':row['nav_currency']='USD'
   elif mode=='refs':row['original_case_evidence']['candidate']['account_reference']['path']='old-paired'
   else:row['formal_dual_benchmark_admission']=0
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_case(case=a['cases'][0],comparison_row=row,scenario_index=0)
 def test_old_metric_is_exact_evidence_copy_and_missing_is_not_cash(self):
  a=f.fixture();a['cases'][0]['saved_reference_metrics']['same_flow_incumbent']['metrics']['annualized_return_diagnostic_decimal']='0.123456789'
  c=a['cases'][0]['candidate'];c.update(status='TECHNICAL_FAILURE',reason='saved error',account=None,account_reference=None,accounting_inputs=None,inputs_reference=None)
  out=producer.compare_selected_cash_paths(**a);m.inspect_comparison(**a,comparison=out)
  altered=copy.deepcopy(out['rows'][0]);altered['metrics']['same_flow_incumbent']['annualized_return_diagnostic_decimal']='0'
  with self.assertRaises(ValueError):m.inspect_case(case=a['cases'][0],comparison_row=altered,scenario_index=0)
  altered=copy.deepcopy(out['rows'][0]);altered['metrics']['candidate']=copy.deepcopy(out['rows'][1]['metrics']['candidate'])
  with self.assertRaises(ValueError):m.inspect_case(case=a['cases'][0],comparison_row=altered,scenario_index=0)
 def test_calendar_flow_and_all_denominators(self):
  for mode in ('calendar','buy','flow','count','order'):
   a,out=copy.deepcopy((self.args,self.output))
   if mode=='calendar':a['cases'][0]['calendar'].pop(1)
   elif mode=='buy':a['cases'][0]['candidate']['accounting_inputs']['sessions'][0]['buy_shares']={'A':1}
   elif mode=='flow':a['cases'][0]['candidate']['account']['rows'][1]['cash_injection_usd']='1'
   elif mode=='count':out['scenario_count']=True
   else:a['expected_scenario_ids'].reverse()
   # Re-signing the preserved case cannot conceal inconsistent source structures.
   out['rows'][0]['original_case_evidence']=copy.deepcopy(a['cases'][0])
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_comparison(**a,comparison=out)
if __name__=='__main__':unittest.main()
