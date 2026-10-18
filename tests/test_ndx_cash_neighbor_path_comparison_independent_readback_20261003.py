import copy,importlib.util,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from scripts import ndx_cash_neighbor_path_comparison_independent_readback_20261003 as m
from scripts import ndx_cash_neighbor_path_comparison_20261003 as producer
spec=importlib.util.spec_from_file_location('case_source_fixture',ROOT/'tests/test_ndx_cash_neighbor_path_comparison_20261003.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def fixture():
 refs,inc,triples=f.adapter_fixture();old,same,nav,c=triples[0];case=producer.build_case(old,same,nav,inc,refs,0,c)
 return case,old,same,nav,inc,refs

class Tests(unittest.TestCase):
 def test_original_roles_and_reverse_mapping_complete_case_evidence(self):
  values=fixture();before=copy.deepcopy(values);m.check_case_evidence(*values,0);self.assertEqual(values,before)
  for mode in ('role','inc','nav','source'):
   case,old,same,nav,inc,refs=copy.deepcopy(values)
   if mode=='role':case['saved_reference_metrics']['same_flow_incumbent']['reference']['json_pointer']='/rows/0/candidate'
   elif mode=='inc':case['incumbent']['mapping_reference']['json_pointer']='/scenario_mappings/0'
   elif mode=='nav':case['nav_rows'][0]['value']='2'
   else:case['saved_original_reference_metadata']['nav_limits']['paired_row_reference']['sha256']='b'*64
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.check_case_evidence(case,old,same,nav,inc,refs,0)
 def test_machine_bytes_types_boundaries_and_no_reencoding(self):
  row=dict(scenario_index=0,scenario_id='s0',candidate_status='AVAILABLE_NEW');raw=m.enc(row)+b'\n';descriptor=dict(scenario_index=0,scenario_id='s0',candidate_status='AVAILABLE_NEW',byte_start=0,byte_stop=len(raw),row_sha256=m.sha(raw))
  self.assertEqual(m.inspect_line(raw,descriptor,0,0),row)
  for key,value in [('scenario_index',False),('byte_start',False),('byte_stop',len(raw)+1),('row_sha256','a'*64)]:
   d=dict(descriptor);d[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):m.inspect_line(raw,d,0,0)
  for b in (raw[:-1],b'{"scenario_index":0,"scenario_index":0}\n'):
   d=dict(descriptor,byte_stop=len(b),row_sha256=m.sha(b))
   with self.assertRaises(ValueError):m.inspect_line(b,d,0,0)
 def test_reuse_requires_audited_request_and_actual_old_path_identity(self):
  case,old,same,nav,inc,refs=fixture();rr=m.ref('request.json','a'*64);path=m.ptr(refs['paired'],'/rows/0/paths/candidate');control=m.ptr(refs['paired'],'/rows/0/paths/same_flow_zero_trade_control')
  req=dict(old_paired_evidence=old,scenario_id=old['scenario_id'],status='REUSE_EXISTING_PAIRED_PATH',input_references=dict(selection_reference=case['selection_reference']),control_path_reference=control,reused_candidate_path_reference=path,accounting_request=None)
  entry=dict(scenario_index=0,scenario_id=old['scenario_id'],outcome='REUSE_EXISTING_PAIRED_PATH',request_reference=rr,status=req['status'],control_reference=control,candidate_reference=path)
  audit=dict(entry,detail=None);case['candidate']=dict(status='AVAILABLE_REUSED',reason=None,account=old['paths']['candidate']['account'],account_reference=m.ptr(refs['paired'],'/rows/0/paths/candidate/account'),accounting_inputs=old['paths']['candidate']['accounting_inputs'],inputs_reference=m.ptr(refs['paired'],'/rows/0/paths/candidate/accounting_inputs'),evidence_reference=m.ptr(refs['selected_audit'],'/cases/0'))
  doc=dict(request=req,**dict.fromkeys(m.PARENT_FALSE,False));sources={rr['path']:rr['sha256']}
  with patch.object(m,'read',return_value=doc):m.check_candidate(case,old,entry,audit,refs,0,sources,{})
  with patch.object(m,'read',side_effect=AssertionError('No unauthenticated read')):
   with self.assertRaises(ValueError):m.check_candidate(case,old,entry,audit,refs,0,{}, {})
  case['candidate']['account_reference']['json_pointer']='/rows/1/paths/candidate/account'
  with patch.object(m,'read',return_value=doc),self.assertRaises(ValueError):m.check_candidate(case,old,entry,audit,refs,0,sources,{})
 def test_future_pins_before_io_and_failed_namespace_source_guard(self):
  with patch.object(Path,'read_bytes',side_effect=AssertionError('No future IO')),patch.object(Path,'exists',side_effect=AssertionError('No future IO')):
   with self.assertRaisesRegex(ValueError,'Pending'):m.readback(execute=True)
  with tempfile.TemporaryDirectory()as td:
   p=Path(td)/'source';p.write_bytes(b'{}');s={str(p):m.sha(b'{}')};m.guard(s);(p.parent/'failure.json').write_bytes(b'{}')
   with self.assertRaises(ValueError):m.guard(s)
if __name__=='__main__':unittest.main()
