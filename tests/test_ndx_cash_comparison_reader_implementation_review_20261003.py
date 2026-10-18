"""Independent metadata/JSONL attacks, no actual files or production reconstruction."""
import ast,copy,io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_cash_neighbor_path_comparison_independent_readback_20261003 as r
from test_ndx_cash_neighbor_path_comparison_20261003 import adapter_fixture
from test_ndx_cash_neighbor_path_comparison_research import fixture

def source_fixture(index=0):
 refs,inc,triples=adapter_fixture();old,same,nav,_=triples[index];case=copy.deepcopy(fixture()['cases'][index]);pi=next(i for i,p in enumerate(inc['paths'])if p['path_id']==case['incumbent']['mapping']['path_id']);mi=39-index
 case['calendar_reference']=r.ptr(refs['sameflow'],f'/rows/{index}/calendar')
 case['incumbent'].update(account_reference=r.ptr(refs['incumbent'],f'/paths/{pi}/account'),mapping_reference=r.ptr(refs['incumbent'],f'/scenario_mappings/{mi}'),evidence_reference=r.md(refs['incumbent_audit']))
 case['zero_trade_control'].update(account_reference=r.ptr(refs['paired'],f'/rows/{index}/paths/same_flow_zero_trade_control/account'),inputs_reference=r.ptr(refs['paired'],f'/rows/{index}/paths/same_flow_zero_trade_control/accounting_inputs'),evidence_reference=r.md(refs['reference_audit']))
 case['nav_rows']=[dict(session=x['source_row']['session'],nav_date=x['source_row']['nav_date'],value=str(x['source_row']['nav']),reference=x['reference'],encoding=x['encoding'],source_row=x['source_row'])for x in nav['observations']['fund_nav']];case['nav_evidence_reference']=r.md(refs['reference_audit'])
 for role in r.ROLES:
  parent='sameflow'if role=='same_flow_incumbent'else'reference';pointer=f'/rows/{index}/metrics/{role}'if parent=='sameflow'else f'/rows/{index}/comparison/roles/{role}'
  case['saved_reference_metrics'][role].update(reference=r.ptr(refs[parent],pointer),evidence_reference=r.md(refs[parent+'_audit']))
 case['saved_original_reference_metadata']=dict(sameflow_limits={k:v for k,v in same.items()if k not in ('metrics','observations')},nav_limits={k:v for k,v in nav.items()if k not in ('comparison','observations')})
 return case,old,same,nav,inc,refs

class Tests(unittest.TestCase):
 def test_forty_line_byte_chain_no_omission_reordering_or_tail_alias(self):
  raws=[];descriptors=[];offset=0
  for i in range(40):
   row=dict(scenario_index=i,scenario_id=f'id{i}',candidate_status='AVAILABLE_REUSED');raw=r.enc(row)+b'\n';raws.append(raw);descriptors.append(dict(row,byte_start=offset,byte_stop=offset+len(raw),row_sha256=r.sha(raw)));offset+=len(raw)
  for mode in ('valid','swap','missing','extra','offset','type'):
   raw=list(raws);ds=copy.deepcopy(descriptors)
   if mode=='swap':raw[1],raw[2]=raw[2],raw[1]
   elif mode=='missing':raw.pop(3)
   elif mode=='extra':raw.append(raws[-1])
   elif mode=='offset':ds[-1]['byte_start']-=1
   elif mode=='type':ds[0]['byte_start']=False
   def verify():
    f=io.BytesIO(b''.join(raw));start=0
    for i,d in enumerate(ds):b=f.readline();r.inspect_line(b,d,i,start);start+=len(b)
    r.require(f.read(1)==b'','EOF must be exact')
   if mode=='valid':verify()
   else:
    with self.subTest(mode=mode),self.assertRaises(ValueError):verify()
 def test_actual_role_sources_not_index_join_or_cloned_same_metric(self):
  original=source_fixture();r.check_case_evidence(*original,0)
  for mode in ('duplicate_map','metricrole','audit','scenario','observation'):
   case,old,same,nav,inc,refs=copy.deepcopy(original)
   if mode=='duplicate_map':inc['scenario_mappings'].append(copy.deepcopy(inc['scenario_mappings'][-1]))
   elif mode=='metricrole':case['saved_reference_metrics']['same_flow_incumbent']['reference']['json_pointer']='/rows/0/metrics/candidate'
   elif mode=='audit':case['saved_reference_metrics']['fund_012922_cny_nav_reference']['evidence_reference']=r.md(refs['sameflow_audit'])
   elif mode=='scenario':case['incumbent']['mapping']['scenario_id']='foreign'
   else:same['observations']['same_flow_incumbent'][0]['reference']['json_pointer']='/paths/1/account/daily/0'
   with self.subTest(mode=mode),self.assertRaises(ValueError):r.check_case_evidence(case,old,same,nav,inc,refs,0)
 def test_candidate_actual_audit_and_zero_boolean_gate(self):
  case,old,same,nav,inc,refs=source_fixture();rr=r.ref('request','a'*64);rawref=r.ref('raw','b'*64);postref=r.ref('post','c'*64);control=r.ptr(refs['paired'],'/rows/0/paths/same_flow_zero_trade_control')
  entry=dict(scenario_index=0,scenario_id=old['scenario_id'],status='NEW_PATH_REQUIRED',outcome='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK',request_reference=rr,raw_reference=rawref,postcheck_reference=postref,control_reference=control)
  audit=dict(entry,detail=dict(independent_saved_quote_arithmetic_verified=True));req=dict(old_paired_evidence=old,scenario_id=old['scenario_id'],status=entry['status'],input_references=dict(selection_reference=case['selection_reference']),control_path_reference=control,accounting_request=case['candidate']['accounting_inputs'])
  docs={'request':dict(request=req,**dict.fromkeys(r.PARENT_FALSE,False)),'raw':dict(account=case['candidate']['account'],request_reference=rr,error=None,**dict.fromkeys(r.PARENT_FALSE,False)),'post':dict(raw_reference=rawref,validation_error=None,outcome=entry['outcome'],**dict.fromkeys(r.PARENT_FALSE,False))}
  case['candidate'].update(evidence_reference=r.ptr(refs['selected_audit'],'/cases/0'),account_reference=r.ptr(rawref,'/account'),inputs_reference=r.ptr(rr,'/request/accounting_request'))
  for mode in ('valid','missingpost','wronghash','bool','error'):
   authenticated={v['path']:v['sha256']for v in (rr,rawref,postref)};d=copy.deepcopy(docs)
   if mode=='missingpost':authenticated.pop('post')
   elif mode=='wronghash':authenticated['raw']='d'*64
   elif mode=='bool':d['raw']['point_in_time_verified']=0
   elif mode=='error':d['raw']['error']='saved technical failure'
   with patch.object(r,'read',side_effect=lambda ref,s:d[ref['path']]):
    if mode=='valid':r.check_candidate(case,old,entry,audit,refs,0,authenticated,{})
    else:
     with self.subTest(mode=mode),self.assertRaises(ValueError):r.check_candidate(case,old,entry,audit,refs,0,authenticated,{})
 def test_source_drift_new_failure_and_no_production_reconstruction(self):
  with tempfile.TemporaryDirectory()as td:
   p=Path(td)/'source.json';p.write_bytes(b'{}');sources={str(p):r.sha(b'{}')};r.guard(sources);p.write_bytes(b'{ }')
   with self.assertRaises(ValueError):r.guard(sources)
   p.write_bytes(b'{}');(p.parent/'failure.json').write_bytes(b'{}')
   with self.assertRaises(ValueError):r.guard(sources)
  tree=ast.parse(Path(r.__file__).read_text(encoding='utf-8-sig'))
  names={getattr(n.func,'attr',getattr(n.func,'id',''))for n in ast.walk(tree)if isinstance(n,ast.Call)}
  self.assertFalse(names&{'build_case','compare_case','compare_selected_cash_paths','account_path'})
  with patch.object(r,'BOUND',{'index':('pending',None)}),patch.object(Path,'read_bytes',side_effect=AssertionError('future IO')):
   with self.assertRaises(ValueError):r.readback(execute=True)

if __name__=='__main__':unittest.main()
