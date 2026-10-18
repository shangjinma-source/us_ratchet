"""Independent full16 saved comparison readback, reconstructing all source roles.
No engine, scoring, ledger arithmetic or comparison implementation is imported.
Complete published account evidence required; technical attempts remain in their
original failure namespaces and cannot become successful comparable accounts.
"""
from pathlib import Path
from copy import deepcopy
import hashlib,json,re,os,types,traceback
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
LINEAGE=ROOT/'backtest/ndx_history_failed_lineage_guard_20261008.py';LINEAGE_SHA='fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
BOUND={}
for role,prefix in (('candidate','account'),('control','incumbent')):
 for name,file in (('inputs','inputs.json'),('inputs_publication','publication.json')):BOUND[role+'_'+name]=(f'data/cache/research/multidecision_{prefix}_inputs_20261003_v1/{file}',None)
 BOUND[role+'_inputs_audit']=(f'data/cache/research/multidecision_{prefix}_inputs_independent_readback_20261003_v1/independent_readback.json',None)
 BOUND[role+'_inputs_reader']=(f'scripts/ndx_multidecision_{prefix}_inputs_independent_readback_20261003.py',None)
 for name,file in (('execution','result.json'),('execution_publication','publication.json')):BOUND[role+'_'+name]=(f'data/cache/research/multidecision_{prefix}_execution_20261003_v1/{file}',None)
 BOUND[role+'_audit']=(f'data/cache/research/multidecision_{prefix}_execution_independent_readback_20261003_v1/independent_readback.json',None)
 BOUND[role+'_reader']=(f'scripts/ndx_multidecision_{prefix}_execution_independent_readback_20261003.py',None)
BOUND.update(nav_metrics=('data/cache/research/multidecision_nav_reference_metrics_20261003_v1/metrics.json',None),nav_publication=('data/cache/research/multidecision_nav_reference_metrics_20261003_v1/publication.json',None),nav_audit=('data/cache/research/multidecision_nav_reference_metrics_independent_readback_20261003_v1/independent_readback.json',None),nav_reader=('scripts/ndx_multidecision_nav_reference_metrics_independent_readback_20261003.py',None))
ACTUAL_SOURCE_HASHES={'candidate_inputs': 'c3311e2e9aea24c96c695e5a860f6ecd784356bbc8995657f1e13061de0ff4b9', 'candidate_inputs_publication': '64c301cd36c9274f345997a2adb6ba67eb46ce824d8190865b4578441afca940', 'candidate_inputs_audit': '8568bbe2ea6fa33d2aa9956a72a8b11d902f353b6078044a9a832384ec0886fb', 'candidate_inputs_reader': '85f3fd668a948bf9b3e68f1d4c013ee6def02d806f57373c41ef65698443576d', 'candidate_execution': 'c79aafa533d78be14f888cd109d9942702c829c39d5ce0d09904501b5c812870', 'candidate_execution_publication': 'e1b00c1c1f8e4b4d31893e77ba46bc12009ba3e5fd452fdca1b1b01266ab68c7', 'candidate_audit': '33ebcb571c81793f92070c8db789b409b98eca139778c0c192c80fa6abcc74bb', 'candidate_reader': '69c54a144ca582a8537a4c52b0fbb6fdf61a0f2ece0d4233206cc87f6f729ca2', 'control_inputs': '9705b1ed2e42351050a5e413dcbe73fdc5d42efc16a03a79b560fe0c69f68aa4', 'control_inputs_publication': '5b8da9d3440422ec8899d5ad73abf589ea43a1869aa4aa84b6227ce480958fe9', 'control_inputs_audit': '48aac644a66b2832d48ff6ea7100e3aa720c68da2e6d1a3bc35e1f5ae95d02f1', 'control_inputs_reader': 'de6b6a6da0c3aa327855e029e937a25d66069d98b01598b69818534984f8ffc9', 'control_execution': 'f837b2a71c7a0d9a08610e211d2c7b1a799902aa38ae1e92d661906a806c2eb4', 'control_execution_publication': 'c56230fca7cc7de0c7ef79604a4588eb7afa3202f61c0baaeae8b5609d5c4afd', 'control_audit': '8b8e318426c94b6a70389a724f50c30df68c807204ad789f2159185cd943e975', 'control_reader': '35cd3824d935f75eb00c05161f89291f287587122fce0b63f7dd8a8fa1fff730', 'nav_metrics': '2dc029413e03a8721c0c9baf6494115244f9d96b57640849090fb36be4d69a59', 'nav_publication': 'eda71707860dc127c43e343d568b6cfdb781060576b2d649546e90797e8866db', 'nav_audit': '7d93d12d18059d5806ce9059e376b2beb0f3995dd3b0d3f12f61892b25cf1372', 'nav_reader': 'c3a0a7ad28f6e8eb46c172ab000e520fe17c7744e679f9834fcf776fda83f6f6'}
BOUND={role:(path,ACTUAL_SOURCE_HASHES[role]) for role,(path,_) in BOUND.items()}
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX');LANES=('RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE')
FLAGS=dict.fromkeys(('source_bytes_authenticated','account_executed','account_ledger_independently_reaudited','fit_performed','formal_comparison_passed','promotion_allowed','point_in_time_verified'),False)
EXEC_FLAGS=('source_bytes_authenticated','fit_performed','selection_performed','actual_orders_executed','execution_authorized','promotion_allowed','point_in_time_verified','formal_benchmark_passed','automatic_retry_allowed','full_ndx_membership_verified','cash_add_only_search_performed')
def require(v,m):
 if not v:raise ValueError(m)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,m):require(enc(a)==enc(b),m)
def sha(b):return hashlib.sha256(b).hexdigest()
def ref(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def pointer(r,p):return dict(r,json_pointer=p)
def merge(s,r):
 require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and Path(r['path']).is_absolute() and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Absolute full byte reference');require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def decode(b):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def load(r,s,body=True):
 merge(s,r);p=Path(r['path']);require(not(p.parent/'failure.json').exists(),'Failed source namespace');b=p.read_bytes();require(sha(b)==r['sha256'],'Hash same consumed bytes');return decode(b) if body else b
def lineage_members(sources):
 raw=LINEAGE.read_bytes();require(sha(raw)==LINEAGE_SHA,'Fixed diagnostic helper bytes')
 module=types.ModuleType('_fixed_history_failed_lineage');module.__file__=str(LINEAGE)
 exec(compile(raw,str(LINEAGE),'exec'),module.__dict__)
 return module.diagnostic_members(sources)

def guard(sources,inventories):
 require(sha(SOURCE.read_bytes())==LOADED,'Loaded adapter drift')
 diagnostic=lineage_members(sources)
 for p,h in sources.items():
  q=Path(p);require(p in diagnostic or not(q.parent/'failure.json').exists(),'Parent failed');digest=hashlib.sha256()
  with q.open('rb') as f:
   for b in iter(lambda:f.read(1048576),b''):digest.update(b)
  require(digest.hexdigest()==h,'Source drift')
 for parent,expected in inventories.items():require({str(p.resolve()) for p in Path(parent).rglob('*') if p.is_file()}==set(expected),'Exact source namespace')
def false(v,keys):
 for k in keys:require(v[k] is False,'No source authority '+k)
def project_inputs(*,documents,references,slot_documents):
 d=documents;refs=references;slots={}
 for role,prefix in (('candidate','MULTIDECISION_ACCOUNT'),('control','MULTIDECISION_INCUMBENT_ACCOUNT')):
  result=d[role+'_execution'];pub=d[role+'_execution_publication'];audit=d[role+'_audit'];inputs=d[role+'_inputs']['inputs'];prepared_schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_V1' if role=='candidate' else 'MULTIDECISION_ORIGINAL_EIGHT_CONTROL_INPUTS_V1'
  idoc=d[role+'_inputs'];ipub=d[role+'_inputs_publication'];ia=d[role+'_inputs_audit'];base='MULTIDECISION_STATEFUL_ACCOUNT' if role=='candidate' else 'MULTIDECISION_ORIGINAL_EIGHT'
  require(idoc['schema']==base+'_INPUTS_DOCUMENT_V1' and ipub['schema']==base+'_INPUTS_PUBLICATION_V1','Role-specific original input publication')
  require(ipub['status']==('PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS' if role=='candidate' else 'PUBLISHED_CONTROL_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS'),'Published prepared-only state');exact(ipub['inputs_reference'],refs[role+'_inputs'],'Input publication anchor')
  require(ia['schema']==base+'_INPUTS_INDEPENDENT_READBACK_V1' and ia['status']=='PASS' and ia['scope']==('SAVED_FULL48_TO_16_STATEFUL_INPUT_PROJECTION_NOT_ACCOUNT_EXECUTION' if role=='candidate' else 'SAVED_NOMINAL_ORIGINAL_EIGHT_16_CONTROL_INPUT_PROJECTIONS_NOT_ACCOUNTS'),'Actual input audit role');exact(ia['inputs_reference'],refs[role+'_inputs'],'Input audit bytes');exact(ia['publication_reference'],refs[role+'_inputs_publication'],'Input audit publication');require(ia['reader_sha256']==refs[role+'_inputs_reader']['sha256'],'Input reader code role')
  pflags=('source_bytes_authenticated','account_simulation_performed','fit_performed','selection_performed','execution_authorized','promotion_allowed','point_in_time_verified','formal_benchmark_passed','automatic_retry_allowed')
  for obj in (idoc,ipub):false(obj,pflags)
  false(ia,('producer_called','fit_called','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed')+(('account_engine_called',) if role=='candidate' else ('control_engine_called','candidate_engine_called')))
  if role=='control':
   for obj in (idoc,ipub):false(obj,('weights_normalized','cross_lane_execution_reused'))
  exact(idoc['source_hashes'],ipub['source_hashes'],'Original input source union')
  for p,h in idoc['source_hashes'].items():require(ia['source_hashes'].get(p)==h,'Original input audit full source coverage')
  require(inputs['schema']==prepared_schema and len(inputs['rows'])==8,'Exact prepared role');require(sha(enc({k:v for k,v in inputs.items() if k!='content_sha256'}))==inputs['content_sha256'],'Original prepared content hash')
  require(result['schema']==prefix+'_EXECUTION_RESULT_V1' and result['status']=='ALL16_INPUT_SLOTS_PROCESSED_PENDING_INDEPENDENT_READBACK' and result['failure'] is None,'No incomplete account publication')
  require(pub['schema']==prefix+'_EXECUTION_PUBLICATION_V1' and pub['status']=='PUBLISHED_CONDITIONAL_ACCOUNT_RETURNS_PENDING_INDEPENDENT_READBACK','Published account role');exact(pub['result_reference'],refs[role+'_execution'],'Execution publication link')
  require(audit['schema']==prefix+'_EXECUTION_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Actual role-specific ledger audit');require(audit['scope']==('SAVED16_ACCOUNT_LEDGER_CONSERVATION_AND_TWR_NOT_REPAIR_OPTIMALITY' if role=='candidate' else 'SAVED16_ORIGINAL_EIGHT_LEDGER_CONSERVATION_AND_TWR_WITH_LITERAL_WEIGHTS_RISK_OBSERVATION'),'Exact independent arithmetic scope')
  exact(audit['result_reference'],refs[role+'_execution'],'Audited execution');exact(audit['publication_reference'],refs[role+'_execution_publication'],'Audited publication');require(audit['reader_sha256']==refs[role+'_reader']['sha256'],'Pinned role reader')
  require(len(result['rows'])==len(audit['rows'])==len(slot_documents[role])==16,'Full16 source slots')
  for obj in (result,pub,audit):false(obj,EXEC_FLAGS)
  false(audit,('account_engine_called','fit_called','integer_repair_search_independently_recomputed'))
  if role=='control':false(audit,('control_engine_called','candidate_engine_called','weights_normalized','risk_is_order_gate'))
  for k,n in (('track_count',16),('lane_count',8),('outer_coordinate_count',48)):
   for obj in (result,audit):require(type(obj[k])is int and obj[k]==n,'Exact complete source denominator')
  reconstructed_counts={v:sum(row['outcome']==v for row in result['rows']) for v in sorted({row['outcome'] for row in result['rows']})}
  exact(result['counts'],reconstructed_counts,'Counts from complete original rows')
  for key,value in dict(account_call_count=sum(row['call_invoked'] is True for row in result['rows']),returned_call_count=sum(row['returned_call_count'] for row in result['rows'])).items():require(type(result[key])is int and result[key]==value,'Exact original execution call count')
  exact(result['counts'],audit['counts'],'Audited all states');exact(result['source_hashes'],pub['source_hashes'],'Published closure')
  expected_ir={k:refs[role+'_'+alias] for k,alias in dict(inputs='inputs',publication='inputs_publication',readback='inputs_audit',reader='inputs_reader').items()}
  exact(result['input_references'],expected_ir,'Original input four roles');exact(pub['input_references'],expected_ir,'Published input four roles')
  for p,h in result['source_hashes'].items():require(audit['source_hashes'].get(p)==h,'Ledger audit source coverage')
  for r in (refs[role+'_execution'],refs[role+'_execution_publication'],refs[role+'_reader']):require(audit['source_hashes'].get(r['path'])==r['sha256'],'Audit direct role coverage')
  slots[role]=[]
  for i,(row,ar,body) in enumerate(zip(result['rows'],audit['rows'],slot_documents[role])):
   coord=[MODES[i//8],LANES[(i//2)%4],('CONTINUOUS','WHOLE_LOT')[i%2]]
   require(type(row['track_index'])is int and row['track_index']==i and type(ar['track_index'])is int and ar['track_index']==i,'Exact original slot index');exact([row['fx_mode'],row['lane'],row['track']],coord,'Original coordinate');exact(ar['coordinate'],coord,'Audit original coordinate');require(ar['outcome']==row['outcome'],'Audit outcome')
   exact(ar['saved_references'],{k:row[k] for k in ('started_reference','postcheck_reference','raw_reference')},'Audited saved byte references')
   start=body['started'];post=body['postcheck'];raw=body['raw'];tr=inputs['rows'][i//2]['tracks'][i%2]
   require(start['schema']==prefix+'_TRACK_STARTED_V1' and post['schema']==prefix+'_TRACK_POSTCHECK_V1','Saved per-slot roles');exact(start['prepared_track'],tr,'Original prepared track');require(start['input_pointer']==f'/inputs/rows/{i//2}/tracks/{i%2}','Exact prepared pointer');exact(start['coordinate'],coord,'Saved attempt coordinate')
   for k,v in row.items():exact(post[k],None if k=='postcheck_reference' else v,'Original post/result field')
   for obj in (start,post,raw):
    if obj is not None:exact(obj['input_references'],expected_ir,'Slot original sources');exact(obj['source_hashes'],result['source_hashes'],'Slot complete source map');false(obj,EXEC_FLAGS)
   entry=dict(coordinate=coord,outcome=row['outcome'],evidence_reference=pointer(row['postcheck_reference'],''),reason=None,result=None,result_reference=None,audit_evidence=None)
   if row['outcome']=='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT':
    require(raw is None and row['raw_reference'] is None and ar['inspection'] is None and row['call_invoked'] is False and type(row['returned_call_count'])is int and row['returned_call_count']==0,'Blocked means no fabricated account');require(type(row['blocking_reasons'])is list and row['blocking_reasons'],'Saved blocked reason');entry['reason']='ORIGINAL_BLOCKING_REASONS_JSON:'+enc(row['blocking_reasons']).decode('utf-8');entry['blocking_reasons_preserved']=deepcopy(row['blocking_reasons'])
   else:
    require(row['outcome']=='ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK' and raw['schema']==prefix+'_RAW_RETURN_V1' and raw['returned'] is True and raw['original_return_is_json'] is True and raw['error'] is None,'Saved comparable return');require(type(raw['returned_call_count'])is int and raw['returned_call_count']==1 and raw['call_invoked'] is True,'One original returned call');exact(raw['started_reference'],row['started_reference'],'Original raw start')
    ins=ar['inspection'];require(ins['schema']==('MULTIDECISION_ACCOUNT_LEDGER_INSPECTION_V1' if role=='candidate' else 'MULTIDECISION_ORIGINAL_EIGHT_LEDGER_INSPECTION_V1') and ins['status']=='PASS' and ins['track']==coord[2],'Actual role-specific per-slot inspection')
    resultref=pointer(row['raw_reference'],'/result');entry.update(result=deepcopy(raw['result']),result_reference=resultref,audit_evidence=dict(reference=pointer(refs[role+'_audit'],f'/rows/{i}/inspection'),reader_reference=pointer(refs[role+'_reader'],''),result_reference=resultref,inspection=deepcopy(ins)))
   slots[role].append(entry)
 control=d['control_inputs']['inputs'];candidate=d['candidate_inputs']['inputs'];exact(control['candidate_evidence_references'],{k:refs['candidate_'+alias] for k,alias in dict(inputs='inputs',publication='inputs_publication',readback='inputs_audit',reader='inputs_reader').items()},'Control parent is this exact candidate input')
 mapping=[dict(fx_mode=r['fx_mode'],lane=r['lane'],coordinate_indexes=deepcopy(r['coordinate_indexes']),tracks=[{k:deepcopy(t[k]) for k in ('track','candidate_status_preserved','candidate_blocking_reasons_preserved','candidate_input_reference')} for t in r['tracks']]) for r in control['rows']]
 exact(d['control_execution']['candidate_mapping_preserved'],mapping,'Complete candidate/control mapping')
 for i,r in enumerate(control['rows']):
  for j,tr in enumerate(r['tracks']):
   ct=candidate['rows'][i]['tracks'][j];exact(tr['candidate_input_reference'],pointer(refs['candidate_inputs'],f'/inputs/rows/{i}/tracks/{j}'),'Actual candidate source pointer');exact(tr['candidate_status_preserved'],ct['status'],'Saved candidate status');exact(tr['candidate_blocking_reasons_preserved'],ct['blocking_reasons'],'Saved candidate blockers')
 nav=d['nav_metrics'];np=d['nav_publication'];na=d['nav_audit'];require(nav['schema']=='MULTIDECISION_NAV_REFERENCE_METRICS_DOCUMENT_V1' and np['schema']=='MULTIDECISION_NAV_REFERENCE_METRICS_PUBLICATION_V1' and np['status']=='PUBLISHED_RETROSPECTIVE_EXTERNAL_REFERENCE_ONLY_PENDING_READBACK','Actual NAV reference document')
 exact(np['metrics_reference'],refs['nav_metrics'],'NAV publication');require(na['schema']=='MULTIDECISION_NAV_REFERENCE_METRICS_INDEPENDENT_READBACK_V1' and na['status']=='PASS' and na['scope']=='SAVED_ALIGNMENT120_PROJECTION_AND_METRICS_NOT_FX_OR_ACCOUNT_REAUDIT','Actual NAV independent scope');exact(na['metrics_reference'],refs['nav_metrics'],'Audited NAV');exact(na['publication_reference'],refs['nav_publication'],'Audited NAV pub');require(na['reader_sha256']==refs['nav_reader']['sha256'],'NAV reader')
 navflags=('source_bytes_authenticated','account_executed','account_metrics_calculated','subscription_redemption_modeled','fit_performed','selection_performed','point_in_time_verified','historical_available_at_verified','benchmark_qualified','formal_admission_allowed','formal_comparison_passed','cohort_statistics_computed','cohort_p50_computed','cohort_p10_computed','mode_selected_using_results','calendar_compressed','missing_values_filled','execution_authorized','promotion_allowed','automatic_retry_allowed','alignment_conversion_reaudited','future_independent_oos','untouched_holdout')
 for obj in (nav,np,na):false(obj,navflags)
 false(na,('producer_called','old_metrics_called','original_started_dispatch_authority_verified'))
 for key,alias in dict(account_inputs='inputs',account_publication='inputs_publication',account_audit='inputs_audit',account_reader='inputs_reader').items():
  for obj in (nav,np):exact(obj['input_references'][key],refs['candidate_'+alias],'All four original NAV calendar roles')
 for obj in (nav,np):
  exact(obj['input_references']['account_inputs'],refs['candidate_inputs'],'NAV uses same account calendar source');exact(obj['source_hashes'],nav['source_hashes'],'NAV publisher source union')
 for p,h in nav['source_hashes'].items():require(na['source_hashes'].get(p)==h,'NAV audit full source coverage')
 for r in (refs['nav_metrics'],refs['nav_publication'],refs['nav_reader']):require(na['source_hashes'].get(r['path'])==r['sha256'],'NAV audit direct role coverage')
 return dict(candidate_prepared=deepcopy(candidate),control_prepared=deepcopy(control),candidate_slots=slots['candidate'],control_slots=slots['control'],nav_metrics=deepcopy(nav['metrics']),source_references=dict(candidate_prepared=pointer(refs['candidate_inputs'],'/inputs'),control_prepared=pointer(refs['control_inputs'],'/inputs'),candidate_results=pointer(refs['candidate_execution'],''),control_results=pointer(refs['control_execution'],''),nav_metrics=pointer(refs['nav_metrics'],'/metrics')))
def load_sources():
 require(all(type(h)is str and re.fullmatch('[a-f0-9]{64}',h) for _,h in BOUND.values()),'All20 external roles required before IO')
 refs={k:ref(ROOT/p,h) for k,(p,h) in BOUND.items()};sources={str((ROOT/ADAPTER[0]).resolve()):ADAPTER[1],str(LINEAGE):LINEAGE_SHA};docs={k:load(r,sources,not k.endswith('_reader')) for k,r in refs.items()};inventories={};slotdocs={}
 for role in ('candidate','control'):
  parent=Path(refs[role+'_execution']['path']).parent;expected={str(parent/name) for name in ('started.json','result.json','publication.json')};slotdocs[role]=[]
  startref=docs[role+'_execution_publication']['started_reference'];require(Path(startref['path']).resolve()==parent/'started.json','Fixed global start');load(startref,sources)
  for i,row in enumerate(docs[role+'_execution']['rows']):
   item={}
   for k,filename in dict(started='started.json',postcheck='postcheck.json',raw='raw_result.json').items():
    r=row[{'started':'started_reference','postcheck':'postcheck_reference','raw':'raw_reference'}[k]]
    if r is None:require(k=='raw','Required actual saved source');item[k]=None;continue
    require(Path(r['path']).resolve()==parent/'tracks'/f'{i:02d}'/filename,'Exact per-task byte source');item[k]=load(r,sources);expected.add(r['path'])
   slotdocs[role].append(item)
  inventories[str(parent)]=expected
  for name,files in (('inputs',('started.json','inputs.json','publication.json')),('inputs_audit',('started.json','independent_readback.json')),('audit',('started.json','independent_readback.json'))):
   folder=Path(refs[role+'_'+name]['path']).parent;inventories[str(folder)]={str(folder/f) for f in files}
  load(docs[role+'_inputs_publication']['started_reference'],sources)
 navparent=Path(refs['nav_metrics']['path']).parent;inventories[str(navparent)]={str(navparent/f) for f in ('started.json','raw_result.json','metrics.json','publication.json')}
 for key,filename in (('started_reference','started.json'),('raw_reference','raw_result.json')):
  rr=docs['nav_publication'][key];require(Path(rr['path']).resolve()==navparent/filename,'Original NAV auxiliary path');body=load(rr,sources)
  if key=='raw_reference':exact(body['result'],docs['nav_metrics']['metrics'],'NAV raw result preserved')
 folder=Path(refs['nav_audit']['path']).parent;inventories[str(folder)]={str(folder/f) for f in ('started.json','independent_readback.json')}
 for obj in docs.values():
  if type(obj)is dict:
   for p,h in obj.get('source_hashes',{}).items():merge(sources,ref(p,h))
 # An audit started record is observed bytes only unless its original audit
 # explicitly bound it. It is never used as dispatch or numerical authority.
 for parent,names in inventories.items():
  start=Path(parent)/'started.json'
  if str(start) not in sources:
   raw=start.read_bytes();merge(sources,ref(start,sha(raw)))
 kwargs=project_inputs(documents=docs,references=refs,slot_documents=slotdocs);guard(sources,inventories)
 return dict(kwargs=kwargs,source_hashes=sources,input_references=refs,source_inventories={k:sorted(v) for k,v in inventories.items()},all_original_audit_starts_externally_anchored=False,**FLAGS)


PARENT=ROOT/'data/cache/research/multidecision_path_comparison_20261003_v1'
OUTPUT=ROOT/'data/cache/research/multidecision_path_comparison_independent_readback_20261003_v1'
COMPARISON_SHA='40e32bbea680775252bcdc880c5ca07cc7163ed5e0af42707ac8c56a009e1656'
PUBLICATION_SHA='bdbb1abdff6253227b73329b4a3a7081f98a12fb180d6bbd06724a2798f4430e'
PRODUCER=('scripts/ndx_multidecision_path_comparison_20261003.py','8e964f9aab6a8395b66579bdcbc0ce1b8b4a667405bd83b861ae5b879b0b9cf0')
ADAPTER=('scripts/ndx_multidecision_path_comparison_source_adapter_20261003.py','3e9690118f50248dbf939f613cc7cf0fc5dabbb7ee2db5a4d3be79b33285d32b')
CHECKER=('backtest/ndx_multidecision_path_comparison_inspection_research.py','abe953c1277f1817ae1c1d84f7be2c1ceb4754222af169aa46a4afa1be72d236')
PRODUCER_CODE={
'ndx_multidecision_path_comparison_research':'741cfa727b30949dff60983ece89a8a734df98b988c1c0a484b1c650d80278d1',
'ndx_multidecision_reference_metrics_research':'0a1ef7ff8590538fdb29ce013027bd2ebd0ed17a816f405bc43bb0eef9489e62',
'ndx_same_window_nav_reference_metrics_research':'bfb582e72dd3a23da5da4898d633d5afa310af0132aa16bb6896ebcac0d82a4f',
'ndx_cash_fork_reference_window_research':'0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163'}
PUBLICATION_FLAGS=('source_bytes_authenticated','account_engine_called','account_ledger_replayed','fit_performed','selection_performed','actual_orders_executed','execution_authorized','promotion_allowed','point_in_time_verified','formal_comparison_passed','formal_noninferiority_passed','cohort_statistics_computed','future_independent_oos','automatic_retry_allowed')
def saved(path,obj):
 raw=enc(obj)
 with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 require(path.read_bytes()==raw,'Own output bytes');return ref(path,sha(raw))
def readback(*,execute=False):
 require(execute is True,'Explicit independent readback')
 for h in (COMPARISON_SHA,PUBLICATION_SHA,PRODUCER[1],ADAPTER[1],CHECKER[1],*[h for _,h in BOUND.values()]):require(type(h)is str and re.fullmatch('[a-f0-9]{64}',h),'Future all source/result anchors pending; no IO')
 require(not OUTPUT.exists(),'Exclusive readback no retry')
 c=load_sources();expected=dict(c['source_hashes']);load(ref(ROOT/PRODUCER[0],PRODUCER[1]),expected,False)
 for name,h in PRODUCER_CODE.items():load(ref(ROOT/'backtest'/f'{name}.py',h),expected,False)
 sources=dict(expected);merge(sources,ref(SOURCE,LOADED));rawchecker=load(ref(ROOT/CHECKER[0],CHECKER[1]),sources,False);checker=types.ModuleType('_independent_comparison_arithmetic');exec(compile(rawchecker,CHECKER[0],'exec'),checker.__dict__)
 rr=ref(PARENT/'comparison.json',COMPARISON_SHA);pr=ref(PARENT/'publication.json',PUBLICATION_SHA);document=load(rr,sources);publication=load(pr,sources)
 require(publication['schema']=='MULTIDECISION_PATH_COMPARISON_PUBLICATION_V1' and publication['status']=='PUBLISHED_SINGLE_PATH_DIAGNOSTICS_PENDING_INDEPENDENT_READBACK_NOT_FORMAL_GATE','Successful diagnostic publication')
 exact(publication['comparison_reference'],rr,'Actual published comparison');rawref=publication['raw_reference'];startref=publication['started_reference']
 require(Path(rawref['path']).resolve()==PARENT/'raw_result.json' and Path(startref['path']).resolve()==PARENT/'started.json','Fixed original auxiliary files')
 raw=load(rawref,sources);start=load(startref,sources);require(start['schema']=='MULTIDECISION_PATH_COMPARISON_STARTED_V1' and raw['schema']=='MULTIDECISION_PATH_COMPARISON_RAW_RETURN_V1','Original start and raw schemas')
 require(raw['call_invoked'] is True and raw['returned'] is True and raw['original_return_is_json'] is True and raw['returned_type']=='dict' and raw['error'] is None,'No technical failure falsely scored');exact(raw['started_reference'],startref,'Returned raw start')
 require(document['schema']=='MULTIDECISION_PATH_COMPARISON_DOCUMENT_V1' and document['independent_readback_status']=='PENDING','Original pending comparison');exact(document['raw_reference'],rawref,'Document original raw');exact(document['comparison'],raw['result'],'Original raw full result preserved')
 for obj in (start,raw,document,publication):
  exact(obj['input_references'],c['input_references'],'All20 actual roles');exact(obj['source_hashes'],expected,'Complete independently constructed producer source union');exact(obj['source_inventories'],c['source_inventories'],'Complete closed source inventories');exact(obj['adapter_reference'],ref(ROOT/ADAPTER[0],ADAPTER[1]),'Versioned source adapter bytes')
  require(obj['adapter_configuration_source']=='AUTHENTICATED_PUBLISHER_STATIC20_BOUND_IN_PRIVATE_INSTANCE_ON_DISK_DEFAULTS_NOT_EXECUTED' and obj['all_original_audit_starts_externally_anchored'] is False,'Static configured adapter, no invented start authority');false(obj,PUBLICATION_FLAGS)
 inventories=dict(c['source_inventories']);inventories[str(PARENT)]=[str(PARENT/name) for name in ('started.json','raw_result.json','comparison.json','publication.json')];guard(sources,inventories);OUTPUT.mkdir(parents=True);written=[];arithmetic_completed=False
 try:
  written.append(saved(OUTPUT/'started.json',dict(schema='MULTIDECISION_PATH_COMPARISON_INDEPENDENT_STARTED_V1',comparison_reference=rr,publication_reference=pr,source_hashes=sources,**dict.fromkeys(PUBLICATION_FLAGS,False))))
  inspection=checker.inspect_multidecision_comparison(saved_comparison=document['comparison'],**c['kwargs']);require(inspection['status']=='PASS','Complete independent comparison inspection');arithmetic_completed=True;guard(sources,inventories)
  result=saved(OUTPUT/'independent_readback.json',dict(schema='MULTIDECISION_PATH_COMPARISON_INDEPENDENT_READBACK_V1',status='PASS',scope='SAVED16_FULL_PATH_METRICS_AND_PAIRED_DISTANCES_NOT_ACCOUNT_REAUDIT_OR_COHORT_GATE',comparison_reference=rr,publication_reference=pr,reader_sha256=LOADED,input_references=c['input_references'],source_hashes=sources,source_inventories=inventories,inspection=inspection,producer_called=False,adapter_called=False,comparator_called=False,**dict.fromkeys(PUBLICATION_FLAGS,False)));written.append(result);guard(sources,inventories)
  require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact own inventory')
  for r in written:require(sha(Path(r['path']).read_bytes())==r['sha256'],'Own saved bytes drift')
  return result
 except BaseException as e:
  if not (OUTPUT/'failure.json').exists():saved(OUTPUT/'failure.json',dict(status='FAILED_NO_RETRY',arithmetic_inspection_completed=arithmetic_completed,saved_references=written,comparison_reference=rr,publication_reference=pr,error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc()),**dict.fromkeys(PUBLICATION_FLAGS,False)))
  raise
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
