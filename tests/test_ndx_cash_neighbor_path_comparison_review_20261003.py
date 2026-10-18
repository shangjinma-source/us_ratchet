"""Independent synthetic comparisons, no saved accounts or real evaluation."""
import copy,importlib.util,sys,unittest
from pathlib import Path
from fractions import Fraction
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_cash_neighbor_path_comparison_research as m
spec=importlib.util.spec_from_file_location('comparison_fixture',ROOT/'tests/test_ndx_cash_neighbor_path_comparison_research.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def fixture():
 a=f.fixture()
 for c in a['cases']:
  for role in ('candidate','zero_trade_control'):
   e=c[role]
   for inp,day in zip(e['accounting_inputs']['sessions'],e['account']['rows']):
    inp.update(cash_injection_usd=day['cash_injection_usd'],buy_shares=copy.deepcopy(day['buy_shares']))
    day.setdefault('holdings_before',copy.deepcopy(e['accounting_inputs']['initial']['holdings']))
 return a

class Tests(unittest.TestCase):
 def test_input_to_saved_account_binding(self):
  for mode in ('buy','flow','oldshares','zero_fee','zero_flow'):
   a=fixture();c=a['cases'][0]
   if mode=='buy':c['candidate']['accounting_inputs']['sessions'][0]['buy_shares']={'A':1,'Z':0}
   elif mode=='flow':c['candidate']['accounting_inputs']['sessions'][0]['cash_injection_usd']='0'
   elif mode=='oldshares':c['candidate']['account']['rows'][0]['holdings_before']['A']=11
   elif mode=='zero_fee':c['zero_trade_control']['accounting_inputs']['transaction_cost_bps']='0'
   else:c['zero_trade_control']['accounting_inputs']['sessions'][0]['cash_injection_usd']='0'
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.compare_selected_cash_paths(**a)
 def test_same_terminal_different_peak_and_cash_not_performance(self):
  a=fixture();c=a['cases'][0];acc=c['candidate']['account'];acc['rows'][0]['cumulative_twr']=m.ratio(Fraction(1,4))
  acc['terminal_equity_usd']='999999999';before=copy.deepcopy(a)
  out=m.compare_selected_cash_paths(**a);self.assertEqual(a,before)
  candidate=out['rows'][0]['metrics']['candidate'];self.assertEqual(candidate['cumulative_return'],m.ratio(Fraction(0)));self.assertEqual(candidate['maximum_drawdown'],m.ratio(Fraction(1,5)))
  self.assertEqual(out['rows'][8]['metrics']['candidate']['interval_count'],1)
  self.assertGreater(m.value(out['rows'][0]['candidate_minus_incumbent_nav_distance']['maximum_drawdown_absolute_distance_difference']),0)
 def test_all_missing_retains_forty_without_any_metric_recompute(self):
  a=fixture()
  for c in a['cases']:c['candidate'].update(status='UNDISPATCHED',reason='explicit saved not-dispatched',account=None,account_reference=None,accounting_inputs=None,inputs_reference=None)
  with patch.object(m.metrics_core,'metrics',side_effect=AssertionError('No candidate exists')):out=m.compare_selected_cash_paths(**a)
  self.assertEqual(len(out['rows']),40);self.assertEqual(out['candidate_status_counts']['UNDISPATCHED'],40)
  for row in out['rows']:
   self.assertIsNone(row['metrics']['candidate']);self.assertIsNotNone(row['metrics']['same_flow_incumbent']);self.assertFalse(row['formal_dual_benchmark_admission'])
 def test_full_calendar_shared_incumbent_and_source_pointers(self):
  for mode in ('truncate','shared','navfuture','flowbool'):
   a=fixture();c=a['cases'][0]
   if mode=='truncate':c['calendar'].pop(1)
   elif mode=='shared':a['cases'][10]['incumbent']['account_reference']['sha256']='b'*64
   elif mode=='navfuture':c['nav_rows'][0]['nav_date']='2023-05-01'
   else:c['candidate']['account']['rows'][0]['cash_injection_usd']=True
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.compare_selected_cash_paths(**a)
  a=fixture();a['cases'][0]['candidate']['account_reference']['json_pointer']='/new_candidate/result/account'
  out=m.compare_selected_cash_paths(**a);self.assertEqual(out['rows'][0]['original_case_evidence']['candidate']['account_reference']['json_pointer'],'/new_candidate/result/account')
if __name__=='__main__':unittest.main()
