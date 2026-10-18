"""Bounded first-decision cutoff fits from one immutable corrected queue snapshot."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from weakref import WeakKeyDictionary
from scripts import ndx_corrected_frontier_cutoff_refit_archive_research as adapter
from scripts import ndx_corrected_frontier_single_refit_archive_research as single

SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
STATES=WeakKeyDictionary()
FLAGS=('checkpoint_weights_used','selection_performed','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed')


class Snapshot:
    __slots__=('__weakref__',)


def read(path,sha):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External cutoff artifact SHA differs')
    return json.loads(raw)


def state(snapshot):
    if type(snapshot) is not Snapshot or snapshot not in STATES or STATES[snapshot]['closed']:raise ValueError('Unknown or finished cutoff snapshot')
    return STATES[snapshot]


def verify_small(s):
    if adapter.digest(s['reference'])!=s['reference_digest']:raise ValueError('Captured queue reference changed')
    expected_sources=dict(s['queue']['historical_expected_source_hashes'])
    adapter.archive.merge(expected_sources,{str(SOURCE):LOADED,str(single.SOURCE):single.LOADED,s['reference']['path']:s['reference']['sha256']})
    if s['sources']!=expected_sources:raise ValueError('Captured full source denominator changed')
    small={p:h for p,h in expected_sources.items() if Path(p).suffix.lower()=='.py'}
    small.update({s['reference']['path']:s['reference']['sha256'],str(adapter.archive.ARCHIVE):adapter.archive.ARCHIVE_SHA})
    if s['small_sources']!=small:raise ValueError('Per-task source guard denominator changed')
    if adapter.digest(s['seed'])!=s['seed_reference_digest']:raise ValueError('Captured seed presence/reference changed')
    if adapter.digest(s['additional'])!=s['additional_digest']:raise ValueError('Captured additional source closure changed')
    if adapter.digest(s['records'])!=s['records_digest']:raise ValueError('Captured completed records changed')
    adapter.archive.strict(s['small_sources'])
    if adapter.typed.current_runtime()!=s['queue']['original_runtime']:raise ValueError('Actual cutoff runtime changed')
    if adapter.typed.provenance._digest(s['changed'])!=s['queue']['input_binding']['corrected_decoded_inputs_sha256']:
        raise ValueError('Captured corrected six-input memory changed')
    if adapter.digest(s['queue'])!=s['queue_digest']:raise ValueError('Captured original queue memory changed')
    expected_rows={entry['task']['job_id']:entry for entry in s['queue']['candidates']}
    if not adapter.audit.original.exact(s['rows'],expected_rows):raise ValueError('Captured candidate identity map changed')
    if s['seed']:
        if (adapter.digest(s['seed'])!=s['seed_reference_digest'] or adapter.digest(s['seed_value'])!=s['seed_wrapper_digest']
            or not adapter.audit.original.exact(read(s['seed']['path'],s['seed']['sha256']),s['seed_value'])):
            raise ValueError('Captured external seed reference or wrapper changed')
    adapter.audit.original.verify_gaps(s['queue']['historical_loader_gap_observations'])


def verify_all(s):
    verify_small(s)
    sources=dict(s['sources']);adapter.archive.merge(sources,s['additional'])
    checked=adapter.archive.verify_expected_sources(sources,adapter.archive.load_contract())
    adapter.audit.original.verify_gaps(s['queue']['historical_loader_gap_observations'])
    return checked


def begin(*,queue_path,queue_sha256,seed_path=None,seed_sha256=None):
    if bool(seed_path)!=bool(seed_sha256):raise ValueError('Explicit external seed pair required')
    reference=dict(path=str(Path(queue_path).resolve()),sha256=queue_sha256)
    queue=read(reference['path'],reference['sha256']);f=queue['frontier'];c=queue['context']
    prepared=adapter.prepare_queue(frontier_path=f['path'],frontier_sha256=f['sha256'],context_path=c['path'],context_sha256=c['sha256'],historical_cutoff=queue['historical_cutoff'])
    if not adapter.audit.original.exact(queue,prepared):raise ValueError('Complete queue differs from hard reconstruction')
    context=read(c['path'],c['sha256']);frontier=read(f['path'],f['sha256'])
    _,changed,_,binding=adapter.correct_context(context,frontier,queue['historical_cutoff'])
    if binding!=queue['input_binding']:raise ValueError('Full corrected matrix binding differs')
    sources=dict(queue['historical_expected_source_hashes'])
    adapter.archive.merge(sources,{str(SOURCE):LOADED,str(single.SOURCE):single.LOADED,reference['path']:reference['sha256']})
    rows={e['task']['job_id']:e for e in queue['candidates']}
    if len(rows)!=queue['candidate_count']:raise ValueError('Unique complete candidate queue required')
    snapshot=Snapshot();s=dict(queue=queue,queue_digest=adapter.digest(queue),reference=reference,rows=rows,changed=changed,sources=sources,
        small_sources={p:h for p,h in sources.items() if Path(p).suffix.lower()=='.py'},additional={},additional_digest=adapter.digest({}),records={},records_digest=adapter.digest({}),closed=False,seed=None,
        seed_reference_digest=adapter.digest(None),reference_digest=adapter.digest(reference))
    s['small_sources'][reference['path']]=reference['sha256']
    s['small_sources'][str(adapter.archive.ARCHIVE)]=adapter.archive.ARCHIVE_SHA
    STATES[snapshot]=s
    verify_all(s)
    if seed_path:
        seed_ref=dict(path=str(Path(seed_path).resolve()),sha256=seed_sha256);seed=read(**dict(path=seed_ref['path'],sha=seed_ref['sha256']))
        validate_seed(s,seed,seed_ref);s['seed']=seed_ref
        adapter.archive.merge(s['additional'],{seed_ref['path']:seed_ref['sha256']})
        s['additional_digest']=adapter.digest(s['additional'])
        s['seed_value']=seed
        s['seed_reference_digest']=adapter.digest(seed_ref);s['seed_wrapper_digest']=adapter.digest(seed)
    verify_all(s);return snapshot


def matrix_check(s,entry,fitted):
    adapter.audit.original.require_false(fitted,('point_in_time_verified','source_authenticity_verified','promotion_allowed','historical_task_evaluation_performed','order_generation_allowed'))
    if (fitted['weight_spec']!=entry['task']['weight_spec'] or fitted['anchor_policy']!='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED'
        or any(type(v) not in (int,float) or v!=0 for v in fitted['anchor_by_security'].values())):raise ValueError('First-decision anchor metadata differs')
    checks=adapter.check_fitted(fitted,entry['selected'],s['queue']['fit_parameters'],s['queue']['historical_cutoff'])
    names=[entry['selected'][sid]['ticker'] for sid in sorted(entry['selected'])]
    frame=s['changed']['returns'].iloc[-s['queue']['fit_parameters']['fit_days']:][names]
    payload=dict(dates=[d.date().isoformat() for d in frame.index],tickers=names,returns=frame.to_numpy().tolist())
    if fitted['fit_start']!=payload['dates'][0] or fitted['fit_data_sha256']!=adapter.digest(payload) or fitted['source_hashes']!=adapter.fitter._sources():
        raise ValueError('Exact captured cutoff matrix or numerical source differs')
    return checks


def validate_result(s,result):
    job=result['job_id']
    if job not in s['rows'] or result.get('schema')!='CORRECTED_CUTOFF_SNAPSHOT_NUMERICAL_RESULT_V1':raise ValueError('Unknown cutoff result')
    if (result['queue_sha256']!=s['queue_digest'] or not adapter.audit.original.exact(result['candidate'],s['rows'][job])
        or result['historical_cutoff']!=s['queue']['historical_cutoff'] or result['diagnostic_policy']!=adapter.POLICY
        or type(result['new_cutoff_fit_attempt_count']) is not int or result['new_cutoff_fit_attempt_count']!=1
        or type(result['effective_anchor_strength']) not in (int,float) or result['effective_anchor_strength']!=0 or result['input_binding']!=s['queue']['input_binding']):raise ValueError('Saved cutoff result identity differs')
    adapter.audit.original.require_false(result,FLAGS+('whole_lot_execution_performed','forward_oos_evaluation_performed','numerical_failure_is_economic_infeasibility'))
    if result['status']=='FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY':
        if result['refit'] is not None or type(result.get('error')) is not str or result.get('error_type') not in ('ValueError','RuntimeError','ArithmeticError','FloatingPointError','OverflowError','ZeroDivisionError'):
            raise ValueError('Explicit numerical failure record required')
    else:
        checks=matrix_check(s,s['rows'][job],result['refit'])
        if result['independently_recomputed_five_checks']!=checks or result['status']!=('FITTED_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_FIVE_RISKS_FAILED'):
            raise ValueError('Saved original risk classification differs')


def validate_seed(s,seed,reference):
    if (seed.get('schema')!='CORRECTED_FRONTIER_SINGLE_REFIT_EXECUTION_V1' or seed['queue']!=s['reference']
        or seed['job_id'] not in s['rows'] or seed.get('fit_performed') is not True):raise ValueError('Exact single-fit seed required')
    adapter.audit.original.require_false(seed,('selection_performed','point_in_time_verified','promotion_allowed'))
    expected={str(single.SOURCE):single.LOADED,s['reference']['path']:s['reference']['sha256']}
    if seed['runner_source_hashes']!=expected:raise ValueError('Original single-runner source differs')
    started=seed['started_attempt'];attempt=read(started['path'],started['sha256'])
    if attempt!=dict(schema='CORRECTED_FRONTIER_SINGLE_REFIT_ATTEMPT_V1',queue=s['reference'],job_id=seed['job_id'],output=reference['path'],runner_source_hashes=expected,status='STARTED_NOT_COMPLETED'):
        raise ValueError('Exact external seed attempt differs')
    if Path(started['path'])!=Path(reference['path']+'.started.json'):raise ValueError('Seed attempt coordinate differs')
    old=seed['result']
    if old.get('schema')!='CORRECTED_FRONTIER_HISTORICAL_CUTOFF_TASK_V1':raise ValueError('Original single-fit numerical schema required')
    adapter.verify(old)
    if old['job_id']!=seed['job_id']:raise ValueError('Seed nested job differs')
    result={k:deepcopy(v) for k,v in old.items() if k not in ('historical_expected_source_hashes','archive_resolution','historical_loader_gap_observations')}
    result.update(schema='CORRECTED_CUTOFF_SNAPSHOT_NUMERICAL_RESULT_V1',input_binding=s['queue']['input_binding'])
    validate_result(s,result)
    adapter.archive.merge(s['additional'],{started['path']:started['sha256']})
    adapter.archive.merge(s['additional'],old['historical_expected_source_hashes'])
    s['additional_digest']=adapter.digest(s['additional'])
    return result


def envelope(s,result,mode):
    return dict(schema='CORRECTED_CUTOFF_SNAPSHOT_TASK_V1',queue=s['reference'],job_id=result['job_id'],mode=mode,result=result,
        risk_projection_metadata_independently_recomputed=False,historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False)


def import_seed(snapshot):
    s=state(snapshot)
    if not s['seed']:raise ValueError('No externally bound seed supplied')
    seed=read(s['seed']['path'],s['seed']['sha256']);job=seed['job_id']
    if job in s['records']:raise ValueError('Seed already completed')
    verify_small(s);result=validate_seed(s,seed,s['seed'])
    value=envelope(s,result,'EXTERNAL_SINGLE_FIT_IMPORTED_WITHOUT_REFIT')
    value.update(seed=s['seed'],original_single_fit_wrapper=seed)
    s['records'][job]=deepcopy(value);s['records_digest']=adapter.digest(s['records']);verify_small(s);return value


def evaluate(snapshot,job):
    s=state(snapshot)
    verify_small(s)
    if job not in s['rows'] or job in s['records'] or s['seed'] and job==s['seed_value']['job_id']:raise ValueError('Unknown/already completed/seed job cannot fit')
    entry=s['rows'][job]
    result=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_NUMERICAL_RESULT_V1',queue_sha256=s['queue_digest'],job_id=job,candidate=deepcopy(entry),
        historical_cutoff=s['queue']['historical_cutoff'],diagnostic_policy=adapter.POLICY,effective_anchor_strength=0.,
        input_binding=deepcopy(s['queue']['input_binding']),new_cutoff_fit_attempt_count=1,
        whole_lot_execution_performed=False,forward_oos_evaluation_performed=False,numerical_failure_is_economic_infeasibility=False,**dict.fromkeys(FLAGS,False))
    try:
        fitted=adapter.fitter.refit_dynamic_cutoff_weights(returns=s['changed']['returns'],cutoff=s['queue']['historical_cutoff'],selected=entry['selected'],
            weight_spec=entry['task']['weight_spec'],previous_target_weights=None,**s['queue']['fit_parameters'])
    except (ValueError,ArithmeticError,RuntimeError) as error:
        result.update(status='FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY',refit=None,error_type=type(error).__name__,error=str(error))
    else:
        checks=matrix_check(s,entry,fitted)
        result.update(status='FITTED_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_FIVE_RISKS_FAILED',refit=fitted,independently_recomputed_five_checks=checks)
    finally:verify_small(s)
    validate_result(s,result);value=envelope(s,result,'ONE_NEW_HISTORICAL_CUTOFF_FIT');s['records'][job]=deepcopy(value);s['records_digest']=adapter.digest(s['records']);return value


def restore(snapshot,path,sha):
    s=state(snapshot);value=read(path,sha);job=value['job_id']
    if job in s['records']:raise ValueError('Duplicate restore')
    verify_small(s);validate_result(s,value['result'])
    if job!=value['result']['job_id']:raise ValueError('Restored nested job differs')
    if s['seed'] and job==s['seed_value']['job_id']:
        seed=read(s['seed']['path'],s['seed']['sha256']);result=validate_seed(s,seed,s['seed'])
        expected=envelope(s,result,'EXTERNAL_SINGLE_FIT_IMPORTED_WITHOUT_REFIT');expected.update(seed=s['seed'],original_single_fit_wrapper=seed)
    else:expected=envelope(s,value['result'],'ONE_NEW_HISTORICAL_CUTOFF_FIT')
    if not adapter.audit.original.exact(expected,value):raise ValueError('Complete restored cutoff wrapper differs')
    adapter.archive.merge(s['additional'],{str(Path(path).resolve()):sha});s['additional_digest']=adapter.digest(s['additional']);s['records'][job]=deepcopy(value);s['records_digest']=adapter.digest(s['records']);verify_small(s)


def track(snapshot,path,sha):
    s=state(snapshot)
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Tracked source changed')
    adapter.archive.merge(s['additional'],{str(Path(path).resolve()):sha})
    s['additional_digest']=adapter.digest(s['additional'])


def finish(snapshot):
    s=state(snapshot)
    try:
        partition=verify_all(s)
        return dict(schema='CORRECTED_CUTOFF_SNAPSHOT_FINALIZATION_V1',planned=len(s['rows']),completed=len(s['records']),
            status='COMPLETE' if len(s['records'])==len(s['rows']) else 'PARTIAL',archive_resolution=partition,
            historical_expected_source_hashes=dict(s['sources'],**s['additional']),historical_loader_gap_observations=s['queue']['historical_loader_gap_observations'],
            **dict.fromkeys(FLAGS,False))
    finally:s['closed']=True


def verify_finished(snapshot):
    if snapshot not in STATES or not STATES[snapshot]['closed']:raise ValueError('Finalized snapshot required')
    return verify_all(STATES[snapshot])
