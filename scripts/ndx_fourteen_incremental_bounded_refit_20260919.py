"""Bounded new-input fits only. Old 764 results stay external references."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_latest_conditional_all_k_refit_20260919 as original
from scripts import ndx_latest_fourteen_incremental_plan_20260919 as producer

# Filled only after review and external sealing; no discovery or self-signing.
PLAN_PATH=ROOT/'data/cache/research/latest_fourteen_incremental_refit_20260919_v1/plan.json'
PLAN_SHA='b604b6f5ca1385c83d4fea3fb930b0ddc6e3a1bb30eeab665261f4b53ed5b563'
PRODUCER_SHA='ff789ced2e2892b12d8cf9fc5bbda640a8afce748381c6c427c9b424c2c8756b'
ORIGINAL_SHA='4f6383a40c730d20a52fdb636570fffe23834a6bdb6cc06c738c4caa47a69898'
LOADED={str(Path(m.__file__).resolve()):hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (original,producer)}
LOADED[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
FALSE=original.FALSE


def pack(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def unpack(value):return json.loads(value)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(ref,sources):return original.read(ref['path'],ref['sha256'],sources)
def full(sources):return original.verify_sources(sources)


def select_new_tasks(plan):
    delta=plan['delta'];rows=delta['tasks']
    if plan['schema']!='SOURCE_BOUND_FOURTEEN_INCREMENTAL_PLAN_V1' or any(plan[k] is not False for k in ('result_import_performed','fit_performed','automatic_refit_authorized','point_in_time_verified','promotion_allowed')):raise ValueError('Exact pending delta scope required')
    if len(rows)!=31828 or delta['old_canonical_count']!=764 or delta['new_canonical_count']!=31828 or delta['input_equivalent_old_count']!=764 or delta['new_input_count']!=31064 or delta['completed_old_reference_count']!=764:raise ValueError('Exact old/new denominator required')
    tasks=[];old=[];ids=set()
    for row in rows:
        task=row['task'];identifier=original.digest(task)
        if row['task_id']!=identifier or identifier in ids or row['result_reused'] is not False:raise ValueError('Unique exact task identity required')
        ids.add(identifier)
        if row['input_equivalent_to_old_task'] is True:
            if row['completed_old_result_verified'] is not True or not row['completed_old_result_reference'] or row['old_equivalent_task_id']!=identifier or row['status']!='OLD_INPUT_EQUIVALENT_RESULT_REFERENCE_VERIFIED_NOT_IMPORTED':raise ValueError('Old result must remain independently verified reference')
            old.append(dict(task_id=identifier,reference=row['completed_old_result_reference']))
        else:
            if row['input_equivalent_to_old_task'] is not False or row['completed_old_result_verified'] is not False or row['old_equivalent_task_id'] is not None or row['completed_old_result_reference'] is not None or row['status']!='PENDING_OLD_OR_NEW':raise ValueError('Only genuinely new inputs enter fitter queue')
            tasks.append(dict(task,task_id=identifier))
    if len(old)!=764 or len(tasks)!=31064:raise ValueError('Exact reference/fit queue sizes required')
    return tuple(pack(task) for task in sorted(tasks,key=lambda t:t['task_id'])),tuple(pack(v) for v in sorted(old,key=lambda t:t['task_id']))


def prepare(path,expected_sha):
    if PLAN_SHA is None or PRODUCER_SHA is None:raise ValueError('Await externally sealed delta plan and producer')
    reference=dict(path=str(Path(path).resolve()),sha256=expected_sha)
    if reference!={'path':str(PLAN_PATH),'sha256':PLAN_SHA} or LOADED[str(Path(producer.__file__).resolve())]!=PRODUCER_SHA or LOADED[str(Path(original.__file__).resolve())]!=ORIGINAL_SHA:raise ValueError('Hard plan/source differs')
    sources=dict(LOADED);plan=read(reference,sources)
    original.archive.merge(sources,plan['historical_expected_source_hashes'])
    full(sources)
    tasks,old=select_new_tasks(plan)
    document=read(plan['new_panel_reference'],sources);panel=original.panel_io.typed_decode(document['panel'])
    if panel['conditional_security_count']!=14:raise ValueError('Exact independently audited fourteen panel required')
    numeric=original.fitter._sources();original.archive.merge(sources,numeric)
    # Private, immutable queue/metadata snapshot. No mutable plan reaches a fitter.
    snapshot=dict(reference=reference,panel_reference=plan['new_panel_reference'],audit_reference=plan['new_panel_audit_reference'],
        sources=sources,numerical=numeric,old_references=[unpack(v) for v in old])
    full(sources)
    return pack(snapshot),tasks,panel


def index_value(reference,folder,entries,*,finalized):
    return dict(schema='FOURTEEN_INCREMENTAL_BOUNDED_INDEX_V1',plan_reference=reference,output_directory=str(folder),
        original_reference_count=764,new_input_planned=31064,new_input_completed=len(entries),new_input_pending=31064-len(entries),
        status='COMPLETE' if len(entries)==31064 else 'PARTIAL',finalized_after_full_source_verification=finalized,
        entries=entries,old_results_imported=0,**dict.fromkeys(FALSE,False))


def small_verify(snapshot_bytes,task_bytes,panel,panel_digest,actual,current_marker=None):
    snapshot=unpack(snapshot_bytes);task=unpack(task_bytes)
    if original.digest(original.panel_io.typed_encode(panel))!=panel_digest:raise ValueError('Typed RAM snapshot changed')
    if original.digest({k:v for k,v in task.items() if k!='task_id'})!=task['task_id']:raise ValueError('Immutable task identity differs')
    required=snapshot['sources']
    for path,h in actual.items():
        if path not in required:
            if current_marker is None or path!=str(current_marker):raise ValueError('Unknown task source')
            if sha(path)!=h:raise ValueError('Attempt marker changed')
        elif required[path]!=h:raise ValueError('Source digest replaced')
    if any(actual.get(p)!=h for p,h in required.items()):raise ValueError('Complete snapshot source omitted')
    for path,h in required.items():
        if Path(path).suffix=='.py' and sha(path)!=h:raise ValueError('Loaded numerical/research code changed')
    selected=original.panel_core.selected_mapping(panel,list(task['selected']))
    if pack(selected)!=pack(task['selected']):raise ValueError('Selected panel coordinate changed')


def validate_saved(value,task,snapshot,marker_ref,contract,panel):
    keys={'schema','plan_reference','task','result','attempt_count','old_results_imported','status','historical_expected_source_hashes','archive_resolution'}|set(FALSE)
    if set(value)!=keys or value['schema']!='FOURTEEN_INCREMENTAL_SINGLE_REFIT_V1' or pack(value['plan_reference'])!=pack(snapshot['reference']) or pack(value['task'])!=pack(task) or type(value['attempt_count']) is not int or value['attempt_count']!=1 or any(value.get(k) is not False for k in FALSE) or type(value['old_results_imported']) is not int or value['old_results_imported']!=0:raise ValueError('Recovered task scope differs')
    original.check_result(value['result'],task,panel)
    if task['weight_spec']=='equal_weight' and any(row['target_weight']!=1./len(task['selected']) for row in value['result']['targets'].values()):raise ValueError('Original equal weights must be exactly equal')
    if pack(value['result']['source_hashes'])!=pack(snapshot['numerical']):raise ValueError('Original numerical closure differs')
    passed=value['result']['declared_constraints_passed']
    if value['status']!=('FITTED_ORIGINAL_FIVE_RISKS_PASSED' if passed else 'FITTED_ORIGINAL_FIVE_RISKS_FAILED'):raise ValueError('Risk status differs')
    required=dict(snapshot['sources']);original.archive.merge(required,{marker_ref['path']:marker_ref['sha256']})
    if pack(value['historical_expected_source_hashes'])!=pack(required):raise ValueError('Exact complete per-task closure required')
    if pack(value['archive_resolution'])!=pack(original.declared_partition(required,contract)):raise ValueError('Task partition differs')


def run_bounded(path,expected_sha,folder,*,max_new=0,index_path=None,index_sha256=None):
    if type(max_new) is not int or not 0<=max_new<=100:raise ValueError('Explicit integer budget 0..100 required')
    snapshot_bytes,tasks,panel=prepare(path,expected_sha);snapshot=unpack(snapshot_bytes)
    panel_digest=original.digest(original.panel_io.typed_encode(panel));sources=dict(snapshot['sources'])
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True);entries=[]
    if (index_path is None)!=(index_sha256 is None):raise ValueError('External index path/SHA pair required')
    if index_path is not None:
        index=read(dict(path=str(Path(index_path).resolve()),sha256=index_sha256),sources);entries=index['entries']
        if pack(index)!=pack(index_value(snapshot['reference'],folder,entries,finalized=True)):raise ValueError('Only externally bound finalized index may resume')
    if len(entries)>len(tasks) or [e['task_id'] for e in entries]!=[unpack(t)['task_id'] for t in tasks[:len(entries)]]:raise ValueError('Exact new-task completed prefix required')
    allowed={e['task_id']+suffix for e in entries for suffix in ('.json','.json.started.json')}
    for item in folder.glob('*.json'):
        if item.name not in allowed and not item.name.startswith(('progress_','index_')):raise ValueError('Unindexed attempt/result/failure refuses fitting')
    contract=original.archive.load_contract()
    for entry,task_bytes in zip(entries,tasks):
        task=unpack(task_bytes);output=folder/(task['task_id']+'.json');marker=Path(str(output)+'.started.json')
        if set(entry)!={'task_id','path','sha256','started_sha256'} or entry['path']!=str(output):raise ValueError('Exact task address required')
        value=read(dict(path=str(output),sha256=entry['sha256']),sources);marker_ref=dict(path=str(marker),sha256=entry['started_sha256'])
        started=read(marker_ref,sources)
        if pack(started)!=pack(dict(schema='FOURTEEN_INCREMENTAL_SINGLE_ATTEMPT_V1',plan_reference=snapshot['reference'],task_id=task['task_id'],attempt_count=1)):raise ValueError('Original exclusive marker differs')
        validate_saved(value,task,snapshot,marker_ref,contract,panel)
        original.archive.merge(sources,value['historical_expected_source_hashes'])
    full(sources);new_count=0
    try:
        for task_bytes in tasks[len(entries):len(entries)+max_new]:
            task=unpack(task_bytes);output=folder/(task['task_id']+'.json');marker=Path(str(output)+'.started.json');failure=Path(str(output)+'.failure.json')
            if any(p.exists() for p in (output,marker,failure)):raise ValueError('Existing attempt refuses automatic refit')
            local=dict(snapshot['sources']);small_verify(snapshot_bytes,task_bytes,panel,panel_digest,local)
            published=original.exclusive_publish(marker,dict(schema='FOURTEEN_INCREMENTAL_SINGLE_ATTEMPT_V1',plan_reference=snapshot['reference'],task_id=task['task_id'],attempt_count=1))
            original.archive.merge(local,{published['path']:published['sha256']})
            try:
                small_verify(snapshot_bytes,task_bytes,panel,panel_digest,local,marker)
                # Exactly one original full refit. Old references never enter here.
                result=original.fitter.refit_dynamic_cutoff_weights(returns=panel['returns'],cutoff=task['cutoff'],selected=task['selected'],weight_spec=task['weight_spec'],previous_target_weights=None,**task['parameters'])
                if pack(task)!=task_bytes:raise ValueError('Fitter changed the explicit task input')
                task=unpack(task_bytes)
                small_verify(snapshot_bytes,task_bytes,panel,panel_digest,local,marker)
                value=dict(schema='FOURTEEN_INCREMENTAL_SINGLE_REFIT_V1',plan_reference=snapshot['reference'],task=task,result=result,attempt_count=1,old_results_imported=0,
                    status='FITTED_ORIGINAL_FIVE_RISKS_PASSED' if result['declared_constraints_passed'] else 'FITTED_ORIGINAL_FIVE_RISKS_FAILED',
                    historical_expected_source_hashes=local,archive_resolution=original.declared_partition(local,contract),**dict.fromkeys(FALSE,False))
                validate_saved(value,task,snapshot,published,contract,panel)
                saved=original.exclusive_publish(output,value);small_verify(snapshot_bytes,task_bytes,panel,panel_digest,local,marker)
                entries.append(dict(task_id=task['task_id'],**saved,started_sha256=published['sha256']));new_count+=1
                original.archive.merge(sources,local);original.archive.merge(sources,{saved['path']:saved['sha256']})
                progress=index_value(snapshot['reference'],folder,entries,finalized=False)
                original.exclusive_publish(folder/('progress_'+original.digest(progress)+'.json'),progress)
            except BaseException as exc:
                if not failure.exists():original.exclusive_publish(failure,dict(schema='FOURTEEN_INCREMENTAL_FAILED_ATTEMPT_V1',task_id=task['task_id'],plan_reference=snapshot['reference'],error_type=type(exc).__name__,partial_result=None,automatic_retry_allowed=False))
                raise
        full(sources)
        final=index_value(snapshot['reference'],folder,entries,finalized=True)
        final_path=folder/('index_'+original.digest(final)+'.json')
        if final_path.exists():
            if pack(json.loads(final_path.read_bytes()))!=pack(final):raise ValueError('Existing final index differs')
            saved=dict(path=str(final_path),sha256=sha(final_path))
        else:saved=original.exclusive_publish(final_path,final)
        full(sources)
        return dict(index_reference=saved,completed=len(entries),new_fits_this_invocation=new_count,old_reference_count=764,old_results_imported=0)
    finally:full(sources)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--folder',required=True);p.add_argument('--max-new',type=int,default=0);p.add_argument('--index');p.add_argument('--index-sha256');a=p.parse_args()
    print(json.dumps(run_bounded(a.plan,a.plan_sha256,a.folder,max_new=a.max_new,index_path=a.index,index_sha256=a.index_sha256)))
