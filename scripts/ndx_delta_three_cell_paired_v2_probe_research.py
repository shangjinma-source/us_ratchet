"""Versioned 614-task preparation with one explicit historical loader gap."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_delta_three_cell_paired_probe_research as prior
from backtest import ndx_delta_paired_trace_recovery_v2_research as adapter
from scripts.ndx_joint_weight_verify import _restore_input
SELF=Path(__file__).resolve();LOADED=hashlib.sha256(SELF.read_bytes()).hexdigest()
PARENT_PLAN=prior.OUTPUT/'plan.json'
PARENT_SHA='aea80dcd9929a5bf266c68d21b308aba6254b39db8eb3cd7950fc1d64a0d890c'
OUTPUT=ROOT/'data/cache/research/delta_three_cell_paired_trace_20260912_v2'
SCOPE='NUMERICAL_RECONSTRUCTION_WITH_HISTORICAL_LOADER_PROVENANCE_GAP'


def source_hashes(parent):
    return prior.original.merge(parent['source_hashes'],{str(PARENT_PLAN):PARENT_SHA,str(SELF):LOADED,str(adapter.SOURCE):adapter.LOADED})


def projected_dates(parent):
    dates=deepcopy(parent['dates'])
    for day in dates:
        for row in day['tasks']:
            row['parent_new_job_id']=row['new_job_id']
            row['new_job_id']=adapter.encoding._sha(dict(schema='ndx_delta_paired_gap_task_v2',parent_plan_sha256=PARENT_SHA,
                parent_task=row['task'],original_checkpoint_sha256=row['checkpoint_sha256'],errors=prior.ERRORS,
                gap_path=adapter.GAP_PATH,gap_expected_sha256=adapter.GAP_EXPECTED_SHA,adapter_sha256=adapter.LOADED,runner_sha256=LOADED))
    return dates


def verify_observations(observations,sources):
    for path,entry in observations.items():
        context=prior.original.read(path,entry['context_sha256'])
        if adapter.validate_historical_evidence(context,sources)!=entry['gaps']:
            raise ValueError('Historical gap observation changed')


def prepare():
    parent=prior.load_plan(PARENT_PLAN,PARENT_SHA);sources=source_hashes(parent);dates=projected_dates(parent)
    observations={}
    for day in dates:
        for row in day['tasks']:
            path=row['context_path']
            if path in observations:continue
            context=prior.original.read(path,row['context_sha256'])
            gaps=adapter.validate_historical_evidence(context,sources)
            inputs={key:_restore_input(value) for key,value in context['prepared_inputs'].items()}
            prior.apply_three(inputs)
            observations[path]=dict(context_sha256=row['context_sha256'],gaps=gaps)
    prior.original.original._verify_sources(sources)
    verify_observations(observations,sources)
    return dict(schema='ndx_delta_three_cell_paired_gap_plan_v2',parent_plan_path=str(PARENT_PLAN),parent_plan_sha256=PARENT_SHA,
        dates=dates,planned=614,errors=prior.ERRORS,source_hashes=sources,context_count=len(observations),
        historical_context_gap_observations=observations,reconstruction_scope=SCOPE,
        probe=dict(date=dates[0]['date'],task=dates[0]['tasks'][0]),
        original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False,
        historical_training_performed=False)


def load_plan(path,sha):
    plan=prior.original.read(path,sha);parent=prior.load_plan(PARENT_PLAN,PARENT_SHA)
    if (plan['schema']!='ndx_delta_three_cell_paired_gap_plan_v2' or plan['parent_plan_sha256']!=PARENT_SHA or
        plan['parent_plan_path']!=str(PARENT_PLAN) or plan['planned']!=614 or plan['dates']!=projected_dates(parent) or
        plan['errors']!=prior.ERRORS or plan['reconstruction_scope']!=SCOPE or
        plan['original_historical_provenance_verified'] is not False or plan['point_in_time_verified'] is not False or
        plan['promotion_allowed'] is not False or plan['historical_training_performed'] is not False):
        raise ValueError('Exact limited numerical reconstruction plan required')
    if plan['source_hashes']!=source_hashes(parent):raise ValueError('Exact original numerical closure required')
    verify_observations(plan['historical_context_gap_observations'],plan['source_hashes'])
    expected={row['context_path']:row['context_sha256'] for day in plan['dates'] for row in day['tasks']}
    if ({path:entry['context_sha256'] for path,entry in plan['historical_context_gap_observations'].items()}!=expected or
        plan['context_count']!=len(expected)):raise ValueError('Complete per-context gap denominator required')
    prior.original.original._verify_sources(plan['source_hashes'])
    return plan


def run_first_probe(*,plan_path,plan_sha256,output):
    destination=Path(output)
    if destination.exists():raise FileExistsError('Existing probe must not repeat original trace')
    plan=load_plan(plan_path,plan_sha256);day=plan['dates'][0];row=day['tasks'][0]
    if plan['probe']!=dict(date=day['date'],task=row):raise ValueError('First structural task differs')
    context=prior.original.read(row['context_path'],row['context_sha256'])
    inputs={key:_restore_input(value) for key,value in context['prepared_inputs'].items()};prior.check_paired(row['task'],inputs)
    sources=prior.original.merge(plan['source_hashes'],{str(Path(plan_path).resolve()):plan_sha256})
    started=perf_counter()
    result=adapter.recover_paired_delta(arguments=dict(task=row['task'],inputs=inputs,engine='joint_weight_v3',runtime=row['runtime'],source_hashes=sources),
        corrected_inputs=prior.apply_three(inputs),context_path=row['context_path'],context_sha256=row['context_sha256'],
        checkpoint_path=row['checkpoint_path'],checkpoint_sha256=row['checkpoint_sha256'])
    elapsed=perf_counter()-started
    saved=prior.original.publish(destination,dict(schema='ndx_delta_three_cell_paired_gap_probe_v2',selected=plan['probe'],
        plan_path=str(Path(plan_path).resolve()),plan_sha256=plan_sha256,result=result,elapsed_seconds=elapsed,
        whole_batch_executed=False,planned=614,promotion_allowed=False,original_historical_provenance_verified=False))
    prior.original.original._verify_sources(result['source_hashes'])
    if adapter.validate_historical_evidence(context,result['source_hashes'])!=result['historical_loader_provenance_gaps']:
        raise ValueError('Historical gap observation changed during publication')
    return dict(**saved,elapsed_seconds=elapsed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--preflight',action='store_true');group.add_argument('--prepare',action='store_true');group.add_argument('--first-probe',action='store_true')
    parser.add_argument('--plan-path');parser.add_argument('--plan-sha256');parser.add_argument('--output');options=parser.parse_args()
    if options.preflight or options.prepare:
        plan=prepare()
        if options.preflight:print(json.dumps(dict(planned=plan['planned'],contexts=plan['context_count'],
            gaps=next(iter(plan['historical_context_gap_observations'].values()))['gaps'],historical_training_performed=False)))
        else:
            destination=Path(options.output) if options.output else OUTPUT/'plan.json'
            if destination.exists():raise FileExistsError('Existing plan must be externally verified')
            saved=prior.original.publish(destination,plan);prior.original.original._verify_sources(plan['source_hashes'])
            verify_observations(plan['historical_context_gap_observations'],plan['source_hashes']);print(json.dumps(saved))
    else:
        if not options.plan_path or not options.plan_sha256:raise ValueError('External plan required')
        print(json.dumps(run_first_probe(plan_path=options.plan_path,plan_sha256=options.plan_sha256,output=options.output or OUTPUT/'first_probe.json')))
