"""Scoped, fully verified date snapshots around the sealed BASE delta adapter."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
from weakref import WeakKeyDictionary
from backtest import ndx_base_window_delta_research as sealed
from scripts.ndx_joint_weight_verify import _restore_input

SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
_STATES=WeakKeyDictionary()


class DateSnapshot:
    __slots__=('__weakref__',)


def _state(snapshot):
    if type(snapshot) is not DateSnapshot or snapshot not in _STATES:raise ValueError('Unknown verified snapshot capability')
    state=_STATES[snapshot]
    if state['closed']:raise ValueError('Date snapshot already closed')
    return state


def _bytes(path,sha):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External source SHA differs')
    return raw


def _sources():
    result=sealed.base._sources()
    for module,path,sha in (
        (sealed,sealed.SOURCE,sealed.LOADED),
        (sealed.recovery,sealed.recovery.SOURCE,sealed.recovery.LOADED),
        (sealed.recovery.equivalence,sealed.recovery.equivalence.SOURCE,sealed.recovery.equivalence.LOADED_SHA)):
        result[str(path)]=sha
    result.update(sealed.recovery.equivalence.previous.LOADED)
    result[str(SOURCE)]=LOADED
    return result


def begin_snapshot(*,manifest_path,manifest_sha256):
    raw=_bytes(manifest_path,manifest_sha256);manifest=json.loads(raw)
    if manifest['schema']!='ndx_base_window_snapshot_manifest_v1':raise ValueError('Explicit date snapshot manifest required')
    sources=dict(manifest['source_hashes'])
    for path,sha in _sources().items():
        if path in sources and sources[path]!=sha:raise ValueError('Declared numerical source differs')
        sources[path]=sha
    manifest_path=str(Path(manifest_path).resolve())
    if manifest_path in sources and sources[manifest_path]!=manifest_sha256:raise ValueError('Conflicting snapshot manifest SHA')
    sources[manifest_path]=manifest_sha256
    sealed.checkpoints._verify_sources(sources)
    captured={}
    for role in ('context','typed_context'):
        reference=manifest[role];path=str(Path(reference['path']).resolve());sha=reference['sha256']
        if sources.get(path)!=sha:raise ValueError('Snapshot source declaration omitted')
        captured[path]=(sha,_bytes(path,sha))
    context=json.loads(captured[str(Path(manifest['context']['path']).resolve())][1])
    typed=json.loads(captured[str(Path(manifest['typed_context']['path']).resolve())][1])
    for value in (context,typed):
        if any(sources.get(path)!=sha for path,sha in value.get('source_hashes',{}).items()):
            raise ValueError('Original source closure omitted or replaced')
    inputs={key:_restore_input(value) for key,value in typed['prepared_inputs'].items()}
    corrected=deepcopy(inputs);cells=manifest['corrections']
    if not cells or len({(row['ticker'],row['session']) for row in cells})!=len(cells):raise ValueError('Unique declared corrections required')
    for cell in cells:
        if any(type(cell[key]) not in (int,float) or not math.isfinite(cell[key]) for key in ('old','new')) or cell['new']<=-1.:
            raise ValueError('Finite explicit numerical correction required')
        if corrected['returns'].loc[cell['session'],cell['ticker']]!=cell['old']:raise ValueError('Original correction value differs')
        corrected['returns'].loc[cell['session'],cell['ticker']]=cell['new']
    rows={}
    for row in manifest['tasks']:
        identifier=row['new_job_id'];path=str(Path(row['checkpoint_path']).resolve())
        if (identifier in rows or row['task'] not in context['tasks'] or
            sources.get(path)!=row['checkpoint_sha256']):raise ValueError('Original task/checkpoint binding differs')
        rows[identifier]=deepcopy(row)
    if not rows:raise ValueError('Nonempty explicit task denominator required')
    first=next(iter(rows.values()))
    for data in (inputs,corrected):
        sealed.recovery.equivalence.candidate_numerical_input_fingerprint(task=first['task'],inputs=data,
            engine='non_equal_fractional_v1',runtime=context['runtime'],source_hashes=sources)
    snapshot=DateSnapshot()
    _STATES[snapshot]=dict(manifest=manifest,manifest_path=manifest_path,manifest_sha256=manifest_sha256,
        sources=sources,captured=captured,context=context,inputs=inputs,corrected=corrected,rows=rows,
        input_digest=sealed._input_digest(inputs),corrected_digest=sealed._input_digest(corrected),
        records={},closed=False,busy=False)
    sealed.checkpoints._verify_sources(sources)
    return snapshot


def _verify_scoped(state,mapping):
    for path,sha in mapping.items():
        if state['sources'].get(path)!=sha:raise ValueError('Unknown/unverified path or SHA in scoped verification')
    # Only already verified historical bytes used through the captured typed
    # snapshot skip repeat disk reads. Code files are rehashed every task/call.
    sealed.checkpoints._verify_sources({path:sha for path,sha in mapping.items() if Path(path).suffix.lower()=='.py'})


def evaluate_task(snapshot,new_job_id):
    state=_state(snapshot)
    if state['busy']:raise ValueError('Concurrent access to one date snapshot is not allowed')
    if new_job_id not in state['rows']:raise ValueError('Unknown planned task')
    _verify_scoped(state,_sources())
    if sealed._input_digest(state['inputs'])!=state['input_digest'] or sealed._input_digest(state['corrected'])!=state['corrected_digest']:
        raise ValueError('Verified typed snapshot values mutated')
    if new_job_id in state['records']:return deepcopy(state['records'][new_job_id])
    state['busy']=True
    try:
        row=state['rows'][new_job_id];checkpoint_path=str(Path(row['checkpoint_path']).resolve())
        raw=_bytes(checkpoint_path,row['checkpoint_sha256']);checkpoint=json.loads(raw)
        if sealed.checkpoints._bytes(checkpoint)!=raw:raise ValueError('Original checkpoint encoding differs')
        captured=dict(state['captured']);captured[checkpoint_path]=(row['checkpoint_sha256'],raw)
        def captured_read(path,sha):
            path=str(Path(path).resolve())
            if path not in captured or captured[path][0]!=sha:raise ValueError('Read outside captured task/context bytes')
            return json.loads(captured[path][1])
        def checkpoint_read(path):
            path=str(Path(path).resolve())
            if path!=checkpoint_path:raise ValueError('Unexpected original checkpoint read')
            return json.loads(raw)
        verify=lambda mapping:_verify_scoped(state,mapping)
        bind=sealed.base.binding._bind
        previous=sealed.recovery.equivalence.previous
        previous_proxy=SimpleNamespace(**dict(vars(previous),_verify=verify,
            candidate_numerical_input_fingerprint=bind(previous.candidate_numerical_input_fingerprint,_verify=verify)))
        equivalence=sealed.recovery.equivalence
        equivalence_proxy=SimpleNamespace(**dict(vars(equivalence),previous=previous_proxy,
            candidate_numerical_input_fingerprint=bind(equivalence.candidate_numerical_input_fingerprint,previous=previous_proxy)))
        recovery=sealed.recovery
        recover=bind(recovery.recover,equivalence=equivalence_proxy)
        recovery_proxy=SimpleNamespace(**dict(vars(recovery),equivalence=equivalence_proxy,recover=recover,
            verify_original=bind(recovery.verify_original,recover=recover)))
        checkpoints=sealed.checkpoints
        checkpoint_proxy=SimpleNamespace(**dict(vars(checkpoints),_verify_sources=verify,
            _read_checkpoint=bind(checkpoints._read_checkpoint,_read=checkpoint_read)))
        evaluate=bind(sealed.evaluate_window_delta,checkpoints=checkpoint_proxy,recovery=recovery_proxy,_read=captured_read)
        manifest=state['manifest']
        result=evaluate(arguments=dict(task=row['task'],inputs=state['inputs'],engine='non_equal_fractional_v1',
            runtime=state['context']['runtime'],source_hashes=state['sources']),corrected_inputs=state['corrected'],
            checkpoint_path=checkpoint_path,checkpoint_sha256=row['checkpoint_sha256'],
            context_path=manifest['context']['path'],context_sha256=manifest['context']['sha256'],
            typed_context_path=manifest['typed_context']['path'],typed_context_sha256=manifest['typed_context']['sha256'])
        _verify_scoped(state,result['source_hashes'])
        output=dict(schema='ndx_base_window_snapshot_task_v1',new_job_id=new_job_id,result=result,
            manifest_path=state['manifest_path'],manifest_sha256=state['manifest_sha256'],
            numerical_input_digests=dict(original=state['input_digest'],corrected=state['corrected_digest']),
            date_source_closure_finalized=False,mode='NEW_NUMERICAL_EVALUATION',promotion_allowed=False)
        state['records'][new_job_id]=deepcopy(output)
        return output
    finally:state['busy']=False


def finish_snapshot(snapshot):
    state=_state(snapshot)
    if state['busy']:raise ValueError('Cannot finalize an active evaluation')
    try:
        sealed.checkpoints._verify_sources(state['sources'])
        if sealed._input_digest(state['inputs'])!=state['input_digest'] or sealed._input_digest(state['corrected'])!=state['corrected_digest']:
            raise ValueError('Snapshot input drift before finalization')
        return dict(schema='ndx_base_window_snapshot_finalization_v1',manifest_path=state['manifest_path'],
            manifest_sha256=state['manifest_sha256'],source_hashes=state['sources'],
            planned=len(state['rows']),completed=len(state['records']),
            source_closure_verified=True,status='COMPLETE' if len(state['records'])==len(state['rows']) else 'PARTIAL',
            promotion_allowed=False)
    finally:state['closed']=True


def import_probe(snapshot,*,probe_path,probe_sha256):
    state=_state(snapshot)
    if state['busy']:raise ValueError('Snapshot currently active')
    path=str(Path(probe_path).resolve())
    if path in state['sources'] and state['sources'][path]!=probe_sha256:raise ValueError('Conflicting imported source SHA')
    raw=_bytes(probe_path,probe_sha256);probe=json.loads(raw)
    identifier=probe['selected']['new_job_id']
    if identifier not in state['rows'] or identifier in state['records']:raise ValueError('Probe task absent or already handled')
    row=state['rows'][identifier];result=probe['result']
    if (probe['schema']!='ndx_base_window_delta_probe_v1' or probe['selected']['parent_task']!=row['task'] or
        result['cache_checkpoint_sha256']!=row['checkpoint_sha256']):raise ValueError('Probe original lineage differs')
    expected_digests=dict(original=state['input_digest'],corrected=state['corrected_digest'])
    if (sealed._input_digest(state['inputs'])!=expected_digests['original'] or
        sealed._input_digest(state['corrected'])!=expected_digests['corrected']):
        raise ValueError('Verified typed snapshot values mutated')
    if 'numerical_input_digests' in probe:
        if probe['numerical_input_digests']!=expected_digests:raise ValueError('Probe numerical inputs differ')
    else:
        # The sealed legacy probes predate explicit digests. Their bound runner
        # applies exactly ERRORS to the plan's externally bound typed context.
        from scripts import ndx_base_three_cell_window_delta_research as legacy
        manifest=state['manifest'];plan_path=str(Path(manifest['parent_plan_path']).resolve())
        plan_sha=manifest['parent_plan_sha256']
        if state['sources'].get(plan_path)!=plan_sha:raise ValueError('Probe plan source missing')
        plan=json.loads(_bytes(plan_path,plan_sha))
        if (plan['schema']!='ndx_base_three_cell_window_delta_plan_v2' or
            plan['source_hashes'].get(str(legacy.SELF))!=legacy.LOADED or
            result['source_hashes'].get(str(legacy.SELF))!=legacy.LOADED or
            plan['errors']!=legacy.ERRORS or manifest['corrections']!=legacy.ERRORS or
            probe['selected'] not in plan['probes'].values()):raise ValueError('Legacy probe correction contract differs')
        day,=[entry for entry in plan['dates'] if entry['date']==probe['selected']['date']]
        if (row not in day['tasks'] or
            manifest['context']!=dict(path=day['context_path'],sha256=day['context_sha256']) or
            manifest['typed_context']!=dict(path=day['typed_context_path'],sha256=day['typed_context_sha256'])):
            raise ValueError('Legacy probe input context differs')
        legacy_inputs={key:_restore_input(value) for key,value in json.loads(
            state['captured'][str(Path(day['typed_context_path']).resolve())][1])['prepared_inputs'].items()}
        legacy_corrected=deepcopy(legacy_inputs)
        for cell in legacy.ERRORS:
            if legacy_corrected['returns'].loc[cell['session'],cell['ticker']]!=cell['old']:
                raise ValueError('Legacy probe original cell differs')
            legacy_corrected['returns'].loc[cell['session'],cell['ticker']]=cell['new']
        if dict(original=sealed._input_digest(legacy_inputs),corrected=sealed._input_digest(legacy_corrected))!=expected_digests:
            raise ValueError('Legacy probe numerical inputs differ')
    _verify_scoped(state,result['source_hashes'])
    sealed.checkpoints._validate_result(result['evaluation'],row['task'],sealed.base._sources())
    if result['original_metric_reconstruction_max_error']>1e-12:raise ValueError('Original metric reconstruction failed')
    path=str(Path(probe_path).resolve());state['sources'][path]=probe_sha256
    output=dict(schema='ndx_base_window_snapshot_task_v1',new_job_id=identifier,result=deepcopy(result),
        manifest_path=state['manifest_path'],manifest_sha256=state['manifest_sha256'],
        numerical_input_digests=expected_digests,
        imported_probe_path=path,imported_probe_sha256=probe_sha256,
        date_source_closure_finalized=False,mode='EXTERNALLY_BOUND_COMPLETED_PROBE_IMPORTED_NO_FIT',promotion_allowed=False)
    state['records'][identifier]=deepcopy(output)
    return output


def prepare_restore_sources(snapshot,entries):
    """Preload all externally indexed provenance before any ordered restore."""
    state=_state(snapshot);additional={}
    for entry in entries:
        path=str(Path(entry['path']).resolve());sha=entry['sha256']
        value=json.loads(_bytes(path,sha))
        if (value['schema']!='ndx_base_window_snapshot_task_v1' or
            value['manifest_path']!=state['manifest_path'] or value['manifest_sha256']!=state['manifest_sha256'] or
            value['new_job_id'] not in state['rows']):raise ValueError('Restore source belongs to different snapshot')
        pairs=[(path,sha)]
        if value['mode']=='EXTERNALLY_BOUND_COMPLETED_PROBE_IMPORTED_NO_FIT':
            pairs.append((str(Path(value['imported_probe_path']).resolve()),value['imported_probe_sha256']))
        for source,digest in pairs:
            if (source in state['sources'] and state['sources'][source]!=digest) or (source in additional and additional[source]!=digest):
                raise ValueError('Conflicting externally indexed source SHA')
            _bytes(source,digest);additional[source]=digest
    state['sources'].update(additional)


def restore_task(snapshot,*,checkpoint_path,checkpoint_sha256):
    """Restore only from a caller's externally SHA-bound completion index."""
    state=_state(snapshot);path=str(Path(checkpoint_path).resolve())
    if path in state['sources'] and state['sources'][path]!=checkpoint_sha256:raise ValueError('Conflicting restored source SHA')
    value=json.loads(_bytes(path,checkpoint_sha256));identifier=value['new_job_id']
    if state['busy'] or identifier not in state['rows'] or identifier in state['records']:
        raise ValueError('Unknown/duplicate restored task')
    if (value['schema']!='ndx_base_window_snapshot_task_v1' or
        value['manifest_path']!=state['manifest_path'] or value['manifest_sha256']!=state['manifest_sha256'] or
        value['numerical_input_digests']!=dict(original=state['input_digest'],corrected=state['corrected_digest']) or
        value['result']['cache_checkpoint_sha256']!=state['rows'][identifier]['checkpoint_sha256'] or
        value['promotion_allowed'] is not False):raise ValueError('Restored task input/source binding differs')
    _verify_scoped(state,value['result']['source_hashes'])
    sealed.checkpoints._validate_result(value['result']['evaluation'],state['rows'][identifier]['task'],sealed.base._sources())
    if value['mode']=='EXTERNALLY_BOUND_COMPLETED_PROBE_IMPORTED_NO_FIT':
        probe_path=str(Path(value['imported_probe_path']).resolve())
        if probe_path in state['sources'] and state['sources'][probe_path]!=value['imported_probe_sha256']:
            raise ValueError('Conflicting restored probe SHA')
        _bytes(value['imported_probe_path'],value['imported_probe_sha256'])
        state['sources'][probe_path]=value['imported_probe_sha256']
    elif value['mode']!='NEW_NUMERICAL_EVALUATION':raise ValueError('Unknown restored numerical mode')
    state['sources'][path]=checkpoint_sha256;state['records'][identifier]=deepcopy(value)
    return value
