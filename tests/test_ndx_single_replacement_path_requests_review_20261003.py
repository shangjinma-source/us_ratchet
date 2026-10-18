from copy import deepcopy
from fractions import Fraction
import unittest
from backtest import ndx_single_replacement_path_requests_research as m
from backtest import ndx_signed_cash_flow_return_accounting_research as account
from backtest import ndx_signed_cash_flow_account_inspection_research as inspection
from test_ndx_single_replacement_path_requests_research import fixture

class Tests(unittest.TestCase):
 def test_real_signed_account_and_independent_ledger_all_clock_lengths(self):
  args=fixture(); before=deepcopy(args); out=m.prepare_single_replacement_path_requests(**args)
  for index in (0,8,16,24,32):
   req=out['rows'][index]['accounting_request']
   result=account.account_path(**req)
   report=inspection.inspect_saved_signed_account(**req,saved_result=result)
   self.assertEqual(report['status'],'PASS')
   self.assertEqual(Fraction(out['rows'][index]['expected_first_trade']['total_fee_usd']),Fraction(3,25))
  self.assertEqual(args,before)
 def test_invalid_decimal_cannot_be_ready_for_account(self):
  for value in (' 10','9e40'):
   a=fixture();a['old_paired_rows'][0]['paths']['candidate']['accounting_inputs']['sessions'][1]['close_prices']['A']=value
   with self.subTest(value=value),self.assertRaises(ValueError):m.prepare_single_replacement_path_requests(**a)
  a=fixture();a['selection']['document']['no_feasible_case_count']=False;a['selection']['content_sha256']=m.digest(a['selection']['document'])
  with self.assertRaises(ValueError):m.prepare_single_replacement_path_requests(**a)
 def test_source_locator_and_detached_complete_requests(self):
  a=fixture();out=m.prepare_single_replacement_path_requests(**a)
  self.assertEqual(len(out['rows']),40)
  self.assertEqual(out['rows'][39]['selection_reference']['json_pointer'],'/selection/document/rows/39')
  out['rows'][0]['accounting_request']['sessions'][0]['trade_shares']['A']=0
  self.assertEqual(a['selection']['document']['rows'][0]['selected']['task']['signed_trade_quantities']['A'],-10)
  self.assertIsNone(out['rows'][0]['reused_candidate_path_reference'])

if __name__=='__main__':unittest.main()

