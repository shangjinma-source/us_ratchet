"""V2 canonical-column account after sealed pre-loop v1 failure; one new attempt."""
import argparse
from copy import deepcopy
from decimal import Decimal, Context, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import numpy as np
import pandas as pd
import scipy

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_dynamic_frozen_execution_research as engine
from backtest import ndx_frozen_accounting_independent_audit_research as independent
from backtest import ndx_frozen_target_normalization_audit_research as normalization
from backtest import ndx_root_price_archive_contract_research as archive

BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'return_six_period_conditional_execution_20260923_v2'
SOURCE=Path(__file__).resolve()
PRIOR_SOURCE=ROOT/'scripts/ndx_return_six_period_conditional_execution_20260923.py'
PRIOR_SOURCE_SHA='103cbf56bf665a54a942257ffc28f542121ae0777d6ce2b988146ad08715f0d4'
BOUND={
 'v1_started':('return_six_period_conditional_execution_20260923_v1/started.json','dd2ad9f804eca0cbf6bc866b68eb21d645dad38e33e611d1bd6d7ace2d23b886'),
 'v1_failure':('return_six_period_conditional_execution_20260923_v1/failure.json','6a594080e9dfb35584b11a22aa00513eaf049d564d42bdf27f42e65e693550f3'),
 'schedule':('return_lane_targets_20260923_v1/schedule.json','f5ee54df3651882791e4e6ecac548d0ec7847c44a9c551938d20c17c2cb23c70'),
 'audit':('return_lane_targets_20260923_v1/completed6_independent_readback.json','ca8bf38f5090c9703da2ed8094421d3abae4324fd7837097f82ef0546b94778f'),
 'linkage':('return_lane_targets_20260923_v1/schedule_independent_linkage.json','f1529817338a022bb9831de9e4d08407a7eb7015098e085e43ea37506ac8ed0b'),
 'price':('return_eight_price_only_20260923_v1/raw_assembly.json','e1f00af594bfcb9a9c75b02493cf62fc64622e0b280ba2774346832b530b7336'),
 'price_final':('return_eight_price_only_20260923_v1/finalization.json','5f5714e66b906d02c33006e7b556177cd20945c0afca0a4d400df4e2073e2b9a'),
 'identity':('return_eight_conditional_identity_20260923_v1/identities.json','5f5bcbad2f5a3a340e0b3449b4b78ed55a44941d6402a4ee067dd779a4abaa6e'),
}
FROZEN={
 'ndx_dynamic_frozen_execution_research.py':'69d2bf761eac32edd8c39a9fdbffed300ba7cb4740771fbd008b4f09b204813b',
 'ndx_dynamic_whole_lot_path.py':'3ad63f1e59baaa14c32eceddd32340755a516c1022077bd802763d10ef360a95',
 'ndx_dynamic_whole_lot_repair_path.py':'e614be1a2fe461e483e17413af03153f9a2fe99c31e0412b5daa8954c53d3f34',
 'ndx_whole_lot_repair_diagnostic.py':'e2f00388b92c88588acaff51c30c608830bf93a00cfc6a84ad8e20a9470381bf',
 'ndx_split_accounting_research.py':'11bb5225e90c76fe303e90fa9f639e34c3978fd922d230bb2a45f8f9ad24877c',
 'ndx_frozen_accounting_independent_audit_research.py':'3fb63dbf58e94eb92fd93bf39cca8fdefe52fdb4853bf9abd7d63a0a391fe7dc',
 'ndx_frozen_target_normalization_audit_research.py':'32c9fd773a35465152f567ca1f3c314d3663191f2a8e53a41a1ce6dafe39ce2f',
}
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
    (SOURCE,Path(independent.__file__).resolve(),Path(normalization.__file__).resolve(),archive.SOURCE,Path(archive.drift.__file__).resolve())}
archive.merge(LOADED,engine._LOADED_SOURCES)
RUNTIME_FILES=[Path(sys.executable).resolve(),*(Path(m.__file__).resolve() for m in (np,pd,scipy))]
RUNTIME_LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in RUNTIME_FILES}
CLOCK=[('2023-03-31','2023-04-03'),('2023-04-28','2023-05-01'),('2023-05-31','2023-06-01'),
       ('2023-06-30','2023-07-03'),('2023-07-31','2023-08-01'),('2023-08-31','2023-09-01')]
CONTRACT=dict(initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10,
    max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
SCHEMA='RETURN_SIX_PERIOD_CONDITIONAL_ACCOUNT_V2'
FALSE_FLAGS=dict.fromkeys(('fit_performed','point_in_time_verified','promotion_allowed','live_execution_authorized',
    'provider_binding_verified','continuous_identity_interval_verified','corporate_action_completeness_verified',
    'dividend_cash_flows_modelled','additional_cash_flows_supported','historical_full_source_closure_recovered'),False)


def require(condition,message):
    if not condition:raise ValueError(message)


def encoded(value):
    return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def exact(a,b):return encoded(a)==encoded(b)


def reference(role):
    path,sha=BOUND[role];return dict(path=str(BASE/path),sha256=sha)


def read(ref):
    raw=Path(ref['path']).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==ref['sha256'],'External reference bytes differ')
    return json.loads(raw)


def runtime():
    archive.strict(RUNTIME_LOADED)
    return dict(python=platform.python_version(),executable=str(Path(sys.executable).resolve()),
        numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__,runtime_entry_file_hashes=RUNTIME_LOADED,
        full_binary_dependency_closure_verified=False)


def assemble(target,price,identities):
    require(target['schema']=='RETURN_SIX_PERIOD_STRATEGIC_TARGET_SCHEDULE_V1' and
        price['schema']=='RETURN_EIGHT_107_OBSERVED_SESSION_CONDITIONAL_PRICE_ONLY_V1' and
        identities['schema']=='RETURN_EIGHT_CONDITIONAL_IDENTITY_ASSEMBLY_V1','Exact new input schemas required')
    require(target['promotion_allowed'] is False and target['member_point_in_time_verified'] is False and
        target['whole_lot_execution_performed'] is False and target['all_six_targets_passed'] is True,'Target scope differs')
    for document in (price,identities):
        require(document['point_in_time_verified'] is False and document['promotion_allowed'] is False,'Conditional scope differs')
    require(identities['conditional_window']==dict(start='2023-03-31',end='2023-09-01') and
        identities['continuous_identity_interval_verified'] is False and identities['provider_price_binding_verified'] is False,
        'Explicit conditional identity interval required')
    labels={r['security_id']:r for r in identities['rows']}
    require(len(labels)==len(identities['rows'])==8 and len({r['issuer_id'] for r in labels.values()})==7,'Eight SID and seven issuer denominator required')
    require({r['ticker'] for r in labels.values()}==set(price['tickers']) and len(price['tickers'])==8,'Price identity union differs')
    calendar=price['calendar'];schedule=deepcopy(target['schedule'])
    require(len(calendar)==107 and calendar==sorted(set(calendar)) and calendar==[d for d in target['calendar'] if '2023-03-31'<=d<='2023-09-01'] and
        [(r['decision_date'],r['execution_date']) for r in schedule]==CLOCK,'Exact 107-day six-decision clock required')
    require(set().union(*(r['targets'] for r in schedule))==set(labels),'Complete target SID union required')
    chains=target['risk_chains_by_decision']
    require(set(chains)=={a for a,b in CLOCK},'Complete risk-chain decision denominator required')
    for row in schedule:
        require(calendar[calendar.index(row['decision_date'])+1]==row['execution_date'],'Next observed Open required')
        require(set(chains[row['decision_date']])==set(row['targets']),'Exact decision risk identities required')
        require(len({v['issuer_id'] for v in row['targets'].values()})==len(row['targets']),'Multiple classes of one issuer in target')
        for sid,value in row['targets'].items():
            require(value['ticker']==labels[sid]['ticker'] and value['issuer_id']==labels[sid]['issuer_id'],'Target identity contradiction')
    columns={sid:'SID_'+sid.split(':')[1]+'_'+sid.split(':')[2] for sid in labels}
    require(len(set(columns.values()))==8,'Distinct internal security columns required')
    marks={d:{} for d in calendar};frames={};conversion=[]
    require(price['price_cell_count']==1712 and price['session_count']==107 and price['ticker_count']==8,'Price denominator differs')
    for kind in ('open','close'):
        require(set(price['matrices'][kind])==set(calendar),'Price dates differ')
        for day in calendar:
            require(set(price['matrices'][kind][day])==set(price['tickers']),'Missing price identity')
            for sid,label in labels.items():
                raw=price['matrices'][kind][day][label['ticker']]
                require(type(raw) is str,'Exact Decimal string price required')
                value=Decimal(raw)
                require(value.is_finite() and value>0 and math.isfinite(float(value)) and float(value)>0,'Positive finite price required')
                marks[day].setdefault(sid,dict(ticker=label['ticker']))[kind]=value
                with localcontext(Context(prec=160)):
                    error=abs(Decimal.from_float(float(value))-value)
                conversion.append(dict(session=day,security_id=sid,field=kind,original_decimal=raw,
                    execution_float=float(value),absolute_binary_float_error=str(error)))
        frames[kind]=pd.DataFrame({columns[sid]:[float(marks[d][sid][kind]) for d in calendar] for sid in labels},index=pd.DatetimeIndex(calendar))
    translated=deepcopy(schedule)
    for row in translated:
        for sid,value in row['targets'].items():value['ticker']=columns[sid]
    normalized,evidence=normalization.normalized_schedule(schedule)
    arguments=dict(opens=frames['open'],closes=frames['close'],schedule=translated,risk_chains_by_decision=deepcopy(chains),
        corporate_actions=[],identity_events=[],valuation_end_date=calendar[-1],max_repair_evaluations=262144,**CONTRACT)
    validation=validate_engine_inputs(arguments)
    return dict(arguments=arguments,calendar=calendar,schedule=schedule,normalized=normalized,normalization_evidence=evidence,
        prices=marks,contract=deepcopy(CONTRACT),columns=columns,labels=labels,
        engine_input_validation=validation,
        price_conversion_evidence=dict(policy='EXPLICIT_FLOAT_ONLY_AT_FROZEN_ENGINE_BOUNDARY_DECIMAL_MARKS_RETAINED_FOR_INDEPENDENT_AUDIT',
            cell_count=len(conversion),cells=conversion))


def validate_engine_inputs(arguments):
    """Run frozen cheap validators on copies, never simulate or mutate submitted targets."""
    engine._check_sources()
    opens=arguments['opens'];closes=arguments['closes'];repair=engine.repair
    repair._strict_price_index(closes,'closes');repair._strict_price_index(opens,'opens')
    require(closes.index.equals(opens.index),'Open/Close calendars differ')
    require(closes.columns.equals(opens.columns),'Open/Close security columns differ')
    rows=deepcopy(arguments['schedule'])
    for row in rows:
        repair._strict_session_date(row['decision_date'],'decision_date')
        repair._strict_session_date(row['execution_date'],'execution_date')
        for sid,target in row['targets'].items():
            require(all(type(v) is str and v and v==v.strip() for v in (sid,target['issuer_id'],target['ticker']))
                and target['ticker']==target['ticker'].upper(),'Canonical engine target identities required')
            repair._finite(target['target_weight'],'target_weight')
    items=engine.identity._normalise_schedule(rows)
    engine.identity._validate_schedule_identity_and_execution_guards(items,valuation_prices=closes,
        separate_execution_prices_supplied=True,require_separate_execution_prices=True,
        require_next_session_execution=True,require_issuer_trace=True)
    contract=repair._normalise_contract(items,risk_chains_by_decision=arguments['risk_chains_by_decision'],
        max_repair_evaluations=arguments['max_repair_evaluations'],**{key:arguments[key] for key in CONTRACT})
    end=repair._strict_session_date(arguments['valuation_end_date'],'valuation_end_date')
    require(items[0]['decision_date'] in closes.index and end in closes.index and end>=items[-1]['execution_date'] and
        all(item['decision_date'] in closes.index for item in items),'Explicit engine interval differs')
    require(type(arguments['corporate_actions']) in (list,tuple) and not arguments['corporate_actions'] and
        type(arguments['identity_events']) in (list,tuple) and not arguments['identity_events'],'Action-free conditional contract required')
    observed={}
    for item in items:
        for sid,target in item['targets'].items():
            require(sid not in observed or observed[sid]==target['ticker'],'Unexpected security rename')
            observed[sid]=target['ticker']
    for frame in (opens,closes):
        require(np.isfinite(frame.to_numpy(dtype=float)).all() and (frame.to_numpy(dtype=float)>0).all(),'Finite positive engine price matrix required')
    return dict(frozen_price_index_validators_called=True,frozen_schedule_and_contract_validators_called=True,
        normalized_copy_discarded=True,submitted_schedule_modified=False,simulate_called=False,
        session_count=len(closes),security_column_count=len(closes.columns),decision_count=len(items))


def prepare():
    for name,sha in FROZEN.items():
        require(LOADED.get(str(ROOT/'backtest'/name))==sha,'Frozen loaded engine/audit source differs')
    archive.strict(LOADED);archive.strict({str(PRIOR_SOURCE):PRIOR_SOURCE_SHA})
    docs={role:read(reference(role)) for role in BOUND};sources=dict(LOADED)
    for role,doc in docs.items():
        ref=reference(role);archive.merge(sources,{ref['path']:ref['sha256']})
        for key in ('source_hashes','historical_expected_source_hashes'):
            if key in doc:archive.merge(sources,doc[key])
    archive.merge(sources,{str(PRIOR_SOURCE):PRIOR_SOURCE_SHA})
    failure=docs['v1_failure'];started=docs['v1_started']
    require(failure['schema']=='RETURN_SIX_PERIOD_CONDITIONAL_ACCOUNT_V1_FAILURE' and
        failure['started_reference']==reference('v1_started') and failure['raw_reference'] is None and
        failure['engine_call_started'] is True and failure['automatic_retry_allowed'] is False and
        failure['numerical_failure_is_economic_infeasibility'] is False and
        failure['error_type']=='NdxDynamicWholeLotRepairPathError' and
        failure['error']=='closes ticker columns must be canonical, nonempty, and unique',
        'Exact sealed pre-loop v1 failure required')
    require(started['schema']=='RETURN_SIX_PERIOD_CONDITIONAL_ACCOUNT_V1_STARTED' and
        started['source_hashes'].get(str(PRIOR_SOURCE))==PRIOR_SOURCE_SHA,'Exact frozen v1 source lineage required')
    require({p.name for p in (BASE/BOUND['v1_failure'][0]).parent.iterdir()}=={'started.json','failure.json'},
        'V1 must remain one failed attempt without raw or completed ledger')
    audit=docs['audit'];linkage=docs['linkage'];final=docs['price_final']
    require(audit['status']=='PASSED' and audit['completed_prefix_count']==6 and len(audit['details'])==6,'Complete independent target audit required')
    require(linkage['exact_schedule_reconstruction'] is True and linkage['schedule_reference']==reference('schedule') and
        linkage['independent_target_audit_reference']==reference('audit'),'Exact independent schedule linkage required')
    require(final['raw_reference']==reference('price') and final['status']=='CONDITIONAL_RAW_PRICE_RECONSTRUCTION_PASSED','Price final/raw linkage differs')
    require(docs['identity']['source_references']['schedule']==reference('schedule') and
        docs['identity']['source_references']['linkage']==reference('linkage'),'Identity schedule linkage differs')
    prepared=assemble(docs['schedule'],docs['price'],docs['identity'])
    contract=archive.load_contract();resolution=archive.verify_expected_sources(sources,contract)
    return dict(prepared=prepared,sources=sources,archive_contract=contract,resolution=resolution,runtime=runtime())


def check(state):
    require(runtime()==state['runtime'],'Numerical runtime differs')
    require(archive.verify_expected_sources(state['sources'],state['archive_contract'])==state['resolution'],'Source resolution changed')
    require({p.name for p in (BASE/BOUND['v1_failure'][0]).parent.iterdir()}=={'started.json','failure.json'},'V1 evidence directory changed')


def restore_and_audit(raw,prepared):
    result=deepcopy(raw);labels=prepared['labels'];columns=prepared['columns']
    for row in result['decisions']:
        for sid,value in row['targets'].items():
            require(value['ticker']==columns[sid],'Internal target column differs');value['ticker']=labels[sid]['ticker']
    for row in result['trades']:
        sid=row['security_id'];require(row['ticker']==columns[sid],'Internal trade column differs');row['ticker']=labels[sid]['ticker']
    for row in result['daily']:
        require(row['tickers']=={sid:columns[sid] for sid in row['shares']},'Internal daily columns differ')
        row['tickers']={sid:labels[sid]['ticker'] for sid in row['shares']}
    with localcontext(Context(prec=80)):
        audit=independent.audit(execution=result,calendar=prepared['calendar'],schedule=prepared['normalized'],prices=prepared['prices'],
            risk_chains_by_decision=prepared['arguments']['risk_chains_by_decision'],contract=prepared['contract'])
    return result,audit


def publish(path,value):
    raw=encoded(value)
    with Path(path).open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    require(Path(path).read_bytes()==raw,'Publication readback differs')
    return dict(path=str(Path(path).resolve()),sha256=hashlib.sha256(raw).hexdigest())


def started_value(state):
    p=state['prepared']
    return dict(schema=SCHEMA+'_STARTED',source_hashes=state['sources'],runtime=state['runtime'],
        input_references={role:reference(role) for role in BOUND},calendar=p['calendar'],schedule=p['schedule'],
        internal_columns=p['columns'],execution_contract=p['contract'],normalization_evidence=p['normalization_evidence'],
        price_conversion_evidence=p['price_conversion_evidence'],
        engine_input_validation=p['engine_input_validation'],
        historical_v1_engine_attempt_count=1,historical_v1_complete_ledger_count=0,
        automatic_retry_allowed=False,**FALSE_FLAGS)


def raw_value(state,started,execution):
    return dict(schema=SCHEMA+'_RAW',execution=execution,started_reference=started,
        engine_call_count=1,runtime=state['runtime'],source_hashes=state['sources'],**FALSE_FLAGS)


def evidence_directory(output,expected):
    require({p.name for p in output.iterdir()}==set(expected) and all((output/name).is_file() for name in expected),
        'Unexpected/orphan attempt evidence')


def finalize(state,started,raw_ref,output,failure=None):
    names={'started.json','raw_execution.json'}|({'failure.json'} if failure else set())
    evidence_directory(output,names)
    check(state);require(exact(read(started),started_value(state)),'Started envelope differs')
    raw=read(raw_ref)
    require(exact(raw,raw_value(state,started,raw['execution'])),'Raw attempt envelope differs')
    if failure:
        saved_failure=read(failure)
        require(type(saved_failure['error_type']) is str and type(saved_failure['error']) is str and
            exact(saved_failure,dict(schema=SCHEMA+'_FAILURE',started_reference=started,raw_reference=raw_ref,
                engine_call_started=True,error_type=saved_failure['error_type'],error=saved_failure['error'],
                automatic_retry_allowed=False,numerical_failure_is_economic_infeasibility=False,**FALSE_FLAGS)),
            'Failure evidence does not belong to the saved raw attempt')
    execution,audit=restore_and_audit(raw['execution'],state['prepared'])
    check(state);read(started);read(raw_ref);evidence_directory(output,names)
    if failure:read(failure)
    p=state['prepared']
    value=dict(schema=SCHEMA,status='INDEPENDENT_ACCOUNTING_PASSED',execution=execution,independent_decimal_accounting=audit,
        calendar=p['calendar'],schedule=p['schedule'],normalized_schedule=p['normalized'],normalization_evidence=p['normalization_evidence'],
        execution_contract=p['contract'],internal_columns=p['columns'],security_count=8,distinct_issuer_count=7,
        price_conversion_evidence=p['price_conversion_evidence'],
        engine_input_validation=p['engine_input_validation'],
        historical_v1_engine_attempt_count=1,historical_v1_complete_ledger_count=0,
        per_decision_target_counts=[len(r['targets']) for r in p['schedule']],fixed_four_security_policy=False,
        goog_googl_relationship='DIFFERENT_SECURITY_IDS_SAME_ISSUER_NOT_A_RENAME',
        started_reference=started,raw_reference=raw_ref,recovered_failure_reference=failure,source_hashes=state['sources'],runtime=state['runtime'],
        archive_resolution=state['resolution'],engine_call_count=1,execution_performed=True,**FALSE_FLAGS)
    saved=publish(output/'account.json',value);check(state);read(started);read(raw_ref);read(saved)
    evidence_directory(output,names|{'account.json'})
    if failure:read(failure)
    return saved


def run(output=OUTPUT,execute=False):
    require(type(execute) is bool,'Explicit boolean execute required')
    output=Path(output).resolve();require(output==OUTPUT.resolve(),'Hard single-attempt namespace required')
    require(not output.exists(),'Fresh single-attempt namespace required')
    state=prepare();check(state)
    if not execute:return dict(prepare_completed=True,execution_performed=False,session_count=107,decision_count=6,security_count=8,distinct_issuer_count=7,
        engine_input_validation=state['prepared']['engine_input_validation'],historical_v1_engine_attempt_count=1,historical_v1_complete_ledger_count=0,**FALSE_FLAGS)
    output.mkdir(parents=True,exist_ok=False)
    started=publish(output/'started.json',started_value(state));raw_ref=None;called=False
    try:
        check(state);read(started);evidence_directory(output,{'started.json'});called=True
        execution=engine.simulate_dynamic_frozen_execution_research(**deepcopy(state['prepared']['arguments']))
        raw_ref=publish(output/'raw_execution.json',raw_value(state,started,execution))
        return finalize(state,started,raw_ref,output)
    except Exception as error:
        publish(output/'failure.json',dict(schema=SCHEMA+'_FAILURE',started_reference=started,raw_reference=raw_ref,
            engine_call_started=called,error_type=type(error).__name__,error=str(error),automatic_retry_allowed=False,
            numerical_failure_is_economic_infeasibility=False,**FALSE_FLAGS))
        raise


def recover(output,started_sha256,raw_sha256):
    """Only audit an externally pinned saved ledger; this never invokes the engine."""
    output=Path(output).resolve()
    require(output==OUTPUT.resolve(),'Hard single-attempt namespace required')
    require(bool(started_sha256) and bool(raw_sha256),'External started and raw SHA required')
    require({p.name for p in output.iterdir()} in ({'started.json','raw_execution.json'},
        {'started.json','raw_execution.json','failure.json'}),'Exact recoverable evidence directory required')
    state=prepare();started=dict(path=str(output/'started.json'),sha256=started_sha256)
    raw=dict(path=str(output/'raw_execution.json'),sha256=raw_sha256)
    failure_path=output/'failure.json'
    failure=dict(path=str(failure_path),sha256=hashlib.sha256(failure_path.read_bytes()).hexdigest()) if failure_path.exists() else None
    return finalize(state,started,raw,output,failure)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default=str(OUTPUT))
    parser.add_argument('--execute',action='store_true');parser.add_argument('--recover',action='store_true')
    parser.add_argument('--started-sha256');parser.add_argument('--raw-sha256');args=parser.parse_args()
    if args.recover:
        require(not args.execute,'Recovery cannot execute')
        result=recover(args.output,args.started_sha256,args.raw_sha256)
    else:
        require(not args.started_sha256 and not args.raw_sha256,'Unexpected recovery references')
        result=run(args.output,args.execute)
    print(json.dumps(result))
