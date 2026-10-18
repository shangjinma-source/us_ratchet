"""Future outer-receipt interface: resolve adjacent audited targets, never fit.

Envelope checks are structural declarations. A source-bound reader must authenticate
all bytes and its version separately; a caller's PASS is not byte authentication.
"""
from copy import deepcopy
import math
from backtest.ndx_multidecision_selected_refit_inputs_research import (
    CUTOFFS, MODES, LANES, PARAMETERS, FLAGS, require, exact, digest, merge, flags)

PREFIX = 'OUTER_LANE_CUTOFF_REFIT_'
ENVELOPE_FLAGS = ('execution_authorized','promotion_allowed','point_in_time_verified',
                  'source_bytes_authenticated','optimization_reperformed')


def number(x):
    require(type(x) in (int,float) and math.isfinite(x),'Finite nonboolean numeric value')
    return float(x)


def coordinate(row):
    return row['cutoff'], row['fx_mode'], row['lane']


def make_request(row, fitter_contract):
    require(row['numerical_identity'] is not None and row['prior_value_resolved'] is True
            and row['missing_latest_return_slots']==[], 'Complete resolved request only')
    require(row['numerical_task_id']==digest(row['numerical_identity'])
            and row['location_id']==digest(row['location_identity'])
            and row['fit_data_sha256']==digest(row['fit_matrix']), 'Exact request identities')
    request=dict(schema=PREFIX+'REQUEST_V1', coordinate=list(coordinate(row)),
        numerical_identity=deepcopy(row['numerical_identity']),numerical_task_id=row['numerical_task_id'],
        location_identity=deepcopy(row['location_identity']),location_id=row['location_id'],
        fit_matrix=deepcopy(row['fit_matrix']),fitter_contract_reference=deepcopy(fitter_contract['reference']),
        prior_evidence_reference=deepcopy(row['prior_reference']),
        source_slot_evidence=deepcopy(row['source_slot_evidence']),
        required_runtime_versions=deepcopy(fitter_contract['runtime_versions']),
        required_worker_environment=deepcopy(fitter_contract['required_worker_environment']),
        **dict.fromkeys(ENVELOPE_FLAGS,False))
    request['content_sha256']=digest(request)
    return request


def validate_fitter(fitter):
    require(fitter['schema']=='OUTER_CUTOFF_REFIT_SOURCE_CONTRACT_V1','Explicit outer source contract')
    require(type(fitter['source_hashes']) is dict and len(fitter['source_hashes'])==25
            and digest(fitter['source_hashes'])==fitter['fitter_source_fingerprint'],'Complete outer25 source declaration')
    exact(fitter['parameters'],PARAMETERS,'Original eight parameters')
    require(fitter['first_requested_previous_target_weights'] is None
            and type(fitter['first_effective_turnover_anchor_strength']) is int
            and fitter['first_effective_turnover_anchor_strength']==0,'Outer initial None disables anchor')
    require(fitter['prior_policy']=='SAME_FX_SAME_LANE_PREVIOUS_ADJACENT_AUDITED_OUTER_REFIT_TARGET','Adjacent audited prior policy')
    exact(fitter['required_worker_environment'],{'PYTHONHASHSEED':'0','sys_flags_hash_randomization':0},'Fixed worker hash environment')
    require(set(fitter['runtime_versions'])=={'python','numpy','pandas','scipy'}
            and all(type(v) is str and v for v in fitter['runtime_versions'].values()),'Explicit full runtime versions')


def inspect_return(body, request, fitter):
    identity=request['numerical_identity']; selected=identity['selected']; sids=sorted(selected)
    require(body['schema']=='ndx_dynamic_cutoff_refit_research_v2','Actual frozen v2 result schema')
    for k in ('cutoff','weight_spec','fit_data_sha256'):exact(body[k],identity[k],'Return '+k)
    matrix=request['fit_matrix']
    require(type(body['fit_row_count']) is int and body['fit_row_count']==126,'Actual126 return rows')
    exact([body['fit_start'],body['fit_end']],[matrix['dates'][0],matrix['dates'][-1]],'Actual fit endpoints')
    exact(body['source_hashes'],fitter['source_hashes'],'Original full25 result sources')
    exact(body['declared_parameters'],{k:v for k,v in PARAMETERS.items() if k!='fit_days'},'Old seven result parameters')
    require(type(body['targets']) is dict and set(body['targets'])==set(sids),'Complete original selected target set')
    weights={}
    for sid in sids:
        target=body['targets'][sid]
        require(set(target)=={'ticker','issuer_id','target_weight'},'Exact old target fields')
        exact([target['ticker'],target['issuer_id']],[selected[sid]['ticker'],selected[sid]['issuer_id']],'Original SID identity')
        weights[sid]=number(target['target_weight']);require(weights[sid]>0,'Old admitted outer target is positive')
    require(math.isclose(sum(weights.values()),1.,abs_tol=1e-12,rel_tol=0),'Prior accepted by original fitter simplex gate')
    exact(body['risk_chains_by_security'],{s:selected[s]['risk_chain'] for s in sids},'Original chains')
    previous=identity['requested_previous_target_weights'] or {}
    exact(body['previous_target_weights'],previous,'None request versus empty returned prior')
    mass=sum(previous.get(s,0.) for s in sids)
    anchor={s:previous.get(s,0.)/mass if mass>0 else 0. for s in sids}
    strength=.25 if mass>0 and identity['weight_spec']=='constrained_fixed_shrinkage_turnover_anchor' else 0.
    exact(body['surviving_anchor_mass'],mass,'Original ordered overlap mass')
    exact(body['anchor_by_security'],anchor,'Surviving normalized anchor')
    exact(body['effective_anchor_strength'],strength,'Actual effective anchor')
    require(body['anchor_policy']=='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED','Original anchor policy')
    ordered=sorted(weights.values(),reverse=True); groups={}
    for s,w in weights.items():groups[selected[s]['risk_chain']]=groups.get(selected[s]['risk_chain'],0.)+w
    checks=dict(MAX_SINGLE_WEIGHT=ordered[0]<=.45+1e-9,MIN_SINGLE_WEIGHT=ordered[-1]>=.05-1e-9,
        SECURITY_TOP3_WEIGHT=sum(ordered[:3])<=.8+1e-9,
        MINIMUM_EFFECTIVE_N=1./sum(w*w for w in weights.values())>=len(weights)*.7-1e-9,
        RISK_CHAIN_TOP1_WEIGHT=max(groups.values())<=.55+1e-9)
    exact(body['declared_constraint_checks'],checks,'Original five risk check arithmetic')
    require(all(checks.values()) and body['declared_constraints_passed'] is True,'Only admitted prior advances')
    flags(body,('checkpoint_weights_used','point_in_time_verified','source_authenticity_verified',
        'promotion_allowed','historical_task_evaluation_performed','order_generation_allowed'))
    require(type(body['risk_chain_projection_relaxed']) is bool,'Original solver diagnostic retained')
    exact(body['single_name_projection_relaxed'],identity['weight_spec']!='equal_weight' and .45<1./len(sids),'Original single projection diagnostic')
    exact(body['top3_projection_semantics_relaxed'],identity['weight_spec']!='equal_weight' and (len(sids)<=3 or .8<min(3,len(sids)-1)/len(sids)),'Original top3 projection diagnostic')
    require(body['numerical_projection']=='V3_CERTIFIED_RECOVERY_ORIGINAL_PROBE_CLOSURE','Actual projection version')
    audit=body['projection_reconstruction_audit']
    require(audit['schema']=='ndx_projection_reconstruction_audit_v1'
        and audit['scope']=='NUMERICAL_PROJECTION_RECOVERY_NOT_ECONOMIC_QUALIFICATION'
        and type(audit['attempts']) is list and type(audit['attempt_count']) is int
        and audit['attempt_count']==len(audit['attempts']),'Full reconstruction declaration')
    flags(audit,('prior_results_reused','promotion_allowed'))
    return {s:body['targets'][s]['target_weight'] for s in sids}


def inspect_prior(envelope, expected_request, fitter, receipt_contract, sources, resolved_requests):
    base_keys={'request','raw_result','postcheck','readback','references'}
    require(type(envelope) is dict and set(envelope) in (base_keys,base_keys|{'numerical_reuse_evidence'}),'Full future evidence envelope, not bare weights')
    reused='numerical_reuse_evidence' in envelope
    refs=envelope['references'];require(set(refs)=={'request','raw_result','postcheck','readback','reader'},'All five external roles')
    for r in refs.values():merge(sources,r)
    exact(refs['reader'],receipt_contract['reader_reference'],'Explicit versioned future independent reader')
    request=envelope['request'];raw=envelope['raw_result'];post=envelope['postcheck'];audit=envelope['readback']
    exact(request,expected_request,'Same adjacent lane request, full matrix and resolved prior')
    raw_request=request;raw_request_ref=refs['request']
    if reused:
        original=envelope['numerical_reuse_evidence']
        require(type(original) is dict and set(original)==base_keys,'Reuse only first actual audited call, no alias chains')
        origin=original['request'];require(origin['location_id']!=request['location_id'],'Reuse must name distinct original location')
        origin_key=tuple(origin['coordinate'])
        require(len(origin_key)==3 and origin_key[0] in CUTOFFS and origin_key[1] in MODES
            and origin_key[2] in LANES and origin_key in resolved_requests,'Registered already resolved original lane')
        exact(origin,resolved_requests[origin_key],'Reuse original must match independently prepared original lane request')
        require(origin['content_sha256']==digest({k:v for k,v in origin.items() if k!='content_sha256'})
            and origin['location_id']==digest(origin['location_identity'])
            and origin['numerical_task_id']==digest(origin['numerical_identity']),'Original complete request identities')
        for k in ('numerical_identity','numerical_task_id','fit_matrix','fitter_contract_reference','required_runtime_versions','required_worker_environment'):
            exact(origin[k],request[k],'Identical numeric reuse input '+k)
        exact(origin['coordinate'],[origin['location_identity'][k] for k in ('cutoff','fx_mode','lane')],'Original location mapping')
        require(origin['coordinate'][0]==request['coordinate'][0],'No future/cross-cutoff numerical reuse')
        inspect_prior(original,resolved_requests[origin_key],fitter,receipt_contract,sources,resolved_requests)
        exact(raw,original['raw_result'],'Original actual raw object retained unchanged')
        exact(refs['raw_result'],original['references']['raw_result'],'Original raw immutable reference')
        raw_request=origin;raw_request_ref=original['references']['request']
        for r in original['references'].values():
            require(post['source_hashes'].get(r['path'])==r['sha256'],'Reuse post covers full original audit chain')
        for p,h in original['readback']['source_hashes'].items():
            require(post['source_hashes'].get(p)==h,'Reuse covers original audit source declarations')
    for obj,kind in ((raw,'RAW_RETURN'),(post,'POSTCHECK'),(audit,'INDEPENDENT_READBACK')):
        require(obj['schema']==PREFIX+kind+'_V1','Explicit future '+kind+' interface');flags(obj,ENVELOPE_FLAGS)
        bound_request=raw_request if kind=='RAW_RETURN' else request
        exact(obj['request_reference'],raw_request_ref if kind=='RAW_RETURN' else refs['request'],'Original request reference')
        require(obj['numerical_task_id']==bound_request['numerical_task_id'] and obj['location_id']==bound_request['location_id'],'Numerical and lane identities')
        require(type(obj['source_hashes']) is dict,'Complete source declarations')
        for p,h in obj['source_hashes'].items():merge(sources,dict(path=p,sha256=h))
    require(raw['returned'] is True and raw['call_invoked'] is True and type(raw['returned_call_count']) is int
            and raw['returned_call_count']==1 and raw['error'] is None,'Successful single saved return only')
    exact(raw['runtime_versions'],fitter['runtime_versions'],'Runtime versions')
    exact(raw['worker_environment'],fitter['required_worker_environment'],'Worker actual environment')
    require(raw['internal_optimizer_call_count'] is None,'Do not invent optimizer call counts')
    for obj in (post,audit):exact(obj['raw_result_reference'],refs['raw_result'],'Raw return external binding')
    require(post['outcome']==('REUSED_AUDITED_NUMERICAL_RESULT' if reused else 'REFIT_PASSED_PENDING_INDEPENDENT_READBACK') and post['error'] is None,'Failure never becomes a prior')
    require(post['current_location_call_invoked'] is (not reused)
        and type(post['current_location_returned_call_count']) is int
        and post['current_location_returned_call_count']==(0 if reused else 1),'No fictitious calls in reused lane')
    require(audit['status']=='PASS' and audit['scope']=='SAVED_OUTER_RESULT_ARITHMETIC_AND_SOURCE_BINDING_NOT_REOPTIMIZATION','Specific readback success scope')
    exact(audit['postcheck_reference'],refs['postcheck'],'Audit postcheck binding')
    require(audit['reader_sha256']==refs['reader']['sha256'],'Reader version declaration')
    exact(audit['targets_preserved'],raw['result']['targets'],'Independently checked saved target object')
    require(audit['raw_result_body_sha256']==digest(raw['result']),'Whole raw body retained')
    required=dict(fitter['source_hashes'])
    for r in (fitter['reference'],raw_request_ref):merge(required,r)
    for p,h in required.items():require(raw['source_hashes'].get(p)==h,'Raw source declaration covers frozen input')
    for p,h in raw['source_hashes'].items():require(post['source_hashes'].get(p)==h,'Post covers raw source declaration')
    for r in (refs['request'],refs['raw_result'],refs['postcheck'],refs['reader']):
        require(audit['source_hashes'].get(r['path'])==r['sha256'],'Audit covers exact evidence role')
    for p,h in post['source_hashes'].items():require(audit['source_hashes'].get(p)==h,'Audit covers all prior sources')
    return inspect_return(raw['result'],raw_request,fitter)


def resolve_adjacent_refit_priors(*, prepared, prior_evidence, receipt_contract):
    """Incrementally produce all 48 request slots; missing adjacency stays unresolved."""
    require(type(prior_evidence) is list,'Explicit complete supplied prior evidence list')
    require(receipt_contract['schema']=='OUTER_LANE_RECEIPT_INTERFACE_CONTRACT_V1'
            and receipt_contract['source_bytes_authenticated'] is False,'Future receipt contract is not authentication')
    result=deepcopy(prepared);require(result['schema']=='MULTIDECISION_SELECTED_LATEST126_REFIT_INPUTS_V1','Original preparation version')
    require(prepared['content_sha256']==digest({k:v for k,v in prepared.items() if k!='content_sha256'}),'Full preparation digest')
    flags(result,FLAGS);fitter=result['fitter_contract_preserved'];validate_fitter(fitter)
    sources=result['source_hashes'];merge(sources,receipt_contract['reader_reference'])
    by={};used=set();resolved={}
    for e in prior_evidence:
        key=tuple(e['request']['coordinate']);require(key not in by,'Unique receipt per lane and cutoff');by[key]=e
    rows=result['rows'];require(len(rows)==48,'No coordinate truncation')
    for i,row in enumerate(rows):
        di,rem=divmod(i,8);mi,li=divmod(rem,4);key=(CUTOFFS[di],MODES[mi],LANES[li])
        require(coordinate(row)==key and type(row['decision_index']) is int and row['decision_index']==di,'Full original48 order')
        row['outer_request']=None
        if row['fit_matrix'] is None or row['missing_latest_return_slots']:continue
        if di:
            previous=(CUTOFFS[di-1],key[1],key[2])
            if previous not in by or previous not in resolved:continue
            weights=inspect_prior(by[previous],resolved[previous],fitter,receipt_contract,sources,resolved);used.add(previous)
            row.update(requested_previous_target_weights=weights,prior_value_resolved=True,
                prior_resolution='PREVIOUS_ADJACENT_AUDITED_OUTER_TARGET',prior_reference=deepcopy(by[previous]['references']['readback']))
            identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=row['cutoff'],
                holding_count=len(row['selected']),selected=deepcopy(row['selected']),weight_spec=row['weight_spec'],
                parameters=deepcopy(PARAMETERS),requested_previous_target_weights=deepcopy(weights),
                fit_data_sha256=row['fit_data_sha256'],fitter_source_fingerprint=fitter['fitter_source_fingerprint'])
            location=dict(schema='MULTIDECISION_OUTER_REFIT_LOCATION_IDENTITY_V1',cutoff=row['cutoff'],fx_mode=row['fx_mode'],
                lane=row['lane'],selection_reference=row['choice_reference'],selected_scoring_job_id=row['selected_scoring_job_id'],history_reference=result['history_reference'])
            row.update(numerical_identity=identity,numerical_task_id=digest(identity),location_identity=location,
                location_id=digest(location),status='ADJACENT_PRIOR_REFIT_INPUTS_MATERIALIZED_NOT_DISPATCHED')
        request=make_request(row,fitter);row['outer_request']=request;resolved[key]=request
    require(used==set(by),'Future, unconsumed, cross-lane or nonadjacent prior evidence refused')
    result.update(schema='MULTIDECISION_SELECTED_LATEST126_REFIT_INPUTS_V2',
        parent_preparation_content_sha256=prepared['content_sha256'],prior_receipt_interface_preserved=deepcopy(receipt_contract),
        prior_evidence_preserved=deepcopy(prior_evidence),prior_evidence_interface='EXPLICIT_OUTER_LANE_FUTURE_RECEIPTS_V1',
        numerical_identity_generated_only_for_initial_complete_inputs=False,
        later_matrix_prepared_without_final_task_identity=any(r['status']=='INPUTS_PREPARED_PRIOR_UNRESOLVED' for r in rows))
    result['status_counts']={s:sum(r['status']==s for r in rows) for s in {r['status'] for r in rows}}
    result.pop('content_sha256');result['content_sha256']=digest(result)
    return result


def prepare_resolved_selected_cutoff_refit_inputs(*, selection, history, channel_bindings,
        fitter_contract, prior_evidence, receipt_contract):
    """Full source-matrix preparation then bounded evidence resolution; no fitter import."""
    from backtest.ndx_multidecision_selected_refit_inputs_research import prepare_selected_cutoff_refit_inputs
    prepared=prepare_selected_cutoff_refit_inputs(selection=selection,history=history,
        channel_bindings=channel_bindings,fitter_contract=fitter_contract,previous_refit_evidence=None)
    return resolve_adjacent_refit_priors(prepared=prepared,prior_evidence=prior_evidence,receipt_contract=receipt_contract)
