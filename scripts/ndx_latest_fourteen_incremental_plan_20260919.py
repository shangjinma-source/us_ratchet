"""Source-bound pending delta plan. No fitting, importing, or automatic retries."""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_latest_fourteen_conditional_panel_20260919 as panel14
from scripts import ndx_latest_all_k_completed_audit_publish_v2_20260919 as audit9
from backtest import ndx_conditional_panel_incremental_plan_research as pure
old=panel14.old;archive=old.archive
PLAN=dict(path=str(old.BASE/'latest_conditional_all_k_refit_20260919_v1/plan.json'),sha256='7b9cd1fd9dbbc9c42625495e73803e633a81f86039e1e1113ba9de3d295c52f0')
OLD_INDEX=dict(path=str(old.BASE/'latest_conditional_all_k_refit_20260919_v1/tasks/index_ea701a3e672b371f934cdb3c6b109f919ce72f5ff5b70759fedda0694af0f113.json'),sha256='df98a564d94363fb7c88be55db2f62fd5d3dfd1ffaeda3850fb5f9a50a2cf13d')
OLD_AUDIT=dict(path=str(old.BASE/'latest_conditional_all_k_refit_20260919_v1/completed_764_independent_audit_v2.json'),sha256='7a30bd765f16707f8e6f7ce46e447b27c6f58f0dccffa34e69694d3ef9b4882f')
PANEL14=dict(path=str(old.BASE/'latest_fourteen_conditional_panel_20260919_v1/panel.json'),sha256='63638aab89a75147f8d9a0eb827173a221aa81f0df7f47967f3e5a5f2fd76b61')
PURE_SHA='9876a6d28e575e5a96d2db6678da77c910c0642ab2b0d65ba5154405342b53f6'
PRODUCER_SHA='b231418888fc8b7588b3565a8498574dadbb3410d68d7a46827fe312b9d6d384'
# Filled only after the independently reviewed fourteen-panel reader is sealed.
AUDIT14_PATH=old.BASE/'latest_fourteen_conditional_panel_20260919_v1/independent_readback.json'
AUDIT14_SHA='8de9db0caf5816ee348554e3b9af48b7b656ceb21548d1398d8de504559f249f'
AUDIT14_READER_SHA='a8b83195ea607ba94aec2e26bc97850d9fdf6797013807bdc73700afb2973e25'
LOADED={str(Path(m.__file__).resolve()):hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (panel14,audit9,pure)}
LOADED[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
archive.merge(LOADED,{str(Path(pure.core.__file__).resolve()):hashlib.sha256(Path(pure.core.__file__).read_bytes()).hexdigest(),
    str(Path(pure.bounds.__file__).resolve()):hashlib.sha256(Path(pure.bounds.__file__).read_bytes()).hexdigest()})
archive.merge(LOADED,pure.bounds._LOADED)


def validate_audit14(value):
    """Only the subsequently sealed independent reader may validate its contract."""
    if AUDIT14_READER_SHA is None:raise ValueError('Fourteen independent audit reader has not been sealed')
    from scripts import ndx_latest_fourteen_panel_independent_readback_20260919 as reader
    path=Path(reader.__file__).resolve()
    if hashlib.sha256(path.read_bytes()).hexdigest()!=AUDIT14_READER_SHA:raise ValueError('Independent fourteen reader source differs')
    reader.validate_report(value)
    if not old.batch.exact(value['panel_reference'],PANEL14):raise ValueError('Independent fourteen panel reference differs')
    if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in reader.LOADED.items()):raise ValueError('Fourteen reader source closure omitted')
    if value['historical_expected_source_hashes'].get(str(path))!=AUDIT14_READER_SHA:raise ValueError('Hard fourteen reader omitted')
    if not old.batch.exact(audit9.old.declared_partition(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution']):raise ValueError('Fourteen audit source partition differs')


def mark_completed(plan,old_plan,old_audit):
    """External bytes and independent readback are verified by build, not this helper."""
    tasks={t['task_id']:t for t in old_plan['canonical_tasks']}
    if len(tasks)!=len(old_plan['canonical_tasks']):raise ValueError('Unique old canonical task IDs required')
    details={d['task_id']:d for d in old_audit['details']}
    if len(details)!=len(old_audit['details']) or not set(details)<=set(tasks):raise ValueError('Unique known completed tasks required')
    count=0
    for row in plan['tasks']:
        if row.get('status')!='PENDING_OLD_OR_NEW' or row.get('completed_old_result_verified') is not False or row.get('result_reused') is not False:
            raise ValueError('Only fresh unauthenticated pending delta rows allowed')
        row['completed_old_result_reference']=None
        prior=row['old_equivalent_task_id']
        if prior is None or prior not in details:continue
        if not old.batch.exact(dict(row['task'],task_id=prior),tasks[prior]) or row['fit_data_sha256']!=details[prior]['fit_data_sha256']:
            raise ValueError('Old completed task/matrix differs from new input')
        row.update(status='OLD_INPUT_EQUIVALENT_RESULT_REFERENCE_VERIFIED_NOT_IMPORTED',completed_old_result_verified=True,
            completed_old_result_reference=copy.deepcopy(details[prior]['checkpoint_reference']),result_reused=False)
        count+=1
    plan['completed_old_reference_count']=count
    plan['pending_old_or_new_count']=len(plan['tasks'])-count


def build(*,new_audit_path,new_audit_sha,index_path,index_sha,old_audit_path,old_audit_sha,completed_prefix_confirmed=False):
    if (AUDIT14_SHA is None or Path(new_audit_path).resolve()!=AUDIT14_PATH.resolve() or new_audit_sha!=AUDIT14_SHA):
        raise ValueError('Sealed independent fourteen audit path/SHA required')
    if completed_prefix_confirmed is not True:raise ValueError('Caller must confirm bounded old run has ended')
    if not old.batch.exact(dict(path=str(Path(index_path).resolve()),sha256=index_sha),OLD_INDEX) or not old.batch.exact(dict(path=str(Path(old_audit_path).resolve()),sha256=old_audit_sha),OLD_AUDIT):
        raise ValueError('This delta version binds the completed 764 index and independent audit')
    if LOADED[str(Path(pure.__file__).resolve())]!=PURE_SHA or LOADED[str(Path(panel14.__file__).resolve())]!=PRODUCER_SHA:
        raise ValueError('Frozen delta/panel code differs')
    sources=dict(LOADED)
    def read(ref):return old.batch.read(ref,sources)
    before=read(panel14.PANEL);after=read(PANEL14);plan=read(PLAN)
    new_audit=read(dict(path=str(Path(new_audit_path).resolve()),sha256=new_audit_sha));validate_audit14(new_audit)
    previous_audit=read(dict(path=str(Path(old_audit_path).resolve()),sha256=old_audit_sha))
    indexref=dict(path=str(Path(index_path).resolve()),sha256=index_sha);index=read(indexref)
    if not old.batch.exact(previous_audit['index_reference'],indexref):raise ValueError('Old audit/index external binding differs')
    audit9.validate_report(previous_audit,plan,index)
    for value in (before,after,plan,new_audit,previous_audit):archive.merge(sources,value['historical_expected_source_hashes'])
    archive.verify_expected_sources(sources,archive.load_contract())
    # One independent readback scans each saved task/marker and 126 matrix, merges
    # their sources, and hashes the union only at its boundaries; never calls a fitter.
    actual=audit9.build(indexref['path'],indexref['sha256'],completed_prefix_confirmed=True)
    if not old.batch.exact(actual,previous_audit):raise ValueError('Entire old completed-prefix audit does not reproduce')
    panel14.verify(after)
    old_panel=old.typed_decode(before['panel']);new_panel=old.typed_decode(after['panel'])
    if not old.batch.exact(plan['panel_reference'],panel14.PANEL):raise ValueError('Hard old plan/panel binding differs')
    parameters=plan['canonical_tasks'][0]['parameters']
    if any(not old.batch.exact(t['parameters'],parameters) for t in plan['canonical_tasks']):raise ValueError('Original eight parameters inconsistent')
    numerical=audit9.old.numerical_sources._sources()
    result=pure.build_incremental_plan(old_panel=old_panel,new_panel=new_panel,old_parameters=parameters,new_parameters=parameters,
        old_fitter_sources=numerical,new_fitter_sources=numerical,exact_limit=50000)
    mark_completed(result,plan,actual)
    archive.merge(sources,actual['historical_expected_source_hashes']);archive.merge(sources,numerical)
    return dict(schema='SOURCE_BOUND_FOURTEEN_INCREMENTAL_PLAN_V1',delta=result,old_panel_reference=panel14.PANEL,new_panel_reference=PANEL14,
        old_plan_reference=PLAN,new_panel_audit_reference=dict(path=str(Path(new_audit_path).resolve()),sha256=new_audit_sha),
        old_index_reference=indexref,old_independent_audit_reference=dict(path=str(Path(old_audit_path).resolve()),sha256=old_audit_sha),
        historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,archive.load_contract()),
        result_import_performed=False,fit_performed=False,automatic_refit_authorized=False,point_in_time_verified=False,promotion_allowed=False)


def verify(value):
    if value.get('schema')!='SOURCE_BOUND_FOURTEEN_INCREMENTAL_PLAN_V1':raise ValueError('Exact delta source schema required')
    for key in ('result_import_performed','fit_performed','automatic_refit_authorized','point_in_time_verified','promotion_allowed'):
        if value.get(key) is not False:raise ValueError('Delta publication boundary upgraded')
    required=dict(LOADED)
    for ref in (PLAN,PANEL14,panel14.PANEL,OLD_INDEX,OLD_AUDIT):archive.merge(required,{ref['path']:ref['sha256']})
    if AUDIT14_SHA is None:raise ValueError('Independent fourteen audit not sealed')
    archive.merge(required,{str(AUDIT14_PATH):AUDIT14_SHA})
    sources=value['historical_expected_source_hashes']
    if any(sources.get(p)!=h for p,h in required.items()):raise ValueError('Delta publication sources omitted or re-signed')
    expected=build(new_audit_path=str(AUDIT14_PATH),new_audit_sha=AUDIT14_SHA,
        index_path=OLD_INDEX['path'],index_sha=OLD_INDEX['sha256'],old_audit_path=OLD_AUDIT['path'],old_audit_sha=OLD_AUDIT['sha256'],completed_prefix_confirmed=True)
    if not old.batch.exact(value,expected):raise ValueError('Complete delta plan/source report does not reproduce')


def publish_verified(path,value):
    if Path(path).exists():raise FileExistsError('Create-only delta plan')
    verify(value)
    saved=old.batch.recipe.exclusive_publish(path,value)
    if not old.batch.exact(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution']):raise ValueError('Delta source changed after publication')
    return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--new-audit',required=True);parser.add_argument('--new-audit-sha',required=True)
    parser.add_argument('--index',required=True);parser.add_argument('--index-sha',required=True)
    parser.add_argument('--old-audit',required=True);parser.add_argument('--old-audit-sha',required=True)
    parser.add_argument('--completed-prefix-confirmed',action='store_true');parser.add_argument('--output',required=True)
    args=parser.parse_args()
    value=build(new_audit_path=args.new_audit,new_audit_sha=args.new_audit_sha,index_path=args.index,index_sha=args.index_sha,old_audit_path=args.old_audit,old_audit_sha=args.old_audit_sha,completed_prefix_confirmed=args.completed_prefix_confirmed)
    print(json.dumps(publish_verified(args.output,value)))
