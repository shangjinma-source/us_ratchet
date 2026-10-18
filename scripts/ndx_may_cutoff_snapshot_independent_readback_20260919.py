"""May-only finalized cutoff readback, with no seed and no fitter calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_first_cutoff_refit_independent_audit_20260919 as pure
from scripts.ndx_base_three_cell_window_delta_research import publish
archive=pure.archive
BASE=ROOT/'data/cache/research/corrected_frontier_cutoff_archive_20260919_v1'
QUEUE=BASE/'20230501_queue.json'
QUEUE_SHA='183b2aeafe7cf84b05945099b769f62ab4bacee68851a9ac4644501177bd64a8'
CONTEXT_SHA='d923eae195d884afb45b79a3ce990f74bb0959910dc6c4ae880a4914c2bf2d22'
CONTEXT=ROOT/'data/cache/research/ndx_joint_weight_runs_v3'/CONTEXT_SHA/'context.json'
CORE=ROOT/'backtest/ndx_corrected_cutoff_snapshot_research.py'
RUNNER=ROOT/'scripts/ndx_corrected_cutoff_snapshot_runner_research.py'
SCHEMA='MAY_NO_SEED_CUTOFF_SNAPSHOT_INDEPENDENT_TYPED_DECIMAL_READBACK_V1'
FLAGS=('checkpoint_weights_used','selection_performed','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed')
LOADED=dict(pure.LOADED)
for path in (Path(__file__).resolve(),Path(pure.__file__).resolve(),CORE,RUNNER,Path(publish.__code__.co_filename).resolve()):
    archive.merge(LOADED,{str(path):archive.drift.file_sha(path)})
# Exact frozen v2 fitter dependency roles; hashes come from the hard May queue.
NUMERICAL_FILES=tuple('backtest/'+name+'.py' for name in (
    'ndx_cardinality_capital_replay_summary','ndx_cardinality_discovery','ndx_concentration_projection_v2',
    'ndx_dynamic_cutoff_refit_research','ndx_dynamic_cutoff_refit_v2_research','ndx_joint_weight_delta',
    'ndx_joint_weight_evaluation','ndx_joint_weight_evaluation_v2','ndx_joint_weight_evaluation_v3',
    'ndx_joint_weight_history_inputs','ndx_joint_weight_runner','ndx_joint_weight_runner_v2','ndx_joint_weight_runner_v3',
    'ndx_projection_certificate_research','ndx_projection_reconstruction_research','ndx_two_stage_joint_coverage',
    'ndx_whole_lot_rebalance','weights'))+('core/helpers.py','data/ndx_security_identity.py','data/versioning.py',
    'scripts/ndx_joint_weight_batch.py','scripts/ndx_joint_weight_progress.py','scripts/ndx_joint_weight_verify.py','scripts/ndx_projection_reconstruction_probe.py')
RESULT_KEYS={'schema','queue_sha256','job_id','candidate','historical_cutoff','diagnostic_policy','effective_anchor_strength',
    'input_binding','new_cutoff_fit_attempt_count','whole_lot_execution_performed','forward_oos_evaluation_performed',
    'numerical_failure_is_economic_infeasibility',*FLAGS,'status','refit'}
FIT_KEYS={'anchor_by_security','anchor_policy','checkpoint_weights_used','cutoff','declared_constraint_checks','declared_constraints_passed',
    'declared_parameters','effective_anchor_strength','fit_data_sha256','fit_end','fit_row_count','fit_start','historical_task_evaluation_performed',
    'numerical_projection','order_generation_allowed','point_in_time_verified','previous_target_weights','projection_reconstruction_audit',
    'promotion_allowed','risk_chain_projection_relaxed','risk_chains_by_security','schema','single_name_projection_relaxed',
    'source_authenticity_verified','source_hashes','surviving_anchor_mass','targets','top3_projection_semantics_relaxed','weight_spec'}
CHECKS={'MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT'}


def false_fields(value,fields):
    if any(value[k] is not False for k in fields):raise ValueError('Research scope upgraded')


def validate_index(index,queue):
    if (set(index)!={'schema','queue','seed','planned','completed','status','finalization',*FLAGS}
        or index['schema']!='CORRECTED_CUTOFF_SNAPSHOT_COMPLETION_INDEX_V1'
        or index['queue']!=dict(path=str(QUEUE),sha256=QUEUE_SHA) or index['seed'] is not None):
        raise ValueError('Hard May queue without seed required')
    jobs=[r['task']['job_id'] for r in queue['candidates']];ids=[e['job_id'] for e in index['completed']]
    if (len(jobs)!=104 or queue['candidate_count']!=104 or len(set(jobs))!=104
        or type(index['planned']) is not int or index['planned']!=104
        or len(ids)!=len(set(ids)) or ids!=[j for j in jobs if j in set(ids)]):raise ValueError('Exact ordered May subset required')
    status='COMPLETE' if len(ids)==104 else 'PARTIAL';final=index['finalization']
    if (index['status']!=status or type(final) is not dict or final['schema']!='CORRECTED_CUTOFF_SNAPSHOT_FINALIZATION_V1'
        or type(final['planned']) is not int or final['planned']!=104 or type(final['completed']) is not int
        or final['completed']!=len(ids) or final['status']!=status):raise ValueError('Finalized actual denominator required')
    false_fields(index,FLAGS);false_fields(final,FLAGS)
    return {r['task']['job_id']:r for r in queue['candidates']}


def validate_task(value,attempt,queue,index,candidates):
    job=value['job_id'];result=value['result']
    if (set(value)!={'schema','queue','job_id','mode','result','risk_projection_metadata_independently_recomputed','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed'}
        or value['schema']!='CORRECTED_CUTOFF_SNAPSHOT_TASK_V1' or value['queue']!=index['queue'] or value['mode']!='ONE_NEW_HISTORICAL_CUTOFF_FIT'):
        raise ValueError('No-seed complete wrapper required')
    false_fields(value,('risk_projection_metadata_independently_recomputed','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed'))
    expected=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_ATTEMPT_V1',queue=index['queue'],seed=None,job_id=job,mode=value['mode'],
        runner_source_hashes={str(RUNNER):LOADED[str(RUNNER)]},status='STARTED_NOT_COMPLETED')
    if pure.digest(attempt)!=pure.digest(expected):raise ValueError('Exact durable attempt required')
    if (job not in candidates or result['job_id']!=job or pure.digest(result['candidate'])!=pure.digest(candidates[job])
        or result['schema']!='CORRECTED_CUTOFF_SNAPSHOT_NUMERICAL_RESULT_V1' or result['queue_sha256']!=pure.digest(queue)
        or result['input_binding']!=queue['input_binding'] or result['historical_cutoff']!=queue['historical_cutoff']
        or result['diagnostic_policy']!='FIRST_DECISION_NO_PRIOR_TARGET_DIAGNOSTIC'
        or type(result['effective_anchor_strength']) not in (int,float) or result['effective_anchor_strength']!=0
        or type(result['new_cutoff_fit_attempt_count']) is not int or result['new_cutoff_fit_attempt_count']!=1):raise ValueError('May task/typed inputs differ')
    false_fields(result,FLAGS+('whole_lot_execution_performed','forward_oos_evaluation_performed','numerical_failure_is_economic_infeasibility'))
    if result['status']=='FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY':
        if (set(result)!=RESULT_KEYS|{'error','error_type'} or result['refit'] is not None or type(result['error']) is not str
            or result['error_type'] not in ('ValueError','RuntimeError','ArithmeticError','FloatingPointError','OverflowError','ZeroDivisionError')):
            raise ValueError('Explicit failure without fitted payload required')
    elif result['status'] in ('FITTED_FIVE_RISKS_PASSED','FITTED_FIVE_RISKS_FAILED'):
        checks=result.get('independently_recomputed_five_checks')
        if (set(result)!=RESULT_KEYS|{'independently_recomputed_five_checks'} or type(result['refit']) is not dict
            or type(checks) is not dict or set(checks)!=CHECKS or any(type(v) is not bool for v in checks.values())):
            raise ValueError('Successful fit requires full payload and five boolean risks')
        fit=result['refit'];expected_sources={str(ROOT/p):queue['historical_expected_source_hashes'][str(ROOT/p)] for p in NUMERICAL_FILES}
        if (set(fit)!=FIT_KEYS or fit['schema']!='ndx_dynamic_cutoff_refit_research_v2'
            or fit['anchor_policy']!='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED'
            or fit['source_hashes']!=expected_sources):raise ValueError('Original numerical dependency/schema differs')
        false_fields(fit,('checkpoint_weights_used','historical_task_evaluation_performed','order_generation_allowed','point_in_time_verified','promotion_allowed','source_authenticity_verified'))
    else:raise ValueError('Unknown numerical status')
    return result


def verify_gaps(rows):
    for row in rows:
        path=Path(row['path']);actual=archive.drift.file_sha(path) if path.exists() else None
        if actual!=row['observed_current_sha256']:raise ValueError('Historical loader gap observation changed')


def build(index_path,index_sha256):
    sources=dict(LOADED)
    def read(path,sha):
        path=Path(path).resolve();raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External artifact SHA differs')
        archive.merge(sources,{str(path):sha});return json.loads(raw)
    queue=read(QUEUE,QUEUE_SHA);context=read(CONTEXT,CONTEXT_SHA);index=read(index_path,index_sha256);candidates=validate_index(index,queue)
    if queue['context']!=dict(path=str(CONTEXT),sha256=CONTEXT_SHA) or queue['original_runtime']!=context['runtime'] or queue['historical_cutoff']!='2023-04-28':raise ValueError('Hard May context/runtime/cutoff differs')
    final=index['finalization']
    if final['historical_loader_gap_observations']!=queue['historical_loader_gap_observations']:raise ValueError('Historical gaps differ')
    required_final=dict(queue['historical_expected_source_hashes'],**{str(QUEUE):QUEUE_SHA,str(CORE):LOADED[str(CORE)],str(RUNNER):LOADED[str(RUNNER)]})
    if any(final['historical_expected_source_hashes'].get(p)!=h for p,h in required_final.items()):raise ValueError('Finalized complete original queue/source closure required')
    for document in (queue,final):
        archive.merge(sources,document['historical_expected_source_hashes'])
        if archive.verify_expected_sources(document['historical_expected_source_hashes'],archive.load_contract())!=document['archive_resolution']:raise ValueError('Source partition differs')
    verify_gaps(queue['historical_loader_gap_observations']);details=[];folder=Path(index_path).resolve().parent
    for entry in index['completed']:
        job=entry['job_id']
        if set(entry)!={'job_id','started','result'}:raise ValueError('Exact completed entry required')
        for key,name in (('result',job+'.json'),('started',job+'.started.json')):
            if (set(entry[key])!={'path','sha256'} or entry[key]['path']!=str(folder/name)
                or final['historical_expected_source_hashes'].get(entry[key]['path'])!=entry[key]['sha256']):raise ValueError('Complete checkpoint/source lineage differs')
        value=read(entry['result']['path'],entry['result']['sha256']);attempt=read(entry['started']['path'],entry['started']['sha256'])
        result=validate_task(value,attempt,queue,index,candidates)
        if value['job_id']!=job:raise ValueError('Index and saved task differ')
        detail=dict(job_id=job,status=result['status'],result_reference=entry['result'],typed_decimal=None)
        if result['refit'] is not None:
            detail['typed_decimal']=pure.inspect_context(context,queue,result)
            checks=detail['typed_decimal']['decimal_risks']['checks']
            if (pure.digest(checks)!=pure.digest(result['independently_recomputed_five_checks'])
                or result['status']!=('FITTED_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_FIVE_RISKS_FAILED')):raise ValueError('Independent May risks differ')
        else:detail.update(error_type=result['error_type'],error=result['error'],numerical_failure_is_economic_infeasibility=False)
        details.append(detail)
    value=dict(schema=SCHEMA,index=dict(path=str(Path(index_path).resolve()),sha256=index_sha256),queue=index['queue'],seed=None,
        planned=104,completed=len(details),status=index['status'],details=details,
        fitted_count=sum(d['typed_decimal'] is not None for d in details),numerical_failure_count=sum(d['typed_decimal'] is None for d in details),
        historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,archive.load_contract()),
        historical_loader_gap_observations=queue['historical_loader_gap_observations'],fitter_called=False,owner_check_fitted_called=False,
        projection_metadata_independently_recomputed=False,optimizer_optimality_proved=False,performance_or_dual_benchmark_pass_claimed=False,
        historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False)
    verify(value);return value


def verify(value):
    required=dict(LOADED,**{str(QUEUE):QUEUE_SHA,str(CONTEXT):CONTEXT_SHA})
    if value['schema']!=SCHEMA or value['seed'] is not None or any(value['historical_expected_source_hashes'].get(p)!=h for p,h in required.items()):raise ValueError('May independent source closure required')
    false_fields(value,('fitter_called','owner_check_fitted_called','projection_metadata_independently_recomputed','optimizer_optimality_proved',
        'performance_or_dual_benchmark_pass_claimed','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed'))
    if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Source partition changed')
    verify_gaps(value['historical_loader_gap_observations'])


def publish_verified(path,value):
    if Path(path).exists():raise FileExistsError('Create-only May audit')
    verify(value);saved=publish(path,value);verify(value);return saved


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('index-path','index-sha256','output'):p.add_argument('--'+name,required=True)
    args=p.parse_args();print(json.dumps(publish_verified(args.output,build(args.index_path,args.index_sha256))))
