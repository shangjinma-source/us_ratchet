"""Independent saved account-input verification; never runs producer or engines."""
from pathlib import Path
from copy import deepcopy
from fractions import Fraction
from datetime import date
from urllib.parse import urlsplit
import hashlib,json,math,os,re,shutil,traceback,types
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/multidecision_account_inputs_20261003_v1'
OUTPUT=ROOT/'data/cache/research/multidecision_account_inputs_independent_readback_20261003_v1'
PRODUCER=ROOT/'scripts/ndx_multidecision_account_inputs_20261003.py';PRODUCER_SHA='8773815f275e32653a3104860b53c6b668cb680d96c37a4e746f4fe7058b8618'
INPUTS_SHA='c3311e2e9aea24c96c695e5a860f6ecd784356bbc8995657f1e13061de0ff4b9';PUBLICATION_SHA='64c301cd36c9274f345997a2adb6ba67eb46ce824d8190865b4578441afca940';CORE_SHA='5f2edd4ebc8413d39c320f4f9dca781f30d0205d987d88b37b3d40e692fe9233'
CORE=ROOT/'backtest/ndx_multidecision_account_inputs_research.py'
LINEAGE=ROOT/'backtest/ndx_history_failed_lineage_guard_20261008.py';LINEAGE_SHA='fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
OUTER_ROOT=ROOT/'data/cache/research/outer_lane_cutoff_refit_coordinator_20261008_v2'
OUTER_READER=ROOT/'scripts/ndx_outer_lane_refit_independent_readback_v2_20261008.py'
BOUND={
 'channels':('data/cache/research/bulk_long_window_channels_20261003_v1/channels.json','0f13e2cca5979608d742bfe1bf7a04c46ee9ca4396e5f45f22741420ee540516'),
 'price_publication':('data/cache/research/bulk_long_window_channels_20261003_v1/publication.json','b6c172eb6916361e9a701b8aed31f0caacb7161d6fdf1056d6c6127183343731'),
 'price_readback':('DYNAMIC_BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_20261003.json','3b7b35a3574757c9cdd12c74e701366979e490f5aadebcf0019da97349f4da65'),
 'price_reader':('scripts/ndx_bulk_long_window_channels_independent_review_20261003.py','7227e3705b12782c9514d39df7b23f12b1ae10e8da775f7364796d7c83ddcc99'),
 'outer_result':('data/cache/research/outer_lane_cutoff_refit_coordinator_20261008_v2/result.json','bceefa2a4f725bb2fe6166f9048494f47f7bd364234d1acad018c59a68ed0916'),
 'outer_coordinator':('scripts/ndx_outer_lane_refit_coordinator_v2_20261008.py','813508aca24a013e50805d4c4d0a375bae52ae5903af474ab865c35b3c18a522'),
 'account_contract':('research_contracts/multidecision_stateful_account_inputs_20261003_v1.json','3b657ea472b0098fc4ac22043f9b4ba5406caf363848dbf5c7fe3af626d8517c')}
CUTOFFS=['2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31']
MODES=['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'];LANES=['RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE']
PARAMETERS=dict(initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
ENGINES=[dict(path='backtest/ndx_dynamic_fractional_flow_split_research_v2.py',sha256='40cda887911209e1e2b4dfd401ce702105ba7584506007a2a92cf427667be287',function='simulate_dynamic_fractional_flow_split_research'),dict(path='backtest/ndx_dynamic_frozen_flow_split_research.py',sha256='35c19184f08a0394838171fa61afeb781cd4f314799058063186d9c3d38376a8',function='simulate_dynamic_frozen_flow_split_research')]
FALSE=('source_bytes_authenticated','account_simulation_performed','weights_refitted','inner_window_weights_used','state_reset_between_decisions','cross_track_execution_reused','formal_benchmark_passed','point_in_time_verified','full_ndx_membership_verified','execution_authorized','promotion_allowed','corporate_action_completeness_verified','dividends_modelled','future_independent_oos')
OUTER_FLAGS=('point_in_time_verified','promotion_allowed','execution_authorized','account_executed','scoring_weights_used','automatic_retry_allowed','formal_benchmark_passed','source_bytes_authenticated')
PFLAGS=('source_bytes_authenticated','account_simulation_performed','fit_performed','selection_performed','execution_authorized','promotion_allowed','point_in_time_verified','formal_benchmark_passed','automatic_retry_allowed')

def require(x,m):
 if not x:raise ValueError(m)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,m):require(enc(a)==enc(b),m)
def ref(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def valid(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and Path(r['path']).is_absolute() and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Absolute source reference')
def merge(s,r):
 valid(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Conflicting source');s[r['path']]=r['sha256']
def claims(s,o):
 for p,h in o.get('source_hashes',{}).items():merge(s,dict(path=p,sha256=h))
def decode(b):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate key');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def load(r,s,body=True):
 valid(r);p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed source namespace');b=p.read_bytes();require(sha(b)==r['sha256'],'Source bytes changed');merge(s,r);return decode(b) if body else b
def hashfile(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def lineage_members(sources):
 raw=LINEAGE.read_bytes();require(sha(raw)==LINEAGE_SHA,'Fixed diagnostic helper bytes')
 module=types.ModuleType('_fixed_history_failed_lineage');module.__file__=str(LINEAGE)
 exec(compile(raw,str(LINEAGE),'exec'),module.__dict__)
 return module.diagnostic_members(sources)

def guard(s):
 require(hashfile(SOURCE)==LOADED,'Reader source drift')
 diagnostic=lineage_members(s)
 for p,h in s.items():require((p in diagnostic or not (Path(p).parent/'failure.json').exists()) and hashfile(p)==h,'Source drift or failure')
def flags(o,keys):
 for k in keys:require(o[k] is False,'Authority or false type '+k)
def target(e,coordinate):
 if e is None:return None
 q,a,p,r=e['request'],e['readback'],e['postcheck'],e['raw_result'];refs=e['references']
 exact(q['coordinate'],coordinate,'Outer coordinate');require(a['schema']=='OUTER_LANE_CUTOFF_REFIT_INDEPENDENT_READBACK_V1' and a['reader_sha256']==refs['reader']['sha256'],'Outer independent role')
 for role in ('request','raw_result','postcheck'):exact(a[role+'_reference'],refs[role],'Audited source relation')
 exact(p['request_reference'],refs['request'],'Request relation');exact(p['raw_result_reference'],refs['raw_result'],'Raw relation')
 for obj in (q,a,p,r):flags(obj,('execution_authorized','promotion_allowed','point_in_time_verified','source_bytes_authenticated','optimization_reperformed'))
 require(a['scope']=='SAVED_OUTER_RESULT_ARITHMETIC_AND_SOURCE_BINDING_NOT_REOPTIMIZATION','Independent scope');require(a['numerical_task_id']==q['numerical_task_id'] and a['location_id']==q['location_id'],'Audit identity')
 for role in ('request','raw_result','postcheck','reader'):require(a['source_hashes'].get(refs[role]['path'])==refs[role]['sha256'],'Audit source evidence')
 if 'numerical_reuse_evidence' in e:
  origin=e['numerical_reuse_evidence'];require('numerical_reuse_evidence' not in origin,'No chained reuse');oc=origin['request']['coordinate'];require(oc[0]==coordinate[0] and oc[1] in MODES and oc[2] in LANES,'Same cutoff original registered role');ot=target(origin,oc)
  exact(r,origin['raw_result'],'Original raw unmodified');exact(refs['raw_result'],origin['references']['raw_result'],'Original raw locator');exact(q['numerical_identity'],origin['request']['numerical_identity'],'Reuse numerical identity');exact(q['fit_matrix'],origin['request']['fit_matrix'],'Reuse full matrix')
  require(q['location_id']!=origin['request']['location_id'] and p['current_location_call_invoked'] is False and type(p['current_location_returned_call_count'])is int and p['current_location_returned_call_count']==0,'Reuse is not new numerical execution');exact(p['numerical_reuse_evidence_references'],origin['references'],'Original full receipt links')
  for rr in origin['references'].values():require(a['source_hashes'].get(rr['path'])==rr['sha256'],'Reuse source closure')
  if p['outcome']=='REUSED_AUDITED_NUMERICAL_RISK_FAILURE':require(ot is None and origin['postcheck']['outcome']=='REFIT_RISK_FAILED' and origin['readback']['status']=='PASS_SAVED_RISK_FAILURE' and a['status']=='PASS_SAVED_RISK_FAILURE' and a['prior_eligible'] is False,'Audited original risk-failure reuse')
  else:require(p['outcome']=='REUSED_AUDITED_NUMERICAL_RESULT' and ot is not None,'Successful original reuse')
 else:require(p['outcome'] not in ('REUSED_AUDITED_NUMERICAL_RESULT','REUSED_AUDITED_NUMERICAL_RISK_FAILURE'),'Missing original reuse evidence')
 if a['status']!='PASS' or a['prior_eligible'] is not True:return None
 require(p['outcome'] in ('REFIT_PASSED_PENDING_INDEPENDENT_READBACK','REUSED_AUDITED_NUMERICAL_RESULT') and a['attempt_outcome']==p['outcome'],'Accepted outer outcome')
 body=r['result'];require(body['schema']=='ndx_dynamic_cutoff_refit_research_v2' and body['cutoff']==coordinate[0] and sha(enc(body))==a['raw_result_body_sha256'],'Original audited outer target body');exact(a['targets_preserved'],body['targets'],'Original targets')
 require(set(body['targets'])==set(q['numerical_identity']['selected']),'Full target slots')
 for sid,t in body['targets'].items():
  selected=q['numerical_identity']['selected'][sid];require(set(t)=={'ticker','issuer_id','target_weight'} and type(t['target_weight'])in(int,float) and math.isfinite(t['target_weight']) and t['target_weight']>0,'Positive original outer weights');exact([t['ticker'],t['issuer_id']],[selected['ticker'],selected['issuer_id']],'Selected exact identity')
 require(len({t['issuer_id'] for t in body['targets'].values()})==len(body['targets']),'Unique issuer targets')
 return deepcopy(body['targets'])

def inspect_projection(*,saved,outer_rows,channels,price_audit,price_refs,contract,contract_ref):
 """Independently project saved Close/Open slots and receipts, not account results."""
 require(saved['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_V1','Input schema');flags(saved,FALSE)
 require(saved['price_path_role']=='CONDITIONAL_NOMINAL_PRICE_ONLY_DIVIDENDS_NOT_MODELLED' and saved['full_k_selection_scope']=='ORIGINAL_OUTER_EVIDENCE_REFERENCES_ONLY_NO_DOMAIN_RESTRICTION_ADDED' and saved['full_k_selection_denominator_independently_revalidated'] is False,'No fresh domain authority')
 require(channels['schema']=='BULK_LONG_WINDOW_CONDITIONAL_CHANNELS_V1','Price schema');flags(channels,('point_in_time_verified','execution_authorized','promotion_allowed','complete_corporate_actions_verified'))
 require(price_audit['status']=='PASS' and price_audit['channels_sha256']==price_refs['channels']['sha256'] and price_audit['publication_sha256']==price_refs['publication']['sha256'] and price_audit['reader_sha256']==price_refs['reader']['sha256'],'Actual price audit binding')
 pure_sources={}
 def add(r):
  require(type(r)is dict and set(r)=={'path','sha256'},'Projection source reference');require(r['path'] not in pure_sources or pure_sources[r['path']]==r['sha256'],'Projection source conflict');pure_sources[r['path']]=r['sha256']
 def evidence_sources(e):
  for rr in e['references'].values():add(rr)
  for path,h in e['readback']['source_hashes'].items():add(dict(path=path,sha256=h))
  if 'numerical_reuse_evidence' in e:evidence_sources(e['numerical_reuse_evidence'])
 for rr in price_refs.values():add(rr)
 add(contract_ref)
 for rr in contract['benchmark_references'].values():add(rr)
 for row in outer_rows:
  if row['evidence'] is not None:evidence_sources(row['evidence'])

 exact([saved['coordinate_count'],saved['lane_count'],saved['track_count']],[48,8,16],'All denominators')
 exact(saved['content_sha256'],sha(enc({k:v for k,v in saved.items() if k!='content_sha256'})),'Input digest')
 require(len(outer_rows)==48 and len(saved['rows'])==8,'Full original domain');exact(saved['outer_coordinate_rows_preserved'],outer_rows,'Original missing and complete evidence')
 require(len(channels['rows'])==77 and len({r['coordinate']['security_id'] for r in channels['rows']})==77 and len({r['coordinate']['issuer_id'] for r in channels['rows']})==76,'77 SID 76 issuer')
 for name,count in [('original_provenance_and_missing',101),('preserved_evidence_sidecars',7)]:require(len(channels[name])==count,'Full provenance');exact(saved[name],channels[name],'Preserved provenance')
 exact(saved['full_candidate_inventory_preserved'],[r['coordinate'] for r in channels['rows']],'Full inventory');exact(saved['price_evidence_references'],price_refs,'Price roles')
 require(contract['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_SOURCE_CONTRACT_V1','Account source contract schema');flags(contract,PFLAGS)
 require(set(contract['benchmark_references'])=={'target_012922','original_8_incumbent'},'Two reference roles');require(set(contract['flows_by_lane'])=={m+'|'+l for m in MODES for l in LANES},'All eight flow roles')
 ex=deepcopy(contract['execution_contract']);ex['reference']=contract_ref;exact(saved['execution_contract_preserved'],ex,'Original contract');exact(ex['parameters'],PARAMETERS,'Parameters')
 require(ex['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUT_CONTRACT_V1' and ex['cash_flow_role'] in ('ZERO_FLOW_BASELINE','EXPLICIT_NEW_CASH_RESEARCH'),'Explicit execution cash contract')
 cal=channels['calendar253'];require(len(cal)==253 and cal==sorted(set(cal)),'Original 253 sessions');calendar=[d for d in cal if CUTOFFS[0]<=d<=ex['valuation_end_date']]
 for day in cal:require(type(day)is str and date.fromisoformat(day).isoformat()==day and date.fromisoformat(day).weekday()<5,'Canonical observed weekday')
 require(ex['valuation_end_date'] in cal and ex['valuation_end_date']>CUTOFFS[-1],'Covered explicit end')
 clock=[dict(decision_date=d,execution_date=next((v for v in cal if v>d and v<=ex['valuation_end_date']),None) if d in cal else None) for d in CUTOFFS];exact(saved['execution_clock_from_saved_calendar'],clock,'Observed execution calendar')
 by={r['coordinate']['security_id']:(i,r) for i,r in enumerate(channels['rows'])};audits={r['ticker']:r for r in price_audit['per_channel']};require(len(audits)==77,'Complete quote audits')
 for _,r in by.values():
  ch=r['channel'];a=audits[r['coordinate']['ticker']];exact(a['raw_reference'],ch['raw_reference'],'Raw audit');exact(a['receipt_reference'],ch['receipt_reference'],'Receipt audit');require(a['quote_rows_sha256']==ch['quote_rows_sha256']==sha(enc(ch['quote_rows'])),'Quote source digest')
 ts={};reasons={};prior={}
 for i,row in enumerate(outer_rows):
  coord=[CUTOFFS[i//8],MODES[(i%8)//4],LANES[i%4]];require(type(row['coordinate_index'])is int and row['coordinate_index']==i,'Exact ordinal');exact(row['coordinate'],coord,'Original ordered coordinate');t=target(row['evidence'],coord);ts[i]=t
  reasons[i]='MISSING_OUTER_EVIDENCE:'+row['status'] if row['evidence'] is None else 'OUTER_REFIT_NOT_ACCEPTED:'+row['evidence']['readback']['status']
  if t is not None:
   requested=row['evidence']['request']['numerical_identity']['requested_previous_target_weights'];key=tuple(coord[1:]);
   if i<8:require(requested is None,'Initial prior None')
   else:
    require(key in prior and prior[key][0]==CUTOFFS[i//8-1],'Successful adjacent cutoff prior required');exact(requested,prior[key][1],'Prior strategic weights')
   prior[key]=(coord[0],{s:v['target_weight'] for s,v in t.items()})
 cells=0
 for j,lane in enumerate(saved['rows']):
  flags(lane,FALSE);mi,li=divmod(j,4);exact([lane['fx_mode'],lane['lane']],[MODES[mi],LANES[li]],'Lane order');ids=[d*8+j for d in range(6)];exact(lane['coordinate_indexes'],ids,'All six periods')
  schedules=[];chains={};blocked=[]
  for d,i in enumerate(ids):
   if ts[i] is None:blocked.append(dict(coordinate_index=i,reason=reasons[i]));continue
   if clock[d]['execution_date'] is None:blocked.append(dict(coordinate_index=i,reason='NO_SAVED_NEXT_OBSERVED_EXECUTION_SESSION'));continue
   schedules.append(dict(decision_date=CUTOFFS[d],execution_date=clock[d]['execution_date'],targets=ts[i]));sel=outer_rows[i]['evidence']['request']['numerical_identity']['selected'];chains[CUTOFFS[d]]={s:sel[s]['risk_chain'] for s in ts[i]}
  exact(lane['original_targets_schedule'],schedules,'No refit/normalization or inner weights');exact(lane['outer_evidence_references'],[outer_rows[i]['evidence']['references'] if outer_rows[i]['evidence'] else None for i in ids],'Missing chain preserved')
  sids=sorted({s for row in schedules for s in row['targets']});internal={s:'SID_COLUMN_'+str(k).zfill(4) for k,s in enumerate(sids)};columns=list(internal.values());values={};conversion=[];slots=[];actions=[]
  for sid in sids:
   ri,r=by[sid];c=r['coordinate'];ch=r['channel'];q={v['session']:(qi,v) for qi,v in enumerate(ch['quote_rows'])};require(len(q)==len(ch['quote_rows']),'Unique quote sessions');values[sid]={}
   for row in schedules:
    if sid in row['targets']:exact([row['targets'][sid]['ticker'],row['targets'][sid]['issuer_id']],[c['ticker'],c['issuer_id']],'Target source identity')
   for day in calendar:
    if day not in q:blocked.append(dict(security_id=sid,session=day,reason='MISSING_SAVED_DAILY_NOMINAL_QUOTE'));continue
    qi,v=q[day];pair=[]
    for field in ('nominal_open_exact','nominal_close_exact'):
     raw=v.get(field)
     if raw is None:blocked.append(dict(security_id=sid,session=day,field=field,reason='MISSING_SAVED_NOMINAL_FIELD'));pair.append(None);continue
     require(type(raw)is str,'Saved exact rational');f=Fraction(raw);val=float(f);require(f>0 and math.isfinite(val) and val>0,'Positive finite quote');pair.append(val);cells+=1
     conversion.append(dict(security_id=sid,session=day,field=field,exact=raw,binary64_hex=val.hex(),json_pointer=f'/rows/{ri}/channel/quote_rows/{qi}/{field}'))
    values[sid][day]=pair
   slots.append(dict(security_id=sid,coordinate_preserved=c,channel_pointer=f'/rows/{ri}/channel',raw_reference=ch['raw_reference'],receipt_reference=ch['receipt_reference'],returned_events_preserved=ch['returned_events'],event_policies_preserved=ch['event_policies'],original_identity_assumed_window=r['original_identity_assumed_window']))
   for ev in ch['event_policies']:
    if CUTOFFS[0]<=ev['session']<=ex['valuation_end_date']:
     require(ev['kind']=='ORDINARY_SPLIT' and type(ev['numerator'])is int and type(ev['denominator'])is int and ev['numerator']>0 and ev['denominator']>0,'Split role');receipt=ch['receipt_preserved'];exact([receipt['raw_path'],receipt['raw_sha256'],receipt['ticker']],[ch['raw_reference']['path'],ch['raw_reference']['sha256'],c['ticker']],'Event receipt')
     require(ev['numerator']!=ev['denominator'] and ev['session'] in calendar and not any(a['security_id']==sid and a['session']==ev['session'] for a in actions),'Unique effective split on observed session')
     url=receipt['request_url'];u=urlsplit(url);require(type(url)is str and not any(c.isspace() for c in url) and u.scheme=='https' and u.hostname and not u.username and not u.password,'Original public event URL')
     actions.append(dict(security_id=sid,session=ev['session'],new_shares=ev['numerator'],old_shares=ev['denominator'],source_url=receipt['request_url'],evidence_sha256=ch['raw_reference']['sha256']))
  for slot in slots:
   add(slot['raw_reference']);add(slot['receipt_reference'])
  exact(lane['source_slots'],slots,'All source slots/actions/identity assumptions');exact(lane['exact_quote_conversion_evidence'],conversion,'All exact-to-float evidence')
  aliased=deepcopy(schedules)
  for row in aliased:
   for s,v in row['targets'].items():v['ticker']=internal[s]
  flows=contract['flows_by_lane'][MODES[mi]+'|'+LANES[li]]
  require(type(flows)is list and [f['session'] for f in flows]==sorted(f['session'] for f in flows),'Ordered explicit flows');seen=set()
  if ex['cash_flow_role']=='ZERO_FLOW_BASELINE':require(flows==[],'No hidden flow in zero-flow role')
  for flow in flows:
   require(type(flow)is dict and set(flow)=={'session','amount_usd','currency','timing','source_reference'} and flow['session'] in calendar and flow['currency']=='USD' and flow['timing']=='BEFORE_OPEN','Explicit same-session USD flow')
   amount=flow['amount_usd'];require(type(amount)in(int,float) and math.isfinite(amount) and amount>=0,'Nonnegative finite nonboolean injection');rr=flow['source_reference'];require(type(rr)is dict and set(rr)=={'path','sha256'} and type(rr['path'])is str and rr['path'] and rr['path'].strip()==rr['path'] and type(rr['sha256'])is str and re.fullmatch('[a-f0-9]{64}',rr['sha256']),'Flow receipt reference')
   key=(flow['session'],rr['path'],rr['sha256']);require(key not in seen,'Duplicate source flow');seen.add(key);add(rr)

  state=dict(calendar=calendar,opens=dict(index=calendar,columns=columns,data=[[values[s].get(d,[None,None])[0] for s in sids] for d in calendar]),closes=dict(index=calendar,columns=columns,data=[[values[s].get(d,[None,None])[1] for s in sids] for d in calendar]),schedule=aliased,risk_chains_by_decision=chains,corporate_actions=actions,external_flows=flows,parameters=PARAMETERS,valuation_end_date=ex['valuation_end_date'],initial_state=dict(cash_usd=25000,shares={}),internal_columns_by_security=internal)
  exact(lane['benchmark_references'],contract['benchmark_references'],'Independent benchmark roles');require(lane['benchmark_status']=='SAME_CALENDAR_AND_SAME_FLOW_PATHS_STILL_REQUIRED','Unexecuted benchmarks')
  require(len(lane['tracks'])==2,'Two independent tracks')
  for ti,tr in enumerate(lane['tracks']):
   flags(tr,FALSE);name=['CONTINUOUS','WHOLE_LOT'][ti];require(tr['track']==name and tr['one_full_path_invocation_required'] is True,'One path distinct track');exact(tr['stateful_input'],state,'Independent full state projection');exact(tr['own_initial_state'],state['initial_state'],'No fill/state sharing')
   gaps=deepcopy(blocked)
   if any(f['session']==calendar[0] for f in flows):gaps.append(dict(reason='FLOW_BEFORE_INITIAL_DECISION_CLOSE_REQUIRES_EXPLICIT_INITIAL_CAPITAL_CONTRACT'))
   if ti==0 and any(a['session']==calendar[0] for a in actions):gaps.append(dict(reason='SPLIT_AT_INITIAL_CLOSE_OUTSIDE_FRACTIONAL_OPEN_ACTION_INTERVAL'))
   exact(tr['blocking_reasons'],gaps,'Missing not cash');require(tr['status']==('BLOCKED_ENGINE_OR_SOURCE_INPUT' if gaps else 'ENGINE_INPUTS_PREPARED_NOT_EXECUTED'),'Blocked partition')
   eng=ENGINES[ti];add({k:eng[k] for k in ('path','sha256')});kwargs={k:deepcopy(state[k]) for k in ('closes','opens','schedule','corporate_actions','valuation_end_date','external_flows')};kwargs.update(PARAMETERS if ti else {k:PARAMETERS[k] for k in ('initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps')})
   if ti:kwargs['risk_chains_by_decision']=chains
   binding=tr['engine_binding'];exact(binding['source_reference'],{k:eng[k] for k in ('path','sha256')},'Versioned engine');require(binding['function']==eng['function'],'Fixed function');exact(binding['keyword_arguments'],kwargs,'Exact engine signature and argument projection');exact(binding['dataframe_restoration_required'],['closes','opens'],'Only explicit restoration');require(binding['source_bytes_authenticated'] is False and binding['external_flows_passed_to_explicit_versioned_engine'] is True and binding['no_flow_bitwise_identity_to_legacy_twr_claimed'] is False,'Engine capability scope')
   require(tr['execution_quantity_policy']==('OWN_OPEN_EQUITY_FRACTIONAL_COST_SOLVER' if ti==0 else 'OWN_PRIOR_CLOSE_FROZEN_INTEGER_BASKET_NEXT_OPEN_REJECT_NO_RESIZE'),'Distinct quantity policy')
   require(binding['risk_chain_fields_role']==('OBSERVATION_ONLY_NOT_A_NEW_FRACTIONAL_RISK_GATE' if ti==0 else 'ORIGINAL_WHOLE_LOT_FIVE_RISK_GATE') and binding['action_family']=='FULL_REBALANCE_MAY_SELL_NOT_ADD_ONLY_COMPETITION','Risk/action scope')
 exact(saved['source_hashes'],pure_sources,'Complete projection source claims')
 return dict(status='PASS',coordinate_count=48,lane_count=8,track_count=16,security_count=77,issuer_count=76,provenance_count=101,sidecar_count=7,checked_numeric_cells=cells,producer_called=False,account_engine_called=False,fit_called=False,source_bytes_authenticated=False)

def envelope(rs,s):
 if set(rs)=={'references','numerical_reuse_references'}:
  e=envelope(rs['references'],s);e['numerical_reuse_evidence']=envelope(rs['numerical_reuse_references'],s);return e
 require(set(rs)=={'request','raw_result','postcheck','readback','reader'},'Five external receipt roles');require(Path(rs['reader']['path']).resolve()==OUTER_READER.resolve(),'Fixed outer audit reader');e={'references':deepcopy(rs)}
 for role,r in rs.items():
  value=load(r,s,role!='reader')
  if role!='reader':e[role]=value;claims(s,value)
 return e

def inventory(root,expected):require(not (root/'failure.json').exists() and {str(p) for p in root.rglob('*') if p.is_file()}==set(expected),'Exact saved namespace')
def load_inputs():
 pins=[INPUTS_SHA,PUBLICATION_SHA,PRODUCER_SHA,CORE_SHA]+[h for _,h in BOUND.values()]
 require(all(type(h)is str and re.fullmatch('[a-f0-9]{64}',h) for h in pins),'Future source binding pending before IO')
 sources={str(SOURCE):LOADED};refs={k:ref(ROOT/p,h) for k,(p,h) in BOUND.items()};docs={};expected={str(PRODUCER):PRODUCER_SHA,str(LINEAGE):LINEAGE_SHA}
 for k,r in refs.items():
  value=load(r,expected,k not in ('price_reader','outer_coordinator'))
  if type(value)is dict:docs[k]=value;claims(expected,value)
 load(ref(PRODUCER,PRODUCER_SHA),sources,False);load(ref(CORE,CORE_SHA),expected,False)
 ir=ref(PARENT/'inputs.json',INPUTS_SHA);pr=ref(PARENT/'publication.json',PUBLICATION_SHA);doc=load(ir,sources);pub=load(pr,sources)
 require(doc['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1' and doc['independent_readback_status']=='PENDING','Saved input role');require(pub['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_PUBLICATION_V1' and pub['status']=='PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS','Publication role');exact(pub['inputs_reference'],ir,'External saved input')
 sr=pub['started_reference'];require(Path(sr['path'])==PARENT/'started.json','Fixed started');started=load(sr,sources);require(started['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_STARTED_V1','Started role')
 result=docs['outer_result'];require(result['schema']=='OUTER_LANE_FULL48_COORDINATOR_RESULT_V1' and result['status']=='COMPLETED_REGISTERED_COORDINATES' and result['failure'] is None and len(result['rows'])==48,'Full traversed outer domain')
 flags(result,OUTER_FLAGS)
 outer_started_ref=doc['outer_started_reference'];require(Path(outer_started_ref['path'])==OUTER_ROOT/'started.json','Outer started location');outer_started=load(outer_started_ref,expected);claims(expected,outer_started)
 flags(outer_started,OUTER_FLAGS);require(outer_started['schema']=='OUTER_LANE_FULL48_COORDINATOR_STARTED_V1' and type(outer_started['coordinate_count'])is int and outer_started['coordinate_count']==48,'Started48');require(outer_started['source_hashes'].get(refs['outer_coordinator']['path'])==refs['outer_coordinator']['sha256'],'Coordinator code relation')
 receipt=load(outer_started['receipt_contract_reference'],expected);require(receipt['schema']=='OUTER_LANE_RECEIPT_INTERFACE_CONTRACT_V1','Outer receipt contract role');reader=receipt['reader_reference'];require(Path(reader['path']).resolve()==OUTER_READER.resolve(),'Declared fixed reader');load(reader,expected,False)
 prepared=load(result['prepared_reference'],expected);require(prepared['schema']=='OUTER_LANE_FULL48_INITIAL_PREPARATION_V1' and len(prepared['prepared']['rows'])==48,'Full prepared domain')
 flags(prepared,OUTER_FLAGS)
 known={str(OUTER_ROOT/'result.json'),outer_started_ref['path'],result['prepared_reference']['path']};rows=[]
 for i,row in enumerate(result['rows']):
  require(type(row['coordinate_index'])is int and row['coordinate_index']==i,'Coordinator original order');initial=prepared['prepared']['rows'][i];exact([initial['cutoff'],initial['fx_mode'],initial['lane']],row['coordinate'],'Prepared location');e=None
  if row['outcome'] in ('AUDITED_DIRECT_SUCCESS','AUDITED_NUMERICAL_REUSE','AUDITED_RISK_FAILURE','AUDITED_REUSED_RISK_FAILURE'):
   e=envelope(row['evidence_references'],expected);exact(e['references']['reader'],reader,'Fixed actual audit reader');exact(row['postcheck_reference'],e['references']['postcheck'],'Actual post');exact(row['readback_reference'],e['references']['readback'],'Actual audit');p=OUTER_ROOT/f'coordinates/{i:02d}-accepted.json';b=p.read_bytes();exact(decode(b),row,'Saved accepted row');merge(expected,ref(p,sha(b)));known.add(str(p))
  else:require(row['outcome'] in ('SOURCE_BLOCKED','NO_REFIT_INPUT_OR_ADJACENT_PRIOR'),'No technical failure called complete')
  for field in ('blocked_state_reference','dispatch_started_reference'):
   if field in row:
    m=load(row[field],expected);require(type(m['coordinate_index'])is int and m['coordinate_index']==i,'Coordinate marker');flags(m,OUTER_FLAGS);known.add(row[field]['path'])
    if field=='blocked_state_reference':
     require(m['schema']=='OUTER_LANE_COORDINATE_NOT_DISPATCHED_V1','Blocked role');item=m['prepared_row'];exact([item['cutoff'],item['fx_mode'],item['lane']],row['coordinate'],'Blocked coordinate')
    else:require(m['schema']=='OUTER_LANE_COORDINATE_DISPATCH_STARTED_V1','Dispatch role');exact(m['request']['coordinate'],row['coordinate'],'Dispatch coordinate')
  rows.append(dict(coordinate_index=i,coordinate=deepcopy(row['coordinate']),status=row['outcome'],evidence=e,coordinator_row_preserved=deepcopy(row)))
 for r in docs['account_contract']['benchmark_references'].values():load(r,expected,False)
 for flows in docs['account_contract']['flows_by_lane'].values():
  for event in flows:load(event['source_reference'],expected,False)
 for row in docs['channels']['rows']:
  for role in ('raw_reference','receipt_reference'):load(row['channel'][role],expected,False)
 for engine in ENGINES:load(ref(ROOT/engine['path'],engine['sha256']),expected,False)
 for obj in (doc,pub,started):flags(obj,PFLAGS);exact(obj['input_references'],refs,'Fixed complete input roles');exact(obj['source_hashes'],expected,'Independent complete producer source closure')
 require(doc['outer_started_externally_anchored'] is False and started['outer_started_externally_anchored'] is False,'No inherited external started claim');exact(started['outer_started_reference'],outer_started_ref,'Same observed started bytes')
 for p,h in expected.items():merge(sources,dict(path=p,sha256=h))
 inventory(OUTER_ROOT,known);inventory(PARENT,[str(PARENT/n) for n in ('started.json','inputs.json','publication.json')]);guard(sources)
 args=dict(saved=doc['inputs'],outer_rows=rows,channels=docs['channels'],price_audit=docs['price_readback'],price_refs={k:refs[v] for k,v in dict(channels='channels',publication='price_publication',readback='price_readback',reader='price_reader').items()},contract=docs['account_contract'],contract_ref=refs['account_contract'])
 return dict(args=args,sources=sources,inputs_reference=ir,publication_reference=pr,outer_inventory=sorted(known))

def save(name,value,emergency=False):
 b=enc(value)
 if not emergency:require(shutil.disk_usage(OUTPUT.parent).free>=5*1024**3+len(b),'Resource reserve')
 p=OUTPUT/name
 with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==b,'Readback output drift');return ref(p,sha(b))
def readback(*,execute=False):
 require(execute is True,'Explicit independent readback');c=load_inputs();require(not OUTPUT.exists(),'Create only no retry');OUTPUT.mkdir(parents=True);written=[]
 try:
  written.append(save('started.json',dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_READBACK_STARTED_V1',inputs_reference=c['inputs_reference'],publication_reference=c['publication_reference'],source_hashes=c['sources'])))
  inspection=inspect_projection(**c['args']);guard(c['sources']);inventory(OUTER_ROOT,c['outer_inventory']);inventory(PARENT,[str(PARENT/n) for n in ('started.json','inputs.json','publication.json')])
  report=dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_INDEPENDENT_READBACK_V1',status='PASS',inputs_reference=c['inputs_reference'],publication_reference=c['publication_reference'],reader_sha256=LOADED,source_hashes=c['sources'],inspection=inspection,scope='SAVED_FULL48_TO_16_STATEFUL_INPUT_PROJECTION_NOT_ACCOUNT_EXECUTION',outer_started_external_authority_verified=False,producer_called=False,account_engine_called=False,fit_called=False,point_in_time_verified=False,formal_benchmark_passed=False,execution_authorized=False,promotion_allowed=False)
  r=save('independent_readback.json',report);written.append(r);guard(c['sources']);inventory(OUTER_ROOT,c['outer_inventory']);inventory(PARENT,[str(PARENT/n) for n in ('started.json','inputs.json','publication.json')]);inventory(OUTPUT,[v['path'] for v in written])
  for v in written:require(hashfile(v['path'])==v['sha256'],'Final own bytes')
  return r
 except BaseException as e:
  if not (OUTPUT/'failure.json').exists():save('failure.json',dict(status='FAILED_NO_RETRY',saved_references=written,error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc()),producer_called=False,account_engine_called=False),True)
  raise

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
