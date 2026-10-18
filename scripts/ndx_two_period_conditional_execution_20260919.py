"""One-shot bounded seven-SID conditional account, using the unchanged frozen engine."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_dynamic_frozen_execution_research as engine
from backtest import ndx_frozen_accounting_independent_audit_research as independent
from backtest import ndx_root_price_archive_contract_research as archive
from scripts import ndx_seven_dated_identity_assembly_20260919 as identity
from scripts.ndx_may_cutoff_snapshot_independent_readback_20260919 import verify_gaps
from scripts.ndx_corrected_frontier_single_refit_archive_research import publish

BASE=ROOT/'data/cache/research'
BOUND={
 'target':('corrected_explicit_path_20260919_v1/target_path.json','3270302ee18a8a4a3503ab9227bebc53c6a4b3a6728c79ffdc8b5c5196fee266'),
 'audit':('corrected_explicit_path_20260919_v1/independent_audit.json','afff057b93b7ddaa7478bf1b879e8c3960024fcd97a759203c0147461d5c0fbb'),
 'prices':('seven_ticker_price_only_20260919_v1/prices.json','56dece6ee94518d39fbeb101d1d5e06c7351a05e90dd70cf87adf713196cc7bb')}
CLOCK=[('2023-03-31','2023-04-03'),('2023-04-28','2023-05-01')]
SOURCE=Path(__file__).resolve()
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(independent.__file__).resolve(),
    Path(identity.__file__).resolve(),archive.SOURCE,Path(verify_gaps.__code__.co_filename).resolve(),Path(publish.__code__.co_filename).resolve())}
archive.merge(LOADED,engine._LOADED_SOURCES)


def exact(a,b): return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def assemble(target,price,identities):
    """No fitting or execution; all identity intervals remain explicit assumptions."""
    if target['schema']!='CORRECTED_EXPLICIT_STRATEGIC_TARGET_PATH_V1' or price['schema']!='SEVEN_TICKER_21_SESSION_PRICE_ONLY_V1' or identities['schema']!='SEVEN_DATED_IDENTITY_CONDITIONAL_ACCOUNTING_ASSEMBLY_V1':
        raise ValueError('Exact target, price-only and conditional identity schemas required')
    for report in (target,price,identities):
        if report['point_in_time_verified'] is not False or report['promotion_allowed'] is not False: raise ValueError('Research scope cannot be upgraded')
    if identities['conditional_window']!={'start':'2023-03-31','end':'2023-05-01'} or identities['continuous_identity_interval_verified'] is not False or identities['provider_price_binding_verified'] is not False or identities['early_evidence_availability_inferred'] is not False:
        raise ValueError('Conditional dated identity window differs')
    identity.validate_report(identities)
    labels={r['security_id']:r for r in identities['rows']}
    calendar=price['calendar'];schedule=deepcopy(target['schedule'])
    if len(calendar)!=21 or calendar!=sorted(set(calendar)) or calendar!=[d for d in target['calendar'] if '2023-03-31'<=d<='2023-05-01'] or [(r['decision_date'],r['execution_date']) for r in schedule]!=CLOCK:
        raise ValueError('Exact bounded target and observed execution clock required')
    if set(price['tickers'])!={r['ticker'] for r in labels.values()} or len(price['tickers'])!=7 or set().union(*(r['targets'] for r in schedule))!=set(labels):
        raise ValueError('Complete seven-security price/target identity union required')
    for row in schedule:
        if calendar[calendar.index(row['decision_date'])+1]!=row['execution_date']: raise ValueError('Next observed Open required')
        for sid,value in row['targets'].items():
            if value['ticker']!=labels[sid]['ticker'] or value['issuer_id']!=labels[sid]['issuer_id']: raise ValueError('Target contradicts dated identity coordinate')
    numeric=dict(initial_cash_usd=target['downstream_execution_capital_usd'],minimum_cash_buffer_usd=target['downstream_execution_cash_buffer_usd'],
        transaction_cost_bps=target['downstream_execution_transaction_cost_bps'],**target['fixed_risk_parameters'])
    expected=dict(initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10,max_single_weight=.45,min_single_weight=.05,
        top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
    if set(numeric)!=set(expected) or any(independent.number(numeric[k])!=independent.number(v) for k,v in expected.items()): raise ValueError('Formal execution capital/fees/five risks differ')
    columns={sid:'SID_'+sid.split(':')[1]+'_'+sid.split(':')[2] for sid in labels}
    marks={d:{} for d in calendar};frames={}
    for kind in ('open','close'):
        if set(price['matrices'][kind])!=set(calendar): raise ValueError('Price calendar differs')
        for d in calendar:
            if set(price['matrices'][kind][d])!=set(price['tickers']): raise ValueError('Complete price matrix required')
            for sid,row in labels.items():
                value=price['matrices'][kind][d][row['ticker']]
                if independent.number(value)<=0: raise ValueError('Positive nominal price required')
                marks[d].setdefault(sid,dict(ticker=row['ticker']))[kind]=value
        frames[kind]=pd.DataFrame({columns[sid]:[marks[d][sid][kind] for d in calendar] for sid in labels},index=pd.DatetimeIndex(calendar))
    translated=deepcopy(schedule)
    for row in translated:
        for sid,value in row['targets'].items(): value['ticker']=columns[sid]
    arguments=dict(opens=frames['open'],closes=frames['close'],schedule=translated,risk_chains_by_decision=deepcopy(target['risk_chains_by_decision']),
        corporate_actions=[],identity_events=[],valuation_end_date=calendar[-1],max_repair_evaluations=262144,**numeric)
    return dict(arguments=arguments,calendar=calendar,schedule=schedule,prices=marks,contract=numeric,columns=columns,labels=labels)


def execute_prepared(prepared):
    result=engine.simulate_dynamic_frozen_execution_research(**deepcopy(prepared['arguments']))
    labels=prepared['labels'];columns=prepared['columns']
    for decision in result['decisions']:
        for sid,value in decision['targets'].items():
            if value['ticker']!=columns[sid]: raise ValueError('Engine internal column changed')
            value['ticker']=labels[sid]['ticker']
    for trade in result['trades']:
        if trade['ticker']!=columns[trade['security_id']]: raise ValueError('Unexpected trade column')
        trade['ticker']=labels[trade['security_id']]['ticker']
    for row in result['daily']:
        if row['tickers']!={sid:columns[sid] for sid in row['shares']}: raise ValueError('Unexpected daily column')
        row['tickers']={sid:labels[sid]['ticker'] for sid in row['shares']}
    audit=independent.audit(execution=result,calendar=prepared['calendar'],schedule=prepared['schedule'],prices=prepared['prices'],
        risk_chains_by_decision=prepared['arguments']['risk_chains_by_decision'],contract=prepared['contract'])
    return result,audit


def prepare(identity_path,identity_sha256):
    sources=dict(LOADED);docs={}
    def read(path,sha):
        path=Path(path).resolve();raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha: raise ValueError('External artifact bytes differ')
        archive.merge(sources,{str(path):sha});return json.loads(raw)
    for role,(path,sha) in BOUND.items(): docs[role]=read(BASE/path,sha)
    identities=read(identity_path,identity_sha256)
    if not exact(identities,identity.build()): raise ValueError('Bound dated evidence no longer reconstructs')
    target=docs['target']['result'];audit=docs['audit'];price=docs['prices']
    if audit['result']!={'path':str(BASE/BOUND['target'][0]),'sha256':BOUND['target'][1]} or audit['whole_first_seed_refit_exact'] is not True or audit['complete_strategic_prior_verified'] is not True:
        raise ValueError('Independent target audit is not linked to exact path')
    for report in (target,audit,price,identities):
        for key in ('source_hashes','historical_expected_source_hashes'):
            if key in report: archive.merge(sources,report[key])
    archive.merge(sources,docs['target']['runner_source_hashes'])
    gaps=target['historical_loader_gap_observations']
    prepared=assemble(target,price,identities)
    return prepared,sources,gaps


def run(*,identity_path,identity_sha256,output,execute=False):
    if type(execute) is not bool: raise ValueError('Explicit execute boolean required')
    output=Path(output).resolve();started_path=Path(str(output)+'.started.json');failed_path=Path(str(output)+'.failure.json')
    if not output.is_relative_to(BASE) or any(p.exists() for p in (output,started_path,failed_path)): raise FileExistsError('New research destination/attempt required')
    prepared,sources,gaps=prepare(identity_path,identity_sha256)
    def verify():
        verify_gaps(gaps)
        return archive.verify_expected_sources(sources,archive.load_contract())
    resolution=verify()
    if not execute: return dict(prepare_completed=True,execution_performed=False,fit_performed=False,session_count=21,promotion_allowed=False)
    started=publish(started_path,dict(schema='TWO_PERIOD_CONDITIONAL_EXECUTION_ATTEMPT_V1',status='STARTED_NOT_COMPLETED',
        identity_reference=dict(path=str(Path(identity_path).resolve()),sha256=identity_sha256),source_hashes=sources))
    def verify_attempt():
        if hashlib.sha256(Path(started['path']).read_bytes()).hexdigest()!=started['sha256']: raise ValueError('Durable attempt changed')
        if verify()!=resolution: raise ValueError('Source partition changed')
    try:
        verify_attempt();execution,audit=execute_prepared(prepared);verify_attempt()
    except Exception as error:
        publish(failed_path,dict(schema='TWO_PERIOD_CONDITIONAL_EXECUTION_FAILURE_V1',started_attempt=started,error_type=type(error).__name__,
            error=str(error),automatic_retry_allowed=False,numerical_failure_is_economic_infeasibility=False,promotion_allowed=False))
        raise
    result=dict(schema='TWO_PERIOD_CONDITIONAL_FROZEN_ACCOUNT_V1',execution=execution,independent_decimal_accounting=audit,calendar=prepared['calendar'],
        schedule=prepared['schedule'],execution_contract=prepared['contract'],internal_columns=prepared['columns'],started_attempt=started,
        historical_expected_source_hashes=sources,archive_resolution=resolution,historical_loader_gap_observations=gaps,
        scope='EXPLICIT_DIAGNOSTIC_TARGET_PATH_CONDITIONAL_DATED_IDENTITIES_NOT_SELECTED_WINNER',
        execution_performed=True,fit_performed=False,legacy_identity_bridge_called=False,frozen_engine_source_modified=False,
        additional_cash_flows_supported=False,dividend_cash_flows_modelled=False,continuous_identity_interval_verified=False,
        provider_binding_verified=False,corporate_action_completeness_verified=False,point_in_time_verified=False,promotion_allowed=False)
    verify_attempt();saved=publish(output,result);verify_attempt();return dict(saved,execution_performed=True,independent_accounting_passed=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('identity-path','identity-sha256','output'): parser.add_argument('--'+name,required=True)
    parser.add_argument('--execute',action='store_true');print(json.dumps(run(**vars(parser.parse_args()))))
