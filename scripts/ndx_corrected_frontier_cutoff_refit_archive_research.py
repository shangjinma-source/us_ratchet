"""Explicit complete corrected frontier queue and one historical-cutoff diagnostic fit."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_corrected_complete_date_frontier_archive_research as frontier
from scripts import ndx_selected_archive_completed_independent_audit_20260919 as audit
from backtest import ndx_dynamic_cutoff_refit_v2_research as fitter
from backtest import ndx_dynamic_training_semantics as semantics
from backtest import ndx_delta_selected_input_research as typed
archive=frontier.archive
PARAMETERS=('fit_days','shrinkage_intensity','turnover_anchor_strength','max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap')
POLICY='FIRST_DECISION_NO_PRIOR_TARGET_DIAGNOSTIC'
LOADED=dict(frontier.LOADED)
for module in (sys.modules[__name__],fitter,semantics,typed):
    path=Path(module.__file__).resolve();archive.merge(LOADED,{str(path):archive.drift.file_sha(path)})
archive.merge(LOADED,fitter._sources())


def digest(value):return audit.original.digest(value)


def candidate_queue(report,records):
    if report.get('scope')!='ORIGINAL_RESEARCHED_SUBPOOL_NOT_FULL_NDX' or report.get('winner') is not None:
        raise ValueError('Original full researched cohort, without winner, required')
    if len(report['candidate_diagnostics'])!=report['original_count'] or len(records)!=report['original_count']:
        raise ValueError('Complete candidate denominator required')
    tasks={r['task']['job_id']:r['task'] for r in records}
    diagnostics={r['job_id']:r for r in report['candidate_diagnostics']}
    if len(tasks)!=len(records) or set(diagnostics)!=set(tasks):raise ValueError('Full original task identities differ')
    candidates={}
    for role,key in (('RISK_LIQUIDITY_FRONTIER','risk_liquidity_frontier'),('USER_PREFERENCE_REFERENCE','user_preference_references')):
        seen=set()
        for row in report[key]:
            job=row['job_id']
            if job in seen or job not in tasks or not audit.original.exact(row,diagnostics[job]):raise ValueError('Frontier/reference row changed')
            seen.add(job);task=tasks[job]
            if any(type(row[k]) is not type(task[k]) or row[k]!=task[k] for k in ('tickers','holding_count','weight_spec')):raise ValueError('Full task identity differs')
            if role=='RISK_LIQUIDITY_FRONTIER' and row['fractional_risk_liquidity_passed'] is not True:raise ValueError('Invalid risk frontier')
            if role=='USER_PREFERENCE_REFERENCE' and (row['user_preference_reference'] is not True or task['weight_spec']!='equal_weight' or set(task['tickers'].split(';'))!={'AMAT','AVGO','CDNS','GOOG'}):raise ValueError('Invalid explicit preference')
            if job not in candidates:candidates[job]=dict(candidate=deepcopy(row),task=deepcopy(task),roles=[])
            candidates[job]['roles'].append(role)
    if len(report['user_preference_references'])!=1:raise ValueError('One preference reference required, even if risk fails')
    return [candidates[k] for k in sorted(candidates)]


def correct_context(context,report,cutoff):
    if context.get('schema')!='ndx_joint_weight_checkpoint_v1' or context.get('numerical_sources')!=typed.trace.full._LOADED_SOURCES:
        raise ValueError('Explicit original full typed v3 context required')
    if cutoff!=report['original_decision_data_end'] or fitter.previous._date(cutoff)>=fitter.previous._date(report['coordinate']['selection_date']):
        raise ValueError('Explicit original historical cutoff required')
    if context['runtime']!=typed.current_runtime():raise ValueError('Original and actual numerical runtimes differ')
    encoded=context['prepared_inputs'];inputs={k:typed._restore_input(v) for k,v in encoded.items()}
    original=semantics.training_semantics(inputs=inputs,decision_data_end=cutoff,source_batch=report['coordinate']['source_batch'],universe_track=report['coordinate']['universe_track'])
    if original['training_semantics_sha256']!=report['original_training_contract_reference_sha256']:
        raise ValueError('Entire six-input original cohort differs')
    if set(inputs['contract'])!=set(PARAMETERS)|{'window_days','step_days','transaction_cost_bps','portfolio_cash_usd','minimum_cash_buffer_usd','minimum_median_dollar_volume_usd'}:raise ValueError('Original fourteen explicit parameters required')
    changed=deepcopy(inputs);changed_encoded=deepcopy(encoded);applied=[]
    for ticker,date,before,after in typed.CORRECTIONS:
        if ticker not in changed['returns'] or date not in changed['returns'].index or changed['returns'].loc[date,ticker]!=before:
            raise ValueError('Exact evidenced original return cell absent or changed')
        changed['returns'].loc[date,ticker]=after
        column=list(inputs['returns'].columns).index(ticker);position=list(inputs['returns'].index).index(typed.pd.Timestamp(date))
        cell=changed_encoded['returns']['payload']['mapping']['column_values']['items'][column]['items'][position]
        if set(cell)!={'float_hex'} or float.fromhex(cell['float_hex'])!=before:raise ValueError('Original exact typed float cell differs')
        cell['float_hex']=after.hex();applied.append(dict(ticker=ticker,date=date,old=before,new=after))
    corrected=semantics.training_semantics(inputs=changed,decision_data_end=cutoff,source_batch=report['coordinate']['source_batch'],universe_track=report['coordinate']['universe_track'])
    for key in original['payload']:
        if key!='returns_sha256' and original['payload'][key]!=corrected['payload'][key]:raise ValueError('Non-return training channel changed')
    if digest(encoded)!=digest({k:context['prepared_inputs'][k] for k in inputs}):raise ValueError('Typed input denominator differs')
    universe=inputs['universe'];required=('ticker','security_id','issuer_id','risk_chain')
    if not set(required)<=set(universe.columns) or universe['ticker'].duplicated().any() or universe['security_id'].duplicated().any():raise ValueError('Unique security coordinates required')
    identities={}
    for row in universe[list(required)].to_dict('records'):
        if any(type(v) is not str or not v or v!=v.strip() for v in row.values()) or row['ticker']!=row['ticker'].upper():raise ValueError('Canonical security coordinates required')
        identities[row['ticker']]=row
    restored_changed={k:typed._restore_input(v) for k,v in changed_encoded.items()}
    if typed.provenance._digest(restored_changed)!=typed.provenance._digest(changed):raise ValueError('Exact three typed edits differ from numerical matrix')
    return inputs,changed,identities,dict(original_typed_inputs_sha256=digest(encoded),corrected_typed_inputs_sha256=digest(changed_encoded),original_decoded_inputs_sha256=typed.provenance._digest(inputs),corrected_decoded_inputs_sha256=typed.provenance._digest(changed),
        original_training_semantics=original,corrected_training_semantics=corrected,corrections=applied)


def prepare_queue(*,frontier_path,frontier_sha256,context_path,context_sha256,historical_cutoff):
    sources=dict(LOADED)
    def read(path,sha):
        path=str(Path(path).resolve());raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External artifact changed')
        archive.merge(sources,{path:sha});return json.loads(raw)
    report=read(frontier_path,frontier_sha256);frontier.verify(report)
    complete_ref=report['complete_date_artifact'];diff_ref=report['independent_full_diff_artifact']
    rebuilt=frontier.build(date=report['coordinate']['selection_date'],complete_path=complete_ref['path'],complete_sha256=complete_ref['sha256'],diff_path=diff_ref['path'],diff_sha256=diff_ref['sha256'])
    if not audit.original.exact(rebuilt,report):raise ValueError('Frontier must equal complete corrected date reconstruction')
    archive.merge(sources,report['historical_expected_source_hashes'])
    if sources.get(str(Path(context_path).resolve()))!=context_sha256:raise ValueError('Context not in original hard frontier source closure')
    complete=read(complete_ref['path'],complete_ref['sha256']);queue=candidate_queue(report,complete['records'])
    context=read(context_path,context_sha256)
    inputs,changed,identities,binding=correct_context(context,report,historical_cutoff)
    for entry in queue:
        names=entry['task']['tickers'].split(';')
        if len(names)!=entry['task']['holding_count'] or len(set(names))!=len(names) or any(t not in identities or t not in changed['returns'] for t in names):raise ValueError('Candidate absent from bound full cohort')
        selected={identities[t]['security_id']:{k:identities[t][k] for k in ('ticker','issuer_id','risk_chain')} for t in names}
        if len({r['issuer_id'] for r in selected.values()})!=len(names):raise ValueError('Duplicate issuer in candidate')
        entry['selected']=selected
    archive.merge(sources,typed.correction_sources())
    partition=archive.verify_expected_sources(sources,archive.load_contract())
    result=dict(schema='CORRECTED_FRONTIER_HISTORICAL_CUTOFF_QUEUE_V1',frontier=dict(path=str(Path(frontier_path).resolve()),sha256=frontier_sha256),
        context=dict(path=str(Path(context_path).resolve()),sha256=context_sha256),coordinate=report['coordinate'],historical_cutoff=historical_cutoff,
        cutoff_scope='EXPLICIT_ARCHIVED_HISTORICAL_DATE_NOT_CURRENT_LIVE_AS_OF_DATE',candidates=queue,candidate_count=len(queue),
        risk_liquidity_frontier_count=len(report['risk_liquidity_frontier']),user_preference_count=len(report['user_preference_references']),
        full_original_count=report['original_count'],all_frontier_and_preference_candidates_included=True,input_binding=binding,
        original_fourteen_parameter_contract=inputs['contract'],fit_parameters={k:inputs['contract'][k] for k in PARAMETERS},
        diagnostic_policy=POLICY,previous_target_weights=None,effective_anchor_strength=0.,
        historical_expected_source_hashes=sources,archive_resolution=partition,historical_loader_gap_observations=report['historical_loader_gap_observations'],
        original_runtime=context['runtime'],checkpoint_weights_used=False,fit_performed=False,selection_performed=False,
        historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False)
    verify(result);return result


def verify(value):
    sources=value['historical_expected_source_hashes']
    if any(sources.get(p)!=h for p,h in LOADED.items()):raise ValueError('Loaded adapter dependency omitted')
    if not audit.original.exact(archive.verify_expected_sources(sources,archive.load_contract()),value['archive_resolution']):raise ValueError('Archive partition changed')
    audit.original.verify_gaps(value['historical_loader_gap_observations'])
    audit.original.require_false(value,('checkpoint_weights_used','selection_performed','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed'))


def check_fitted(fitted,selected,parameters,cutoff):
    if (fitted.get('schema')!='ndx_dynamic_cutoff_refit_research_v2' or fitted['cutoff']!=cutoff or fitted['fit_end']!=cutoff
        or type(fitted['fit_row_count']) is not int or fitted['fit_row_count']!=parameters['fit_days']
        or fitted['previous_target_weights']!={} or fitted['effective_anchor_strength']!=0 or fitted['surviving_anchor_mass']!=0
        or any(type(fitted[k]) not in (int,float) for k in ('effective_anchor_strength','surviving_anchor_mass'))
        or fitted['anchor_by_security']!={sid:0. for sid in selected}
        or fitted['checkpoint_weights_used'] is not False or set(fitted['targets'])!=set(selected)
        or fitted['declared_parameters']!={k:v for k,v in parameters.items() if k!='fit_days'}
        or fitted['risk_chains_by_security']!={s:r['risk_chain'] for s,r in selected.items()}):raise ValueError('Original first-decision refit contract differs')
    weights={}
    for sid,target in fitted['targets'].items():
        if any(target[k]!=selected[sid][k] for k in ('ticker','issuer_id')):raise ValueError('Fitted security identity differs')
        w=target['target_weight']
        if type(w) not in (int,float) or not math.isfinite(w) or w<0:raise ValueError('Finite nonnegative target required')
        weights[sid]=w
    if abs(sum(weights.values())-1)>1e-9:raise ValueError('Fitted simplex differs')
    values=sorted(weights.values(),reverse=True);chains={}
    for sid,w in weights.items():
        key=selected[sid]['risk_chain'];chains[key]=chains.get(key,0)+w
    checks=dict(MAX_SINGLE_WEIGHT=values[0]<=parameters['max_single_weight']+1e-9,MIN_SINGLE_WEIGHT=values[-1]>=parameters['min_single_weight']-1e-9,
        SECURITY_TOP3_WEIGHT=sum(values[:3])<=parameters['top_weight_cap']+1e-9,MINIMUM_EFFECTIVE_N=1/sum(w*w for w in values)>=len(values)*parameters['minimum_effective_n_ratio']-1e-9,
        RISK_CHAIN_TOP1_WEIGHT=max(chains.values())<=parameters['risk_chain_top1_cap']+1e-9)
    if fitted['declared_constraint_checks']!=checks or any(type(v) is not bool for v in fitted['declared_constraint_checks'].values()) or fitted['declared_constraints_passed'] is not all(checks.values()):raise ValueError('Independent five original risk checks differ')
    return checks


def run_one(*,prepared,job_id):
    ref=prepared['frontier'];context=prepared['context']
    fresh=prepare_queue(frontier_path=ref['path'],frontier_sha256=ref['sha256'],context_path=context['path'],context_sha256=context['sha256'],historical_cutoff=prepared['historical_cutoff'])
    if not audit.original.exact(fresh,prepared):raise ValueError('Prepared full queue changed')
    entry,=[e for e in fresh['candidates'] if e['task']['job_id']==job_id]
    report=json.loads(Path(ref['path']).read_bytes());ctx=json.loads(Path(context['path']).read_bytes())
    _,changed,_,binding=correct_context(ctx,report,fresh['historical_cutoff'])
    if binding!=fresh['input_binding']:raise ValueError('Typed matrix changed before fit')
    fit_sources=fitter._sources()
    result=dict(schema='CORRECTED_FRONTIER_HISTORICAL_CUTOFF_TASK_V1',queue_sha256=digest(prepared),job_id=job_id,candidate=entry,
        historical_cutoff=fresh['historical_cutoff'],diagnostic_policy=POLICY,effective_anchor_strength=0.,
        checkpoint_weights_used=False,selection_performed=False,historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False,
        historical_expected_source_hashes=fresh['historical_expected_source_hashes'],archive_resolution=fresh['archive_resolution'],historical_loader_gap_observations=fresh['historical_loader_gap_observations'])
    try:
        fitted=fitter.refit_dynamic_cutoff_weights(returns=changed['returns'],cutoff=fresh['historical_cutoff'],selected=entry['selected'],weight_spec=entry['task']['weight_spec'],previous_target_weights=None,**fresh['fit_parameters'])
    except (ValueError,ArithmeticError,RuntimeError) as error:
        result.update(status='FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY',refit=None,error_type=type(error).__name__,error=str(error))
    else:
        if fitted['source_hashes']!=fit_sources:raise ValueError('Fitter sources differ')
        securities=sorted(entry['selected']);names=[entry['selected'][sid]['ticker'] for sid in securities]
        frame=changed['returns'].iloc[-fresh['fit_parameters']['fit_days']:][names]
        payload=dict(dates=[d.date().isoformat() for d in frame.index],tickers=names,returns=frame.to_numpy().tolist())
        if fitted['fit_start']!=payload['dates'][0] or fitted['fit_data_sha256']!=digest(payload):raise ValueError('Exact last-cutoff fitted matrix differs')
        checks=check_fitted(fitted,entry['selected'],fresh['fit_parameters'],fresh['historical_cutoff'])
        result.update(status='FITTED_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_FIVE_RISKS_FAILED',refit=fitted,independently_recomputed_five_checks=checks)
    finally:
        verify(fresh)
        if fitter._sources()!=fit_sources or typed.provenance._digest(changed)!=binding['corrected_decoded_inputs_sha256']:raise ValueError('Numerical sources or input matrix mutated')
    result.update(new_cutoff_fit_attempt_count=1,whole_lot_execution_performed=False,forward_oos_evaluation_performed=False,numerical_failure_is_economic_infeasibility=False)
    verify(result);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('frontier-path','frontier-sha256','context-path','context-sha256','historical-cutoff','output'):parser.add_argument('--'+name,required=True)
    args=vars(parser.parse_args());target=args.pop('output')
    if Path(target).exists():raise FileExistsError('Create-only preparation; no fitting by default')
    queue=prepare_queue(**args);saved=frontier.reader.publish(target,queue);verify(queue);print(json.dumps(saved))
