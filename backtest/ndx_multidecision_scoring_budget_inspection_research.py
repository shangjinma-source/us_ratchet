"""Independent inspection of saved six-cutoff budgets, without planning or sampling calls."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
import re
from backtest.ndx_issuer_combination_index_research import IssuerCombinationIndex

CUTOFFS=('2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31')
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
ORDER='MULTIDECISION_ISSUER_COVER_STRATIFIED_RANK_V1'
SEED='NDX_MULTIDECISION_CONDITIONAL_SCORE_ROUND1_20261003'
POLICY_SHA='6cc7f67093ba996b7cad0c6e24acbc3691a457930103872b8105b6a44c38424f'
POLICY_CONTENT='830f84b80ef1728f6e55eecb2b16b7c337f2b0188388ba9c8525250eed2a5068'
BUDGET=dict(combinations_per_retained_k=32,max_proposals_per_decision=4096,proposal_scope='ALL_K_WITHIN_ONE_CUTOFF_INCLUDING_REJECTIONS',small_domain_policy='MIN_32_OR_FULL_DOMAIN_COUNT')
PARAMETERS=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
MATH=dict(issuer_index='bc24b924ba53f093f7f9bfc05fd237234fbed851ff5d32f7b41324a08594d87b',necessary_bounds='4f433404895070613d217acc8a245e6fb346f2835652fe1a934eb2be909c943c')
FLAGS=('source_bytes_authenticated','point_in_time_verified','complete_ndx_universe_verified','qualification_evidence_authenticated','sector_filter_applied','economic_results_used_for_sampling','parent_artifact_hash_used_for_sampling','mode_selected_using_results','score_computed','fit_performed','account_executed','registration_published','execution_authorized','promotion_allowed','global_optimum_proven','old_plan_reused','outer_lane_prior_resolved')


def require(ok,message):
    if not ok:raise ValueError(message)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def exact(a,b,message):require(digest(a)==digest(b),message)
def ref(r):
    require(type(r) is dict and {'path','sha256'}<=set(r),'Reference object')
    require(type(r['path']) is str and bool(r['path']) and r['path'].strip()==r['path'],'Reference path')
    require(type(r['sha256']) is str and re.fullmatch('[a-f0-9]{64}',r['sha256']) is not None,'Reference digest')
def groups(rows):
    result={}
    for row in rows:result.setdefault(row['issuer_id'],[]).append(row['security_id'])
    return [dict(issuer_id=issuer,security_ids=sorted(sids)) for issuer,sids in sorted(result.items())]
def index(groups_):return IssuerCombinationIndex([(x['issuer_id'],x['security_ids']) for x in groups_])
def rational(value):return dict(numerator=str(value.numerator),denominator=str(value.denominator))
def cards(idx):
    result=[]
    for k,n in idx.counts_by_k().items():
        pad=Fraction(k+1,10**12);tol=Fraction(1,10**9);lower=1-tol-pad;upper=1+tol+pad
        comparisons=[('MAX_SINGLE_CAPACITY_BELOW_MINIMUM_SIMPLEX_MASS',k*(Fraction(45,100)+tol)+pad,'<',lower),
                     ('MIN_SINGLE_REQUIRED_MASS_ABOVE_MAXIMUM_SIMPLEX_MASS',k*(Fraction(5,100)-tol)-pad,'>',upper),
                     ('TRUE_TOP3_UNIVERSAL_LOWER_BOUND_ABOVE_ACCEPTED_CAP',Fraction(min(3,k),k)*lower,'>',Fraction(8,10)+tol+pad)]
        cert=[]
        for reason,left,op,right in comparisons:
            if (left<right if op=='<' else left>right):
                cert.append(dict(reason=reason,left=rational(left),comparison=op,right=rational(right),strict_gap=rational(abs(left-right)),arithmetic='EXACT_RATIONAL_DECIMAL_INPUT_WITH_CONSERVATIVE_TOLERANCE_AND_ROUNDING_PADDING'))
        result.append(dict(k=k,combination_count=n,necessary_bound_certificates=cert))
    return result


def inspect_sampling(saved,idx,context,cardinalities):
    """Consume the declared proposal transcript in deterministic protocol order.

    No call to a sampler: each supplied proposal is checked against its static
    hash interval and prior acceptance state; the transcript cannot omit retries.
    """
    log=saved['proposal_log'];require(type(log) is list and len(log)<=4096,'Bounded full proposal transcript')
    cursor=0;positions=[];coverage=[];strata=[];seed=digest(context)
    for card in cardinalities:
        k=card['k'];total=card['combination_count'];wanted=0 if card['necessary_bound_certificates'] else min(32,total)
        chosen=set();covers=[]
        if wanted:
            permutation=sorted(range(len(idx.issuer_ids)),key=lambda i:(digest([ORDER,seed,k,idx.issuer_ids[i]]),idx.issuer_ids[i]))
            base=[tuple(idx.security_groups[i][0] for i in sorted(permutation[(s+j)%len(permutation)] for j in range(k))) for s in range(0,len(permutation),k)]
            for i,members in enumerate(idx.security_groups):
                initial=next(row for row in base if members[0] in row)
                base.extend(tuple(sid if old==members[0] else old for old in initial) for sid in members[1:])
            for members in base:
                rank=idx.rank(k,members)
                if rank not in covers:covers.append(rank)
        require(len(covers)<=wanted,'SID coverage must fit declared budget')
        def consume(kind,rank,extra):
            nonlocal cursor
            if cursor>=4096:return False
            require(cursor<len(log),'Missing proposal record')
            outcome='HASH_RANGE_REJECTED' if rank is None else 'DUPLICATE' if rank in chosen else 'ACCEPTED'
            expected=dict(proposal_index=cursor,k=k,rank=rank,selection_kind=kind,outcome=outcome,**extra)
            exact(log[cursor],expected,'Proposal identity/order/hash/outcome')
            if outcome=='ACCEPTED':
                members=list(idx.unrank(k,rank));require(idx.rank(k,members)==rank,'Rank roundtrip')
                positions.append(dict(k=k,rank=rank,security_ids=members,selection_kind=kind,proposal_index=cursor));chosen.add(rank)
            cursor+=1
            return outcome=='ACCEPTED'
        def check_draw(lo,hi,kind,ordinal,attempt):
            if cursor>=4096:return False
            width=hi-lo;bits=(width-1).bit_length();size=max(1,(bits+7)//8)
            entropy=b''.join(bytes.fromhex(digest([ORDER,seed,k,kind,ordinal,attempt,block])) for block in range((size+31)//32))
            raw=int.from_bytes(entropy[:size],'big')&((1<<bits)-1)
            return consume(kind,None if raw>=width else lo+raw,dict(interval_start=lo,interval_stop=hi,stratum_index=ordinal,draw_index=attempt))
        for rank in covers:consume('SID_COVERAGE',rank,{})
        remainder=wanted-len(covers)
        for j in range(remainder):
            lo=j*total//remainder;hi=(j+1)*total//remainder;strata.append(dict(k=k,stratum_index=j,start=lo,stop=hi));attempt=0
            while cursor<4096 and sum(lo<=r<hi for r in chosen)<hi-lo:
                accepted=check_draw(lo,hi,'STRATIFIED_RANK',j,attempt);attempt+=1
                if accepted:break
        attempt=0
        while len(chosen)<wanted and cursor<4096:
            check_draw(0,total,'STRATIFIED_REFILL',-1,attempt);attempt+=1
        exposure={sid:0 for members in idx.security_groups for sid in members}
        for p in positions:
            if p['k']==k:
                for sid in p['security_ids']:exposure[sid]+=1
        coverage.append(dict(**card,requested_position_count=wanted,selected_position_count=len(chosen),unprocessed_requested_position_count=wanted-len(chosen),unsearched_combination_count=total-len(chosen),security_exposures=exposure,all_security_ids_covered=bool(wanted) and all(exposure.values())))
    require(cursor==len(log),'Extra proposal records')
    complete=all(c['selected_position_count']==c['requested_position_count'] for c in coverage)
    exact(saved,dict(status='PLANNED_NOT_ATTEMPTED' if complete else 'INCOMPLETE_POINT_SELECTION',positions=positions,cardinality_coverage=coverage,proposal_log=log,proposal_count=cursor,strata=strata,complete=complete),'Complete sampling state')
    return positions,coverage,complete


def inspect_scoring_budget(*,registration,registration_reference,universe,decisions,saved_plan):
    ref(registration_reference);require(registration_reference['sha256']==POLICY_SHA and digest(registration)==POLICY_CONTENT,'Frozen actual registration')
    require(type(universe) is list and len(universe)==77,'Complete77 inventory')
    for row in universe:
        require(all(type(row[k]) is str and row[k] and row[k].strip()==row[k] for k in ('security_id','issuer_id','ticker')),'Canonical coordinates')
    require(len({u['security_id'] for u in universe})==77 and len({u['ticker'] for u in universe})==77 and len({u['issuer_id'] for u in universe})==76,'Unique77/76 inventory')
    fullcards=cards(index(groups(universe)));require(type(decisions) is list and len(decisions)==6,'Six decisions')
    require(type(saved_plan.get('rows')) is list and len(saved_plan['rows'])==6,'Saved six decisions')
    expected_rows=[];alljobs=set()
    for source,cutoff,actual in zip(decisions,CUTOFFS,saved_plan['rows']):
        require(source['cutoff']==cutoff,'Cutoff order')
        for key in ('scoring_data_reference','fitter_source_reference','incumbent_fee_reference'):ref(source[key])
        dates=source['scoring_price_dates']
        require(type(dates) is list and len(dates)==505 and dates==sorted(set(dates)) and dates[-1]==cutoff,'505 original dates')
        require(all(type(d) is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5 for d in dates),'Canonical weekday dates')
        qrows=source['qualifications'];require(type(qrows) is list and [q['security_id'] for q in qrows]==[u['security_id'] for u in universe],'Full ordered qualifications')
        eligible=[];excluded=[]
        for u,q in zip(universe,qrows):
            require(q['cutoff']==cutoff,'Qualification cutoff')
            for field in ('history_13_complete','mdv_available','conditional_member_scope_passed'):require(type(q[field]) is bool,'Qualification boolean')
            require(q['liquidity_passed'] is None or type(q['liquidity_passed']) is bool,'Unknown liquidity preserved')
            mdv=q['mdv_evidence'];require(mdv['coordinate']['security_id']==u['security_id'] and mdv['formal_eligibility_verified'] is False,'Conditional MDV coordinate')
            exact(mdv['required_dates'],dates[-63:],'Same63 causal days')
            value=mdv['median_dollar_volume_exact']
            if value is None:
                require(mdv['status']=='UNKNOWN_LIQUIDITY' and q['mdv_available'] is False and q['liquidity_passed'] is None and mdv['conditional_numerical_threshold_passed'] is None,'Unknown state')
            else:
                require(type(value) is str and Fraction(value)>=0 and mdv['status']=='CONDITIONAL_MDV_COMPUTABLE' and q['mdv_available'] is True,'Computable MDV')
                passed=Fraction(value)>=50000000
                require(q['liquidity_passed'] is passed and mdv['conditional_numerical_threshold_passed'] is passed,'Threshold evidence')
            for key in ('history_reference','mdv_reference'):ref(q[key])
            require(type(q['reasons']) is list and all(type(x) is str and x for x in q['reasons']),'Original reasons')
            reasons=[]
            for condition,reason in ((not q['history_13_complete'],'BLOCKED_FULL13_HISTORY'),(not q['mdv_available'],'UNKNOWN_MDV_SUPPLY'),(q['liquidity_passed'] is not True,'LIQUIDITY_GATE_NOT_PASSED'),(not q['conditional_member_scope_passed'],'CONDITIONAL_MEMBER_SCOPE_NOT_PASSED')):
                if condition:reasons.append(reason)
            if reasons:excluded.append(dict(security_id=u['security_id'],reasons=reasons,original_qualification=deepcopy(q)))
            else:eligible.append(u)
        grouped=groups(eligible)
        context=dict(algorithm_version=ORDER,seed_text=SEED,decision_cutoff=cutoff,canonical_issuer_security_groups=grouped,static_budget=deepcopy(BUDGET))
        if grouped:
            idx=index(grouped);ecards=cards(idx);positions,coverage,complete=inspect_sampling(actual['sampling'],idx,context,ecards)
        else:
            ecards=[];positions=[];coverage=[];complete=True
            exact(actual['sampling'],dict(status='NO_SCORABLE_SECURITIES',positions=[],cardinality_coverage=[],proposal_log=[],proposal_count=0,strata=[],complete=True),'Empty pool diagnostic')
        modes=source['mode_sources'];require(type(modes) is list and [m['mode'] for m in modes]==list(MODES),'Both modes in original order')
        modeplans=[]
        for mode in modes:
            ref(mode['reference']);require(type(mode['complete_thirteen_windows']) is bool,'Full13 mode flag')
            tasks=[]
            if complete:
                for p in positions:
                    for spec in SPECS:
                        identity=dict(schema='MULTIDECISION_CAUSAL_SCORING_JOB_IDENTITY_V1',cutoff=cutoff,fx_mode=mode['mode'],security_ids=p['security_ids'],weight_spec=spec,parameters=PARAMETERS,scoring_data_reference=source['scoring_data_reference'],target_reference=mode['reference'],fitter_source_reference=source['fitter_source_reference'],scoring_window_contract=dict(price_count=505,fit_return_count=126,evaluation_return_count=126,step_return_count=21,window_count=13),internal_initial_previous_weights=None,inner_rolling_fit_prior='FIRST_WINDOW_NONE_THEN_SAME_CANDIDATE_PREVIOUS_WINDOW_TARGET',candidate_transaction_cost_bps=10,candidate_turnover_cost_formula='0.5*SUM_ABS_TARGET_MINUS_REFERENCE*10/10000',first_candidate_fee_reference=deepcopy(source['incumbent_fee_reference']),fee_reference_policy='FIRST_NORMALIZED_ORIGINAL_CONTROL_THEN_SAME_CANDIDATE_PREVIOUS_TARGET',outer_lane_prior_applied=False)
                        job=digest(identity);require(job not in alljobs,'Duplicate global job');alljobs.add(job)
                        tasks.append(dict(job_id=job,identity=identity,position=p,status='PLANNED_NOT_ATTEMPTED' if mode['complete_thirteen_windows'] else 'SOURCE_BLOCKED'))
            status='INCOMPLETE_POINT_SELECTION' if not complete else 'SOURCE_BLOCKED' if not mode['complete_thirteen_windows'] else 'NO_RETAINED_CANDIDATES' if not tasks else 'PLANNED_NOT_ATTEMPTED'
            modeplans.append(dict(mode=mode['mode'],status=status,source_preserved=deepcopy(mode),tasks=tasks,task_count=len(tasks),score_dispatch_authorized=False))
        byk={c['k']:c for c in ecards};selected={c['k']:c['selected_position_count'] for c in coverage};domains=[]
        for c in fullcards:
            k=c['k'];eligiblecount=byk.get(k,{}).get('combination_count',0);n=selected.get(k,0);excludedcount=eligiblecount if c['necessary_bound_certificates'] else 0
            domains.append(dict(k=k,full_inventory_combination_count=c['combination_count'],qualification_excluded_combination_count=c['combination_count']-eligiblecount,eligible_pool_combination_count=eligiblecount,necessary_bound_excluded_combination_count=excludedcount,selected_combination_count=n,unsearched_eligible_after_bounds=eligiblecount-excludedcount-n,unselected_full_domain_combination_count=c['combination_count']-n,full_three_spec_task_denominator=3*c['combination_count'],necessary_bound_certificates=c['necessary_bound_certificates']))
        expected_rows.append(dict(domain_coverage=domains,cutoff=cutoff,universe_preserved=deepcopy(universe),qualification_rows_preserved=deepcopy(qrows),excluded_securities=excluded,eligible_security_ids=[u['security_id'] for u in eligible],canonical_eligible_groups=grouped,full_inventory_cardinalities=fullcards,eligible_pool_cardinalities=ecards,draw_context=context,draw_context_sha256=digest(context),sampling=actual['sampling'],mode_plans=modeplans,full_domain_exhausted=False,source_bytes_authenticated=False,eligibility_verified=False))
    expected=dict(schema='MULTIDECISION_SCORING_BUDGET_PLAN_V1',registration_preserved=deepcopy(registration),registration_reference_preserved=deepcopy(registration_reference),full_universe_preserved=deepcopy(universe),decision_inputs_preserved=deepcopy(decisions),rows=expected_rows,mathematical_source_hash_claims=MATH,**{key:False for key in FLAGS})
    expected['content_sha256']=digest(expected);exact(saved_plan,expected,'Complete saved plan inspection')
    return dict(schema='MULTIDECISION_SCORING_BUDGET_INSPECTION_V1',status='PASS',decision_count=6,security_count=77,issuer_count=76,job_count=len(alljobs),source_bytes_authenticated=False,fit_performed=False,score_computed=False,execution_authorized=False,promotion_allowed=False)
