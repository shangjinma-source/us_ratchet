"""One mechanical historical structure, independently checked; no account execution."""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_dynamic_cutoff_refit_v2_research as fitter
from backtest import ndx_root_price_archive_contract_research as archive
from scripts import ndx_latest_all_k_completed_independent_audit_20260919 as scalar
from scripts import ndx_latest_fourteen_panel_independent_readback_20260919 as typed
from scripts.ndx_latest_conditional_channels_20260919 import exclusive_publish
BASE=ROOT/'data/cache/research'
INPUT=dict(path=str(BASE/'latest_twenty_historical_inputs_20260919_v1/inputs.json'),sha256='49551a1f9cc0069935646d696b27621b748681b5769bfecbe1c8e8fa87d80939')
AUDIT_PATH=BASE/'latest_twenty_historical_inputs_20260919_v1/independent_raw_decimal_audit.json'
AUDIT_SHA='eafcb471cd4a9b5480f24539d40a33381e7152a4dbb78b2540392e36a8d17c23'
AUDIT_READER=ROOT/'scripts/ndx_twenty_historical_inputs_independent_audit_20260919.py'
AUDIT_READER_SHA='dce5010d6b844711a0aa3a7eed1a36b12b2df976460255275dc0409d25641fc9'
PLAN=dict(path=str(BASE/'latest_fourteen_incremental_refit_20260919_v1/plan.json'),sha256='b604b6f5ca1385c83d4fea3fb930b0ddc6e3a1bb30eeab665261f4b53ed5b563')
STRUCTURE_TASK='00065cbc0bccd9ba06b1fbafab0f80070bd79ba26d9607103edd4c1d814361e1'
TICKERS={'ADI','AMAT','LRCX','FAST','AMZN','NFLX','DXCM','AVGO'}
FALSE=('execution_performed','orders_created','winner_selected','latest_weights_imported','point_in_time_verified','legal_training_input_admitted','promotion_allowed','dual_benchmark_evaluation_performed','oos_evaluation_performed','global_optimum_proven')
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(fitter.__file__).resolve(),archive.SOURCE,archive.drift.SOURCE,Path(scalar.__file__).resolve(),Path(typed.__file__).resolve(),Path(exclusive_publish.__code__.co_filename).resolve())}


def digest(value):return scalar.digest(value)
def read(reference,sources):return scalar.read(reference,sources)
def verify_sources(sources):return archive.verify_expected_sources(sources,archive.load_contract())


def historical_view(document,structure):
    source=structure['task']
    if structure['task_id']!=STRUCTURE_TASK or structure['task_id']!=digest(source) or source['cutoff']!='2026-09-17' or source['holding_count']!=8 or source['weight_spec']!='constrained_fixed_shrinkage' or {r['ticker'] for r in source['selected'].values()}!=TICKERS or not scalar.exact(source['parameters'],scalar.PARAMS) or source['previous_target_weights'] is not None:raise ValueError('Exact mechanical structure, not fitted weights, required')
    prices=document['prices'];calendar=prices['calendar'];frame=typed.decode(prices['returns'])
    if len(calendar)!=253 or len(frame)!=252 or calendar[126]!='2026-03-18' or calendar[127]!='2026-03-19' or calendar[-1]!='2026-09-17' or [d.date().isoformat() for d in frame.index]!=calendar[1:] or prices['fit_return_dates']!=calendar[1:127] or prices['evaluation_return_dates']!=calendar[127:]:raise ValueError('Exact separated historical fit/forward calendar required')
    # The fitter receives only these rows. No full-frame or tail-slicing shortcut.
    fit=frame.iloc[:126].copy(deep=True)
    if len(fit)!=126 or fit.index[-1]!=pd.Timestamp('2026-03-18'):raise ValueError('Explicit fit-only matrix required')
    by_sid={row['security_id']:row for row in document['candidate_coordinate_and_risk_rows']}
    for sid,selected in source['selected'].items():
        if sid not in by_sid or not scalar.exact(selected,{key:by_sid[sid][key] for key in ('ticker','issuer_id','risk_chain')}):raise ValueError('Historical conditional structure differs from bound identities')
    task=copy.deepcopy(source);task['cutoff']='2026-03-18';task['task_id']=digest(task)
    if task['task_id']==STRUCTURE_TASK:raise ValueError('Historical job must have a new identity')
    return fit,task,calendar[126:]


def prepare():
    if AUDIT_SHA is None:raise ValueError('Await externally sealed independent 20-channel audit')
    sources=dict(LOADED);document=read(INPUT,sources);audit_ref=dict(path=str(AUDIT_PATH),sha256=AUDIT_SHA);audit=read(audit_ref,sources);plan=read(PLAN,sources)
    if audit['schema']!='TWENTY_HISTORICAL_INPUTS_INDEPENDENT_RAW_DECIMAL_AUDIT_V1' or not scalar.exact(audit['artifact_reference'],INPUT) or any(audit[k] is not False for k in ('producer_build_called','pure_assemble_called','fit_performed','point_in_time_verified','promotion_allowed')) or audit['source_roles_and_identity_assumptions_exact'] is not True:raise ValueError('Independent historical input authority differs')
    for key,count in dict(securities=20,price_rows_per_security=253,return_rows_per_security=252,open_close_cells=10120,return_cells=5040).items():
        if type(audit[key]) is not int or audit[key]!=count:raise ValueError('Complete independent audit denominator required')
    if audit['historical_expected_source_hashes'].get(str(AUDIT_READER))!=AUDIT_READER_SHA:raise ValueError('Frozen independent input reader source missing')
    archive.merge(sources,{str(AUDIT_READER):AUDIT_READER_SHA})
    for value in (document,audit,plan):archive.merge(sources,value['historical_expected_source_hashes'])
    numeric=fitter._sources();archive.merge(sources,numeric);verify_sources(sources)
    row=min((r for r in plan['delta']['tasks'] if r['input_equivalent_to_old_task'] is False),key=lambda r:r['task_id'])
    fit,task,calendar=historical_view(document,row)
    return dict(task=task,fit_returns=fit,execution_observation_calendar=calendar,input_reference=INPUT,independent_input_audit_reference=audit_ref,
        structure_reference=dict(plan_reference=PLAN,original_task_id=STRUCTURE_TASK,role='FIRST_NEW_TASK_MECHANICAL_WIRING_FIXTURE_NOT_WINNER'),
        conditional_coordinate_provenance=document['candidate_full_original_provenance'],supplemental_dated_provenance=document['candidate_supplemental_dated_provenance'],
        static_risk_and_liquidity_roles=dict(risk=document['risk_label_role'],liquidity=document['latest_liquidity_role']),
        numerical_sources=numeric,historical_expected_source_hashes=sources)


def state_digest(state):
    return digest({k:typed.prior.frame_payload(v) if isinstance(v,pd.DataFrame) else v for k,v in state.items()})


def validate_fit(result,state):
    fit=state['fit_returns'];task=state['task']
    if len(fit)!=126 or fit.index[-1]!=pd.Timestamp(task['cutoff']):raise ValueError('Only explicit 126 historical rows may be audited')
    if not scalar.exact(result['source_hashes'],state['numerical_sources']):raise ValueError('Original frozen fitter closure differs')
    return scalar.inspect_result(result,task,dict(returns=typed.prior.frame_payload(fit)))


def run(folder,*,execute=False):
    state=prepare();sealed=state_digest(state);sources=dict(state['historical_expected_source_hashes']);task=copy.deepcopy(state['task'])
    if execute is not True:
        verify_sources(sources)
        return dict(schema='HISTORICAL_SINGLE_TARGET_PREFLIGHT_V1',job_id=task['task_id'],fit_rows=126,cutoff='2026-03-18',evaluation_calendar_count=127,
            next_open_observation='2026-03-19',actual_fitter_calls=0,**dict.fromkeys(FALSE,False))
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    marker=folder/'started.json';raw_path=folder/'raw_fit_receipt.json';output=folder/'target.json';failure=folder/'failure.json'
    if any(p.exists() for p in (marker,raw_path,output,failure)):raise ValueError('Existing attempt/result refuses any automatic refit')
    started=exclusive_publish(marker,dict(schema='HISTORICAL_SINGLE_TARGET_ATTEMPT_V1',job_id=task['task_id'],input_reference=state['input_reference'],attempt_count=1))
    archive.merge(sources,{started['path']:started['sha256']})
    try:
        verify_sources(sources)
        if state_digest(state)!=sealed:raise ValueError('Prepared historical input changed')
        fit_input_before_call=typed.prior.frame_payload(state['fit_returns'])
        result=fitter.refit_dynamic_cutoff_weights(returns=state['fit_returns'],cutoff=task['cutoff'],selected=task['selected'],weight_spec=task['weight_spec'],previous_target_weights=None,**task['parameters'])
        # Preserve returned bytes before validation; no retry if later audit fails.
        raw=exclusive_publish(raw_path,dict(schema='HISTORICAL_SINGLE_TARGET_RAW_FIT_RECEIPT_V1',job_id=state['task']['task_id'],original_result=result,
            explicit_fit_matrix=fit_input_before_call,task=state['task'],input_reference=state['input_reference'],
            independent_input_audit_reference=state['independent_input_audit_reference'],structure_reference=state['structure_reference'],
            started_reference=started,historical_expected_source_hashes=sources,**dict.fromkeys(FALSE,False)))
        archive.merge(sources,{raw['path']:raw['sha256']})
        if state_digest(state)!=sealed or not scalar.exact(task,state['task']):raise ValueError('Fitter mutated historical input/selected structure')
        audit=validate_fit(result,state);partition=verify_sources(sources)
        value=dict(schema='HISTORICAL_SINGLE_CONDITIONAL_TARGET_V1',job_id=task['task_id'],task=task,result=result,independent_matrix_and_risk_audit=audit,
            status='FITTED_FIVE_RISKS_PASSED' if audit['risk_pass'] else 'FITTED_FIVE_RISKS_FAILED',raw_fit_reference=raw,started_reference=started,
            input_reference=state['input_reference'],independent_input_audit_reference=state['independent_input_audit_reference'],structure_reference=state['structure_reference'],
            execution_observation_calendar=state['execution_observation_calendar'],baseline_close_date='2026-03-18',first_next_open_observation='2026-03-19',
            schedule=[dict(decision_date='2026-03-18',execution_date='2026-03-19',targets=result['targets'])],
            risk_chains_by_decision={'2026-03-18':result['risk_chains_by_security']},
            target_does_not_prove_order_acceptance=True,static_risk_and_liquidity_roles=state['static_risk_and_liquidity_roles'],
            conditional_coordinate_provenance=state['conditional_coordinate_provenance'],supplemental_dated_provenance=state['supplemental_dated_provenance'],
            historical_expected_source_hashes=sources,archive_resolution=partition,**dict.fromkeys(FALSE,False))
        saved=exclusive_publish(output,value);verify_sources(sources);return saved
    except BaseException as exc:
        if not failure.exists():exclusive_publish(failure,dict(schema='HISTORICAL_SINGLE_TARGET_FAILED_ATTEMPT_V1',job_id=state['task']['task_id'],error_type=type(exc).__name__,raw_result_preserved=raw_path.exists(),automatic_retry_allowed=False))
        raise
    finally:verify_sources(sources)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--folder',required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args();print(json.dumps(run(args.folder,execute=args.execute)))
