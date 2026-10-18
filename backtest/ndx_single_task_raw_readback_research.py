"""Independent saved one-task numerical readback; never optimize or import fitter."""
from datetime import date
from decimal import Decimal,Context,localcontext
import hashlib
import json
import math

FIT_KEYS={'anchor_by_security','anchor_policy','checkpoint_weights_used','cutoff','declared_constraint_checks','declared_constraints_passed','declared_parameters','effective_anchor_strength','fit_data_sha256','fit_end','fit_row_count','fit_start','historical_task_evaluation_performed','numerical_projection','order_generation_allowed','point_in_time_verified','previous_target_weights','projection_reconstruction_audit','promotion_allowed','risk_chain_projection_relaxed','risk_chains_by_security','schema','single_name_projection_relaxed','source_authenticity_verified','source_hashes','surviving_anchor_mass','targets','top3_projection_semantics_relaxed','weight_spec'}
CHECKS={'MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT'}


def require(ok,message):
    if not ok:raise ValueError(message)


def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(encoded(v)).hexdigest()
def exact(a,b):return encoded(a)==encoded(b)


def number(value):
    require(type(value) in (int,float) and math.isfinite(value),'Finite nonboolean saved number required')
    return Decimal(str(value))


def inspect_projection(audit,spec,selected,weights,risk_relaxed,parameters):
    with localcontext(Context(prec=80)):
        return _inspect_projection(audit,spec,selected,weights,risk_relaxed,parameters)


def _inspect_projection(audit,spec,selected,weights,risk_relaxed,parameters):
    require(set(audit)=={'schema','scope','attempt_count','attempts','prior_results_reused','promotion_allowed'},'Projection audit fields')
    require(audit['schema']=='ndx_projection_reconstruction_audit_v1' and audit['scope']=='NUMERICAL_PROJECTION_RECOVERY_NOT_ECONOMIC_QUALIFICATION' and audit['prior_results_reused'] is False and audit['promotion_allowed'] is False,'Projection scope')
    require(type(audit['attempt_count']) is int and audit['attempt_count']>=0 and type(audit['attempts']) is list and audit['attempt_count']==len(audit['attempts']),'Projection count')
    if spec=='equal_weight':require(audit['attempt_count']==0,'Equal cannot optimize/recover')
    names={v['ticker'] for v in selected.values()};reports=[]
    require(len(audit['attempts'])<=2,'At most grouped projection and one original ungrouped fallback')
    for position,attempt in enumerate(audit['attempts']):
        require(set(attempt) in ({'optimizer_message','reconstruction'},{'optimizer_message','reconstruction','independent_certificate','failed_optimizer_vector'}) and type(attempt['optimizer_message']) is str,'Projection attempt fields')
        r=attempt['reconstruction'];cert=attempt.get('independent_certificate')
        require(r['schema']=='ndx_projection_reconstruction_research_v1' and type(r['certified']) is bool,'Saved reconstruction schema/type')
        for flag in ('primal_infeasibility_proven','promotion_allowed','task_recomputed','order_generation_allowed'):require(r[flag] is False,'Reconstruction authority')
        if cert is not None:
            vector=attempt['failed_optimizer_vector'];require(type(vector) is list and len(vector)==2*len(selected)+1,'Failed proposal dimension')
            for v in vector:number(v)
            require(type(cert['certified']) is bool,'Independent certificate type')
        labels={row['ticker']:row['risk_chain'] for row in selected.values()}
        grouped=r['constraints']['group_labels'] is not None
        expected_constraints=dict(max_weight=max(float(parameters['max_single_weight']),1./len(selected)),min_weight=float(parameters['min_single_weight']),top_weight_count=min(3,len(selected)-1),top_weight_cap=max(float(parameters['top_weight_cap']),min(3,len(selected)-1)/len(selected)),min_effective_n=max(1.,float(parameters['minimum_effective_n_ratio'])*len(selected)),group_labels=labels if grouped else None,max_group_weight=float(parameters['risk_chain_top1_cap']) if grouped else None)
        require(exact(r['constraints'],expected_constraints),'Original projection envelope/group mode')
        successful=r['certified'] is True and cert is not None and cert['certified'] is True
        if not successful:
            require(position==0 and risk_relaxed is True and r['constraints']['group_labels'] is not None,'Failed internal group recovery only before original fallback')
            if r['certified'] is False:require(r['weights'] is None,'Uncertified reconstruction cannot carry accepted weights')
            reports.append(dict(saved_failed_internal_group_attempt_preserved=True,final_target_linkage_claimed=False,kkt_system_independently_recomputed=False))
            continue
        require(position==len(audit['attempts'])-1,'Successful projection must be terminal recovery')
        require((r['constraints']['group_labels'] is None) is risk_relaxed,'Terminal group/fallback semantics')
        require(r['schema']=='ndx_projection_reconstruction_research_v1' and r['status']=='RECONSTRUCTED_NUMERICAL_KKT_CERTIFIED' and r['certified'] is True,'Saved reconstruction certified')
        require(set(r['weights'])==names and exact(r['weights'],r['certificate']['candidate']) and exact(r['weights'],cert['candidate']),'Complete reconstructed weights linkage')
        require(exact(r['constraints'],cert['constraints']) and exact(r['certificate']['constraints'],cert['constraints']),'Projection constraints linkage')
        for flag in ('primal_infeasibility_proven','promotion_allowed','task_recomputed','order_generation_allowed'):require(r[flag] is False,'Reconstruction authority')
        for certificate in (r['certificate'],cert):
            require(certificate['schema']=='ndx_projection_kkt_certificate_research_v1' and certificate['status']=='NUMERICAL_KKT_CERTIFIED' and certificate['certified'] is True and certificate['primal_passed'] is True and certificate['dual_passed'] is True and certificate['all_top_subsets_examined'] is True,'Saved KKT status')
            require(set(certificate['candidate'])==set(certificate['target'])==names,'Certificate ticker denominator')
            for v in certificate['candidate'].values():number(v)
            for v in certificate['target'].values():number(v)
            for flag in ('task_recomputed','primal_infeasibility_proven','promotion_allowed','order_generation_allowed'):require(certificate[flag] is False,'Certificate authority')
            tol=certificate['tolerances']
            require(exact(tol,dict(primal=1e-10,active=1e-9,stationarity=1e-9,complementarity=1e-10)),'Original certificate tolerances')
            for v in tol.values():require(number(v)>0,'Positive certificate tolerance')
            require(number(certificate['stationarity_max_abs'])<=number(tol['stationarity']) and number(certificate['stationarity_max_abs'])>=0,'Stationarity stored bound')
            require(number(certificate['complementarity_max_abs'])<=number(tol['complementarity']) and number(certificate['complementarity_max_abs'])>=0,'Complementarity stored bound')
            require(all(number(v)<=number(tol['primal']) for v in certificate['primal_residuals'].values()),'Primal stored bound')
            for active in certificate['active_constraints']:require(number(active['multiplier'])>=0,'Dual nonnegative')
        for sid,row in selected.items():require(abs(number(r['weights'][row['ticker']])-number(weights[sid]))<=Decimal('1e-9'),'Saved final/reconstruction target linkage')
        reports.append(dict(saved_certificate_structure_and_target_linkage_verified=True,kkt_system_independently_recomputed=False))
    return dict(attempt_count=len(reports),attempts=reports,optimizer_optimality_proven=False,projection_metadata_is_not_original_risk_admission=True)


def inspect_fitted(*,task,combination,fitted,numerical_sources):
    require(type(fitted) is dict and set(fitted)==FIT_KEYS,'Full fitted result schema')
    require(fitted['schema']=='ndx_dynamic_cutoff_refit_research_v2' and fitted['numerical_projection']=='V3_CERTIFIED_RECOVERY_ORIGINAL_PROBE_CLOSURE','Frozen V2 numerical contract')
    ident=task['numerical_identity'];matrix=combination['fit_matrix'];selected=ident['selected'];params=ident['parameters'];spec=ident['weight_spec']
    require(spec in ('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor'),'Three explicit specs')
    require(set(params)=={'fit_days','shrinkage_intensity','turnover_anchor_strength','max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap'},'All eight parameters')
    require(type(params['fit_days']) is int,'Exact fit days integer')
    require(matrix['dates']==sorted(set(matrix['dates'])) and all(type(d) is str and date.fromisoformat(d).isoformat()==d for d in matrix['dates']),'Canonical fit dates')
    require(all(type(row) is list and len(row)==len(selected) for row in matrix['returns']),'Full selected matrix dimensions')
    for row in matrix['returns']:
        for v in row:require(number(v)>-1,'Finite surviving return')
    require(task['numerical_task_id']==digest(ident) and task['location_id']==digest(task['location_identity']),'Task dual IDs')
    require(len(numerical_sources)==25 and fitted['source_hashes']==numerical_sources and ident['fitter_source_fingerprint']==digest(numerical_sources),'Exact25 numerical sources')
    require(ident['fit_data_sha256']==combination['fit_data_sha256']==digest(matrix)==fitted['fit_data_sha256'],'Exact126 matrix identity')
    require(len(matrix['dates'])==len(matrix['returns'])==126 and params['fit_days']==126 and type(fitted['fit_row_count']) is int and fitted['fit_row_count']==126,'126 fit window')
    require(fitted['fit_start']==matrix['dates'][0] and fitted['fit_end']==matrix['dates'][-1]==ident['cutoff']==fitted['cutoff'] and fitted['weight_spec']==spec,'Result task dates/spec')
    require(exact(fitted['declared_parameters'],{k:float(v) for k,v in params.items() if k!='fit_days'}),'All declared seven numerical/risk parameters')
    require(set(fitted['targets'])==set(selected) and len({v['issuer_id'] for v in selected.values()})==len(selected),'Complete unique target SID/issuer set')
    require(matrix['tickers']==[selected[s]['ticker'] for s in sorted(selected)],'Canonical SID matrix columns')
    weights={}
    for sid in sorted(selected):
        target=fitted['targets'][sid];require(set(target)=={'ticker','issuer_id','target_weight'} and all(target[k]==selected[sid][k] for k in ('ticker','issuer_id')),'Target coordinate mismatch')
        weights[sid]=target['target_weight'];require(number(weights[sid])>=0,'Nonnegative weights')
    require(math.isclose(sum(weights.values()),1.,abs_tol=1e-9,rel_tol=0),'Saved target simplex')
    prior=ident['requested_previous_target_weights'];expected=prior or {}
    require(exact(fitted['previous_target_weights'],{k:float(v) for k,v in expected.items()}) and exact(task['expected_fitter_previous_target_weights'],expected),'Full prior including exits')
    for v in expected.values():require(number(v)>=0,'Prior nonnegative')
    if expected:require(math.isclose(sum(float(v) for v in expected.values()),1.,abs_tol=1e-12,rel_tol=0),'Full prior mass')
    mass=sum(float(expected.get(s,0.)) for s in sorted(selected));anchor={s:float(expected.get(s,0.))/mass if mass>0 else 0. for s in sorted(selected)}
    strength=float(params['turnover_anchor_strength']) if mass>0 and spec=='constrained_fixed_shrinkage_turnover_anchor' else 0.
    for v in fitted['anchor_by_security'].values():number(v)
    require(exact(fitted['surviving_anchor_mass'],mass) and exact(fitted['anchor_by_security'],anchor) and exact(fitted['effective_anchor_strength'],strength),'Full prior survivor normalization/anchor strength')
    require(fitted['anchor_policy']=='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED','Anchor policy')
    require(fitted['risk_chains_by_security']=={s:r['risk_chain'] for s,r in selected.items()},'Risk coordinate linkage')
    if spec=='equal_weight':require(fitted['risk_chain_projection_relaxed'] is False,'Equal cannot relax projection')
    if spec=='equal_weight':require(all(type(v) is float and v==1./len(selected) for v in weights.values()),'Exact deterministic equal weights')
    with localcontext(Context(prec=80)):
        values=[number(v) for v in weights.values()];ordered=sorted(values,reverse=True);groups={}
        for sid,v in weights.items():
            chain=selected[sid]['risk_chain'];groups[chain]=groups.get(chain,Decimal(0))+number(v)
        neff=Decimal(1)/sum(v*v for v in values);t=Decimal('1e-9')
        checks=dict(MAX_SINGLE_WEIGHT=ordered[0]<=number(params['max_single_weight'])+t,MIN_SINGLE_WEIGHT=ordered[-1]>=number(params['min_single_weight'])-t,
          SECURITY_TOP3_WEIGHT=sum(ordered[:3])<=number(params['top_weight_cap'])+t,MINIMUM_EFFECTIVE_N=neff>=len(values)*number(params['minimum_effective_n_ratio'])-t,
          RISK_CHAIN_TOP1_WEIGHT=max(groups.values())<=number(params['risk_chain_top1_cap'])+t)
    decimal_checks=checks
    float_ordered=sorted(weights.values(),reverse=True);float_groups={}
    for sid,v in weights.items():
        chain=selected[sid]['risk_chain'];float_groups[chain]=float_groups.get(chain,0.)+v
    float_neff=1./sum(v*v for v in weights.values())
    checks=dict(MAX_SINGLE_WEIGHT=float_ordered[0]<=float(params['max_single_weight'])+1e-9,
      MIN_SINGLE_WEIGHT=float_ordered[-1]>=float(params['min_single_weight'])-1e-9,
      SECURITY_TOP3_WEIGHT=sum(float_ordered[:3])<=float(params['top_weight_cap'])+1e-9,
      MINIMUM_EFFECTIVE_N=float_neff>=len(weights)*float(params['minimum_effective_n_ratio'])-1e-9,
      RISK_CHAIN_TOP1_WEIGHT=max(float_groups.values())<=float(params['risk_chain_top1_cap'])+1e-9)
    require(set(fitted['declared_constraint_checks'])==CHECKS and all(type(v) is bool for v in fitted['declared_constraint_checks'].values()) and fitted['declared_constraint_checks']==checks and fitted['declared_constraints_passed'] is all(checks.values()),'Independent original five risks')
    require(type(fitted['risk_chain_projection_relaxed']) is bool,'Projection relaxation metadata type')
    require(fitted['single_name_projection_relaxed'] is (spec!='equal_weight' and params['max_single_weight']<1./len(selected)) and fitted['top3_projection_semantics_relaxed'] is (spec!='equal_weight' and (len(selected)<=3 or params['top_weight_cap']<min(3,len(selected)-1)/len(selected))),'Projection semantic metadata')
    for flag in ('checkpoint_weights_used','historical_task_evaluation_performed','order_generation_allowed','point_in_time_verified','promotion_allowed','source_authenticity_verified'):require(fitted[flag] is False,'Fitted authority escalation')
    projection=inspect_projection(fitted['projection_reconstruction_audit'],spec,selected,weights,fitted['risk_chain_projection_relaxed'],params)
    return dict(status='FITTED_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_FIVE_RISKS_FAILED',checks=checks,original_float_effective_n=float_neff,extra_decimal_diagnostic_checks=decimal_checks,effective_n=str(neff),risk_chain_weights={k:str(v) for k,v in groups.items()},complete_targets_verified=True,complete_prior_verified=True,exited_prior_sids=sorted(set(expected)-set(selected)),projection_audit=projection,risk_projection_metadata_independently_recomputed=False,optimizer_optimality_proved=False,numerical_failure_is_economic_infeasibility=False,fitter_called=False,promotion_allowed=False)
