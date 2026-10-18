"""Independent saved-report census; never import producers, fitters or raw auditors."""
from collections import Counter
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASE=ROOT/'data/cache/research/dated_batch_summary_20261003_v1'
FULL=6222659648236112670
CATEGORIES=('RISK_PASSED','RISK_FAILED','NUMERICAL_EXCEPTION','VALIDATION_FAILURE','DISPATCHED_WITHOUT_ACCEPTED_READBACK','NOT_DISPATCHED')
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
READER=str(ROOT/'scripts/ndx_dated_single_task_independent_readback_20261003.py')
READER_SHA='bd63ce1541c63d3f38e90a7313666d37abcbb9b51cc9d2291f702ee8fad43cea'

def require(ok,message):
    if not ok:raise ValueError(message)

def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,message):require(enc(a)==enc(b),message)

def read(ref,sources):
    require(type(ref) is dict and set(ref)=={'path','sha256'},'Exact reference')
    path=ref['path'];blob=Path(path).read_bytes();require(sha(blob)==ref['sha256'],'Source bytes')
    require(path not in sources or sources[path]==ref['sha256'],'Source conflict');sources[path]=ref['sha256']
    def pairs(items):
        out={}
        for key,value in items:require(key not in out,'Duplicate JSON key');out[key]=value
        return out
    def invalid(value):raise ValueError('Nonfinite JSON')
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=invalid)

def inspect(summary,preparation,initial,batch,reports):
    materialized=preparation['materialized'];exact(materialized['materialized_task_count'],1632,'Materialized exact count');exact(materialized['full_plan_task_denominator'],FULL,'New full domain')
    require(len(materialized['combinations'])==544,'544 complete combos')
    for ci,c in enumerate(materialized['combinations']):
        exact([t['numerical_identity']['weight_spec'] for t in c['tasks']],list(SPECS),'Three ordered specs')
        for t in c['tasks']:
            exact(t['numerical_identity']['holding_count'],4+ci//32,'Ordered k coverage');require(t['numerical_identity']['requested_previous_target_weights'] is None,'None prior')
    tasks=[t for c in preparation['materialized']['combinations'] for t in c['tasks']]
    ids=[t['numerical_task_id'] for t in tasks]
    require(len(ids)==len(set(ids))==1632,'Full distinct queue')
    require(all(t['numerical_identity']['cutoff']=='2026-03-20' and sha(enc(t['numerical_identity']))==t['numerical_task_id'] for t in tasks),'Original identities')
    require(initial['schema']=='DATED_INITIAL_COMPLETED_TASKS_V1' and batch['schema']=='DATED_BATCH_RESULT_V1','Initial/batch schema')
    exact(initial['preparation_reference'],summary['input_references']['preparation'],'Initial preparation source');exact(batch['initial_completed_rows'],initial['rows'],'Initial rows unchanged');require(len(initial['rows'])==2,'Exactly two initial tasks')
    context=batch['batch_context'];exact(context['preparation_reference'],summary['input_references']['preparation'],'Batch preparation source');exact(context['initial_completed_reference'],summary['input_references']['initial'],'Batch initial source')
    exact(context['planned_total_task_count'],1632,'Batch total');exact(context['prior_completed_task_count'],2,'Batch prior two');require(context['old_cutoff_completion_reused'] is False,'No old cutoff reuse');require(context['ordered_task_ids_sha256']==sha(enc(ids)),'Full ordered batch identity digest')
    for role in ('initial',):
        r=summary['input_references'][role];require(context['source_hashes'].get(r['path'])==r['sha256'],'Batch source reference')
    require(context['source_hashes'].get(READER)==READER_SHA,'Batch reader pin')
    newrows=batch['newly_readback_rows'];exact(batch['new_readback_count'],len(newrows),'Exact batch readback count');exact(batch['planned_remaining_dispatch_count'],1630,'Remaining dispatch budget')
    for i,r in enumerate(newrows):exact(r['ordinal'],i,'Ordered new row ordinal')
    exact(batch['new_outcome_counts'],{c:sum(r['attempt_outcome']==c for r in newrows) for c in CATEGORIES[:4]},'Batch outcome counts')
    accepted=initial['rows']+batch['newly_readback_rows'];lookup={r['numerical_task_id']:r for r in accepted}
    require(len(lookup)==len(accepted) and set(reports)==set(lookup),'One report per accepted identity')
    exact(list(lookup),ids[:len(accepted)],'Original accepted prefix')
    unresolved=batch['unresolved_dispatched_task_ids'];pending=batch['undispatched_task_ids']
    require(type(unresolved) is list and len(unresolved)<=1 and type(pending) is list,'Bounded unresolved dispatch')
    exact(list(lookup)+unresolved+pending,ids,'Whole queue partition')
    failure=batch['failure']
    if failure is None:require(batch['status']=='BUDGETED_QUEUE_FINISHED' and not unresolved and not pending,'Finished complete partition')
    else:
        require(batch['status']=='STOPPED_WITH_EVIDENCE','Failure stop status')
        if failure.get('task_readback_saved') is True:
            require(not unresolved and 'dispatch_invoked' not in failure and newrows and failure['reason'] in CATEGORIES[2:4] and newrows[-1]['attempt_outcome']==failure['reason'] and failure['numerical_task_id']==accepted[-1]['numerical_task_id'],'Saved failed terminal')
        else:require(failure['reason']=='DISPATCH_OR_READBACK_FAILURE' and type(failure['dispatch_invoked']) is bool and failure['dispatch_invoked'] is bool(unresolved) and failure['numerical_task_id']==(unresolved or pending)[0],'Unaccepted dispatch failure')
    rows=summary['rows'];exact([r['numerical_task_id'] for r in rows],ids,'Saved full order')
    counts=Counter();coverage={}
    for i,(task,row) in enumerate(zip(tasks,rows)):
        tid=ids[i];identity=task['numerical_identity'];group=(identity['holding_count'],identity['weight_spec'])
        exact([row['k'],row['weight_spec']],list(group),'Original k/spec')
        pointer=dict(summary['input_references']['preparation'],json_pointer=f'/materialized/combinations/{i//3}/tasks/{i%3}')
        exact(row['task_reference'],pointer,'Original task pointer')
        if tid in lookup:
            report=reports[tid];require(report['schema']=='DATED_SINGLE_TASK_INDEPENDENT_READBACK_V1' and report['status']=='PASSED' and report['numerical_task_id']==tid,'Accepted saved audit')
            exact(report['materialized_task_denominator'],1632,'Report queue count');require(report['source_hashes'].get(READER)==READER_SHA,'Independent report source')
            for flag in ('runner_called','fitter_called','optimization_repeated','promotion_allowed','point_in_time_verified'):require(report[flag] is False,'Report authority')
            category=report['attempt_outcome'];require(category in CATEGORIES[:4],'Known terminal')
            if i>=2:require(category==lookup[tid]['attempt_outcome'],'Original outcome agrees')
            else:require(category in CATEGORIES[:2],'Initial risk result only')
            exact(row['independent_report_preserved'],report,'Complete original report')
            exact(row['saved_batch_row'],lookup[tid],'Complete batch row')
            exact(report['task_reference'],pointer,'Report parent identity')
            exact(report['postcheck_reference'],lookup[tid]['postcheck_reference'],'Report post anchor')
            exact(report['full_plan_task_denominator'],FULL,'No old-domain denominator')
        else:
            category='DISPATCHED_WITHOUT_ACCEPTED_READBACK' if tid in unresolved else 'NOT_DISPATCHED'
            require(row['saved_batch_row'] is None and row['independent_report_preserved'] is None,'No invented terminal')
        require(row['category']==category,'Classification from original report');counts[category]+=1
        coverage.setdefault(group,Counter())[category]+=1
    expected_counts={c:counts[c] for c in CATEGORIES};exact(summary['category_counts'],expected_counts,'All categories')
    expected_coverage=[dict(k=k,weight_spec=spec,planned_task_count=sum(v.values()),counts={c:v[c] for c in CATEGORIES}) for (k,spec),v in sorted(coverage.items())]
    exact(summary['k_spec_coverage'],expected_coverage,'Every k/spec cell')
    require(len(coverage)==51 and all(sum(v.values())==32 for v in coverage.values()),'Full fixed coverage')
    expected=dict(materialized_task_count=1632,accepted_independent_terminal_count=len(accepted),attempted_task_count=len(accepted)+len(unresolved),risk_passed_task_count=counts['RISK_PASSED'],risk_failed_task_count=counts['RISK_FAILED'],failed_terminal_task_count=counts['NUMERICAL_EXCEPTION']+counts['VALIDATION_FAILURE'],unresolved_dispatched_count=len(unresolved),undispatched_count=len(pending),full_new_cutoff_task_denominator=FULL,remaining_without_accepted_terminal_count=FULL-len(accepted),old_different_cutoff_completed_count_deducted=0)
    for k,v in expected.items():exact(summary[k],v,'Integer count '+k)
    exact(summary['initial_rows_preserved'],initial['rows'],'Initial rows');exact(summary['batch_failure_preserved'],batch['failure'],'Failure preserved')
    for k in ('fit_performed','raw_audit_repeated','old_cutoff_completion_reused','economic_comparison_performed','promotion_allowed','point_in_time_verified','execution_authorized','all_plan_tasks_completed'):require(summary[k] is False,'No authority upgrade')
    return dict(category_counts=expected_counts,k_spec_cell_count=51,report_count=len(reports),**expected)

def run(summary_reference,publication_reference):
    output=ROOT/'DYNAMIC_DATED_BATCH_SUMMARY_INDEPENDENT_READBACK_20261003.json'
    require(not output.exists(),'Already audited; reuse only')
    require(Path(summary_reference['path'])==BASE/'summary.json' and Path(publication_reference['path'])==BASE/'publication.json','Fixed source paths')
    require({p.name for p in BASE.iterdir()}=={'started.json','summary.json','publication.json'},'Complete source namespace')
    sources={str(SOURCE):LOADED};summary=read(summary_reference,sources);pub=read(publication_reference,sources)
    require(summary['schema']=='DATED_BATCH_SAVED_READBACK_SUMMARY_V1' and pub['schema']=='DATED_BATCH_SUMMARY_PUBLICATION_V1' and pub['status']=='PUBLISHED','Successful metadata publication')
    exact(pub['summary_reference'],summary_reference,'Publication anchor');exact(pub['source_hashes'],summary['source_hashes'],'Publication sources')
    parents={k:read(r,sources) for k,r in summary['input_references'].items()}
    reports={}
    for r in parents['initial']['rows']+parents['batch']['newly_readback_rows']:
        tid=r['numerical_task_id'];require(tid not in reports,'Duplicate report');reports[tid]=read(r['independent_readback_reference'],sources)
    counts=inspect(summary,parents['preparation'],parents['initial'],parents['batch'],reports)
    for p,h in summary['source_hashes'].items():require(p not in sources or sources[p]==h,'Source conflict');sources[p]=h
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Final byte guard')
    report=dict(schema='DATED_BATCH_SUMMARY_INDEPENDENT_READBACK_V1',status='PASS',summary_reference=summary_reference,publication_reference=publication_reference,source_hashes=sources,reader_sha256=LOADED,counts=counts,producer_called=False,fitter_called=False,old_raw_audit_repeated=False,point_in_time_verified=False,promotion_allowed=False,economic_comparison_performed=False)
    blob=enc(report)
    with output.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(output.read_bytes()==blob,'Durable audit')
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Post-publication source drift')
    return dict(path=str(output),sha256=sha(blob))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--summary-sha256',required=True);p.add_argument('--publication-sha256',required=True);a=p.parse_args()
    print(json.dumps(run(dict(path=str(BASE/'summary.json'),sha256=a.summary_sha256),dict(path=str(BASE/'publication.json'),sha256=a.publication_sha256))))
