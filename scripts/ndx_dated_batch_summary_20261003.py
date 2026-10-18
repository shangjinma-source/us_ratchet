"""Read saved dated readback reports; no fitting or raw accounting replay."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/dated_batch_summary_20261003_v1'
FULL=6222659648236112670
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
OUTCOMES=('RISK_PASSED','RISK_FAILED','NUMERICAL_EXCEPTION','VALIDATION_FAILURE')
CATEGORIES=OUTCOMES+('DISPATCHED_WITHOUT_ACCEPTED_READBACK','NOT_DISPATCHED')
FLAGS=dict.fromkeys(('fit_performed','raw_audit_repeated','old_cutoff_completion_reused','economic_comparison_performed','promotion_allowed','point_in_time_verified','execution_authorized','all_plan_tasks_completed'),False)
BOUND={
 'preparation':dict(path=str(ROOT/'data/cache/research/dated_fixed_task_preparation_20261003_v1/preparation.json'),sha256='ff24a6b732bc55ea6dbb7b453a41ff58d0f2ee316e3f2120aa4006f3b82d3d0e'),
 'initial':dict(path=str(ROOT/'research_contracts/dated_initial_completed_tasks_20261003_v1.json'),sha256='72ba335644c6fec313d31692d317d1df63a425d91eee0a50d3586f6ab865ab9c'),
 'batch':dict(path=str(ROOT/'data/cache/research/dated_batch_20261003_v1/result.json'),sha256='f3d138b370d680c96dc44cbfe7edfc9388396b4b92e54d6dbc7ddc580fd46847'),
}
READER=str(ROOT/'scripts/ndx_dated_single_task_independent_readback_20261003.py')
READER_SHA='bd63ce1541c63d3f38e90a7313666d37abcbb9b51cc9d2291f702ee8fad43cea'

def require(ok,message):
    if not ok:raise ValueError(message)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,message):require(encode(a)==encode(b),message)
def integer(v,n,message):require(type(v) is int and v==n,message)
def merge(sources,path,digest):
    require(path not in sources or sources[path]==digest,'Conflicting source');sources[path]=digest

def assemble_summary(preparation,initial,batch,reports_by_id,references):
    m=preparation['materialized'];tasks=[]
    integer(m['materialized_task_count'],1632,'Full new task count');integer(m['full_plan_task_denominator'],FULL,'Full dated domain')
    integer(len(m['combinations']),544,'All saved combinations')
    for ci,combo in enumerate(m['combinations']):
        exact([t['numerical_identity']['weight_spec'] for t in combo['tasks']],list(SPECS),'Three original specifications')
        for task in combo['tasks']:
            ident=task['numerical_identity'];integer(ident['holding_count'],4+ci//32,'All k coverage in saved order')
            require(ident['cutoff']=='2026-03-20' and ident['requested_previous_target_weights'] is None,'Dated identity')
            require(task['numerical_task_id']==sha(encode(ident)),'Task identity digest')
            tasks.append(task)
    ids=[t['numerical_task_id'] for t in tasks];require(len(ids)==len(set(ids))==1632,'Unique complete queue')
    require(initial['schema']=='DATED_INITIAL_COMPLETED_TASKS_V1' and batch['schema']=='DATED_BATCH_RESULT_V1','Initial/batch schemas')
    exact(initial['preparation_reference'],references['preparation'],'Preparation reference')
    exact(batch['initial_completed_rows'],initial['rows'],'Initial rows preserved')
    first=initial['rows'];integer(len(first),2,'Exactly initial two')
    require([r['numerical_task_id'] for r in first]==ids[:2],'Initial prefix')
    rows=batch['newly_readback_rows'];integer(batch['new_readback_count'],len(rows),'Readback count');integer(batch['planned_remaining_dispatch_count'],1630,'Remainder')
    for i,r in enumerate(rows):integer(r['ordinal'],i,'Ordered batch ordinal')
    accepted=first+rows;accepted_ids=[r['numerical_task_id'] for r in accepted]
    require(accepted_ids==ids[:len(accepted)] and set(reports_by_id)==set(accepted_ids),'Exact accepted prefix/report set')
    unresolved=batch['unresolved_dispatched_task_ids'];undispatched=batch['undispatched_task_ids']
    require(type(unresolved) is list and len(unresolved)<=1 and accepted_ids+unresolved+undispatched==ids,'Complete disjoint partition in saved order')
    failure=batch['failure'];require((failure is None)==(batch['status']=='BUDGETED_QUEUE_FINISHED'),'Terminal status')
    if failure is None:require(not unresolved and not undispatched,'Finished complete')
    else:
        require(batch['status']=='STOPPED_WITH_EVIDENCE','Stopped status')
        if failure.get('task_readback_saved') is True:
            require(not unresolved and 'dispatch_invoked' not in failure and failure['reason'] in ('NUMERICAL_EXCEPTION','VALIDATION_FAILURE'),'Accepted failure shape')
            require(rows and rows[-1]['attempt_outcome']==failure['reason'],'Accepted failure classification')
        else:
            require(failure['reason']=='DISPATCH_OR_READBACK_FAILURE' and type(failure['dispatch_invoked']) is bool,'Dispatch failure exact bool')
            require(bool(unresolved) is failure['dispatch_invoked'],'Dispatch/partition agreement')
        expected_failure = accepted_ids[-1:] if failure.get('task_readback_saved') is True else (unresolved or undispatched[:1])
        require(failure['numerical_task_id'] in expected_failure,'Failure task position')
    saved={r['numerical_task_id']:r for r in accepted};summary=[]
    for i,task in enumerate(tasks):
        tid=ids[i];ident=task['numerical_identity'];status='NOT_DISPATCHED';report=None
        if tid in saved:
            report=reports_by_id[tid];row=saved[tid]
            require(report['schema']=='DATED_SINGLE_TASK_INDEPENDENT_READBACK_V1' and report['status']=='PASSED' and report['numerical_task_id']==tid,'Accepted independent report')
            status=report['attempt_outcome'];require(status in OUTCOMES,'Known outcome')
            if i>=2:require(status==row['attempt_outcome'],'Batch/report outcome')
            else:require(status in OUTCOMES[:2],'Initial completed risk result')
            exact(report['postcheck_reference'],row['postcheck_reference'],'Postcheck reference')
            exact(report['task_reference'],dict(references['preparation'],json_pointer=f'/materialized/combinations/{i//3}/tasks/{i%3}'),'Task pointer')
            integer(report['full_plan_task_denominator'],FULL,'Report dated denominator');integer(report['materialized_task_denominator'],1632,'Report task denominator')
            for key in ('runner_called','fitter_called','optimization_repeated','promotion_allowed','point_in_time_verified'):require(report[key] is False,'Report authority')
            require(report['source_hashes'].get(READER)==READER_SHA,'Frozen independent reader binding')
        elif tid in unresolved:status='DISPATCHED_WITHOUT_ACCEPTED_READBACK'
        summary.append(dict(numerical_task_id=tid,k=ident['holding_count'],weight_spec=ident['weight_spec'],category=status,task_reference=dict(references['preparation'],json_pointer=f'/materialized/combinations/{i//3}/tasks/{i%3}'),saved_batch_row=deepcopy(saved.get(tid)),independent_report_preserved=deepcopy(report)))
    counts={s:sum(r['category']==s for r in summary) for s in CATEGORIES}
    exact(batch['new_outcome_counts'],{s:sum(r['attempt_outcome']==s for r in rows) for s in OUTCOMES},'Batch outcome counters')
    coverage=[]
    for k,spec in sorted({(r['k'],r['weight_spec']) for r in summary}):
        subset=[r for r in summary if (r['k'],r['weight_spec'])==(k,spec)]
        coverage.append(dict(k=k,weight_spec=spec,planned_task_count=len(subset),counts={s:sum(r['category']==s for r in subset) for s in CATEGORIES}))
    return dict(schema='DATED_BATCH_SAVED_READBACK_SUMMARY_V1',rows=summary,category_counts=counts,k_spec_coverage=coverage,materialized_task_count=1632,accepted_independent_terminal_count=len(accepted),attempted_task_count=len(accepted)+len(unresolved),risk_passed_task_count=counts['RISK_PASSED'],risk_failed_task_count=counts['RISK_FAILED'],failed_terminal_task_count=counts['NUMERICAL_EXCEPTION']+counts['VALIDATION_FAILURE'],unresolved_dispatched_count=len(unresolved),undispatched_count=len(undispatched),full_new_cutoff_task_denominator=FULL,remaining_without_accepted_terminal_count=FULL-len(accepted),old_different_cutoff_completed_count_deducted=0,initial_rows_preserved=deepcopy(first),batch_failure_preserved=deepcopy(failure),input_references=deepcopy(references),summary_scope='SAVED_READBACK_METADATA_NOT_NEW_RAW_AUDIT_OR_ECONOMIC_QUALIFICATION',**FLAGS)

def load(ref,sources):
    require(type(ref) is dict and set(ref)=={'path','sha256'} and type(ref['sha256']) is str and len(ref['sha256'])==64,'Explicit source anchor')
    raw=Path(ref['path']).read_bytes();require(sha(raw)==ref['sha256'],'Source drift');merge(sources,ref['path'],ref['sha256'])
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda s:(_ for _ in ()).throw(ValueError(s)))
def guard(sources):
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source drift')
def save(path,value):
    raw=encode(value)
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==raw,'Saved drift');return dict(path=str(path),sha256=sha(raw))
def run(*,execute=False):
    require(type(execute) is bool and execute,'Explicit execute required');require(not OUTPUT.exists(),'Immutable namespace exists')
    sources={str(SOURCE):LOADED,READER:READER_SHA};docs={k:load(r,sources) for k,r in BOUND.items()};reports={}
    for row in docs['initial']['rows']+docs['batch']['newly_readback_rows']:
        tid=row['numerical_task_id'];require(tid not in reports,'Duplicate report ID');reports[tid]=load(row['independent_readback_reference'],sources)
    guard(sources);OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(schema='DATED_BATCH_SUMMARY_STARTED_V1',input_references=BOUND,source_hashes=sources,**FLAGS))
        result=assemble_summary(docs['preparation'],docs['initial'],docs['batch'],reports,BOUND);result['source_hashes']=sources;guard(sources)
        out=save(OUTPUT/'summary.json',result);require({p.name for p in OUTPUT.iterdir()}=={'started.json','summary.json'},'Unexpected output')
        guard(sources);pub=save(OUTPUT/'publication.json',dict(schema='DATED_BATCH_SUMMARY_PUBLICATION_V1',status='PUBLISHED',summary_reference=out,source_hashes=sources,**FLAGS));guard(sources)
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','summary.json','publication.json'},'Unexpected output')
        for r in (out,pub):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Output drift')
        return out
    except Exception as error:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(error),retry_allowed=False));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
