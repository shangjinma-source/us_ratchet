"""First dated single-path diagnostics from externally audited saved outputs."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_dated_economic_comparison_research.py';CORE_SHA='6216723e1d906ba689be58aa9eaee4f6b43dd2711ad2ed681566a1c7c3c5ef1b'
OUTPUT=ROOT/'data/cache/research/dated_first_economic_comparison_20261003_v1'
TASK='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
BOUND={
 'candidate_account':('data/cache/research/dated_account_execution_20261003_v1/candidates/'+TASK+'/raw.json','00de88eb4c7c7c74e6d97df166dd6cda97eb168b1e58f20663907c749d286606'),
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
    merged=dict(sources);merge(merged,str(SOURCE),LOADED_SHA);merge(merged,str(CORE),CORE_SHA)
    for path,h in merged.items():require(sha(Path(path).read_bytes())==h,'Source drift '+path)


def project_inputs(docs):
    audit=docs['account_audit'];require(audit['schema']=='DATED_FIRST_ACCOUNTS_INDEPENDENT_ACCOUNTING_READBACK_V1' and audit['status']=='PASS' and audit['reader_sha256']==ref('account_reader')['sha256'],'Independent integer account audit')
    require([r['track'] for r in audit['rows']]==['candidate','incumbent'],'Both audited tracks in fixed roles')
    for k in ('account_reexecution_performed','old_audit_repeated','point_in_time_verified','promotion_allowed','formal_cohort_verified'):require(audit[k] is False,'No account audit authority')
    for row in audit['rows']:
        role=row['track'];raw=docs[role+'_account'];post=docs[role+'_postcheck'];started=docs[role+'_started']
        require(row['status']=='PASS' and type(row['days']) is int and row['days']==127,'Full audited path')
        same_ref(row['raw_reference'],ref(role+'_account'),'Audited raw bytes');same_ref(post['raw_reference'],ref(role+'_account'),'Post raw bytes');same_ref(post['started_reference'],raw['started_reference'],'Started raw linkage')
        require(raw['schema']=='DATED_ACCOUNT_RAW_V1' and raw['status']=='ACCOUNT_RETURNED' and type(raw['engine_call_attempt_count']) is int and raw['engine_call_attempt_count']==1 and type(raw['returned_account_count']) is int and raw['returned_account_count']==1 and raw['error'] is None,'One returned account')
        require(post['schema']=='DATED_ACCOUNT_POSTCHECK_V1' and post['status']=='ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING' and post['error'] is None and post['track']==role and post['numerical_task_id']==TASK,'Original postcheck')
        require(started['schema']=='DATED_ACCOUNT_STARTED_V1' and started['state']['track']==role and started['state']['numerical_task_id']==TASK,'Original started track')
        same_ref(started['state']['inputs_reference'],row['input_reference'],'Account input crosslink')
        same_ref(row['input_reference'],docs['continuous']['input_references']['inputs'],'Continuous/int same prepared input')
        exact(raw['source_hashes'],started['state']['source_hashes'],'Raw sources preserved')
    require(audit['rows'][0]['common_incumbent_identity']==audit['rows'][1]['common_incumbent_identity'],'Shared original control contract')
    for role,parent_role,field in [('continuous','continuous','diagnostic_reference'),('nav','nav_metrics','metrics_reference')]:
        d=docs[parent_role];pub=docs[role+'_publication'];a=docs[role+'_audit']
        same_ref(pub[field],ref(parent_role),'Publication payload');exact(pub['source_hashes'],d['source_hashes'],'Publication sources')
        require(pub['schema']==('DATED_CONTINUOUS_DIAGNOSTIC_PUBLICATION_V1' if role=='continuous' else 'SAME_WINDOW_NAV_REFERENCE_METRICS_PUBLICATION_V1') and pub['status']==('PUBLISHED_CONDITIONAL_FRACTIONAL_DIAGNOSTIC_NOT_ACCOUNT' if role=='continuous' else 'PUBLISHED_RETROSPECTIVE_EXTERNAL_REFERENCE_ONLY') and a['status']=='PASS' and a['reader_sha256']==ref(role+'_reader')['sha256'],'Successful audited parent')
        if role=='continuous':
            require(a['schema']=='DATED_CONTINUOUS_INDEPENDENT_READBACK_V1','Continuous independent schema');same_ref(a['diagnostic_reference'],ref('continuous'),'Continuous audit');same_ref(a['publication_reference'],ref('continuous_publication'),'Continuous receipt audit')
        else:require(a['schema']=='SAME_WINDOW_NAV_REFERENCE_INDEPENDENT_READBACK_V1' and a['metrics_sha256']==ref('nav_metrics')['sha256'] and a['publication_sha256']==ref('nav_publication')['sha256'],'NAV independent schema/binding')
    require(docs['continuous']['original_task_preserved']['numerical_task_id']==TASK,'Same dated task')
    return dict(candidate_account=deepcopy(docs['candidate_account']['account']),incumbent_account=deepcopy(docs['incumbent_account']['account']),continuous_document=deepcopy(docs['continuous']),nav_metrics=deepcopy(docs['nav_metrics']['metrics']),source_references={k:ref(k) for k in ('candidate_account','incumbent_account','continuous','nav_metrics')})


def load_inputs():
    sources={str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA};guard(sources);docs={}
    for role in BOUND:
        if role.endswith('_reader'):
            r=ref(role);blob=Path(r['path']).read_bytes();require(sha(blob)==r['sha256'],'Reader source pin');merge(sources,r['path'],r['sha256'])
        else:docs[role]=read(ref(role),sources)
    for row in docs['account_audit']['rows']:
        role=row['track'];require(role in ('candidate','incumbent'),'Audit role')
        docs[role+'_postcheck']=read(row['postcheck_reference'],sources)
        docs[role+'_started']=read(docs[role+'_account']['started_reference'],sources)
        require({p.name for p in Path(ref(role+'_account')['path']).parent.iterdir()}=={'started.json','raw.json','postcheck.json'},'Immutable completed account namespace')
    for role,filename in [('continuous','diagnostic.json'),('nav_metrics','metrics.json')]:require({p.name for p in Path(ref(role)['path']).parent.iterdir()}=={'started.json',filename,'publication.json'},'Successful immutable source namespace')
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Fresh core');core=types.ModuleType('_dated_economic_core');core.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),core.__dict__)
    guard(sources);return docs,sources,core


def save(path,value):
    blob=encode(value)
    with path.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==blob,'Written evidence changed');return dict(path=str(path),sha256=sha(blob))


def run(*,execute=False):
    require(type(execute) is bool and execute,'Explicit execute=True required');require(not OUTPUT.exists(),'Immutable comparison exists; no retry')
    docs,sources,core=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(input_references={k:ref(k) for k in BOUND},source_hashes=sources,**FLAGS))
        args=project_inputs(docs);result=core.compare_dated_paths(**args)
        require(result['schema']=='DATED_SAME_WINDOW_ECONOMIC_DIAGNOSTIC_V1' and result['status']=='SINGLE_PATH_DIAGNOSTIC_ONLY' and result['formal_comparison_passed'] is False and result['winner_selected'] is False,'Only diagnostic result')
        document=dict(schema='SOURCE_BOUND_DATED_FIRST_ECONOMIC_COMPARISON_V1',comparison=result,independent_audits_preserved={k:deepcopy(docs[k]) for k in ('account_audit','continuous_audit','nav_audit')},input_references={k:ref(k) for k in BOUND},source_hashes=sources,**FLAGS)
        guard(sources);output=save(OUTPUT/'comparison.json',document);guard(sources)
        receipt=save(OUTPUT/'publication.json',dict(schema='DATED_FIRST_ECONOMIC_COMPARISON_PUBLICATION_V1',status='PUBLISHED_SINGLE_PATH_DIAGNOSTIC_ONLY',comparison_reference=output,source_hashes=sources,**FLAGS))
        guard(sources)
        for r in (output,receipt):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Publication readback changed')
        return output
    except Exception as error:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',type=type(error).__name__,message=str(error),retry_allowed=False));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(run(execute=parser.parse_args().execute)))
