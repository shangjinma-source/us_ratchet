"""October-only independent no-seed cutoff readback; no fitter or owner validator."""
import argparse, hashlib, json, sys
from pathlib import Path
from types import FunctionType
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_may_cutoff_snapshot_independent_readback_20260919 as may
pure=may.pure;archive=may.archive;publish=may.publish
BASE=may.BASE
QUEUE=ROOT/'data/cache/research/corrected_cutoff_snapshot_20260923_v1/20231002_queue.json'
QUEUE_SHA='c79e98c28137a8f96a55fecd2d89a2ef2a3892dd9961253702dd7d722815f060'
PLANNED=425
CONTEXT_SHA='9425c1750d42642ed243bd4212e362a8584f35a64443ce9021bc4e3b29ccfe62'
CONTEXT=ROOT/'data/cache/research/ndx_joint_weight_runs_v3'/CONTEXT_SHA/'context.json'
CORE=may.CORE;RUNNER=may.RUNNER
SCHEMA='OCTOBER_NO_SEED_CUTOFF_SNAPSHOT_INDEPENDENT_TYPED_DECIMAL_READBACK_V1'
FLAGS=may.FLAGS;RESULT_KEYS=may.RESULT_KEYS;FIT_KEYS=may.FIT_KEYS;CHECKS=may.CHECKS;NUMERICAL_FILES=may.NUMERICAL_FILES
MAY_SOURCE=Path(may.__file__).resolve()
MAY_SOURCE_SHA='a0b43635d1197b5c7d50eb8809701bdc430a181bcff5b9b5fd1cca9e93a38e49'
if archive.drift.file_sha(MAY_SOURCE)!=MAY_SOURCE_SHA:raise ValueError('Frozen independent scalar reader differs')
LOADED=dict(may.LOADED)
archive.merge(LOADED,{str(MAY_SOURCE):MAY_SOURCE_SHA,str(Path(__file__).resolve()):archive.drift.file_sha(Path(__file__).resolve())})
false_fields=may.false_fields
verify_gaps=may.verify_gaps
# Private function binding changes only the explicit October constants, never May globals.
validate_task=FunctionType(may.validate_task.__code__,globals(),'validate_task',may.validate_task.__defaults__)

def validate_index(index,queue):
    if type(PLANNED) is not int or PLANNED<=0 or not isinstance(QUEUE_SHA,str) or len(QUEUE_SHA)!=64:raise ValueError('October queue has not been externally sealed')
    if (set(index)!={'schema','queue','seed','planned','completed','status','finalization',*FLAGS}
        or index['schema']!='CORRECTED_CUTOFF_SNAPSHOT_COMPLETION_INDEX_V1'
        or index['queue']!=dict(path=str(QUEUE),sha256=QUEUE_SHA) or index['seed'] is not None):
        raise ValueError('Hard October queue without seed required')
    jobs=[r['task']['job_id'] for r in queue['candidates']];ids=[e['job_id'] for e in index['completed']]
    if (len(jobs)!=PLANNED or type(queue['candidate_count']) is not int or queue['candidate_count']!=PLANNED or len(set(jobs))!=PLANNED
        or type(index['planned']) is not int or index['planned']!=PLANNED
        or len(ids)!=len(set(ids)) or ids!=[j for j in jobs if j in set(ids)]):raise ValueError('Exact ordered October subset required')
    status='COMPLETE' if len(ids)==PLANNED else 'PARTIAL';final=index['finalization']
    if (index['status']!=status or type(final) is not dict or final['schema']!='CORRECTED_CUTOFF_SNAPSHOT_FINALIZATION_V1'
        or type(final['planned']) is not int or final['planned']!=PLANNED or type(final['completed']) is not int
        or final['completed']!=len(ids) or final['status']!=status):raise ValueError('Finalized actual denominator required')
    false_fields(index,FLAGS);false_fields(final,FLAGS)
    return {r['task']['job_id']:r for r in queue['candidates']}

def build(index_path,index_sha256):
    if type(PLANNED) is not int or PLANNED<=0 or type(QUEUE_SHA) is not str or len(QUEUE_SHA)!=64:raise ValueError('October queue denominator and external SHA have not been sealed')
    sources=dict(LOADED)
    def read(path,sha):
        path=Path(path).resolve();raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External artifact SHA differs')
        archive.merge(sources,{str(path):sha});return json.loads(raw)
    queue=read(QUEUE,QUEUE_SHA);context=read(CONTEXT,CONTEXT_SHA);index=read(index_path,index_sha256);candidates=validate_index(index,queue)
    if queue['context']!=dict(path=str(CONTEXT),sha256=CONTEXT_SHA) or queue['original_runtime']!=context['runtime'] or queue['historical_cutoff']!='2023-09-29':raise ValueError('Hard October context/runtime/cutoff differs')
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
                or result['status']!=('FITTED_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_FIVE_RISKS_FAILED')):raise ValueError('Independent October risks differ')
        else:detail.update(error_type=result['error_type'],error=result['error'],numerical_failure_is_economic_infeasibility=False)
        details.append(detail)
    value=dict(schema=SCHEMA,index=dict(path=str(Path(index_path).resolve()),sha256=index_sha256),queue=index['queue'],seed=None,
        planned=PLANNED,completed=len(details),status=index['status'],details=details,
        fitted_count=sum(d['typed_decimal'] is not None for d in details),numerical_failure_count=sum(d['typed_decimal'] is None for d in details),
        historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,archive.load_contract()),
        historical_loader_gap_observations=queue['historical_loader_gap_observations'],fitter_called=False,owner_check_fitted_called=False,
        projection_metadata_independently_recomputed=False,optimizer_optimality_proved=False,performance_or_dual_benchmark_pass_claimed=False,
        historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False)
    verify(value);return value


def verify(value):
    required=dict(LOADED,**{str(QUEUE):QUEUE_SHA,str(CONTEXT):CONTEXT_SHA})
    if value['schema']!=SCHEMA or value['seed'] is not None or any(value['historical_expected_source_hashes'].get(p)!=h for p,h in required.items()):raise ValueError('October independent source closure required')
    false_fields(value,('fitter_called','owner_check_fitted_called','projection_metadata_independently_recomputed','optimizer_optimality_proved',
        'performance_or_dual_benchmark_pass_claimed','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed'))
    if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Source partition changed')
    verify_gaps(value['historical_loader_gap_observations'])


def publish_verified(path,value):
    if Path(path).exists():raise FileExistsError('Create-only October audit')
    expected=build(value['index']['path'],value['index']['sha256'])
    if not pure.digest(value)==pure.digest(expected):raise ValueError('Entire independent October readback differs')
    verify(value);saved=publish(path,value);verify(value);return saved

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('index-path','index-sha256','output'):p.add_argument('--'+name,required=True)
    args=p.parse_args();print(json.dumps(publish_verified(args.output,build(args.index_path,args.index_sha256))))
