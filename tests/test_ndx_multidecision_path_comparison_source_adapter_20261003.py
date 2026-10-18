from pathlib import Path
from copy import deepcopy
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_path_comparison_source_adapter_20261003 as a
from test_ndx_multidecision_path_comparison_research import fixture
from scripts.ndx_multidecision_nav_reference_metrics_20261003 import FLAGS as NAVFLAGS

def physical(root):
 x=fixture();refs={};docs={}
 def put(path,value,raw=False):
  path.parent.mkdir(parents=True,exist_ok=True);b=value if raw else a.enc(value);path.write_bytes(b);return a.ref(path,a.sha(b))
 def role(name,path,value,raw=False):refs[name]=put(path,value,raw);docs[name]=value;return refs[name]
 pflags=dict.fromkeys(('source_bytes_authenticated','account_simulation_performed','fit_performed','selection_performed','execution_authorized','promotion_allowed','point_in_time_verified','formal_benchmark_passed','automatic_retry_allowed','weights_normalized','cross_lane_execution_reused'),False)
 for name in ('candidate','control'):
  reader=role(name+'_inputs_reader',root/(name+'_input_reader.py'),b'# source only',True);body=deepcopy(x[name+'_prepared']);base='MULTIDECISION_STATEFUL_ACCOUNT' if name=='candidate' else 'MULTIDECISION_ORIGINAL_EIGHT'
  if name=='control':
   body['candidate_evidence_references']={k:refs['candidate_'+alias] for k,alias in dict(inputs='inputs',publication='inputs_publication',readback='inputs_audit',reader='inputs_reader').items()}
   for i,lane in enumerate(body['rows']):
    for j,t in enumerate(lane['tracks']):t['candidate_input_reference']=a.pointer(refs['candidate_inputs'],f'/inputs/rows/{i}/tracks/{j}')
  body['content_sha256']=a.sha(a.enc({k:v for k,v in body.items() if k!='content_sha256'}));st=put(root/name/'inputs/started.json',{})
  ir=role(name+'_inputs',root/name/'inputs/inputs.json',dict(schema=base+'_INPUTS_DOCUMENT_V1',inputs=body,source_hashes={},**pflags))
  pr=role(name+'_inputs_publication',root/name/'inputs/publication.json',dict(schema=base+'_INPUTS_PUBLICATION_V1',status='PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS' if name=='candidate' else 'PUBLISHED_CONTROL_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS',inputs_reference=ir,started_reference=st,source_hashes={},**pflags))
  put(root/name/'inputaudit/started.json',{});role(name+'_inputs_audit',root/name/'inputaudit/independent_readback.json',dict(schema=base+'_INPUTS_INDEPENDENT_READBACK_V1',status='PASS',scope='SAVED_FULL48_TO_16_STATEFUL_INPUT_PROJECTION_NOT_ACCOUNT_EXECUTION' if name=='candidate' else 'SAVED_NOMINAL_ORIGINAL_EIGHT_16_CONTROL_INPUT_PROJECTIONS_NOT_ACCOUNTS',inputs_reference=ir,publication_reference=pr,reader_sha256=reader['sha256'],source_hashes={r['path']:r['sha256'] for r in (ir,pr,st,reader)},**dict.fromkeys(('producer_called','fit_called','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed','account_engine_called','control_engine_called','candidate_engine_called'),False)))
  er=role(name+'_reader',root/(name+'_ledger_reader.py'),b'# independent arithmetic source',True)
  irs={k:refs[name+'_'+alias] for k,alias in dict(inputs='inputs',publication='inputs_publication',readback='inputs_audit',reader='inputs_reader').items()};sources={r['path']:r['sha256'] for r in irs.values()};prefix='MULTIDECISION_ACCOUNT' if name=='candidate' else 'MULTIDECISION_INCUMBENT_ACCOUNT';rows=[];audits=[];home=root/name/'execution';gs=put(home/'started.json',dict(source_hashes=sources))
  for i,slot in enumerate(x[name+'_slots']):
   tr=body['rows'][i//2]['tracks'][i%2];coord=slot['coordinate'];folder=home/'tracks'/f'{i:02d}'
   sr=put(folder/'started.json',dict(schema=prefix+'_TRACK_STARTED_V1',prepared_track=tr,input_pointer=f'/inputs/rows/{i//2}/tracks/{i%2}',coordinate=coord,input_references=irs,source_hashes=sources,**dict.fromkeys(a.EXEC_FLAGS,False)))
   rawref=None
   if slot['result'] is not None:rawref=put(folder/'raw_result.json',dict(schema=prefix+'_RAW_RETURN_V1',returned=True,call_invoked=True,returned_call_count=1,original_return_is_json=True,error=None,result=slot['result'],started_reference=sr,input_references=irs,source_hashes=sources,**dict.fromkeys(a.EXEC_FLAGS,False)))
   row=dict(track_index=i,fx_mode=coord[0],lane=coord[1],track=coord[2],outcome=slot['outcome'],call_invoked=rawref is not None,returned_call_count=int(rawref is not None),started_reference=sr,raw_reference=rawref,postcheck_reference=None,blocking_reasons=deepcopy(tr['blocking_reasons']))
   post=put(folder/'postcheck.json',dict(schema=prefix+'_TRACK_POSTCHECK_V1',**deepcopy(row),input_references=irs,source_hashes=sources,**dict.fromkeys(a.EXEC_FLAGS,False)));row['postcheck_reference']=post;rows.append(row);audits.append(dict(track_index=i,coordinate=coord,outcome=row['outcome'],saved_references={k:row[k] for k in ('started_reference','postcheck_reference','raw_reference')},inspection=slot['audit_evidence']['inspection'] if slot['audit_evidence'] else None))
  result=dict(schema=prefix+'_EXECUTION_RESULT_V1',status='ALL16_INPUT_SLOTS_PROCESSED_PENDING_INDEPENDENT_READBACK',failure=None,rows=rows,account_call_count=sum(r['call_invoked'] for r in rows),returned_call_count=sum(r['returned_call_count'] for r in rows),counts={v:sum(r['outcome']==v for r in rows) for v in sorted({r['outcome'] for r in rows})},track_count=16,lane_count=8,outer_coordinate_count=48,input_references=irs,source_hashes=sources,**dict.fromkeys(a.EXEC_FLAGS,False))
  if name=='control':result['candidate_mapping_preserved']=[dict(fx_mode=r['fx_mode'],lane=r['lane'],coordinate_indexes=r['coordinate_indexes'],tracks=[{k:deepcopy(t[k]) for k in ('track','candidate_status_preserved','candidate_blocking_reasons_preserved','candidate_input_reference')} for t in r['tracks']]) for r in body['rows']]
  rr=role(name+'_execution',home/'result.json',result);pr=role(name+'_execution_publication',home/'publication.json',dict(schema=prefix+'_EXECUTION_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_ACCOUNT_RETURNS_PENDING_INDEPENDENT_READBACK',result_reference=rr,started_reference=gs,input_references=irs,source_hashes=sources,**dict.fromkeys(a.EXEC_FLAGS,False)))
  put(root/name/'audit/started.json',{});role(name+'_audit',root/name/'audit/independent_readback.json',dict(schema=prefix+'_EXECUTION_INDEPENDENT_READBACK_V1',status='PASS',scope='SAVED16_ACCOUNT_LEDGER_CONSERVATION_AND_TWR_NOT_REPAIR_OPTIMALITY' if name=='candidate' else 'SAVED16_ORIGINAL_EIGHT_LEDGER_CONSERVATION_AND_TWR_WITH_LITERAL_WEIGHTS_RISK_OBSERVATION',result_reference=rr,publication_reference=pr,reader_sha256=er['sha256'],rows=audits,counts=result['counts'],track_count=16,lane_count=8,outer_coordinate_count=48,account_engine_called=False,control_engine_called=False,candidate_engine_called=False,weights_normalized=False,risk_is_order_gate=False,fit_called=False,integer_repair_search_independently_recomputed=False,source_hashes={**sources,**{r['path']:r['sha256'] for r in (rr,pr,er)}},**dict.fromkeys(a.EXEC_FLAGS,False)))
 nr=role('nav_reader',root/'nav_reader.py',b'# NAV independent',True);ir={k:refs['candidate_'+alias] for k,alias in dict(account_inputs='inputs',account_publication='inputs_publication',account_audit='inputs_audit',account_reader='inputs_reader').items()};ns={r['path']:r['sha256'] for r in ir.values()};st=put(root/'nav/started.json',{});raw=put(root/'nav/raw_result.json',dict(result=x['nav_metrics']))
 mr=role('nav_metrics',root/'nav/metrics.json',dict(schema='MULTIDECISION_NAV_REFERENCE_METRICS_DOCUMENT_V1',metrics=x['nav_metrics'],input_references=ir,source_hashes=ns,**NAVFLAGS));pr=role('nav_publication',root/'nav/publication.json',dict(schema='MULTIDECISION_NAV_REFERENCE_METRICS_PUBLICATION_V1',status='PUBLISHED_RETROSPECTIVE_EXTERNAL_REFERENCE_ONLY_PENDING_READBACK',metrics_reference=mr,started_reference=st,raw_reference=raw,input_references=ir,source_hashes=ns,**NAVFLAGS));put(root/'navaudit/started.json',{})
 role('nav_audit',root/'navaudit/independent_readback.json',dict(schema='MULTIDECISION_NAV_REFERENCE_METRICS_INDEPENDENT_READBACK_V1',status='PASS',scope='SAVED_ALIGNMENT120_PROJECTION_AND_METRICS_NOT_FX_OR_ACCOUNT_REAUDIT',metrics_reference=mr,publication_reference=pr,reader_sha256=nr['sha256'],source_hashes={**ns,**{r['path']:r['sha256'] for r in (mr,pr,nr)}},producer_called=False,old_metrics_called=False,original_started_dispatch_authority_verified=False,**NAVFLAGS))
 return {k:(r['path'],r['sha256']) for k,r in refs.items()}

class Tests(unittest.TestCase):
 def test_all20_pending_before_io(self):
  with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'All20'):a.read_inputs()
 def test_full_physical_projection_real_compare_api_and_structured_blockers(self):
  with tempfile.TemporaryDirectory() as td:
   bound=physical(Path(td))
   with patch.object(a,'BOUND',bound):c=a.read_inputs()
   self.assertEqual(len(c['kwargs']['candidate_slots']),16);self.assertEqual(len(c['kwargs']['control_slots']),16);b=c['kwargs']['candidate_slots'][0];self.assertIsNone(b['result']);self.assertEqual(a.decode(b['reason'].split(':',1)[1]),b['blocking_reasons_preserved']);self.assertIsInstance(b['blocking_reasons_preserved'][0],dict)
   from backtest.ndx_multidecision_path_comparison_research import compare_multidecision_paths
   r=compare_multidecision_paths(**c['kwargs']);self.assertEqual(len(r['rows']),16);self.assertFalse(r['formal_comparison_passed'])
 def test_audit_role_false_and_raw_slot_swaps_fail(self):
  for kind in ('audit','flag','mapping'):
   with self.subTest(kind=kind),tempfile.TemporaryDirectory() as td:
    root=Path(td);bound=physical(root)
    role='candidate_audit' if kind!='mapping' else 'control_execution';path=Path(bound[role][0]);obj=a.decode(path.read_bytes())
    if kind=='audit':obj['rows'][8]['saved_references']['raw_reference']=obj['rows'][10]['saved_references']['raw_reference']
    elif kind=='flag':obj['point_in_time_verified']=0
    else:obj['candidate_mapping_preserved'][0]['tracks'][0]['candidate_input_reference']['json_pointer']='/inputs/rows/7/tracks/0'
    raw=a.enc(obj);path.write_bytes(raw);bound[role]=(str(path),a.sha(raw))
    with patch.object(a,'BOUND',bound),self.assertRaises(ValueError):a.read_inputs()
if __name__=='__main__':unittest.main()
