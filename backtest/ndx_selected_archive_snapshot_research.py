"""New archive-resolution snapshot; historical live-pointer claims are not reused."""
from copy import deepcopy
import json
from pathlib import Path
from types import FunctionType
from weakref import WeakKeyDictionary
from backtest import ndx_selected_delta_drift_snapshot_research as old
from backtest import ndx_root_price_archive_contract_research as archive

SOURCE=Path(__file__).resolve();LOADED=old.drift.file_sha(SOURCE)
STATES=WeakKeyDictionary()
FALSE_FLAGS=('historical_full_source_closure_verified','original_historical_provenance_verified','point_in_time_verified','promotion_allowed')


class Snapshot:
    __slots__=('__weakref__',)


def exact(a,b):
    return old.selected.encoding._json_bytes(a)==old.selected.encoding._json_bytes(b)


def sources():
    return old.sources()|{str(SOURCE):LOADED,str(archive.SOURCE):archive.LOADED}


def state(snapshot):
    if type(snapshot) is not Snapshot or snapshot not in STATES or STATES[snapshot]['closed']:
        raise ValueError('Unknown or closed archive snapshot')
    return STATES[snapshot]


def queue_entries(index,legacy):
    if (index.get('schema')!='ndx_selected_delta_exact_gap_completion_index_v1'
        or index.get('manifest')!=dict(path=str(archive.INVENTORY),sha256=archive.INVENTORY_SHA)
        or type(index.get('planned')) is not int or index['planned']!=legacy['planned']):
        raise ValueError('Hard legacy queue coordinate required')
    n=len(index['completed']);final=index.get('finalization');status='COMPLETE' if n==legacy['planned'] else 'PARTIAL'
    if not 1<=n<=legacy['planned'] or not isinstance(final,dict):raise ValueError('Finalized legacy prefix required')
    if (final.get('schema')!='ndx_selected_delta_exact_gap_finalization_v1' or index['status']!=status
        or final.get('status')!=status or type(final.get('completed')) is not int or final['completed']!=n
        or type(final.get('planned')) is not int or final['planned']!=legacy['planned']
        or final.get('immutable_numerical_source_closure_verified') is not True):raise ValueError('Legacy finalization denominator differs')
    for value in (index,final):
        if any(value.get(k) is not False for k in FALSE_FLAGS):raise ValueError('Legacy scope upgraded')
    entries={}
    for row,entry in zip(legacy['tasks'],index['completed']):
        identifier=row['new_job_id'];path=Path(entry['path'])
        if path!=archive.INVENTORY.parent/'tasks'/(identifier+'.json') or identifier in entries:
            raise ValueError('Exact ordered original task address required')
        entries[identifier]=entry
    indexed={Path(e['path']).resolve() for e in entries.values()}
    on_disk={p.resolve() for p in (archive.INVENTORY.parent/'tasks').glob('*.json') if not p.name.startswith('index_')}
    if indexed!=on_disk:raise ValueError('Legacy queue contains unindexed task; finalized full current prefix required')
    return entries


def build_manifest(*,legacy_index_path,legacy_index_sha256):
    legacy=old.read(archive.INVENTORY,archive.INVENTORY_SHA)
    parent=old.read(old.drift.SELECTED_PLAN,old.drift.SELECTED_PLAN_SHA)
    if not exact(legacy['tasks'],[r for d in parent['dates'] for r in d['tasks']]) or not exact(legacy['corrections'],parent['errors']):
        raise ValueError('Hard legacy plan tasks/corrections differ')
    path=str(Path(legacy_index_path).resolve());index=old.read(path,legacy_index_sha256)
    entries=queue_entries(index,legacy)
    return dict(schema='SELECTED_ARCHIVE_RESOLUTION_MANIFEST_V1',legacy_manifest=dict(path=str(archive.INVENTORY),sha256=archive.INVENTORY_SHA),
        parent_plan=dict(path=str(old.drift.SELECTED_PLAN),sha256=old.drift.SELECTED_PLAN_SHA),
        archive_manifest=dict(path=str(archive.ARCHIVE),sha256=archive.ARCHIVE_SHA),
        implementation_source_hashes=sources(),
        legacy_completed_index=dict(path=path,sha256=legacy_index_sha256),legacy_completed_count=len(entries),
        tasks=legacy['tasks'],corrections=legacy['corrections'],planned=legacy['planned'],context_count=legacy['context_count'],
        historical_full_source_closure_verified=False,original_live_price_paths_verified=False,point_in_time_verified=False,promotion_allowed=False)


def verify_all(s):
    expected=dict(s['expected']);old.merge(expected,s['additional'])
    checked=archive.verify_expected_sources(expected,s['contract'])
    for item in s['contexts'].values():
        old.check_memory(item)
        if item['context']['runtime']!=old.selected.current_runtime():raise ValueError('Actual runtime changed')
        if old.selected.provenance.validate_historical_evidence(item['context'],expected)!=item['gaps']:
            raise ValueError('Historical config observation changed')
    return checked


def verify_task(s,row):
    item=s['contexts'][row['context_path']];old.check_memory(item)
    if row['runtime']!=old.selected.current_runtime():raise ValueError('Actual runtime changed')
    old.verify_small(s,sources())
    # Large authority manifests and every archived byte are verified at begin,
    # finish and post-publication. Per-task retain the fixed resolver anchor.
    archive.strict({str(archive.ARCHIVE):archive.ARCHIVE_SHA,str(archive.SOURCE):archive.LOADED})
    archive.strict({p:h for p,h in s['additional'].items() if Path(p).suffix.lower()=='.py'})
    if old.selected.provenance.validate_historical_evidence(item['context'],s['expected'])!=item['gaps']:
        raise ValueError('Historical config observation changed')


def begin(*,manifest_path,manifest_sha256):
    path=str(Path(manifest_path).resolve());manifest=old.read(path,manifest_sha256)
    ref=manifest['legacy_completed_index']
    if not exact(manifest,build_manifest(legacy_index_path=ref['path'],legacy_index_sha256=ref['sha256'])):
        raise ValueError('New archive manifest must equal exact hard-plan reconstruction')
    legacy=old.read(archive.INVENTORY,archive.INVENTORY_SHA);parent=old.read(old.drift.SELECTED_PLAN,old.drift.SELECTED_PLAN_SHA)
    index=old.read(ref['path'],ref['sha256']);entries=queue_entries(index,legacy)
    expected=dict(parent['source_hashes'])
    for mapping in (legacy['historical_expected_source_hashes'],index['finalization']['historical_expected_source_hashes'],index['finalization']['additional_provenance_hashes'],sources(),
                    {path:manifest_sha256,ref['path']:ref['sha256'],str(archive.INVENTORY):archive.INVENTORY_SHA,str(old.drift.SELECTED_PLAN):old.drift.SELECTED_PLAN_SHA}):old.merge(expected,mapping)
    contract=archive.load_contract();archive.verify_expected_sources(expected,contract)
    contexts={};rows={}
    for row in manifest['tasks']:
        identifier=row['new_job_id'];p=row['context_path']
        if identifier in rows or expected.get(p)!=row['context_sha256'] or expected.get(row['checkpoint_path'])!=row['checkpoint_sha256']:
            raise ValueError('Task source coordinate differs')
        if p not in contexts:
            context=old.read(p,row['context_sha256'])
            if context['runtime']!=old.selected.current_runtime():raise ValueError('Actual runtime differs')
            inputs={k:old.selected._restore_input(v) for k,v in context['prepared_inputs'].items()};changed=deepcopy(inputs)
            for ticker,date,before,after in old.selected.CORRECTIONS:
                if changed['returns'].loc[date,ticker]!=before:raise ValueError('Original correction differs')
                changed['returns'].loc[date,ticker]=after
            gaps=old.selected.provenance.validate_historical_evidence(context,expected)
            if not exact(parent['historical_context_gap_observations'][p],dict(context_sha256=row['context_sha256'],gaps=gaps)):raise ValueError('Original config gap differs')
            contexts[p]=dict(context=context,inputs=inputs,changed=changed,gaps=gaps,original_digest=old.selected.provenance._digest(inputs),corrected_digest=old.selected.provenance._digest(changed))
        if not any(exact(row['task'],t) for t in contexts[p]['context']['tasks']) or not exact(row['runtime'],contexts[p]['context']['runtime']):raise ValueError('Task/runtime differs')
        rows[identifier]=row
    if len(rows)!=manifest['planned'] or len(contexts)!=manifest['context_count']:raise ValueError('Full manifest denominator differs')
    snapshot=Snapshot();STATES[snapshot]=dict(manifest=manifest,parent=parent,legacy=legacy,legacy_entries=entries,path=path,sha=manifest_sha256,expected=expected,contract=contract,contexts=contexts,rows=rows,records={},additional={},closed=False,busy=False)
    verify_all(STATES[snapshot]);return snapshot


def track(snapshot,path,sha):
    s=state(snapshot);old.track(s,path,sha)


def wrap(s,row,item,result,mode):
    return dict(schema='SELECTED_ARCHIVE_RESOLUTION_TASK_V1',new_job_id=row['new_job_id'],original=row,result=result,manifest_path=s['path'],manifest_sha256=s['sha'],mode=mode,
        input_digests=dict(original=item['original_digest'],corrected=item['corrected_digest']),saved_result_revalidation_scope=old.RESTORE_SCOPE,
        non20_risk_projection_fields_independently_recomputed=False,binary_float_ledger_hash_independently_verified=False,
        original_live_price_paths_verified=False,historical_full_source_closure_verified=False,source_closure_finalized=False,
        original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)


def evaluate(snapshot,identifier):
    s=state(snapshot)
    if identifier in s['legacy_entries']:raise ValueError('Previously completed task must restore without fit')
    verify_task(s,s['rows'][identifier])
    function=old.evaluate
    bound=FunctionType(function.__code__,dict(function.__globals__,state=state,wrap=wrap,sources=sources),function.__name__,function.__defaults__,function.__closure__)
    try:return bound(snapshot,identifier)
    finally:verify_task(s,s['rows'][identifier])


def restore_legacy(snapshot,identifier):
    s=state(snapshot)
    if identifier not in s['legacy_entries'] or identifier in s['records']:raise ValueError('Unknown/duplicate legacy task')
    entry=s['legacy_entries'][identifier];value=old.read(entry['path'],entry['sha256']);row=s['rows'][identifier];item=s['contexts'][row['context_path']]
    if (value.get('schema')!='ndx_selected_delta_exact_gap_task_v1' or value.get('new_job_id')!=identifier
        or not exact(value['original'],row) or value['manifest_path']!=str(archive.INVENTORY) or value['manifest_sha256']!=archive.INVENTORY_SHA
        or value.get('non20_risk_projection_fields_independently_recomputed') is not False or value.get('saved_result_revalidation_scope')!=old.RESTORE_SCOPE
        or any(value.get(k) is not False for k in FALSE_FLAGS)
        or not exact(value['input_digests'],dict(original=item['original_digest'],corrected=item['corrected_digest']))):raise ValueError('Legacy task identity/scope differs')
    if value['mode']=='EXTERNAL_FIRST_PROBE_IMPORTED_WITHOUT_NEW_FIT':
        known=s['legacy']['completed_probe']
        if dict(path=value['imported_probe_path'],sha256=value['imported_probe_sha256'],new_job_id=identifier)!=known:raise ValueError('Original probe identity differs')
        old.track(s,known['path'],known['sha256'])
    elif value['mode']!='ONE_NEW_INPUT_FULL_V3_EVALUATION_NO_OLD_WINDOW_REUSE' or identifier==s['legacy']['completed_probe']['new_job_id']:raise ValueError('Legacy task mode differs')
    verify_task(s,row)
    try:
        old.validate_saved(s,row,value['result']);old.track(s,entry['path'],entry['sha256'])
        output=wrap(s,row,item,deepcopy(value['result']),'LEGACY_COMPLETED_RESULT_RESTORED_NO_NEW_FIT')
        output['legacy_completed_artifact']=dict(entry)
        output['legacy_original_wrapper']=deepcopy(value)
        s['records'][identifier]=deepcopy(output);return output
    finally:verify_task(s,row)


def restore(snapshot,path,sha):
    s=state(snapshot);value=old.read(path,sha);identifier=value['new_job_id']
    if identifier not in s['rows'] or identifier in s['records']:raise ValueError('Unknown/duplicate saved task')
    row=s['rows'][identifier];item=s['contexts'][row['context_path']]
    template=wrap(s,row,item,value['result'],value['mode'])
    if identifier in s['legacy_entries']:
        template['mode']='LEGACY_COMPLETED_RESULT_RESTORED_NO_NEW_FIT';template['legacy_completed_artifact']=s['legacy_entries'][identifier]
        original=old.read(template['legacy_completed_artifact']['path'],template['legacy_completed_artifact']['sha256'])
        template['legacy_original_wrapper']=original
        if not exact(original['result'],value['result']):raise ValueError('Legacy result altered')
    elif value['mode']!='ONE_NEW_INPUT_FULL_V3_EVALUATION_NO_OLD_WINDOW_REUSE':raise ValueError('New task mode differs')
    if not exact(value,template):raise ValueError('Saved new archive wrapper differs')
    verify_task(s,row)
    try:
        old.validate_saved(s,row,value['result']);old.track(s,path,sha)
        if identifier in s['legacy_entries']:
            entry=s['legacy_entries'][identifier];old.track(s,entry['path'],entry['sha256'])
        s['records'][identifier]=deepcopy(value);return value
    finally:verify_task(s,row)


def finish(snapshot):
    s=state(snapshot)
    if s['busy']:raise ValueError('Task evaluating')
    try:
        checked=verify_all(s)
        return dict(checked,schema='SELECTED_ARCHIVE_RESOLUTION_FINALIZATION_V1',planned=len(s['rows']),completed=len(s['records']),status='COMPLETE' if len(s['rows'])==len(s['records']) else 'PARTIAL',
            historical_expected_source_hashes=s['expected'],additional_provenance_hashes=s['additional'],immutable_numerical_source_closure_verified=True,
            original_live_price_paths_verified=False,historical_full_source_closure_verified=False,original_historical_provenance_verified=False)
    finally:s['closed']=True


def verify_finished(snapshot):
    if snapshot not in STATES or not STATES[snapshot]['closed']:raise ValueError('Finalized snapshot required')
    return verify_all(STATES[snapshot])
