"""Prepare the exact 614 DELTA paired-only tasks; execute one explicit first probe."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_delta_paired_trace_recovery_research as adapter
from scripts import ndx_base_three_cell_window_delta_research as original
from scripts.ndx_joint_weight_verify import _restore_input
SELF=Path(__file__).resolve();LOADED=hashlib.sha256(SELF.read_bytes()).hexdigest()
CLASSIFICATION=original.CLASSIFICATION;CLASSIFICATION_SHA=original.CLASSIFICATION_SHA
GOOG_REPORT=original.REVIEW;GOOG_SHA=original.REVIEW_SHA
EXTRA_REPORT=ROOT/'data/cache/research/legacy_pool_additional_split_probe_20260912_v1/report.json'
EXTRA_SHA='64e6c86a9ad8045dcb925990c04a7d00c8480cdec2e922ef215e9ed839acd850'
INVENTORY=ROOT/'data/cache/research/dynamic_frozen_v2/combined_summary_inventory_20260912.json'
INVENTORY_SHA='baa74f6447e4663ac13a0b4174ad0fa0cf0d799ce3d35a735c9f25379e24ca09'
ERRORS=deepcopy(original.ERRORS)
OUTPUT=ROOT/'data/cache/research/delta_three_cell_paired_trace_20260912_v1'


def _sources():
    return original.merge(adapter.trace.source_hashes(),adapter.equivalence.previous.numerical_source_hashes('joint_weight_v3'),adapter.equivalence.previous.LOADED,
        {str(SELF):LOADED,str(adapter.SOURCE):adapter.LOADED,str(adapter.equivalence.SOURCE):adapter.equivalence.LOADED_SHA,
         str(original.SELF):original.LOADED,str(CLASSIFICATION):CLASSIFICATION_SHA,str(GOOG_REPORT):GOOG_SHA,str(EXTRA_REPORT):EXTRA_SHA,
         str(INVENTORY):INVENTORY_SHA})


def apply_three(inputs):
    changed=deepcopy(inputs)
    for error in ERRORS:
        if changed['returns'].loc[error['session'],error['ticker']]!=error['old']:raise ValueError('Original evidenced cell differs')
        changed['returns'].loc[error['session'],error['ticker']]=error['new']
    return changed


def check_paired(task,inputs):
    contract=inputs['contract'];returns=inputs['returns'];fit=contract['fit_days'];window=contract['window_days']
    starts=list(range(fit,len(returns)-window+1,contract['step_days']));selected=set(task['tickers'].split(';'));incumbent=False
    if task['weight_spec'] not in ('constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor'):
        raise ValueError('Original fitted DELTA task required')
    for error in ERRORS:
        position=returns.index.get_loc(error['session'])
        selected_effect=any(s-fit<=position<s+window for s in starts)
        if error['ticker'] in selected and selected_effect:raise ValueError('Task is not paired-only under three corrections')
        incumbent|=inputs['incumbent_weights'].get(error['ticker'],0)>0 and any(s<=position<s+window for s in starts)
    if not incumbent:raise ValueError('No incumbent-forward error dependency')


def task_context_reference(row,sources):
    path=str(Path(row['checkpoint_path']).parent/'context.json')
    if path not in sources:raise ValueError('External original task context source absent')
    return dict(context_path=path,context_sha256=sources[path])


def build_plan():
    classified=original.read(CLASSIFICATION,CLASSIFICATION_SHA)
    if classified['errors']!=ERRORS or classified['counts']['DELTA|PAIRED_ONLY_NO_REFIT']!=614:raise ValueError('Exact three-cell 614 classification required')
    evidence=[original.read(GOOG_REPORT,GOOG_SHA),original.read(EXTRA_REPORT,EXTRA_SHA)]
    inventory=original.read(INVENTORY,INVENTORY_SHA)
    sources=original.merge(_sources(),classified['source_hashes'],*(entry['source_hashes'] for entry in evidence))
    original.original._verify_sources(sources)
    dates=[];seen=set()
    for date in sorted(classified['masks_by_date']):
        rows=sorted(classified['buckets'].get(date+'|DELTA|PAIRED_ONLY_NO_REFIT',[]),key=lambda row:row['task']['job_id'])
        if not rows:continue
        descriptor,=[entry for entry in inventory['summaries'] if entry['coordinate']['selection_date']==date]
        summary=original.read(descriptor['path'],descriptor['sha256'])
        sources=original.merge(sources,summary['source_hashes'],{descriptor['path']:descriptor['sha256']})
        contexts={}
        tasks=[]
        for row in rows:
            reference=task_context_reference(row,sources);context_path=reference['context_path'];context_sha=reference['context_sha256']
            if context_path not in contexts:
                context=original.read(context_path,context_sha)
                if context['numerical_sources']!=adapter.trace.full._LOADED_SOURCES:raise ValueError('Original DELTA source closure differs')
                inputs={key:_restore_input(value) for key,value in context['prepared_inputs'].items()};apply_three(inputs)
                contexts[context_path]=(context,inputs)
            context,inputs=contexts[context_path]
            task=row['task'];identifier=task['job_id']
            if identifier in seen or task not in context['tasks'] or task['selection_date']!=date:raise ValueError('Duplicate or different task coordinate')
            if sources.get(row['checkpoint_path'])!=row['checkpoint_sha256']:raise ValueError('Original checkpoint source differs')
            checkpoint=original.read(row['checkpoint_path'],row['checkpoint_sha256'])
            payload=deepcopy(checkpoint);digest=payload.pop('checkpoint_sha256')
            if (payload['context_sha256']!=adapter.encoding._sha(context) or payload['task']!=task or
                payload['status']!='EVALUATED' or digest!=adapter.encoding._sha(payload)):raise ValueError('Original checkpoint/context differs')
            check_paired(task,inputs);seen.add(identifier)
            tasks.append(dict(**row,context_path=context_path,context_sha256=context_sha,runtime=context['runtime'],new_job_id=adapter.encoding._sha(dict(schema='ndx_delta_three_cell_paired_task_v1',
                task=task,checkpoint_sha256=row['checkpoint_sha256'],errors=ERRORS,adapter_sha256=adapter.LOADED,runner_sha256=LOADED))))
        dates.append(dict(date=date,context_count=len(contexts),tasks=tasks,planned=len(tasks)))
    if len(seen)!=614 or len(dates)!=10:raise ValueError('Exact 614 task / 10 date denominator required')
    original.original._verify_sources(sources)
    return dict(schema='ndx_delta_three_cell_paired_plan_v1',dates=dates,planned=614,errors=ERRORS,source_hashes=sources,
        probe=dict(date=dates[0]['date'],task=dates[0]['tasks'][0]),probe_selection='FIRST_DATE_THEN_ORIGINAL_JOB_ID_NO_ECONOMIC_SORT',
        trace_recovery_requires_original_v3_execution=True,historical_training_performed=False,promotion_allowed=False)


def load_plan(path,sha):
    plan=original.read(path,sha)
    if plan['schema']!='ndx_delta_three_cell_paired_plan_v1' or plan['planned']!=614 or plan['errors']!=ERRORS:
        raise ValueError('Exact external three-cell DELTA plan required')
    for source,digest in _sources().items():
        if plan['source_hashes'].get(source)!=digest:raise ValueError('Plan loaded source differs')
    classified=original.read(CLASSIFICATION,CLASSIFICATION_SHA)
    for source,digest in classified['source_hashes'].items():
        if plan['source_hashes'].get(source)!=digest:raise ValueError('Plan omitted classification source closure')
    expected_dates=[date for date in sorted(classified['masks_by_date']) if classified['buckets'].get(date+'|DELTA|PAIRED_ONLY_NO_REFIT')]
    if [day['date'] for day in plan['dates']]!=expected_dates:raise ValueError('Plan date order/denominator differs')
    inventory=original.read(INVENTORY,INVENTORY_SHA)
    for day in plan['dates']:
        descriptor,=[entry for entry in inventory['summaries'] if entry['coordinate']['selection_date']==day['date']]
        summary=original.read(descriptor['path'],descriptor['sha256'])
        for source,digest in summary['source_hashes'].items():
            if plan['source_hashes'].get(source)!=digest:raise ValueError('Plan omitted original summary source')
        expected=sorted(classified['buckets'][day['date']+'|DELTA|PAIRED_ONLY_NO_REFIT'],key=lambda row:row['task']['job_id'])
        if [{key:row[key] for key in ('task','checkpoint_path','checkpoint_sha256')} for row in day['tasks']]!=expected:
            raise ValueError('Plan exact original task set/order differs')
        for row in day['tasks']:
            if task_context_reference(row,summary['source_hashes'])!={key:row[key] for key in ('context_path','context_sha256')}:
                raise ValueError('Plan original task context source differs')
        if day['context_count']!=len({row['context_path'] for row in day['tasks']}):raise ValueError('Plan context denominator differs')
    if sum(len(day['tasks']) for day in plan['dates'])!=614:raise ValueError('Incomplete DELTA task denominator')
    original.original._verify_sources(plan['source_hashes'])
    return plan


def run_first_probe(*,plan_path,plan_sha256,output):
    path=Path(output)
    if path.exists():raise FileExistsError('Probe already exists; verify external SHA without repeating trace')
    plan=load_plan(plan_path,plan_sha256);day=plan['dates'][0];row=day['tasks'][0]
    if plan['probe']!=dict(date=day['date'],task=row):raise ValueError('First structural probe selection differs')
    context=original.read(row['context_path'],row['context_sha256'])
    inputs={key:_restore_input(value) for key,value in context['prepared_inputs'].items()};check_paired(row['task'],inputs)
    corrected=apply_three(inputs);sources=original.merge(plan['source_hashes'],{str(Path(plan_path).resolve()):plan_sha256})
    started=perf_counter()
    result=adapter.recover_paired_delta(arguments=dict(task=row['task'],inputs=inputs,engine='joint_weight_v3',runtime=row['runtime'],source_hashes=sources),
        corrected_inputs=corrected,context_path=row['context_path'],context_sha256=row['context_sha256'],
        checkpoint_path=row['checkpoint_path'],checkpoint_sha256=row['checkpoint_sha256'])
    elapsed=perf_counter()-started
    saved=original.publish(path,dict(schema='ndx_delta_three_cell_paired_probe_v1',plan_path=str(Path(plan_path).resolve()),
        plan_sha256=plan_sha256,selected=plan['probe'],result=result,elapsed_seconds=elapsed,planned=614,
        whole_batch_executed=False,promotion_allowed=False))
    original.original._verify_sources(result['source_hashes'])
    return dict(**saved,elapsed_seconds=elapsed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--first-probe',action='store_true');parser.add_argument('--plan-path');parser.add_argument('--plan-sha256')
    parser.add_argument('--output');options=parser.parse_args()
    if options.prepare==options.first_probe:raise ValueError('Explicit prepare OR first-probe required')
    if options.prepare:
        destination=Path(options.output) if options.output else OUTPUT/'plan.json'
        if destination.exists():raise FileExistsError('Existing plan must be externally verified')
        plan=build_plan();saved=original.publish(destination,plan);original.original._verify_sources(plan['source_hashes']);print(json.dumps(saved))
    else:
        if not options.plan_path or not options.plan_sha256:raise ValueError('External plan path and SHA required')
        print(json.dumps(run_first_probe(plan_path=options.plan_path,plan_sha256=options.plan_sha256,
            output=options.output or OUTPUT/'first_probe.json')))
