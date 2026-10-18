"""Independent outer-refit receipts; explicit external postcheck anchor, no fitting."""
from copy import deepcopy
from pathlib import Path
from fractions import Fraction
import hashlib,json,math,os,re,sys,types
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PRODUCER=ROOT/'scripts/ndx_outer_lane_refit_worker_v2_20261008.py';PRODUCER_SHA='81f4d0a35f049ba7642cdb3f7861b0dd8ad3e63c735b8fbf0eed474ad1bac5cd'
INSPECTOR=ROOT/'backtest/ndx_outer_refit_result_inspection_research.py'
INSPECTOR_SHA='2ed1cf88dce32f9c84359a0606325ef920c8d9addc13dcfbf0130407e62bdc5a'
PARENT=ROOT/'data/cache/research/outer_lane_cutoff_refit_worker_20261008_v2'
OUTPUT=ROOT/'data/cache/research/outer_lane_cutoff_refit_independent_readback_20261008_v2'
CODES={'prepare':('backtest/ndx_multidecision_selected_refit_inputs_research.py','d1ffb2fb550dd1000a3fc8a7003230c38245238e257d3c5a4b286cc966c55b4b'),
 'evidence':('backtest/ndx_outer_lane_refit_evidence_research.py','5f91bb452cd58724b2dca85579ec499f5ecf177aad5dac146556418e19252151')}
CUTOFFS=('2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31')
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX');LANES=('RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE')
FLAGS=dict.fromkeys(('execution_authorized','promotion_allowed','point_in_time_verified','source_bytes_authenticated','optimization_reperformed'),False)

LINEAGE=ROOT/'backtest/ndx_history_failed_lineage_guard_20261008.py';LINEAGE_SHA='fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
PARAMETERS=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)


def require(x,m):
 if not x:raise ValueError(m)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(x):return hashlib.sha256(x).hexdigest()
def exact(a,b,m):require(enc(a)==enc(b),m)
def reference(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def valid(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and Path(r['path']).is_absolute() and r['path']==r['path'].strip() and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Explicit external reference')
def merge(s,r):
 valid(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def flags(d):
 for k in FLAGS:require(d[k] is False,'No authority '+k)
def loads(b):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate key');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def take(r,s,allowed_failed=()):
 valid(r);p=Path(r['path']);require(p.parent in allowed_failed or not (p.parent/'failure.json').exists(),'Failed evidence namespace')
 raw=p.read_bytes();require(sha(raw)==r['sha256'],'Hash the bytes actually consumed');merge(s,r);return raw
def filehash(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()

def lineage_members(sources):
 raw=LINEAGE.read_bytes();require(sha(raw)==LINEAGE_SHA,'Fixed diagnostic helper bytes')
 module=types.ModuleType('_fixed_history_failed_lineage');module.__file__=str(LINEAGE)
 exec(compile(raw,str(LINEAGE),'exec'),module.__dict__)
 return module.diagnostic_members(sources)

def guard(s,inventories=(),allowed_failed=()):
 require(filehash(SOURCE)==LOADED,'Reader drift')
 diagnostic=lineage_members(s)
 for p,h in s.items():require((p in diagnostic or Path(p).parent in allowed_failed or not (Path(p).parent/'failure.json').exists()) and filehash(p)==h,'Source drift '+p)
 for directory,names in inventories:require({p.name for p in directory.iterdir()}==set(names),'Exact attempt inventory')
def save(p,v):
 b=enc(v)
 with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==b,'Saved report bytes');return reference(p,sha(b))
def private_inspector(s):
 b=take(reference(INSPECTOR,INSPECTOR_SHA),s);m=types.ModuleType('_outer_independent_arithmetic');m.__file__=str(INSPECTOR)
 exec(compile(b,str(INSPECTOR),'exec'),m.__dict__);return m.inspect_saved_outer_result


def inspect_request(request,*,selection,history,channels,fitter,refs,prior=None):
 """Rebuild latest126 from original source slots and selected record, not producer."""
 require(request['schema']=='OUTER_LANE_CUTOFF_REFIT_REQUEST_V1','Request schema');flags(request)
 require(request['content_sha256']==sha(enc({k:v for k,v in request.items() if k!='content_sha256'})),'Request complete digest')
 coordinate=request['coordinate'];require(type(coordinate)is list and len(coordinate)==3,'Explicit coordinate')
 cutoff,mode,lane=coordinate;require(cutoff in CUTOFFS and mode in MODES and lane in LANES,'Registered48 coordinate')
 di=CUTOFFS.index(cutoff);ci=di*2+MODES.index(mode);li=LANES.index(lane)
 require(selection['schema']=='FULL_NDX_MULTIDECISION_FOUR_LANE_SELECTION_V1' and len(selection['rows'])==12,'Whole selected12 source')
 row=selection['rows'][ci];c=row['coordinate_preserved'];choice=row['choices'][li]
 exact([c['cutoff'],c['fx_mode'],choice['lane']],coordinate,'Selection coordinate')
 require(c['source_status']=='READY_FOR_SCORING' and choice['status']=='SELECTED_REQUIRES_NEW_CUTOFF_REFIT','Only selected original composition')
 chosen=choice['selected'];record=chosen['record_preserved'];idx=chosen['record_index'];require(type(idx)is int and 0<=idx<len(selection['records_preserved']),'Selected record index')
 exact(record,selection['records_preserved'][idx],'Original selected record');task=record['task']
 require(chosen['job_id']==task['job_id'] and task['cutoff']==cutoff and task['fx_mode']==mode,'Chosen job role')
 universe={r['coordinate']['security_id']:r for r in history['rows']};require(len(universe)==77,'Full77 inventory')
 sids=task['security_ids'];require(sids==sorted(set(sids)) and all(s in universe for s in sids),'Original sorted SID composition')
 selected={s:{k:universe[s]['coordinate'][k] for k in ('ticker','issuer_id','risk_chain')} for s in sids}
 pd=c['scoring_price_dates'];require(len(pd)==505 and pd[-1]==cutoff,'Original505 window')
 columns=[];evidence=[]
 for sid in sids:
  binding=channels[sid];exact(binding['reference'],universe[sid]['channel_reference'],'Original channel reference');ch=binding['channel'];d=ch['decisions'][di]
  require(ch['schema']=='MULTIDECISION_SCORING_HISTORY_CHANNEL_V1' and ch['ticker']==selected[sid]['ticker'] and d['cutoff']==cutoff,'Original source ticker/decision')
  exact(d['required_price_dates'],pd,'Full price window');off=d['price_index_start']
  require(type(off)is int and off>=0 and type(d['price_index_stop'])is int and d['price_index_stop']==off+505,'Source offsets')
  begin,end=off+378,off+504;slots=ch['return_rows'][begin:end];require(len(slots)==126,'No missing source slots');values=[];exactvalues=[]
  for i,r in enumerate(slots):
   require(r['status']=='CONDITIONAL_NUMERIC_SLOT' and r['dividends_included'] is False and r['session']==pd[379+i] and r['previous_session']==pd[378+i],'Causal saved adjacent126')
   x=r['split_only_return_float'];q=r['split_only_return_exact'];require(type(x)in(int,float) and math.isfinite(x) and x>-1 and type(q)is str and float(Fraction(q)).hex()==float(x).hex(),'Saved exact/float correspondence')
   values.append(float(x));exactvalues.append(q)
  columns.append(values);evidence.append(dict(security_id=sid,channel_reference=deepcopy(binding['reference']),decision_reference=dict(binding['reference'],json_pointer=f'/decisions/{di}'),return_index_start=begin,return_index_stop=end,exact_return_values=exactvalues,original_decision_metadata=deepcopy(d)))
 matrix=dict(dates=pd[-126:],tickers=[selected[s]['ticker'] for s in sids],returns=[list(v) for v in zip(*columns)])
 exact(request['fit_matrix'],matrix,'Independent original matrix');exact(request['source_slot_evidence'],evidence,'Exact source slots')
 previous=None;priorref=None
 if di:
  require(type(prior)is dict and prior['readback']['status']=='PASS','Actual audited adjacent evidence required')
  pr=prior['request'];pa=prior['readback'];exact(pr['coordinate'],[CUTOFFS[di-1],mode,lane],'Immediate same-lane predecessor')
  require(pa['numerical_task_id']==pr['numerical_task_id'] and pa['location_id']==pr['location_id'],'Audited predecessor identities')
  exact(pa['targets_preserved'],prior['raw_result']['result']['targets'],'Whole saved predecessor targets')
  previous={s:v['target_weight'] for s,v in sorted(pa['targets_preserved'].items())};priorref=prior['references']['readback']
 else:require(prior is None,'Initial prior explicitly absent')
 exact(request['prior_evidence_reference'],priorref,'Adjacent audit reference')
 identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=cutoff,holding_count=len(sids),selected=selected,weight_spec=task['weight_spec'],parameters=PARAMETERS,requested_previous_target_weights=previous,fit_data_sha256=sha(enc(matrix)),fitter_source_fingerprint=fitter['fitter_source_fingerprint'])
 location=dict(schema='MULTIDECISION_OUTER_REFIT_LOCATION_IDENTITY_V1',cutoff=cutoff,fx_mode=mode,lane=lane,selection_reference=dict(refs['selection'],json_pointer=f'/result/rows/{ci}/choices/{li}'),selected_scoring_job_id=task['job_id'],history_reference=refs['history'])
 exact(request['numerical_identity'],identity,'Original numeric task identity');require(request['numerical_task_id']==sha(enc(identity)),'Numerical hash')
 exact(request['location_identity'],location,'Independent lane location');require(request['location_id']==sha(enc(location)),'Location hash')
 exact(request['fitter_contract_reference'],refs['fitter'],'Fitter contract reference')
 for key in ('runtime_versions','worker_environment'):exact(request['required_'+key],fitter[key if key=='runtime_versions' else 'required_worker_environment'],'Required '+key)
 return dict(coordinate_index=di*8+MODES.index(mode)*4+li,fit_data_sha256=identity['fit_data_sha256'],original_source_slots_verified=126*len(sids))


def inspect_envelope(*,request,raw,post,refs,fitter,arithmetic,original=None):
 """Direct or referenced numerical receipt; invocation facts never cloned."""
 flags(request);flags(raw);flags(post)
 reused=post['outcome'] in ('REUSED_AUDITED_NUMERICAL_RESULT','REUSED_AUDITED_NUMERICAL_RISK_FAILURE');origin_request=request
 if reused:
  risk_reuse=post['outcome']=='REUSED_AUDITED_NUMERICAL_RISK_FAILURE'
  require(type(original)is dict and original['readback']['status']==('PASS_SAVED_RISK_FAILURE' if risk_reuse else 'PASS'),'Original independently audited direct execution')
  origin_request=original['request'];require(original['postcheck']['outcome']==('REFIT_RISK_FAILED' if risk_reuse else 'REFIT_PASSED_PENDING_INDEPENDENT_READBACK'),'No reuse alias chain')
  exact(raw,original['raw_result'],'Original raw unchanged');exact(refs['raw_result'],original['references']['raw_result'],'Original raw external ref')
  exact(request['numerical_identity'],origin_request['numerical_identity'],'Entire reused numeric identity');exact(request['fit_matrix'],origin_request['fit_matrix'],'Entire reused matrix')
  require(request['coordinate'][0]==origin_request['coordinate'][0] and request['location_id']!=origin_request['location_id'],'Same cutoff distinct registered location')
  exact(post['numerical_reuse_evidence_references'],original['references'],'Complete original reuse provenance')
 require(raw['schema']=='OUTER_LANE_CUTOFF_REFIT_RAW_RETURN_V1' and post['schema']=='OUTER_LANE_CUTOFF_REFIT_POSTCHECK_V1','Actual envelope schemas')
 for body,expected,r in ((raw,origin_request,original['references']['request'] if reused else refs['request']),(post,request,refs['request'])):
  exact(body['request_reference'],r,'Immutable request role');require(body['numerical_task_id']==expected['numerical_task_id'] and body['location_id']==expected['location_id'],'Original numeric/location identities')
 exact(post['raw_result_reference'],refs['raw_result'],'Post points to raw');exact(raw['runtime_versions'],fitter['runtime_versions'],'Actual runtime');exact(raw['worker_environment'],fitter['required_worker_environment'],'Actual hash environment')
 require(raw['call_invoked'] is True and raw['returned'] is True and type(raw['returned_call_count'])is int and raw['returned_call_count']==1 and raw['internal_optimizer_call_count'] is None and raw['error'] is None,'Successful serializable saved return only')
 require(post['current_location_call_invoked'] is (not reused) and type(post['current_location_returned_call_count'])is int and post['current_location_returned_call_count']==(0 if reused else 1),'Honest local invocation facts')
 result=arithmetic(request=origin_request,result=raw['result'],fitter_contract=fitter)
 require(result['status']=='PASS_SAVED_ARITHMETIC','Independent saved arithmetic')
 risks=result['declared_risks_passed'] is True;next_prior=result['next_prior_simplex_eligible'] is True
 expected=('REUSED_AUDITED_NUMERICAL_RESULT' if risks and next_prior else 'REUSED_AUDITED_NUMERICAL_RISK_FAILURE' if not risks else 'INVALID_REUSE') if reused else ('REFIT_RISK_FAILED' if not risks else ('REFIT_PASSED_PENDING_INDEPENDENT_READBACK' if next_prior else 'VALIDATION_FAILURE'))
 require(post['outcome']==expected,'Saved outcome consistent with independent arithmetic and separate next-prior gate')
 if expected=='VALIDATION_FAILURE':require(type(post['error']) is dict and type(post['error'].get('message')) is str,'Original next-prior validation failure preserved')
 else:require(post['error'] is None,'No hidden success error')
 return result


ROLE_PATHS={
 'selection':'data/cache/research/registered_scoring_selection_20261003_v1/raw_selection.json',
 'selection_index':'data/cache/research/registered_scoring_selection_20261003_v1/index.json',
 'selection_publication':'data/cache/research/registered_scoring_selection_20261003_v1/publication.json',
 'selection_audit':'data/cache/research/registered_scoring_selection_independent_readback_20261003_v1/independent_readback.json',
 'selection_reader':'scripts/ndx_registered_scoring_selection_independent_readback_20261003.py',
 'history':'data/cache/research/multidecision_scoring_history_20261003_v1/index.json',
 'history_audit':'data/cache/research/multidecision_scoring_history_independent_readback_20261003_v2/independent_readback.json',
 'history_reader':'scripts/ndx_multidecision_scoring_history_independent_readback_v2_20261003.py',
 'fitter':'research_contracts/multidecision_outer_cutoff_fitter_sources_20261003_v1.json'}
FIXED={'history':'ce4fd8a1a8f7f0c9c1ddd20cd4136c1c078e4aae81b37e61c9a1b0aae981ff2d',
 'history_audit':'a338dbbdfa4bc7ffdc6e83ee93bc6e55802201dd7f18049d398ae394029a5b1a',
 'history_reader':'6ae5ca2c757badd0ebfa2fa35bf3550584b4a989155e44e7d7fd120ca61f6703',
 'fitter':'ca57e56d5aa2a36949be9e056ea176d68c55dec97f6b461dfb51e00c786529d3'}


def load_inputs(refs):
 require(type(refs)is dict and set(refs)==set(ROLE_PATHS)|{'receipt_contract','outer_reader'},'Complete fixed input roles')
 expected={str(PRODUCER.resolve()):PRODUCER_SHA,str(LINEAGE):LINEAGE_SHA};docs={}
 for k,r in refs.items():
  valid(r)
  if k in ROLE_PATHS:require(Path(r['path']).resolve()==(ROOT/ROLE_PATHS[k]).resolve(),'Fixed source role '+k)
  if k in FIXED:require(r['sha256']==FIXED[k],'Fixed original source bytes '+k)
  if k=='outer_reader':exact(r,reference(SOURCE,LOADED),'Immutable reader self binding')
  b=take(r,expected)
  if not k.endswith('reader'):docs[k]=loads(b)
 contract=docs['receipt_contract'];require(contract['schema']=='OUTER_LANE_RECEIPT_INTERFACE_CONTRACT_V1' and contract['source_bytes_authenticated'] is False,'Separately published future contract')
 exact(contract['reader_reference'],refs['outer_reader'],'Contract fixes this immutable reader')
 si,sp,sa=docs['selection_index'],docs['selection_publication'],docs['selection_audit']
 require(si['schema']=='REGISTERED_SCORING_SELECTION_INDEX_V1' and sp['schema']=='REGISTERED_SCORING_SELECTION_PUBLICATION_V1' and sp['status']=='PUBLISHED_CONDITIONAL_SELECTION_ONLY','Selection successful publication')
 require(sa['schema']=='REGISTERED_SCORING_SELECTION_INDEPENDENT_READBACK_V1' and sa['status']=='PASS' and sa['reader_sha256']==refs['selection_reader']['sha256'],'Independent selection evidence')
 for d in (sp,sa):exact(d['index_reference'],refs['selection_index'],'Selection index mutual link');exact(d['raw_selection_reference'],refs['selection'],'Selection raw mutual link')
 exact(sa['publication_reference'],refs['selection_publication'],'Selection publication audit');exact(si['selection_reference'],refs['selection'],'Selection index raw')
 require(docs['selection']['schema']=='REGISTERED_SCORING_SELECTION_RAW_V1','Original selection wrapper')
 ha=docs['history_audit'];hi=docs['history']
 require(ha['schema']=='MULTIDECISION_SCORING_HISTORY_INDEPENDENT_READBACK_V2' and ha['status']=='PASS' and ha['reader_sha256']==refs['history_reader']['sha256'],'Audited original history')
 exact(ha['index_reference'],refs['history'],'History index audit')
 require(len(hi['rows'])==len(ha['rows'])==77 and len(hi['original_provenance_and_missing'])==101 and len(hi['preserved_evidence_sidecars'])==7,'Full77/101/7 history')
 for d in (si,sp,sa,hi,ha,docs['fitter']):
  for p,h in d['source_hashes'].items():merge(expected,reference(p,h))
 channels={}
 for i,(r,a) in enumerate(zip(hi['rows'],ha['rows'])):
  require(type(r['index'])is int and r['index']==i,'Original history order');exact(r['coordinate'],a['coordinate'],'Audited full coordinate');exact(r['channel_reference'],a['channel_reference'],'Audited channel ref');require(a['inspection']['status']=='PASS','Original numeric audit')
  cr=r['channel_reference'];require(ha['source_hashes'].get(cr['path'])==cr['sha256'],'History audit covers raw channel');channels[r['coordinate']['security_id']]=dict(reference=cr,channel=loads(take(cr,expected)))
 for p,h in CODES.values():take(reference(ROOT/p,h),expected)
 take(reference(INSPECTOR,INSPECTOR_SHA),expected);take(reference(PRODUCER,PRODUCER_SHA),expected)
 fitter=deepcopy(docs['fitter']);fitter['reference']=refs['fitter']
 require(len(fitter['source_hashes'])==25 and fitter['fitter_source_fingerprint']==sha(enc(fitter['source_hashes'])),'Frozen complete outer25')
 return docs,channels,fitter,expected


def load_evidence(item,sources,inventories,allow_risk_failure=False):
 require(type(item)is dict,'Explicit saved evidence roles')
 wrapped=set(item)=={'references','numerical_reuse_references'};refs=item['references'] if wrapped else item
 require(set(refs)=={'request','raw_result','postcheck','readback','reader'},'Five complete evidence anchors')
 exact(refs['reader'],reference(SOURCE,LOADED),'Only this immutable reader version')
 e={k:loads(take(refs[k],sources)) for k in ('request','raw_result','postcheck','readback')};take(refs['reader'],sources);e['references']=deepcopy(refs)
 q,a=e['request'],e['readback'];lid=q['location_id'];nid=q['numerical_task_id']
 require(Path(refs['request']['path']).resolve()==PARENT/'locations'/lid/'request.json' and Path(refs['postcheck']['path']).resolve()==PARENT/'locations'/lid/'postcheck.json','Original location paths')
 require(Path(refs['raw_result']['path']).resolve()==PARENT/'numerical'/nid/'raw_result.json' and Path(refs['readback']['path']).resolve()==OUTPUT/lid/'independent_readback.json','Original numeric/audit paths')
 failed_risk=allow_risk_failure and a['status']=='PASS_SAVED_RISK_FAILURE'
 require(a['schema']=='OUTER_LANE_CUTOFF_REFIT_INDEPENDENT_READBACK_V1' and a['status']==('PASS_SAVED_RISK_FAILURE' if failed_risk else 'PASS') and a['reader_sha256']==LOADED,'Previously accepted independent outer result')
 require(a['scope']=='SAVED_OUTER_RESULT_ARITHMETIC_AND_SOURCE_BINDING_NOT_REOPTIMIZATION' and a['prior_eligible'] is (not failed_risk),'Specific independent prior qualification')
 allowed=('REFIT_RISK_FAILED',) if failed_risk else ('REFIT_PASSED_PENDING_INDEPENDENT_READBACK','REUSED_AUDITED_NUMERICAL_RESULT')
 require(a['attempt_outcome']==e['postcheck']['outcome'] and a['attempt_outcome'] in allowed,'Specific accepted original attempt')
 flags(a)
 for key in ('request','raw_result','postcheck'):exact(a[key+'_reference'],refs[key],'Previous audit external evidence')
 require(a['numerical_task_id']==nid and a['location_id']==lid and a['raw_result_body_sha256']==sha(enc(e['raw_result']['result'])),'Previous audit full numeric body')
 exact(a['targets_preserved'],e['raw_result']['result']['targets'],'Previous entire targets')
 for r in refs.values():require(a['source_hashes'].get(r['path'])==r['sha256'] if r!=refs['readback'] else True,'Audit covers original roles')
 for obj in e.values():
  if type(obj)is dict and 'source_hashes' in obj:
   for p,h in obj['source_hashes'].items():merge(sources,reference(p,h))
 inventories.extend(((PARENT/'locations'/lid,{'request.json','postcheck.json'}),(PARENT/'numerical'/nid,{'started.json','raw_result.json'}),(OUTPUT/lid,{'started.json','independent_readback.json'})))
 if wrapped:
  require(set(item['numerical_reuse_references'])==set(refs),'Only direct origin evidence')
  e['numerical_reuse_evidence']=load_evidence(item['numerical_reuse_references'],sources,inventories)
 return e


def readback(postcheck_reference,*,execute=False,common=None):
 # Runtime refs are explicit arguments: no source mutation when an actual run appears.
 valid(postcheck_reference);valid(reference(PRODUCER,PRODUCER_SHA));require(execute is True and common is None,'Explicit independent invocation')
 path=Path(postcheck_reference['path']).resolve();require(path.name=='postcheck.json' and path.parent.parent==PARENT/'locations' and re.fullmatch('[a-f0-9]{64}',path.parent.name),'Fixed location postcheck path')
 location=path.parent;output=OUTPUT/location.name;require(not output.exists(),'Any existing reader attempt forbids retry')
 current_failed=(location,) if (location/'failure.json').exists() else ()
 sources={};post=loads(take(postcheck_reference,sources,current_failed));refs=dict(request=post['request_reference'],raw_result=post['raw_result_reference'],postcheck=postcheck_reference)
 require(Path(refs['request']['path']).resolve()==location/'request.json','Current original request')
 request=loads(take(refs['request'],sources,current_failed));require(request['location_id']==location.name,'Directory location identity')
 numeric=PARENT/'numerical'/request['numerical_task_id'];require(Path(refs['raw_result']['path']).resolve()==numeric/'raw_result.json','Fixed original numeric result path')
 raw=loads(take(refs['raw_result'],sources));startedraw=(numeric/'started.json').read_bytes();startedref=reference(numeric/'started.json',sha(startedraw));started=loads(startedraw);merge(sources,startedref)
 docs,channels,fitter,expected=load_inputs(post['input_references']);input_refs=post['input_references'];inventories=[]
 flags(post);flags(raw);flags(started)
 require(post['schema']=='OUTER_LANE_CUTOFF_REFIT_POSTCHECK_V1' and started['schema']=='OUTER_LANE_CUTOFF_REFIT_STARTED_V1' and raw['schema']=='OUTER_LANE_CUTOFF_REFIT_RAW_RETURN_V1','Saved actual three schemas')
 inv=post['coordinate_inventory'];require(type(inv)is list and len(inv)==48,'Complete48 inventory')
 for i,r in enumerate(inv):
  di,rem=divmod(i,8);mi,li=divmod(rem,4)
  require(type(r['coordinate_index'])is int and r['coordinate_index']==i,'Inventory ordinal')
  exact(r['coordinate'],[CUTOFFS[di],MODES[mi],LANES[li]],'Original48 order')
  choice=docs['selection']['result']['rows'][di*2+mi]['choices'][li]
  if choice['selected'] is None:
   require(r['status']==choice['status'] and r['numerical_task_id'] is None and r['location_id'] is None,'Blocked coordinate never acquires target identity')
 current=inv[CUTOFFS.index(request['coordinate'][0])*8+MODES.index(request['coordinate'][1])*4+LANES.index(request['coordinate'][2])]
 require(current['numerical_task_id']==request['numerical_task_id'] and current['location_id']==request['location_id'],'Current inventory task identity')
 prior_items=post['prior_evidence_references'];require(type(prior_items)is list,'Complete explicit prior reference list')
 priors=[load_evidence(item,expected,inventories) for item in prior_items];by={}
 for e in priors:
  key=tuple(e['request']['coordinate']);require(key not in by,'No duplicate prior coordinate');by[key]=e
 def project(q):
  di=CUTOFFS.index(q['coordinate'][0]);prior=by.get((CUTOFFS[di-1],q['coordinate'][1],q['coordinate'][2])) if di else None
  return inspect_request(q,selection=docs['selection']['result'],history=docs['history'],channels=channels,fitter=fitter,refs=input_refs,prior=prior)
 for e in priors:project(e['request'])
 provenance=project(request);original=None
 if post['outcome'] in ('REUSED_AUDITED_NUMERICAL_RESULT','REUSED_AUDITED_NUMERICAL_RISK_FAILURE'):
  original=load_evidence(post['numerical_reuse_evidence_references'],expected,inventories,allow_risk_failure=True);project(original['request'])
 merge(expected,refs['request']);raw_expected=deepcopy(expected)
 if original is None:
  exact(raw['source_hashes'],raw_expected,'Independent complete raw source closure')
  exact(started['source_hashes'],raw_expected,'Original started source closure')
  exact(started['request_reference'],refs['request'],'Started exact request')
  for obj in (started,raw):
   exact(obj['input_references'],input_refs,'Original full input roles');exact(obj['prior_evidence_references'],prior_items,'Original prior inventory')
   exact(obj['coordinate_inventory'],inv,'Entire original dispatch snapshot')
  require(started['location_id']==request['location_id'] and started['numerical_task_id']==request['numerical_task_id'],'Started call identity')
  exact(started['runtime_versions'],raw['runtime_versions'],'Started runtime');exact(started['worker_environment'],raw['worker_environment'],'Started environment')
  merge(expected,refs['raw_result'])
 exact(post['source_hashes'],expected,'Complete post source closure, no missing or added claims')
 for p,h in expected.items():merge(sources,reference(p,h))
 names={'request.json','postcheck.json'}|({'failure.json'} if current_failed else set())
 numericnames={'started.json','raw_result.json'}
 if raw.get('original_return_is_json') is False:
  dr=raw['diagnostic_reference'];valid(dr);require(Path(dr['path']).resolve()==numeric/'unserializable_return.bin','Exact opaque serialization diagnostic role')
  take(dr,sources);numericnames.add('unserializable_return.bin')
 else:require('diagnostic_reference' not in raw,'No invented opaque diagnostic')
 inventories.extend(((location,names),(numeric,numericnames)))
 for directory in (location,numeric):
  for extra in ('failure.json','unserializable_return.bin'):
   if (directory/extra).exists():b=(directory/extra).read_bytes();merge(sources,reference(directory/extra,sha(b)))
 guard(sources,inventories,current_failed);arithmetic=private_inspector(sources)
 output.parent.mkdir(parents=True,exist_ok=True);output.mkdir(exist_ok=False)
 ownstarted=save(output/'started.json',dict(schema='OUTER_LANE_REFIT_READBACK_STARTED_V1',postcheck_reference=postcheck_reference,reader_sha256=LOADED,source_hashes=sources,**FLAGS))
 try:
  inspection=None;technical_error=None
  if raw['returned'] is True and raw['error'] is None and type(raw['result'])is dict:
   try:inspection=inspect_envelope(request=request,raw=raw,post=post,refs=refs,fitter=fitter,arithmetic=arithmetic,original=original)
   except (ValueError,KeyError,TypeError) as e:
    require(post['outcome']=='VALIDATION_FAILURE' and current_failed and type(post['error'])is dict,'Unexpected invalid success evidence')
    technical_error=dict(saved_error=deepcopy(post['error']),independent_error=dict(type=type(e).__name__,message=str(e)))
   if inspection is not None and 'saved_result_inspection' in post:exact(post['saved_result_inspection'],inspection,'Original saved independent arithmetic copy')
  else:
   require(original is None and post['outcome'] in ('NUMERICAL_EXCEPTION','VALIDATION_FAILURE') and type(post['error'])is dict,'Explicit technical failure only')
   require(type(raw['call_invoked'])is bool and type(raw['returned'])is bool and type(raw['returned_call_count'])is int and raw['returned_call_count']==int(raw['returned']),'Actual attempted call facts')
   technical_error=deepcopy(post['error'])
  accepted=inspection is not None and inspection['declared_risks_passed'] is True and inspection['next_prior_simplex_eligible'] is True and not current_failed
  status='PASS' if accepted else ('PASS_SAVED_RISK_FAILURE' if inspection is not None and inspection['declared_risks_passed'] is False else 'TECHNICAL_FAILURE_RECORDED_NOT_PRIOR')
  merge(sources,reference(SOURCE,LOADED));merge(sources,ownstarted)
  report=dict(schema='OUTER_LANE_CUTOFF_REFIT_INDEPENDENT_READBACK_V1',status=status,scope='SAVED_OUTER_RESULT_ARITHMETIC_AND_SOURCE_BINDING_NOT_REOPTIMIZATION',request_reference=refs['request'],raw_result_reference=refs['raw_result'],postcheck_reference=refs['postcheck'],reader_sha256=LOADED,reader_reference=reference(SOURCE,LOADED),numerical_task_id=request['numerical_task_id'],location_id=request['location_id'],targets_preserved=deepcopy(raw['result']['targets']) if inspection is not None else None,raw_result_body_sha256=sha(enc(raw['result'])) if raw['returned'] else None,arithmetic_inspection=inspection,source_projection_inspection=provenance,technical_error=technical_error,attempt_outcome=post['outcome'],prior_eligible=accepted,source_hashes=sources,original_numeric_started_reference=startedref,started_reference_externally_anchored=False,**FLAGS)
  report.update(coordinate_inventory_preserved=deepcopy(inv),coordinate_inventory_validation_scope='ALL48_REGISTERED_ORDER_AND_BLOCKED_ROWS_PLUS_CURRENT_REQUEST_IDENTITY',other_coordinate_numerical_ids_and_statuses_independently_verified=False)
  out=save(output/'independent_readback.json',report);guard(sources,inventories,current_failed)
  require(filehash(ownstarted['path'])==ownstarted['sha256'] and filehash(out['path'])==out['sha256'] and {p.name for p in output.iterdir()}=={'started.json','independent_readback.json'},'Final own inventory and bytes')
  return out
 except BaseException as e:
  save(output/'failure.json',dict(status='FAILED_NO_RETRY',error=dict(type=type(e).__name__,message=str(e)),postcheck_reference=postcheck_reference,**FLAGS));raise


if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--postcheck',required=True);parser.add_argument('--postcheck-sha256',required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
 print(json.dumps(readback(reference(args.postcheck,args.postcheck_sha256),execute=args.execute)))
