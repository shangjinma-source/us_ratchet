"""Readback of saved registered rolling fit evidence; never optimize or fit."""
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
    attempts=saved_fit['reconstruction_attempts'];require(type(attempts) is list,'Recovery evidence list')
    for attempt in attempts:
        require(type(attempt) is dict and {'optimizer_message','reconstruction','independent_certificate','failed_optimizer_vector'}==set(attempt),'Complete saved recovery evidence')
        require(type(attempt['optimizer_message']) is str and attempt['reconstruction']['certified'] is True and attempt['independent_certificate']['certified'] is True,'Saved recovery claimed certificates')
        require(type(attempt['failed_optimizer_vector']) is list and len(attempt['failed_optimizer_vector'])==2*k+1 and all(type(x) is float and math.isfinite(x) for x in attempt['failed_optimizer_vector']),'Saved failed proposal vector')
    if fit['weight_spec']=='equal_weight':require(not attempts,'Equal weight no projection recoveries')
    # All fields retained: this is an evidence consistency check, not recertification.
    expected_keys={'schema','cutoff','securities','weight_spec','windows','reconstruction_attempts','numerical_projection','inner_prior_policy','source_hashes','source_bytes_authenticated','outer_lane_prior_applied','fit_performed','score_computed','point_in_time_verified','account_executed','promotion_allowed'}
    require(set(saved_fit)==expected_keys,'Complete fit return body')
    detail=arithmetic.inspect_fitted_scoring_windows(**score,fitted_windows=windows,saved_score=saved_score)
    exact(saved_score_inspection,detail,'Saved independent score evidence reproduced')
    return dict(schema='REGISTERED_SCORING_RESULT_INSPECTION_V1',status='PASS',job_id=assembled['job_id'],window_count=13,fit_matrix_hashes=[w['fit_data_sha256'] for w in windows],score_arithmetic=detail,reconstruction_attempts_preserved=deepcopy(attempts),optimization_rerun=False,optimized_weights_independently_verified=False,recovery_certificates_recomputed=False,source_bytes_authenticated=False,fit_performed=False,account_executed=False,promotion_allowed=False)
