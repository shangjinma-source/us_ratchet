"""Independent saved single-window accounts: no producer, engine or fit calls."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_frozen_accounting_independent_audit_research as candidate_oracle
from backtest import ndx_fixed_control_accounting_independent_audit_research as control_oracle
from backtest import ndx_fixed_control_accounting_independent_audit_v2_research as control_oracle_v2
from backtest import ndx_frozen_target_normalization_audit_research as normalization
from backtest import ndx_single_window_benchmark_metrics_research as metrics
from scripts import ndx_historical_single_target_independent_audit_20260919 as target_reader
archive=target_reader.archive
publish=target_reader.exclusive_publish
BASE=ROOT/'data/cache/research'
INPUT=target_reader.INPUT
TARGET=dict(path=str(target_reader.TARGET_PATH),sha256='4d174d9263153f7df77b7c4357ed18eb13a2a8eb9194781a642d923762af90b6')
TARGET_AUDIT=dict(path=str(Path(TARGET['path']).parent/'independent_readback.json'),sha256='a3d18620288e95be31555a0226c935b8c5926c4aa47fd0e45efc5848b593890b')
ACCOUNT_BASE=BASE/'historical_single_window_accounts_20260920_v1'
ACCOUNT_SHA={'candidate':'34b2b21b297e48a41e4568948644a5fcef4aeb7f3a3aca0d1849289181c0433d','incumbent':'361f1a99b7da952eb3abf08e087a40a8f626bb51df1dc1ad5817b06a56a4bcf5'}
RECOVERY_PATH=BASE/'historical_single_window_accounts_20260923_control_recovery_v2/account.json'
RECOVERY_SOURCE=ROOT/'scripts/ndx_single_window_control_raw_recovery_20260923.py'
RECOVERY_SOURCE_SHA='eee313cb9025e1c8409c4b76f939cfcad25ac1245530b63037699a3dadf100a4'
CONTROL_V2_SHA='dd66c787bd8e8b2cad0c14df25e88ecc7e04d502f19515072e4fa51a783140e7'
CONTROL_REFS={name:dict(path=str(ACCOUNT_BASE/'incumbent'/filename),sha256=sha) for name,filename,sha in (
    ('raw','raw_execution.json','149aa072ae6f086f45f2fe07859163d78710f35856038f062e6e475b5bf48865'),
    ('started','started.json','d722d99538b4034481110baf2a27fa9e462002da6764ad70e3921bd7708c2f34'),
    ('failure','failure.json','f8d670dfd101ad9c6284d742d981cb87d5684685690946f7c53009dc3baa6a83'))}
OWNER=ROOT/'scripts/ndx_historical_single_window_accounts_20260920.py'
OWNER_SHA='41cf0e15058b464d81b5977d3fa224608f1621abf77e9defa96ad938aec2964f'
METRICS_SHA='722a0ef12bb86ad727a10d945b22dfab1ef9d43e3c1c13ef8d3f9b4b23c91c7d'
TARGET_READER_SHA='35dab90c9ccff180acf721ccee5cafc83087702541a3e1bd85bfde0a3d75b993'
NAV_SHA='6323ef0f897eb55c50612f9f46444c5d4b499acc79596e2a3c363b6e1abe06fe'
CONTRACT=dict(initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10,max_single_weight=.45,
 min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
ACCOUNT_FALSE=('fit_performed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','winner_selected','provider_identity_verified','continuous_identity_interval_verified','corporate_action_completeness_verified','cash_dividends_modelled','additional_cash_flows_supported')
FALSE=ACCOUNT_FALSE+('producer_called','engine_called','account_execution_rerun','formal_dual_benchmark_admission','future_one_year_oos_evaluation_performed','currency_fx_equivalence_verified','nav_publication_time_verified','historical_full_source_closure_verified')
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),*(Path(m.__file__).resolve() for m in (candidate_oracle,control_oracle,control_oracle_v2,normalization,metrics,target_reader)),archive.SOURCE,archive.drift.SOURCE,Path(publish.__code__.co_filename).resolve())}


def exact(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def read(ref,sources):return target_reader.read(ref,sources)


def reconstruct(inputs,target,track):
    """Independent matrices and metadata; authentication belongs to build."""
    if track not in ('candidate','incumbent'):raise ValueError('Known account track required')
    full=inputs['prices']['calendar'];calendar=full[126:];metrics.check_calendar(calendar)
    if len(full)!=253 or inputs['prices']['known_evaluation_split_events']!=[]:raise ValueError('Action-free complete source calendar required')
    if track=='candidate':
        schedule=copy.deepcopy(target['schedule']);all_labels={r['security_id']:r for r in inputs['candidate_coordinate_and_risk_rows']}
        labels={sid:all_labels[sid] for sid in schedule[0]['targets']}
        effective,evidence=normalization.normalized_schedule(schedule)
    else:
        labels={r['security_id']:r for r in inputs['incumbent_original_securities']}
        schedule=[dict(decision_date=calendar[0],execution_date=calendar[1],targets={sid:{k:r[k] for k in ('ticker','issuer_id','target_weight')} for sid,r in labels.items()})]
        effective=copy.deepcopy(schedule);evidence=dict(policy='ORIGINAL_CONTROL_WEIGHTS_NOT_NORMALIZED',normalization_count=0)
    if len(schedule)!=1 or schedule[0]['decision_date']!=calendar[0] or schedule[0]['execution_date']!=calendar[1]:raise ValueError('Historical Close/next-Open clock differs')
    for sid,row in schedule[0]['targets'].items():
        if any(row[k]!=labels[sid][k] for k in ('ticker','issuer_id')):raise ValueError('Target coordinate differs')
    columns={sid:'SID_'+sid.upper().replace(':','_') for sid in labels}
    marks={d:{} for d in calendar};frames={}
    for name,field in (('nominal_open','open'),('nominal_close','close')):
        encoded=inputs['prices'][name]
        if encoded['index']!=[d+'T00:00:00' for d in full] or encoded['dtypes']!=['float64']*20 or len(encoded['data'])!=253 or len(encoded['columns'])!=20:raise ValueError('Complete typed source prices required')
        locations={sid:encoded['columns'].index(r['ticker']) for sid,r in labels.items()}
        for i,day in enumerate(calendar,126):
            if len(encoded['data'][i])!=20:raise ValueError('Incomplete price row')
            for sid,r in labels.items():
                value=encoded['data'][i][locations[sid]]
                if type(value) is not float or candidate_oracle.number(value)<=0:raise ValueError('Positive float64 marks required')
                marks[day].setdefault(sid,dict(ticker=r['ticker']))[field]=value
        frames['opens' if field=='open' else 'closes']=dict(type='dataframe',index_type='DatetimeIndex',index=[d+'T00:00:00' for d in calendar],
            columns=[columns[s] for s in sorted(labels)],dtypes=['float64']*len(labels),data=[[marks[d][s][field] for s in sorted(labels)] for d in calendar])
    chains={calendar[0]:{sid:labels[sid]['risk_chain'] for sid in labels}}
    if track=='candidate' and not exact(chains,target['risk_chains_by_decision']):raise ValueError('Candidate historical risk coordinates differ')
    translated=copy.deepcopy(schedule)
    for sid,row in translated[0]['targets'].items():row['ticker']=columns[sid]
    arguments=dict(**frames,schedule=translated,risk_chains_by_decision=chains,corporate_actions=[],valuation_end_date=calendar[-1],**CONTRACT)
    if track=='candidate':arguments.update(identity_events=[],max_repair_evaluations=262144)
    selected=dict(arguments=arguments,original_schedule=schedule,columns=columns,labels=labels,prices=marks,
        restore_actual_ticker_by_security={s:r['ticker'] for s,r in labels.items()},risk_is_order_gate=track=='candidate',original_weights_normalized_by_assembler=False)
    return dict(track=track,selected=selected,calendar=calendar,contract=CONTRACT,effective_schedule=effective,normalization_evidence=evidence,
        input_reference=INPUT,target_reference=TARGET,independent_target_audit_reference=TARGET_AUDIT)


def restored_ledger(raw,columns,labels):
    result=copy.deepcopy(raw)
    for decision in result['decisions']:
        for sid,row in decision['targets'].items():
            if row['ticker']!=columns[sid]:raise ValueError('Raw decision internal label differs')
            row['ticker']=labels[sid]['ticker']
    for row in result['trades']:
        sid=row['security_id']
        if row['ticker']!=columns[sid]:raise ValueError('Raw trade internal label differs')
        row['ticker']=labels[sid]['ticker']
    for row in result['daily']:
        if row['tickers']!={s:columns[s] for s in row['shares']}:raise ValueError('Raw daily internal labels differ')
        row['tickers']={s:labels[s]['ticker'] for s in row['shares']}
    return result


def inspect(account,raw,started,state,sources,partition,recovery=None):
    track=state['track'];selected=state['selected'];sealed_state=dict(state,historical_expected_source_hashes=sources,archive_resolution=partition)
    prepared=digest(sealed_state)
    marker=dict(schema='HISTORICAL_SINGLE_WINDOW_ACCOUNT_ATTEMPT_V1',track=track,attempt_count=1,prepared_sha256=prepared,
        input_reference=INPUT,target_reference=TARGET,independent_target_audit_reference=TARGET_AUDIT)
    if not exact(started,marker):raise ValueError('Exact one-shot prepared attempt required')
    expected_raw=dict(schema='HISTORICAL_SINGLE_WINDOW_RAW_EXECUTION_V1',track=track,execution=raw['execution'],started_reference=account['started_reference'],
        original_schedule=selected['original_schedule'],internal_columns=selected['columns'],calendar=state['calendar'],execution_contract=CONTRACT,
        independent_accounting_completed=False,**dict.fromkeys(ACCOUNT_FALSE,False))
    if not exact(raw,expected_raw):raise ValueError('Complete raw receipt metadata differs')
    execution=restored_ledger(raw['execution'],selected['columns'],selected['labels'])
    if not exact(execution,account['execution']):raise ValueError('Saved account differs beyond ticker restoration')
    if (track=='incumbent')!=(recovery is not None):raise ValueError('Incumbent requires explicit raw-only recovery lineage')
    oracle=candidate_oracle if track=='candidate' else control_oracle_v2
    audit=oracle.audit(execution=execution,calendar=state['calendar'],schedule=state['effective_schedule'],prices=selected['prices'],
        risk_chains_by_decision=selected['arguments']['risk_chains_by_decision'],contract=CONTRACT)
    expected=dict(schema='HISTORICAL_SINGLE_WINDOW_CONDITIONAL_ACCOUNT_V1',track=track,execution=execution,independent_decimal_accounting=audit,
        calendar=state['calendar'],schedule=selected['original_schedule'],effective_schedule=state['effective_schedule'],normalization_evidence=state['normalization_evidence'],
        execution_contract=CONTRACT,internal_columns=selected['columns'],input_reference=INPUT,target_reference=TARGET,independent_target_audit_reference=TARGET_AUDIT,
        started_reference=account['started_reference'],raw_execution_reference=account['raw_execution_reference'],historical_expected_source_hashes=sources,archive_resolution=partition,
        prepared_sha256=prepared,execution_performed=True,risk_is_order_gate=track=='candidate',scope='CONDITIONAL_HISTORICAL_MECHANICAL_STRUCTURE_NOT_WINNER',**dict.fromkeys(ACCOUNT_FALSE,False))
    if recovery is not None:
        expected.update(schema='HISTORICAL_SINGLE_WINDOW_CONDITIONAL_ACCOUNT_RAW_RECOVERY_V2',original_execution_source_hashes=sources,
            recovery_failure_reference=CONTROL_REFS['failure'],read_only_raw_recovery=True,execution_replayed=False,
            historical_expected_source_hashes=recovery['sources'],archive_resolution=recovery['partition'])
    if not exact(account,expected):raise ValueError('Complete account/scope/source/independent audit differs')
    return audit


def owner_sources(inputs,target,audit):
    # Explicit producer imports and frozen engine direct dependencies; do not import either engine.
    paths=['backtest/'+name+'.py' for name in ('ndx_conditional_single_window_account_arguments_research','ndx_dynamic_frozen_execution_research',
        'ndx_dynamic_frozen_incumbent_control','ndx_dynamic_whole_lot_path','ndx_dynamic_whole_lot_repair_path','ndx_whole_lot_repair_diagnostic','ndx_split_accounting_research')]
    result={str(OWNER):OWNER_SHA}
    for path in paths:
        p=(ROOT/path).resolve();archive.merge(result,{str(p):hashlib.sha256(p.read_bytes()).hexdigest()})
    for module in (candidate_oracle,control_oracle,normalization,target_reader):
        p=Path(module.__file__).resolve();archive.merge(result,{str(p):LOADED[str(p)]})
    archive.merge(result,{str(archive.SOURCE):LOADED[str(archive.SOURCE)],str(archive.drift.SOURCE):LOADED[str(archive.drift.SOURCE)],str(Path(publish.__code__.co_filename).resolve()):LOADED[str(Path(publish.__code__.co_filename).resolve())]})
    archive.merge(result,target_reader.LOADED)
    for ref,value in ((INPUT,inputs),(TARGET,target),(TARGET_AUDIT,audit)):
        archive.merge(result,{ref['path']:ref['sha256']});archive.merge(result,value['historical_expected_source_hashes'])
    return result


def check_original_failure(failure):
    expected=dict(schema='HISTORICAL_SINGLE_WINDOW_FAILED_ATTEMPT_V1',track='incumbent',started_reference=CONTROL_REFS['started'],
        raw_execution_reference=CONTROL_REFS['raw'],engine_call_started=True,error_type='ValueError',automatic_retry_allowed=False,
        failure_is_economic_infeasibility=False,**dict.fromkeys(ACCOUNT_FALSE,False))
    if not exact(failure,expected):raise ValueError('Exact original non-economic failure evidence required')


def build():
    if any(v is None for v in ACCOUNT_SHA.values()) or RECOVERY_SOURCE_SHA is None or CONTROL_V2_SHA is None:raise ValueError('Await both sealed actual accounts; never execute here')
    if LOADED[str(Path(metrics.__file__).resolve())]!=METRICS_SHA or LOADED[str(Path(target_reader.__file__).resolve())]!=TARGET_READER_SHA:raise ValueError('Sealed independent dependency differs')
    sources=dict(LOADED);inputs=read(INPUT,sources);target=read(TARGET,sources);audit=read(TARGET_AUDIT,sources)
    if audit['schema']!='HISTORICAL_SINGLE_TARGET_INDEPENDENT_READBACK_V1' or audit['target_reference']!=TARGET:raise ValueError('Hard target audit reference differs')
    expected_sources=owner_sources(inputs,target,audit);archive.merge(sources,expected_sources)
    contract=archive.load_contract();partition=archive.verify_expected_sources(expected_sources,contract)
    accounts={};details={};refs={}
    for track in ('candidate','incumbent'):
        folder=ACCOUNT_BASE/track;ref=dict(path=str(folder/'account.json') if track=='candidate' else str(RECOVERY_PATH),sha256=ACCOUNT_SHA[track]);refs[track]=ref
        value=read(ref,sources)
        for key,name in (('started_reference','started.json'),('raw_execution_reference','raw_execution.json')):
            if value[key]['path']!=str(folder/name):raise ValueError('Exact isolated attempt directory required')
        started=read(value['started_reference'],sources);raw=read(value['raw_execution_reference'],sources)
        recovery=None
        if track=='incumbent':
            if not exact(value['raw_execution_reference'],CONTROL_REFS['raw']) or not exact(value['started_reference'],CONTROL_REFS['started']) or not exact(value['recovery_failure_reference'],CONTROL_REFS['failure']):raise ValueError('Hard failed attempt/raw recovery lineage differs')
            failure=read(CONTROL_REFS['failure'],sources)
            check_original_failure(failure)
            recovery_sources=dict(expected_sources)
            archive.merge(recovery_sources,{str(RECOVERY_SOURCE):RECOVERY_SOURCE_SHA,str(Path(control_oracle_v2.__file__).resolve()):CONTROL_V2_SHA})
            for original in CONTROL_REFS.values():archive.merge(recovery_sources,{original['path']:original['sha256']})
            archive.merge(sources,recovery_sources)
            recovery=dict(sources=recovery_sources,partition=archive.verify_expected_sources(recovery_sources,contract))
        state=reconstruct(inputs,target,track);details[track]=inspect(value,raw,started,state,expected_sources,partition,recovery);accounts[track]=value
    nav_paths=[p for p,h in inputs['historical_expected_source_hashes'].items() if h==NAV_SHA]
    if len(nav_paths)!=1:raise ValueError('Unique original NAV bytes required')
    nav_ref=dict(path=nav_paths[0],sha256=NAV_SHA);nav_bytes=Path(nav_ref['path']).read_bytes()
    if hashlib.sha256(nav_bytes).hexdigest()!=NAV_SHA:raise ValueError('Original NAV bytes changed')
    archive.merge(sources,{nav_ref['path']:NAV_SHA})
    compared=metrics.compare(calendar=accounts['candidate']['calendar'],candidate_daily=accounts['candidate']['execution']['daily'],incumbent_daily=accounts['incumbent']['execution']['daily'],nav_csv=nav_bytes.decode('utf-8-sig'))
    if not exact(compared['nav']['rows'],inputs['target_012922']['rows'][126:]):raise ValueError('Independent past-only NAV map differs from hard input')
    return dict(schema='HISTORICAL_SINGLE_WINDOW_ACCOUNT_COMPARISON_V1',account_references=refs,input_reference=INPUT,target_reference=TARGET,independent_target_audit_reference=TARGET_AUDIT,
        nav_reference=nav_ref,independent_accounting=details,comparison=compared,raw_only_ticker_restoration_verified=True,
        historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,contract),**dict.fromkeys(FALSE,False))


def verify(value):
    if not exact(value,build()):raise ValueError('Complete independent comparison differs')


def publish_verified(path,value):
    verify(value);saved=publish(path,value)
    if not exact(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution']):raise ValueError('Source drift after publication')
    return saved


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(publish_verified(a.output,build())))
