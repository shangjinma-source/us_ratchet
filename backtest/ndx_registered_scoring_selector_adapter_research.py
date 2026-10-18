"""Saved registered scores to selector inputs; no selection, scoring, fitting or IO."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib,json,math,re
CUTOFFS=('2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31')
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
POLICY_HASH='830f84b80ef1728f6e55eecb2b16b7c337f2b0188388ba9c8525250eed2a5068'
POLICY_SHA='6cc7f67093ba996b7cad0c6e24acbc3691a457930103872b8105b6a44c38424f'
SUCCESS='SCORED_PENDING_INDEPENDENT_READBACK'
ERRORS=('NUMERICAL_EXCEPTION','VALIDATION_FAILURE','UNRESOLVED_DISPATCH','UNDISPATCHED','RESOURCE_STOP_AFTER_START')
RISK=('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')
METRICS=('return_p50','return_p10','max_drawdown_p50','max_drawdown_p90','target_012922_distance')
SAVED_METRICS={prefix+metric for prefix in ('','incumbent_','target_') for metric in METRICS[:4]}|{'target_012922_distance','paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent','paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent'}


def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(enc(v)).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def integer(v,n=None):require(type(v) is int and v>=0 and (n is None or v==n),'Exact nonnegative count')
def ref(v):
    require(type(v) is dict and {'path','sha256'}<=set(v),'Source reference')
    require(type(v['path']) is str and bool(v['path']) and type(v['sha256']) is str and re.fullmatch('[a-f0-9]{64}',v['sha256']),'Source path/SHA')
def pointer(v):ref(v);require(type(v.get('json_pointer')) is str and v['json_pointer'].startswith('/'),'Actual JSON pointer')
def false(v,keys):
    for k in keys:require(v[k] is False,'No authority upgrade '+k)
def counts(universe):
    groups={}
    for u in universe:groups[u['issuer_id']]=groups.get(u['issuer_id'],0)+1
    values=[1]
    for size in groups.values():
        values.append(0)
        for k in range(len(values)-1,0,-1):values[k]+=values[k-1]*size
    return [dict(holding_count=k,combination_count=v) for k,v in enumerate(values) if k]
def score_ref(p):
    if p['source_kind']=='FIRST_EXTERNAL':
        pointer(p['score_reference']);require(p['score_reference']['json_pointer']=='/result','First raw score pointer')
    else:
        require(p['source_kind']=='JOURNAL','Known successful source kind');r=p['score_reference'];require(set(r)=={'journal_reference','record_locator','result_field'},'Journal locator fields');ref(r['journal_reference'])
        q=r['record_locator'];require(set(q)=={'sequence','byte_start','byte_stop','record_sha256','stage'},'Actual record locator')
        for k in ('sequence','byte_start','byte_stop'):integer(q[k])
        require(q['byte_stop']>q['byte_start'] and q['stage']=='RAW_SCORE' and re.fullmatch('[a-f0-9]{64}',q['record_sha256']) and r['result_field']=='payload.result','Raw score record location')


def convert_score(p,job,days,inventory):
    score=p['score'];inspection=p['inspection'];identity=job['identity'];sid_order=identity['security_ids']
    score_ref(p);pointer(p['inspection_reference']);pointer(p['evidence_reference'])
    require(inspection['schema']=='REGISTERED_SCORING_RESULT_INSPECTION_V1' and inspection['status']=='PASS' and inspection['job_id']==job['job_id'],'Same independent result inspection for first and journals')
    integer(inspection['window_count'],13);require(len(inspection['fit_matrix_hashes'])==13 and all(type(x) is str and re.fullmatch('[a-f0-9]{64}',x) for x in inspection['fit_matrix_hashes']),'Thirteen audited fit hashes')
    false(inspection,('optimization_rerun','optimized_weights_independently_verified','recovery_certificates_recomputed','source_bytes_authenticated','fit_performed','account_executed','promotion_allowed'))
    arithmetic=inspection['score_arithmetic'];require(arithmetic['schema']=='MULTIDECISION_WINDOW_SCORING_INSPECTION_V1' and arithmetic['status']=='PASS' and arithmetic['binary64_comparison']=='EXACT_HEX_NO_TOLERANCE','Independent saved score arithmetic')
    for k,n in (('window_count',13),('window_return_count',126),('metric_count',17)):integer(arithmetic[k],n)
    false(arithmetic,('source_bytes_authenticated','fit_performed','formal_benchmark_passed','account_executed','promotion_allowed'))
    require(score['schema']=='MULTIDECISION_FITTED_WINDOW_SCORE_REDUCTION_V1' and score['cutoff']==identity['cutoff'],'Score role/cutoff')
    exact(score['securities'],[{k:inventory[s][k] for k in ('security_id','ticker','issuer_id','risk_chain')} for s in sid_order],'Original fitted column order/identity')
    false(score,('source_bytes_authenticated','fit_performed','point_in_time_verified','selected_rolling_weights_are_execution_targets','whole_lot_gate_evaluated','formal_benchmark_passed','account_executed','promotion_allowed'));require(score['score_computed'] is True,'Saved scoring result')
    require(score['risk_gate_semantics']=='ALL_FIVE_DECLARED_FRACTIONAL_CONSTRAINTS_EVERY_WINDOW','Saved risk gate semantics')
    require(type(score['metrics']) is dict and set(score['metrics'])==SAVED_METRICS,'Complete original metrics')
    for v in score['metrics'].values():require(type(v) in (float,int) and math.isfinite(v),'Finite nonboolean saved score')
    for k in METRICS:require(k in score['metrics'],'Required selector metric')
    for k in ('max_drawdown_p50','max_drawdown_p90','target_012922_distance'):require(score['metrics'][k]>=0,'Nonnegative risk/distance')
    require(type(score['windows']) is list and len(score['windows'])==13,'No partial scoring window ranking')
    windows=[];risk=True
    for i,w in enumerate(score['windows']):
        integer(w['window_index'],i);checks=w['risk_checks'];require(set(checks)==set(RISK) and all(type(v) is bool for v in checks.values()),'Five explicit window risk observations');risk=risk and all(checks.values())
        f=w['fitted_window_preserved'];integer(f['window_index'],i);require(f['fit_data_sha256']==inspection['fit_matrix_hashes'][i],'Saved fitted-window audit association')
        left=i*21;expected=dict(fit_first_return_end=days[left+1],fit_last_return_end=days[left+126],evaluation_first_return_end=days[left+127],evaluation_last_return_end=days[left+252])
        for key,value in expected.items():require(f[key]==value,'Causal scoring boundary')
        windows.append(dict(window_index=i,status='COMPLETE',fit_return_count=126,evaluation_return_count=126,fit_price_predecessor=days[left],evaluation_price_predecessor=days[left+126],**expected))
    require(type(score['fractional_risk_passed']) is bool and score['fractional_risk_passed']==risk,'Saved risk summary equals all thirteen windows')
    return windows,risk


def assemble_registered_selector_inputs(*,budget_plan,budget_reference,budget_audit_reference,projections,selection_registration_reference):
    """All logical rows required, including explicit blocked/error/undispatched evidence.

    Byte/locator authentication belongs to a future source wrapper, not this pure adapter.
    Error records deliberately prevent the frozen selector from ranking an incomplete coordinate.
    """
    for r in (budget_reference,budget_audit_reference,selection_registration_reference):ref(r)
    b=budget_plan;require(b['schema']=='MULTIDECISION_SCORING_BUDGET_PLAN_V1','Registered budget schema')
    require(b['content_sha256']==digest({k:v for k,v in b.items() if k!='content_sha256'}),'Saved budget content digest')
    policy=b['registration_preserved'];require(digest(policy)==POLICY_HASH and b['registration_reference_preserved']['sha256']==POLICY_SHA,'Frozen scoring/selection policy')
    false(b,('source_bytes_authenticated','point_in_time_verified','complete_ndx_universe_verified','qualification_evidence_authenticated','sector_filter_applied','economic_results_used_for_sampling','mode_selected_using_results','score_computed','fit_performed','execution_authorized','promotion_allowed'))
    u=b['full_universe_preserved'];require(type(u) is list and len(u)==77 and len({x['security_id'] for x in u})==77 and len({x['issuer_id'] for x in u})==76 and len({x['ticker'] for x in u})==77,'Full conditional77/76 inventory')
    inventory={x['security_id']:x for x in u};cards=counts(u);full=sum(x['combination_count'] for x in cards)
    require(type(projections) is list and len(b['rows'])==len(b['decision_inputs_preserved'])==6,'Complete source projections/six decisions')
    registration=dict(schema='FULL_NDX_MULTIDECISION_SELECTION_REGISTRATION_V1',policy_id='FULL_NDX_FOUR_LANE_RESEARCH_SELECTOR_JOB_ID_TIE_V1',registration_reference=deepcopy(selection_registration_reference),scope_reference=deepcopy(b['registration_reference_preserved']),universe_scope='ALL_CONDITIONAL_NDX_MEMBERS_ALL_INDUSTRIES',sector_filter_applied=False,decision_cutoffs=list(CUTOFFS),fx_modes=list(MODES),universe=deepcopy(u),all_k_denominators=cards,coordinates=[])
    records=[];ledger=[];cursor=0;seen=set();first_success=None
    for j,(row,d,cutoff) in enumerate(zip(b['rows'],b['decision_inputs_preserved'],CUTOFFS)):
        require(row['cutoff']==d['cutoff']==cutoff and row['sampling']['complete'] is True,'Registered complete position selection')
        exact(row['universe_preserved'],u,'Inventory unchanged');exact(row['qualification_rows_preserved'],d['qualifications'],'Qualification source unchanged')
        require([q['security_id'] for q in d['qualifications']]==list(inventory),'Full qualification order');qby={q['security_id']:q for q in d['qualifications']}
        days=d['scoring_price_dates'];require(len(days)==505 and days==sorted(set(days)) and days[-1]==cutoff,'Full505 uncompressed cutoff calendar')
        for day in days:require(date.fromisoformat(day).isoformat()==day and date.fromisoformat(day).weekday()<5,'Canonical weekday')
        require([x['mode'] for x in row['mode_plans']]==[x['mode'] for x in d['mode_sources']]==list(MODES),'Both FX coordinates in fixed order')
        require(len(row['domain_coverage'])==76,'All76 k domain retained')
        for card,coverage in zip(cards,row['domain_coverage']):
            integer(coverage['k'],card['holding_count']);integer(coverage['full_inventory_combination_count'],card['combination_count'])
            for key in ('qualification_excluded_combination_count','necessary_bound_excluded_combination_count','selected_combination_count','unsearched_eligible_after_bounds'):integer(coverage[key])
            require(sum(coverage[k] for k in ('qualification_excluded_combination_count','necessary_bound_excluded_combination_count','selected_combination_count','unsearched_eligible_after_bounds'))==card['combination_count'],'Full domain partition')
        semantics=digest(dict(policy_reference=b['registration_reference_preserved'],scoring_policy=policy['scoring'],fitter_source_reference=d['fitter_source_reference']))
        exclusions=[dict(reason_code=reason,security_ids=[e['security_id']],holding_counts=[],evidence_reference=dict(budget_reference,json_pointer=f'/plan/rows/{j}/excluded_securities/{n}')) for n,e in enumerate(row['excluded_securities']) for reason in e['reasons']]
        exclusions += [dict(reason_code='REGISTERED_NECESSARY_BOUND',security_ids=[],holding_counts=[c['k']],evidence_reference=dict(budget_reference,json_pointer=f'/plan/rows/{j}/domain_coverage/{n}')) for n,c in enumerate(row['domain_coverage']) if c['necessary_bound_certificates']]
        mode_semantics=[]
        for mi,(mp,source) in enumerate(zip(row['mode_plans'],d['mode_sources'])):
            exact(mp['source_preserved'],source,'Saved mode source');require(type(source['complete_thirteen_windows']) is bool,'Explicit complete13 source')
            blocked=not source['complete_thirteen_windows'];tasks=mp['tasks'];integer(mp['task_count'],len(tasks));require(len(tasks)==len(row['sampling']['positions'])*3,'Complete registered positions and all three specs');require(mp['status']==('SOURCE_BLOCKED' if blocked else 'PLANNED_NOT_ATTEMPTED' if tasks else 'NO_RETAINED_CANDIDATES'),'Coordinate availability')
            ids=[t['job_id'] for t in tasks];require(len(set(ids))==len(ids),'Unique registered jobs')
            registration['coordinates'].append(dict(cutoff=cutoff,decision_date=cutoff,fx_mode=source['mode'],expected_job_ids=ids,source_status='SOURCE_BLOCKED' if blocked else 'READY_FOR_SCORING',source_blockers=[dict(reason_code='TARGET_FULL13_SOURCE_BLOCKED',evidence_reference=deepcopy(source['reference']))] if blocked else [],training_semantics_sha256=semantics,budget_reference=deepcopy(budget_reference),scoring_price_dates=deepcopy(days),budget_coverage=dict(full_combination_count=full,full_three_spec_task_denominator=full*3,registered_task_count=len(ids),unscored_full_domain_task_count=full*3-len(ids),pre_registered_exclusions=deepcopy(exclusions)),full_domain_coverage_preserved=deepcopy(row['domain_coverage']),qualification_rows_preserved=deepcopy(d['qualifications'])))
            signatures=[]
            for ti,job in enumerate(tasks):
                identity=job['identity'];jid=job['job_id'];exact(job['position'],row['sampling']['positions'][ti//3],'Registered saved position');require(identity['weight_spec']==SPECS[ti%3],'Original three-spec order');require(jid==digest(identity) and jid not in seen,'Unique content-addressed job identity');seen.add(jid)
                require(identity['cutoff']==cutoff and identity['fx_mode']==source['mode'] and identity['weight_spec'] in SPECS,'Registered job coordinate')
                sids=identity['security_ids'];require(type(sids) is list and len(sids)==len(set(sids)) and all(s in inventory for s in sids),'Original selected inventory');require(len({inventory[s]['issuer_id'] for s in sids})==len(sids),'One security per issuer')
                exact(job['position']['security_ids'],sids,'Position identity');integer(job['position']['k'],len(sids));exact(identity['parameters'],dict(policy['scoring']['parameters'],fit_days=126),'Frozen fit parameters')
                exact(identity['scoring_window_contract'],dict(price_count=505,fit_return_count=126,evaluation_return_count=126,step_return_count=21,window_count=13),'13 complete windows contract')
                for k,expected in (('scoring_data_reference',d['scoring_data_reference']),('target_reference',source['reference']),('fitter_source_reference',d['fitter_source_reference']),('first_candidate_fee_reference',d['incumbent_fee_reference'])):exact(identity[k],expected,'Registered numerical input '+k)
                require(identity['internal_initial_previous_weights'] is None and identity['outer_lane_prior_applied'] is False and identity['inner_rolling_fit_prior']==policy['scoring']['inner_rolling_fit_prior'],'Inner prior semantics')
                integer(identity['candidate_transaction_cost_bps'],10);require(identity['candidate_turnover_cost_formula']=='0.5*SUM_ABS_TARGET_MINUS_REFERENCE*10/10000' and identity['fee_reference_policy']=='FIRST_NORMALIZED_ORIGINAL_CONTROL_THEN_SAME_CANDIDATE_PREVIOUS_TARGET','Original fee semantics')
                signature=(tuple(sids),identity['weight_spec']);require(signature not in signatures,'No duplicate composition/spec');signatures.append(signature)
                require(job['status']==('SOURCE_BLOCKED' if blocked else 'PLANNED_NOT_ATTEMPTED'),'Per-task registered source status')
                require(cursor<len(projections),'No incomplete result projection list');p=projections[cursor];require(p['job_id']==jid,'Full logical projection order');pointer(p['evidence_reference'])
                if not blocked and first_success is None:first_success=jid
                task=dict(job_id=jid,cutoff=cutoff,decision_date=cutoff,fx_mode=source['mode'],security_ids=sorted(sids),holding_count=len(sids),tickers=';'.join(sorted(inventory[s]['ticker'] for s in sids)),weight_spec=identity['weight_spec'])
                if blocked:
                    require(p['outcome']=='SOURCE_BLOCKED' and p['source_kind']=='REGISTERED_SOURCE_BLOCKED','No strict-mode substitution')
                    require(all(p[k] is None for k in ('score','inspection','score_reference','inspection_reference')),'Blocked scores cannot be fabricated')
                elif p['outcome']==SUCCESS:
                    require(p['error'] is None,'Successful source has no error');require(p['source_kind']==('FIRST_EXTERNAL' if jid==first_success else 'JOURNAL'),'Fixed first external reuse and new journal roles')
                    windows,risk=convert_score(p,job,days,inventory)
                    for sid in sids:
                        q=qby[sid];require(q['cutoff']==cutoff and all(q[k] is True for k in ('history_13_complete','mdv_available','liquidity_passed','conditional_member_scope_passed')),'Registered scoring qualification')
                        require(Fraction(q['mdv_evidence']['median_dollar_volume_exact'])>=50000000 and q['mdv_evidence']['conditional_numerical_threshold_passed'] is True,'Saved conditional liquidity threshold')
                    result={k:deepcopy(task[k]) for k in ('security_ids','holding_count','tickers','weight_spec')};result.update(deepcopy(p['score']['metrics']))
                    records.append(dict(task=task,status='EVALUATED',result=result,training_semantics_sha256=semantics,evidence_reference=deepcopy(p['evidence_reference']),eligibility=dict(fractional_risk_passed=risk,liquidity_passed=True,conditional_member_scope_passed=True),scoring_windows=windows,original_fitted_security_order=deepcopy(sids),score_reference=deepcopy(p['score_reference']),inspection_reference=deepcopy(p['inspection_reference']),saved_score_preserved=deepcopy(p['score']),independent_inspection_preserved=deepcopy(p['inspection'])))
                else:
                    require(p['outcome'] in ERRORS and p['score'] is None and p['inspection'] is None and p['error'] is not None,'Explicit nonrankable technical/missing result')
                    records.append(dict(task=task,status=p['outcome'],result=None,training_semantics_sha256=semantics,evidence_reference=deepcopy(p['evidence_reference']),error_preserved=deepcopy(p['error'])))
                ledger.append(dict(logical_ordinal=cursor,decision_index=j,mode_index=mi,task_index=ti,job_id=jid,outcome=p['outcome'],source_kind=p['source_kind'],evidence_preserved=deepcopy({k:v for k,v in p.items() if k not in ('score','inspection')})));cursor+=1
            mode_semantics.append(signatures)
        exact(mode_semantics[0],mode_semantics[1],'Both modes identical registered combinations/specs')
    require(cursor==len(projections),'No extra result projections')
    out=dict(schema='REGISTERED_SCORING_SELECTOR_INPUTS_V1',registration=registration,records=records,logical_task_ledger=ledger,logical_task_count=cursor,source_blocked_task_count=sum(x['outcome']=='SOURCE_BLOCKED' for x in ledger),evaluated_task_count=sum(x['status']=='EVALUATED' for x in records),nonrankable_task_count=sum(x['status']!='EVALUATED' for x in records),budget_reference=deepcopy(budget_reference),budget_audit_reference=deepcopy(budget_audit_reference),source_bytes_authenticated=False,score_reference_bytes_authenticated=False,selector_called=False,score_computed=False,fit_performed=False,account_executed=False,point_in_time_verified=False,complete_ndx_universe_verified=False,outer_lane_prior_resolved=False,selected_weights_are_execution_targets=False,mode_selected_using_results=False,formal_benchmark_passed=False,promotion_allowed=False)
    out['content_sha256']=digest(out);return out
