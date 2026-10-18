"""Independent two-period typed-matrix, strategic-anchor and Decimal-risk readback.

Never calls the path producer, schedule validator, optimizer or execution engine.
"""
import argparse
from copy import deepcopy
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sys
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from backtest import ndx_delta_selected_input_research as typed
from scripts.ndx_base_three_cell_window_delta_research import publish

BASE=ROOT/'data/cache/research'
PATH=dict(path=str(BASE/'corrected_explicit_path_20260919_v1/path.json'),sha256='97145090fe6056b4594963877d96370cbf754c074daafb8c9b5421213daa6254')
CALENDAR=dict(path=str(BASE/'corrected_explicit_path_20260919_v1/calendar.json'),sha256='57ac5d3187c656694a5351fda4cde7ce4331f9e471bcfc8881930c8b9984fa1c')
SEED=dict(path=str(BASE/'corrected_frontier_cutoff_archive_20260919_v1/20230403_first_non_equal_refit.json'),sha256='4d6846dfe7283716985ac663ff42a7409320c53c51e28b4b694af71e33231df0')
OBJECTIVE=dict(path=str(ROOT/'config/ndx_portfolio_objective_v2.yaml'),sha256='4f299d67a96204c9da605d3d326b723e3ab88d31926702128000c176ea316c7d')
CORRECTIONS=(('GOOG','2022-07-18',-.025335378898117544),('GOOGL','2022-07-18',-.024580059928059006),('FTNT','2022-06-23',.019968386675822902))
LOADED={str(p):archive.drift.file_sha(p) for p in (Path(__file__).resolve(),archive.SOURCE,Path(typed.__file__).resolve(),Path(publish.__code__.co_filename).resolve())}
for function in (typed._restore_input,typed.provenance._digest):
    p=Path(function.__code__.co_filename).resolve();archive.merge(LOADED,{str(p):archive.drift.file_sha(p)})
PRODUCER_SOURCES={str(p):archive.drift.file_sha(p) for p in (ROOT/'backtest/ndx_corrected_explicit_path_research.py',ROOT/'scripts/ndx_corrected_explicit_path_runner_research.py')}
archive.merge(LOADED,PRODUCER_SOURCES)
SCHEDULE_SOURCE=ROOT/'backtest/ndx_dynamic_refit_schedule_research.py'
PERIOD_SOURCE_PATHS=(ROOT/'backtest/ndx_corrected_cutoff_snapshot_research.py',ROOT/'scripts/ndx_corrected_frontier_single_refit_archive_research.py')
for p in (*PERIOD_SOURCE_PATHS,SCHEDULE_SOURCE):archive.merge(LOADED,{str(p):archive.drift.file_sha(p)})
FALSE=('checkpoint_weights_used','point_in_time_verified','promotion_allowed','source_authenticity_verified','historical_task_evaluation_performed','order_generation_allowed')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def schedule_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def exact(left,right):
    if digest(left)!=digest(right):raise ValueError('Exact bound value differs')


def number(value):
    if type(value) not in (int,float):raise ValueError('Nonboolean numeric value required')
    result=Decimal(str(value))
    if not result.is_finite():raise ValueError('Finite value required')
    return result


def read(reference,sources):
    path=str(Path(reference['path']).resolve());raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('External artifact bytes differ')
    archive.merge(sources,{path:reference['sha256']})
    return json.loads(raw)


def verify_gaps(gaps):
    for row in gaps:
        if row['original_pointer_preserved'] is not True or row['used_as_current_numerical_input'] is not False or archive.drift.file_sha(row['path'])!=row['observed_current_sha256']:
            raise ValueError('Historical loader observation changed')


def corrected_inputs(context,binding):
    original=context['prepared_inputs'];exact(digest(original),binding['original_typed_inputs_sha256'])
    encoded=deepcopy(original)
    values={k:typed._restore_input(v) for k,v in original.items()}
    exact(typed.provenance._digest(values),binding['original_decoded_inputs_sha256'])
    for ticker,day,after in CORRECTIONS:
        frame=values['returns'];column=list(frame.columns).index(ticker);position=list(frame.index).index(typed.pd.Timestamp(day))
        cell=encoded['returns']['payload']['mapping']['column_values']['items'][column]['items'][position]
        if set(cell)!={'float_hex'} or float.fromhex(cell['float_hex'])!=0.:raise ValueError('Original correction cell differs')
        cell['float_hex']=after.hex()
    exact(digest(encoded),binding['corrected_typed_inputs_sha256'])
    changed={k:typed._restore_input(v) for k,v in encoded.items()}
    exact(typed.provenance._digest(changed),binding['corrected_decoded_inputs_sha256'])
    return changed


def inspect_period(*,fitted,selected,parameters,returns,cutoff,previous,weight_spec):
    if fitted['schema']!='ndx_dynamic_cutoff_refit_research_v2' or any(fitted[k] is not False for k in FALSE):raise ValueError('Cutoff result scope differs')
    exact(fitted['previous_target_weights'],previous or {})
    exact(fitted['declared_parameters'],{k:float(v) for k,v in parameters.items() if k!='fit_days'})
    if fitted['weight_spec']!=weight_spec or set(fitted['targets'])!=set(selected):raise ValueError('Candidate specification differs')
    if fitted['anchor_policy']!='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED':raise ValueError('Strategic anchor policy differs')
    names=[selected[s]['ticker'] for s in sorted(selected)]
    frame=returns.iloc[-parameters['fit_days']:][names]
    matrix=dict(dates=[d.date().isoformat() for d in frame.index],tickers=names,returns=frame.to_numpy().tolist())
    if (type(fitted['fit_row_count']) is not int or fitted['fit_row_count']!=parameters['fit_days']
            or len(frame)!=parameters['fit_days'] or fitted['fit_start']!=matrix['dates'][0]
            or fitted['fit_end']!=cutoff or fitted['cutoff']!=cutoff or matrix['dates'][-1]!=cutoff
            or fitted['fit_data_sha256']!=digest(matrix)):
        raise ValueError('Independent corrected fit matrix differs')
    if not all(number(v).is_finite() for row in matrix['returns'] for v in row):raise ValueError('Invalid matrix')
    exact(fitted['risk_chains_by_security'],{s:v['risk_chain'] for s,v in selected.items()})
    with localcontext() as ctx:
        ctx.prec=50
        prior={s:number(w) for s,w in (previous or {}).items()}
        mass=sum((prior.get(s,Decimal(0)) for s in selected),Decimal(0))
        if abs(number(fitted['surviving_anchor_mass'])-mass)>Decimal('1e-14'):raise ValueError('Surviving strategic target mass differs')
        if set(fitted['anchor_by_security'])!=set(selected):raise ValueError('Anchor denominator differs')
        for sid in selected:
            expected=prior.get(sid,Decimal(0))/mass if mass>0 else Decimal(0)
            if abs(number(fitted['anchor_by_security'][sid])-expected)>Decimal('1e-14'):raise ValueError('Surviving/new-entry anchor differs')
        strength=number(parameters['turnover_anchor_strength']) if mass>0 and weight_spec=='constrained_fixed_shrinkage_turnover_anchor' else Decimal(0)
        if number(fitted['effective_anchor_strength'])!=strength:raise ValueError('Effective anchor strength differs')
        weights={};chains={}
        for sid,target in fitted['targets'].items():
            if set(target)!={'ticker','issuer_id','target_weight'} or any(target[k]!=selected[sid][k] for k in ('ticker','issuer_id')):raise ValueError('Target identity differs')
            w=number(target['target_weight'])
            if w<=0:raise ValueError('Positive target required')
            weights[sid]=w;chain=selected[sid]['risk_chain'];chains[chain]=chains.get(chain,Decimal(0))+w
        tolerance=Decimal('1e-9')
        if abs(sum(weights.values())-1)>tolerance:raise ValueError('Target simplex differs')
        ordered=sorted(weights.values(),reverse=True);effective=1/sum(w*w for w in ordered)
        checks=dict(MAX_SINGLE_WEIGHT=ordered[0]<=number(parameters['max_single_weight'])+tolerance,
            MIN_SINGLE_WEIGHT=ordered[-1]>=number(parameters['min_single_weight'])-tolerance,
            SECURITY_TOP3_WEIGHT=sum(ordered[:3])<=number(parameters['top_weight_cap'])+tolerance,
            MINIMUM_EFFECTIVE_N=effective>=len(weights)*number(parameters['minimum_effective_n_ratio'])-tolerance,
            RISK_CHAIN_TOP1_WEIGHT=max(chains.values())<=number(parameters['risk_chain_top1_cap'])+tolerance)
        exact(fitted['declared_constraint_checks'],checks)
        if fitted['declared_constraints_passed'] is not True or not all(checks.values()):raise ValueError('Five-risk failure cannot enter schedule')
    return dict(fit_data_sha256=digest(matrix),fit_rows=len(frame),surviving_anchor_mass=str(mass),effective_anchor_strength=str(strength),
        newly_entering_sids=sorted(set(selected)-set(prior)),exiting_sids=sorted(set(prior)-set(selected)),checks=checks,
        security_top3=str(sum(ordered[:3])),effective_n=str(effective),risk_chain_top1=str(max(chains.values())))


def build(*,result_path,result_sha256):
    sources=dict(LOADED)
    reference=dict(path=str(Path(result_path).resolve()),sha256=result_sha256)
    value=read(reference,sources);path=read(PATH,sources);calendar_doc=read(CALENDAR,sources);seed=read(SEED,sources)
    archive.merge(sources,seed['result']['historical_expected_source_hashes'])
    archive.merge(sources,seed['runner_source_hashes'])
    seed_started=read(seed['started_attempt'],sources)
    exact(seed_started,dict(schema='CORRECTED_FRONTIER_SINGLE_REFIT_ATTEMPT_V1',queue=seed['queue'],job_id=seed['job_id'],output=SEED['path'],runner_source_hashes=seed['runner_source_hashes'],status='STARTED_NOT_COMPLETED'))
    parent=read(calendar_doc['source'],sources);calendar=calendar_doc['calendar']
    exact(calendar,[r['session'] for r in parent['execution']['daily']])
    if value['schema']!='EXPLICIT_STRATEGIC_TARGET_PATH_EXECUTION_V1' or value['target_schedule_built'] is not True:raise ValueError('Complete target path wrapper required')
    for flag in ('whole_lot_execution_performed','independently_selected_winner','point_in_time_verified','promotion_allowed'):
        if value[flag] is not False:raise ValueError('Execution/admission claim upgraded')
    exact(value['path'],PATH);exact(value['calendar'],CALENDAR)
    exact(value['runner_source_hashes'],dict(PRODUCER_SOURCES,**{PATH['path']:PATH['sha256'],CALENDAR['path']:CALENDAR['sha256']}))
    archive.merge(sources,value['runner_source_hashes'])
    if value['started_attempt']['path']!=reference['path']+'.started.json':raise ValueError('Actual result attempt coordinate differs')
    started=read(value['started_attempt'],sources)
    exact(started,dict(schema='EXPLICIT_STRATEGIC_TARGET_PATH_ATTEMPT_V1',path=PATH,calendar=CALENDAR,output=reference['path'],runner_source_hashes=value['runner_source_hashes'],status='STARTED_NOT_COMPLETED'))
    result=value['result']
    if result['schema']!='CORRECTED_EXPLICIT_STRATEGIC_TARGET_PATH_V1':raise ValueError('Target path schema differs')
    exact(result['explicit_path'],path);exact(result['path_reference'],PATH);exact(result['calendar_reference'],CALENDAR)
    exact(result['original_first_seed_wrapper'],seed);exact(result['first_seed_reference'],SEED);exact(result['calendar'],calendar)
    if result['first_seed_imported_without_refit'] is not True or type(result['new_fit_count']) is not int or result['new_fit_count']!=1:raise ValueError('Exactly one new fit and unchanged seed required')
    if (type(result['decision_count']) is not int or result['decision_count']!=2
            or type(result['submitted_decision_count']) is not int or result['submitted_decision_count']!=2
            or result['submitted_decision_path_complete'] is not True or result['externally_supplied_selection_path'] is not True
            or result['whole_lot_status']!='NOT_EVALUATED'):
        raise ValueError('Complete explicit target-only denominator differs')
    for flag in ('execution_performed','order_generation_allowed','point_in_time_verified','promotion_allowed','historical_full_source_closure_verified',
                 'anchor_uses_actual_fills_or_holdings','later_execution_failure_resets_target_anchor','partial_schedule_allowed','implicit_hold_or_cash_policy_applied',
                 'downstream_execution_contract_applied','independently_selected_winner','decision_ticker_authenticity_verified','source_authenticity_verified',
                 'external_expected_decision_denominator_verified','selector_execution_performed','unique_selection_performed'):
        if result[flag] is not False:raise ValueError('Target-only strategic path scope upgraded')
    if result['target_anchor_policy']!='PREVIOUS_SUCCESSFUL_SCHEDULE_TARGET_BY_SID_REGARDLESS_OF_LATER_EXECUTION_STATUS':raise ValueError('Anchor policy differs')
    if any(len(result[k])!=2 for k in ('schedule','refits','period_bindings')):raise ValueError('Entire two-period path required')
    exact(sorted(result['risk_chains_by_decision']),sorted(p['decision_date'] for p in path['periods']))
    exact(result['calendar_sha256'],schedule_digest(calendar))
    archive.merge(sources,result['historical_expected_source_hashes'])
    contract=archive.load_contract()
    exact(archive.verify_expected_sources(result['historical_expected_source_hashes'],contract),result['archive_resolution'])
    verify_gaps(result['historical_loader_gap_observations'])
    archive.strict({OBJECTIVE['path']:OBJECTIVE['sha256']});archive.merge(sources,{OBJECTIVE['path']:OBJECTIVE['sha256']})
    objective=yaml.safe_load(Path(OBJECTIVE['path']).read_bytes())['execution_contract']
    exact(result['downstream_execution_contract_reference'],OBJECTIVE)
    for target,source in (('downstream_execution_capital_usd','starting_capital_usd'),('downstream_execution_cash_buffer_usd','minimum_cash_buffer_usd'),('downstream_execution_transaction_cost_bps','transaction_cost_bps')):exact(result[target],objective[source])
    previous=None;details=[];issuers={};expected_gaps=[];input_hashes=[];risk_contract=None
    for index,period in enumerate(path['periods']):
        queue=read(period['queue'],sources);archive.merge(sources,queue['historical_expected_source_hashes'])
        expected_gaps.extend(queue['historical_loader_gap_observations'])
        entry,=[r for r in queue['candidates'] if r['task']['job_id']==period['job_id']]
        context=read(queue['context'],sources);changed=corrected_inputs(context,queue['input_binding'])
        exact(changed['contract'],queue['original_fourteen_parameter_contract'])
        if context['runtime']!=typed.current_runtime():raise ValueError('Actual original runtime differs')
        expected_binding=dict(queue=period['queue'],job_id=period['job_id'],full_candidate=entry,input_binding=queue['input_binding'],original_fourteen_parameter_contract=queue['original_fourteen_parameter_contract'])
        exact(result['period_bindings'][index],expected_binding)
        day=period['decision_date'];execution=period['execution_date']
        if day!=period['cutoff'] or day!=queue['historical_cutoff'] or execution!=queue['coordinate']['selection_date'] or calendar.index(execution)!=calendar.index(day)+1:raise ValueError('Exact next-observation clock differs')
        selected=entry['selected']
        universe=changed['universe'].set_index('security_id')
        for sid,row in selected.items():
            exact(row,{k:universe.loc[sid,k] for k in ('ticker','issuer_id','risk_chain')})
            if sid in issuers and issuers[sid]!=row['issuer_id']:raise ValueError('Permanent issuer changed')
            issuers[sid]=row['issuer_id']
        refit=result['refits'][index]
        if refit['decision_date']!=day or refit['execution_date']!=execution:raise ValueError('Refit clock differs')
        exact(refit['previous_schedule_target_by_security'],previous)
        fitted=refit['result']
        period_sources=dict(queue['historical_expected_source_hashes'])
        archive.merge(period_sources,{str(p):LOADED[str(p)] for p in PERIOD_SOURCE_PATHS})
        archive.merge(period_sources,{period['queue']['path']:period['queue']['sha256']})
        frame=changed['returns']
        input_payload=dict(decision_date=day,execution_date=execution,cutoff=day,weight_spec=entry['task']['weight_spec'],
            selected=selected,parameters=queue['fit_parameters'],source_hashes=period_sources,
            calendar_scope='EXPLICIT_EXECUTION_CALENDAR_NOT_VERIFIED_EXCHANGE_CALENDAR',calendar=calendar,
            returns=dict(dates=[d.date().isoformat() for d in frame.index],columns=list(frame.columns),
                values=[[float(number(v)) for v in row] for row in frame.to_numpy().tolist()]))
        input_hashes.append(schedule_digest(input_payload));exact(refit['input_sha256'],input_hashes[-1])
        source_set=dict(seed['result']['refit']['source_hashes'])
        archive.merge(source_set,{str(SCHEDULE_SOURCE):LOADED[str(SCHEDULE_SOURCE)]});archive.merge(source_set,period_sources)
        exact(refit['source_set_sha256'],schedule_digest(source_set))
        this_risk={k:float(v) for k,v in queue['fit_parameters'].items() if k in ('max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap')}
        if risk_contract is not None:exact(this_risk,risk_contract)
        risk_contract=this_risk
        if index==0:exact(fitted,{k:v for k,v in seed['result']['refit'].items() if k!='source_hashes'})
        detail=inspect_period(fitted=fitted,selected=selected,parameters=queue['fit_parameters'],returns=changed['returns'],cutoff=day,previous=previous,weight_spec=entry['task']['weight_spec'])
        exact(result['schedule'][index],dict(decision_date=day,execution_date=execution,targets=fitted['targets']))
        exact(result['risk_chains_by_decision'][day],{s:v['risk_chain'] for s,v in selected.items()})
        previous={s:v['target_weight'] for s,v in fitted['targets'].items()}
        details.append(dict(job_id=period['job_id'],decision_date=day,**detail))
    exact(result['historical_loader_gap_observations'],expected_gaps)
    exact(result['schedule_input_sha256'],schedule_digest(input_hashes))
    exact(result['fixed_risk_parameters'],risk_contract)
    verify_gaps(expected_gaps);partition=archive.verify_expected_sources(sources,contract)
    return dict(schema='EXPLICIT_TWO_PERIOD_INDEPENDENT_TYPED_DECIMAL_AUDIT_V1',result=reference,periods=details,
        whole_first_seed_refit_exact=True,complete_strategic_prior_verified=True,fit_performed=False,
        optimizer_or_owner_validator_called=False,optimal_weights_independently_proved=False,execution_performed=False,
        historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False,
        historical_expected_source_hashes=sources,archive_resolution=partition,historical_loader_gap_observations=expected_gaps)


def publish_verified(path,value):
    def verify():
        if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in LOADED.items()):raise ValueError('Loaded auditor sources omitted')
        exact(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution'])
        verify_gaps(value['historical_loader_gap_observations'])
    verify();saved=publish(path,value);verify();return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('result-path','result-sha256','output'):parser.add_argument('--'+key,required=True)
    args=vars(parser.parse_args());output=args.pop('output')
    print(json.dumps(publish_verified(output,build(**args))))
