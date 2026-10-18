"""One explicit v2 attempt: preserve raw execution before independent normalization/accounting audit."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_two_period_conditional_execution_20260919 as prior
from backtest import ndx_frozen_target_normalization_audit_research as normalization

BASE=prior.BASE
FAILURE=BASE/'two_period_conditional_execution_20260919_v1/account.json.failure.json'
FAILURE_SHA='39a35e86644c878ffe07bb7658da3e7ceb351f8328172da9cb542e9963ab9775'
OLD_STARTED=BASE/'two_period_conditional_execution_20260919_v1/account.json.started.json'
OLD_STARTED_SHA='817569d0ff48971d8675e15527229db58e8373ba7b26cc8e636fa3af79989798'
IDENTITY=BASE/'seven_dated_identity_assembly_20260919_v1/identities.json'
IDENTITY_SHA='ed810b2fc1626e05f3c1edee10212645dad37435461b8b7e8d01dcba1354e7c2'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(prior.__file__).resolve(),Path(normalization.__file__).resolve())}


def prepare():
    prepared,sources,gaps=prior.prepare(IDENTITY,IDENTITY_SHA)
    prior.archive.merge(sources,LOADED)
    for path,sha in ((FAILURE,FAILURE_SHA),(OLD_STARTED,OLD_STARTED_SHA)):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('Historical failed attempt differs')
        prior.archive.merge(sources,{str(path):sha})
    failure=json.loads(FAILURE.read_bytes())
    if failure['started_attempt']!={'path':str(OLD_STARTED),'sha256':OLD_STARTED_SHA} or failure['error']!='Saved target schedule differs' or failure['automatic_retry_allowed'] is not False or failure['numerical_failure_is_economic_infeasibility'] is not False:raise ValueError('Exact documented historical failure required')
    normalized,evidence=normalization.normalized_schedule(prepared['schedule'])
    return prepared,normalized,evidence,sources,gaps


def restore_and_audit(raw,prepared,normalized):
    """Restore labels only; no second normalization or execution."""
    result=deepcopy(raw);columns=prepared['columns'];labels=prepared['labels']
    for decision in result['decisions']:
        for sid,value in decision['targets'].items():
            if value['ticker']!=columns[sid]:raise ValueError('Unexpected internal decision column')
            value['ticker']=labels[sid]['ticker']
    for trade in result['trades']:
        sid=trade['security_id']
        if trade['ticker']!=columns[sid]:raise ValueError('Unexpected internal trade column')
        trade['ticker']=labels[sid]['ticker']
    for row in result['daily']:
        if row['tickers']!={sid:columns[sid] for sid in row['shares']}:raise ValueError('Unexpected daily internal columns')
        row['tickers']={sid:labels[sid]['ticker'] for sid in row['shares']}
    audit=prior.independent.audit(execution=result,calendar=prepared['calendar'],schedule=normalized,prices=prepared['prices'],
        risk_chains_by_decision=prepared['arguments']['risk_chains_by_decision'],contract=prepared['contract'])
    return result,audit


def run(*,output,execute=False):
    if type(execute) is not bool:raise ValueError('Explicit execution boolean required')
    output=Path(output).resolve();started_path=Path(str(output)+'.started.json');failed_path=Path(str(output)+'.failure.json');raw_path=Path(str(output)+'.raw_execution.json')
    if not output.is_relative_to(BASE/'two_period_conditional_execution_20260919_v2') or any(p.exists() for p in (output,started_path,failed_path,raw_path)):raise FileExistsError('Fresh v2 namespace/attempt required; raw or failed attempts cannot rerun')
    prepared,normalized,evidence,sources,gaps=prepare()
    def verify():
        prior.verify_gaps(gaps)
        return prior.archive.verify_expected_sources(sources,prior.archive.load_contract())
    resolution=verify()
    if not execute:return dict(prepare_completed=True,execution_performed=False,fit_performed=False,session_count=len(prepared['calendar']),normalization_evidence=evidence,promotion_allowed=False)
    started=prior.publish(started_path,dict(schema='TWO_PERIOD_CONDITIONAL_EXECUTION_ATTEMPT_V2',status='STARTED_NOT_COMPLETED',
        identity_reference={'path':str(IDENTITY),'sha256':IDENTITY_SHA},historical_v1_failure_reference={'path':str(FAILURE),'sha256':FAILURE_SHA},source_hashes=sources))
    raw_ref=None;engine_called=False
    def verify_attempt():
        for ref in [started]+([raw_ref] if raw_ref else []):
            if hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()!=ref['sha256']:raise ValueError('Durable attempt/raw execution changed')
        if verify()!=resolution:raise ValueError('Source partition changed')
    try:
        verify_attempt();engine_called=True
        raw=prior.engine.simulate_dynamic_frozen_execution_research(**deepcopy(prepared['arguments']))
        # Preserve the first returned engine ledger BEFORE any downstream audit.
        raw_ref=prior.publish(raw_path,dict(schema='TWO_PERIOD_RAW_EXECUTION_RECEIPT_V2',execution=raw,original_schedule=prepared['schedule'],
            internal_columns=prepared['columns'],calendar=prepared['calendar'],execution_contract=prepared['contract'],started_attempt=started,
            historical_expected_source_hashes=sources,independent_accounting_completed=False,point_in_time_verified=False,promotion_allowed=False))
        verify_attempt();execution,audit=restore_and_audit(raw,prepared,normalized);verify_attempt()
        result=dict(schema='TWO_PERIOD_CONDITIONAL_FROZEN_ACCOUNT_V2',execution=execution,independent_decimal_accounting=audit,
            calendar=prepared['calendar'],schedule=prepared['schedule'],normalized_schedule=normalized,normalization_evidence=evidence,
            execution_contract=prepared['contract'],internal_columns=prepared['columns'],started_attempt=started,raw_execution_reference=raw_ref,
            historical_v1_failure_reference={'path':str(FAILURE),'sha256':FAILURE_SHA},historical_expected_source_hashes=sources,
            archive_resolution=resolution,historical_loader_gap_observations=gaps,
            scope='EXPLICIT_DIAGNOSTIC_TARGET_PATH_CONDITIONAL_DATED_IDENTITIES_NOT_SELECTED_WINNER',execution_performed=True,fit_performed=False,
            legacy_identity_bridge_called=False,frozen_engine_source_modified=False,additional_cash_flows_supported=False,
            dividend_cash_flows_modelled=False,continuous_identity_interval_verified=False,provider_binding_verified=False,
            corporate_action_completeness_verified=False,point_in_time_verified=False,promotion_allowed=False)
        saved=prior.publish(output,result);verify_attempt()
        return dict(saved,execution_performed=True,independent_accounting_passed=True,raw_execution_reference=raw_ref)
    except Exception as error:
        prior.publish(failed_path,dict(schema='TWO_PERIOD_CONDITIONAL_EXECUTION_FAILURE_V2',started_attempt=started,
            raw_execution_reference=raw_ref,engine_call_started=engine_called,error_type=type(error).__name__,error=str(error),
            automatic_retry_allowed=False,numerical_failure_is_economic_infeasibility=False,promotion_allowed=False))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--execute',action='store_true')
    print(json.dumps(run(**vars(parser.parse_args()))))
