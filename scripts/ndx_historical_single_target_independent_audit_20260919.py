"""Independent persisted historical-target readback; no producer or solver calls."""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_latest_all_k_completed_independent_audit_20260919 as scalar
from scripts import ndx_latest_fourteen_panel_independent_readback_20260919 as typed
from scripts.ndx_latest_conditional_channels_20260919 import exclusive_publish
archive=scalar.archive
BASE=ROOT/'data/cache/research'
OWNER=ROOT/'scripts/ndx_twenty_historical_single_target_20260919.py'
OWNER_SHA='7e2af70326d428a0f79964c19f7c57ced1696d165dadbd0a8b42167c357a5f9c'
INPUT=dict(path=str(BASE/'latest_twenty_historical_inputs_20260919_v1/inputs.json'),sha256='49551a1f9cc0069935646d696b27621b748681b5769bfecbe1c8e8fa87d80939')
AUDIT=dict(path=str(BASE/'latest_twenty_historical_inputs_20260919_v1/independent_raw_decimal_audit.json'),sha256='eafcb471cd4a9b5480f24539d40a33381e7152a4dbb78b2540392e36a8d17c23')
PLAN=dict(path=str(BASE/'latest_fourteen_incremental_refit_20260919_v1/plan.json'),sha256='b604b6f5ca1385c83d4fea3fb930b0ddc6e3a1bb30eeab665261f4b53ed5b563')
INPUT_READER=ROOT/'scripts/ndx_twenty_historical_inputs_independent_audit_20260919.py'
INPUT_READER_SHA='dce5010d6b844711a0aa3a7eed1a36b12b2df976460255275dc0409d25641fc9'
STRUCTURE='00065cbc0bccd9ba06b1fbafab0f80070bd79ba26d9607103edd4c1d814361e1'
JOB='712e595ba0b9e7a5ec610278478faba20435af654dc1455bb917fa28fe1a21ab'
TARGET_PATH=BASE/'latest_twenty_historical_single_target_20260919_v1/target.json'
TARGET_SHA='4d174d9263153f7df77b7c4357ed18eb13a2a8eb9194781a642d923762af90b6'
FALSE=('execution_performed','orders_created','winner_selected','latest_weights_imported','point_in_time_verified','legal_training_input_admitted','promotion_allowed','dual_benchmark_evaluation_performed','oos_evaluation_performed','global_optimum_proven')
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(scalar.__file__).resolve(),Path(typed.__file__).resolve(),archive.SOURCE,archive.drift.SOURCE,Path(exclusive_publish.__code__.co_filename).resolve())}


def exact(a,b):return scalar.exact(a,b)
def read(ref,sources):return scalar.read(ref,sources)


def reconstruct(inputs,plan):
    row=min((r for r in plan['delta']['tasks'] if r['input_equivalent_to_old_task'] is False),key=lambda r:r['task_id'])
    original=row['task']
    if row['task_id']!=STRUCTURE or scalar.digest(original)!=STRUCTURE or original['cutoff']!='2026-09-17' or original['weight_spec']!='constrained_fixed_shrinkage' or not exact(original['parameters'],scalar.PARAMS) or original['previous_target_weights'] is not None:raise ValueError('Hard mechanical source structure differs')
    selected=original['selected'];by_sid={r['security_id']:r for r in inputs['candidate_coordinate_and_risk_rows']}
    if len(selected)!=8 or len({r['issuer_id'] for r in selected.values()})!=8:raise ValueError('Eight unique historical structure issuers required')
    for sid,row in selected.items():
        if not exact(row,{k:by_sid[sid][k] for k in ('ticker','issuer_id','risk_chain')}):raise ValueError('Bound conditional identities/risk labels differ')
    calendar=inputs['prices']['calendar'];encoded=inputs['prices']['returns']
    frame=typed.decode(encoded)
    if len(calendar)!=253 or len(frame)!=252 or [d.date().isoformat() for d in frame.index]!=calendar[1:] or calendar[126]!='2026-03-18' or calendar[127]!='2026-03-19' or calendar[-1]!='2026-09-17':raise ValueError('Hard 253/252 date boundary differs')
    # Slice the persisted rows explicitly, retaining all twenty original columns.
    fit=copy.deepcopy(encoded);fit['index']=fit['index'][:126];fit['data']=fit['data'][:126]
    if len(typed.decode(fit))!=126 or fit['index'][-1][:10]!='2026-03-18':raise ValueError('Only historical first126 may be audited')
    task=copy.deepcopy(original);task['cutoff']='2026-03-18';task['task_id']=scalar.digest(task)
    if task['task_id']!=JOB:raise ValueError('Independent historical job digest differs')
    structure=dict(plan_reference=PLAN,original_task_id=STRUCTURE,role='FIRST_NEW_TASK_MECHANICAL_WIRING_FIXTURE_NOT_WINNER')
    return task,fit,calendar[126:],structure


def inspect(value,raw,started,inputs,plan,numerical,expected_sources):
    """Pure comparison; external hard bytes are checked by build, not this helper."""
    task,fit,calendar,structure=reconstruct(inputs,plan)
    marker=value['started_reference'];rawref=value['raw_fit_reference']
    expected_marker=dict(schema='HISTORICAL_SINGLE_TARGET_ATTEMPT_V1',job_id=JOB,input_reference=INPUT,attempt_count=1)
    if not exact(started,expected_marker):raise ValueError('Exclusive historical attempt differs')
    result=raw['original_result']
    if not exact(result['source_hashes'],numerical):raise ValueError('Frozen numerical source closure differs')
    diagnostics=scalar.inspect_result(result,task,dict(returns=fit))
    raw_sources=dict(expected_sources);archive.merge(raw_sources,{marker['path']:marker['sha256']})
    expected_raw=dict(schema='HISTORICAL_SINGLE_TARGET_RAW_FIT_RECEIPT_V1',job_id=JOB,original_result=result,explicit_fit_matrix=fit,task=task,input_reference=INPUT,
        independent_input_audit_reference=AUDIT,structure_reference=structure,started_reference=marker,historical_expected_source_hashes=raw_sources,**dict.fromkeys(FALSE,False))
    if not exact(raw,expected_raw):raise ValueError('Complete raw receipt/matrix/task/source differs')
    target_sources=dict(raw_sources);archive.merge(target_sources,{rawref['path']:rawref['sha256']})
    expected=dict(schema='HISTORICAL_SINGLE_CONDITIONAL_TARGET_V1',job_id=JOB,task=task,result=result,independent_matrix_and_risk_audit=diagnostics,
        status='FITTED_FIVE_RISKS_PASSED' if diagnostics['risk_pass'] else 'FITTED_FIVE_RISKS_FAILED',raw_fit_reference=rawref,started_reference=marker,
        input_reference=INPUT,independent_input_audit_reference=AUDIT,structure_reference=structure,execution_observation_calendar=calendar,
        baseline_close_date='2026-03-18',first_next_open_observation='2026-03-19',schedule=[dict(decision_date='2026-03-18',execution_date='2026-03-19',targets=result['targets'])],
        risk_chains_by_decision={'2026-03-18':result['risk_chains_by_security']},target_does_not_prove_order_acceptance=True,
        static_risk_and_liquidity_roles=dict(risk=inputs['risk_label_role'],liquidity=inputs['latest_liquidity_role']),
        conditional_coordinate_provenance=inputs['candidate_full_original_provenance'],supplemental_dated_provenance=inputs['candidate_supplemental_dated_provenance'],
        historical_expected_source_hashes=target_sources,archive_resolution=value['archive_resolution'],**dict.fromkeys(FALSE,False))
    if not exact(value,expected):raise ValueError('Entire target/schedule/clock/provenance/source differs')
    return dict(job_id=JOB,fit_rows=126,fit_start=fit['index'][0][:10],fit_end='2026-03-18',calendar_count=127,first_next_open='2026-03-19',
        full_raw_and_target_and_started_exact=True,first126_matrix_independently_reconstructed=True,future126_not_consumed=True,diagnostics=diagnostics)


def build(path,sha256):
    if TARGET_PATH is None or TARGET_SHA is None or Path(path).resolve()!=Path(TARGET_PATH).resolve() or sha256!=TARGET_SHA:raise ValueError('Await hard completed target path/SHA')
    sources=dict(LOADED);reference=dict(path=str(Path(path).resolve()),sha256=sha256);value=read(reference,sources)
    owner_sources={str(OWNER):OWNER_SHA}
    for module_path in (Path(scalar.numerical_sources.__file__).resolve(),archive.SOURCE,archive.drift.SOURCE,Path(scalar.__file__).resolve(),Path(typed.__file__).resolve(),Path(exclusive_publish.__code__.co_filename).resolve()):
        owner_sources[str(module_path)]=hashlib.sha256(module_path.read_bytes()).hexdigest()
    inputs=read(INPUT,owner_sources);audit=read(AUDIT,owner_sources);plan=read(PLAN,owner_sources)
    if audit['schema']!='TWENTY_HISTORICAL_INPUTS_INDEPENDENT_RAW_DECIMAL_AUDIT_V1' or not exact(audit['artifact_reference'],INPUT) or audit['historical_expected_source_hashes'].get(str(INPUT_READER))!=INPUT_READER_SHA:raise ValueError('Hard input independent audit lineage differs')
    archive.merge(owner_sources,{str(INPUT_READER):INPUT_READER_SHA})
    for document in (inputs,audit,plan):archive.merge(owner_sources,document['historical_expected_source_hashes'])
    numerical=scalar.numerical_sources._sources();archive.merge(owner_sources,numerical)
    folder=Path(reference['path']).parent
    if value['started_reference']['path']!=str(folder/'started.json') or value['raw_fit_reference']['path']!=str(folder/'raw_fit_receipt.json'):raise ValueError('Raw/marker must share exact attempt directory')
    started=read(value['started_reference'],sources);raw=read(value['raw_fit_reference'],sources)
    archive.merge(sources,owner_sources);archive.merge(sources,value['historical_expected_source_hashes'])
    archive.verify_expected_sources(sources,archive.load_contract())
    details=inspect(value,raw,started,inputs,plan,numerical,owner_sources)
    if not exact(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution']):raise ValueError('Saved target source partition differs')
    return dict(schema='HISTORICAL_SINGLE_TARGET_INDEPENDENT_READBACK_V1',target_reference=reference,input_reference=INPUT,independent_input_audit_reference=AUDIT,
        details=details,producer_prepare_or_validation_called=False,fitter_called=False,account_execution_called=False,
        historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,archive.load_contract()),**dict.fromkeys(FALSE,False))


def verify(value):
    if value.get('schema')!='HISTORICAL_SINGLE_TARGET_INDEPENDENT_READBACK_V1' or not exact(value,build(value['target_reference']['path'],value['target_reference']['sha256'])):raise ValueError('Complete independent target readback differs')


def publish_verified(path,value):
    verify(value);saved=exclusive_publish(path,value)
    if not exact(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution']):raise ValueError('Source drift after publication')
    return saved


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--target',required=True);p.add_argument('--target-sha256',required=True);p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(publish_verified(a.output,build(a.target,a.target_sha256))))
