"""Pure bounded lazy-position materialization with reference-only completed-task reuse."""
from copy import deepcopy
import hashlib,json,math
from pathlib import Path
from backtest import ndx_issuer_task_materialization_research as old
from backtest import ndx_bulk_budgeted_search_schedule_research as scheduling

SOURCE=Path(__file__).resolve()
SCHEMA='BULK_LAZY_TASK_MATERIALIZATION_V1'
HARD_OLD='11348bd4aa99b8ee61bacdd12438aaf3c600e1f808e430130464895c22a2df88'
SCHEDULE_SHA='e3e477328b50c43f3bfed31ded0ef0d545dc180ab2980c5b4165331c601897df'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(old.__file__).resolve(),Path(scheduling.__file__).resolve())}
for dependency in (old.LOADED,scheduling.LOADED):
    for path,expected in dependency.items():
        if path in LOADED and LOADED[path]!=expected:raise ValueError('Conflicting loaded source')
        LOADED[path]=expected
FLAGS=dict.fromkeys(('fit_performed','wrapper_called','source_bytes_authenticated','source_bytes_reverified_at_call','identity_authenticated','point_in_time_verified','promotion_allowed','legal_training_input_admitted','execution_authorized','all_plan_tasks_completed','full_shard_completed','old_task_readback_repeated','old_weight_values_reaudited','anchor_alias_equivalence_verified'),False)

def require(ok,message):
    if not ok:raise ValueError(message)

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def reference(value):
    require(type(value) is dict and set(value)=={'path','sha256'} and type(value['path']) is str and value['path'] and type(value['sha256']) is str and len(value['sha256'])==64 and all(c in '0123456789abcdef' for c in value['sha256']),'Explicit content reference required')
    return deepcopy(value)

def completed_lookup(envelope,plan_ref,context):
    require(type(envelope) is dict and set(envelope)=={'reference','document'},'Completed source envelope required')
    ref=reference(envelope['reference']);doc=envelope['document']
    require(doc['schema']=='BULK_COMPLETED_TASK_REBINDING_V1' and type(doc['externally_rebound_task_count']) is int and doc['externally_rebound_task_count']==504 and type(doc['externally_rebound_combination_count']) is int and doc['externally_rebound_combination_count']==168,'Full saved504/168 inventory')
    require(doc['input_references']['plan']==plan_ref and doc['numerical_contracts_unchanged'] is True,'Completed rebinding plan reference')
    for k in ('fit_performed','task_readback_repeated','materialization_repeated','promotion_allowed','legal_training_input_admitted','point_in_time_verified','execution_authorized'):require(doc[k] is False,'Saved authority upgrade')
    require(type(doc['rows']) is list and len(doc['rows'])==504,'Full saved row denominator')
    by={};combos={}
    for i,row in enumerate(doc['rows']):
        previous=row['old_completed_row'];task=previous['full_task'];identity=task['numerical_identity'];tid=digest(identity)
        require(previous['status'] in {'FITTED_FIVE_RISKS_PASSED','COMPLETED_EXTERNALLY_AUDITED_ORIGINAL_FIVE_RISKS_PASSED'},'Saved original completed status')
        for key in ('started_reference','raw_reference','postcheck_reference','independent_readback_reference'):reference(previous[key])
        require(row['status']=='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND' and type(row['new_wrapper_call_attempt_count']) is int and row['new_wrapper_call_attempt_count']==0,'Saved reference-only completed state')
        require(tid==task['numerical_task_id']==row['numerical_task_id']==row['old_completed_row']['numerical_task_id'] and tid not in by,'Unique complete numerical identity')
        require(digest(task['location_identity'])==task['location_id'] and digest(row['new_location_identity'])==row['new_location_id'] and row['new_location_identity']['plan_reference']==plan_ref,'Saved location hashes')
        require(identity['weight_spec'] in context['weight_specs'] and digest(identity['parameters'])==digest(context['parameters']) and digest(identity['requested_previous_target_weights'])==digest(context['previous_target_weights']) and identity['fitter_source_fingerprint']==context['fitter_source_fingerprint'] and identity['cutoff']==context['decision_cutoff'],'Completed original numeric contract differs')
        require(row['verified_fit_data_sha256']==identity['fit_data_sha256']==row['old_completed_row']['fit_data_sha256'],'Saved matrix linkage')
        by[tid]=(row,dict(ref,json_pointer='/rows/'+str(i)))
        key=tuple(sorted(identity['selected']));combos.setdefault(key,[]).append(identity['weight_spec'])
    require(len(combos)==168 and all(len(v)==3 and set(v)==set(context['weight_specs']) for v in combos.values()),'Full saved three-spec combinations')
    return by,ref

def materialize_positions(*,lazy_plan,plan_reference,panel,positions,max_combinations,completed_rebinding):
    require(LOADED[str(Path(old.__file__).resolve())]==HARD_OLD and all(old.LOADED[p]==h for p,h in old.HARD_SOURCES.items()),'Frozen panel validator differs')
    require(type(SCHEDULE_SHA) is str and LOADED[str(Path(scheduling.__file__).resolve())]==SCHEDULE_SHA,'Schedule validator source pending/different')
    plan_ref=reference(plan_reference);index=scheduling.validate_lazy_plan(lazy_plan);ctx=lazy_plan['context']
    require(type(max_combinations) is int and 1<=max_combinations<=10000,'Explicit bounded combination budget1..10000')
    require(type(positions) is list and len(positions)<=max_combinations,'Positions exceed declared budget')
    require(len(lazy_plan['fitter_source_hashes'])==25,'Complete frozen25 numerical sources')
    matrix,by_sid=old.validate_panel(panel,ctx,index)
    prior=ctx['previous_target_weights']
    if prior is not None:require(math.isclose(sum(float(v) for v in prior.values()),1.,rel_tol=0,abs_tol=1e-12),'Full prior fails fitter mass gate')
    completed,completed_ref=completed_lookup(completed_rebinding,plan_ref,ctx)
    saved=completed_rebinding['document'];total=lazy_plan['planned_canonical_task_count']
    require(type(total) is int and type(saved['full_plan_task_denominator']) is int and saved['full_plan_task_denominator']==total and type(saved['remaining_uncompleted_task_count']) is int and saved['remaining_uncompleted_task_count']==total-504,'Completed/global denominator differs')
    require(type(saved['new_wrapper_call_attempt_count']) is int and saved['new_wrapper_call_attempt_count']==0 and type(saved['new_fit_count']) is int and saved['new_fit_count']==0,'Reference-only saved zero operations')
    seen=set();proposal_seen=set();prepared=[]
    for pos in positions:
        require(type(pos) is dict and set(pos)=={'k','rank','prefix_security_ids','selection_kind','proposal_index'},'Exact selection position fields')
        k,rank,proposal=pos['k'],pos['rank'],pos['proposal_index'];prefix=pos['prefix_security_ids']
        require(type(k) is int and type(rank) is int and type(proposal) is int and proposal>=0 and proposal not in proposal_seen,'Exact unique proposal integers')
        require(pos['selection_kind'] in {'SID_COVERAGE','STRATIFIED_RANK','STRATIFIED_REFILL'},'Known selection policy')
        require(1<=k<=len(lazy_plan['cardinalities']),'k out of range');card=lazy_plan['cardinalities'][k-1]
        require(card['k']==k and card['planned_combination_count']>0 and 0<=rank<card['planned_combination_count'] and (k,rank) not in seen,'Retained unique rank')
        require(type(prefix) is list and len(prefix)==k and len(set(prefix))==k and all(type(s) is str and s in by_sid for s in prefix),'Complete known SID prefix')
        require(prefix==sorted(prefix,key=lambda s:(by_sid[s]['issuer_id'],s)) and len({by_sid[s]['issuer_id'] for s in prefix})==k,'Issuer-prefix ordering and uniqueness')
        require(index.rank(k,prefix)==rank,'Position rank does not match explicit prefix')
        seen.add((k,rank));proposal_seen.add(proposal);prepared.append((pos,card))
    # All requested coordinates and the full matrix were validated before any unrank.
    locations={ticker:i for i,ticker in enumerate(panel['columns'])};combinations=[];reused=[];new=[]
    for pos,card in prepared:
        k,rank=pos['k'],pos['rank'];prefix=list(index.unrank(k,rank));require(prefix==pos['prefix_security_ids'],'Unrank differs from validated position')
        order=sorted(prefix);selected={sid:{key:by_sid[sid][key] for key in ('ticker','issuer_id','risk_chain')} for sid in order};tickers=[selected[s]['ticker'] for s in order]
        payload=dict(dates=deepcopy(panel['dates']),tickers=tickers,returns=[[row[locations[t]] for t in tickers] for row in matrix]);matrix_sha=digest(payload)
        start=(rank//ctx['shard_size'])*ctx['shard_size'];stop=min(start+ctx['shard_size'],card['planned_combination_count']);shard_id=digest(dict(ctx,k=k,start=start,stop=stop));tasks=[]
        for spec_index,spec in enumerate(ctx['weight_specs']):
            numerical=dict(schema=old.NUMERICAL_ID_SCHEMA,cutoff=ctx['decision_cutoff'],holding_count=k,selected=deepcopy(selected),weight_spec=spec,parameters=deepcopy(ctx['parameters']),requested_previous_target_weights=deepcopy(prior),fit_data_sha256=matrix_sha,fitter_source_fingerprint=ctx['fitter_source_fingerprint'])
            location=dict(schema=old.LOCATION_ID_SCHEMA,plan_reference=deepcopy(plan_ref),plan_id=lazy_plan['plan_id'],shard_id=shard_id,order_version=ctx['order_version'],group_fingerprint=ctx['group_fingerprint'],k=k,rank=rank,spec_index=spec_index,weight_spec=spec)
            tid=digest(numerical);lid=digest(location);matched=completed.get(tid)
            task=dict(numerical_task_id=tid,numerical_identity=numerical,location_id=lid,location_identity=location,expected_fitter_previous_target_weights={} if prior is None else deepcopy(prior),wrapper_call_attempt_count=0,fit_performed=False,anchor_alias_equivalence_verified=False)
            if matched:
                row,cref=matched;require(row['old_completed_row']['full_task']['numerical_identity']==numerical and row['new_location_identity']==location and row['new_location_id']==lid,'Completed hash requires exact identity/location equality')
                task.update(status='EXTERNALLY_COMPLETED_REFERENCE_ONLY',completed_reference=deepcopy(cref),complete_saved_rebinding_row=deepcopy(row));reused.append(tid)
            else:task.update(status='MATERIALIZED_NOT_ATTEMPTED',completed_reference=None,complete_saved_rebinding_row=None);new.append(tid)
            tasks.append(task)
        combinations.append(dict(k=k,rank=rank,prefix_security_ids=prefix,fitter_sorted_security_ids=order,selection_position=deepcopy(pos),fit_matrix=payload,fit_data_sha256=matrix_sha,tasks=tasks))
    exposures={}
    for combo in combinations:
        entry=exposures.setdefault(str(combo['k']),dict(combination_count=0,security_occurrence_count=0,risk_chain_occurrence_counts={},security_occurrences=[]));entry['combination_count']+=1
        for sid,coordinate in combo['tasks'][0]['numerical_identity']['selected'].items():
            risk=coordinate['risk_chain'];entry['risk_chain_occurrence_counts'][risk]=entry['risk_chain_occurrence_counts'].get(risk,0)+1;entry['security_occurrence_count']+=1
            entry['security_occurrences'].append(dict(rank=combo['rank'],security_id=sid,**coordinate))
    return dict(schema=SCHEMA,status='BOUNDED_INPUTS_MATERIALIZED_NO_EXECUTION',plan_reference=plan_ref,plan_id=lazy_plan['plan_id'],panel_reference=deepcopy(ctx['panel_reference']),panel_audit_reference=deepcopy(ctx['panel_audit_reference']),panel_content_sha256=panel['panel_content_sha256'],fitter_source_hashes=deepcopy(lazy_plan['fitter_source_hashes']),completed_rebinding_reference=completed_ref,complete_saved_completed_task_count=504,selected_completed_intersection_count=len(reused),new_unattempted_task_count=len(new),materialized_task_count=3*len(combinations),combination_count=len(combinations),max_combinations=max_combinations,full_plan_task_denominator=total,remaining_full_plan_uncompleted_count=total-504,selected_completed_numerical_task_ids=reused,new_unattempted_numerical_task_ids=new,combinations=combinations,materializer_loaded_source_hashes=deepcopy(LOADED),risk_chain_exposures=exposures,risk_chain_exposure_definition='SECURITY_OCCURRENCES_IN_COMBINATIONS_NOT_WEIGHT_OR_NEW_RISK_GATE',new_wrapper_call_attempt_count=0,new_fit_count=0,**FLAGS)
