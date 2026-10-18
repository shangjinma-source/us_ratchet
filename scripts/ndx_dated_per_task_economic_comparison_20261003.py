"""Per-task dated diagnostics; shared controls are immutable references."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_dated_per_task_comparison_research.py';CORE_SHA='3ad01adc51e1befbb62e0af211070d6fc4293660903b66d75a33fcdacaf31723'
OUTPUT=ROOT/'data/cache/research/dated_per_task_economic_comparison_20261003_v1'
TASK='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
BOUND={
 'incumbent_account':('data/cache/research/dated_account_execution_20261003_v1/incumbent/raw.json','ed060c2cc58f0465c7e47f30e0d5315b4179c85da543e305b2fbd12f53ca7d05'),
 'account_audit':('DYNAMIC_DATED_FIRST_ACCOUNTS_INDEPENDENT_READBACK_20261003.json','64c68233d31913422ef7d3f823602f3f1ecd85c2309184f7cf4cb2d623d4af7a'),
 'account_reader':('scripts/ndx_dated_first_accounts_independent_review_20261003.py','54558b47e85a1364b10962f1ac6f25815922e44aadfef68850f22cea8a8fc281'),
 'continuous':('data/cache/research/dated_continuous_weight_diagnostic_20261003_v1/diagnostic.json','bb81bc97c9bb5564afeab9eed4a1421e40fe5274ae29807ce9994bd7b70b8c7f'),
 'continuous_publication':('data/cache/research/dated_continuous_weight_diagnostic_20261003_v1/publication.json','ad10068b3b2efa98ce13cdef62c52d096c085680343078a8c429daf5225144d8'),
 'continuous_audit':('DYNAMIC_DATED_CONTINUOUS_INDEPENDENT_READBACK_20261003.json','3dca84ea418360f1c039c437614c0887966c665cdfbf4c5c0c99484659d42057'),
 'continuous_reader':('scripts/ndx_dated_continuous_independent_readback_20261003.py','23e527a022ea02673db5367c4ff5c4f6771e54b28a74f1ada66336327fe09ebf'),
 'nav_metrics':('data/cache/research/same_window_nav_reference_metrics_20261003_v1/metrics.json','2f2d072190115b38de2776b8ba33b50372a8546b2c858766751b79915c78dcfa'),
 'nav_publication':('data/cache/research/same_window_nav_reference_metrics_20261003_v1/publication.json','338ae747c8d79ac70050742ce7b43e723c3d608f59776175186ab16d4fd08b5a'),
 'nav_audit':('DYNAMIC_SAME_WINDOW_NAV_REFERENCE_INDEPENDENT_READBACK_20261003.json','92b73cc2c812f044e182c5ee7d966bdb245dfd531b01bd28ea1b0e11313a7337'),
 'nav_reader':('scripts/ndx_same_window_nav_metrics_independent_review_20261003.py','0c2b32ce82a64378331a7a76d0c632a129b00f3d559029903c694ffce5a943f4')}
FLAGS=dict.fromkeys(('account_executed','fit_performed','old_audit_repeated','raw_prices_redecoded','point_in_time_verified','promotion_allowed','execution_authorized','winner_selected','formal_comparison_passed','formal_noninferiority_verified','cohort_statistics_computed','future_independent_oos','untouched_holdout','full_transitive_source_closure_reverified'),False)


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(b):return hashlib.sha256(b).hexdigest()
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encode(a)==encode(b),message)
def ref(role):return dict(path=str(ROOT/BOUND[role][0]),sha256=BOUND[role][1])
def same_ref(a,b,message):require(set(a)==set(b)=={'path','sha256'} and Path(a['path'])==Path(b['path']) and a['sha256']==b['sha256'],message)


def loads(blob):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON '+v)
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=invalid)


def merge(sources,path,h):require(path not in sources or sources[path]==h,'Source conflict');sources[path]=h

def read(r,sources):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['sha256']) is str and len(r['sha256'])==64,'Exact external reference')
    path=Path(r['path']);blob=path.read_bytes();require(sha(blob)==r['sha256'],'Hard byte binding');merge(sources,str(path),r['sha256']);return loads(blob)


def guard(sources):
    merged=dict(sources);merge(merged,str(SOURCE),LOADED_SHA);merge(merged,str(CORE),CORE_SHA);merge(merged,str(HELPER),HELPER_SHA)
    for path,h in merged.items():require(type(h) is str and sha(Path(path).read_bytes())==h,'Source drift or pending '+path)


ACCOUNT_ROOT=ROOT/'data/cache/research/dated_account_execution_20261003_v1/candidates'
CONTINUOUS_ROOT=ROOT/'data/cache/research/dated_per_task_continuous_weight_diagnostic_20261003_v1'
INPUT_ROOT=ROOT/'data/cache/research/dated_account_inputs_20261003_v1'
NEW_READERS={
 'account':('scripts/ndx_dated_account_independent_readback_20261003.py','2e412e1dfe66d858656ed68c52ed5a2d976b84c8e7306612b4dc66b60ce0249a'),
 'continuous':('scripts/ndx_dated_per_task_continuous_independent_readback_20261003.py','4a947e8c6f0d96ddae74bb87fc0a5a8dbb691865d550e543e5ecb9311b20e03a')}
HELPER=ROOT/'backtest/ndx_dated_economic_comparison_research.py'
HELPER_SHA='6216723e1d906ba689be58aa9eaee4f6b43dd2711ad2ed681566a1c7c3c5ef1b'
_CACHE={}

def check_task(task_id):
    require(type(task_id) is str and len(task_id)==64 and all(c in '0123456789abcdef' for c in task_id),'Canonical task ID')
    require(task_id!=TASK,'First comparison already completed; reuse saved external result')
    require(not (OUTPUT/task_id).exists(),'Immutable per-task comparison exists; no retry')

def validate_common(docs):
    audit=docs['account_audit'];require(audit['schema']=='DATED_FIRST_ACCOUNTS_INDEPENDENT_ACCOUNTING_READBACK_V1' and audit['status']=='PASS' and audit['reader_sha256']==ref('account_reader')['sha256'],'Shared integer audit')
    rows=[r for r in audit['rows'] if r['track']=='incumbent'];require(len(rows)==1 and rows[0]['status']=='PASS' and type(rows[0]['days']) is int and rows[0]['days']==127,'Unique full control path')
    same_ref(rows[0]['raw_reference'],ref('incumbent_account'),'Shared audited raw')
    raw=docs['incumbent_account'];require(raw['schema']=='DATED_ACCOUNT_RAW_V1' and raw['status']=='ACCOUNT_RETURNED' and raw['error'] is None and type(raw['returned_account_count']) is int and raw['returned_account_count']==1,'Shared saved account')
    for role,parent,field in [('continuous','continuous','diagnostic_reference'),('nav','nav_metrics','metrics_reference')]:
        pub=docs[role+'_publication'];d=docs[parent];a=docs[role+'_audit']
        same_ref(pub[field],ref(parent),'Shared publication target');exact(pub['source_hashes'],d['source_hashes'],'Shared publication sources');require(a['status']=='PASS' and a['reader_sha256']==ref(role+'_reader')['sha256'],'Shared audit reader')
        if role=='continuous':
            require(a['schema']=='DATED_CONTINUOUS_INDEPENDENT_READBACK_V1','Shared continuous audit');same_ref(a['diagnostic_reference'],ref(parent),'Shared continuous target');same_ref(a['publication_reference'],ref(role+'_publication'),'Shared continuous receipt')
        else:require(a['schema']=='SAME_WINDOW_NAV_REFERENCE_INDEPENDENT_READBACK_V1' and a['metrics_sha256']==ref(parent)['sha256'] and a['publication_sha256']==ref(role+'_publication')['sha256'],'Shared NAV audit')
    return rows[0]

def load_common():
    sources={str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA,str(HELPER):HELPER_SHA};guard(sources);docs={}
    for role in BOUND:
        if role.endswith('_reader'):
            r=ref(role);require(sha(Path(r['path']).read_bytes())==r['sha256'],'Shared reader bytes');merge(sources,r['path'],r['sha256'])
        else:docs[role]=read(ref(role),sources)
    for relative,h in NEW_READERS.values():require(sha((ROOT/relative).read_bytes())==h,'Task reader bytes');merge(sources,str(ROOT/relative),h)
    validate_common(docs)
    for role,name in [('incumbent_account','raw.json'),('continuous','diagnostic.json'),('nav_metrics','metrics.json')]:
        folder=Path(ref(role)['path']).parent
        expected={'started.json','raw.json','postcheck.json'} if role=='incumbent_account' else {'started.json',name,'publication.json'}
        require({p.name for p in folder.iterdir()}==expected,'Successful shared namespace only')
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Fresh comparison core');core=types.ModuleType('_new_dated_comparison');core.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),core.__dict__);require(Path(core.__file__)==CORE,'Core path')
    guard(sources);handle=dict(immutable_control_account_reference=ref('incumbent_account'),immutable_control_continuous_reference=dict(ref('continuous'),json_pointer='/tracks/incumbent'),immutable_nav_reference=ref('nav_metrics'));_CACHE[id(handle)]=(handle,docs,sources,core);return handle

def validate_candidate(task_id,docs,refs,common):
    ca=docs['account_audit'];xa=docs['continuous_audit'];raw=docs['raw'];post=docs['postcheck'];d=docs['continuous'];pub=docs['continuous_publication'];inputs=docs['inputs']
    require(ca['schema']=='DATED_ACCOUNT_INDEPENDENT_READBACK_V1' and ca['status']=='PASS' and ca['numerical_task_id']==task_id and ca['reader_sha256']==NEW_READERS['account'][1],'Audited candidate account')
    require(xa['schema']=='DATED_PER_TASK_CONTINUOUS_INDEPENDENT_READBACK_V1' and xa['status']=='PASS' and xa['numerical_task_id']==task_id and xa['reader_sha256']==NEW_READERS['continuous'][1],'Audited candidate continuous')
    for audit in (ca,xa):
        for flag in ('point_in_time_verified','promotion_allowed','fit_performed'):require(audit[flag] is False,'No authority upgrade')
    for key in ('raw','postcheck'):same_ref(ca[key+'_reference'],refs[key],'Audited account evidence')
    same_ref(post['raw_reference'],refs['raw'],'Post/raw binding');same_ref(raw['started_reference'],ca['started_reference'],'Raw/started binding')
    same_ref(ca['inputs_reference'],refs['inputs'],'Account input');same_ref(xa['inputs_reference'],refs['inputs'],'Continuous same input');same_ref(ca['input_readback_reference'],xa['input_readback_reference'],'Both input audits')
    same_ref(xa['diagnostic_reference'],refs['continuous'],'Continuous audit target');same_ref(xa['publication_reference'],refs['continuous_publication'],'Continuous audit publication');same_ref(pub['diagnostic_reference'],refs['continuous'],'Continuous published target');exact(pub['source_hashes'],d['source_hashes'],'Continuous publication map')
    require(d['schema']=='SOURCE_BOUND_DATED_PER_TASK_CONTINUOUS_DIAGNOSTIC_V1' and d['numerical_task_id']==task_id,'Candidate-only continuous schema');same_ref(d['input_references']['inputs'],refs['inputs'],'Continuous original inputs')
    exact(d['immutable_control_reference'],dict(ref('continuous'),json_pointer='/tracks/incumbent'),'Only original shared continuous');same_ref(d['immutable_control_readback_reference'],ref('continuous_audit'),'Shared continuous audit')
    exact(ca['shared_incumbent_result_preserved'],validate_common(common),'Same saved incumbent audit row');exact(ca['shared_incumbent_audit_reference'],dict(ref('account_audit'),json_pointer='/rows/1'),'Same shared account audit')
    require(inputs['schema']=='DATED_ACCOUNT_INPUT_DOCUMENT_V1' and inputs['inputs']['original_task']['numerical_task_id']==task_id,'Exact saved task inputs');task=inputs['inputs']['original_task'];require(task['numerical_identity']['cutoff']=='2026-03-20' and task['numerical_identity']['requested_previous_target_weights'] is None,'Dated weights only')
    exact(d['original_task_preserved'],task,'Same continuous task')
    outcome=ca['attempt_outcome'];require(outcome in ('ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING','NOT_EXECUTED_NONPOSITIVE_TARGET'),'Technical failures cannot become economic results')
    require(post['status']==outcome and post['error'] is None and raw['error'] is None,'Technical account status')
    if outcome=='NOT_EXECUTED_NONPOSITIVE_TARGET':
        require(raw['status']==outcome and raw['account'] is None and ca['accounting_verified'] is False and ca['accounting'] is None,'Missing integer stays missing')
        for key in ('engine_call_attempt_count','returned_account_count'):require(type(raw[key]) is int and raw[key]==0,'No blocked account execution')
    else:
        require(raw['status']=='ACCOUNT_RETURNED' and type(raw['account']) is dict and ca['accounting_verified'] is True,'Actual returned integer account')
        for key in ('engine_call_attempt_count','returned_account_count'):require(type(raw[key]) is int and raw[key]==1,'One returned execution')
    return outcome

def load_candidate(task_id,account_readback_reference,continuous_readback_reference,sources):
    af=ACCOUNT_ROOT/task_id;cf=CONTINUOUS_ROOT/task_id
    require(Path(account_readback_reference['path'])==af/'independent_accounting.json' and Path(continuous_readback_reference['path'])==cf/'independent_readback.json','Fixed external audit paths')
    require({p.name for p in af.iterdir()}=={'started.json','raw.json','postcheck.json','independent_accounting.json'},'Successful audited integer namespace')
    require({p.name for p in cf.iterdir()}=={'started.json','diagnostic.json','publication.json','independent_readback.json'},'Successful audited continuous namespace')
    refs=dict(account_audit=deepcopy(account_readback_reference),continuous_audit=deepcopy(continuous_readback_reference));docs={k:read(v,sources) for k,v in refs.items()}
    for role,r in [('raw',docs['account_audit']['raw_reference']),('postcheck',docs['account_audit']['postcheck_reference']),('inputs',docs['account_audit']['inputs_reference']),('continuous',docs['continuous_audit']['diagnostic_reference']),('continuous_publication',docs['continuous_audit']['publication_reference'])]:refs[role]=deepcopy(r);docs[role]=read(r,sources)
    for role,expected in [('raw',af/'raw.json'),('postcheck',af/'postcheck.json'),('inputs',INPUT_ROOT/task_id/'inputs.json'),('continuous',cf/'diagnostic.json'),('continuous_publication',cf/'publication.json')]:require(Path(refs[role]['path'])==expected,'Exact task source path')
    require({p.name for p in (INPUT_ROOT/task_id).iterdir()}=={'started.json','inputs.json','publication.json','independent_readback.json'},'Audited input namespace')
    return docs,refs


def project_inputs(task_id,docs,refs,common):
    outcome=validate_candidate(task_id,docs,refs,common)
    available=outcome=='ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING'
    status=dict(status='AVAILABLE' if available else 'NOT_EXECUTED_NONPOSITIVE_TARGET',reason=None if available else 'Saved independently audited NOT_EXECUTED_NONPOSITIVE_TARGET; original zero slots retained, no integer path generated',evidence_reference=dict(refs['account_audit'],json_pointer='/attempt_outcome'))
    return dict(candidate_account=docs['raw']['account'] if available else None,candidate_integer_status=status,incumbent_account=common['incumbent_account']['account'],candidate_continuous=docs['continuous']['candidate'],incumbent_continuous=common['continuous']['tracks']['incumbent'],nav_metrics=common['nav_metrics']['metrics'],source_references=dict(candidate_integer=dict(refs['raw'],json_pointer='/account') if available else None,incumbent_integer=dict(ref('incumbent_account'),json_pointer='/account'),candidate_continuous=dict(refs['continuous'],json_pointer='/candidate'),incumbent_continuous=dict(ref('continuous'),json_pointer='/tracks/incumbent'),nav_metrics=dict(ref('nav_metrics'),json_pointer='/metrics')))

def assemble(task_id,docs,refs,common,core):
    args=project_inputs(task_id,docs,refs,common)
    result=core.compare_per_task_paths(**args)
    require(result['schema']=='DATED_PER_TASK_PARTIAL_ECONOMIC_DIAGNOSTIC_V1' and result['status'] in ('ALL_FOUR_SAVED_TRACKS_DIAGNOSTIC_ONLY','PARTIAL_CANDIDATE_INTEGER_UNAVAILABLE'),'New diagnostic schema only')
    require(result['formal_comparison_passed'] is False and result['winner_selected'] is False and result['integer_missing_replaced_with_cash'] is False,'No economic or authority invention')
    return dict(schema='SOURCE_BOUND_DATED_PER_TASK_ECONOMIC_COMPARISON_V1',numerical_task_id=task_id,comparison=result,input_references=deepcopy(refs),shared_references={k:ref(k) for k in BOUND},independent_audits_preserved={k:deepcopy(docs[k]) for k in ('account_audit','continuous_audit')},original_task_preserved=deepcopy(docs['inputs']['inputs']['original_task']),original_input_limitations=deepcopy(docs['inputs']['inputs']['limitations']),original_provenance_and_missing=deepcopy(docs['inputs']['original_provenance_and_missing']),preserved_evidence_sidecars=deepcopy(docs['inputs']['preserved_evidence_sidecars']),shared_account_reexecuted=False,shared_continuous_recomputed=False,comparison_core_call_count=1,**FLAGS)

def save(path,value):
    blob=encode(value)
    with path.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==blob,'Written evidence changed');return dict(path=str(path),sha256=sha(blob))

def run(task_id,account_readback_reference,continuous_readback_reference,*,execute=False,common=None):
    require(type(execute) is bool and execute,'Explicit execute=True required');check_task(task_id)
    if common is None:common=load_common()
    stored=_CACHE.get(id(common));require(stored is not None and stored[0] is common,'Issued common handle only')
    _,shared,base_sources,core=stored
    exact(common,dict(immutable_control_account_reference=ref('incumbent_account'),immutable_control_continuous_reference=dict(ref('continuous'),json_pointer='/tracks/incumbent'),immutable_nav_reference=ref('nav_metrics')),'Common handle unchanged')
    sources=dict(base_sources);guard(sources);docs,refs=load_candidate(task_id,account_readback_reference,continuous_readback_reference,sources)
    validate_candidate(task_id,docs,refs,shared);guard(sources);check_task(task_id);folder=OUTPUT/task_id;folder.mkdir(parents=True,exist_ok=False)
    try:
        save(folder/'started.json',dict(schema='DATED_PER_TASK_ECONOMIC_COMPARISON_STARTED_V1',numerical_task_id=task_id,input_references=refs,shared_references={k:ref(k) for k in BOUND},planned_comparison_core_call_count=1,source_hashes=sources,**FLAGS))
        value=assemble(task_id,docs,refs,shared,core);value['source_hashes']=sources;guard(sources)
        out=save(folder/'comparison.json',value);guard(sources);require({p.name for p in folder.iterdir()}=={'started.json','comparison.json'},'Unexpected output before receipt')
        pub=save(folder/'publication.json',dict(schema='DATED_PER_TASK_ECONOMIC_COMPARISON_PUBLICATION_V1',status='PUBLISHED_SINGLE_PATH_DIAGNOSTIC_ONLY',comparison_reference=out,source_hashes=sources,**FLAGS));guard(sources)
        require({p.name for p in folder.iterdir()}=={'started.json','comparison.json','publication.json'},'Unexpected publication files')
        for r in (out,pub):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final output drift')
        return out
    except Exception as error:save(folder/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),retry_allowed=False));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task-id',required=True);p.add_argument('--account-readback-sha256',required=True);p.add_argument('--continuous-readback-sha256',required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    print(json.dumps(run(a.task_id,dict(path=str(ACCOUNT_ROOT/a.task_id/'independent_accounting.json'),sha256=a.account_readback_sha256),dict(path=str(CONTINUOUS_ROOT/a.task_id/'independent_readback.json'),sha256=a.continuous_readback_sha256),execute=a.execute)))
