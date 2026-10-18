"""Source-bound saved account ledger readback; never executes an engine."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,os,re,types,traceback
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/multidecision_incumbent_execution_20261003_v1'
OUTPUT=ROOT/'data/cache/research/multidecision_incumbent_execution_independent_readback_20261003_v1'
LINEAGE=ROOT/'backtest/ndx_history_failed_lineage_guard_20261008.py';LINEAGE_SHA='fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
BOUND={'result':(str(PARENT/'result.json'),'f837b2a71c7a0d9a08610e211d2c7b1a799902aa38ae1e92d661906a806c2eb4'),'publication':(str(PARENT/'publication.json'),'c56230fca7cc7de0c7ef79604a4588eb7afa3202f61c0baaeae8b5609d5c4afd')}
PRODUCER=('scripts/ndx_multidecision_incumbent_execution_20261003.py','8d05fbc339c525a4721fe20e3d8098c83a748b31dcb179d303b569e4b15ec70a')
CORE=('backtest/ndx_multidecision_incumbent_account_inspection_research.py','8cad873ff374eb2af1031ff0ccf900b7f1fd9ac7575f14229ec4fc7fd6792e16')
CODE={
 'ndx_incumbent_flow_split_control_research':'5e963ddcf321de8b9b607dab11fe36e570050399b68125fdd02f12f671dfdeb3',
 'ndx_dynamic_frozen_incumbent_control':'537908ef0447b1e4e7104afdd2008d4d3d04b60f820bfaab33562dc7114f54e6',
 'ndx_dynamic_fractional_flow_split_research':'d33937157b7b3e4aa0d031962d1a0b0669eb7aa0ded7c1f8818b5d4348291687',
 'ndx_dynamic_fractional_flow_split_research_v2':'40cda887911209e1e2b4dfd401ce702105ba7584506007a2a92cf427667be287',
 'ndx_dynamic_frozen_flow_split_research':'35c19184f08a0394838171fa61afeb781cd4f314799058063186d9c3d38376a8',
 'ndx_dynamic_whole_lot_path':'3ad63f1e59baaa14c32eceddd32340755a516c1022077bd802763d10ef360a95',
 'ndx_dynamic_whole_lot_repair_path':'e614be1a2fe461e483e17413af03153f9a2fe99c31e0412b5daa8954c53d3f34',
 'ndx_whole_lot_repair_diagnostic':'e2f00388b92c88588acaff51c30c608830bf93a00cfc6a84ad8e20a9470381bf',
 'ndx_split_accounting_research':'11bb5225e90c76fe303e90fa9f639e34c3978fd922d230bb2a45f8f9ad24877c',
 'ndx_dynamic_frozen_execution_research':'69d2bf761eac32edd8c39a9fdbffed300ba7cb4740771fbd008b4f09b204813b'}
INPUT_PATHS=dict(inputs='data/cache/research/multidecision_incumbent_inputs_20261003_v1/inputs.json',publication='data/cache/research/multidecision_incumbent_inputs_20261003_v1/publication.json',readback='data/cache/research/multidecision_incumbent_inputs_independent_readback_20261003_v1/independent_readback.json',reader='scripts/ndx_multidecision_incumbent_inputs_independent_readback_20261003.py')
FLAGS=dict.fromkeys(('source_bytes_authenticated','fit_performed','selection_performed','actual_orders_executed','execution_authorized','promotion_allowed','point_in_time_verified','formal_benchmark_passed','automatic_retry_allowed','full_ndx_membership_verified','cash_add_only_search_performed'),False)
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX');LANES=('RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE')
def require(v,m):
 if not v:raise ValueError(m)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,m):require(enc(a)==enc(b),m)
def ref(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def merge(s,r):
 require(type(r)is dict and set(r)=={'path','sha256'} and Path(r['path']).is_absolute() and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Exact absolute external reference');require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def decode(raw):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def load(r,s,body=True):
 merge(s,r);p=Path(r['path']);require(not(p.parent/'failure.json').exists(),'Failed parent');raw=p.read_bytes();require(sha(raw)==r['sha256'],'Same authenticated bytes');return decode(raw) if body else raw
def false(obj):
 for k in FLAGS:require(obj[k] is False,'Exact authority False '+k)
def saved(path,obj):
 raw=enc(obj)
 with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 require(path.read_bytes()==raw,'Saved report bytes');return ref(path,sha(raw))
def hashfile(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def lineage_members(sources):
 raw=LINEAGE.read_bytes();require(sha(raw)==LINEAGE_SHA,'Fixed diagnostic helper bytes')
 module=types.ModuleType('_fixed_history_failed_lineage');module.__file__=str(LINEAGE)
 exec(compile(raw,str(LINEAGE),'exec'),module.__dict__)
 return module.diagnostic_members(sources)

def guard(s,inventory):
 require(hashfile(SOURCE)==LOADED,'Loaded reader drift')
 diagnostic=lineage_members(s)
 for p,h in s.items():require((p in diagnostic or not(Path(p).parent/'failure.json').exists()) and hashfile(p)==h,'Source drift/failure')
 input_parent=Path(INPUT_PATHS['inputs']);input_parent=input_parent if input_parent.is_absolute() else ROOT/input_parent
 require({p.name for p in input_parent.parent.iterdir()}=={'started.json','inputs.json','publication.json'},'Exact original input namespace')
 require({str(p.resolve()) for p in PARENT.rglob('*') if p.is_file()}==inventory,'Exact saved execution inventory')
def inspect_slot(*,row,track,start,post,raw,inspection):
 i=row['track_index'];require(type(i)is int and 0<=i<16,'Exact slot');exact([row['fx_mode'],row['lane'],row['track']],[MODES[i//8],LANES[(i//2)%4],('CONTINUOUS','WHOLE_LOT')[i%2]],'All original coordinates')
 require(start['schema']=='MULTIDECISION_INCUMBENT_ACCOUNT_TRACK_STARTED_V1' and post['schema']=='MULTIDECISION_INCUMBENT_ACCOUNT_TRACK_POSTCHECK_V1','Slot schemas');require(type(start['track_index'])is int and start['track_index']==i,'Started slot');exact(start['coordinate'],[row['fx_mode'],row['lane'],row['track']],'Started coordinate');require(start['input_pointer']==f'/inputs/rows/{i//2}/tracks/{i%2}','Original input pointer');exact(start['prepared_track'],track,'Exact original track')
 for key,value in row.items():exact(post[key],None if key=='postcheck_reference' else value,'Post/result original row '+key)
 for obj in (start,post):false(obj)
 if track['status']=='BLOCKED_ORIGINAL_CONTROL_INPUT':
  require(row['outcome']=='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT' and row['call_invoked'] is False and type(row['returned_call_count'])is int and row['returned_call_count']==0 and raw is None and row['raw_reference'] is None,'Blocked no fabricated cash account');exact(row['blocking_reasons'],track['blocking_reasons'],'Original blockers');return None
 require(track['status']=='CONTROL_INPUTS_PREPARED_NOT_EXECUTED' and row['outcome']=='ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK','Only complete saved account success can certify arithmetic')
 require(row['call_invoked'] is True and type(row['returned_call_count'])is int and row['returned_call_count']==1,'One returned call');require(raw['schema']=='MULTIDECISION_INCUMBENT_ACCOUNT_RAW_RETURN_V1' and raw['returned'] is True and raw['call_invoked'] is True and type(raw['returned_call_count'])is int and raw['returned_call_count']==1 and raw['internal_call_count_unobserved'] is True,'Raw returned facts');require(raw['original_return_is_json'] is True and raw['returned_type']=='dict' and raw['error'] is None and raw['diagnostic_reference'] is None and raw['repr_error'] is None,'Original complete JSON return');false(raw);exact(raw['started_reference'],row['started_reference'],'Raw start');require(post['error'] is None and post['validation_error'] is None,'No technical failure masquerades success')
 return inspection.inspect_saved_control(prepared_track=track,result=raw['result'])
def readback(*,execute=False):
 require(execute is True,'Explicit readback');require(not OUTPUT.exists(),'Create-only no retry');require(all(type(h)is str and re.fullmatch('[a-f0-9]{64}',h) for _,h in BOUND.values()),'Future result/publication pending; no IO')
 sources={str(SOURCE):LOADED};refs={k:ref(p,h) for k,(p,h) in BOUND.items()};d=load(refs['result'],sources);pub=load(refs['publication'],sources)
 require(d['schema']=='MULTIDECISION_INCUMBENT_ACCOUNT_EXECUTION_RESULT_V1' and d['status']=='ALL16_INPUT_SLOTS_PROCESSED_PENDING_INDEPENDENT_READBACK' and d['failure'] is None,'Technical/partial result preserved, cannot certify complete ledger')
 require(pub['schema']=='MULTIDECISION_INCUMBENT_ACCOUNT_EXECUTION_PUBLICATION_V1' and pub['status']=='PUBLISHED_CONDITIONAL_ACCOUNT_RETURNS_PENDING_INDEPENDENT_READBACK','Successful saved publication');exact(pub['result_reference'],refs['result'],'External publication result');false(d);false(pub)
 exact(d['input_references'],pub['input_references'],'Inputs binding');exact(d['source_hashes'],pub['source_hashes'],'Publisher source closure')
 ir=d['input_references'];require(set(ir)==set(INPUT_PATHS),'Four original input roles')
 for k,p in INPUT_PATHS.items():require(Path(ir[k]['path']).resolve()==(ROOT/p).resolve(),'Fixed original input path')
 parents={k:load(r,sources,k!='reader') for k,r in ir.items()};inp=parents['inputs'];audit=parents['readback'];ipub=parents['publication']
 require(inp['schema']=='MULTIDECISION_ORIGINAL_EIGHT_INPUTS_DOCUMENT_V1' and ipub['schema']=='MULTIDECISION_ORIGINAL_EIGHT_INPUTS_PUBLICATION_V1' and ipub['status']=='PUBLISHED_CONTROL_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS','Original inputs source roles');exact(ipub['inputs_reference'],ir['inputs'],'Input pub');require(audit['schema']=='MULTIDECISION_ORIGINAL_EIGHT_INPUTS_INDEPENDENT_READBACK_V1' and audit['status']=='PASS' and audit['scope']=='SAVED_NOMINAL_ORIGINAL_EIGHT_16_CONTROL_INPUT_PROJECTIONS_NOT_ACCOUNTS','Independent inputs scope');exact(audit['inputs_reference'],ir['inputs'],'Audit inputs');exact(audit['publication_reference'],ir['publication'],'Audit pub');require(audit['reader_sha256']==ir['reader']['sha256'],'Original input reader')
 for obj in (inp,ipub):
  for key in ('source_bytes_authenticated','account_simulation_performed','fit_performed','selection_performed','execution_authorized','promotion_allowed','point_in_time_verified','formal_benchmark_passed','automatic_retry_allowed','weights_normalized','cross_lane_execution_reused'):require(obj[key] is False,'Original parent authority False')
 for key in ('producer_called','control_engine_called','candidate_engine_called','fit_called','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed'):require(audit[key] is False,'Input audit authority False')
 exact(inp['source_hashes'],ipub['source_hashes'],'Input publisher closure')
 for p,h in inp['source_hashes'].items():require(audit['source_hashes'].get(p)==h,'Input audit full source coverage')
 for key,n in (('coordinate_count',48),('lane_count',8),('track_count',16),('control_security_count',8),('original_provenance_count',101),('preserved_sidecar_count',7)):require(type(audit['inspection'][key])is int and audit['inspection'][key]==n,'Full input audit denominator')
 expected={str(LINEAGE):LINEAGE_SHA}
 merge(expected,ref(ROOT/PRODUCER[0],PRODUCER[1]))
 for r in ir.values():merge(expected,r)
 for obj in (inp,ipub,audit):
  for p,h in obj['source_hashes'].items():merge(expected,ref(p,h))
 pstart=ipub['started_reference'];require(Path(pstart['path']).resolve()==Path(ir['inputs']['path']).parent/'started.json','Input start');load(pstart,sources);merge(expected,pstart)
 for name,h in CODE.items():merge(expected,ref(ROOT/'backtest'/f'{name}.py',h))
 # Runtime binary entry points are declarations from the frozen runtime version;
 # authenticate all of them, without calling/importing either account engine.
 import sys,numpy,pandas
 require((sys.version.split()[0],numpy.__version__,pandas.__version__)==('3.13.1','2.4.6','2.2.3'),'Original runtime versions')
 for path in (sys.executable,numpy.__file__,pandas.__file__):merge(expected,ref(path,hashfile(path)))
 exact(expected,d['source_hashes'],'Independently constructed producer source union')
 for p,h in expected.items():merge(sources,ref(p,h))
 rawcore=load(ref(ROOT/CORE[0],CORE[1]),sources,False);core=types.ModuleType('_independent_account_ledger');exec(compile(rawcore,CORE[0],'exec'),core.__dict__)
 startref=pub['started_reference'];require(Path(startref['path']).resolve()==PARENT/'started.json','Global started');start=load(startref,sources);require(start['schema']=='MULTIDECISION_INCUMBENT_ACCOUNT_EXECUTION_STARTED_V1','Global start schema');false(start)
 for obj in (pub,start):exact(obj['source_hashes'],expected,'Full global closure');exact(obj['input_references'],ir,'Original references')
 exact(start['runtime'],d['runtime'],'Runtime preserved');require(type(start['track_count'])is int and start['track_count']==16,'Started full16');require(d['runtime']['python']==sys.version and d['runtime']['numpy']==numpy.__version__ and d['runtime']['pandas']==pandas.__version__ and d['runtime']['implementation']==sys.implementation.name,'Frozen runtime provenance')
 inputs=inp['inputs'];require(inputs['schema']=='MULTIDECISION_ORIGINAL_EIGHT_CONTROL_INPUTS_V1','Original full prepared inputs');require(sha(enc({k:v for k,v in inputs.items() if k!='content_sha256'}))==inputs['content_sha256'],'Full prepared content');require(len(inputs['rows'])==8 and len(d['rows'])==16,'All8/16 slots')
 require(d['benchmark_path_status']=='ORIGINAL_EIGHT_SAME_FLOW_CONTROLS_RETURNED_PENDING_AUDIT_012922_EXTERNAL_NAV_ONLY','Original reference account role')
 expected_mapping=[dict(fx_mode=row['fx_mode'],lane=row['lane'],coordinate_indexes=deepcopy(row['coordinate_indexes']),tracks=[{key:deepcopy(t[key]) for key in ('track','candidate_status_preserved','candidate_blocking_reasons_preserved','candidate_input_reference')} for t in row['tracks']]) for row in inputs['rows']]
 exact(d['candidate_mapping_preserved'],expected_mapping,'Complete original candidate mapping')
 require(len(inputs['source_slots'])==8 and len(inputs['original_candidate_provenance'])==101 and len(inputs['preserved_candidate_evidence_sidecars'])==7,'Original8 full provenance domain')
 for li,lane in enumerate(inputs['rows']):
  exact([lane['fx_mode'],lane['lane']],[MODES[li//4],LANES[li%4]],'Complete original lane order');exact(lane['coordinate_indexes'],[li+8*di for di in range(6)],'Full48 candidate linkage');require(len(lane['tracks'])==2 and lane['risk_is_order_gate'] is False,'Two control tracks observed risk only')
  for ti,track in enumerate(lane['tracks']):
   require(track['track']==('CONTINUOUS','WHOLE_LOT')[ti] and track['execution_reused'] is False,'Own original track, no execution reuse')
   for key in ('source_bytes_authenticated','account_simulation_performed','fit_performed','weights_normalized','weights_reoptimized','candidate_inventory_extended','cross_lane_execution_reused','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed','corporate_action_completeness_verified','future_independent_oos'):require(track[key] is False,'Prepared original control authority')
   binding=track['engine_binding'];exact(binding['source_reference'],dict(path='backtest/ndx_incumbent_flow_split_control_research.py',sha256=CODE['ndx_incumbent_flow_split_control_research']),'Fixed original control source');require(binding['function']=='simulate_incumbent_flow_split_control' and binding['keyword_arguments']['track']==track['track'],'Specific original control entry')
   exact(binding['dataframe_restoration_required'],['closes','opens'],'Source matrix restoration');require(type(track['blocking_reasons'])is list and bool(track['blocking_reasons'])==(track['status']=='BLOCKED_ORIGINAL_CONTROL_INPUT'),'Original blocked reason')

 inventory={refs['result']['path'],refs['publication']['path'],startref['path']};reports=[]
 for row in d['rows']:
  for key in ('started_reference','postcheck_reference','raw_reference'):
   if row[key] is not None:inventory.add(row[key]['path'])
 guard(sources,inventory);OUTPUT.mkdir(parents=True)
 try:
  ownstart=saved(OUTPUT/'started.json',dict(schema='MULTIDECISION_INCUMBENT_ACCOUNT_EXECUTION_READBACK_STARTED_V1',result_reference=refs['result'],publication_reference=refs['publication'],source_hashes=sources,**FLAGS))
  for i,row in enumerate(d['rows']):
   require(type(row['track_index'])is int and row['track_index']==i,'Full16 original order');track=inputs['rows'][i//2]['tracks'][i%2];parts={}
   for role,filename in (('started_reference','started.json'),('postcheck_reference','postcheck.json'),('raw_reference','raw_result.json')):
    r=row[role]
    if r is None:require(role=='raw_reference','Required saved slot evidence');parts[role]=None;continue
    require(Path(r['path']).resolve()==PARENT/'tracks'/f'{i:02d}'/filename,'Fixed original slot file');parts[role]=load(r,sources);inventory.add(r['path'])
   for obj in parts.values():
    if obj is not None:exact(obj['source_hashes'],expected,'Slot source closure');exact(obj['input_references'],ir,'Slot input roles')
   for role in ('started_reference','raw_reference'):
    if parts[role] is not None:exact(parts[role]['runtime'],d['runtime'],'Slot original runtime')
   report=inspect_slot(row=row,track=track,start=parts['started_reference'],post=parts['postcheck_reference'],raw=parts['raw_reference'],inspection=core);reports.append(dict(track_index=i,coordinate=[row['fx_mode'],row['lane'],row['track']],outcome=row['outcome'],saved_references={k:row[k] for k in parts},inspection=report))
  for k,n in (('track_count',16),('lane_count',8),('outer_coordinate_count',48),('account_call_count',sum(r['call_invoked'] is True for r in d['rows'])),('returned_call_count',sum(r['returned_call_count'] for r in d['rows']))):require(type(d[k])is int and d[k]==n,'Exact full result denominator')
  exact(d['counts'],{v:sum(r['outcome']==v for r in d['rows']) for v in sorted({r['outcome'] for r in d['rows']})},'All outcomes counted')
  report=dict(schema='MULTIDECISION_INCUMBENT_ACCOUNT_EXECUTION_INDEPENDENT_READBACK_V1',status='PASS',scope='SAVED16_ORIGINAL_EIGHT_LEDGER_CONSERVATION_AND_TWR_WITH_LITERAL_WEIGHTS_RISK_OBSERVATION',result_reference=refs['result'],publication_reference=refs['publication'],reader_sha256=LOADED,source_hashes=sources,rows=reports,counts=d['counts'],track_count=16,lane_count=8,outer_coordinate_count=48,account_engine_called=False,control_engine_called=False,candidate_engine_called=False,weights_normalized=False,risk_is_order_gate=False,fit_called=False,integer_repair_search_independently_recomputed=False,**FLAGS)
  rr=saved(OUTPUT/'independent_readback.json',report);guard(sources,inventory)
  for r in (ownstart,rr):require(hashfile(r['path'])==r['sha256'],'Own output drift')
  require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact readback inventory');return rr
 except BaseException as e:
  if not(OUTPUT/'failure.json').exists():saved(OUTPUT/'failure.json',dict(status='FAILED_NO_RETRY',completed_track_count=len(reports),completed_track_inspections=reports,result_reference=refs['result'],publication_reference=refs['publication'],error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc()),**FLAGS))
  raise
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
