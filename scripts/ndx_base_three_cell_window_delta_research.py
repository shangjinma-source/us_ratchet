"""Separate BASE window delta plan, explicit probes and externally bound resume."""
from copy import deepcopy
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_base_window_delta_research as adapter
from scripts import ndx_non_equal_base_runner as original
from scripts.ndx_joint_weight_verify import _restore_input

SELF=Path(__file__).resolve();LOADED=hashlib.sha256(SELF.read_bytes()).hexdigest()
DIRECTORY=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1'
CLASSIFICATION=DIRECTORY/'three_cell_saved_dependency_20260912.json'
CLASSIFICATION_SHA='ae3fed1689457034fbe51227de1f9202a3b9602e6e0a95afa3657fdae2771da0'
K1=DIRECTORY/'base_k1_three_cell_plan_20260912.json'
K1_SHA='25596548b56e164be036419c1919ac875dd6025a31197fbaa046a4d5ac90c078'
REVIEW=DIRECTORY/'root_return_semantics_review_20260912.json'
REVIEW_SHA='a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b'
OUTPUT=ROOT/'data/cache/research/base_three_cell_window_delta_20260912_v1'
ERRORS=[dict(ticker='GOOG',session='2022-07-18',old=0.,new=-0.025335378898117544),
        dict(ticker='FTNT',session='2022-06-23',old=0.,new=0.019968386675822902),
        dict(ticker='GOOGL',session='2022-07-18',old=0.,new=-0.024580059928059006)]


def read(path,sha):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External artifact SHA differs')
    return json.loads(raw)


def merge(*mappings):
    result={}
    for mapping in mappings:
        for path,sha in mapping.items():
            if path in result and result[path]!=sha:raise ValueError('Conflicting source SHA')
            result[path]=sha
    return result


def publish(path,value):
    path=Path(path);raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    if path.exists():
        if path.read_bytes()!=raw:raise ValueError('Immutable existing artifact differs')
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        descriptor,temporary=tempfile.mkstemp(prefix='.publishing-',suffix='.tmp',dir=path.parent)
        try:
            with os.fdopen(descriptor,'wb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            try:os.link(temporary,path)
            except FileExistsError:
                if path.read_bytes()!=raw:raise ValueError('Concurrent immutable artifact differs')
        finally:
            Path(temporary).unlink(missing_ok=True)
    return dict(path=str(path.resolve()),sha256=hashlib.sha256(raw).hexdigest())


def build_plan():
    classified=read(CLASSIFICATION,CLASSIFICATION_SHA);k1=read(K1,K1_SHA);review=read(REVIEW,REVIEW_SHA)
    if classified['errors']!=ERRORS:raise ValueError('Exact three corrections required')
    metadata=merge({str(SELF):LOADED,str(adapter.SOURCE):adapter.LOADED,
        str(adapter.recovery.SOURCE):adapter.recovery.LOADED,
        str(adapter.recovery.equivalence.SOURCE):adapter.recovery.equivalence.LOADED_SHA,
        str(CLASSIFICATION):CLASSIFICATION_SHA,str(K1):K1_SHA,str(REVIEW):REVIEW_SHA},original._LOADED,
        adapter.base._sources(),adapter.recovery.equivalence.previous.LOADED)
    dates=[];seen=set();k1_seen=set();total=0
    for date in sorted(classified['masks_by_date']):
        rows=sorted(classified['buckets'][date+'|NON_EQUAL_BASE|SELECTED_INPUT_CHANGED'],key=lambda r:r['task']['job_id'])
        context_paths={str(Path(row['checkpoint_path']).parent/'context.json') for row in rows}
        if len(context_paths)!=1:raise ValueError('One original BASE context per date required')
        context_path,=context_paths
        checkpoint=read(rows[0]['checkpoint_path'],rows[0]['checkpoint_sha256'])
        context_sha=checkpoint['context_sha256'];context=read(context_path,context_sha)
        location,=[r for r in review['actual_window_error_locations'] if r['coordinate']['selection_date']==date]
        typed_sha=location['context_sha256']
        typed_path,=[p for p,h in review['source_hashes'].items() if h==typed_sha and Path(p).name=='context.json']
        if context['source_hashes'].get(typed_path)!=typed_sha:raise ValueError('Original typed context not bound')
        sources=merge(metadata,context['source_hashes'],{context_path:context_sha,typed_path:typed_sha})
        tasks=[]
        for row in rows:
            task=row['task'];identifier=task['job_id']
            if identifier in seen or task not in context['tasks']:raise ValueError('Original task denominator differs')
            seen.add(identifier);sources[row['checkpoint_path']]=row['checkpoint_sha256']
            single=task['holding_count']==1
            if single:k1_seen.add(identifier)
            else:total+=1
            tasks.append(dict(**row,group='K1_SEPARATE_NO_FIT' if single else 'K_GE_2_WINDOW_REFIT',
                new_job_id=original._sha(dict(schema='ndx_base_three_cell_delta_task_v2',parent_task=task,
                    parent_checkpoint_sha256=row['checkpoint_sha256'],errors=ERRORS,
                    adapter_sha256=adapter.LOADED,runner_sha256=LOADED))))
        original._verify_sources(sources)
        dates.append(dict(date=date,coordinate=location['coordinate'],tasks=tasks,source_hashes=sources,
            context_path=context_path,context_sha256=context_sha,typed_context_path=typed_path,typed_context_sha256=typed_sha,
            runtime=context['runtime'],planned_k_ge_2=sum(row['group']=='K_GE_2_WINDOW_REFIT' for row in tasks),
            planned_k1=sum(row['group']=='K1_SEPARATE_NO_FIT' for row in tasks)))
    if total!=15488 or len(k1_seen)!=90 or k1_seen!={r['task']['job_id'] for r in k1['tasks']}:
        raise ValueError('Exact 15488 plus independent 90 denominator required')
    # Probe choices use only original date/job ordering, never economic metrics.
    probes={}
    all_rows=[(day,row) for day in dates for row in day['tasks']]
    for kind in ('anchored','non_anchor','k1'):
        eligible=[(day,row) for day,row in all_rows if (row['group']=='K1_SEPARATE_NO_FIT' if kind=='k1' else
            row['group']=='K_GE_2_WINDOW_REFIT' and (row['task']['weight_spec']=='constrained_fixed_shrinkage_turnover_anchor')==(kind=='anchored'))]
        day,row=min(eligible,key=lambda pair:(pair[0]['date'],pair[1]['task']['job_id']))
        probes[kind]=dict(date=day['date'],new_job_id=row['new_job_id'],parent_task=row['task'])
    return dict(schema='ndx_base_three_cell_window_delta_plan_v2',dates=dates,probes=probes,errors=ERRORS,
        planned_k_ge_2=15488,planned_k1=90,existing_2444_batch_included=False,
        source_hashes=metadata,historical_training_performed=False,promotion_allowed=False)


def load_plan(path,sha):
    plan=read(path,sha)
    if plan['schema']!='ndx_base_three_cell_window_delta_plan_v2' or plan['errors']!=ERRORS:
        raise ValueError('Original separate plan required')
    if plan['source_hashes'].get(str(SELF))!=LOADED or plan['source_hashes'].get(str(adapter.SOURCE))!=adapter.LOADED:
        raise ValueError('Plan and loaded adapter sources differ')
    return plan


def prepare_date(plan,date):
    day,=[d for d in plan['dates'] if d['date']==date]
    original._verify_sources(day['source_hashes'])
    context=read(day['context_path'],day['context_sha256'])
    typed=read(day['typed_context_path'],day['typed_context_sha256'])
    inputs={k:_restore_input(v) for k,v in typed['prepared_inputs'].items()}
    changed=deepcopy(inputs)
    for error in ERRORS:
        if changed['returns'].loc[error['session'],error['ticker']]!=error['old']:raise ValueError('Original cell differs')
        changed['returns'].loc[error['session'],error['ticker']]=error['new']
    return dict(day=day,inputs=inputs,corrected_inputs=changed,context=context)


def execute_task(prepared,row):
    day=prepared['day']
    if row not in day['tasks']:raise ValueError('Task not in complete date plan')
    expected=deepcopy(prepared['inputs'])
    for error in ERRORS:
        if expected['returns'].loc[error['session'],error['ticker']]!=error['old']:raise ValueError('Original repair cell differs')
        expected['returns'].loc[error['session'],error['ticker']]=error['new']
    if adapter._input_digest(expected)!=adapter._input_digest(prepared['corrected_inputs']):
        raise ValueError('Unlisted corrected input change')
    arguments=dict(task=row['task'],inputs=prepared['inputs'],engine='non_equal_fractional_v1',
        runtime=day['runtime'],source_hashes=day['source_hashes'])
    started=perf_counter()
    result=adapter.evaluate_window_delta(arguments=arguments,corrected_inputs=prepared['corrected_inputs'],
        checkpoint_path=row['checkpoint_path'],checkpoint_sha256=row['checkpoint_sha256'],
        context_path=day['context_path'],context_sha256=day['context_sha256'],
        typed_context_path=day['typed_context_path'],typed_context_sha256=day['typed_context_sha256'])
    elapsed=perf_counter()-started
    if any(day['source_hashes'].get(path)!=sha for path,sha in result['source_hashes'].items()):
        raise ValueError('Task numerical closure absent from shared date context')
    if row['group']=='K1_SEPARATE_NO_FIT' and result['refitted_window_count']!=0:
        raise ValueError('Single-name branch unexpectedly fitted')
    return result,elapsed


def run_probe(plan,kind):
    choice=plan['probes'][kind];prepared=prepare_date(plan,choice['date'])
    row,=[r for r in prepared['day']['tasks'] if r['new_job_id']==choice['new_job_id']]
    destination=OUTPUT/'probes'/(kind+'.json')
    if destination.exists():raise FileExistsError('Existing probe must be verified, not repeated')
    result,elapsed=execute_task(prepared,row)
    original._verify_sources(result['source_hashes'])
    published=publish(destination,dict(schema='ndx_base_window_delta_probe_v1',probe_selection_rule='FIRST_DATE_THEN_ORIGINAL_JOB_ID',
        selected=choice,result=result,elapsed_seconds=elapsed,global_planned_k_ge_2=15488,global_planned_k1=90,
        whole_batch_executed=False,promotion_allowed=False))
    original._verify_sources(result['source_hashes'])
    return published


def validate_resume_entry(entry,day,context_ref):
    value=read(entry['path'],entry['sha256']);identifier=value['new_job_id']
    matches=[r for r in day['tasks'] if r['new_job_id']==identifier]
    if (len(matches)!=1 or value['context']!=context_ref or value['original']!=matches[0]
        or value.get('schema')!='ndx_base_window_delta_checkpoint_v1'
        or value.get('status')!='EVALUATED_ORIGINAL_BASE_WINDOW_DELTA'
        or value.get('promotion_allowed') is not False):raise ValueError('Resume original task differs')
    return identifier


def run_date(plan,date,*,plan_path,plan_sha256,max_new_tasks,resume_index=None,resume_index_sha256=None):
    if type(max_new_tasks) is not int or max_new_tasks<1:raise ValueError('Explicit positive new-task budget required')
    if plan!=read(plan_path,plan_sha256):raise ValueError('External plan differs')
    prepared=prepare_date(plan,date);day=prepared['day'];folder=OUTPUT/date.replace('-','')
    context=dict(schema='ndx_base_window_delta_date_v1',plan_path=str(plan_path),plan_sha256=plan_sha256,day=day)
    context_ref=publish(folder/'context.json',context)
    completed={}
    if resume_index is not None:
        if resume_index_sha256 is None:raise ValueError('External completion index SHA required')
        prior=read(resume_index,resume_index_sha256)
        if prior['context']!=context_ref:raise ValueError('Resume date context differs')
        for entry in prior['completed']:
            identifier=validate_resume_entry(entry,day,context_ref)
            if identifier in completed:raise ValueError('Duplicate resume task')
            completed[identifier]=entry
    attempted=0;latest=None
    for row in day['tasks']:
        identifier=row['new_job_id']
        if identifier in completed:continue
        if attempted>=max_new_tasks:break
        attempted+=1
        result,elapsed=execute_task(prepared,row)
        result.pop('source_hashes')
        checkpoint=dict(schema='ndx_base_window_delta_checkpoint_v1',new_job_id=identifier,context=context_ref,
            original=row,result=result,status='EVALUATED_ORIGINAL_BASE_WINDOW_DELTA',promotion_allowed=False)
        # An unindexed leftover is accepted only after full new numerical reconstruction.
        completed[identifier]=publish(folder/(identifier+'.json'),checkpoint)
        index=dict(schema='ndx_base_window_delta_completion_index_v1',context=context_ref,
            completed=[completed[r['new_job_id']] for r in day['tasks'] if r['new_job_id'] in completed],
            planned_k_ge_2=day['planned_k_ge_2'],planned_k1=day['planned_k1'],status='PARTIAL',promotion_allowed=False)
        latest=publish(folder/('index_'+original._sha(index)+'.json'),index)
        print(json.dumps(dict(date=date,completed=len(completed),planned=len(day['tasks']),
            last_task_seconds=elapsed,external_completion_index=latest)),flush=True)
    # Never call a date complete until the whole original source closure passes again.
    original._verify_sources(day['source_hashes'])
    final=dict(schema='ndx_base_window_delta_completion_index_v1',context=context_ref,
        completed=[completed[r['new_job_id']] for r in day['tasks'] if r['new_job_id'] in completed],
        planned_k_ge_2=day['planned_k_ge_2'],planned_k1=day['planned_k1'],
        status='COMPLETE' if len(completed)==len(day['tasks']) else 'PARTIAL',promotion_allowed=False)
    latest=publish(folder/('index_'+original._sha(final)+'.json'),final)
    original._verify_sources(day['source_hashes'])
    return dict(**latest,status=final['status'],attempted=attempted,completed=len(completed))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-plan',action='store_true');parser.add_argument('--plan-path');parser.add_argument('--plan-sha256')
    parser.add_argument('--probe-kind',choices=('anchored','non_anchor','k1'));parser.add_argument('--selection-date')
    parser.add_argument('--execute',action='store_true');parser.add_argument('--max-new-tasks',type=int)
    parser.add_argument('--resume-index');parser.add_argument('--resume-index-sha256');options=parser.parse_args()
    if options.build_plan:
        print(json.dumps(publish(OUTPUT/'sealed_plan_v2.json',build_plan())))
    else:
        plan=load_plan(options.plan_path,options.plan_sha256)
        if not options.execute:
            print(json.dumps(dict(planned_k_ge_2=15488,planned_k1=90,probes=plan['probes'],training_performed=False)))
        elif options.probe_kind:print(json.dumps(run_probe(plan,options.probe_kind)))
        else:print(json.dumps(run_date(plan,options.selection_date,plan_path=options.plan_path,plan_sha256=options.plan_sha256,
            max_new_tasks=options.max_new_tasks,resume_index=options.resume_index,resume_index_sha256=options.resume_index_sha256)))
