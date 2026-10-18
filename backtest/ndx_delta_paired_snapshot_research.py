"""Private immutable-input snapshots for the original DELTA paired v2 recovery."""
from copy import deepcopy
import hashlib
import json
import math
import platform
from pathlib import Path
from types import SimpleNamespace
from weakref import WeakKeyDictionary
import numpy as np
import pandas as pd
import scipy
from backtest import ndx_delta_paired_trace_recovery_v2_research as sealed
from scripts.ndx_joint_weight_verify import _restore_input

SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
_STATES=WeakKeyDictionary()


class Snapshot:
    __slots__=('__weakref__',)


def _state(snapshot):
    if type(snapshot) is not Snapshot or snapshot not in _STATES:raise ValueError('Unknown snapshot capability')
    state=_STATES[snapshot]
    if state['closed']:raise ValueError('Closed snapshot')
    return state


def _bytes(path,sha):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External artifact SHA differs')
    return raw


def source_hashes():
    return sealed.trace.source_hashes()|sealed.equivalence.previous.LOADED|{
        str(sealed.equivalence.SOURCE):sealed.equivalence.LOADED_SHA,str(sealed.previous.SOURCE):sealed.previous.LOADED,
        str(sealed.SOURCE):sealed.LOADED,str(SOURCE):LOADED}


def validate_runtime(runtime):
    actual=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__)
    if runtime!=actual:raise ValueError('Actual process runtime differs from original context')


def _merge(target,mapping):
    for path,sha in mapping.items():
        if path in target and target[path]!=sha:raise ValueError('Conflicting source SHA')
        target[path]=sha


def _verify_scoped(state,sources):
    if any(state['sources'].get(path)!=sha for path,sha in sources.items()):raise ValueError('Unverified numerical source or SHA')
    sealed.equivalence.previous._verify({path:sha for path,sha in sources.items() if Path(path).suffix.lower()=='.py'})


def _validate_memory(state):
    for item in state['contexts'].values():
        if (sealed._digest(item['inputs'])!=item['original_digest'] or sealed._digest(item['corrected'])!=item['corrected_digest']):
            raise ValueError('Verified typed snapshot changed')


def begin_snapshot(*,manifest_path,manifest_sha256):
    path=str(Path(manifest_path).resolve());manifest=json.loads(_bytes(path,manifest_sha256))
    if manifest['schema']!='ndx_delta_paired_snapshot_manifest_v1':raise ValueError('Explicit snapshot manifest required')
    sources=dict(manifest['source_hashes']);_merge(sources,source_hashes());_merge(sources,{path:manifest_sha256})
    sealed.equivalence.previous._verify(sources)
    parent_path=str(Path(manifest['parent_plan_path']).resolve());parent_sha=manifest['parent_plan_sha256']
    if sources.get(parent_path)!=parent_sha:raise ValueError('Parent plan missing from closure')
    parent=json.loads(_bytes(parent_path,parent_sha))
    if manifest['tasks']!=[row for day in parent['dates'] for row in day['tasks']] or manifest['corrections']!=parent['errors']:
        raise ValueError('Snapshot full original plan task/input denominator differs')
    if any(sources.get(p)!=h for p,h in parent['source_hashes'].items()):raise ValueError('Parent source closure omitted')
    rows={};contexts={}
    for row in manifest['tasks']:
        identifier=row['new_job_id'];context_path=str(Path(row['context_path']).resolve());context_sha=row['context_sha256']
        if identifier in rows or sources.get(context_path)!=context_sha or sources.get(row['checkpoint_path'])!=row['checkpoint_sha256']:
            raise ValueError('Original task/context/checkpoint source differs')
        if context_path not in contexts:
            raw=_bytes(context_path,context_sha);context=json.loads(raw)
            validate_runtime(context['runtime'])
            inputs={key:_restore_input(value) for key,value in context['prepared_inputs'].items()};corrected=deepcopy(inputs)
            for cell in manifest['corrections']:
                if type(cell['new']) not in (int,float) or not math.isfinite(cell['new']) or cell['new']<=-1.:
                    raise ValueError('Finite explicit correction required')
                if corrected['returns'].loc[cell['session'],cell['ticker']]!=cell['old']:raise ValueError('Original correction value differs')
                corrected['returns'].loc[cell['session'],cell['ticker']]=cell['new']
            gaps=sealed.validate_historical_evidence(context,sources)
            if parent['historical_context_gap_observations'][context_path]!=dict(context_sha256=context_sha,gaps=gaps):
                raise ValueError('Parent gap observation differs')
            contexts[context_path]=dict(raw=raw,context=context,inputs=inputs,corrected=corrected,
                original_digest=sealed._digest(inputs),corrected_digest=sealed._digest(corrected),gaps=gaps)
        if row['task'] not in contexts[context_path]['context']['tasks'] or row['runtime']!=contexts[context_path]['context']['runtime']:
            raise ValueError('Original task/runtime differs')
        rows[identifier]=deepcopy(row)
    if not rows or manifest['planned']!=len(rows):raise ValueError('Complete nonempty snapshot denominator required')
    sealed.equivalence.previous._verify(sources)
    snapshot=Snapshot();_STATES[snapshot]=dict(manifest=manifest,manifest_path=path,manifest_sha256=manifest_sha256,
        parent=parent,sources=sources,additional={},contexts=contexts,rows=rows,records={},closed=False,busy=False)
    return snapshot


def evaluate_task(snapshot,identifier):
    state=_state(snapshot)
    if state['busy'] or identifier not in state['rows']:raise ValueError('Unknown or concurrent snapshot task')
    _verify_scoped(state,source_hashes());row=state['rows'][identifier];item=state['contexts'][row['context_path']]
    validate_runtime(row['runtime'])
    if sealed._digest(item['inputs'])!=item['original_digest'] or sealed._digest(item['corrected'])!=item['corrected_digest']:
        raise ValueError('Verified typed snapshot changed')
    if identifier in state['records']:return deepcopy(state['records'][identifier])
    state['busy']=True
    try:
        checkpoint_raw=_bytes(row['checkpoint_path'],row['checkpoint_sha256'])
        def captured_read(path,sha):
            path=str(Path(path).resolve())
            if path==row['context_path'] and sha==row['context_sha256']:return json.loads(item['raw'])
            if path==str(Path(row['checkpoint_path']).resolve()) and sha==row['checkpoint_sha256']:return json.loads(checkpoint_raw)
            raise ValueError('Read outside captured original context/checkpoint')
        verify=lambda mapping:_verify_scoped(state,mapping);bind=sealed.trace.binding._bind
        old=sealed.equivalence.previous
        old_proxy=SimpleNamespace(**dict(vars(old),_verify=verify,
            candidate_numerical_input_fingerprint=bind(old.candidate_numerical_input_fingerprint,_verify=verify)))
        eq=sealed.equivalence
        fingerprint=bind(eq.candidate_numerical_input_fingerprint,previous=old_proxy)
        comparison=bind(eq.compare_candidate_numerical_inputs,previous=old_proxy,candidate_numerical_input_fingerprint=fingerprint)
        eq_proxy=SimpleNamespace(**dict(vars(eq),previous=old_proxy,candidate_numerical_input_fingerprint=fingerprint,
            compare_candidate_numerical_inputs=comparison))
        recover=bind(sealed.recover_paired_delta,equivalence=eq_proxy,_read=captured_read)
        result=recover(arguments=dict(task=row['task'],inputs=item['inputs'],engine='joint_weight_v3',runtime=row['runtime'],source_hashes=state['sources']),
            corrected_inputs=item['corrected'],context_path=row['context_path'],context_sha256=row['context_sha256'],
            checkpoint_path=row['checkpoint_path'],checkpoint_sha256=row['checkpoint_sha256'])
        _verify_scoped(state,result['source_hashes']);result.pop('source_hashes')
        output=_wrap(state,row,item,result,'ORIGINAL_V3_TRACE_RECOVERED')
        state['records'][identifier]=deepcopy(output);return output
    finally:state['busy']=False


def _wrap(state,row,item,result,mode):
    return dict(schema='ndx_delta_paired_snapshot_task_v1',new_job_id=row['new_job_id'],original=row,result=result,
        manifest_path=state['manifest_path'],manifest_sha256=state['manifest_sha256'],mode=mode,
        numerical_input_digests=dict(original=item['original_digest'],corrected=item['corrected_digest']),
        source_closure_reference='EXTERNAL_SHARED_MANIFEST_WITH_IMPORT_TIME_NUMERICAL_SOURCES',
        source_closure_finalized=False,original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)


def _validate_result(state,row,result):
    validate_runtime(row['runtime'])
    item=state['contexts'][row['context_path']];original=json.loads(_bytes(row['checkpoint_path'],row['checkpoint_sha256']))
    if (result['schema']!='ndx_delta_paired_trace_recovery_research_v2' or result['context_path']!=row['context_path'] or
        result['context_sha256']!=row['context_sha256'] or result['checkpoint_sha256']!=row['checkpoint_sha256'] or
        result['checkpoint_path']!=row['checkpoint_path'] or sealed.encoding._normalize(result['original_result'])!=original['result'] or
        result['original_full_result_exact'] is not True or result['original_historical_provenance_verified'] is not False or
        result['promotion_allowed'] is not False or result['point_in_time_verified'] is not False or result['no_fit_reuse'] is not False or
        type(result['old_trace_numerical_evaluation_count']) is not int or result['old_trace_numerical_evaluation_count']!=1 or
        type(result['new_input_fit_count']) is not int or result['new_input_fit_count']!=0 or
        result['trace_recovery_requires_original_v3_execution'] is not True or
        result['reconstruction_scope']!='NUMERICAL_RECONSTRUCTION_WITH_HISTORICAL_LOADER_PROVENANCE_GAP'):
        raise ValueError('Saved numerical trace original binding differs')
    old_rows,old_metrics=sealed._paired_windows(item['inputs'],row['task'],result['historical_window_weights'])
    new_rows,new_metrics=sealed._paired_windows(item['corrected'],row['task'],result['historical_window_weights'])
    def equal(left,right):
        if type(left) in (int,float) and type(right) in (int,float):return math.isfinite(left) and math.isfinite(right) and abs(left-right)<=1e-12
        if type(left)!=type(right):return False
        if isinstance(left,dict):return left.keys()==right.keys() and all(equal(left[key],right[key]) for key in left)
        if isinstance(left,list):return len(left)==len(right) and all(equal(a,b) for a,b in zip(left,right))
        return left==right
    if not equal(old_rows,result['original_windows']) or not equal(new_rows,result['corrected_windows']):raise ValueError('Saved scalar windows differ')
    expected=deepcopy(result['original_result']);expected.update(new_metrics)
    if ({k:v for k,v in expected.items() if k not in sealed.PAIRED}!={k:v for k,v in result['result'].items() if k not in sealed.PAIRED} or
        not equal(expected,result['result']) or any(abs(old_metrics[k]-result['original_result'][k])>1e-12 for k in sealed.PAIRED) or
        result['historical_loader_provenance_gaps']!=sealed.validate_historical_evidence(item['context'],state['sources'])):
        raise ValueError('Saved paired values or historical gap differ')


def _track(state,path,sha):
    path=str(Path(path).resolve())
    if (path in state['sources'] and state['sources'][path]!=sha) or (path in state['additional'] and state['additional'][path]!=sha):
        raise ValueError('Conflicting external provenance SHA')
    _bytes(path,sha);state['additional'][path]=sha


def import_probe(snapshot,*,probe_path,probe_sha256):
    state=_state(snapshot);_validate_memory(state);probe=json.loads(_bytes(probe_path,probe_sha256))
    identifier=probe['selected']['task']['new_job_id']
    if (state['busy'] or identifier not in state['rows'] or identifier in state['records'] or
        probe['schema']!='ndx_delta_three_cell_paired_gap_probe_v2' or probe['selected']!=state['parent']['probe'] or
        probe['plan_path']!=state['manifest']['parent_plan_path'] or probe['plan_sha256']!=state['manifest']['parent_plan_sha256']):
        raise ValueError('External probe original corrected plan binding differs')
    row=state['rows'][identifier];result=deepcopy(probe['result']);_verify_scoped(state,result['source_hashes']);result.pop('source_hashes')
    _validate_result(state,row,result);_track(state,probe_path,probe_sha256)
    output=_wrap(state,row,state['contexts'][row['context_path']],result,'EXTERNAL_COMPLETED_PROBE_IMPORTED_NO_REPEAT_TRACE')
    output.update(imported_probe_path=str(Path(probe_path).resolve()),imported_probe_sha256=probe_sha256)
    state['records'][identifier]=deepcopy(output);return output


def restore_task(snapshot,*,checkpoint_path,checkpoint_sha256):
    state=_state(snapshot);value=json.loads(_bytes(checkpoint_path,checkpoint_sha256));identifier=value['new_job_id']
    if state['busy'] or identifier not in state['rows'] or identifier in state['records']:raise ValueError('Unknown/duplicate restored task')
    row=state['rows'][identifier];item=state['contexts'][row['context_path']]
    if (value['schema']!='ndx_delta_paired_snapshot_task_v1' or value['original']!=row or
        value['manifest_path']!=state['manifest_path'] or value['manifest_sha256']!=state['manifest_sha256'] or
        value['original_historical_provenance_verified'] is not False or value['point_in_time_verified'] is not False or value['promotion_allowed'] is not False or
        value['numerical_input_digests']!=dict(original=item['original_digest'],corrected=item['corrected_digest'])):
        raise ValueError('Restored task source/input binding differs')
    _validate_result(state,row,value['result']);_track(state,checkpoint_path,checkpoint_sha256)
    if value['mode']=='EXTERNAL_COMPLETED_PROBE_IMPORTED_NO_REPEAT_TRACE':_track(state,value['imported_probe_path'],value['imported_probe_sha256'])
    elif value['mode']!='ORIGINAL_V3_TRACE_RECOVERED':raise ValueError('Unknown restored mode')
    state['records'][identifier]=deepcopy(value);return value


def finish_snapshot(snapshot):
    state=_state(snapshot)
    if state['busy']:raise ValueError('Active trace cannot finalize')
    try:
        sealed.equivalence.previous._verify(state['sources']);sealed.equivalence.previous._verify(state['additional']) if state['additional'] else None
        _validate_memory(state)
        for item in state['contexts'].values():
            if sealed.validate_historical_evidence(item['context'],state['sources'])!=item['gaps']:raise ValueError('Historical loader gap observation changed')
        return dict(schema='ndx_delta_paired_snapshot_finalization_v1',manifest_path=state['manifest_path'],manifest_sha256=state['manifest_sha256'],
            planned=len(state['rows']),completed=len(state['records']),status='COMPLETE' if len(state['rows'])==len(state['records']) else 'PARTIAL',
            source_hashes=state['sources'],additional_provenance_hashes=state['additional'],source_closure_verified=True,
            original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)
    finally:state['closed']=True


def verify_finalization(snapshot):
    if type(snapshot) is not Snapshot or snapshot not in _STATES or not _STATES[snapshot]['closed']:
        raise ValueError('Closed registered snapshot required for post-publication verification')
    state=_STATES[snapshot];sealed.equivalence.previous._verify(state['sources'])
    if state['additional']:sealed.equivalence.previous._verify(state['additional'])
    _validate_memory(state)
    for item in state['contexts'].values():
        if sealed.validate_historical_evidence(item['context'],state['sources'])!=item['gaps']:
            raise ValueError('Historical gap observation changed after finalization')
