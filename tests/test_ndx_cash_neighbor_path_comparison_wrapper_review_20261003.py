import copy,importlib.util,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from scripts import ndx_cash_neighbor_path_comparison_20261003 as m
spec=importlib.util.spec_from_file_location('adapter_fixtures',ROOT/'tests/test_ndx_cash_neighbor_path_comparison_20261003.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

class Tests(unittest.TestCase):
 def test_reference_metrics_roles_and_real_mapping_pointers(self):
  refs,inc,triples=f.adapter_fixture();old,same,nav,c=triples[0]
  same['metrics']['same_flow_incumbent']['annualized_return_diagnostic_decimal']='0.7654'
  nav['comparison']['roles']['fund_012922_cny_nav_reference']['annualized_return_diagnostic_decimal']='0.1234'
  before=copy.deepcopy((old,same,nav,c));case=m.build_case(old,same,nav,inc,refs,0,c)
  self.assertEqual((old,same,nav,c),before);saved=case['saved_reference_metrics']
  self.assertEqual(saved['same_flow_incumbent']['metrics'],same['metrics']['same_flow_incumbent'])
  self.assertEqual(saved['fund_012922_cny_nav_reference']['metrics'],nav['comparison']['roles']['fund_012922_cny_nav_reference'])
  self.assertEqual(saved['same_flow_incumbent']['reference'],m.pointer(refs['sameflow'],'/rows/0/metrics/same_flow_incumbent'))
  self.assertEqual(case['incumbent']['mapping_reference']['json_pointer'],'/scenario_mappings/39')
  self.assertEqual(saved['fund_012922_cny_nav_reference']['evidence_reference'],m.markdown(refs['reference_audit']))
  self.assertEqual(case['nav_rows'][0]['value'],'1.0')
 def test_whole_old_observations_and_pointer_swap(self):
  for mode in ('zero_source','inc_short','nav_source','input'):
   refs,inc,triples=f.adapter_fixture();old,same,nav,c=triples[0]
   if mode=='zero_source':nav['observations']['same_flow_zero_trade_control'][0]['reference']['json_pointer']='/rows/1/account'
   elif mode=='inc_short':same['observations']['same_flow_incumbent'].pop()
   elif mode=='nav_source':nav['paired_row_reference']['sha256']='b'*64
   else:same['original_input_reference']=dict(same['original_input_reference'],json_pointer='/wrong')
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.build_case(old,same,nav,inc,refs,0,c)
 def test_new_raw_and_post_are_both_bound_by_external_arithmetic_audit(self):
  refs,inc,triples=f.adapter_fixture();old=triples[0][0];sid=old['scenario_id']
  rr=m.ref('request.json','a'*64);rawref=m.ref('raw.json','b'*64);postref=m.ref('post.json','c'*64);control=m.pointer(refs['paired'],'/rows/0/paths/same_flow_zero_trade_control')
  request=dict(old_paired_evidence=old,scenario_id=sid,status='NEW_PATH_REQUIRED',control_path_reference=control,input_references=dict(selection_reference=m.pointer(m.ref('selection.json','d'*64),'/selection')),accounting_request=triples[0][3]['accounting_inputs'])
  entry=dict(scenario_index=0,scenario_id=sid,status='NEW_PATH_REQUIRED',outcome='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK',request_reference=rr,raw_reference=rawref,postcheck_reference=postref,control_reference=control)
  audit=dict(scenario_index=0,scenario_id=sid,outcome=entry['outcome'],request_reference=rr,raw_reference=rawref,control_reference=control,detail=dict(independent_saved_quote_arithmetic_verified=True))
  docs={'request.json':dict(request=request),'raw.json':dict(request_reference=rr,error=None,account=triples[0][3]['account']),'post.json':dict(raw_reference=rawref,validation_error=None,outcome=entry['outcome'])}
  for doc in docs.values():doc.update(dict.fromkeys(m.PARENT_FALSE,False))
  sources={r['path']:r['sha256']for r in (rr,rawref,postref)}
  for missing in ('raw.json','post.json'):
   bound=dict(sources);del bound[missing];seen=[]
   def read(ref,local):seen.append(ref['path']);return copy.deepcopy(docs[ref['path']])
   with patch.object(m,'read',side_effect=read),self.assertRaisesRegex(ValueError,'independently audited'):m.selected_candidate(entry,audit,refs,0,old,{},bound)
   self.assertEqual(seen,['request.json'])
  docs['post.json']['raw_reference']=m.ref('other-raw.json','e'*64)
  with patch.object(m,'read',side_effect=lambda ref,_:copy.deepcopy(docs[ref['path']])),self.assertRaises(ValueError):m.selected_candidate(entry,audit,refs,0,old,{},sources)
 def test_pending_never_compiles_or_reads_actual(self):
  with patch.object(Path,'read_bytes',side_effect=AssertionError('No actual reads')),patch.object(m,'private_module',side_effect=AssertionError('No compile')):
   with self.assertRaisesRegex(ValueError,'Pending'):m.load()
 def test_parent_authority_exact_type_and_new_failure_namespace(self):
  import tempfile
  valid=dict.fromkeys(m.PARENT_FALSE,False);m.parent_flags(valid)
  for value in (True,0,None):
   bad=dict(valid,point_in_time_verified=value)
   with self.assertRaises(ValueError):m.parent_flags(bad)
  with tempfile.TemporaryDirectory()as td:
   folder=Path(td);source=folder/'parent.json';source.write_bytes(b'{}');sources={str(source):m.sha(b'{}')};m.guard(sources)
   (folder/'failure.json').write_bytes(b'{}')
   with self.assertRaises(ValueError):m.guard(sources)
if __name__=='__main__':unittest.main()
