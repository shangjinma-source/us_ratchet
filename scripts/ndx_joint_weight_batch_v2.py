"""Isolated v2 batch: fixed old input captures, never reuse old results."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_joint_weight_batch as original
from scripts.ndx_joint_weight_verify import _restore, _restore_input
from backtest import ndx_joint_weight_runner as old_runner
from backtest import ndx_joint_weight_runner_v2 as runner
from backtest.ndx_joint_weight_evaluation_v2 import _bind
from backtest.ndx_joint_weight_history_inputs import _Sources, prepare_joint_weight_history_inputs

BATCH_ROOT=ROOT/'data/cache/research/ndx_joint_weight_batches_v2'
DEPENDENCIES=tuple(sorted(set(runner.NUMERICAL_SOURCES)|{
    'scripts/ndx_joint_weight_batch_v2.py','scripts/ndx_joint_weight_batch.py',
    'scripts/ndx_joint_weight_verify.py','backtest/ndx_joint_weight_history_inputs.py',
    'backtest/ndx_cardinality_capital_replay_summary.py','data/ndx_security_identity.py'}))


def _require(condition,message):
    if not condition:
        raise ValueError(message)


def dependency_hashes():
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in DEPENDENCIES}


def load_frozen_inputs(manifest_path,plan):
    sources=_Sources()
    path=Path(manifest_path).resolve();raw=path.read_bytes();sources.observe(path,raw)
    manifest=json.loads(raw)
    _require(set(manifest)=={'schema','original_experiment_sha256','captures'}
        and manifest['schema']=='ndx_joint_weight_frozen_inputs_v1'
        and manifest['original_experiment_sha256']==plan['experiment_sha256'], 'Frozen manifest experiment/schema differs')
    _require(isinstance(manifest['captures'],list),'Frozen captures must be a list')
    coordinate_map={p['child_sha256']:p for p in plan['plans']}
    frozen={}
    for descriptor in manifest['captures']:
        _require(isinstance(descriptor,dict) and set(descriptor)=={'path','sha256'},'Invalid frozen descriptor')
        captured_raw=sources.read(descriptor)
        captured=json.loads(captured_raw)
        _require(old_runner._json_bytes(captured)==captured_raw,'Noncanonical frozen capture')
        digest=captured.pop('capture_sha256',None)
        _require(digest==old_runner._sha(captured),'Frozen capture checksum differs')
        _require(set(captured)=={'schema','experiment_sha256','cli_sha256','tasks','prepared_inputs',
            'source_evidence','numerical_sources','runtime','panel_metadata'}
            and captured['schema']=='ndx_joint_weight_batch_capture_v1'
            and captured['experiment_sha256']==plan['experiment_sha256'],'Frozen capture schema/experiment differs')
        _require(captured['numerical_sources']==old_runner._source_hashes(),'Frozen v1 source contract differs')
        tasks=captured['tasks']
        _require(isinstance(tasks,list) and bool(tasks),'Frozen capture tasks missing')
        for task in tasks:
            old_runner._validate_task(task)
        child=tasks[0]['child_manifest_sha256']
        _require(child in coordinate_map and child not in frozen,'Unknown/duplicate frozen coordinate')
        _require(old_runner._json_bytes(tasks)==old_runner._json_bytes(coordinate_map[child]['tasks']),
                 'Frozen capture full task plan differs')
        inputs={k:_restore_input(v) for k,v in captured['prepared_inputs'].items()}
        _require(set(inputs)=={'universe','returns','target_returns','nominal_prices','incumbent_weights','contract'},
                 'Frozen prepared fields differ')
        _require(old_runner._json_bytes(old_runner._normalize(inputs['contract']))==
                 old_runner._json_bytes(old_runner._normalize(plan['experiment']['evaluation_contract'])),
                 'Frozen evaluation contract differs')
        evidence=_restore(captured['source_evidence'])
        _require(old_runner._json_bytes(old_runner._normalize(evidence))==old_runner._json_bytes(captured['source_evidence'])
                 and evidence['experiment_sha256']==plan['experiment_sha256']
                 and evidence['cli_sha256']==captured['cli_sha256'],'Frozen source evidence differs')
        frozen[child]=dict(inputs=inputs,provenance=dict(
            frozen_capture=dict(descriptor),frozen_capture_internal_sha256=digest,
            original_capture_source_evidence=evidence,old_results_reused=False))
    sources.validate_unchanged()
    return dict(frozen=frozen,sources=sources,manifest_sha256=hashlib.sha256(raw).hexdigest())


def namespace_hash(experiment_sha256,manifest_sha256,dependencies):
    return old_runner._sha(dict(experiment_sha256=experiment_sha256,
        frozen_input_manifest_sha256=manifest_sha256,dependency_sources=dependencies))


def build_versioned_plan(experiment_path,frozen_input_manifest_path):
    dependencies=dependency_hashes()
    _require(dependencies==_LOADED_DEPENDENCIES,'V2 batch dependencies changed since import')
    plan=original.build_plan(experiment_path)
    bundle=load_frozen_inputs(frozen_input_manifest_path,plan)
    namespace=namespace_hash(plan['experiment_sha256'],bundle['manifest_sha256'],dependencies)
    plan['sources'].validate_unchanged();bundle['sources'].validate_unchanged()
    _require(dependency_hashes()==dependencies,'V2 batch dependencies changed during planning')
    return dict(plan=plan,frozen_bundle=bundle,dependencies=dependencies,
                namespace_sha256=namespace,capture_destination=BATCH_ROOT/namespace)


def bound_executor(frozen_bundle,dependencies):
    def prepare(path,child_sha256,**kwargs):
        if child_sha256 in frozen_bundle['frozen']:
            item=frozen_bundle['frozen'][child_sha256]
            value=dict(item['inputs'],provenance=item['provenance'])
        else:
            value=prepare_joint_weight_history_inputs(path,child_sha256,**kwargs)
        value['provenance']=dict(value['provenance'],
            frozen_input_manifest_sha256=frozen_bundle['manifest_sha256'],
            v2_batch_dependency_sources=dependencies,old_results_reused=False)
        return value
    capture=_bind(original._captured_inputs,_source_hashes=runner.source_hashes,
                  prepare_joint_weight_history_inputs=prepare)
    return _bind(original.execute_plan,_captured_inputs=capture,
                 run_joint_weight_tasks=runner.run_joint_weight_tasks_v2)


def run(experiment_path,frozen_input_manifest_path,*,execute=False,max_new_evaluations=None):
    _require(type(execute) is bool,'Explicit execute flag required')
    if execute:
        _require(type(max_new_evaluations) is int and max_new_evaluations>0,'Positive global budget required')
    dependencies=dependency_hashes()
    _require(dependencies==_LOADED_DEPENDENCIES,'V2 batch dependencies changed since import')
    protected={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in original.PROTECTED}
    plan=bundle=None
    try:
        plan=original.build_plan(experiment_path)
        bundle=load_frozen_inputs(frozen_input_manifest_path,plan)
        namespace=namespace_hash(plan['experiment_sha256'],bundle['manifest_sha256'],dependencies)
        if not execute:
            return dict(status='PLAN_ONLY',planned=plan['planned'],coordinates=len(plan['plans']),
                frozen_coordinates=len(bundle['frozen']),namespace_sha256=namespace,
                old_results_reused=False,promotion_allowed=False)
        destination=BATCH_ROOT/namespace
        destination.mkdir(parents=True,exist_ok=True)
        with old_runner._lock(destination/'.lock'):
            result=bound_executor(bundle,dependencies)(plan,max_new_evaluations=max_new_evaluations,
                destination=destination,cli_hash=dependencies['scripts/ndx_joint_weight_batch_v2.py'])
        return dict(result,namespace_sha256=namespace,old_results_reused=False,
            frozen_input_manifest_sha256=bundle['manifest_sha256'],dependency_sources=dependencies)
    finally:
        if plan is not None:
            plan['sources'].validate_unchanged()
        if bundle is not None:
            bundle['sources'].validate_unchanged()
        _require(dependency_hashes()==dependencies,'V2 batch dependencies changed during run')
        _require(protected=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in original.PROTECTED},
                 'Protected live files changed during v2 batch')


_LOADED_DEPENDENCIES=dependency_hashes()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',required=True)
    parser.add_argument('--frozen-input-manifest',required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--max-new-evaluations',type=int)
    args=parser.parse_args()
    print(json.dumps(run(args.experiment,args.frozen_input_manifest,execute=args.execute,
        max_new_evaluations=args.max_new_evaluations),ensure_ascii=False,indent=2))
