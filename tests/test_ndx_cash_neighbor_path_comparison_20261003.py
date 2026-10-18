import unittest,json,tempfile
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from types import SimpleNamespace
from scripts import ndx_cash_neighbor_path_comparison_20261003 as w
from test_ndx_cash_neighbor_path_comparison_research import fixture,m


def adapter_fixture():
 cases=fixture()['cases'];refs={k:dict(path=k+'.json',sha256='a'*64)for k in ('paired','incumbent','reference','sameflow','selected_audit')}
 refs.update({k:dict(path=k+'.md',sha256='a'*64)for k in ('reference_audit','sameflow_audit','incumbent_audit')})
 inc=dict(paths=[],scenario_mappings=[]);triples=[]
 # Deliberately reverse mapping order: source mappings are not lane-first.
 for c in reversed(cases):inc['scenario_mappings'].append(deepcopy(c['incumbent']['mapping']))
 for c in cases[:10]:inc['paths'].append(dict(path_id=c['incumbent']['mapping']['path_id'],account=deepcopy(c['incumbent']['account'])))
 for i,c in enumerate(cases):
  pi=next(j for j,p in enumerate(inc['paths'])if p['path_id']==c['incumbent']['mapping']['path_id']);mi=39-i
  old=dict(scenario_id=c['scenario_id'],input_row=c['input_row'],input_reference=c['input_reference'],paths={k:dict(account=deepcopy(c[v]['account']),accounting_inputs=deepcopy(c[v]['accounting_inputs']))for k,v in [('candidate','candidate'),('same_flow_zero_trade_control','zero_trade_control')]})
  same=dict(scenario_id=c['scenario_id'],input_row=c['input_row'],original_input_reference=c['input_reference'],calendar=c['calendar'],candidate_paired_row_reference=w.pointer(refs['paired'],f'/rows/{i}'),incumbent_mapping_reference=w.pointer(refs['incumbent'],f'/scenario_mappings/{mi}'),incumbent_path_reference=w.pointer(refs['incumbent'],f'/paths/{pi}'),incumbent_mapping_preserved=inc['scenario_mappings'][mi],observations=dict(same_flow_incumbent=[dict(reference=w.pointer(refs['incumbent'],f'/paths/{pi}/account/daily/{j}'),source_row=r)for j,r in enumerate(inc['paths'][pi]['account']['daily'])]),metrics=dict(same_flow_incumbent=c['saved_reference_metrics']['same_flow_incumbent']['metrics']))
  nav=dict(scenario_id=c['scenario_id'],input_row=c['input_row'],paired_row_reference=w.pointer(refs['paired'],f'/rows/{i}'),comparison=dict(calendar=c['calendar'],roles={k:c['saved_reference_metrics'][k]['metrics']for k in ('same_flow_zero_trade_control','fund_012922_cny_nav_reference')}),observations=dict(same_flow_zero_trade_control=[dict(reference=w.pointer(refs['paired'],f'/rows/{i}/paths/same_flow_zero_trade_control/account/rows/{j}'),source_row=r)for j,r in enumerate(old['paths']['same_flow_zero_trade_control']['account']['rows'])],fund_nav=[dict(encoding='SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE',value_field='nav',reference=r['reference'],source_row=dict(session=r['session'],nav_date=r['nav_date'],nav=1.0))for r in c['nav_rows']]))
  candidate=deepcopy(c['candidate']);candidate['selection_reference']=c['selection_reference'];triples.append((old,same,nav,candidate))
 return refs,inc,triples


class Tests(unittest.TestCase):
 def test_real_role_shape_id_join_and_full_forty(self):
  refs,inc,triples=adapter_fixture();cases=[]
  for i,(old,same,nav,c)in enumerate(triples):
   before=deepcopy(c);cases.append(w.build_case(old,same,nav,inc,refs,i,c));self.assertEqual(c,before)
  out=m.compare_selected_cash_paths(cases=cases,expected_scenario_ids=[c['scenario_id']for c in cases]);self.assertEqual(len(out['rows']),40)
  self.assertEqual(cases[0]['incumbent']['mapping_reference']['json_pointer'],'/scenario_mappings/39');self.assertEqual(cases[0]['saved_reference_metrics']['same_flow_incumbent']['reference']['json_pointer'],'/rows/0/metrics/same_flow_incumbent')
 def test_wrong_role_pointer_and_mapping_rejected(self):
  for mode in ('pointer','mapping','navencoding'):
   refs,inc,triples=adapter_fixture();old,same,nav,c=triples[0]
   if mode=='pointer':same['incumbent_path_reference']['json_pointer']='/paths/9'
   elif mode=='mapping':inc['scenario_mappings'].append(deepcopy(inc['scenario_mappings'][-1]))
   else:nav['observations']['fund_nav'][0]['encoding']='CERTIFIED_USD'
   with self.assertRaises(ValueError):w.build_case(old,same,nav,inc,refs,0,c)
 def test_audited_request_required_before_read(self):
  refs,inc,triples=adapter_fixture();old=triples[0][0];rr=dict(path='request.json',sha256='a'*64);entry=dict(scenario_index=0,scenario_id=old['scenario_id'],outcome='REUSE_EXISTING_PAIRED_PATH',request_reference=rr);audit=deepcopy(entry)
  with patch.object(w,'read',side_effect=AssertionError('must not read')):
   with self.assertRaisesRegex(ValueError,'independently audited'):w.selected_candidate(entry,audit,refs,0,old,{}, {})
 def test_pending_before_io_resource_exact_and_no_boolean_size(self):
  with patch.object(w,'BOUND',{'pending':('x',None)}),patch.object(w.Path,'read_bytes',side_effect=AssertionError('No IO')):
   with self.assertRaises(ValueError):w.load()
  with patch.object(w.shutil,'disk_usage',return_value=SimpleNamespace(free=5*1024**3+9)):
   w.resource_check('.',9)
   for value in (10,True):
    with self.assertRaises(ValueError):w.resource_check('.',value)

 def test_stream_publication_source_union_and_failure_marker(self):
  refs,inc,triples=adapter_fixture()
  for fail in (False,True):
   with tempfile.TemporaryDirectory()as td:
    root=Path(td);out=root/'new';r=deepcopy(refs);r['metrics']=dict(path='metrics.py',sha256='a'*64)
    for role in w.STREAMED:
     p=root/(role+'.json');p.write_bytes(role.encode());r[role]=dict(path=str(p),sha256=w.sha(p.read_bytes()))
    # Rebuild role pointers using the new temporary file references.
    for i,(old,same,nav,c)in enumerate(triples):
     same['candidate_paired_row_reference']=w.pointer(r['paired'],f'/rows/{i}');nav['paired_row_reference']=w.pointer(r['paired'],f'/rows/{i}')
     for j,ob in enumerate(nav['observations']['same_flow_zero_trade_control']):ob['reference']=w.pointer(r['paired'],f'/rows/{i}/paths/same_flow_zero_trade_control/account/rows/{j}')
    role_rows={'paired':[t[0]for t in triples],'sameflow':[t[1]for t in triples],'reference':[t[2]for t in triples]}
    class Stream:
     def __init__(self,f):self.role=Path(f.name).stem;self.it=iter(enumerate(role_rows[self.role]));self.summary=dict(row_count=40,complete_document_consumed=True,sha256=r[self.role]['sha256'],metadata=dict(source_hashes={}))
     def __iter__(self):return self
     def __next__(self):
      i,v=next(self.it);return dict(row_index=i,value=v)
    docs=dict(incumbent=inc,selected_result=dict(completed_rows=[dict(scenario_id=t[0]['scenario_id'])for t in triples]),selected_audit=dict(cases=[{}]*40,consumed_case_sources={}))
    docs.update({k+'_publication':dict(source_hashes={})for k in w.STREAMED})
    def candidate(entry,audit,refs,index,old,sources,closure):
     if fail:raise ValueError('synthetic case failure')
     return deepcopy(triples[index][3])
    with patch.object(w,'OUTPUT',out),patch.object(w,'load',return_value=(docs,r,{},m,SimpleNamespace(JsonRowsStream=Stream))),patch.object(w,'guard'),patch.object(w,'resource_check'),patch.object(w,'selected_candidate',side_effect=candidate):
     if fail:
      with self.assertRaisesRegex(ValueError,'synthetic'):w.run(execute=True)
      self.assertTrue((out/'failure.json').exists());self.assertFalse((out/'publication.json').exists())
     else:
      rr=w.run(execute=True);doc=json.loads(Path(rr['path']).read_bytes());self.assertEqual(len(doc['cases']),40)
      for role in w.STREAMED:self.assertEqual(doc['source_hashes'][r[role]['path']],r[role]['sha256'])
     with self.assertRaisesRegex(ValueError,'Create-only'):w.run(execute=True)

if __name__=='__main__':unittest.main()
