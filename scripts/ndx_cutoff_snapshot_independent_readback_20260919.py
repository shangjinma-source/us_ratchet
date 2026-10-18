"""Read completed April cutoff tasks via typed matrices and Decimal risks, never fit."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_first_cutoff_refit_independent_audit_20260919 as pure
from scripts.ndx_base_three_cell_window_delta_research import publish
archive=pure.archive
FIRST_AUDIT=pure.BASE/'first_refit_independent_audit.json'
FIRST_AUDIT_SHA='6cbd74304d99dd4979db6ebe3a5f758f2e6f5c062e9af22cea13efaebc0885e4'
CORE=ROOT/'backtest/ndx_corrected_cutoff_snapshot_research.py'
RUNNER=ROOT/'scripts/ndx_corrected_cutoff_snapshot_runner_research.py'
LOADED=dict(pure.LOADED)
for path in (Path(__file__).resolve(),Path(pure.__file__).resolve(),CORE,RUNNER,Path(publish.__code__.co_filename).resolve()):
    archive.merge(LOADED,{str(path):archive.drift.file_sha(path)})
FLAGS=('checkpoint_weights_used','selection_performed','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed')


def false_fields(value,names):
    if any(value[k] is not False for k in names):raise ValueError('Research scope upgraded')


def validate_index(index,queue):
    if (set(index)!={'schema','queue','seed','planned','completed','status','finalization',*FLAGS}
        or index['schema']!='CORRECTED_CUTOFF_SNAPSHOT_COMPLETION_INDEX_V1'
        or index['queue']!=dict(path=str(pure.QUEUE),sha256=pure.QUEUE_SHA)
        or index['seed']!=dict(path=str(pure.EXECUTION),sha256=pure.EXECUTION_SHA)):
        raise ValueError('Hard queue/seed index required')
    false_fields(index,FLAGS)
    jobs=[r['task']['job_id'] for r in queue['candidates']];ids=[e['job_id'] for e in index['completed']]
    if type(index['planned']) is not int or index['planned']!=len(jobs) or len(set(ids))!=len(ids) or ids!=[j for j in jobs if j in set(ids)]:
        raise ValueError('Complete ordered unique queue subset required')
    status='COMPLETE' if len(ids)==len(jobs) else 'PARTIAL';final=index['finalization']
    if (index['status']!=status or not isinstance(final,dict) or final['schema']!='CORRECTED_CUTOFF_SNAPSHOT_FINALIZATION_V1'
        or type(final['completed']) is not int or final['completed']!=len(ids)
        or type(final['planned']) is not int or final['planned']!=len(jobs) or final['status']!=status):
        raise ValueError('Actual completed finalization required')
    false_fields(final,FLAGS)
    return {r['task']['job_id']:r for r in queue['candidates']}


def validate_task(value,attempt,*,queue,index,candidates,seed):
    job=value['job_id'];result=value['result'];is_seed=job==seed['job_id']
    mode='EXTERNAL_SINGLE_FIT_IMPORTED_WITHOUT_REFIT' if is_seed else 'ONE_NEW_HISTORICAL_CUTOFF_FIT'
    keys={'schema','queue','job_id','mode','result','risk_projection_metadata_independently_recomputed','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed'}
    if is_seed:keys.update(('seed','original_single_fit_wrapper'))
    if (set(value)!=keys or value['schema']!='CORRECTED_CUTOFF_SNAPSHOT_TASK_V1' or value['queue']!=index['queue'] or value['mode']!=mode):raise ValueError('Complete task wrapper differs')
    false_fields(value,('risk_projection_metadata_independently_recomputed','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed'))
    expected_attempt=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_ATTEMPT_V1',queue=index['queue'],seed=index['seed'],job_id=job,mode=mode,
        runner_source_hashes={str(RUNNER):LOADED[str(RUNNER)]},status='STARTED_NOT_COMPLETED')
    if pure.digest(attempt)!=pure.digest(expected_attempt):raise ValueError('Durable attempt coordinate differs')
    if (job not in candidates or result['job_id']!=job or pure.digest(result['candidate'])!=pure.digest(candidates[job])
        or result['schema']!='CORRECTED_CUTOFF_SNAPSHOT_NUMERICAL_RESULT_V1' or result['queue_sha256']!=pure.digest(queue)
        or result['input_binding']!=queue['input_binding'] or result['historical_cutoff']!=queue['historical_cutoff']
        or result['diagnostic_policy']!=queue['diagnostic_policy']
        or type(result['effective_anchor_strength']) not in (int,float) or result['effective_anchor_strength']!=0
        or type(result['new_cutoff_fit_attempt_count']) is not int or result['new_cutoff_fit_attempt_count']!=1):raise ValueError('Task identity/input/single-fit binding differs')
    false_fields(result,FLAGS+('whole_lot_execution_performed','forward_oos_evaluation_performed','numerical_failure_is_economic_infeasibility'))
    result_keys=set(seed['result'])-{'historical_expected_source_hashes','archive_resolution','historical_loader_gap_observations'}
    result_keys.add('input_binding')
    if result['status']=='FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY':
        result_keys.remove('independently_recomputed_five_checks');result_keys.update(('error','error_type'))
    if set(result)!=result_keys:raise ValueError('Exact numerical result fields required')
    if is_seed:
        expected={k:deepcopy(v) for k,v in seed['result'].items() if k not in ('historical_expected_source_hashes','archive_resolution','historical_loader_gap_observations')}
        expected.update(schema='CORRECTED_CUTOFF_SNAPSHOT_NUMERICAL_RESULT_V1',input_binding=queue['input_binding'])
        if (value['seed']!=index['seed'] or pure.digest(value['original_single_fit_wrapper'])!=pure.digest(seed) or pure.digest(result)!=pure.digest(expected)):
            raise ValueError('Seed must be imported exactly without refit')
    if result['status']=='FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY':
        if result['refit'] is not None or type(result.get('error')) is not str or result.get('error_type') not in ('ValueError','RuntimeError','ArithmeticError','FloatingPointError','OverflowError','ZeroDivisionError'):
            raise ValueError('Explicit numerical failure required')
    elif result['status'] not in ('FITTED_FIVE_RISKS_PASSED','FITTED_FIVE_RISKS_FAILED'):raise ValueError('Unknown fitted status')
    return result


def gaps(queue):
    for row in queue['historical_loader_gap_observations']:
        path=Path(row['path']);actual=archive.drift.file_sha(path) if path.exists() else None
        if actual!=row['observed_current_sha256']:raise ValueError('Historical loader gap observation changed')


def build(index_path,index_sha256):
    sources=dict(LOADED)
    def read(path,sha):
        path=Path(path).resolve();raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External artifact SHA differs')
        archive.merge(sources,{str(path):sha});return json.loads(raw)
    queue=read(pure.QUEUE,pure.QUEUE_SHA);seed=read(pure.EXECUTION,pure.EXECUTION_SHA);first=read(FIRST_AUDIT,FIRST_AUDIT_SHA)
    context=read(pure.CONTEXT,pure.CONTEXT_SHA);index=read(index_path,index_sha256);candidates=validate_index(index,queue)
    if first['execution']!=dict(path=str(pure.EXECUTION),sha256=pure.EXECUTION_SHA) or first['queue']!=index['queue']:raise ValueError('Hard first independent audit differs')
    if queue['context']!=dict(path=str(pure.CONTEXT),sha256=pure.CONTEXT_SHA) or context['runtime']!=queue['original_runtime']:raise ValueError('Hard typed context/runtime differs')
    final=index['finalization']
    if final['historical_loader_gap_observations']!=queue['historical_loader_gap_observations']:raise ValueError('Gap declaration changed')
    for report in (queue,first,final):
        archive.merge(sources,report['historical_expected_source_hashes'])
        if archive.verify_expected_sources(report['historical_expected_source_hashes'],archive.load_contract())!=report['archive_resolution']:raise ValueError('Source partition differs')
    gaps(queue);details=[];folder=Path(index_path).resolve().parent
    for entry in index['completed']:
        job=entry['job_id']
        if set(entry)!={'job_id','started','result'}:raise ValueError('Exact completion entry required')
        for key,name in (('result',job+'.json'),('started',job+'.started.json')):
            if entry[key]['path']!=str(folder/name) or final['historical_expected_source_hashes'].get(entry[key]['path'])!=entry[key]['sha256']:raise ValueError('Finalized checkpoint lineage differs')
        value=read(**dict(path=entry['result']['path'],sha=entry['result']['sha256']));attempt=read(**dict(path=entry['started']['path'],sha=entry['started']['sha256']))
        result=validate_task(value,attempt,queue=queue,index=index,candidates=candidates,seed=seed)
        if value['job_id']!=job:raise ValueError('Completion job differs')
        detail=dict(job_id=job,status=result['status'],mode=value['mode'],result_reference=entry['result'])
        if result['refit'] is not None:
            fit=result['refit'];false_fields(fit,('checkpoint_weights_used','historical_task_evaluation_performed','order_generation_allowed','point_in_time_verified','promotion_allowed','source_authenticity_verified'))
            first_fit=seed['result']['refit']
            if (set(fit)!=set(first_fit) or fit['schema']!=first_fit['schema'] or fit['anchor_policy']!=first_fit['anchor_policy']
                or fit['source_hashes']!=first_fit['source_hashes']):raise ValueError('Original fitter schema/source/anchor policy differs')
            for p,h in fit['source_hashes'].items():
                if final['historical_expected_source_hashes'].get(p)!=h:raise ValueError('Numerical source omitted')
            detail['typed_decimal']=pure.inspect_context(context,queue,result)
            checks=detail['typed_decimal']['decimal_risks']['checks']
            if pure.digest(checks)!=pure.digest(result['independently_recomputed_five_checks']) or result['status']!=('FITTED_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_FIVE_RISKS_FAILED'):raise ValueError('Five-risk status differs')
        details.append(detail)
    checked=archive.verify_expected_sources(sources,archive.load_contract());gaps(queue)
    return dict(schema='CUTOFF_SNAPSHOT_COMPLETED_INDEPENDENT_TYPED_DECIMAL_READBACK_V1',index=dict(path=str(Path(index_path).resolve()),sha256=index_sha256),
        queue=index['queue'],seed=index['seed'],planned=index['planned'],completed=len(details),status=index['status'],details=details,
        historical_expected_source_hashes=sources,archive_resolution=checked,historical_loader_gap_observations=queue['historical_loader_gap_observations'],
        fitter_called=False,owner_check_fitted_called=False,risk_projection_metadata_independently_recomputed=False,
        optimizer_optimality_proved=False,performance_or_dual_benchmark_pass_claimed=False,point_in_time_verified=False,promotion_allowed=False)


def publish_verified(path,value):
    if Path(path).exists():raise FileExistsError('Create-only independent audit')
    def verify():
        if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in LOADED.items()):raise ValueError('Loaded independent sources omitted')
        if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Source partition changed')
        gaps(value)
    verify();saved=publish(path,value);verify();return saved


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('index-path','index-sha256','output'):p.add_argument('--'+name,required=True)
    args=p.parse_args();print(json.dumps(publish_verified(args.output,build(args.index_path,args.index_sha256))))
