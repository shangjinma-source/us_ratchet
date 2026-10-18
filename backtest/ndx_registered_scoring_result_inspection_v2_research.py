"""V2 saved rolling recovery evidence; no fitting or KKT recertification."""
from copy import deepcopy
from fractions import Fraction
import hashlib,json,math
from backtest import ndx_multidecision_window_scoring_inspection_research as arithmetic

SCORE_INSPECTOR_SHA='cceb0cb4ed97d4b4f94fe049558c67d0b2501090cdfd4da65f59104490416bf8'
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
CUTOFFS=('2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31')
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')


def require(ok,message):
    if not ok:raise ValueError(message)
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def exact(a,b,m):
    try:arithmetic.exact(a,b)
    except ValueError as error:raise ValueError(m) from error

RECOVERY_SOURCES = {
    'ndx_projection_reconstruction_research.py': 'f72bd35a7eb3295194dfb751898bb7213f93f95d44df0b9539dec2751654320e',
    'ndx_projection_certificate_research.py': '1a795b99c5c4d9b4e536bde1c8b70e4f08a94afeb8bcffbf3aaabd5c61e545b9',
}
AUTHORITY_KEYS = {'task_recomputed','primal_infeasibility_proven','promotion_allowed','order_generation_allowed'}
CERT_BASE = {'schema','scope','certified','certification_kind','target_preprocessing','target','candidate','constraints','objective_value','objective','top_subset_count','max_top_subsets','tolerances','primal_residuals','individual_bound_residuals','primal_passed','status'} | AUTHORITY_KEYS
CERT_KKT = {'active_constraints','equality_multiplier','stationarity_residuals','stationarity_max_abs','complementarity_max_abs','dual_passed','all_top_subsets_examined'}
RECON_BASE = {'schema','scope','certified','weights','proposed_candidate','raw_target','constraints','proposed_certificate','source_hashes','activity_tolerance','rank_relative_tolerance','max_top_subsets','active_subset_search_performed','status'} | AUTHORITY_KEYS
RECON_AFFINE = {'affine_constraints','affine_rows','affine_rhs','affine_rank','affine_singular_values','affine_center','nullspace_target','affine_center_residuals'}
RECON_FINAL = {'certificate','reconstructed_candidate','reconstructed_affine_residuals'}


def finite(value):
    require(type(value) is float and math.isfinite(value),'Finite saved binary64 evidence')
    return value


def numeric_map(value,names):
    require(type(value) is dict and set(value)==set(names),'Complete original ticker evidence')
    for number in value.values():finite(number)


def certificate_evidence(c,constraints,names):
    require(type(c) is dict,'Certificate object')
    status=c.get('status')
    extras = CERT_KKT if status in ('NUMERICAL_KKT_CERTIFIED','KKT_NOT_CERTIFIED') else ({'multiplier_search_error'} if status=='MULTIPLIER_SEARCH_UNRESOLVED' else set())
    require(status in ('PRIMAL_REJECTED','SUBSET_BUDGET_EXCEEDED','MULTIPLIER_SEARCH_UNRESOLVED','INVALID_MULTIPLIER_OUTPUT','NUMERICAL_KKT_CERTIFIED','KKT_NOT_CERTIFIED') and set(c)==CERT_BASE|extras,'Frozen certificate status/fields')
    require(c['schema']=='ndx_projection_kkt_certificate_research_v1' and c['scope']=='FIXED_TARGET_CONVEX_PROJECTION_ONLY' and c['certification_kind']=='NUMERICAL_KKT_WITH_DISCLOSED_ABSOLUTE_TOLERANCES','Certificate schema/scope')
    require(c['objective']=='SUM_SQUARED_DISTANCE_TO_NORMALIZED_TARGET' and c['target_preprocessing']=='CLIP_NEGATIVE_NORMALIZE_OR_UNIFORM_IF_ALL_NONPOSITIVE','Original certificate objective')
    for flag in AUTHORITY_KEYS:require(c[flag] is False,'Certificate authority')
    exact(c['constraints'],constraints,'Original certificate constraints')
    exact(c['tolerances'],dict(primal=1e-10,active=1e-9,stationarity=1e-9,complementarity=1e-10),'Fixed certificate tolerances')
    numeric_map(c['candidate'],names);numeric_map(c['target'],names)
    require(min(c['target'].values())>=0 and abs(sum(c['target'].values())-1.)<=1e-12,'Normalized certificate target')
    require(finite(c['objective_value'])>=0,'Nonnegative original objective')
    require(type(c['top_subset_count']) is int and c['top_subset_count']==math.comb(len(names),constraints['top_weight_count']) and type(c['max_top_subsets']) is int and c['max_top_subsets']==100000,'Exact subset denominator')
    residual_keys={'simplex_abs','lower','upper','top_k','hhi','effective_n_deficit'}
    if constraints['group_labels'] is not None:residual_keys|={'group:'+label for label in constraints['group_labels'].values()}
    require(type(c['primal_residuals']) is dict and set(c['primal_residuals'])==residual_keys,'Original primal residual denominator')
    residuals=[finite(v) for v in c['primal_residuals'].values()]
    require(c['primal_passed'] is all(v<=1e-10 for v in residuals),'Saved primal residual/status correspondence')
    require(type(c['individual_bound_residuals']) is dict and set(c['individual_bound_residuals'])==set(names),'Individual bound denominator')
    for row in c['individual_bound_residuals'].values():
        require(type(row) is dict and set(row)=={'lower','upper'},'Individual bound fields')
        for v in row.values():finite(v)
    require(c['certified'] is (status=='NUMERICAL_KKT_CERTIFIED'),'Certificate certified/status correspondence')
    if status=='PRIMAL_REJECTED':require(c['primal_passed'] is False,'Rejected primal')
    else:require(c['primal_passed'] is True,'Primal passed before later certificate stage')
    if status=='SUBSET_BUDGET_EXCEEDED':require(c['top_subset_count']>100000,'Actual subset budget exceeded')
    elif status!='PRIMAL_REJECTED':require(c['top_subset_count']<=100000,'Subset budget before KKT')
    if status=='MULTIPLIER_SEARCH_UNRESOLVED':require(type(c['multiplier_search_error']) is str,'Original multiplier error')
    if extras==CERT_KKT:
        require(c['all_top_subsets_examined'] is True and type(c['dual_passed']) is bool,'Full saved KKT examination flags')
        numeric_map(c['stationarity_residuals'],names)
        finite(c['equality_multiplier']);stationarity=finite(c['stationarity_max_abs']);complementarity=finite(c['complementarity_max_abs'])
        require(stationarity>=0 and complementarity>=0,'Nonnegative KKT maxima')
        exact(stationarity,max(abs(v) for v in c['stationarity_residuals'].values()),'Saved stationarity max linkage')
        require(type(c['active_constraints']) is list,'Saved active constraints')
        labels=[];multipliers=[];complements=[]
        for row in c['active_constraints']:
            require(type(row) is dict and set(row)=={'name','residual','multiplier','complementarity_residual'},'Active constraint exact fields')
            name=row['name'];require(type(name) is str and name,'Active constraint name');labels.append(name)
            allowed={'HHI'}|{'LOWER:'+n for n in names}|{'UPPER:'+n for n in names}
            if constraints['group_labels'] is not None:allowed|={'GROUP:'+g for g in constraints['group_labels'].values()}
            if name.startswith('TOP:'):
                subset=name[4:].split(',');require(len(subset)==constraints['top_weight_count'] and len(set(subset))==len(subset) and subset==[n for n in names if n in subset],'Original ordered top subset')
            else:require(name in allowed,'Known active constraint role')
            residual=finite(row['residual']);multiplier=finite(row['multiplier']);component=finite(row['complementarity_residual'])
            exact(component,residual*multiplier,'Saved complementarity product')
            multipliers.append(multiplier);complements.append(abs(component))
        require(len(labels)==len(set(labels)),'Unique saved active constraints')
        require(c['dual_passed'] is all(v>=0 for v in multipliers),'Saved dual sign check')
        exact(complementarity,max(complements,default=0.),'Saved complementarity max')
        require(c['certified'] is (c['dual_passed'] and stationarity<=1e-9 and complementarity<=1e-10),'Saved KKT tolerance/status linkage')
    return c['certified']


def recovery_attempt(attempt,securities,sources):
    names=[s['ticker'] for s in securities];k=len(names)
    two={'optimizer_message','reconstruction'};four=two|{'independent_certificate','failed_optimizer_vector'}
    require(type(attempt) is dict and set(attempt) in (two,four) and type(attempt['optimizer_message']) is str,'Exact original recovery attempt fields')
    r=attempt['reconstruction'];require(type(r) is dict,'Saved reconstruction object')
    status=r.get('status');early=('SUBSET_BUDGET_EXCEEDED','AFFINE_SVD_UNRESOLVED');middle=('PROPOSED_AFFINE_FACE_UNRESOLVED','PROPOSED_FACE_HHI_INTERSECTION_UNRESOLVED','NONFINITE_RECONSTRUCTION');final=('RECONSTRUCTION_NOT_CERTIFIED','RECONSTRUCTED_NUMERICAL_KKT_CERTIFIED')
    require(status in early+middle+final,'Known frozen reconstruction status')
    expected=RECON_BASE.copy()
    if status not in early:expected|=RECON_AFFINE
    if status in ('PROPOSED_FACE_HHI_INTERSECTION_UNRESOLVED','NONFINITE_RECONSTRUCTION')+final:expected|={'hhi_radius_squared'}
    if status in final:expected|=RECON_FINAL
    require(set(r)==expected,'Frozen reconstruction stage exact fields')
    require(r['schema']=='ndx_projection_reconstruction_research_v1' and r['scope']=='PROPOSED_ACTIVE_FACE_PROJECTION_ONLY','Reconstruction schema/scope')
    for key in AUTHORITY_KEYS|{'active_subset_search_performed'}:require(r[key] is False,'Reconstruction authority')
    exact(r['activity_tolerance'],1e-6,'Original active-face tolerance');exact(r['rank_relative_tolerance'],1e-12,'Original rank tolerance')
    require(type(r['max_top_subsets']) is int and r['max_top_subsets']==100000,'Original reconstruction subset budget')
    expected_sources={p:h for p,h in sources.items() if p.replace('\\','/').rsplit('/',1)[-1] in RECOVERY_SOURCES}
    require(len(expected_sources)==2 and all(h==RECOVERY_SOURCES[p.replace('\\','/').rsplit('/',1)[-1]] for p,h in expected_sources.items()),'Frozen reconstruction two-source binding')
    exact(r['source_hashes'],expected_sources,'Recovery source subset of registered closure')
    grouped=r['constraints']['group_labels'] is not None
    constraints=dict(max_weight=max(.45,1./k),min_weight=.05,top_weight_count=min(3,k-1),top_weight_cap=max(.8,min(3,k-1)/k),min_effective_n=max(1.,.7*k),group_labels={s['ticker']:s['risk_chain'] for s in securities} if grouped else None,max_group_weight=.55 if grouped else None)
    exact(r['constraints'],constraints,'Fixed original grouped or fallback envelope')
    require((math.comb(k,constraints['top_weight_count'])>100000)==(status=='SUBSET_BUDGET_EXCEEDED'),'Saved reconstruction subset branch reachable')
    numeric_map(r['raw_target'],names);numeric_map(r['proposed_candidate'],names)
    certificate_evidence(r['proposed_certificate'],constraints,names)
    exact(r['proposed_certificate']['candidate'],r['proposed_candidate'],'Original proposed certificate candidate')
    clipped=[max(r['raw_target'][name],0.) for name in names]
    if max(clipped)==0:clipped=[1.]*k
    total=sum(clipped);require(math.isfinite(total) and total>0,'Finite normalized original raw target')
    require(all(math.isclose(r['proposed_certificate']['target'][name],value/total,rel_tol=0,abs_tol=1e-12) for name,value in zip(names,clipped)),'Original raw target/preprocessing linkage within binary64 summation allowance')
    if status not in early:
        rows=r['affine_rows'];labels=r['affine_constraints'];count=len(labels)
        require(type(labels) is list and count>0 and labels[0]=='SIMPLEX' and len(set(labels))==count and all(type(x) is str for x in labels),'Saved affine labels')
        require(type(rows) is list and len(rows)==count and all(type(row) is list and len(row)==k for row in rows),'Saved affine dimensions')
        for row in rows:
            for v in row:finite(v)
        for key,length in (('affine_rhs',count),('affine_center_residuals',count),('affine_center',k),('nullspace_target',k),('affine_singular_values',min(count,k))):
            require(type(r[key]) is list and len(r[key])==length,'Saved affine vector dimension')
            for v in r[key]:finite(v)
        require(type(r['affine_rank']) is int and 0<=r['affine_rank']<=min(count,k),'Saved affine rank')
        require((max(abs(v) for v in r['affine_center_residuals'])>1e-10)==(status=='PROPOSED_AFFINE_FACE_UNRESOLVED'),'Saved reconstruction affine branch reachable')
        for label,row,rhs in zip(labels,rows,r['affine_rhs']):
            if label=='SIMPLEX':expected_row=[1.]*k;expected_rhs=1.
            elif label.startswith(('LOWER:','UPPER:')):
                ticker=label.split(':',1)[1];require(ticker in names,'Original affine ticker')
                expected_row=[float(n==ticker) for n in names];expected_rhs=constraints['min_weight' if label.startswith('LOWER:') else 'max_weight']
            elif label.startswith('TOP:'):
                subset=label[4:].split(',');require(len(subset)==constraints['top_weight_count'] and len(set(subset))==len(subset) and subset==[n for n in names if n in subset],'Original affine top subset')
                expected_row=[float(n in subset) for n in names];expected_rhs=constraints['top_weight_cap']
            else:
                require(grouped and label.startswith('GROUP:') and label[6:] in constraints['group_labels'].values(),'Original affine group')
                expected_row=[float(constraints['group_labels'][n]==label[6:]) for n in names];expected_rhs=.55
            exact(row,expected_row,'Saved affine original constraint coefficients');exact(rhs,expected_rhs,'Saved affine original bound')
    if 'hhi_radius_squared' in r:
        radius=finite(r['hhi_radius_squared'])
        require((radius < -1e-12)==(status=='PROPOSED_FACE_HHI_INTERSECTION_UNRESOLVED'),'Saved reconstruction HHI branch reachable')
    success=status==final[1];require(r['certified'] is success,'Reconstruction certified/status')
    if not success:require(r['weights'] is None,'Failed reconstruction has no accepted weights')
    if status in final:
        certificate_evidence(r['certificate'],constraints,names);numeric_map(r['reconstructed_candidate'],names)
        exact(r['certificate']['candidate'],r['reconstructed_candidate'],'Reconstructed certificate candidate')
        exact(r['certificate']['target'],r['proposed_certificate']['target'],'Same original normalized target')
        require(r['certificate']['certified'] is success,'Internal reconstruction certificate status')
        require(type(r['reconstructed_affine_residuals']) is list and len(r['reconstructed_affine_residuals'])==len(r['affine_constraints']),'Reconstructed affine residual dimensions')
        for v in r['reconstructed_affine_residuals']:finite(v)
    if set(attempt)==two:require(not success and grouped,'Two-field evidence only unresolved grouped reconstruction before fallback')
    else:
        require(success,'Four-field recovery only after reconstruction success')
        vector=attempt['failed_optimizer_vector'];require(type(vector) is list and len(vector)==2*k+1,'Full failed optimizer vector')
        for v in vector:finite(v)
        exact(dict(zip(names,vector[:k])),r['proposed_candidate'],'Failed optimizer vector linkage')
        numeric_map(r['weights'],names);exact(r['weights'],r['certificate']['candidate'],'Reconstruction weights linkage')
        certificate_evidence(attempt['independent_certificate'],constraints,names)
        exact(attempt['independent_certificate']['candidate'],r['weights'],'Independent candidate linkage')
        exact(attempt['independent_certificate']['target'],r['certificate']['target'],'Independent target linkage')
        success=attempt['independent_certificate']['certified']
        if not success:require(grouped,'Uncertified ungrouped fallback cannot return fitted window')
    return dict(grouped=grouped,successful=success,weights=r['weights'] if success else None,raw_target=r['raw_target'])


def inspect_recovery_evidence(attempts,windows,securities,spec,sources):
    require(type(attempts) is list and len(attempts)<=26,'At most two saved attempts per thirteen windows')
    if spec=='equal_weight':require(not attempts and all(w['projection_relaxed'] is False for w in windows),'Equal has no recovery or relaxation')
    parsed=[recovery_attempt(a,securities,sources) for a in attempts]
    names=[s['ticker'] for s in securities];n=len(parsed)
    # Dynamic programming preserves all possible ordered assignments. No stored
    # window index exists: existence is established, never a unique attribution.
    states={0};reachable=[]
    for w in windows:
        next_states=set()
        def matches(a):return a['successful'] and all(a['weights'][name]==value for name,value in zip(names,w['weights']))
        for position in states:
            next_states.add(position)  # successful ordinary optimizer: no probe record
            if position==n:continue
            a=parsed[position]
            if not w['projection_relaxed']:
                if a['grouped'] and matches(a):next_states.add(position+1)
            else:
                if a['grouped'] and not a['successful']:
                    next_states.add(position+1)  # ordinary successful fallback
                    if position+1<n:
                        b=parsed[position+1]
                        if not b['grouped'] and matches(b) and a['raw_target']==b['raw_target']:next_states.add(position+2)
                elif not a['grouped'] and matches(a):next_states.add(position+1)
        states=next_states;reachable.append(sorted(states))
    require(n in states,'Recovery sequence has no legal ordered thirteen-window attribution')
    return dict(schema='REGISTERED_ROLLING_RECOVERY_EVIDENCE_INSPECTION_V2',attempt_count=n,failed_group_attempt_count=sum(a['grouped'] and not a['successful'] for a in parsed),successful_recovery_count=sum(a['successful'] for a in parsed),ordered_window_assignment_exists=True,unique_window_assignment_claimed=False,window_assignment_method='ORDERED_DYNAMIC_PROGRAMMING_ALLOWING_UNRECORDED_ORDINARY_SOLVER_RETURNS',saved_certificate_fields_and_linkages_verified=True,certificate_residuals_independently_recomputed=False,recovery_certificates_recomputed=False,optimizer_rerun=False,failed_group_recovery_is_economic_infeasibility=False)


def inspect_registered_scoring_result(*,assembled,saved_fit,saved_score,saved_score_inspection,
                                      numerical_source_hashes,channel_bindings,original8_inputs,target_inputs):
    require(assembled['schema']=='REGISTERED_MULTIDECISION_SCORING_JOB_INPUTS_V1' and assembled['status']=='ASSEMBLED_NOT_DISPATCHED','Complete assembled inputs')
    require(assembled['content_sha256']==digest({k:v for k,v in assembled.items() if k!='content_sha256'}),'Input content hash')
    for key in ('source_bytes_authenticated','fit_performed','score_computed','dispatch_authorized','execution_authorized','point_in_time_verified','complete_ndx_universe_verified','promotion_allowed','outer_lane_prior_applied','original_control_account_reused','mode_selected_using_results','missing_values_filled','unequal_window_pooling_allowed'):
        require(assembled[key] is False,'Original assembled authority '+key)
    job=assembled['registered_job_preserved'];identity=job['identity']
    require(job['job_id']==assembled['job_id']==digest(identity),'Registered identity hash')
    require(job['status']=='PLANNED_NOT_ATTEMPTED' and identity['fx_mode']==assembled['fx_mode'],'Unattempted registered mode')
    require(identity['cutoff']==assembled['cutoff'] and identity['cutoff'] in CUTOFFS,'Registered cutoff')
    require(identity['weight_spec'] in SPECS,'Weight specification')
    require(identity['internal_initial_previous_weights'] is None and identity['outer_lane_prior_applied'] is False,'Inner prior scope')
    exact(assembled['required_worker_environment'],dict(PYTHONHASHSEED='0',sys_flags_hash_randomization=0),'Declared required hash seed')
    fit=assembled['rolling_inputs'];score=assembled['reducer_inputs'];names=[s['ticker'] for s in fit['securities']]
    require(set(fit)=={'cutoff','return_dates','securities','candidate_returns','weight_spec'},'Complete fit arguments')
    require(set(score)=={'cutoff','return_dates','securities','candidate_returns','incumbent_returns','target_returns','original_incumbent_weights'},'Complete reducer arguments')
    for key in ('cutoff','return_dates','securities','candidate_returns'):exact(fit[key],score[key],'Fit and score share exact original matrix/dates')
    exact(fit['securities'],assembled['ordered_securities'],'Ordered original security metadata')
    exact([s['security_id'] for s in fit['securities']],identity['security_ids'],'Original job column order')
    require(fit['weight_spec']==identity['weight_spec'],'Fitted specification binding')
    dates=fit['return_dates'];matrix=fit['candidate_returns'];k=len(names);j=CUTOFFS.index(fit['cutoff']);mi=MODES.index(identity['fx_mode'])
    require(len(dates)==len(matrix)==504 and dates[-1]==fit['cutoff'],'Full504 fit/score inputs')
    require(len(channel_bindings)==k and len(assembled['channel_bindings_preserved'])==k,'Complete selected channels')
    columns=[];exacts=[]
    for column,binding in enumerate(channel_bindings):
        preserved=assembled['channel_bindings_preserved'][column];ch=binding['channel'];coordinate=binding['coordinate'];decision=ch['decisions'][j]
        exact(preserved['coordinate'],coordinate,'Full saved coordinate');exact(preserved['reference'],binding['reference'],'Saved channel reference')
        exact({key:coordinate[key] for key in ('security_id','ticker','issuer_id','risk_chain')},fit['securities'][column],'Selected source security')
        exact(preserved['decision_metadata'],decision,'Original decision metadata')
        exact(decision['required_price_dates'][1:],dates,'Source cutoff calendar')
        require(ch['ticker']==names[column] and decision['cutoff']==fit['cutoff'] and decision['complete_thirteen_window_numeric_supply'] is True,'Original channel complete')
        offset=decision['price_index_start'];require(type(offset) is int and offset>=0,'Source start offset')
        require(type(preserved['return_index_start']) is int and type(preserved['return_index_stop']) is int and preserved['return_index_start']==offset and preserved['return_index_stop']==offset+504,'Original matrix source offsets')
        selected=ch['return_rows'][offset:offset+504];require(len(selected)==504,'Complete source rows')
        floats=[];strings=[]
        for n,row in enumerate(selected):
            require(row['session']==dates[n] and row['previous_session']==decision['required_price_dates'][n] and row['status']=='CONDITIONAL_NUMERIC_SLOT' and row['dividends_included'] is False,'Original return slot')
            value=row['split_only_return_float'];text=row['split_only_return_exact']
            require(type(value) is float and math.isfinite(value) and value>-1 and type(text) is str and float(Fraction(text)).hex()==value.hex(),'Exact-to-binary64 source correspondence')
            floats.append(value);strings.append(text)
        columns.append(floats);exacts.append(strings)
    exact(matrix,[list(row) for row in zip(*columns)],'Actual original source matrix unchanged')
    exact(assembled['candidate_return_exact_columns'],exacts,'Exact source values preserved')
    control=original8_inputs['decisions'][j];exact(control['price_dates'][1:],dates,'Original8 same calendar')
    exact(score['incumbent_returns'],[r['return_float'] for r in control['return_rows']],'Original8 saved binary64 returns')
    exact(assembled['original8_definition_preserved'],original8_inputs['original_control_preserved'],'Original8 full definition')
    weights={r['ticker']:float(r['target_weight']) for r in original8_inputs['original_control_preserved']['securities']}
    exact(score['original_incumbent_weights'],weights,'Original unnormalized fee weights')
    exact(assembled['normalized_first_fee_reference_preserved'],original8_inputs['normalized_scoring_weights'],'Original normalized fee declaration')
    total=sum(weights.values());require(math.isfinite(total) and total>0,'Finite positive original8 weight total');exact(original8_inputs['normalized_scoring_weights'],{key:value/total for key,value in weights.items()},'Original fee normalization')
    mode=target_inputs['modes'][mi];td=mode['decisions'][j];exact(td['required_price_dates'][1:],dates,'Target calendar')
    require(mode['mode']==identity['fx_mode'] and td['complete_thirteen_window_numeric_supply'] is True,'Selected target mode not substituted')
    offset=target_inputs['session_dates'].index(td['required_price_dates'][0]);selected=mode['return_slots'][offset:offset+504]
    require(len(selected)==504,'Full target slots');targets=[];texts=[]
    for n,row in enumerate(selected):
        require(row['session']==dates[n] and row['previous_session']==td['required_price_dates'][n] and row['status']=='CONDITIONAL_NUMERIC_RETURN','Target return source slot')
        value=row['return_float'];text=row['return_exact'];require(type(value) is float and type(text) is str and math.isfinite(value) and float(Fraction(text)).hex()==value.hex(),'Target exact value')
        targets.append(value);texts.append(text)
    exact(score['target_returns'],targets,'Target source returns');exact(assembled['target_return_exact'],texts,'Target source exact evidence')
    require(saved_fit['schema']=='MULTIDECISION_CAUSAL_ROLLING_FITS_V1' and saved_fit['cutoff']==fit['cutoff'] and saved_fit['weight_spec']==fit['weight_spec'],'Saved fit schema/identity')
    exact(saved_fit['securities'],fit['securities'],'Fit metadata');exact(saved_fit['source_hashes'],numerical_source_hashes,'Registered fitter closure')
    require(type(numerical_source_hashes) is dict and len(numerical_source_hashes)==25,'Complete registered25 sources')
    require(saved_fit['numerical_projection']=='V3_CERTIFIED_RECOVERY_ORIGINAL_PROBE_CLOSURE' and saved_fit['inner_prior_policy']=='FIRST_NONE_THEN_SAME_CANDIDATE_PREVIOUS_TARGET','Original recovery/prior semantics')
    for key in ('source_bytes_authenticated','outer_lane_prior_applied','score_computed','point_in_time_verified','account_executed','promotion_allowed'):require(saved_fit[key] is False,'No fit authority')
    require(saved_fit['fit_performed'] is (fit['weight_spec']!='equal_weight'),'Actual fitter role')
    windows=saved_fit['windows'];require(type(windows) is list and len(windows)==13,'Thirteen preserved fitted windows');previous=None
    for i,w in enumerate(windows):
        start=21*i;v=w['weights'];require(type(v) is list and len(v)==k and all(type(x) is float and math.isfinite(x) and x>=0 for x in v),'Saved complete weight vector')
        require(math.isclose(sum(v),1.,rel_tol=0,abs_tol=1e-9),'Saved original simplex')
        payload=dict(dates=dates[start:start+126],tickers=names,returns=matrix[start:start+126]);anchored=fit['weight_spec']==SPECS[2]
        expected=dict(window_index=i,fit_first_return_end=dates[start],fit_last_return_end=dates[start+125],evaluation_first_return_end=dates[start+126],evaluation_last_return_end=dates[start+251],fit_data_sha256=digest(payload),weights=v,projection_relaxed=w['projection_relaxed'],requested_inner_prior=deepcopy(previous),fitter_anchor_used=deepcopy(previous) if anchored else None,fitter_anchor_strength=.25 if anchored else 0.)
        require(type(w['projection_relaxed']) is bool,'Projection flag type');exact(w,expected,'Saved window hash/causal fit/prior/anchor')
        if fit['weight_spec']=='equal_weight':exact(v,[1./k]*k,'Explicit equal weights')
        previous=dict(zip(names,v))
    attempts=saved_fit['reconstruction_attempts']
    recovery_detail=inspect_recovery_evidence(attempts,windows,fit['securities'],fit['weight_spec'],numerical_source_hashes)
    # All fields retained: this is an evidence consistency check, not recertification.
    expected_keys={'schema','cutoff','securities','weight_spec','windows','reconstruction_attempts','numerical_projection','inner_prior_policy','source_hashes','source_bytes_authenticated','outer_lane_prior_applied','fit_performed','score_computed','point_in_time_verified','account_executed','promotion_allowed'}
    require(set(saved_fit)==expected_keys,'Complete fit return body')
    detail=arithmetic.inspect_fitted_scoring_windows(**score,fitted_windows=windows,saved_score=saved_score)
    exact(saved_score_inspection,detail,'Saved independent score evidence reproduced')
    return dict(schema='REGISTERED_SCORING_RESULT_INSPECTION_V1',status='PASS',job_id=assembled['job_id'],window_count=13,fit_matrix_hashes=[w['fit_data_sha256'] for w in windows],score_arithmetic=detail,reconstruction_attempts_preserved=deepcopy(attempts),recovery_evidence_inspection=recovery_detail,optimization_rerun=False,optimized_weights_independently_verified=False,recovery_certificates_recomputed=False,source_bytes_authenticated=False,fit_performed=False,account_executed=False,promotion_allowed=False)
