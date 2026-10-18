"""Independent scalar/Decimal audit with explicit immutable archive resolution."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_selected_completed_queue_independent_audit_20260919 as original
from backtest import ndx_root_price_archive_contract_research as archive

SCHEMA='SELECTED_ARCHIVE_COMPLETED_INDEPENDENT_SCALAR_DECIMAL_AUDIT_V1'
LOADED=dict(original.LOADED)
LOADED.update({str(Path(__file__).resolve()):original.drift.file_sha(__file__),str(archive.SOURCE):archive.LOADED})
FLAGS=('historical_full_source_closure_verified','original_live_price_paths_verified','point_in_time_verified','promotion_allowed')


def audit_view(value,row,manifest_reference,legacy_entry,read):
    """Validate the complete new envelope before adapting only its numeric view."""
    if (value.get('schema')!='SELECTED_ARCHIVE_RESOLUTION_TASK_V1' or value.get('new_job_id')!=row['new_job_id']
        or not original.exact(value['original'],row) or value['manifest_path']!=manifest_reference['path']
        or value['manifest_sha256']!=manifest_reference['sha256']):raise ValueError('Archive task coordinates differ')
    original.require_false(value,FLAGS+('original_historical_provenance_verified','non20_risk_projection_fields_independently_recomputed',
        'binary_float_ledger_hash_independently_verified','source_closure_finalized'))
    if value.get('saved_result_revalidation_scope')!=original.SCOPE:raise ValueError('Unsupported audit scope')
    if legacy_entry is not None:
        if value.get('mode')!='LEGACY_COMPLETED_RESULT_RESTORED_NO_NEW_FIT' or value.get('legacy_completed_artifact')!=legacy_entry:
            raise ValueError('Original completed artifact binding differs')
        old=read(legacy_entry['path'],legacy_entry['sha256'])
        if not original.exact(old,value['legacy_original_wrapper']) or not original.exact(old['result'],value['result']) or old['input_digests']!=value['input_digests']:
            raise ValueError('Whole original wrapper/result was not preserved')
        return old
    if value.get('mode')!='ONE_NEW_INPUT_FULL_V3_EVALUATION_NO_OLD_WINDOW_REUSE' or 'legacy_completed_artifact' in value or 'legacy_original_wrapper' in value:
        raise ValueError('Unperformed legacy import cannot be claimed')
    view=deepcopy(value)
    view.update(schema='ndx_selected_delta_exact_gap_task_v1',manifest_path=str(original.MANIFEST),manifest_sha256=original.MANIFEST_SHA)
    return view


def check_index(index,manifest,reference):
    n=len(index['completed']);planned=manifest['planned'];final=index.get('finalization')
    if (index.get('schema')!='SELECTED_ARCHIVE_RESOLUTION_COMPLETION_INDEX_V1' or index.get('manifest')!=reference
        or type(index.get('planned')) is not int or index['planned']!=planned or not 2<=n<=planned
        or not isinstance(final,dict) or final.get('schema')!='SELECTED_ARCHIVE_RESOLUTION_FINALIZATION_V1'
        or type(final.get('completed')) is not int or final['completed']!=n or type(final.get('planned')) is not int or final['planned']!=planned
        or final.get('immutable_numerical_source_closure_verified') is not True):raise ValueError('Finalized archive prefix required')
    status='COMPLETE' if n==planned else 'PARTIAL'
    if index.get('status')!=status or final.get('status')!=status:raise ValueError('Incorrect completion status')
    original.require_false(index,FLAGS);original.require_false(final,FLAGS+('original_historical_provenance_verified',))
    ids=[r['new_job_id'] for r in manifest['tasks'][:n]]
    if len(set(ids))!=n or [Path(e['path']).stem for e in index['completed']]!=ids or len({e['path'] for e in index['completed']})!=n:
        raise ValueError('Exact ordered distinct completed prefix required')
    return ids


def verify_report(report):
    if report.get('schema')!=SCHEMA:raise ValueError('New archive audit schema required')
    original.require_false(report,FLAGS+('optimizer_or_original_simulator_called','saved_non20_fields_independently_recomputed',
        'binary_float_ledger_hash_independently_verified','nominal_quote_authenticity_verified','dynamic_next_open_execution_validated'))
    expected=report['historical_expected_source_hashes']
    if any(expected.get(p)!=h for p,h in LOADED.items()):raise ValueError('Loaded independent source omitted')
    checked=archive.verify_expected_sources(expected,archive.load_contract())
    for key in ('live_verified_source_hashes','archive_resolutions','historical_gap_observations'):
        if not original.exact(report[key],checked[key]):raise ValueError('Archive partition changed')
    if len(checked['archive_resolutions'])!=85 or len(checked['historical_gap_observations'])!=26:raise ValueError('Complete 111 source denominator required')
    for row in report['tasks']:original.verify_gaps(row['historical_loader_provenance_gaps'])


def build(*,manifest_path,manifest_sha256,index_path,index_sha256):
    sources=dict(LOADED)
    def include(mapping):archive.merge(sources,mapping)
    def read(path,sha):
        path=str(Path(path).resolve());raw=Path(path).read_bytes()
        if original.hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External artifact SHA differs')
        include({path:sha});return json.loads(raw)
    reference=dict(path=str(Path(manifest_path).resolve()),sha256=manifest_sha256)
    manifest=read(**dict(path=reference['path'],sha=reference['sha256']))
    legacy=read(original.MANIFEST,original.MANIFEST_SHA);parent=read(original.drift.SELECTED_PLAN,original.drift.SELECTED_PLAN_SHA)
    if (manifest.get('schema')!='SELECTED_ARCHIVE_RESOLUTION_MANIFEST_V1'
        or manifest['legacy_manifest']!=dict(path=str(original.MANIFEST),sha256=original.MANIFEST_SHA)
        or manifest['parent_plan']!=dict(path=str(original.drift.SELECTED_PLAN),sha256=original.drift.SELECTED_PLAN_SHA)
        or manifest['archive_manifest']!=dict(path=str(archive.ARCHIVE),sha256=archive.ARCHIVE_SHA)
        or not original.exact(manifest['tasks'],legacy['tasks']) or not original.exact(manifest['tasks'],[t for d in parent['dates'] for t in d['tasks']])
        or not original.exact(manifest['corrections'],legacy['corrections']) or not original.exact(manifest['corrections'],parent['errors'])
        or type(manifest['planned']) is not int or manifest['planned']!=len(legacy['tasks'])
        or type(manifest['context_count']) is not int or manifest['context_count']!=len({r['context_path'] for r in legacy['tasks']})):raise ValueError('Hard original full plan differs')
    original.require_false(manifest,FLAGS)
    seed=read(original.SEED,original.SEED_SHA)
    oldref=manifest['legacy_completed_index'];oldindex=read(oldref['path'],oldref['sha256'])
    oldids=original.check_index(oldindex,legacy,[r['new_job_id'] for r in seed['tasks']])
    if type(manifest['legacy_completed_count']) is not int or manifest['legacy_completed_count']!=len(oldids):raise ValueError('Legacy import denominator differs')
    legacy_entries=dict(zip(oldids,oldindex['completed']))
    for identifier,entry in legacy_entries.items():
        if Path(entry['path'])!=original.FOLDER/'tasks'/(identifier+'.json'):raise ValueError('Original task address differs')
    index=read(index_path,index_sha256);ids=check_index(index,manifest,reference);final=index['finalization']
    for mapping in (parent['source_hashes'],legacy['historical_expected_source_hashes'],oldindex['finalization']['historical_expected_source_hashes'],
        oldindex['finalization']['additional_provenance_hashes'],manifest['implementation_source_hashes'],final['historical_expected_source_hashes'],final['additional_provenance_hashes']):include(mapping)
    contract=archive.load_contract()
    finalized=dict(final['historical_expected_source_hashes']);archive.merge(finalized,final['additional_provenance_hashes'])
    checked=archive.verify_expected_sources(finalized,contract)
    for key in ('live_verified_source_hashes','archive_resolutions','historical_gap_observations'):
        if not original.exact(final[key],checked[key]):raise ValueError('Finalization archive source partition differs')
    archive.verify_expected_sources(sources,contract)
    for observation in parent['historical_context_gap_observations'].values():original.verify_gaps(observation['gaps'])
    tasks=[];folder=Path(index_path).resolve().parent
    for row,entry in zip(manifest['tasks'],index['completed']):
        identifier=row['new_job_id']
        if Path(entry['path']).resolve()!=folder/(identifier+'.json'):raise ValueError('New task address differs')
        value=read(entry['path'],entry['sha256']);view=audit_view(value,row,reference,legacy_entries.get(identifier),read)
        context=read(row['context_path'],row['context_sha256']);checkpoint=read(row['checkpoint_path'],row['checkpoint_sha256'])
        if parent['historical_context_gap_observations'][row['context_path']]!=dict(context_sha256=row['context_sha256'],gaps=view['result']['historical_loader_provenance_gaps']):raise ValueError('Hard historical loader gap differs')
        audit=original.audit_task(view,row,context,checkpoint,legacy)
        audit['archive_wrapper_mode']=value['mode'];tasks.append(audit)
    checked=archive.verify_expected_sources(sources,contract)
    report=dict(checked,schema=SCHEMA,planned=manifest['planned'],completed=len(tasks),status=index['status'],tasks=tasks,
        completed_queue_all_tasks_audited=True,manifest=reference,completed_index=dict(path=str(Path(index_path).resolve()),sha256=index_sha256),
        historical_expected_source_hashes=sources,historical_full_source_closure_verified=False,original_live_price_paths_verified=False,
        optimizer_or_original_simulator_called=False,saved_non20_fields_independently_recomputed=False,binary_float_ledger_hash_independently_verified=False,
        nominal_quote_authenticity_verified=False,dynamic_next_open_execution_validated=False,
        audit_view_adaptation_is_not_original_live_source_certification=True)
    verify_report(report);return report


def publish_verified(path,report):
    verify_report(report)
    target=Path(path).resolve();target.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf8')
    fd,name=tempfile.mkstemp(prefix='.'+target.name+'.',suffix='.tmp',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(name,target)
    finally:Path(name).unlink(missing_ok=True)
    verify_report(report)
    return dict(path=str(target),sha256=original.drift.file_sha(target),completed=report['completed'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest-path','manifest-sha256','index-path','index-sha256','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();report=build(manifest_path=args.manifest_path,manifest_sha256=args.manifest_sha256,index_path=args.index_path,index_sha256=args.index_sha256)
    print(json.dumps(publish_verified(args.output,report)))
