"""Bounded historical fits, durable raw receipts, and strict external-index resume."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
import sys
import numpy as np
import pandas as pd
import scipy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_historical_fourteen_cross_k_plan_20260923 as producer
from scripts import ndx_fourteen_incremental_independent_audit_20260919 as shape
archive=producer.archive
scalar=producer.target_reader.scalar
fitter=scalar.numerical_sources
publish=producer.target_reader.exclusive_publish
PLAN_PATH=producer.BASE/'historical_fourteen_cross_k_20260923_v1/plan.json'
PLAN_SHA='bd2f64aa33013330d4371c4266556cb4f7b04a27c994b4ad6553025516379f9f'
AUDIT_PATH=PLAN_PATH.parent/'independent_plan_audit.json'
AUDIT_SHA='c94b3d8198081fc9c444a5bf75d503d63d09b9a095c648ade30266e2907fc072'
AUDIT_READER_SHA='bf65e18a8e24bd429476fa447f01ad4ec2dc0d6db2a7fcc5fab964ec478b464f'
PRODUCER_SHA='6f1b3ebece10526e0fc606673d448a720e86bea861ffafb3487dec0156d71896'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(producer.__file__).resolve(),Path(shape.__file__).resolve(),Path(fitter.__file__).resolve())}
archive.merge(LOADED,producer.LOADED)
FALSE=tuple(k for k in producer.FALSE if k!='fit_performed')


def pack(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def unpack(value):return json.loads(value)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def runtime():return dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__)
def full(sources):return archive.verify_expected_sources(sources,archive.load_contract())
def frame_payload(frame):return producer.target_reader.typed.prior.frame_payload(frame)
def read(reference,sources):return producer.target_reader.read(reference,sources)


def select_pending(plan):
    if plan['schema']!='HISTORICAL_FOURTEEN_CROSS_K_TASK_PLAN_V1' or plan['cutoff']!='2026-03-18' or any(plan.get(k) is not False for k in producer.FALSE):raise ValueError('Exact conditional historical plan required')
    tasks=[];refs=[];seen=set()
    for row in plan['tasks']:
        task=row['task'];identifier=producer.digest(task)
        if identifier!=row['task_id'] or identifier in seen or row['result_reused'] is not False or task['cutoff']!='2026-03-18' or task['previous_target_weights'] is not None or not producer.exact(task['parameters'],scalar.PARAMS):raise ValueError('Unique historical task and original parameters required')
        seen.add(identifier)
        if row['status']=='COMPLETED_HISTORICAL_RESULT_EXTERNAL_REFERENCE_NOT_IMPORTED':
            if identifier!=producer.target_reader.JOB or not producer.exact(row['completed_external_reference'],producer.TARGET):raise ValueError('Only the existing historical result stays external')
            refs.append(row)
        elif row['status']=='PENDING_HISTORICAL_FIT' and row['completed_external_reference'] is None:tasks.append(dict(task,task_id=identifier))
        else:raise ValueError('Unknown historical completion state')
    if len(refs)!=1 or any(type(plan[k]) is not int for k in ('canonical_task_count','completed_external_reference_count','pending_historical_fit_count')) or plan['completed_external_reference_count']!=1 or plan['canonical_task_count']!=len(seen) or plan['pending_historical_fit_count']!=len(tasks):raise ValueError('Complete pending/reference denominator required')
    return tuple(pack(t) for t in sorted(tasks,key=lambda t:t['task_id']))


def prepare():
    if PLAN_SHA is None or AUDIT_SHA is None or AUDIT_READER_SHA is None:raise ValueError('Await sealed historical plan and independent plan audit')
    if LOADED[str(Path(producer.__file__).resolve())]!=PRODUCER_SHA:raise ValueError('Frozen historical producer differs')
    from scripts import ndx_historical_fourteen_plan_independent_audit_20260923 as reviewer
    if sha(reviewer.__file__)!=AUDIT_READER_SHA:raise ValueError('Hard independent plan reader differs')
    sources=dict(LOADED);reference=dict(path=str(PLAN_PATH),sha256=PLAN_SHA);plan=read(reference,sources)
    audit_ref=dict(path=str(AUDIT_PATH),sha256=AUDIT_SHA);audit=read(audit_ref,sources)
    reviewer.verify(audit)
    if not producer.exact(audit['plan_reference'],reference):raise ValueError('Independent plan audit lineage differs')
    archive.merge(sources,{str(Path(reviewer.__file__).resolve()):AUDIT_READER_SHA})
    for value in (plan,audit):archive.merge(sources,value['historical_expected_source_hashes'])
    tasks=select_pending(plan)
    frame=producer.target_reader.typed.decode(plan['historical_numerical_view'])
    if len(frame)!=126 or frame.index[-1]!=pd.Timestamp('2026-03-18') or [d.date().isoformat() for d in frame.index]!=plan['fit_calendar']:raise ValueError('Historical first126 matrix only')
    numerical=fitter._sources()
    if not producer.exact(numerical,plan['numerical_source_hashes']):raise ValueError('Plan fitter closure differs')
    archive.merge(sources,numerical);partition=full(sources)
    snapshot=dict(plan_reference=reference,independent_plan_audit_reference=audit_ref,sources=sources,numerical=numerical,
        runtime=runtime(),base_partition=partition,canonical_task_count=plan['canonical_task_count'],pending_planned=len(tasks),external_reference=deepcopy(producer.TARGET),
        coordinates={r['security_id']:{k:r[k] for k in ('ticker','issuer_id','risk_chain')} for r in plan['candidate_coordinate_and_risk_rows']})
    return pack(snapshot),tasks,frame


def check_ram(snapshot,task_bytes,frame,sealed_frame,marker=None):
    if runtime()!=snapshot['runtime'] or pack(frame_payload(frame))!=sealed_frame:raise ValueError('Runtime or typed historical RAM changed')
    task=unpack(task_bytes)
    if task['task_id']!=producer.digest({k:v for k,v in task.items() if k!='task_id'}) or not producer.exact(task['selected'],{s:snapshot['coordinates'][s] for s in task['selected']}):raise ValueError('Task coordinates changed')
    for path,h in snapshot['sources'].items():
        if Path(path).suffix=='.py' and sha(path)!=h:raise ValueError('Loaded numerical/research source changed')
    if marker and sha(marker['path'])!=marker['sha256']:raise ValueError('Durable attempt changed')


def marker_value(snapshot,task):return dict(schema='HISTORICAL_CROSS_K_ATTEMPT_V1',plan_reference=snapshot['plan_reference'],task_id=task['task_id'],attempt_count=1,runtime=snapshot['runtime'])


def task_partition(snapshot,sources):
    """Only new attempt artifacts extend the fully checked invocation snapshot."""
    base=snapshot['sources']
    if any(sources.get(p)!=h for p,h in base.items()):raise ValueError('Snapshot source omitted or replaced')
    value=deepcopy(snapshot['base_partition'])
    for p,h in sources.items():
        if p not in base:
            if Path(p).name not in ('started.json','raw.json') or sha(p)!=h:raise ValueError('Unexpected or changed task source')
            archive.merge(value['live_verified_source_hashes'],{p:h})
    return value


def validate_result(result,task,frame,numerical):
    shape.result_schema(result,task)
    if not producer.exact(result['source_hashes'],numerical):raise ValueError('Original fitter source closure differs')
    return scalar.inspect_result(result,task,dict(returns=frame_payload(frame)))


def index_value(snapshot,folder,entries,sources):
    return dict(schema='HISTORICAL_CROSS_K_FINALIZED_PREFIX_V1',plan_reference=snapshot['plan_reference'],independent_plan_audit_reference=snapshot['independent_plan_audit_reference'],
        folder=str(folder),canonical_task_count=snapshot['canonical_task_count'],external_completed_reference_count=1,external_completed_reference=snapshot['external_reference'],
        pending_task_count=snapshot['pending_planned'],completed_new_count=len(entries),remaining_new_count=snapshot['pending_planned']-len(entries),entries=entries,
        status='COMPLETE' if len(entries)==snapshot['pending_planned'] else 'PARTIAL',finalized_after_full_source_verification=True,contains_new_historical_fit_results=bool(entries),
        historical_expected_source_hashes=sources,archive_resolution=full(sources),**dict.fromkeys(FALSE,False))


def run(*,folder,max_new=0,index_path=None,index_sha256=None):
    if type(max_new) is not int or not 0<=max_new<=100:raise ValueError('Explicit integer budget 0..100 required')
    if (index_path is None)!=(index_sha256 is None):raise ValueError('External completed-index path/SHA pair required')
    snapshot_bytes,tasks,frame=prepare();snapshot=unpack(snapshot_bytes);sources=dict(snapshot['sources']);sealed_frame=pack(frame_payload(frame))
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True);entries=[];previous_sources=None
    if index_path is not None:
        index_ref=dict(path=str(Path(index_path).resolve()),sha256=index_sha256)
        index=read(index_ref,sources);entries=index['entries']
        # Prior index sources are authenticated separately; the new index also binds it.
        previous_sources=index['historical_expected_source_hashes'];full(previous_sources)
        archive.merge(sources,previous_sources)
        if any(previous_sources.get(p)!=h for p,h in snapshot['sources'].items()):raise ValueError('Final index omitted invocation source')
        if pack(index)!=pack(index_value(snapshot,folder,entries,previous_sources)):raise ValueError('Exact finalized index and scope required')
    if len(entries)>len(tasks) or [e['task_id'] for e in entries]!=[unpack(t)['task_id'] for t in tasks[:len(entries)]]:raise ValueError('Only an exact completed historical prefix may resume')
    expected_dirs={e['task_id'] for e in entries}
    for path in folder.iterdir():
        if path.is_dir():
            if path.name not in expected_dirs:raise ValueError('Unindexed attempt directory prevents any new fit')
        elif not (path.is_file() and path.name.startswith('index_') and path.suffix=='.json'):raise ValueError('Unindexed orphan prevents fitting')
    for entry,task_bytes in zip(entries,tasks):
        task=unpack(task_bytes);directory=folder/task['task_id']
        if {p.name for p in directory.iterdir()}!={'started.json','raw.json','result.json'}:raise ValueError('Incomplete or failed attempt cannot resume')
        if set(entry)!={'task_id','started_reference','raw_reference','result_reference'}:raise ValueError('Exact completed entry schema required')
        values={}
        for kind,name in [('started','started.json'),('raw','raw.json'),('result','result.json')]:
            ref=entry[kind+'_reference']
            if ref['path']!=str(directory/name):raise ValueError('Task file address differs')
            values[kind]=read(ref,sources)
        if pack(values['started'])!=pack(marker_value(snapshot,task)):raise ValueError('Historical attempt metadata differs')
        local=dict(snapshot['sources']);archive.merge(local,{entry['started_reference']['path']:entry['started_reference']['sha256']})
        expected_raw=raw_value(snapshot,task,values['raw']['result'],entry['started_reference'],local)
        if pack(values['raw'])!=pack(expected_raw):raise ValueError('Original raw fit receipt differs')
        archive.merge(local,{entry['raw_reference']['path']:entry['raw_reference']['sha256']})
        expected_result=result_value(snapshot,task,values['raw']['result'],entry['started_reference'],entry['raw_reference'],local,frame)
        if pack(values['result'])!=pack(expected_result):raise ValueError('Complete checkpoint/result/source/scope differs')
        archive.merge(sources,local)
    if previous_sources is not None:
        for entry in entries:
            for key in ('started_reference','raw_reference','result_reference'):
                ref=entry[key]
                if previous_sources.get(ref['path'])!=ref['sha256']:raise ValueError('Final index omitted completed artifact source')
    full(sources);new_count=0
    try:
        for task_bytes in tasks[len(entries):len(entries)+max_new]:
            task=unpack(task_bytes);directory=folder/task['task_id']
            if directory.exists():raise ValueError('Historical attempt already exists; never refit')
            check_ram(snapshot,task_bytes,frame,sealed_frame)
            started=publish(directory/'started.json',marker_value(snapshot,task));local=dict(snapshot['sources']);archive.merge(local,{started['path']:started['sha256']});raw_ref=None
            try:
                check_ram(snapshot,task_bytes,frame,sealed_frame,started)
                arguments=dict(returns=frame.copy(deep=True),cutoff=task['cutoff'],selected=deepcopy(task['selected']),weight_spec=task['weight_spec'],previous_target_weights=None,**deepcopy(task['parameters']))
                selected_before=pack(arguments['selected']);matrix_before=pack(frame_payload(arguments['returns']))
                result=fitter.refit_dynamic_cutoff_weights(**arguments)
                raw_ref=publish(directory/'raw.json',raw_value(snapshot,task,result,started,local))
                archive.merge(local,{raw_ref['path']:raw_ref['sha256']})
                if pack(arguments['selected'])!=selected_before or pack(frame_payload(arguments['returns']))!=matrix_before:raise ValueError('Fitter mutated supplied historical arguments')
                check_ram(snapshot,task_bytes,frame,sealed_frame,started)
                saved=publish(directory/'result.json',result_value(snapshot,task,result,started,raw_ref,local,frame))
                check_ram(snapshot,task_bytes,frame,sealed_frame,started)
                if sha(raw_ref['path'])!=raw_ref['sha256'] or sha(saved['path'])!=saved['sha256']:raise ValueError('Published checkpoint bytes changed')
                entries.append(dict(task_id=task['task_id'],started_reference=started,raw_reference=raw_ref,result_reference=saved));new_count+=1
                archive.merge(sources,local);archive.merge(sources,{saved['path']:saved['sha256']})
            except BaseException as error:
                publish(directory/'failure.json',dict(schema='HISTORICAL_CROSS_K_FAILED_ATTEMPT_V1',task_id=task['task_id'],started_reference=started,raw_reference=raw_ref,error_type=type(error).__name__,automatic_retry_allowed=False,failure_is_economic_infeasibility=False))
                raise
        full(sources);value=index_value(snapshot,folder,entries,sources);path=folder/('index_'+producer.digest(value)+'.json')
        if path.exists():
            if pack(json.loads(path.read_bytes()))!=pack(value):raise ValueError('Existing finalized index differs')
            saved=dict(path=str(path),sha256=sha(path))
        else:saved=publish(path,value)
        full(sources)
        return dict(index_reference=saved,completed_new=len(entries),new_fits_this_invocation=new_count,external_reference_count=1,result_imported=False)
    finally:full(sources)


def raw_value(snapshot,task,result,started,sources):
    return dict(schema='HISTORICAL_CROSS_K_RAW_FIT_V1',plan_reference=snapshot['plan_reference'],task=task,result=result,started_reference=started,runtime=snapshot['runtime'],historical_expected_source_hashes=sources,fit_performed=True,**dict.fromkeys(FALSE,False))


def result_value(snapshot,task,result,started,raw_ref,sources,frame):
    details=validate_result(result,task,frame,snapshot['numerical'])
    return dict(schema='HISTORICAL_CROSS_K_CHECKPOINT_V1',plan_reference=snapshot['plan_reference'],task=task,result=result,started_reference=started,raw_reference=raw_ref,
        independent_matrix_and_risk_checks=details,status='FITTED_FIVE_RISKS_PASSED' if details['risk_pass'] else 'FITTED_FIVE_RISKS_FAILED',
        historical_expected_source_hashes=sources,archive_resolution=task_partition(snapshot,sources),fit_performed=True,**dict.fromkeys(FALSE,False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);p.add_argument('--max-new',type=int,default=0);p.add_argument('--index-path');p.add_argument('--index-sha256');print(json.dumps(run(**vars(p.parse_args()))))
