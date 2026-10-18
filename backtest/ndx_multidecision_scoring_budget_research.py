"""Six causal conditional budgets; sampling keys exclude price/source artifacts."""
from copy import deepcopy
from fractions import Fraction
import hashlib,json,re
from datetime import date
from backtest import ndx_issuer_combination_index_research as indexing
from backtest import ndx_membership_cardinality_plan_research as bounds

CUTOFFS=('2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31')
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
BUDGET=dict(combinations_per_retained_k=32,max_proposals_per_decision=4096,proposal_scope='ALL_K_WITHIN_ONE_CUTOFF_INCLUDING_REJECTIONS',small_domain_policy='MIN_32_OR_FULL_DOMAIN_COUNT')
PARAMETERS=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
ORDER='MULTIDECISION_ISSUER_COVER_STRATIFIED_RANK_V1'
POLICY_SOURCE_SHA='6cc7f67093ba996b7cad0c6e24acbc3691a457930103872b8105b6a44c38424f'
POLICY_CONTENT_SHA='830f84b80ef1728f6e55eecb2b16b7c337f2b0188388ba9c8525250eed2a5068'
SEED_TEXT='NDX_MULTIDECISION_CONDITIONAL_SCORE_ROUND1_20261003'
MATH_SOURCES=dict(issuer_index='bc24b924ba53f093f7f9bfc05fd237234fbed851ff5d32f7b41324a08594d87b',necessary_bounds='4f433404895070613d217acc8a245e6fb346f2835652fe1a934eb2be909c943c')


def require(ok,message):
    if not ok:raise ValueError(message)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def exact(a,b,message):require(digest(a)==digest(b),message)
def text(v):require(type(v) is str and v and v==v.strip(),'Canonical string');return v
def ref(r):
    require(type(r) is dict and {'path','sha256'}<=set(r),'Explicit reference');text(r['path']);require(type(r['sha256']) is str and re.fullmatch('[a-f0-9]{64}',r['sha256']) is not None,'Reference SHA')
def group_rows(securities):
    d={}
    for row in securities:d.setdefault(row['issuer_id'],[]).append(row['security_id'])
    return [dict(issuer_id=i,security_ids=sorted(d[i])) for i in sorted(d)]
def index_for(groups):return indexing.IssuerCombinationIndex([(g['issuer_id'],g['security_ids']) for g in groups])
def cards(index):
    risk={k:Fraction(str(PARAMETERS[k])) for k in bounds._RISK_KEYS}
    return [dict(k=k,combination_count=n,necessary_bound_certificates=bounds._necessary_bounds(k,risk)) for k,n in index.counts_by_k().items()]


def sample_positions(index,context,cards_):
    positions=[];log=[];coverage=[];strata=[]
    seed=digest(context);limit=BUDGET['max_proposals_per_decision']
    for card in cards_:
        k=card['k'];total=card['combination_count'];wanted=0 if card['necessary_bound_certificates'] else min(32,total);chosen=set()
        permutation=sorted(range(len(index.issuer_ids)),key=lambda i:(digest([ORDER,seed,k,index.issuer_ids[i]]),index.issuer_ids[i]))
        base=[]
        if wanted:
            n=len(permutation)
            for start in range(0,n,k):base.append(tuple(index.security_groups[i][0] for i in sorted(permutation[(start+j)%n] for j in range(k))))
            for i,g in enumerate(index.security_groups):
                original=next(row for row in base if g[0] in row)
                for sid in g[1:]:base.append(tuple(sid if x==g[0] else x for x in original))
        covers=[];seen=set()
        for row in base:
            rank=index.rank(k,row)
            if rank not in seen:covers.append(rank);seen.add(rank)
        require(len(covers)<=wanted,'32-point budget cannot cover supplied SID domain')
        def accept(rank,kind,extra):
            if len(log)>=limit:return
            duplicate=rank in chosen;entry=dict(proposal_index=len(log),k=k,rank=rank,selection_kind=kind,outcome='DUPLICATE' if duplicate else 'ACCEPTED',**extra);log.append(entry)
            if not duplicate:
                chosen.add(rank);positions.append(dict(k=k,rank=rank,security_ids=list(index.unrank(k,rank)),selection_kind=kind,proposal_index=entry['proposal_index']))
        def draw(lo,hi,kind,ordinal,attempt):
            if len(log)>=limit:return
            width=hi-lo;bits=(width-1).bit_length();size=max(1,(bits+7)//8);blob=b'';block=0
            while len(blob)<size:
                blob+=bytes.fromhex(digest([ORDER,seed,k,kind,ordinal,attempt,block]));block+=1
            raw=int.from_bytes(blob[:size],'big')&((1<<bits)-1)
            extra=dict(interval_start=lo,interval_stop=hi,stratum_index=ordinal,draw_index=attempt)
            if raw>=width:log.append(dict(proposal_index=len(log),k=k,rank=None,selection_kind=kind,outcome='HASH_RANGE_REJECTED',**extra))
            else:accept(lo+raw,kind,extra)
        for rank in covers:accept(rank,'SID_COVERAGE',{})
        remainder=wanted-len(covers)
        for j in range(remainder):
            lo=j*total//remainder;hi=(j+1)*total//remainder;strata.append(dict(k=k,stratum_index=j,start=lo,stop=hi));attempt=0
            while len(log)<limit and sum(lo<=r<hi for r in chosen)<hi-lo:
                before=len(chosen);draw(lo,hi,'STRATIFIED_RANK',j,attempt);attempt+=1
                if len(chosen)>before:break
        attempt=0
        while len(chosen)<wanted and len(log)<limit:draw(0,total,'STRATIFIED_REFILL',-1,attempt);attempt+=1
        exposures={sid:0 for g in index.security_groups for sid in g}
        for p in positions:
            if p['k']==k:
                for sid in p['security_ids']:exposures[sid]+=1
        coverage.append(dict(**deepcopy(card),requested_position_count=wanted,selected_position_count=len(chosen),unprocessed_requested_position_count=wanted-len(chosen),unsearched_combination_count=total-len(chosen),security_exposures=exposures,all_security_ids_covered=bool(wanted) and all(exposures.values())))
    complete=all(c['requested_position_count']==c['selected_position_count'] for c in coverage)
    return dict(status='PLANNED_NOT_ATTEMPTED' if complete else 'INCOMPLETE_POINT_SELECTION',positions=positions,cardinality_coverage=coverage,proposal_log=log,proposal_count=len(log),strata=strata,complete=complete)


def plan_multidecision_scoring_budget(*,registration,registration_reference,universe,decisions):
    ref(registration_reference)
    require(type(POLICY_SOURCE_SHA) is str and registration_reference['sha256']==POLICY_SOURCE_SHA,'Frozen actual policy reference')
    require(digest(registration)==POLICY_CONTENT_SHA,'Complete frozen policy semantics')
    require(registration['schema']=='MULTIDECISION_CONDITIONAL_SCORING_POLICY_V1','Explicit actual policy')
    seed_text=registration['budget']['seed_text'];require(seed_text==SEED_TEXT,'Registered seed text')
    require(type(universe) is list and 0<len(universe)<=512,'Full supplied inventory')
    for u in universe:
        for k in ('security_id','issuer_id','ticker'):text(u[k])
    require(len({u['security_id'] for u in universe})==len(universe) and len({u['ticker'] for u in universe})==len(universe),'Unique SID and ticker inventory')
    require(len(universe)==77 and len({u['issuer_id'] for u in universe})==76,'Full77/76 inventory cannot be replaced by eligible subpool')
    full_groups=group_rows(universe);full_index=index_for(full_groups);full_cards=cards(full_index);by={u['security_id']:u for u in universe}
    require(type(decisions) is list and len(decisions)==6,'Six full decision inputs');results=[]
    for row,cutoff in zip(decisions,CUTOFFS):
        require(row['cutoff']==cutoff,'Original six cutoff order');ref(row['scoring_data_reference']);ref(row['fitter_source_reference']);ref(row['incumbent_fee_reference'])
        dates=row['scoring_price_dates'];require(type(dates) is list and len(dates)==505 and dates==sorted(set(dates)) and dates[-1]==cutoff and all(type(d) is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5 for d in dates),'Full same-cutoff505 dates')
        require(type(row['qualifications']) is list and [q['security_id'] for q in row['qualifications']]==[u['security_id'] for u in universe],'All inventory qualification rows in original order')
        eligible=[];excluded=[]
        for q in row['qualifications']:
            sid=q['security_id'];require(q['cutoff']==cutoff,'Same-cutoff qualification')
            for field in ('history_13_complete','mdv_available','conditional_member_scope_passed'):require(type(q[field]) is bool,'Exact qualification boolean')
            require(q['liquidity_passed'] is None or type(q['liquidity_passed']) is bool,'Unknown liquidity is explicit')
            require(q['mdv_available'] or q['liquidity_passed'] is not True,'Unknown MDV cannot pass')
            mdv=q['mdv_evidence'];require(mdv['coordinate']['security_id']==sid and mdv['formal_eligibility_verified'] is False,'Original conditional MDV coordinate')
            exact(mdv['required_dates'],dates[-63:],'Causal63-date MDV window')
            value=mdv['median_dollar_volume_exact']
            if value is None:
                require(mdv['status']=='UNKNOWN_LIQUIDITY' and q['mdv_available'] is False and q['liquidity_passed'] is None and mdv['conditional_numerical_threshold_passed'] is None,'Unknown MDV preserved')
            else:
                require(type(value) is str and Fraction(value)>=0 and mdv['status']=='CONDITIONAL_MDV_COMPUTABLE' and q['mdv_available'] is True,'Exact saved MDV')
                passed=Fraction(value)>=50000000
                require(q['liquidity_passed'] is passed and mdv['conditional_numerical_threshold_passed'] is passed,'Frozen50M threshold')
            ref(q['history_reference']);ref(q['mdv_reference']);require(type(q['reasons']) is list and all(type(v) is str and v for v in q['reasons']),'Preserved qualification reasons')
            reasons=[]
            if not q['history_13_complete']:reasons.append('BLOCKED_FULL13_HISTORY')
            if not q['mdv_available']:reasons.append('UNKNOWN_MDV_SUPPLY')
            if q['liquidity_passed'] is not True:reasons.append('LIQUIDITY_GATE_NOT_PASSED')
            if not q['conditional_member_scope_passed']:reasons.append('CONDITIONAL_MEMBER_SCOPE_NOT_PASSED')
            if reasons:excluded.append(dict(security_id=sid,reasons=reasons,original_qualification=deepcopy(q)))
            else:eligible.append(by[sid])
        modes=row['mode_sources'];require(type(modes) is list and [m['mode'] for m in modes]==list(MODES),'Both FX source modes, no substitution')
        for m in modes:ref(m['reference']);require(type(m['complete_thirteen_windows']) is bool,'Full13 mode source state')
        groups=group_rows(eligible)
        context=dict(algorithm_version=ORDER,seed_text=seed_text,decision_cutoff=cutoff,canonical_issuer_security_groups=groups,static_budget=deepcopy(BUDGET))
        if groups:
            index=index_for(groups);eligible_cards=cards(index);sample=sample_positions(index,context,eligible_cards)
        else:eligible_cards=[];sample=dict(status='NO_SCORABLE_SECURITIES',positions=[],cardinality_coverage=[],proposal_log=[],proposal_count=0,strata=[],complete=True)
        mode_plans=[]
        for mode in modes:
            tasks=[]
            if sample['complete']:
                for position in sample['positions']:
                    for spec in SPECS:
                        identity=dict(schema='MULTIDECISION_CAUSAL_SCORING_JOB_IDENTITY_V1',cutoff=cutoff,fx_mode=mode['mode'],security_ids=position['security_ids'],weight_spec=spec,parameters=PARAMETERS,scoring_data_reference=row['scoring_data_reference'],target_reference=mode['reference'],fitter_source_reference=row['fitter_source_reference'],scoring_window_contract=dict(price_count=505,fit_return_count=126,evaluation_return_count=126,step_return_count=21,window_count=13),internal_initial_previous_weights=None,inner_rolling_fit_prior='FIRST_WINDOW_NONE_THEN_SAME_CANDIDATE_PREVIOUS_WINDOW_TARGET',candidate_transaction_cost_bps=10,candidate_turnover_cost_formula='0.5*SUM_ABS_TARGET_MINUS_REFERENCE*10/10000',first_candidate_fee_reference=deepcopy(row['incumbent_fee_reference']),fee_reference_policy='FIRST_NORMALIZED_ORIGINAL_CONTROL_THEN_SAME_CANDIDATE_PREVIOUS_TARGET',outer_lane_prior_applied=False)
                        tasks.append(dict(job_id=digest(identity),identity=deepcopy(identity),position=deepcopy(position),status='PLANNED_NOT_ATTEMPTED' if mode['complete_thirteen_windows'] else 'SOURCE_BLOCKED'))
            status='INCOMPLETE_POINT_SELECTION' if not sample['complete'] else 'SOURCE_BLOCKED' if not mode['complete_thirteen_windows'] else 'NO_RETAINED_CANDIDATES' if not tasks else 'PLANNED_NOT_ATTEMPTED'
            mode_plans.append(dict(mode=mode['mode'],status=status,source_preserved=deepcopy(mode),tasks=tasks,task_count=len(tasks),score_dispatch_authorized=False))
        eligible_by_k={c['k']:c for c in eligible_cards};selected_by_k={c['k']:c['selected_position_count'] for c in sample['cardinality_coverage']};domain=[]
        for c in full_cards:
            e=eligible_by_k.get(c['k']);count=0 if e is None else e['combination_count'];n=selected_by_k.get(c['k'],0);excluded_by_bound=count if c['necessary_bound_certificates'] else 0
            domain.append(dict(k=c['k'],full_inventory_combination_count=c['combination_count'],qualification_excluded_combination_count=c['combination_count']-count,eligible_pool_combination_count=count,necessary_bound_excluded_combination_count=excluded_by_bound,selected_combination_count=n,unsearched_eligible_after_bounds=count-excluded_by_bound-n,unselected_full_domain_combination_count=c['combination_count']-n,full_three_spec_task_denominator=3*c['combination_count'],necessary_bound_certificates=deepcopy(c['necessary_bound_certificates'])))
        results.append(dict(domain_coverage=domain,cutoff=cutoff,universe_preserved=deepcopy(universe),qualification_rows_preserved=deepcopy(row['qualifications']),excluded_securities=excluded,eligible_security_ids=[u['security_id'] for u in eligible],canonical_eligible_groups=groups,full_inventory_cardinalities=deepcopy(full_cards),eligible_pool_cardinalities=eligible_cards,draw_context=context,draw_context_sha256=digest(context),sampling=sample,mode_plans=mode_plans,full_domain_exhausted=False,source_bytes_authenticated=False,eligibility_verified=False))
    out=dict(schema='MULTIDECISION_SCORING_BUDGET_PLAN_V1',registration_preserved=deepcopy(registration),registration_reference_preserved=deepcopy(registration_reference),full_universe_preserved=deepcopy(universe),decision_inputs_preserved=deepcopy(decisions),rows=results,mathematical_source_hash_claims=MATH_SOURCES,source_bytes_authenticated=False,point_in_time_verified=False,complete_ndx_universe_verified=False,qualification_evidence_authenticated=False,sector_filter_applied=False,economic_results_used_for_sampling=False,parent_artifact_hash_used_for_sampling=False,mode_selected_using_results=False,score_computed=False,fit_performed=False,account_executed=False,registration_published=False,execution_authorized=False,promotion_allowed=False,global_optimum_proven=False,old_plan_reused=False,outer_lane_prior_resolved=False)
    out['content_sha256']=digest(out);return out
