from copy import deepcopy
from fractions import Fraction
import unittest
import tempfile,json
from unittest.mock import patch
from pathlib import Path
from scripts import ndx_single_replacement_signed_paths_independent_readback_20261003 as m
from backtest import ndx_single_replacement_path_requests_research as requests
from backtest import ndx_signed_cash_flow_return_accounting_research as account
from backtest import ndx_signed_cash_flow_account_inspection_research as ledger
from test_ndx_single_replacement_path_requests_research import fixture

def example():
 args=fixture()
 for case,row in zip(args['prepared']['document']['cases'],args['selection']['document']['rows']):
  source=case['identity']['original_input_row'];row['selected']['evaluation']['equity_after_usd']=str(Fraction(source['starting_cash_usd'])+Fraction(source['cash_event']['amount_usd'])+100-Fraction(3,25))
 args['selection']['content_sha256']=requests.digest(args['selection']['document'])
 return args,requests.prepare_single_replacement_path_requests(**args)

class Tests(unittest.TestCase):
 def test_pending_before_any_source_read(self):
  reference=dict(path='E:/synthetic/not-read.json',sha256='a'*64)
  with patch.object(m,'PUBLISHER_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('No source IO')):
   with self.assertRaises(ValueError):m.readback(registration_reference=reference,result_reference=reference,publication_reference=reference,execute=True)

 def test_complete_request_projection_and_independent_account(self):
  args,saved=example();before=deepcopy(args)
  expected=m.inspect_requests(saved_requests=saved,**args)
  self.assertEqual(len(expected['rows']),40)
  for index in (0,8,16,24,32):
   row=expected['rows'][index];req=row['accounting_request'];result=account.account_path(**req)
   self.assertEqual(ledger.inspect_saved_signed_account(**req,saved_result=result)['status'],'PASS')
   m.inspect_first_trade(row,result)
  self.assertEqual(args,before)
 def test_request_full_object_and_open_not_close_comparison(self):
  args,saved=example()
  for kind in ('count','source','flow','trade','drop'):
   bad=deepcopy(saved)
   if kind=='count':bad['status_counts']['NO_FEASIBLE']=False
   elif kind=='source':bad['rows'][0]['selection_reference']['json_pointer']='/selection/document/rows/1'
   elif kind=='flow':bad['rows'][0]['accounting_request']['sessions'][1]['cash_injection_usd']='1000'
   elif kind=='trade':bad['rows'][0]['accounting_request']['sessions'][1]['trade_shares']={'Z':1}
   else:bad['rows'].pop()
   with self.subTest(kind=kind),self.assertRaises(ValueError):m.inspect_requests(saved_requests=bad,**args)
  row=saved['rows'][0];result=account.account_path(**row['accounting_request']);result['rows'][0]['post_trade_open_equity_usd']=str(Fraction(result['rows'][0]['post_trade_open_equity_usd'])+1)
  with self.assertRaises(ValueError):m.inspect_first_trade(row,result)
 def test_absent_and_missing_quotes_no_synthetic_cash(self):
  args=fixture();selection=args['selection']['document'];row=selection['rows'][0]
  row.update(status='NO_FEASIBLE',selected=None,feasible_count=0,infeasible_count=row['integer_count'])
  selection.update(selected_case_count=39,no_feasible_case_count=1,feasible_count=39,infeasible_count=selection['integer_count']-39)
  args['selection']['content_sha256']=requests.digest(selection)
  del args['old_paired_rows'][1]['paths']['candidate']['accounting_inputs']['sessions'][0]['open_prices']['Z']
  saved=requests.prepare_single_replacement_path_requests(**args)
  expected=m.inspect_requests(saved_requests=saved,**args)
  self.assertIsNone(expected['rows'][0]['accounting_request']);self.assertIsNone(expected['rows'][1]['accounting_request'])

class PhysicalTests(unittest.TestCase):
 def test_full_physical_40_and_mixed38_without_producer_calls(self):
  from test_ndx_single_replacement_signed_paths_20261003 import physical
  from scripts import ndx_single_replacement_signed_paths_20261003 as publisher
  for blocked in (False,True):
   with self.subTest(blocked=blocked),tempfile.TemporaryDirectory()as t,physical(Path(t),blocked=blocked)as rr:
    refs=publisher.run(registration_reference=rr,execute=True);private=publisher.private
    def only_stream(role,raw):
     if role!='stream':raise AssertionError('No production numerical compilation')
     return private(role,raw)
    with patch.object(m,'PUBLISHER_SHA',publisher.LOADED),patch.object(m,'OUTPUT',Path(t)/'reader'),patch.object(publisher,'private',only_stream),patch.object(publisher,'run',side_effect=AssertionError('No producer')):
     reportref=m.readback(registration_reference=rr,result_reference=refs['result'],publication_reference=refs['publication'],execute=True)
     report=json.loads(Path(reportref['path']).read_bytes());self.assertEqual(report['scenario_count'],40);self.assertEqual(report['account_checked_count'],38 if blocked else 40)
     self.assertFalse(report['account_called']);self.assertFalse(report['request_producer_called'])
     with self.assertRaises(ValueError):m.readback(registration_reference=rr,result_reference=refs['result'],publication_reference=refs['publication'],execute=True)
 def test_resigned_bad_cash_retains_failed_readback_no_retry(self):
  from test_ndx_single_replacement_signed_paths_20261003 import physical
  from scripts import ndx_single_replacement_signed_paths_20261003 as publisher
  with tempfile.TemporaryDirectory()as t,physical(Path(t))as rr:
   refs=publisher.run(registration_reference=rr,execute=True)
   def overwrite(r,value):
    path=Path(r['path']);path.write_bytes(publisher.enc(value));return publisher.ref(path,publisher.filehash(path))
   result=json.loads(Path(refs['result']['path']).read_bytes());entry=result['rows'][0]
   raw=json.loads(Path(entry['raw_reference']['path']).read_bytes());raw['result']['rows'][0]['cash_after_usd']=str(Fraction(raw['result']['rows'][0]['cash_after_usd'])+1)
   entry['raw_reference']=overwrite(entry['raw_reference'],raw)
   post=json.loads(Path(entry['postcheck_reference']['path']).read_bytes());post['raw_reference']=entry['raw_reference'];entry['postcheck_reference']=overwrite(entry['postcheck_reference'],post)
   refs['result']=overwrite(refs['result'],result);pub=json.loads(Path(refs['publication']['path']).read_bytes());pub['result_reference']=refs['result'];refs['publication']=overwrite(refs['publication'],pub)
   with patch.object(m,'PUBLISHER_SHA',publisher.LOADED),patch.object(m,'OUTPUT',Path(t)/'reader'):
    with self.assertRaises(ValueError):m.readback(registration_reference=rr,result_reference=refs['result'],publication_reference=refs['publication'],execute=True)
    failure=json.loads((m.OUTPUT/'failure.json').read_bytes());self.assertEqual(failure['completed_case_count'],0)
    self.assertFalse((m.OUTPUT/'independent_readback.json').exists())
    with self.assertRaises(ValueError):m.readback(registration_reference=rr,result_reference=refs['result'],publication_reference=refs['publication'],execute=True)
 def test_output_and_source_failure_after_numeric_pass_is_not_success(self):
  from test_ndx_single_replacement_signed_paths_20261003 import physical
  from scripts import ndx_single_replacement_signed_paths_20261003 as publisher
  for kind in ('own','source'):
   with self.subTest(kind=kind),tempfile.TemporaryDirectory()as t,physical(Path(t))as rr:
    refs=publisher.run(registration_reference=rr,execute=True);save=m.save
    def change(name,value):
     r=save(name,value)
     if name=='independent_readback.json':
      if kind=='own':(m.OUTPUT/'started.json').write_bytes(b'drift')
      else:(Path(t)/'original_journal/failure.json').write_bytes(b'{}')
     return r
    with patch.object(m,'PUBLISHER_SHA',publisher.LOADED),patch.object(m,'OUTPUT',Path(t)/'reader'),patch.object(m,'save',change):
     with self.assertRaises(ValueError):m.readback(registration_reference=rr,result_reference=refs['result'],publication_reference=refs['publication'],execute=True)
     failure=json.loads((m.OUTPUT/'failure.json').read_bytes());self.assertEqual(failure['completed_case_count'],40)
     with self.assertRaises(ValueError):m.readback(registration_reference=rr,result_reference=refs['result'],publication_reference=refs['publication'],execute=True)

if __name__=='__main__':unittest.main()
