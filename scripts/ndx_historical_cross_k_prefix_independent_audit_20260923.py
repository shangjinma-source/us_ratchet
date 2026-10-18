"""Independent persisted historical-fit prefix audit. Never calls runner or fitter."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import sys
import numpy as np
import pandas as pd
import scipy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_historical_fourteen_plan_independent_audit_20260923 as plan_reader
from scripts import ndx_fourteen_incremental_independent_audit_20260919 as shape
archive=plan_reader.archive;scalar=plan_reader.target_reader.scalar
publish=plan_reader.publish
PLAN=dict(path=str(plan_reader.PLAN_PATH),sha256=plan_reader.PLAN_SHA)
AUDIT=dict(path=str(plan_reader.PLAN_PATH.parent/'independent_plan_audit.json'),sha256='c94b3d8198081fc9c444a5bf75d503d63d09b9a095c648ade30266e2907fc072')
PLAN_READER_SHA='bf65e18a8e24bd429476fa447f01ad4ec2dc0d6db2a7fcc5fab964ec478b464f'
RUNNER=ROOT/'scripts/ndx_historical_cross_k_bounded_refit_20260923.py'
RUNNER_SHA='bd61f5d2ddfc148b6d6f93560975e8ccd4e377e7e723208f104edd300e7cf1b1'
FALSE=tuple(k for k in plan_reader.PLAN_FALSE if k!='fit_performed')
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(plan_reader.__file__).resolve(),Path(shape.__file__).resolve(),Path(scalar.__file__).resolve(),archive.SOURCE,archive.drift.SOURCE,Path(publish.__code__.co_filename).resolve())}


def exact(a,b):return plan_reader.exact(a,b)
def digest(value):return plan_reader.digest(value)
def read(ref,sources):return plan_reader.read(ref,sources)
def runtime():return dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__)


def pending_tasks(plan):
    if len(plan['tasks'])!=31828 or plan['canonical_task_count']!=31828:raise ValueError('Complete original task plan required')
    pending=[];external=[];seen=set()
    for row in plan['tasks']:
        if digest(row['task'])!=row['task_id'] or row['task_id'] in seen or row['result_reused'] is not False:raise ValueError('Unique unimported historical tasks required')
        seen.add(row['task_id'])
        if row['task_id']==plan_reader.target_reader.JOB:
            if row['completed_external_reference']!=plan_reader.TARGET or row['status']!='COMPLETED_HISTORICAL_RESULT_EXTERNAL_REFERENCE_NOT_IMPORTED':raise ValueError('Original historical result remains external only')
            external.append(row)
        else:
            if row['completed_external_reference'] is not None or row['status']!='PENDING_HISTORICAL_FIT':raise ValueError('No latest or unrecognized result references allowed')
            pending.append(row)
    if len(external)!=1 or len(pending)!=31827:raise ValueError('One external plus 31827 new denominator required')
    return sorted(pending,key=lambda r:r['task_id'])


def validate_index(value,tasks,base_sources):
    entries=value['entries'];folder=Path(value['folder'])
    if not folder.is_absolute() or str(folder.resolve())!=value['folder'] or type(entries) is not list or len(entries)>len(tasks):raise ValueError('Absolute bounded index directory and prefix required')
    if [e['task_id'] for e in entries]!=[r['task_id'] for r in tasks[:len(entries)]]:raise ValueError('Exact sorted new historical prefix required')
    for entry in entries:
        if set(entry)!={'task_id','started_reference','raw_reference','result_reference'}:raise ValueError('Exact completed entry required')
        for key,name in (('started_reference','started.json'),('raw_reference','raw.json'),('result_reference','result.json')):
            ref=entry[key]
            if set(ref)!={'path','sha256'} or ref['path']!=str(folder/entry['task_id']/name) or type(ref['sha256']) is not str or len(ref['sha256'])!=64:raise ValueError('Exact per-task artifact reference required')
    expected=dict(schema='HISTORICAL_CROSS_K_FINALIZED_PREFIX_V1',plan_reference=PLAN,independent_plan_audit_reference=AUDIT,
        folder=str(folder),canonical_task_count=31828,external_completed_reference_count=1,external_completed_reference=plan_reader.TARGET,
        pending_task_count=31827,completed_new_count=len(entries),remaining_new_count=31827-len(entries),entries=entries,
        status='COMPLETE' if len(entries)==31827 else 'PARTIAL',finalized_after_full_source_verification=True,contains_new_historical_fit_results=bool(entries),
        historical_expected_source_hashes=value['historical_expected_source_hashes'],archive_resolution=value['archive_resolution'],**dict.fromkeys(FALSE,False))
    if not exact(value,expected):raise ValueError('Complete finalized index schema/count/scope differs')
    declared=value['historical_expected_source_hashes']
    required=dict(base_sources)
    for entry in entries:
        for key in ('started_reference','raw_reference','result_reference'):archive.merge(required,{entry[key]['path']:entry[key]['sha256']})
    if any(declared.get(p)!=h for p,h in required.items()):raise ValueError('Finalized index omits or replaces source/receipt')
    extra={p:h for p,h in declared.items() if p not in required}
    for path in extra:
        p=Path(path)
        if p.parent!=folder or not p.name.startswith('index_') or p.suffix!='.json':raise ValueError('Only externally hash-bound prior finalized indices may extend closure')
    return extra


def partition_subset(expected,contract):
    """Derive metadata only. All expected bytes are separately checked as one union."""
    return scalar.declared_partition(expected,contract)


def inspect_task(row,documents,entry,frame,numerical,base_sources,base_partition):
    task=copy.deepcopy(row['task']);identifier=row['task_id']
    if identifier==plan_reader.target_reader.JOB:raise ValueError('The sole historical external reference must never be newly fitted')
    expected=plan_reader.expected_task(task['selected'],task['weight_spec'],scalar.PARAMS,frame,numerical)
    if not exact(row,expected):raise ValueError('Original historical task/matrix/parameters differ')
    task['task_id']=identifier
    marker=dict(schema='HISTORICAL_CROSS_K_ATTEMPT_V1',plan_reference=PLAN,task_id=identifier,attempt_count=1,runtime=runtime())
    if not exact(documents['started'],marker):raise ValueError('Durable historical attempt/runtime differs')
    sources=dict(base_sources);archive.merge(sources,{entry['started_reference']['path']:entry['started_reference']['sha256']})
    result=documents['raw']['result']
    expected_raw=dict(schema='HISTORICAL_CROSS_K_RAW_FIT_V1',plan_reference=PLAN,task=task,result=result,started_reference=entry['started_reference'],runtime=runtime(),historical_expected_source_hashes=sources,fit_performed=True,**dict.fromkeys(FALSE,False))
    if not exact(documents['raw'],expected_raw):raise ValueError('Whole raw receipt/task/source/fit scope differs')
    shape.result_schema(result,task)
    if not exact(result['source_hashes'],numerical):raise ValueError('Original numerical fitter closure differs')
    details=scalar.inspect_result(result,task,dict(returns=frame))
    archive.merge(sources,{entry['raw_reference']['path']:entry['raw_reference']['sha256']})
    partition=copy.deepcopy(base_partition)
    for key in ('started_reference','raw_reference'):
        ref=entry[key];archive.merge(partition['live_verified_source_hashes'],{ref['path']:ref['sha256']})
    expected_saved=dict(schema='HISTORICAL_CROSS_K_CHECKPOINT_V1',plan_reference=PLAN,task=task,result=result,started_reference=entry['started_reference'],raw_reference=entry['raw_reference'],
        independent_matrix_and_risk_checks=details,status='FITTED_FIVE_RISKS_PASSED' if details['risk_pass'] else 'FITTED_FIVE_RISKS_FAILED',
        historical_expected_source_hashes=sources,archive_resolution=partition,fit_performed=True,**dict.fromkeys(FALSE,False))
    if not exact(documents['result'],expected_saved):raise ValueError('Complete checkpoint/weights/risk/raw lineage differs')
    return details


def invocation_sources(plan,audit):
    sources={str(RUNNER):RUNNER_SHA,str(plan_reader.OWNER):plan_reader.OWNER_SHA,
        str(Path(shape.__file__).resolve()):LOADED[str(Path(shape.__file__).resolve())],
        str(Path(scalar.numerical_sources.__file__).resolve()):hashlib.sha256(Path(scalar.numerical_sources.__file__).read_bytes()).hexdigest(),
        str(Path(plan_reader.__file__).resolve()):PLAN_READER_SHA}
    for ref,value in ((PLAN,plan),(AUDIT,audit)):
        archive.merge(sources,{ref['path']:ref['sha256']});archive.merge(sources,value['historical_expected_source_hashes'])
    archive.merge(sources,plan['numerical_source_hashes'])
    return sources


def build(index_path,index_sha256,*,completed_prefix_confirmed=False):
    if completed_prefix_confirmed is not True:raise ValueError('Caller must explicitly confirm bounded run finished, not infer it from an intermediate file')
    if RUNNER_SHA is None:raise ValueError('Await hard sealed historical runner')
    if LOADED[str(Path(plan_reader.__file__).resolve())]!=PLAN_READER_SHA:raise ValueError('Hard independent plan reader differs')
    sources=dict(LOADED);plan=read(PLAN,sources);audit=read(AUDIT,sources)
    if audit['schema']!='HISTORICAL_FOURTEEN_PLAN_INDEPENDENT_AUDIT_V1' or audit['plan_reference']!=PLAN or audit['details']['canonical_task_count']!=31828:raise ValueError('Hard independent plan audit lineage differs')
    document=read(plan_reader.INPUT,sources);frame=plan_reader.first_window(document)
    if not exact(frame,plan['historical_numerical_view']):raise ValueError('Hard historical first126 view differs')
    tasks=pending_tasks(plan);base=invocation_sources(plan,audit);archive.merge(sources,base)
    numerical=scalar.numerical_sources._sources()
    if not exact(numerical,plan['numerical_source_hashes']):raise ValueError('Original numerical sources differ')
    reference=dict(path=str(Path(index_path).resolve()),sha256=index_sha256);index=read(reference,sources)
    contract=archive.load_contract()
    archive.merge(sources,index['historical_expected_source_hashes'])
    archive.verify_expected_sources(sources,contract)
    # Keep one requested index plus small lineage edges, not every cumulative
    # prior index's full repeated task/source dictionaries.
    pending={reference['path']:reference['sha256']};chain={};edges={}
    while pending:
        path,sha=pending.popitem();ref=dict(path=path,sha256=sha)
        if path in chain:
            if chain[path]!=sha:raise ValueError('Conflicting prior index digest')
            continue
        value=index if path==reference['path'] else read(ref,sources)
        if Path(ref['path']).parent!=Path(index['folder']) or Path(ref['path']).name!='index_'+digest(value)+'.json':raise ValueError('Finalized index content/address differs')
        extra=validate_index(value,tasks,base)
        if value['entries']!=index['entries'][:len(value['entries'])]:raise ValueError('Prior index not a prefix of requested completed tasks')
        if any(index['historical_expected_source_hashes'].get(p)!=h for p,h in value['historical_expected_source_hashes'].items()):raise ValueError('Current finalized index omitted ancestor source closure')
        if not exact(value['archive_resolution'],partition_subset(value['historical_expected_source_hashes'],contract)):raise ValueError('Finalized index archive partition differs')
        edges[path]=tuple(extra);chain[path]=sha
        for p,h in extra.items():
            if (p in chain and chain[p]!=h) or (p in pending and pending[p]!=h):raise ValueError('Conflicting ancestor index digest')
            if p not in chain:pending[p]=h
        del value
    active=set();done=set();work=[(reference['path'],False)]
    while work:
        path,finished=work.pop()
        if finished:active.remove(path);done.add(path);continue
        if path in active:raise ValueError('Cyclic finalized index provenance')
        if path in done:continue
        active.add(path);work.append((path,True));work.extend((p,False) for p in edges[path])
    base_partition=partition_subset(base,contract);details=[]
    for row,entry in zip(tasks,index['entries']):
        documents={k:read(entry[k+'_reference'],sources) for k in ('started','raw','result')}
        details.append(inspect_task(row,documents,entry,frame,numerical,base,base_partition))
    count=len(details);passed=sum(r['risk_pass'] for r in details)
    return dict(schema='HISTORICAL_CROSS_K_COMPLETED_PREFIX_INDEPENDENT_AUDIT_V1',index_reference=reference,plan_reference=PLAN,independent_plan_audit_reference=AUDIT,
        canonical_task_count=31828,external_completed_reference_count=1,external_completed_reference=plan_reader.TARGET,pending_task_count=31827,
        completed_new_count=count,remaining_new_count=31827-count,risk_pass_count=passed,risk_failure_count=count-passed,details=details,
        complete_marker_raw_checkpoint_chain_verified=True,write_order_independently_attested=False,
        prefix_confirmation='CALLER_OBSERVED_BOUNDED_RUN_EXIT_NOT_INDEPENDENT_PROCESS_ATTESTATION',
        producer_called=False,runner_called=False,fitter_called=False,constrained_projection_optimality_independently_verified=False,
        fit_performed=False,historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,contract),**dict.fromkeys(FALSE,False))


def verify(value):
    ref=value['index_reference']
    if not exact(value,build(ref['path'],ref['sha256'],completed_prefix_confirmed=True)):raise ValueError('Complete independent historical prefix readback differs')


def publish_verified(path,value):
    verify(value);saved=publish(path,value)
    if not exact(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution']):raise ValueError('Source drift after publication')
    return saved


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--index',required=True);p.add_argument('--index-sha256',required=True);p.add_argument('--completed-prefix-confirmed',action='store_true');p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(publish_verified(a.output,build(a.index,a.index_sha256,completed_prefix_confirmed=a.completed_prefix_confirmed))))
