"""Metadata-only economic batch verification; no engine, fitter or numerical replay."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib,json,os
from pathlib import Path

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESULT_PATH=ROOT/'data/cache/research/dated_economic_batch_20261003_v1/result.json'
RESULT_SHA='6aaa8963043b54ad5de9a380302b3a7ae2007830a41de870a7947ce236d74218'
OUTPUT=ROOT/'data/cache/research/dated_economic_batch_independent_readback_20261003_v1'
FULL=6222659648236112670
STAGES=('inputs','input_readback','account_postcheck','account_readback','continuous','continuous_readback')
FIRST='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
INITIAL_IDS={FIRST,'530200b2ffe3b841c27f62dc68c5440c9b0f1cab7e7249592eaebae304713a68','046b0ad4dc7a207abf15e72ac1786848ad3a2a339515edc3b98e479bfb3678b9'}
BOUND={
 'summary':('data/cache/research/dated_batch_summary_20261003_v1/summary.json','406922de9ffc292417d4b495af30691833f5bb8c2b5b60449c010d5178acb378'),
 'summary_publication':('data/cache/research/dated_batch_summary_20261003_v1/publication.json','23480ca1d99000206344d0176e555b2f16ba12542f2784002854652b7720782b'),
 'summary_audit':('DYNAMIC_DATED_BATCH_SUMMARY_INDEPENDENT_READBACK_20261003.json','d60fefc9121db9a14667d0994cd8e4ee58e1d6c62135f042234396d2212b555a'),
 'initial':('research_contracts/dated_initial_economic_completed_20261003_v1.json','1b5f549979e82653f2448d75ff48a6fa8a79497af1fcbe5066b77a2bcb48ffec'),
 'driver':('scripts/ndx_dated_economic_batch_20261003.py','7f097335e90d99b606ce8e96dfd36553af5354ea3aa3ee8ab9994de517ba5d4b')}
READERS={
 'input_readback':('scripts/ndx_dated_account_input_independent_readback_20261003.py','688685ffffad650b30647cf2be5205aacf819b1aed5215867b0d4c565ed22295'),
 'account_readback':('scripts/ndx_dated_account_independent_readback_20261003.py','2e412e1dfe66d858656ed68c52ed5a2d976b84c8e7306612b4dc66b60ce0249a'),
 'continuous_readback':('scripts/ndx_dated_per_task_continuous_independent_readback_20261003.py','4a947e8c6f0d96ddae74bb87fc0a5a8dbb691865d550e543e5ecb9311b20e03a')}
FLAGS=dict.fromkeys(('fit_performed','account_executed','continuous_arithmetic_recomputed','old_audit_repeated','raw_risk_recomputed','shared_control_reexecuted','economic_comparison_performed','formal_comparison_passed','point_in_time_verified','promotion_allowed','full_transitive_source_closure_reverified','all_plan_tasks_completed'),False)

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def integer(v,n,msg):require(type(v) is int and v==n,msg)
def ref(role):p,h=BOUND[role];return dict(path=str(ROOT/p),sha256=h)
def reference(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'] and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Exact reference')
def merge(s,p,h):require(p not in s or s[p]==h,'Conflicting bytes');s[p]=h
def read(r,s):
    reference(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Referenced bytes drift');merge(s,r['path'],r['sha256'])
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=invalid)
def guard(s):
    merged=dict(s);merge(merged,str(SOURCE),LOADED_SHA)
    for p,h in merged.items():require(sha(Path(p).read_bytes())==h,'Source drift')
def false(obj,keys):
    for k in keys:require(obj[k] is False,'Authority '+k)

def partition(summary,initial,batch):
    require(summary['schema']=='DATED_BATCH_SAVED_READBACK_SUMMARY_V1' and initial['schema']=='DATED_INITIAL_ECONOMIC_COMPLETED_V1' and batch['schema']=='DATED_ECONOMIC_BATCH_RESULT_V1','Source schemas')
    ids=[r['numerical_task_id'] for r in summary['rows']];require(len(ids)==len(set(ids))==1632,'Complete unique queue')
    integer(summary['full_new_cutoff_task_denominator'],FULL,'Full domain');integer(summary['old_different_cutoff_completed_count_deducted'],0,'No old cutoff deduction')
    context=batch['context'];integer(context['full_task_count'],1632,'Context materialized domain');integer(context['full_new_cutoff_task_denominator'],FULL,'Context full dated domain')
    exact(context['input_references'],{k:ref(k) for k in ('summary','summary_publication','summary_audit','initial')},'Original batch source context')
    require(context['source_hashes'].get(ref('driver')['path'])==ref('driver')['sha256'],'Actual frozen batch driver')
    for r in context['input_references'].values():require(context['source_hashes'].get(r['path'])==r['sha256'],'Context source map reference')
    require(context['comparison_stage_not_implemented'] is True and context['disk_gate_is_resource_limit_not_task_domain'] is True,'No economic completion or domain truncation')
    integer(context['minimum_free_disk_bytes'],5*1024**3,'Original resource gate')
    require(len(initial['rows'])==3 and {r['numerical_task_id'] for r in initial['rows']}==INITIAL_IDS,'Explicit initial three')
    exact(batch['initial_rows_preserved'],initial['rows'],'Initial references preserved')
    remaining=[t for t in ids if t not in INITIAL_IDS];new=batch['new_completed_rows']
    require([r['numerical_task_id'] for r in new]==remaining[:len(new)],'Original queue prefix, no selection/retry')
    for row in new:require(set(row['stage_references'])==set(STAGES),'Six completed stage references')
    integer(batch['planned_remaining_count'],1629,'Remaining dispatch denominator');integer(batch['new_completed_count'],len(new),'Completed count')
    u=batch['unresolved_task_ids'];n=batch['undispatched_task_ids'];require(type(u) is list and type(n) is list and len(u)<=1,'Failure partition lists')
    exact([r['numerical_task_id'] for r in new]+u+n,remaining,'Complete ordered partition')
    failure=batch['failure']
    if failure is None:require(batch['status']=='REQUESTED_ECONOMIC_STAGES_FINISHED' and not u and not n,'Finished covers remaining queue')
    else:
        require(batch['status']=='STOPPED_WITH_EVIDENCE','Stopped status');integer(failure['ordinal'],len(new),'Failure ordinal')
        require(failure['numerical_task_id']==remaining[len(new)],'Failure at next task')
        for k in ('task_stage_invoked','current_stage_invoked','stage_may_have_written_evidence'):require(type(failure[k]) is bool,'Exact invocation flags')
        require(failure['task_stage_invoked']==failure['stage_may_have_written_evidence']==bool(u),'Invoked vs undispatched partition')
        require(not failure['current_stage_invoked'] or failure['task_stage_invoked'],'Current invocation implies task invocation')
        require(failure['retry_allowed'] is False,'No retry')
        refs=failure['completed_stage_references'];require(type(refs) is dict and set(refs)==set(STAGES[:len(refs)]),'Partial stage prefix')
        stage=failure['stage'];require(stage is None or stage in STAGES,'Failure stage')
        if stage is None:require(not refs and not u,'Pre-stage failure')
        else:require(len(refs) in (STAGES.index(stage),STAGES.index(stage)+1),'Last attempted stage position')
        if refs:require(failure['task_stage_invoked'],'Returned stages cannot be undispatched')
    false(batch,('fit_performed','incumbent_executed','incumbent_continuous_recomputed','retry_allowed','economic_comparison_performed','promotion_allowed','point_in_time_verified','formal_benchmark_qualified','all_plan_tasks_completed'))
    return ids,new,failure

def validate_task(tid,stage_refs,docs,summary_row,first=False,complete=True):
    """Only cross-links and saved outcomes; deliberately no account arithmetic."""
    if complete:require(set(stage_refs)==set(STAGES),'Complete pipeline must contain all six stages')
    for role in stage_refs:require(type(docs.get(role)) is dict and bool(docs[role]),'Every referenced stage document must be nonempty')
    for r in stage_refs.values():reference(r)
    d=docs.get('inputs');ia=docs.get('input_readback');post=docs.get('account_postcheck');aa=docs.get('account_readback');c=docs.get('continuous');ca=docs.get('continuous_readback')
    result=dict(numerical_task_id=tid,stage_references=deepcopy(stage_refs),pipeline_complete=complete,account_attempt_outcome=None,decision_status=None,execution_statuses=None,integer_account_available=False)
    if d:
        require(d['schema']=='DATED_ACCOUNT_INPUT_DOCUMENT_V1','Input document schema');task=d['inputs']['original_task'];require(task['numerical_task_id']==tid==sha(enc(task['numerical_identity'])),'Complete numerical identity')
        exact(d['task_reference'],summary_row['task_reference'],'Summary/input task position');exact(d['independent_readback_reference'],summary_row['saved_batch_row']['independent_readback_reference'],'Original fitted readback reference')
        require(task['numerical_identity']['cutoff']=='2026-03-20' and task['numerical_identity']['requested_previous_target_weights'] is None,'Dated None prior')
        require(len(d['original_provenance_and_missing'])==101 and len(d['preserved_evidence_sidecars'])==7,'Full evidence preserved')
        false(d,('account_executed','fit_performed','point_in_time_verified','promotion_allowed'))
    if ia:
        require(ia['schema']=='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1' and ia['status']=='PASS','Accepted input readback');exact(ia['inputs_reference'],stage_refs['inputs'],'Input audit bytes')
        pub=docs['inputs_publication'];exact(ia['publication_reference'],docs['_refs']['inputs_publication'],'Audited receipt reference');exact(pub['inputs_reference'],stage_refs['inputs'],'Input receipt');exact(pub['source_hashes'],d['source_hashes'],'Input receipt sources');require(pub['status']=='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED','Input publication status')
    if post:
        require(post['schema']=='DATED_ACCOUNT_POSTCHECK_V1' and post['track']=='candidate' and post['numerical_task_id']==tid,'Candidate postcheck')
        raw=docs['raw'];started=docs['account_started'];exact(raw['started_reference'],post['started_reference'],'Raw/started link')
        require(started['state']['numerical_task_id']==tid and started['state']['track']=='candidate','Started task');exact(started['state']['inputs_reference'],stage_refs['inputs'],'Started input link');exact(started['state']['input_readback_reference'],stage_refs['input_readback'],'Started input audit')
        require(raw['schema']=='DATED_ACCOUNT_RAW_V1' and started['schema']=='DATED_ACCOUNT_STARTED_V1','Original account evidence schemas')
        exact(raw['source_hashes'],started['state']['source_hashes'],'Original account source map');exact(raw['runtime'],started['state']['runtime'],'Original runtime')
        result['account_attempt_outcome']=post['status']
        if post['status']=='ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING':
            require(raw['status']=='ACCOUNT_RETURNED' and raw['error'] is None,'Saved account completion')
            integer(raw['engine_call_attempt_count'],1,'One account attempt');integer(raw['returned_account_count'],1,'One returned account')
            require(type(raw['account']) is dict,'Saved returned ledger type');account=raw['account'];require(len(account['decisions'])==1,'One saved decision')
            result.update(decision_status=account['decisions'][0]['status'],execution_statuses=[r['status'] for r in account['executions']],integer_account_available=True)
            require(result['decision_status'] in ('NO_PLAN','FROZEN') and all(s in ('FILLED','REJECTED','CANCELLED_SPLIT') for s in result['execution_statuses']),'Original decision/execution outcomes')
            if result['decision_status']=='NO_PLAN':require(result['execution_statuses']==[],'NO_PLAN cannot invent entry')
    if aa:
        require(aa['status']=='PASS','Account readback evidence valid')
        if first:
            require(aa['schema']=='DATED_FIRST_ACCOUNTS_INDEPENDENT_ACCOUNTING_READBACK_V1','Original first audit');rows=[r for r in aa['rows'] if r['track']=='candidate'];require(len(rows)==1,'One initial candidate');ar=rows[0]
            exact(ar['input_reference'],stage_refs['inputs'],'First audited input');exact(ar['postcheck_reference'],stage_refs['account_postcheck'],'First post audit');exact(ar['raw_reference'],post['raw_reference'],'First raw audit');require(ar['execution_status']==result['execution_statuses'][0],'First outcome retained')
        else:
            require(aa['schema']=='DATED_ACCOUNT_INDEPENDENT_READBACK_V1' and aa['numerical_task_id']==tid,'New account audit task');exact(aa['postcheck_reference'],stage_refs['account_postcheck'],'Post audit');exact(aa['raw_reference'],post['raw_reference'],'Raw audit');exact(aa['inputs_reference'],stage_refs['inputs'],'Same audited input');exact(aa['input_readback_reference'],stage_refs['input_readback'],'Same audited input reader')
            require(aa['attempt_outcome']==post['status'],'Actual account outcome')
            if aa['attempt_outcome']=='ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING':
                require(aa['accounting_verified'] is True and aa['accounting']['status']=='PASS','Accepted independent accounting');integer(aa['accounting']['daily_rows'],127,'Full saved accounting')
                exact(aa['accounting']['execution_statuses'],result['execution_statuses'],'Execution status preserved');require(aa['accounting']['decision_status']==result['decision_status'],'Decision preserved')
            elif aa['attempt_outcome']=='NOT_EXECUTED_NONPOSITIVE_TARGET':
                require(aa['accounting_verified'] is False and aa['accounting'] is None and raw['account'] is None and raw['status']=='NOT_EXECUTED_NONPOSITIVE_TARGET','Blocked account not cash substitute')
                integer(raw['engine_call_attempt_count'],0,'Blocked means no call');integer(raw['returned_account_count'],0,'Blocked no ledger')
            elif complete:raise ValueError('Technical failure cannot complete pipeline')
        if complete:require(post['status'] in ('ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING','NOT_EXECUTED_NONPOSITIVE_TARGET') and post['error'] is None and raw['error'] is None,'No technical completion')
    if c:
        require(c['schema']==('SOURCE_BOUND_DATED_CONTINUOUS_WEIGHT_DIAGNOSTIC_V1' if first else 'SOURCE_BOUND_DATED_PER_TASK_CONTINUOUS_DIAGNOSTIC_V1'),'Continuous schema');exact(c['original_task_preserved'],d['inputs']['original_task'],'Same continuous task')
        if not first:
            require(c['numerical_task_id']==tid,'Continuous task');integer(c['candidate_core_call_count'],1,'Only candidate calculation');integer(c['control_core_call_count'],0,'Control not recalculated');exact(c['input_references']['inputs'],stage_refs['inputs'],'Continuous input')
        pub=docs['continuous_publication'];exact(pub['diagnostic_reference'],stage_refs['continuous'],'Continuous publication');exact(pub['source_hashes'],c['source_hashes'],'Continuous receipt source map')
    if ca:
        require(ca['status']=='PASS' and ca['schema']==('DATED_CONTINUOUS_INDEPENDENT_READBACK_V1' if first else 'DATED_PER_TASK_CONTINUOUS_INDEPENDENT_READBACK_V1'),'Continuous audit')
        exact(ca['diagnostic_reference'],stage_refs['continuous'],'Continuous audit target');exact(ca['publication_reference'],docs['_refs']['continuous_publication'],'Continuous audit publication')
        if not first:require(ca['numerical_task_id']==tid,'Continuous audit task');exact(ca['inputs_reference'],stage_refs['inputs'],'Continuous audited input')
    for role,obj in (('input_readback',ia),('account_readback',aa),('continuous_readback',ca)):
        if obj and not (first and role!='input_readback'):
            path,h=READERS[role];require(obj['reader_sha256']==h and obj['source_hashes'].get(str(ROOT/path))==h,'Independent reader source binding')
        if obj:false(obj,('point_in_time_verified','promotion_allowed'))
    return result

def task_documents(tid,stage_refs,sources,initial_row=None):
    docs={k:read(r,sources) for k,r in stage_refs.items()};extra={}
    if 'input_readback' in docs:extra['inputs_publication']=docs['input_readback']['publication_reference']
    if 'account_postcheck' in docs:extra.update(raw=docs['account_postcheck']['raw_reference'],account_started=docs['account_postcheck']['started_reference'])
    if 'continuous' in docs:
        if initial_row:extra['continuous_publication']=initial_row['continuous_publication']
        elif 'continuous_readback' in docs:extra['continuous_publication']=docs['continuous_readback']['publication_reference']
        else:
            path=Path(stage_refs['continuous']['path']).with_name('publication.json');extra['continuous_publication']=dict(path=str(path),sha256=sha(path.read_bytes()))
    for k,r in extra.items():docs[k]=read(r,sources)
    docs['_refs']=extra;return docs

def readback(result_reference,*,execute=False):
    require(type(execute) is bool and execute,'Explicit execute');require(RESULT_SHA is not None,'Final result pin pending');reference(result_reference)
    require(Path(result_reference['path'])==RESULT_PATH and result_reference['sha256']==RESULT_SHA,'Unique actual result anchor');require(not OUTPUT.exists(),'Immutable readback namespace')
    base={str(SOURCE):LOADED_SHA};summary=read(ref('summary'),base);initial=read(ref('initial'),base);batch=read(result_reference,base)
    publication=read(ref('summary_publication'),base);audit=read(ref('summary_audit'),base)
    exact(publication['summary_reference'],ref('summary'),'Summary publication');exact(audit['summary_reference'],ref('summary'),'Summary independent audit');exact(audit['publication_reference'],ref('summary_publication'),'Summary audited receipt');require(audit['status']=='PASS','Summary accepted audit')
    for p,h in [BOUND['driver'],*READERS.values()]:merge(base,str(ROOT/p),h)
    guard(base);ids,new,failure=partition(summary,initial,batch)
    started_path=RESULT_PATH.with_name('started.json');started_ref=dict(path=str(started_path),sha256=sha(started_path.read_bytes()));started=read(started_ref,base)
    require(started['schema']=='DATED_ECONOMIC_BATCH_STARTED_V1','Batch started schema');exact(started['ordered_remaining_task_ids'],[t for t in ids if t not in INITIAL_IDS],'Started original order');exact(started['initial_rows'],initial['rows'],'Started initial rows');exact(started['context'],batch['context'],'Started/result context')
    for p,h in batch['context']['source_hashes'].items():merge(base,p,h)
    guard(base);byid={r['numerical_task_id']:r for r in summary['rows']};all_sources=dict(base);rows=[]
    # Each account/document is released before the next task. Only hashes and metadata accumulate.
    ordered=[(r['numerical_task_id'],{k:r[k] for k in STAGES},r,True) for r in initial['rows']]+[(r['numerical_task_id'],r['stage_references'],None,True) for r in new]
    if failure and failure['completed_stage_references']:ordered.append((failure['numerical_task_id'],failure['completed_stage_references'],None,False))
    for tid,refs,initial_row,complete in ordered:
        local={};docs=task_documents(tid,refs,local,initial_row);row=validate_task(tid,refs,docs,byid[tid],tid==FIRST,complete)
        guard(local)
        for p,h in local.items():merge(all_sources,p,h)
        rows.append(row);del docs
    guard(base);complete_rows=[r for r in rows if r['pipeline_complete']]
    counts=dict(Counter(r['account_attempt_outcome'] for r in complete_rows));decisions=dict(Counter(r['decision_status'] for r in complete_rows if r['decision_status'] is not None));executions=dict(Counter(s for r in complete_rows for s in (r['execution_statuses'] or [])))
    report=dict(schema='DATED_ECONOMIC_BATCH_INDEPENDENT_READBACK_V1',status='PASS',evidence_valid=True,result_reference=result_reference,reader_sha256=LOADED_SHA,input_references={k:ref(k) for k in ('summary','initial','summary_publication','summary_audit')},batch_started_reference=started_ref,batch_started_reference_scope='CURRENT_BYTES_MATCH_EXTERNAL_RESULT_CONTEXT_AND_ORDER_NOT_INDEPENDENT_EXTERNAL_SHA',progress_dispatch_log_reverified=False,batch_context_preserved=deepcopy(batch['context']),source_hashes=all_sources,rows=rows,initial_completed_count=3,new_completed_count=len(new),completed_pipeline_count=3+len(new),planned_task_count=1632,full_new_cutoff_task_denominator=FULL,remaining_without_completed_pipeline_count=FULL-3-len(new),unresolved_task_ids=deepcopy(batch['unresolved_task_ids']),undispatched_task_ids=deepcopy(batch['undispatched_task_ids']),batch_failure_preserved=deepcopy(failure),account_attempt_counts=counts,decision_counts=decisions,execution_counts=executions,evidence_valid_does_not_mean_economic_comparison_complete=True,source_verification_scope='DIRECT_REFERENCES_AT_EACH_TASK_READ_COMPLETION;BASE_SOURCES_RECHECKED_AT_END;AUDITED_TRANSITIVE_SOURCE_MAPS_NOT_REHASHED',**FLAGS)
    OUTPUT.mkdir(parents=True,exist_ok=False);path=OUTPUT/'independent_readback.json';blob=enc(report)
    with path.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    guard(base);require(path.read_bytes()==blob and {p.name for p in OUTPUT.iterdir()}=={path.name},'Saved readback bytes');return dict(path=str(path),sha256=sha(blob))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--result-sha256',required=True);p.add_argument('--execute',action='store_true');a=p.parse_args();print(json.dumps(readback(dict(path=str(RESULT_PATH),sha256=a.result_sha256),execute=a.execute)))
