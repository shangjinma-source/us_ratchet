"""Assemble one registered inner-scoring input; no IO, fit, score or dispatch."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib,json,math,re

CUTOFFS=('2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31')
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
PARAMETERS=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
FLAGS=dict.fromkeys(('source_bytes_authenticated','fit_performed','score_computed','dispatch_authorized','execution_authorized','point_in_time_verified','complete_ndx_universe_verified','promotion_allowed','outer_lane_prior_applied','original_control_account_reused','mode_selected_using_results','missing_values_filled','unequal_window_pooling_allowed'),False)


def require(ok,msg):
    if not ok:raise ValueError(msg)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(encode(v)).hexdigest()
def exact(a,b,msg):require(encode(a)==encode(b),msg)
def ref(v):
    require(type(v) is dict and set(v)=={'path','sha256'} and type(v['path']) is str and v['path'] and type(v['sha256']) is str and re.fullmatch('[a-f0-9]{64}',v['sha256']) is not None,'Explicit document reference')
def ptr(v,r,p):exact(v,dict(r,json_pointer=p),'Exact source role/pointer')
def dates(values,count):
    require(type(values) is list and len(values)==count and values==sorted(set(values)),'Full uncompressed date sequence')
    for v in values:require(type(v) is str and date.fromisoformat(v).isoformat()==v and date.fromisoformat(v).weekday()<5,'Canonical weekday')
def false(v,keys):
    for k in keys:require(v[k] is False,'Conditional permission '+k)
def finite(v,returns=False):
    require(type(v) in (int,float) and math.isfinite(v) and (not returns or v>-1),'Finite nonboolean stored numeric')
    return float(v)
def exact_return(row,key,valuekey):
    value=finite(row[valuekey],True);raw=row[key]
    require(type(raw) is str and Fraction(raw)>-1,'Exact saved return')
    converted=float(Fraction(raw));require(math.isfinite(converted) and converted.hex()==value.hex(),'Exact-to-binary64 saved correspondence')
    return value

def window_check(w,i,price_dates,offset,style):
    start=i*21;require(type(w['window_index']) is int and w['window_index']==i,'Original window order')
    expected=dict(training_freeze_close=price_dates[start+126],evaluation_first_return_end=price_dates[start+127],evaluation_last_return_end=price_dates[start+252])
    for k,v in expected.items():require(w[k]==v,'Causal window date '+k)
    if style=='control':
        keys=('training_return_start','training_return_stop','evaluation_return_start','evaluation_return_stop');base=0
        require(w['blocked_return_indexes']==[],'Original control missing returns')
    else:
        keys=('training_return_index_start','training_return_index_stop','evaluation_return_index_start','evaluation_return_index_stop');base=offset
        require(w['training_price_predecessor']==price_dates[start],'Full window initial predecessor')
        require(w['blocked_price_slots']==[] if style=='channel' else w['missing_price_sessions']==[],'Full source window no missing')
    for k,v in zip(keys,(base+start,base+start+126,base+start+126,base+start+252)):require(type(w[k]) is int and w[k]==v,'Exact window indices')
    require(w['status']=='CONDITIONAL_NUMERIC_WINDOW','Full13 window is numeric')



def issuer_rank(eligible,sids):
    groups={}
    for row in eligible:groups.setdefault(row['issuer_id'],[]).append(row['security_id'])
    names=sorted(groups);groups=[sorted(groups[n]) for n in names];k=len(sids);n=len(groups)
    lookup={sid:(i,j) for i,g in enumerate(groups) for j,sid in enumerate(g)}
    selected=[lookup[sid] for sid in sids];require(all(selected[i][0]<selected[i+1][0] for i in range(k-1)),'Canonical issuer/SID column order')
    dp=[[0]*(k+1) for _ in range(n+1)];dp[n][0]=1
    for i in range(n-1,-1,-1):
        dp[i][0]=1
        for r in range(1,k+1):dp[i][r]=dp[i+1][r]+len(groups[i])*dp[i+1][r-1]
    rank=0;start=0;remaining=k
    for index,variant in selected:
        for i in range(start,index):rank+=len(groups[i])*dp[i+1][remaining-1]
        rank+=variant*dp[index+1][remaining-1];start=index+1;remaining-=1
    return rank


def assemble_registered_scoring_job_inputs(*,registered_job,registered_mode_plan,decision_inputs,universe,channel_bindings,original8_inputs,original8_reference,target_inputs,target_reference,fitter_manifest,fitter_reference,budget_reference):
    for r in (original8_reference,target_reference,fitter_reference,budget_reference):ref(r)
    job=registered_job;identity=job['identity'];cutoff=identity['cutoff'];require(cutoff in CUTOFFS and cutoff==decision_inputs['cutoff'],'Registered real decision coordinate')
    require(identity['schema']=='MULTIDECISION_CAUSAL_SCORING_JOB_IDENTITY_V1' and job['job_id']==digest(identity),'Full new numerical job identity')
    exact(identity['parameters'],PARAMETERS,'Frozen eight fitting parameters');require(identity['weight_spec'] in SPECS,'Three registered specifications')
    exact(identity['scoring_window_contract'],dict(price_count=505,fit_return_count=126,evaluation_return_count=126,step_return_count=21,window_count=13),'Fixed13 scoring windows')
    require(identity['internal_initial_previous_weights'] is None and identity['outer_lane_prior_applied'] is False,'Inner prior is not outer prior')
    require(identity['inner_rolling_fit_prior']=='FIRST_WINDOW_NONE_THEN_SAME_CANDIDATE_PREVIOUS_WINDOW_TARGET' and identity['fee_reference_policy']=='FIRST_NORMALIZED_ORIGINAL_CONTROL_THEN_SAME_CANDIDATE_PREVIOUS_TARGET' and type(identity['candidate_transaction_cost_bps']) is int and identity['candidate_transaction_cost_bps']==10 and identity['candidate_turnover_cost_formula']=='0.5*SUM_ABS_TARGET_MINUS_REFERENCE*10/10000','Frozen inner cost/prior semantics')
    exact(identity['fitter_source_reference'],fitter_reference,'Fitter identity binding');exact(decision_inputs['fitter_source_reference'],fitter_reference,'Decision fitter source')
    exact(identity['scoring_data_reference'],decision_inputs['scoring_data_reference'],'Full77 scoring source')
    ptr(identity['first_candidate_fee_reference'],original8_reference,'/scoring_inputs/normalized_scoring_weights');exact(decision_inputs['incumbent_fee_reference'],identity['first_candidate_fee_reference'],'Decision first fee reference')
    require(fitter_manifest['schema']=='MULTIDECISION_ROLLING_SCORING_NUMERICAL_SOURCES_V1','Actual rolling fitter manifest')
    false(fitter_manifest,('execution_authorized','fit_performed','score_computed','point_in_time_verified','promotion_allowed','outer_cutoff_refit_substitution_allowed'))
    exact(fitter_manifest['required_worker_environment'],dict(PYTHONHASHSEED='0',sys_flags_hash_randomization=0),'Future new-process hash seed requirement')
    require(fitter_manifest['first_anchored_fit_none_interpretation']=='LEGACY_EQUAL_WEIGHT_ANCHOR' and type(fitter_manifest['first_anchored_fit_strength']) is float and fitter_manifest['first_anchored_fit_strength']==.25,'Unchanged initial inner anchor')
    require(type(universe) is list and len(universe)==77 and len({u['security_id'] for u in universe})==77 and len({u['issuer_id'] for u in universe})==76,'Full conditional77/76 inventory')
    by={u['security_id']:u for u in universe};sids=identity['security_ids']
    require(type(sids) is list and len(sids)>0 and len(set(sids))==len(sids) and all(s in by for s in sids),'Selected SID order')
    exact(job['position']['security_ids'],sids,'Position and identity same column order');require(type(job['position']['k']) is int and job['position']['k']==len(sids),'Original k')
    securities=[{k:by[s][k] for k in ('security_id','ticker','issuer_id','risk_chain')} for s in sids]
    for key in ('security_id','ticker','issuer_id'):
        require(len({s[key] for s in securities})==len(sids),'No duplicate class/issuer/ticker')
    for s in securities:require(all(type(v) is str and v and v==v.strip() for v in s.values()),'Explicit identity/risk fields')
    require([q['security_id'] for q in decision_inputs['qualifications']]==[u['security_id'] for u in universe],'Full qualification inventory')
    quals={q['security_id']:q for q in decision_inputs['qualifications']}
    for sid in sids:
        q=quals[sid];require(q['cutoff']==cutoff and all(q[k] is True for k in ('history_13_complete','mdv_available','liquidity_passed','conditional_member_scope_passed')),'Registered candidate qualification required')
    price_dates=decision_inputs['scoring_price_dates'];dates(price_dates,505);require(price_dates[-1]==cutoff,'Cutoff close bounds all scoring data')
    require(target_inputs['schema']=='MULTIDECISION_TARGET_SCORING_INPUTS_V1' and [m['mode'] for m in target_inputs['modes']]==list(MODES),'Both FX modes retained')
    false(target_inputs,('point_in_time_verified','benchmark_qualified','score_computed','fit_performed','mode_selected_using_results','partial_window_pooling_allowed','missing_values_filled'))
    require([m['mode'] for m in decision_inputs['mode_sources']]==list(MODES),'Registered modes not substituted')
    j=CUTOFFS.index(cutoff);mode=identity['fx_mode'];require(mode in MODES,'Registered FX mode');mi=MODES.index(mode)
    for k in range(2):
        source=decision_inputs['mode_sources'][k];td=target_inputs['modes'][k]['decisions'][j]
        ptr(source['reference'],target_reference,f'/modes/{k}/decisions/{j}');exact(td['required_price_dates'],price_dates,'Target exact505 source window')
        require(td['cutoff']==cutoff and len(td['windows'])==13 and type(td['window_count']) is int and td['window_count']==13,'Both modes full13 source denominator')
        require(type(td['complete_thirteen_window_numeric_supply']) is bool and source['complete_thirteen_windows'] is td['complete_thirteen_window_numeric_supply'],'Registered mode availability')
    ptr(identity['target_reference'],target_reference,f'/modes/{mi}/decisions/{j}')
    mp=registered_mode_plan;require(mp['mode']==mode and type(mp['task_count']) is int and mp['task_count']==len(mp['tasks']) and mp['score_dispatch_authorized'] is False,'Complete registered mode node')
    exact(mp['source_preserved'],decision_inputs['mode_sources'][mi],'Registered source mode evidence')
    ids=[x['job_id'] for x in mp['tasks']];require(len(ids)==len(set(ids)) and job['job_id'] in ids,'Job belongs to exact registered task set')
    task_index=ids.index(job['job_id']);exact(mp['tasks'][task_index],job,'Original registered job unchanged')
    require(mp['status']==job['status'] and job['status'] in ('SOURCE_BLOCKED','PLANNED_NOT_ATTEMPTED'),'Mode/task registered status')
    eligible=[by[q['security_id']] for q in decision_inputs['qualifications'] if all(q[k] is True for k in ('history_13_complete','mdv_available','liquidity_passed','conditional_member_scope_passed'))]
    rank=issuer_rank(eligible,sids);require(type(job['position']['rank']) is int and job['position']['rank']==rank,'Registered selection rank and SID order')
    td=target_inputs['modes'][mi]['decisions'][j];complete=td['complete_thirteen_window_numeric_supply']
    out=dict(schema='REGISTERED_MULTIDECISION_SCORING_JOB_INPUTS_V1',job_id=job['job_id'],registered_job_preserved=deepcopy(job),budget_reference=deepcopy(budget_reference),registered_task_pointer=f'/plan/rows/{j}/mode_plans/{mi}/tasks/{task_index}',fitter_reference=deepcopy(fitter_reference),required_worker_environment=deepcopy(fitter_manifest['required_worker_environment']),fx_mode=mode,cutoff=cutoff,ordered_securities=securities,source_references=dict(history=deepcopy(identity['scoring_data_reference']),target=deepcopy(identity['target_reference']),original8=deepcopy(identity['first_candidate_fee_reference']),fitter=deepcopy(fitter_reference)),rolling_inputs=None,reducer_inputs=None,window_metadata=deepcopy(td['windows']),**FLAGS)
    if not complete:
        require(job['status']=='SOURCE_BLOCKED','Unavailable target cannot be planned')
        out.update(status='SOURCE_BLOCKED',block_reason='REGISTERED_FULL13_TARGET_SUPPLY_INCOMPLETE',target_decision_preserved=deepcopy(td));out['content_sha256']=digest(out);return out
    require(job['status']=='PLANNED_NOT_ATTEMPTED','Only unattempted registered job assembly')
    require(type(channel_bindings) is list and len(channel_bindings)==len(sids),'Exact selected channel set')
    candidate_columns=[];exact_columns=[];bindings=[]
    for sid,binding in zip(sids,channel_bindings):
        exact(binding['coordinate'],by[sid],'Complete source coordinate and order');ref(binding['reference']);ptr(quals[sid]['history_reference'],binding['reference'],f'/decisions/{j}')
        ch=binding['channel'];require(ch['schema']=='MULTIDECISION_SCORING_HISTORY_CHANNEL_V1' and ch['ticker']==by[sid]['ticker'],'History ticker binding')
        false(ch,('point_in_time_verified','fit_performed','score_computed','missing_or_blocked_slots_dropped','unequal_window_pooling_allowed'))
        d=ch['decisions'][j];exact(d['required_price_dates'],price_dates,'Candidate505 dates');require(d['cutoff']==cutoff and d['complete_thirteen_window_numeric_supply'] is True and len(d['windows'])==13,'No blocked candidate window')
        offset=d['price_index_start'];require(type(offset) is int and offset>=0 and type(d['price_index_stop']) is int and d['price_index_stop']==offset+505,'Original union offsets')
        rows=ch['return_rows'];require(len(rows)>=offset+504,'Complete return array')
        selected=rows[offset:offset+504]
        for n,row in enumerate(selected):require(row['session']==price_dates[n+1] and row['previous_session']==price_dates[n] and row['status']=='CONDITIONAL_NUMERIC_SLOT' and row['dividends_included'] is False,'Causal candidate return source slot')
        candidate_columns.append([exact_return(r,'split_only_return_exact','split_only_return_float') for r in selected]);exact_columns.append([r['split_only_return_exact'] for r in selected])
        for i,w in enumerate(d['windows']):window_check(w,i,price_dates,offset,'channel')
        bindings.append(dict(coordinate=deepcopy(binding['coordinate']),reference=deepcopy(binding['reference']),return_index_start=offset,return_index_stop=offset+504,decision_metadata=deepcopy(d)))
    oi=original8_inputs;require(oi['schema']=='ORIGINAL_EIGHT_FIXED_DAILY_WEIGHT_SCORING_INPUTS_V1','Original8 fixed daily-weight source')
    false(oi,('fit_performed','score_computed','point_in_time_verified','account_simulated','entry_fee_applied','missing_slots_dropped'))
    od=oi['decisions'][j];require(od['cutoff']==cutoff and len(od['return_rows'])==504 and len(od['windows'])==13,'Original8 full cutoff');exact(od['price_dates'],price_dates,'Original8 same505')
    incumbent=[]
    for n,row in enumerate(od['return_rows']):
        require(row['session']==price_dates[n+1] and row['previous_session']==price_dates[n] and row['missing_security_ids']==[],'Original8 complete causal return');incumbent.append(finite(row['return_float'],True))
    for i,w in enumerate(od['windows']):window_check(w,i,price_dates,0,'control')
    originals=oi['original_control_preserved']['securities'];require(len(originals)==8 and len({s['ticker'] for s in originals})==8,'Original8 complete identity')
    weights={s['ticker']:finite(s['target_weight']) for s in originals};require(min(weights.values())>=0 and sum(weights.values())>0,'Original weight evidence')
    exact(sorted(oi['normalized_scoring_weights']),sorted(weights),'Normalized fee reference ticker scope')
    total=sum(weights.values());require(math.isfinite(total) and total>0,'Finite positive original weight sum')
    for ticker,weight in weights.items():require(finite(oi['normalized_scoring_weights'][ticker]).hex()==(weight/total).hex(),'Saved first-fee normalization correspondence')
    target_mode=target_inputs['modes'][mi];slots=target_mode['return_slots'];days=target_inputs['session_dates'];require(type(days) is list and price_dates[0] in days,'Target full union calendar')
    offset=days.index(price_dates[0]);exact(days[offset:offset+505],price_dates,'Target union offset');require(len(slots)==len(days)-1,'All target source slots')
    targets=[];target_exact=[]
    for n,row in enumerate(slots[offset:offset+504]):
        require(row['session']==price_dates[n+1] and row['previous_session']==price_dates[n] and row['status']=='CONDITIONAL_NUMERIC_RETURN','Complete target return')
        targets.append(exact_return(row,'return_exact','return_float'));target_exact.append(row['return_exact'])
    require(len(targets)==504,'Full target504')
    for i,w in enumerate(td['windows']):window_check(w,i,price_dates,offset,'target')
    matrix=[list(row) for row in zip(*candidate_columns)];common=dict(cutoff=cutoff,return_dates=deepcopy(price_dates[1:]),securities=deepcopy(securities),candidate_returns=matrix)
    out.update(status='ASSEMBLED_NOT_DISPATCHED',rolling_inputs=dict(deepcopy(common),weight_spec=identity['weight_spec']),reducer_inputs=dict(deepcopy(common),incumbent_returns=incumbent,target_returns=targets,original_incumbent_weights=weights),candidate_return_exact_columns=exact_columns,target_return_exact=target_exact,channel_bindings_preserved=bindings,original8_definition_preserved=deepcopy(oi['original_control_preserved']),normalized_first_fee_reference_preserved=deepcopy(oi['normalized_scoring_weights']),candidate_original_weights_not_available_before_fit=True,reducer_requires_fitted_windows=True,numeric_semantics='COPY_SAVED_BINARY64_RETURNS;EXACT_FRACTION_CORRESPONDENCE_NOT_NEW_ECONOMIC_RECOMPUTATION')
    out['content_sha256']=digest(out);return out
