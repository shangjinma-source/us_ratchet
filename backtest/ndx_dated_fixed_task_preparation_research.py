"""New dated numeric tasks for an unchanged, explicitly late selected batch."""
from copy import deepcopy
from datetime import date
import hashlib,json,math

SCHEMA='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_V1'
PARAMETERS=dict(fit_days=126,max_single_weight=.45,min_single_weight=.05,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55,shrinkage_intensity=.35,top_weight_cap=.8,turnover_anchor_strength=.25)
SPECS=['equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor']
FULL_TASK_COUNT=6222659648236112670
FLAGS=dict.fromkeys(('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted','old_fit_results_reused','old_weights_reused','old_raw_reaudited','old_task_completion_applies_to_new_cutoff','evaluation_values_used_for_fit','historical_pool_eligibility_verified','historical_selection_timeliness_verified','all_plan_tasks_completed','global_optimum_proven','future_independent_oos','untouched_holdout','source_bytes_authenticated'),False)


def require(ok,msg):
    if not ok:raise ValueError(msg)


def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def digest(v):return hashlib.sha256(encode(v)).hexdigest()


def exact(a,b,msg):require(encode(a)==encode(b),msg)


def ref(r):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'],'Exact reference')
    require(type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Reference hash')


def prepare_dated_tasks(*,training_panel,training_reference,training_readback_reference,prior_preparation,prior_preparation_reference,original_lazy_plan,original_plan_reference):
    for r in (training_reference,training_readback_reference,prior_preparation_reference,original_plan_reference):ref(r)
    panel=training_panel;old=prior_preparation;plan=original_lazy_plan;ctx=plan['context']
    require(panel['schema']=='DATED_CONDITIONAL_TRAINING_PANEL_V1' and panel['content_sha256']==digest({k:v for k,v in panel.items() if k!='content_sha256'}),'Dated panel content/schema')
    for k in ('point_in_time_verified','execution_authorized','legal_training_input_admitted','fit_performed','evaluation_values_in_fit_payload','old_task_weights_reused','liquidity_qualification_at_training_cutoff_verified'):require(panel[k] is False,'Training authority changed')
    payload=panel['fit_payload'];require(set(payload)=={'cutoff','returns','selected_by_security'} and payload['cutoff']=='2026-03-20','Exact fitting input keys/cutoff')
    frame=payload['returns'];require(frame['type']=='DataFrame' and frame['index_type']=='DatetimeIndex' and frame['dtypes']==['float64']*77,'New typed frame')
    require(len(frame['index'])==len(frame['data'])==126 and len(frame['columns'])==77 and frame['columns']==sorted(set(frame['columns'])),'Full126x77 matrix')
    days=[]
    for t in frame['index']:
        require(type(t) is str and t==t[:10]+'T00:00:00' and date.fromisoformat(t[:10]).isoformat()==t[:10],'Exact training timestamp');days.append(t[:10])
    require(days==sorted(set(days)) and days[-1]=='2026-03-20','Training dates cannot contain later evaluation')
    require(all(type(row) is list and len(row)==77 and all(type(v) is float and math.isfinite(v) and v>-1 for v in row) for row in frame['data']),'Finite exact float matrix')
    selected=payload['selected_by_security'];require(type(selected) is dict and len(selected)==77 and list(selected)==sorted(selected),'Canonical77 SID mapping')
    for value in selected.values():require(set(value)=={'ticker','issuer_id','risk_chain'} and all(type(v) is str and v for v in value.values()),'Selected three fields')
    require(sorted(v['ticker'] for v in selected.values())==frame['columns'] and len({v['issuer_id'] for v in selected.values()})==76,'Complete SID/ticker mapping')
    exact(panel['training_frame_sha256'],digest(frame),'Training frame digest');exact(panel['fit_payload_sha256'],digest(payload),'Training fitting digest')
    # The saved exact-to-float evidence independently fixes all 9702 cell values.
    evidence=panel['numeric_conversion_evidence'];require(len(evidence)==77 and {r['security_id'] for r in evidence}==set(selected),'All conversion evidence')
    bycol={t:i for i,t in enumerate(frame['columns'])}
    from fractions import Fraction
    for row in evidence:
        sid=row['security_id'];require(row['ticker']==selected[sid]['ticker'] and len(row['rows'])==126,'Evidence coordinate')
        for i,item in enumerate(row['rows']):
            v=frame['data'][i][bycol[row['ticker']]];require(item['session']==days[i] and item['float_hex']==v.hex() and float(Fraction(item['exact_return']))==v,'Training cell differs from saved exact evidence')
    require(plan['schema']=='ISSUER_ALL_K_LAZY_INTERVAL_PLAN_V1' and len(plan['cardinalities'])==76,'Original all-k domain retained')
    require([r['k'] for r in plan['cardinalities']]==list(range(1,77)) and all(type(r['k']) is int for r in plan['cardinalities']),'Exact all-k range')
    require(type(plan['planned_canonical_task_count']) is int and plan['planned_canonical_task_count']==FULL_TASK_COUNT,'Original entire domain denominator')
    exact(ctx['parameters'],PARAMETERS,'Original risk/fit parameters');exact(ctx['weight_specs'],SPECS,'All three specifications');require(ctx['decision_cutoff']=='2026-09-21' and ctx['previous_target_weights'] is None,'Original None prior/cutoff')
    sources=plan['fitter_source_hashes'];require(type(sources) is dict and len(sources)==25 and all(type(p) is str and type(h) is str and len(h)==64 and all(c in '0123456789abcdef' for c in h) for p,h in sources.items()),'Frozen25 source map')
    require(digest(sources)==ctx['fitter_source_fingerprint'],'Fitter source fingerprint')
    require(old['schema']=='BULK_BUDGETED_SEARCH_PREPARATION_V1' and old['status']=='PREPARED_NOT_ATTEMPTED','Original saved preparation')
    for k in ('fit_performed','point_in_time_verified','legal_training_input_admitted','execution_authorized','winner_selected'):require(old[k] is False,'Original research selection only')
    materialized=old['materialized'];require(materialized['plan_reference']==original_plan_reference and materialized['plan_id']==plan['plan_id'],'Original plan binding')
    exact(materialized['fitter_source_hashes'],sources,'Original25 sources');require(type(materialized['materialized_task_count']) is int and materialized['materialized_task_count']==1632 and type(materialized['combination_count']) is int and materialized['combination_count']==544,'Full saved544/1632')
    require(materialized['full_plan_task_denominator']==FULL_TASK_COUNT and type(materialized['full_plan_task_denominator']) is int,'Original full task denominator')
    combos=materialized['combinations'];positions=old['schedule']['positions'];require(len(combos)==len(positions)==544,'All saved positions, no results filtering')
    context=dict(cutoff='2026-03-20',training_reference=deepcopy(training_reference),training_readback_reference=deepcopy(training_readback_reference),prior_preparation_reference=deepcopy(prior_preparation_reference),original_plan_reference=deepcopy(original_plan_reference),training_frame_sha256=panel['training_frame_sha256'],parameters=deepcopy(PARAMETERS),weight_specs=deepcopy(SPECS),requested_previous_target_weights=None,fitter_source_fingerprint=ctx['fitter_source_fingerprint'])
    context_id=digest(context);new=[];oldids=set();newids=set();counts={k:0 for k in range(4,21)};seen=set()
    for ci,combo in enumerate(combos):
        k=combo['k'];rank=combo['rank'];prefix=combo['prefix_security_ids'];order=combo['fitter_sorted_security_ids']
        require(type(k) is int and k in counts and type(rank) is int and rank>=0 and (k,rank) not in seen,'Unique original position');seen.add((k,rank));counts[k]+=1
        card=plan['cardinalities'][k-1];require(type(card['planned_combination_count']) is int and rank<card['planned_combination_count'],'Original retained rank bounds')
        require(type(prefix) is list and len(prefix)==k and set(prefix)<=set(selected) and len(set(prefix))==k and order==sorted(prefix),'Original canonical SID order')
        require(prefix==sorted(prefix,key=lambda s:(selected[s]['issuer_id'],s)) and len({selected[s]['issuer_id'] for s in prefix})==k,'Issuer-prefix order')
        exact(combo['selection_position'],positions[ci],'Saved selection position exact');require(positions[ci]['k']==k and positions[ci]['rank']==rank and positions[ci]['prefix_security_ids']==prefix,'Position fields differ')
        chosen={sid:deepcopy(selected[sid]) for sid in order};tickers=[chosen[sid]['ticker'] for sid in order]
        matrix=dict(dates=deepcopy(days),tickers=tickers,returns=[[r[bycol[t]] for t in tickers] for r in frame['data']]);matrix_sha=digest(matrix)
        oldmatrix=combo['fit_matrix'];require(digest(oldmatrix)==combo['fit_data_sha256'] and len(oldmatrix['dates'])==126 and oldmatrix['dates'][-1]=='2026-09-21' and oldmatrix['dates'][0]=='2026-03-23','Original matrix provenance and dates')
        require(oldmatrix['tickers']==tickers and len(oldmatrix['returns'])==126 and all(len(r)==k and all(type(v) is float and math.isfinite(v) and v>-1 for v in r) for r in oldmatrix['returns']),'Old matrix coordinate encoding')
        require(matrix_sha!=combo['fit_data_sha256'],'Old matrix cannot be reused at earlier cutoff');tasks=[];require(len(combo['tasks'])==3,'All original specifications')
        for si,spec in enumerate(SPECS):
            previous=combo['tasks'][si];identity=previous['numerical_identity'];oid=digest(identity);location=previous['location_identity']
            require(previous['status']=='MATERIALIZED_NOT_ATTEMPTED' and type(previous['wrapper_call_attempt_count']) is int and previous['wrapper_call_attempt_count']==0 and previous['fit_performed'] is False,'Original preparation is not a weight result')
            expected=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff='2026-09-21',holding_count=k,selected=chosen,weight_spec=spec,parameters=PARAMETERS,requested_previous_target_weights=None,fit_data_sha256=combo['fit_data_sha256'],fitter_source_fingerprint=ctx['fitter_source_fingerprint'])
            exact(identity,expected,'Old complete numeric contract differs');require(oid==previous['numerical_task_id'] and oid not in oldids,'Original unique numerical ID');oldids.add(oid)
            require(digest(location)==previous['location_id'] and location['schema']=='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1' and location['plan_reference']==original_plan_reference and location['plan_id']==plan['plan_id'] and type(location['spec_index']) is int and location['spec_index']==si and location['k']==k and location['rank']==rank and location['weight_spec']==spec,'Original location binding')
            start=rank//ctx['shard_size']*ctx['shard_size'];stop=min(start+ctx['shard_size'],card['planned_combination_count'])
            expected_location=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=original_plan_reference,plan_id=plan['plan_id'],shard_id=digest(dict(ctx,k=k,start=start,stop=stop)),order_version=ctx['order_version'],group_fingerprint=ctx['group_fingerprint'],k=k,rank=rank,spec_index=si,weight_spec=spec)
            exact(location,expected_location,'Complete original location contract')
            numeric=dict(deepcopy(expected),cutoff='2026-03-20',fit_data_sha256=matrix_sha);tid=digest(numeric);require(tid not in oldids and tid not in newids,'New unique dated numeric ID');newids.add(tid)
            priorref=dict(prior_preparation_reference,json_pointer=f'/materialized/combinations/{ci}/tasks/{si}')
            loc=dict(schema='DATED_FIXED_CONSTITUENT_TASK_LOCATION_V1',dated_context_id=context_id,training_reference=deepcopy(training_reference),prior_task_reference=priorref,prior_location_id=previous['location_id'],original_plan_reference=deepcopy(original_plan_reference),combination_index=ci,k=k,rank=rank,spec_index=si,weight_spec=spec)
            tasks.append(dict(numerical_task_id=tid,numerical_identity=numeric,location_id=digest(loc),location_identity=loc,expected_fitter_previous_target_weights={},status='MATERIALIZED_NOT_ATTEMPTED',wrapper_call_attempt_count=0,fit_performed=False,completed_reference=None,prior_different_cutoff_task_reference=priorref,complete_prior_different_cutoff_task=deepcopy(previous)))
        new.append(dict(k=k,rank=rank,prefix_security_ids=deepcopy(prefix),fitter_sorted_security_ids=deepcopy(order),selection_position=deepcopy(combo['selection_position']),fit_matrix=matrix,fit_data_sha256=matrix_sha,tasks=tasks))
    require(all(n==32 for n in counts.values()) and not (oldids&newids),'Fixed32 per k, no old dated identity reuse')
    result=dict(schema=SCHEMA,status='PREPARED_NOT_ATTEMPTED',context=context,context_id=context_id,combinations=new,combination_count=544,materialized_task_count=1632,new_unattempted_task_count=1632,new_wrapper_call_attempt_count=0,new_fit_count=0,new_unattempted_numerical_task_ids=[t['numerical_task_id'] for c in new for t in c['tasks']],prior_different_cutoff_numerical_task_ids=[t['numerical_task_id'] for c in combos for t in c['tasks']],full_plan_task_denominator=FULL_TASK_COUNT,new_cutoff_completed_task_count=0,remaining_new_cutoff_uncompleted_task_count=FULL_TASK_COUNT,original_all_k_cardinalities_preserved=deepcopy(plan['cardinalities']),original_selection_schedule_preserved=deepcopy(old['schedule']),training_reference=deepcopy(training_reference),training_readback_reference=deepcopy(training_readback_reference),fitter_source_hashes=deepcopy(sources),late_pool_and_composition_selection=True,historical_retrospective_only=True,selection_scope='FIXED_PREVIOUSLY_CHOSEN_544_COMPOSITIONS_NOT_HISTORICALLY_KNOWN_OR_RESELECTED',**FLAGS)
    result['content_sha256']=digest(result);return result
