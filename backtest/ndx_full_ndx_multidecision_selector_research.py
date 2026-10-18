"""Registered complete-budget, full-industry conditional selection; no fit or prior."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib,json,math,re

CUTOFFS=('2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31')
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
GATES=('fractional_risk_passed','liquidity_passed','conditional_member_scope_passed')
METRICS=('return_p50','return_p10','max_drawdown_p50','max_drawdown_p90','target_012922_distance')
ORDER={
 'RETURN':(('return_p50',-1),('return_p10',-1),('max_drawdown_p90',1),('target_012922_distance',1)),
 'BAD_TAIL':(('return_p10',-1),('return_p50',-1),('max_drawdown_p90',1),('target_012922_distance',1)),
 'DRAWDOWN':(('max_drawdown_p90',1),('max_drawdown_p50',1),('return_p10',-1),('target_012922_distance',1)),
 'TARGET_ENVELOPE':(('target_012922_distance',1),('return_p10',-1),('max_drawdown_p90',1),('return_p50',-1))}
POLICY='FULL_NDX_FOUR_LANE_RESEARCH_SELECTOR_JOB_ID_TIE_V1'


def require(ok,message):
    if not ok:raise ValueError(message)

def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def text(v):require(type(v) is str and bool(v) and v==v.strip(),'Canonical nonempty text');return v
def day(v):text(v);require(date.fromisoformat(v).isoformat()==v and date.fromisoformat(v).weekday()<5,'Canonical weekday');return v
def reference(v):
    require(type(v) is dict and {'path','sha256'}<=set(v),'Evidence reference')
    text(v['path']);require(type(v['sha256']) is str and re.fullmatch('[a-f0-9]{64}',v['sha256']) is not None,'Evidence SHA')
def number(v):
    require(type(v) in (int,float) and (type(v) is int or math.isfinite(v)),'Finite nonboolean saved metric')
    return Fraction(str(v))


def issuer_counts(universe):
    multiplicities={}
    for security in universe:multiplicities[security['issuer_id']]=multiplicities.get(security['issuer_id'],0)+1
    counts=[1]
    for n in multiplicities.values():
        counts.append(0)
        for k in range(len(counts)-1,0,-1):counts[k]+=counts[k-1]*n
    return [dict(holding_count=k,combination_count=counts[k]) for k in range(1,len(counts))]


def registered_coordinates(registration):
    require(registration['schema']=='FULL_NDX_MULTIDECISION_SELECTION_REGISTRATION_V1' and registration['policy_id']==POLICY,'Explicit new selection registration required')
    reference(registration['registration_reference']);reference(registration['scope_reference'])
    require(registration['universe_scope']=='ALL_CONDITIONAL_NDX_MEMBERS_ALL_INDUSTRIES' and registration['sector_filter_applied'] is False,'No technology subset')
    exact(registration['decision_cutoffs'],list(CUTOFFS),'Explicit six decisions');exact(registration['fx_modes'],list(MODES),'Two isolated target modes')
    universe=registration['universe'];require(type(universe) is list and len(universe)>0,'Full supplied inventory')
    for s in universe:
        for k in ('security_id','issuer_id','ticker'):text(s[k])
    require(len({s['security_id'] for s in universe})==len(universe) and len({s['ticker'] for s in universe})==len(universe),'Unique security/ticker inventory')
    exact(registration['all_k_denominators'],issuer_counts(universe),'Full issuer-constrained allk domain')
    coordinates=registration['coordinates'];require(type(coordinates) is list and len(coordinates)==12,'Six decisions times two modes')
    for row,(cutoff,mode) in zip(coordinates,[(c,m) for c in CUTOFFS for m in MODES]):
        require(row['cutoff']==cutoff and row['decision_date']==cutoff and row['fx_mode']==mode,'Registered decision/mode order')
        ids=row['expected_job_ids'];require(type(ids) is list and all(type(x) is str and x and x==x.strip() for x in ids) and len(ids)==len(set(ids)),'Complete unique registered job IDs')
        require(row['source_status'] in ('READY_FOR_SCORING','SOURCE_BLOCKED'),'Explicit registered source state')
        blockers=row['source_blockers'];require(type(blockers) is list,'Explicit source blockers')
        require(bool(blockers)==(row['source_status']=='SOURCE_BLOCKED'),'Source state and evidence agree')
        for blocker in blockers:
            text(blocker['reason_code']);reference(blocker['evidence_reference'])
        require(type(row['training_semantics_sha256']) is str and re.fullmatch('[a-f0-9]{64}',row['training_semantics_sha256']) is not None,'Registered scoring semantics')
        coverage=row['budget_coverage'];full=sum(x['combination_count'] for x in registration['all_k_denominators'])
        for k,n in dict(full_combination_count=full,full_three_spec_task_denominator=full*3,registered_task_count=len(ids),unscored_full_domain_task_count=full*3-len(ids)).items():require(type(coverage[k]) is int and coverage[k]==n and n>=0,'Exact separate full/budget denominator '+k)
        exclusions=coverage['pre_registered_exclusions'];require(type(exclusions) is list,'Explicit pre-registered exclusions, including empty')
        for e in exclusions:
            text(e['reason_code']);reference(e['evidence_reference'])
            require(type(e['security_ids']) is list and len(e['security_ids'])==len(set(e['security_ids'])) and all(x in {s['security_id'] for s in universe} for x in e['security_ids']),'Exclusions preserve inventory identities')
            require(type(e['holding_counts']) is list and all(type(k) is int and 1<=k<=len(registration['all_k_denominators']) for k in e['holding_counts']),'Excluded k remains in full domain')
        reference(row['budget_reference']);days=row['scoring_price_dates']
        require(type(days) is list and len(days)==505 and days==sorted(set(days)) and days[-1]==cutoff,'Complete common505 cutoff window')
        for d in days:day(d)
    return coordinates,{s['security_id']:s for s in universe}


def validate_record(record,coordinate,inventory):
    task=record['task'];result=record['result'];require(record['status']=='EVALUATED' and type(result) is dict,'Missing evaluated scores')
    require(task['decision_date']==task['cutoff']==coordinate['cutoff'] and task['fx_mode']==coordinate['fx_mode'],'Actual decision cutoff/mode')
    require(record['training_semantics_sha256']==coordinate['training_semantics_sha256'],'Incomparable scoring semantics')
    reference(record['evidence_reference']);require(task['weight_spec'] in SPECS,'Original three specs')
    sids=task['security_ids'];require(type(sids) is list and len(sids)>0 and all(type(s) is str and s in inventory for s in sids) and sids==sorted(set(sids)),'Canonical registered SID composition')
    require(type(task['holding_count']) is int and task['holding_count']==len(sids),'Exact holding count')
    require(len({inventory[s]['issuer_id'] for s in sids})==len(sids),'Multiple classes of one issuer cannot coexist')
    names=task['tickers'];require(type(names) is str and names==';'.join(sorted(inventory[s]['ticker'] for s in sids)),'Exact canonical ticker identity')
    for k in ('security_ids','holding_count','tickers','weight_spec'):exact(result[k],task[k],'Saved result identity '+k)
    for k in METRICS:number(result[k])
    for k in ('max_drawdown_p50','max_drawdown_p90','target_012922_distance'):require(number(result[k])>=0,'Nonnegative drawdown/distance '+k)
    gates=record['eligibility'];require(type(gates) is dict and all(type(gates.get(k)) is bool for k in GATES),'Three explicit boolean research gates')
    require('technology_scope_passed' not in gates,'Do not disguise old technology gate')
    windows=record['scoring_windows'];require(type(windows) is list and len(windows)==13,'All13 scoring windows required')
    dates=coordinate['scoring_price_dates']
    for i,w in enumerate(windows):
        left=i*21
        require(type(w['window_index']) is int and w['window_index']==i and w['status']=='COMPLETE','No unknown or partial scored window')
        for k,n in (('fit_return_count',126),('evaluation_return_count',126)):require(type(w[k]) is int and w[k]==n,'126/126 scoring window')
        expected=dict(fit_price_predecessor=dates[left],fit_first_return_end=dates[left+1],fit_last_return_end=dates[left+126],evaluation_price_predecessor=dates[left+126],evaluation_first_return_end=dates[left+127],evaluation_last_return_end=dates[left+252])
        for k,v in expected.items():require(w[k]==v,'Registered causal window '+k)
    return [k for k in GATES if not gates[k]]


def select_full_ndx_lanes(*,registration,records):
    """Caller-supplied saved metrics only. No ranking across FX modes or lane returns."""
    coordinates,inventory=registered_coordinates(registration);require(type(records) is list,'Complete record list')
    groups={(c['cutoff'],c['fx_mode']):[] for c in coordinates};global_errors=[]
    for i,r in enumerate(records):
        try:
            key=(r['task']['cutoff'],r['task']['fx_mode']);require(key in groups,'Record outside registered coordinate')
            groups[key].append((i,r))
        except (ValueError,KeyError,TypeError) as exc:global_errors.append(dict(record_index=i,error=str(exc)))
    rows=[]
    for coordinate in coordinates:
        group=groups[(coordinate['cutoff'],coordinate['fx_mode'])];expected=coordinate['expected_job_ids'];seen=set();semantic_seen=set();errors=[];rejections=[];valid=[]
        source_blocked=coordinate['source_status']=='SOURCE_BLOCKED'
        for index,record in group:
            identifier=None
            try:
                identifier=text(record['task']['job_id']);require(identifier in expected,'Unregistered job ID');require(identifier not in seen,'Duplicate job ID');seen.add(identifier)
                require(not source_blocked,'Scored record supplied for source-blocked coordinate')
                failed=validate_record(record,coordinate,inventory)
                semantic=(tuple(record['task']['security_ids']),record['task']['weight_spec'])
                require(semantic not in semantic_seen,'Duplicate composition/spec under different job IDs');semantic_seen.add(semantic)
                if failed:rejections.append(dict(job_id=identifier,record_index=index,reasons=failed))
                else:valid.append((index,record))
            except (ValueError,KeyError,TypeError,OverflowError) as exc:errors.append(dict(job_id=identifier,record_index=index,error=str(exc)))
        missing=[job for job in expected if job not in seen]
        if missing and not source_blocked:errors.append(dict(error='Registered budget job IDs missing',missing_job_ids=missing))
        if not source_blocked and len(group)!=len(expected):errors.append(dict(error='Registered budget row denominator differs'))
        choices=[]
        for lane,order in ORDER.items():
            selected=None
            if errors or global_errors:status='INPUT_INVALID'
            elif source_blocked:status='SOURCE_BLOCKED'
            elif not expected:status='NO_REGISTERED_CANDIDATES'
            elif not valid:status='NO_ELIGIBLE_CANDIDATE'
            else:
                def rank(pair):
                    _,r=pair;t=r['task'];v=r['result']
                    return tuple(number(v[k])*direction for k,direction in order)+(t['holding_count'],t['tickers'],t['weight_spec'],t['job_id'])
                position,selected=min(valid,key=rank);status='SELECTED_REQUIRES_NEW_CUTOFF_REFIT'
                selected=dict(job_id=selected['task']['job_id'],record_index=position,record_preserved=deepcopy(selected))
            choices.append(dict(lane=lane,status=status,selected=selected))
        rows.append(dict(coordinate_preserved=deepcopy(coordinate),expected_task_count=len(expected),received_task_count=len(group),source_blocked_task_count=len(expected) if source_blocked else 0,unreceived_job_ids=missing,eligible_count=len(valid),rejections=rejections,input_errors=errors,choices=choices))
    out=dict(schema='FULL_NDX_MULTIDECISION_FOUR_LANE_SELECTION_V1',registration_preserved=deepcopy(registration),records_preserved=deepcopy(records),rows=rows,global_input_errors=global_errors,all_k_denominators_preserved=deepcopy(registration['all_k_denominators']),ranking_arithmetic='EXACT_FRACTION_OF_SAVED_NUMERIC_LITERAL_NOT_RECOMPUTED_SCORES',policy_id=POLICY,source_bytes_authenticated=False,eligibility_source_authenticity_verified=False,point_in_time_verified=False,complete_ndx_universe_verified=False,full_universe_search_verified=False,sector_filter_applied=False,mode_selected_using_results=False,portfolio_track='portfolio_optimization',evaluation_tracks=['continuous','whole_lot'],saved_weights_are_execution_targets=False,cutoff_refit_required=True,prior_resolved=False,numerical_task_ids_generated=False,implicit_carry_forward=False,fit_performed=False,account_executed=False,promotion_allowed=False,execution_authorized=False,formal_benchmark_passed=False)
    out['content_sha256']=hashlib.sha256(encoded(out)).hexdigest();return out
