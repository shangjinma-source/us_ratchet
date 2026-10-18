from copy import deepcopy
from decimal import Context,Decimal,localcontext,Inexact
from fractions import Fraction as F
from unittest.mock import patch
import unittest
from backtest import ndx_single_replacement_path_comparison_research as m
from backtest import ndx_signed_cash_flow_return_accounting_research as account
from backtest import ndx_signed_cash_flow_account_inspection_research as ledger
from test_ndx_single_replacement_path_comparison_research import fixture

def ratio(value):return dict(numerator=str(value.numerator),denominator=str(value.denominator))

def regenerate(candidate):
 candidate['account']=account.account_path(**candidate['accounting_inputs'])
 candidate['account_inspection']=ledger.inspect_saved_signed_account(**candidate['accounting_inputs'],saved_result=candidate['account'])

class Tests(unittest.TestCase):
 def test_actual_fee_initial_one_n1_and_midpath_drawdown_no_reference_recompute(self):
  args=fixture();c=args['cases'][0]['candidate'];c['accounting_inputs']['sessions'][0]['close_prices']['Z']='100';regenerate(c);before=deepcopy(args)
  with patch.object(m.metrics_core,'metrics',wraps=m.metrics_core.metrics)as compute,localcontext()as ctx:
   ctx.prec=1;ctx.traps[Inexact]=True;out=m.compare_selected_single_replacement_paths(**args)
  self.assertEqual(compute.call_count,40);self.assertEqual(args,before)
  # New cash2100 before fee. After fee cash2089.89 plus ten Z; first peak3089.89 then2099.89.
  self.assertEqual(out['rows'][0]['metrics']['candidate']['maximum_drawdown'],ratio(F(99000,308989)))
  metric=out['rows'][8]['metrics']['candidate'];loss=F(11,210000)
  self.assertEqual(metric['cumulative_return'],ratio(-loss));self.assertEqual(metric['maximum_drawdown'],ratio(loss));self.assertEqual(metric['interval_count'],1)
  with localcontext(Context(prec=80)):
   independent=(Decimal(209989)/Decimal(210000))**252-1
   self.assertLess(abs(Decimal(metric['annualized_return_diagnostic_decimal'])-independent),Decimal('1e-72'))
  self.assertEqual(out['rows'][8]['metrics']['fund_012922_cny_nav_reference']['currency_label'],'CNY')
  for source,row in zip(args['cases'],out['rows']):
   for role,env in source['saved_reference_metrics'].items():
    for key,value in env['metrics'].items():self.assertEqual(row['metrics'][role][key],value)
  for key in ('formal_cohort_statistics_computed','formal_dual_benchmark_admission','currency_fx_equivalence_verified','promotion_allowed'):self.assertIs(out[key],False)
  self.assertEqual(out['rows'][0]['original_case_evidence']['candidate']['accounting_inputs']['sessions'][0]['trade_shares']['A'],-10)
 def test_real_altered_paths_or_inspection_identity_cannot_be_substituted(self):
  original=fixture()
  for kind in ('cash','no_sell','later_sell','hash','bool_count','missing_day'):
   args=deepcopy(original);c=args['cases'][0]['candidate']
   if kind=='cash':
    other=deepcopy(c['accounting_inputs']);other['initial']['cash_usd']='1001';c['account']=account.account_path(**other);c['account_inspection']=ledger.inspect_saved_signed_account(**other,saved_result=c['account'])
   elif kind=='no_sell':c['accounting_inputs']['sessions'][0]['trade_shares']['A']=0;regenerate(c)
   elif kind=='later_sell':c['accounting_inputs']['sessions'][1]['trade_shares']={'Z':-1};regenerate(c)
   elif kind=='hash':c['account_inspection']['saved_result_content_sha256']='0'*64
   elif kind=='bool_count':args['cases'][8]['candidate']['account_inspection']['session_count']=True
   else:c['accounting_inputs']['sessions'].pop(2);regenerate(c)
   with self.subTest(kind=kind),self.assertRaises(ValueError):m.compare_selected_single_replacement_paths(**args)
 def test_full_absence_partition_preserves_three_references(self):
  args=fixture()
  for case in args['cases']:
   c=case['candidate'];c.update(status='NO_FEASIBLE',reason='Declared fully inspected family has no feasible point')
   for key in ('account','account_reference','accounting_inputs','inputs_reference','account_inspection','inspection_reference'):c[key]=None
  with patch.object(m.metrics_core,'metrics',side_effect=AssertionError('No new candidate metrics')):out=m.compare_selected_single_replacement_paths(**args)
  self.assertEqual(len(out['rows']),40);self.assertEqual(out['candidate_status_counts']['NO_FEASIBLE'],40)
  for row in out['rows']:
   self.assertIsNone(row['metrics']['candidate']);self.assertIsNone(row['candidate_minus_references']);self.assertIsNotNone(row['metrics']['same_flow_incumbent'])

if __name__=='__main__':unittest.main()
