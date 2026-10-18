"""Pure full-path wiring of audited outer targets; no account or fitter calls.

Both explicitly versioned engines support USD flows and splits, with distinct
fractional Open sizing and frozen whole-lot prior-Close baskets.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib,json,math,re
from urllib.parse import urlsplit
CUTOFFS=('2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31')
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX');LANES=('RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE')
PARAMETERS=dict(initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
FRACTIONAL_ENGINE=dict(path='backtest/ndx_dynamic_fractional_flow_split_research_v2.py',sha256='40cda887911209e1e2b4dfd401ce702105ba7584506007a2a92cf427667be287',function='simulate_dynamic_fractional_flow_split_research')
WHOLE_ENGINE=dict(path='backtest/ndx_dynamic_frozen_flow_split_research.py',sha256='35c19184f08a0394838171fa61afeb781cd4f314799058063186d9c3d38376a8',function='simulate_dynamic_frozen_flow_split_research')
FLAGS=dict.fromkeys(('source_bytes_authenticated','account_simulation_performed','weights_refitted','inner_window_weights_used','state_reset_between_decisions','cross_track_execution_reused','formal_benchmark_passed','point_in_time_verified','full_ndx_membership_verified','execution_authorized','promotion_allowed','corporate_action_completeness_verified','dividends_modelled','future_independent_oos'),False)


def require(x,m):
 if not x:raise ValueError(m)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(x):return hashlib.sha256(enc(x)).hexdigest()
def exact(a,b,m):require(enc(a)==enc(b),m)
def ref(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and r['path'] and r['path'].strip()==r['path'] and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'External immutable reference')
def merge(s,r):
 ref(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def dates(days):
 require(type(days)is list and days and days==sorted(set(days)),'Whole ordered calendar')
 for d in days:require(type(d)is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5,'Canonical observed weekday')


def saved_targets(e,coordinate,sources):
 keys={'request','raw_result','postcheck','readback','references'}
 require(type(e)is dict and set(e) in (keys,keys|{'numerical_reuse_evidence'}),'Complete audited outer envelope')
 refs=e['references'];require(set(refs)=={'request','raw_result','postcheck','readback','reader'},'All outer roles')
 for r in refs.values():merge(sources,r)
 request=e['request'];raw=e['raw_result'];post=e['postcheck'];audit=e['readback']
 if 'numerical_reuse_evidence' in e:
  origin=e['numerical_reuse_evidence'];require(type(origin)is dict and set(origin)==keys,'Reuse must name first direct audited evidence, no alias chains')
  oq=origin['request'];oc=oq['coordinate'];require(len(oc)==3 and oc[0]==coordinate[0] and oc[1] in MODES and oc[2] in LANES,'Original registered same-cutoff reuse location')
  ot,reason=saved_targets(origin,oc,sources)
  reused_risk_failure=post['outcome']=='REUSED_AUDITED_NUMERICAL_RISK_FAILURE'
  if reused_risk_failure:
   require(ot is None and reason=='OUTER_REFIT_NOT_ACCEPTED:PASS_SAVED_RISK_FAILURE' and origin['postcheck']['outcome']=='REFIT_RISK_FAILED' and audit['status']=='PASS_SAVED_RISK_FAILURE' and audit['prior_eligible'] is False,'Preserved audited risk-failure reuse, never a target')
  else:require(reason is None and ot is not None,'Successful original numeric evidence')
  exact(raw,origin['raw_result'],'Original raw reuse body unchanged');exact(refs['raw_result'],origin['references']['raw_result'],'Original raw immutable reference')
  exact(request['numerical_identity'],oq['numerical_identity'],'Complete same numerical input');exact(request['fit_matrix'],oq['fit_matrix'],'Same original source matrix')
  require(request['location_id']!=oq['location_id'] and post['outcome'] in ('REUSED_AUDITED_NUMERICAL_RESULT','REUSED_AUDITED_NUMERICAL_RISK_FAILURE') and post['current_location_call_invoked'] is False and type(post['current_location_returned_call_count'])is int and post['current_location_returned_call_count']==0,'Honest no-call reuse mapping')
  exact(post['numerical_reuse_evidence_references'],origin['references'],'Preserved complete first execution references')
  for r in origin['references'].values():require(audit['source_hashes'].get(r['path'])==r['sha256'],'New audit binds entire reuse origin')
 else:require(post['outcome'] not in ('REUSED_AUDITED_NUMERICAL_RESULT','REUSED_AUDITED_NUMERICAL_RISK_FAILURE'),'Do not strip required reuse evidence chain')
 exact(request['coordinate'],coordinate,'Same FX/lane/decision receipt');require(request['schema']=='OUTER_LANE_CUTOFF_REFIT_REQUEST_V1','Outer request schema')
 require(audit['schema']=='OUTER_LANE_CUTOFF_REFIT_INDEPENDENT_READBACK_V1' and audit['reader_sha256']==refs['reader']['sha256'],'Specific outer independent version')
 require(audit['scope']=='SAVED_OUTER_RESULT_ARITHMETIC_AND_SOURCE_BINDING_NOT_REOPTIMIZATION','Actual independent scope')
 for role in ('request','raw_result','postcheck'):exact(audit[role+'_reference'],refs[role],'Audit evidence link')
 require(audit['numerical_task_id']==request['numerical_task_id'] and audit['location_id']==request['location_id'],'Audited numeric/location identity')
 exact(post['request_reference'],refs['request'],'Current lane request');exact(post['raw_result_reference'],refs['raw_result'],'Original direct/reused raw')
 for obj in (request,raw,post,audit):
  for k in ('execution_authorized','promotion_allowed','point_in_time_verified','source_bytes_authenticated','optimization_reperformed'):require(obj[k] is False,'No receipt authority '+k)
 for p,h in audit['source_hashes'].items():merge(sources,dict(path=p,sha256=h))
 for k in ('request','raw_result','postcheck','reader'):
  r=refs[k];require(audit['source_hashes'].get(r['path'])==r['sha256'],'Audit covers evidence bytes declaration')
 if audit['status']!='PASS' or audit['prior_eligible'] is not True:return None,'OUTER_REFIT_NOT_ACCEPTED:'+audit['status']
 require(post['outcome'] in ('REFIT_PASSED_PENDING_INDEPENDENT_READBACK','REUSED_AUDITED_NUMERICAL_RESULT') and audit['attempt_outcome']==post['outcome'],'Accepted outer outcome')
 body=raw['result'];require(body['schema']=='ndx_dynamic_cutoff_refit_research_v2' and body['cutoff']==coordinate[0],'Original outer target, not inner weights')
 require(audit['raw_result_body_sha256']==digest(body),'Full preserved raw target body');exact(audit['targets_preserved'],body['targets'],'Audited original targets')
 selected=request['numerical_identity']['selected'];require(set(body['targets'])==set(selected),'Complete selected SID targets')
 for sid,t in body['targets'].items():
  require(set(t)=={'ticker','issuer_id','target_weight'} and type(t['target_weight'])in(int,float) and math.isfinite(t['target_weight']) and t['target_weight']>0,'Original positive target coordinates')
  exact([t['ticker'],t['issuer_id']],[selected[sid]['ticker'],selected[sid]['issuer_id']],'Target exact identity')
 require(len({t['issuer_id'] for t in body['targets'].values()})==len(body['targets']),'One SID per issuer each target')
 return deepcopy(body['targets']),None


def prepare_multidecision_account_inputs(*,outer_rows,price_evidence,execution_contract,flows_by_lane,benchmark_references):
 """Each lane is one continuous schedule with independent whole/fractional state."""
 sources={};require(type(outer_rows)is list and len(outer_rows)==48,'Complete48 outer coordinates')
 p=price_evidence['document'];audit=price_evidence['readback'];refs=price_evidence['references']
 require(set(refs)=={'channels','publication','readback','reader'},'Price source roles')
 for r in refs.values():merge(sources,r)
 require(p['schema']=='BULK_LONG_WINDOW_CONDITIONAL_CHANNELS_V1','Saved253 nominal channels schema')
 require(audit['status']=='PASS' and audit['channels_sha256']==refs['channels']['sha256'] and audit['publication_sha256']==refs['publication']['sha256'] and audit['reader_sha256']==refs['reader']['sha256'],'Original independent price audit')
 require(len(p['rows'])==len(audit['per_channel'])==77 and len({r['coordinate']['issuer_id'] for r in p['rows']})==76 and len(p['original_provenance_and_missing'])==101 and len(p['preserved_evidence_sidecars'])==7,'Full77/76/101/7 preserved')
 for k in ('point_in_time_verified','execution_authorized','promotion_allowed','complete_corporate_actions_verified'):require(p[k] is False,'Original conditional price restrictions')
 cal=p['calendar253'];dates(cal);require(len(cal)==253,'Whole source calendar')
 require(execution_contract['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUT_CONTRACT_V1','Explicit new stateful contract')
 merge(sources,execution_contract['reference']);exact(execution_contract['parameters'],PARAMETERS,'Original capital/fee/risk baseline parameters')
 end=execution_contract['valuation_end_date'];require(end in cal and end>CUTOFFS[-1],'Explicit covered end date')
 require(execution_contract['cash_flow_role'] in ('ZERO_FLOW_BASELINE','EXPLICIT_NEW_CASH_RESEARCH'),'Separate new cash role, not old permanent prohibition')
 require(set(benchmark_references)=={'target_012922','original_8_incumbent'},'Both benchmark roles required')
 for r in benchmark_references.values():merge(sources,r)
 keys=[mode+'|'+lane for mode in MODES for lane in LANES];require(set(flows_by_lane)==set(keys),'Each lane explicit flows')
 clock=[]
 for d in CUTOFFS:
  later=[x for x in cal if x>d];clock.append(dict(decision_date=d,execution_date=later[0] if d in cal and later and later[0]<=end else None))
 calendar=[d for d in cal if CUTOFFS[0]<=d<=end]
 by={};a_by={a['ticker']:a for a in audit['per_channel']};require(len(a_by)==77,'Unique audited ticker roles')
 for i,r in enumerate(p['rows']):
  c=r['coordinate'];sid=c['security_id'];require(sid not in by,'Unique source SID');by[sid]=(i,r)
  ch=r['channel'];a=a_by[c['ticker']];require(ch['ticker']==c['ticker'],'Saved source identity')
  exact(a['raw_reference'],ch['raw_reference'],'Audited raw role');exact(a['receipt_reference'],ch['receipt_reference'],'Audited receipt role')
  require(a['quote_rows_sha256']==ch['quote_rows_sha256']==digest(ch['quote_rows']),'Saved nominal rows are audited original bytes projection')
 targets={};reasons={};prior_targets={}
 for i,r in enumerate(outer_rows):
  di,rem=divmod(i,8);mi,li=divmod(rem,4);coordinate=[CUTOFFS[di],MODES[mi],LANES[li]]
  require(type(r['coordinate_index'])is int and r['coordinate_index']==i,'Original48 ordinal');exact(r['coordinate'],coordinate,'Original48 coordinate')
  if r['evidence'] is None:targets[i]=None;reasons[i]='MISSING_OUTER_EVIDENCE:'+r['status'];continue
  target,reason=saved_targets(r['evidence'],coordinate,sources);targets[i]=target;reasons[i]=reason
  if target is None:continue
  request=r['evidence']['request'];pr=request['numerical_identity']['requested_previous_target_weights'];key=tuple(coordinate[1:])
  if di==0:require(pr is None,'Initial strategy prior None')
  else:
   require(key in prior_targets and prior_targets[key][0]==CUTOFFS[di-1],'No skipping missing/failed preceding target')
   exact(pr,prior_targets[key][1],'Actual preceding same-lane strategic target, never other account fills')
  prior_targets[key]=(coordinate[0],{s:v['target_weight'] for s,v in target.items()})
 lanes=[]
 for mi,mode in enumerate(MODES):
  for li,lane in enumerate(LANES):
   key=mode+'|'+lane;indices=[di*8+mi*4+li for di in range(6)];blocked=[];schedule=[];chains={};union=set()
   for di,i in enumerate(indices):
    t=targets[i];ex=clock[di]['execution_date']
    if t is None:blocked.append(dict(coordinate_index=i,reason=reasons[i]));continue
    if ex is None:blocked.append(dict(coordinate_index=i,reason='NO_SAVED_NEXT_OBSERVED_EXECUTION_SESSION'));continue
    union.update(t);schedule.append(dict(decision_date=CUTOFFS[di],execution_date=ex,targets=deepcopy(t)))
    selected=outer_rows[i]['evidence']['request']['numerical_identity']['selected'];chains[CUTOFFS[di]]={s:selected[s]['risk_chain'] for s in t}
   sids=sorted(union);internal={s:'SID_COLUMN_'+str(j).zfill(4) for j,s in enumerate(sids)};columns=[internal[s] for s in sids]
   matrices={'opens':[],'closes':[]};quotes={};actions=[];source_slots=[];conversion=[]
   for sid in sids:
    require(sid in by,'Selected security missing from candidate price inventory');ri,r=by[sid];c=r['coordinate'];ch=r['channel']
    for row in schedule:
     if sid in row['targets']:exact([row['targets'][sid]['ticker'],row['targets'][sid]['issuer_id']],[c['ticker'],c['issuer_id']],'Static saved conditional identity')
    merge(sources,ch['raw_reference']);merge(sources,ch['receipt_reference']);rows=ch['quote_rows'];q={v['session']:(j,v) for j,v in enumerate(rows)};require(len(q)==len(rows),'No duplicate quote date')
    quotes[sid]={}
    for day in calendar:
     if day not in q:blocked.append(dict(security_id=sid,session=day,reason='MISSING_SAVED_DAILY_NOMINAL_QUOTE'));continue
     j,v=q[day];pair=[]
     for field in ('nominal_open_exact','nominal_close_exact'):
      raw=v.get(field)
      if raw is None:blocked.append(dict(security_id=sid,session=day,field=field,reason='MISSING_SAVED_NOMINAL_FIELD'));pair.append(None);continue
      require(type(raw)is str,'Exact saved Fraction string');fraction=Fraction(raw);value=float(fraction);require(fraction>0 and value>0 and math.isfinite(value),'Positive finite nominal quote')
      pair.append(value);conversion.append(dict(security_id=sid,session=day,field=field,exact=raw,binary64_hex=value.hex(),json_pointer=f'/rows/{ri}/channel/quote_rows/{j}/{field}'))
     quotes[sid][day]=pair
    source_slots.append(dict(security_id=sid,coordinate_preserved=deepcopy(c),channel_pointer=f'/rows/{ri}/channel',raw_reference=deepcopy(ch['raw_reference']),receipt_reference=deepcopy(ch['receipt_reference']),returned_events_preserved=deepcopy(ch['returned_events']),event_policies_preserved=deepcopy(ch['event_policies']),original_identity_assumed_window=deepcopy(r['original_identity_assumed_window'])))
    for event in ch['event_policies']:
     if not(CUTOFFS[0]<=event['session']<=end):continue
     require(event['kind']=='ORDINARY_SPLIT' and type(event['numerator'])is int and type(event['denominator'])is int and event['numerator']>0 and event['denominator']>0 and event['numerator']!=event['denominator'],'Explicit ordinary split only')
     require(event['session'] in calendar,'In-period split missing from saved calendar')
     require(not any(a['security_id']==sid and a['session']==event['session'] for a in actions),'Duplicate split evidence/application')
     receipt=ch['receipt_preserved'];require(receipt['raw_path']==ch['raw_reference']['path'] and receipt['raw_sha256']==ch['raw_reference']['sha256'] and receipt['ticker']==c['ticker'],'Actual split/raw receipt binding')
     url=receipt['request_url'];parsed=urlsplit(url);require(not any(c.isspace() for c in url) and parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password,'Original public provider request URL')
     actions.append(dict(security_id=sid,session=event['session'],new_shares=event['numerator'],old_shares=event['denominator'],source_url=url,evidence_sha256=ch['raw_reference']['sha256']))
   for day in calendar:
    matrices['opens'].append([quotes[s].get(day,[None,None])[0] for s in sids]);matrices['closes'].append([quotes[s].get(day,[None,None])[1] for s in sids])
   original_schedule=deepcopy(schedule)
   for row in schedule:
    for sid,target in row['targets'].items():target['ticker']=internal[sid]
   flows=deepcopy(flows_by_lane[key]);require(type(flows)is list,'Explicit lane flow inventory');seen=set()
   require([f['session'] for f in flows]==sorted(f['session'] for f in flows),'Saved ordered flow events')
   for f in flows:
    require(set(f)=={'session','amount_usd','currency','timing','source_reference'} and f['session'] in calendar and f['timing']=='BEFORE_OPEN' and f['currency']=='USD','Explicit observed USD before-Open flow')
    require(type(f['amount_usd'])in(int,float) and math.isfinite(f['amount_usd']) and f['amount_usd']>=0,'Nonnegative explicit new cash amount, not inferred');identity=(f['session'],f['source_reference']['path'],f['source_reference']['sha256']);require(identity not in seen,'Duplicate same source flow event even if amount differs');seen.add(identity);merge(sources,f['source_reference'])
   if execution_contract['cash_flow_role']=='ZERO_FLOW_BASELINE':require(flows==[],'Zero-flow role cannot hide capital injections')
   stateful=dict(calendar=deepcopy(calendar),opens=dict(index=deepcopy(calendar),columns=columns,data=matrices['opens']),closes=dict(index=deepcopy(calendar),columns=columns,data=matrices['closes']),schedule=schedule,risk_chains_by_decision=chains,corporate_actions=actions,external_flows=flows,parameters=deepcopy(PARAMETERS),valuation_end_date=end,initial_state=dict(cash_usd=PARAMETERS['initial_cash_usd'],shares={}),internal_columns_by_security=internal)
   whole=list(blocked);continuous=deepcopy(blocked)
   if any(f['session']==calendar[0] for f in flows):
    whole.append({'reason':'FLOW_BEFORE_INITIAL_DECISION_CLOSE_REQUIRES_EXPLICIT_INITIAL_CAPITAL_CONTRACT'});continuous.append({'reason':'FLOW_BEFORE_INITIAL_DECISION_CLOSE_REQUIRES_EXPLICIT_INITIAL_CAPITAL_CONTRACT'})
   if any(a['session']==calendar[0] for a in actions):continuous.append({'reason':'SPLIT_AT_INITIAL_CLOSE_OUTSIDE_FRACTIONAL_OPEN_ACTION_INTERVAL'})
   def binding(name):
    engine=FRACTIONAL_ENGINE if name=='CONTINUOUS' else WHOLE_ENGINE
    merge(sources,{k:engine[k] for k in ('path','sha256')})
    kwargs=dict(closes=deepcopy(stateful['closes']),opens=deepcopy(stateful['opens']),schedule=deepcopy(schedule),corporate_actions=deepcopy(actions),valuation_end_date=end)
    if name=='CONTINUOUS':
     kwargs.update(external_flows=deepcopy(flows),**{k:PARAMETERS[k] for k in ('initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps')})
    else:kwargs.update(risk_chains_by_decision=deepcopy(chains),external_flows=deepcopy(flows),**deepcopy(PARAMETERS))
    return dict(source_reference={k:engine[k] for k in ('path','sha256')},function=engine['function'],keyword_arguments=kwargs,dataframe_restoration_required=['closes','opens'],source_bytes_authenticated=False,risk_chain_fields_role='OBSERVATION_ONLY_NOT_A_NEW_FRACTIONAL_RISK_GATE' if name=='CONTINUOUS' else 'ORIGINAL_WHOLE_LOT_FIVE_RISK_GATE',action_family='FULL_REBALANCE_MAY_SELL_NOT_ADD_ONLY_COMPETITION',external_flows_passed_to_explicit_versioned_engine=True,no_flow_bitwise_identity_to_legacy_twr_claimed=False)
   def track(name,gaps):return dict(track=name,status='BLOCKED_ENGINE_OR_SOURCE_INPUT' if gaps else 'ENGINE_INPUTS_PREPARED_NOT_EXECUTED',blocking_reasons=gaps,engine_binding=binding(name),one_full_path_invocation_required=True,execution_quantity_policy='OWN_OPEN_EQUITY_FRACTIONAL_COST_SOLVER' if name=='CONTINUOUS' else 'OWN_PRIOR_CLOSE_FROZEN_INTEGER_BASKET_NEXT_OPEN_REJECT_NO_RESIZE',own_initial_state=deepcopy(stateful['initial_state']),stateful_input=deepcopy(stateful),**FLAGS)
   lanes.append(dict(fx_mode=mode,lane=lane,coordinate_indexes=indices,original_targets_schedule=original_schedule,outer_evidence_references=[deepcopy(outer_rows[i]['evidence']['references']) if outer_rows[i]['evidence'] else None for i in indices],source_slots=source_slots,exact_quote_conversion_evidence=conversion,tracks=[track('CONTINUOUS',continuous),track('WHOLE_LOT',whole)],benchmark_references=deepcopy(benchmark_references),benchmark_status='SAME_CALENDAR_AND_SAME_FLOW_PATHS_STILL_REQUIRED',**FLAGS))
 result=dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_V1',lane_count=8,track_count=16,coordinate_count=48,rows=lanes,execution_clock_from_saved_calendar=clock,outer_coordinate_rows_preserved=deepcopy(outer_rows),full_candidate_inventory_preserved=[deepcopy(r['coordinate']) for r in p['rows']],original_provenance_and_missing=deepcopy(p['original_provenance_and_missing']),preserved_evidence_sidecars=deepcopy(p['preserved_evidence_sidecars']),price_evidence_references=deepcopy(refs),execution_contract_preserved=deepcopy(execution_contract),source_hashes=sources,price_path_role='CONDITIONAL_NOMINAL_PRICE_ONLY_DIVIDENDS_NOT_MODELLED',full_k_selection_scope='ORIGINAL_OUTER_EVIDENCE_REFERENCES_ONLY_NO_DOMAIN_RESTRICTION_ADDED',full_k_selection_denominator_independently_revalidated=False,**FLAGS)
 result['content_sha256']=digest(result);return result
