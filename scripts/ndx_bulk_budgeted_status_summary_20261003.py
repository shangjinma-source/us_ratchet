"""Saved evidence status aggregation only: no optimizer, raw returns or risk recheck."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/bulk_budgeted_status_summary_20261003_v1'
BOUND={
 'preparation':('data/cache/research/bulk_budgeted_search_prepare_20261003_v1/preparation.json','03d60c666e06a00fa44b19b16cda9609b4e2a75d411dff7ac6cd0e0c08915da1'),
 'rebinding':('data/cache/research/bulk_completed_task_rebinding_20261003_v1/rebinding.json','e2a3cb619a2cd46a2f7d557be91f362342676089756de6baf9ac4c9692daf29d'),
 'initial':('research_contracts/bulk_budgeted_first_two_completed_20261003_v1.json','6007612374872316d61cded15a9e654f16a72f1899743266221acfdb20b64b9b'),
 'batch':('data/cache/research/bulk_budgeted_batch_20261003_v1/result.json','0bbc85b1768cb45e846fe5706bdd873de77be1faa9023497ecbffeaf09074d2d')}
OUTCOMES=('RISK_PASSED','RISK_FAILED','NUMERICAL_EXCEPTION','VALIDATION_FAILURE')
STATES=OUTCOMES+('UNDISPATCHED','UNRESOLVED_DISPATCH')
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
FALSE=('promotion_allowed','execution_authorized','point_in_time_verified','legal_training_input_admitted','all_plan_tasks_completed','economic_comparison_performed','retry_allowed')

def require(ok,message):
    if not ok:raise ValueError(message)
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(v):return sha(encoded(v))
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def integer(v,n,message):require(type(v) is int and v==n,message)
def reference(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'] and type(r['sha256']) is str and len(r['sha256'])==64 and set(r['sha256'])<=set('0123456789abcdef'),'Explicit complete reference')
def loads(blob):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON '+v)
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=invalid)

def assemble_summary(documents,references,report_envelopes):
    """Caller binds four parent bytes; report envelopes individually verify external bytes."""
    require(set(documents)==set(references)==set(BOUND),'Four parents required')
    for r in references.values():reference(r)
    q=documents['preparation'];m=q['materialized'];old=documents['rebinding'];initial=documents['initial'];batch=documents['batch']
    require(q['schema']=='BULK_BUDGETED_SEARCH_PREPARATION_V1' and q['status']=='PREPARED_NOT_ATTEMPTED','Prepared queue')
    require(old['schema']=='BULK_COMPLETED_TASK_REBINDING_V1' and old['numerical_contracts_unchanged'] is True,'Prior reference-only completion')
    require(initial['schema']=='BULK_BUDGETED_FIRST_TWO_COMPLETED_V1' and batch['schema']=='BULK_BUDGETED_BATCH_RESULT_V1','Batch/initial schemas')
    for obj in (q,batch):require(all(obj[k] is False for k in FALSE if k!='retry_allowed' or k in obj),'Parent permissions')
    for key in ('execution_authorized','promotion_allowed','retry_allowed'):require(initial[key] is False,'Initial permissions')
    integer(initial['remaining_batch_request_count'],1630,'First-two remainder')
    integer(m['materialized_task_count'],1632,'New denominator');integer(m['complete_saved_completed_task_count'],504,'Old denominator');integer(m['selected_completed_intersection_count'],0,'No old intersection')
    new={};order=[]
    for ci,combo in enumerate(m['combinations']):
        require(type(combo['k']) is int and combo['k']==4+ci//32 and len(combo['tasks'])==3,'Complete k/spec scope')
        for si,t in enumerate(combo['tasks']):
            tid=t['numerical_task_id'];identity=t['numerical_identity'];require(tid==digest(identity) and tid not in new and identity['holding_count']==combo['k'] and identity['weight_spec']==SPECS[si],'Unique full task ID and spec')
            new[tid]=dict(k=combo['k'],weight_spec=SPECS[si],task_reference=dict(references['preparation'],json_pointer=f'/materialized/combinations/{ci}/tasks/{si}'));order.append(tid)
    require(len(m['combinations'])==544 and len(order)==1632,'Entire new queue');exact(order,m['new_unattempted_numerical_task_ids'],'Ordered new IDs')
    oldrows=[];oldids=set();tables={str(k):{spec:{s:0 for s in ('EXTERNAL_RISK_PASSED',)+STATES} for spec in SPECS} for k in range(4,21)}
    for i,r in enumerate(old['rows']):
        prior=r['old_completed_row'];task=prior['full_task'];identity=task['numerical_identity'];tid=r['numerical_task_id'];k=identity['holding_count'];spec=identity['weight_spec']
        require(tid==task['numerical_task_id']==digest(identity) and tid not in new and tid not in oldids,'Old504 unique and disjoint');oldids.add(tid)
        require(r['status']=='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND' and prior['status'] in ('FITTED_FIVE_RISKS_PASSED','COMPLETED_EXTERNALLY_AUDITED_ORIGINAL_FIVE_RISKS_PASSED'),'Old pass evidence only')
        integer(r['new_wrapper_call_attempt_count'],0,'Rebinding performs no new attempt');require(type(k) is int and 4<=k<=20 and spec in SPECS,'Old k/spec')
        tables[str(k)][spec]['EXTERNAL_RISK_PASSED']+=1
        oldrows.append(dict(numerical_task_id=tid,k=k,weight_spec=spec,state='EXTERNAL_RISK_PASSED',reference=dict(references['rebinding'],json_pointer=f'/rows/{i}'),old_completed_reference=deepcopy(r['old_completed_row_reference'])))
    require(len(oldids)==504,'Full old504')
    exact([r['numerical_task_id'] for r in initial['rows']],order[:2],'Fixed initial two order');exact(batch['initial_completed_rows'],initial['rows'],'Initial immutable rows')
    context=batch['batch_context'];exact(context['first_two_reference'],references['initial'],'Initial manifest reference');integer(context['planned_total_task_count'],1632,'Batch total');integer(context['prior_completed_task_count'],2,'Prior two')
    require(context['ordered_task_ids_sha256']==sha(json.dumps(order,separators=(',',':')).encode()),'Full ordered queue binding')
    integer(batch['planned_remaining_dispatch_count'],1630,'Remaining planned count')
    rows=batch['newly_readback_rows'];integer(batch['new_readback_count'],len(rows),'Accepted new readbacks')
    require(len(rows)<=1630,'Bounded readback count')
    for i,row in enumerate(rows):integer(row['ordinal'],i,'Contiguous accepted ordinal');require(row['numerical_task_id']==order[i+2],'No skipped or repeated dispatch')
    pending=batch['undispatched_task_ids'];unresolved=batch['unresolved_dispatched_task_ids'];failure=batch['failure']
    require(type(pending) is list and type(unresolved) is list and len(unresolved)<=1,'Pending classifications')
    accepted_ids=order[:2]+[r['numerical_task_id'] for r in rows]
    exact(accepted_ids+unresolved+pending,order,'Complete disjoint1632 partition')
    if failure is None:
        require(batch['status']=='BUDGETED_QUEUE_FINISHED' and not unresolved and not pending,'Finished all bounded tasks')
    else:
        require(batch['status']=='STOPPED_WITH_EVIDENCE' and type(failure) is dict,'Stopped evidence')
        if unresolved:
            require(failure['numerical_task_id']==unresolved[0] and failure.get('dispatch_invoked') is True and failure['reason']=='DISPATCH_OR_READBACK_FAILURE','Unresolved dispatched attempt')
        elif failure.get('task_readback_saved') is True:
            require(rows and failure['numerical_task_id']==rows[-1]['numerical_task_id'] and failure['reason'] in ('NUMERICAL_EXCEPTION','VALIDATION_FAILURE') and rows[-1]['attempt_outcome']==failure['reason'],'Terminal stopped readback')
        else:
            require(failure.get('dispatch_invoked') is False and pending and failure['numerical_task_id']==pending[0],'Pre-dispatch stopped task')
    needed=[r['independent_readback_reference'] for r in initial['rows']+rows]
    if failure and failure.get('independent_readback_reference') is not None:needed.append(failure['independent_readback_reference'])
    expected_by_path={}
    for r in needed:
        reference(r);require(r['path'] not in expected_by_path or expected_by_path[r['path']]==r,'Report reference conflict');expected_by_path[r['path']]=r
    require(type(report_envelopes) is dict and set(report_envelopes)==set(expected_by_path),'Only and all externally referenced saved reports')
    reports={}
    for path,r in expected_by_path.items():
        envelope=report_envelopes[path];require(set(envelope)=={'reference','bytes'} and envelope['reference']==r and type(envelope['bytes']) is bytes and sha(envelope['bytes'])==r['sha256'],'External report SHA')
        report=loads(envelope['bytes']);require(report['schema']=='BULK_BUDGETED_SINGLE_TASK_INDEPENDENT_READBACK_V1' and report['status']=='PASSED' and report['attempt_outcome'] in OUTCOMES,'Independent evidence schema/outcome')
        require(all(report[k] is False for k in FALSE if k!='economic_comparison_performed') and report['independent_readback_performed'] is True and report['runner_called'] is False and report['fitter_called'] is False,'Independent report permissions')
        require(report['optimization_repeated'] is False and report['risk_projection_metadata_independently_recomputed'] is False and report['optimizer_optimality_proved'] is False and report['runtime_binary_closure_verified'] is False and report['full_transitive_source_closure_reverified'] is False,'Saved report scope')
        require(type(report['source_hashes']) is dict and type(report['runtime']) is dict,'Report saved source/runtime metadata')
        for key in ('started_reference','raw_reference','postcheck_reference'):reference(report[key])
        integer(report['other_new_tasks_not_inferred'],1631,'Report only one task')
        integer(report['materialized_task_denominator'],1632,'Report denominator');integer(report['externally_completed_task_count'],504,'Report external count')
        require(report['full_plan_task_denominator']==m['full_plan_task_denominator'],'Report global denominator');exact(report['input_references']['preparation'],references['preparation'],'Report queue authority')
        detail_status=report['detail']['status']
        expected_detail={'RISK_PASSED':'FITTED_FIVE_RISKS_PASSED','RISK_FAILED':'FITTED_FIVE_RISKS_FAILED','NUMERICAL_EXCEPTION':'NUMERICAL_EXCEPTION_NO_RETURNED_FIT'}
        if report['attempt_outcome'] in expected_detail:require(detail_status==expected_detail[report['attempt_outcome']],'Saved detail/outcome classification')
        else:require(detail_status in set(expected_detail.values()),'Validation failure preserves known numerical subresult')
        tid=report['numerical_task_id'];require(tid in new,'Report authorized task');exact(report['task_reference'],new[tid]['task_reference'],'Report exact queue pointer')
        reports[path]=report
    states={};output=[]
    for row in initial['rows']+rows:
        tid=row['numerical_task_id'];r=row['independent_readback_reference'];report=reports[r['path']]
        require(report['numerical_task_id']==tid and report['postcheck_reference']==row['postcheck_reference'],'Task/postcheck cross-reference')
        outcome=report['attempt_outcome']
        if row in initial['rows']:require(outcome in ('RISK_PASSED','RISK_FAILED'),'Initial accepted fit evidence')
        else:require(row['attempt_outcome']==outcome,'Batch outcome not self-authoritative')
        states[tid]=outcome
        output.append(dict(numerical_task_id=tid,**new[tid],state=outcome,independent_readback_reference=deepcopy(r),postcheck_reference=deepcopy(row['postcheck_reference']),successful_reusable_evidence=outcome=='RISK_PASSED'))
    for tid in unresolved+pending:
        state='UNRESOLVED_DISPATCH' if tid in unresolved else 'UNDISPATCHED';states[tid]=state
        extra=deepcopy(failure) if state=='UNRESOLVED_DISPATCH' else None
        if state=='UNRESOLVED_DISPATCH' and failure.get('independent_readback_reference'):
            report=reports[failure['independent_readback_reference']['path']];require(report['numerical_task_id']==tid,'Unaccepted saved report task')
        output.append(dict(numerical_task_id=tid,**new[tid],state=state,failure_evidence=extra,successful_reusable_evidence=False))
    for tid,state in states.items():tables[str(new[tid]['k'])][new[tid]['weight_spec']][state]+=1
    counts={s:sum(v==s for v in states.values()) for s in STATES}
    exact(batch['new_outcome_counts'],{s:sum(r['attempt_outcome']==s for r in rows) for s in OUTCOMES},'Saved batch outcome counts')
    return dict(schema='BULK_BUDGETED_SAVED_STATUS_SUMMARY_V1',status='SUMMARY_OF_SAVED_EVIDENCE_ONLY',input_references=deepcopy(references),old_task_denominator=504,new_task_denominator=1632,combined_task_denominator=2136,new_state_counts=counts,per_cardinality_and_spec=tables,old_external_rows=oldrows,new_rows=output,
        accepted_new_readback_count=len(accepted_ids),saved_independent_report_count=len(reports),unresolved_dispatch_invocation_count=len(unresolved),dispatch_invocation_count=len(accepted_ids)+len(unresolved),dispatch_invocation_is_proven_optimizer_call_count=False,
        new_returned_fit_with_accepted_risk_readback_count=counts['RISK_PASSED']+counts['RISK_FAILED'],successful_new_risk_pass_evidence_count=counts['RISK_PASSED'],successful_reusable_evidence_count=504+counts['RISK_PASSED'],full_plan_task_denominator=m['full_plan_task_denominator'],
        remaining_without_accepted_terminal_readback=m['full_plan_task_denominator']-504-len(accepted_ids),remaining_without_successful_risk_pass=m['full_plan_task_denominator']-504-counts['RISK_PASSED'],bounded_queue_fully_classified=True,bounded_queue_all_dispatched=not pending,bounded_queue_all_readbacks_accepted=not pending and not unresolved,
        report_references=list(deepcopy(expected_by_path).values()),numerical_exception_proves_economic_infeasibility=False,risk_failure_proves_global_infeasibility=False,report_source_closures_reaudited=False,old_raw_read=False,new_raw_read=False,risk_checks_recomputed=False,fit_performed=False,optimizer_call_count=None,parent_bytes_authenticated_by_this_pure_function=False,**dict.fromkeys(FALSE,False))

def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded source drift')
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Source drift: '+path)
def load_inputs():
    require(all(type(h) is str and len(h)==64 for _,h in BOUND.values()),'Actual batch pin pending')
    docs={};refs={};sources={str(SOURCE):LOADED_SHA}
    for role,(relative,h) in BOUND.items():
        path=ROOT/relative;blob=path.read_bytes();require(sha(blob)==h,'Parent SHA');docs[role]=loads(blob);refs[role]=dict(path=str(path),sha256=h);sources[str(path)]=h
    needed=[r['independent_readback_reference'] for r in docs['initial']['rows']+docs['batch']['newly_readback_rows']]
    failure=docs['batch']['failure']
    if failure and failure.get('independent_readback_reference') is not None:needed.append(failure['independent_readback_reference'])
    envelopes={}
    for r in needed:
        reference(r);blob=Path(r['path']).read_bytes();require(sha(blob)==r['sha256'],'External report changed');envelopes[r['path']]=dict(reference=r,bytes=blob);sources[r['path']]=r['sha256']
    guard(sources);return docs,refs,envelopes,sources

def save(path,value):
    blob=encoded(value)
    with path.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==blob,'Output readback');return dict(path=str(path),sha256=sha(blob))
def run():
    require(not OUTPUT.exists(),'Immutable summary namespace exists');docs,refs,envelopes,sources=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(source_hashes=sources,**dict.fromkeys(FALSE,False)))
        result=assemble_summary(docs,refs,envelopes);result['source_hashes']=sources;guard(sources);r=save(OUTPUT/'summary.json',result);guard(sources)
        publication=save(OUTPUT/'publication.json',dict(schema='BULK_BUDGETED_STATUS_SUMMARY_PUBLICATION_V1',summary_reference=r,source_hashes=sources,**dict.fromkeys(FALSE,False)))
        guard(sources);require(sha(Path(r['path']).read_bytes())==r['sha256'] and sha(Path(publication['path']).read_bytes())==publication['sha256'],'Final output bytes');return r
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(exc),retry_allowed=False));raise

if __name__=='__main__':print(json.dumps(run()))
