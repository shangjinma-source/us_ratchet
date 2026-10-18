"""Explicit one-shot conditional 127-session accounts; no fitting or automatic replay."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_conditional_single_window_account_arguments_research as assembly
from backtest import ndx_dynamic_frozen_execution_research as candidate
from backtest import ndx_dynamic_frozen_incumbent_control as control
from backtest import ndx_frozen_accounting_independent_audit_research as candidate_audit
from backtest import ndx_fixed_control_accounting_independent_audit_research as control_audit
from backtest import ndx_frozen_target_normalization_audit_research as normalization
from scripts import ndx_historical_single_target_independent_audit_20260919 as target_reader
from scripts.ndx_latest_conditional_channels_20260919 import exclusive_publish
archive=target_reader.archive
BASE=ROOT/'data/cache/research/historical_single_window_accounts_20260920_v1'
INPUT=target_reader.INPUT
TARGET=dict(path=str(target_reader.TARGET_PATH),sha256='4d174d9263153f7df77b7c4357ed18eb13a2a8eb9194781a642d923762af90b6')
AUDIT_PATH=Path(TARGET['path']).parent/'independent_readback.json'
AUDIT_SHA='a3d18620288e95be31555a0226c935b8c5926c4aa47fd0e45efc5848b593890b'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),*(Path(m.__file__).resolve() for m in (assembly,candidate,control,candidate_audit,control_audit,normalization,target_reader)),archive.SOURCE,archive.drift.SOURCE,Path(exclusive_publish.__code__.co_filename).resolve())}
archive.merge(LOADED,candidate._LOADED_SOURCES)
archive.merge(LOADED,target_reader.LOADED)
FALSE=('fit_performed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','winner_selected','provider_identity_verified','continuous_identity_interval_verified','corporate_action_completeness_verified','cash_dividends_modelled','additional_cash_flows_supported')


def encode(value):
    if isinstance(value,pd.DataFrame):return dict(type='dataframe',index_type=type(value.index).__name__,index=[v.isoformat() for v in value.index],columns=value.columns.tolist(),dtypes=[str(v) for v in value.dtypes],data=value.values.tolist())
    if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
    if isinstance(value,list):return [encode(v) for v in value]
    return value


def digest(value):return hashlib.sha256(json.dumps(encode(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def verify_sources(sources):return archive.verify_expected_sources(sources,archive.load_contract())


def prepare(track):
    if track not in ('candidate','incumbent'):raise ValueError('Explicit candidate or original incumbent track required')
    if AUDIT_SHA is None:raise ValueError('Await sealed independent historical target audit')
    sources=dict(LOADED);document=target_reader.read(INPUT,sources);target=target_reader.read(TARGET,sources)
    audit_ref=dict(path=str(AUDIT_PATH),sha256=AUDIT_SHA);audit=target_reader.read(audit_ref,sources)
    # Full independent persisted-target reconstruction, no producer/solver calls.
    target_reader.verify(audit)
    if audit['target_reference']!=TARGET or audit['input_reference']!=INPUT:raise ValueError('Historical target audit lineage differs')
    for value in (document,target,audit):archive.merge(sources,value['historical_expected_source_hashes'])
    assembled=assembly.assemble_account_arguments(inputs=document,schedule=target['schedule'],risk_chains_by_decision=target['risk_chains_by_decision'])
    selected=assembled[track]
    if track=='candidate':effective,evidence=normalization.normalized_schedule(selected['original_schedule'])
    else:effective=deepcopy(selected['original_schedule']);evidence=dict(policy='ORIGINAL_CONTROL_WEIGHTS_NOT_NORMALIZED',normalization_count=0)
    state=dict(track=track,selected=selected,calendar=assembled['calendar'],contract=assembled['contract'],effective_schedule=effective,normalization_evidence=evidence,
        input_reference=deepcopy(INPUT),target_reference=deepcopy(TARGET),independent_target_audit_reference=audit_ref,historical_expected_source_hashes=sources)
    state['archive_resolution']=verify_sources(sources)
    return state


def restore_and_audit(raw,state):
    value=deepcopy(raw);selected=state['selected'];columns=selected['columns'];labels=selected['labels']
    for row in value['decisions']:
        for sid,item in row['targets'].items():
            if item['ticker']!=columns[sid]:raise ValueError('Unexpected decision internal ticker')
            item['ticker']=labels[sid]['ticker']
    for row in value['trades']:
        if row['ticker']!=columns[row['security_id']]:raise ValueError('Unexpected trade internal ticker')
        row['ticker']=labels[row['security_id']]['ticker']
    for row in value['daily']:
        if row['tickers']!={sid:columns[sid] for sid in row['shares']}:raise ValueError('Unexpected daily internal ticker')
        row['tickers']={sid:labels[sid]['ticker'] for sid in row['shares']}
    oracle=candidate_audit if state['track']=='candidate' else control_audit
    result=oracle.audit(execution=value,calendar=state['calendar'],schedule=state['effective_schedule'],prices=selected['prices'],risk_chains_by_decision=selected['arguments']['risk_chains_by_decision'],contract=state['contract'])
    return value,result


def run(*,track,execute=False):
    if type(execute) is not bool or track not in ('candidate','incumbent'):raise ValueError('Explicit track and execution boolean required')
    folder=BASE/track;paths={k:folder/name for k,name in dict(started='started.json',raw='raw_execution.json',account='account.json',failure='failure.json').items()}
    if folder.exists() and any(folder.iterdir()):raise FileExistsError('Existing attempt, orphan or result prohibits replay')
    state=prepare(track);sealed=digest(state);sources=deepcopy(state['historical_expected_source_hashes']);partition=state['archive_resolution']
    def verify():
        if digest(state)!=sealed:raise ValueError('Prepared account RAM changed')
        if digest(verify_sources(sources))!=digest(partition):raise ValueError('Account source partition changed')
    verify()
    if not execute:return dict(track=track,session_count=len(state['calendar']),execution_performed=False,**dict.fromkeys(FALSE,False))
    started=exclusive_publish(paths['started'],dict(schema='HISTORICAL_SINGLE_WINDOW_ACCOUNT_ATTEMPT_V1',track=track,attempt_count=1,prepared_sha256=sealed,input_reference=INPUT,target_reference=TARGET,independent_target_audit_reference=state['independent_target_audit_reference']))
    references=[started];raw_reference=None;called=False
    def check_attempt():
        verify()
        for ref in references:
            if hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()!=ref['sha256']:raise ValueError('Durable attempt/raw receipt changed')
    try:
        check_attempt();kwargs=deepcopy(state['selected']['arguments']);before=digest(kwargs);called=True
        engine=candidate.simulate_dynamic_frozen_execution_research if track=='candidate' else control.simulate_dynamic_frozen_incumbent_control
        raw=engine(**kwargs)
        raw_reference=exclusive_publish(paths['raw'],dict(schema='HISTORICAL_SINGLE_WINDOW_RAW_EXECUTION_V1',track=track,execution=raw,started_reference=started,
            original_schedule=state['selected']['original_schedule'],internal_columns=state['selected']['columns'],calendar=state['calendar'],execution_contract=state['contract'],independent_accounting_completed=False,**dict.fromkeys(FALSE,False)))
        references.append(raw_reference)
        if digest(kwargs)!=before:raise ValueError('Engine mutated supplied execution arguments')
        check_attempt();execution,audit=restore_and_audit(raw,state);check_attempt()
        result=dict(schema='HISTORICAL_SINGLE_WINDOW_CONDITIONAL_ACCOUNT_V1',track=track,execution=execution,independent_decimal_accounting=audit,
            calendar=state['calendar'],schedule=state['selected']['original_schedule'],effective_schedule=state['effective_schedule'],normalization_evidence=state['normalization_evidence'],
            execution_contract=state['contract'],internal_columns=state['selected']['columns'],input_reference=INPUT,target_reference=TARGET,independent_target_audit_reference=state['independent_target_audit_reference'],
            started_reference=started,raw_execution_reference=raw_reference,historical_expected_source_hashes=sources,archive_resolution=partition,
            prepared_sha256=sealed,execution_performed=True,risk_is_order_gate=track=='candidate',scope='CONDITIONAL_HISTORICAL_MECHANICAL_STRUCTURE_NOT_WINNER',**dict.fromkeys(FALSE,False))
        saved=exclusive_publish(paths['account'],result);references.append(saved);check_attempt();return saved
    except BaseException as error:
        if not paths['failure'].exists():exclusive_publish(paths['failure'],dict(schema='HISTORICAL_SINGLE_WINDOW_FAILED_ATTEMPT_V1',track=track,started_reference=started,raw_execution_reference=raw_reference,
            engine_call_started=called,error_type=type(error).__name__,automatic_retry_allowed=False,failure_is_economic_infeasibility=False,**dict.fromkeys(FALSE,False)))
        raise
    finally:check_attempt()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--track',required=True,choices=('candidate','incumbent'));parser.add_argument('--execute',action='store_true');print(json.dumps(run(**vars(parser.parse_args()))))
