"""Explicit fresh-input computation adapter. No seal, writer, refresh or dispatch.

Only fixed code bytes are read. Caller data/registration refs are structural claims;
future coordinator must authenticate their bytes and supply its observed clock.
"""
from copy import deepcopy
from datetime import date,datetime,timedelta
from hashlib import sha256
from pathlib import Path
import json,math,types
from decimal import Decimal

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED_SHA=sha256(SOURCE.read_bytes()).hexdigest()
COMPUTATION=ROOT/'backtest/ndx_dynamic_shadow_candidate_snapshot.py'
COMPUTATION_SHA='b6ecd412a2e62fb625811101b4076d74150693a0cdc8c2b3fd0fd2d66388f93d'
VERSIONING=ROOT/'data/versioning.py'
VERSIONING_SHA='a71abbf07e8cd1b35f5fa09f9842a15470553fc42e410fe97886c76711fef7df'
CONTRACT=ROOT/'config/ndx_dynamic_shadow_candidate_generator_v1.yaml'
CONTRACT_SHA='46a20fdec256bc0b4f72c8acc64f9ef59b2e80b0e23d6451f60f068b89b059f8'
SCOPE=ROOT/'config/ndx_membership_scope_research_v1.yaml'
SCOPE_SHA='3136387ea83523bd22068c7f70b282dcd44d9195efed985e630bcacd187f5d2a'
INPUT_SCHEMA='PERSISTED_ALL_NDX_CANDIDATE_EXECUTION_INPUT_V2'
OUTPUT_SCHEMA='PERSISTED_ALL_NDX_FRESH_INPUT_SNAPSHOT_COMPUTATION_V2'
ENTRY='backtest.ndx_persisted_fresh_snapshot_executor_v2_research.execute_fresh_input_snapshot'
ROLES=('official_archive','official_receipt','membership','identity_taxonomy','identity_audit','risk_evidence','original8','adjusted_prices','nominal_prices','corporate_actions','target_nav','target_receipt','target_currency','config','generator_contract','membership_scope')
FLAGS=dict.fromkeys(('source_bytes_authenticated','registration_authenticated','clock_authenticity_verified','candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','production_generator_authorized','future_independent_oos','fit_executed','account_executed','seal_executed','snapshot_published','old_generator_called','source_refresh_performed'),False)
UNIVERSE='all_point_in_time_ndx_members'
EVALUATION_TRACKS=('continuous','whole_lot')

def require(ok,message):
 if not ok:raise ValueError(message)
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return sha256(encoded(v)).hexdigest()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def ref(r,s):
 require(type(r)is dict and set(r)=={'path','sha256'},'Exact source reference');p,h=r['path'],r['sha256']
 require(type(p)is str and p and Path(p).is_absolute()and type(h)is str and len(h)==64 and set(h)<=set('0123456789abcdef'),'Absolute path and SHA')
 require(p not in s or s[p]==h,'Conflicting source claim');s[p]=h
def utc(s):
 require(type(s)is str,'Explicit caller research UTC');v=datetime.fromisoformat(s);require(v.tzinfo is not None and v.utcoffset()==timedelta(0),'Aware UTC');return v
def permissions(d):
 for k in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'):require(d[k]is False,'Conditional evidence cannot grant authority')
def claims(d,s):
 require(type(d['source_hashes'])is dict,'Complete source claims')
 for p,h in d['source_hashes'].items():ref(dict(path=p,sha256=h),s)
def associated(s,r):ref(r,{});require(s.get(r['path'])==r['sha256'],'Source association')

def validate_registration(registration):
 """Validate fixed coordinates, not externally authenticate a registration."""
 require(sha256(SOURCE.read_bytes()).hexdigest()==LOADED_SHA,'Loaded executor source drift')
 expected=dict(schema='OBSERVATION_CANDIDATE_EXECUTOR_REGISTRATION_V2',entry_point=ENTRY,operation='FRESH_INPUT_SNAPSHOT_ONLY',executor_reference=dict(path=str(SOURCE),sha256=LOADED_SHA),computation_reference=dict(path=str(COMPUTATION),sha256=COMPUTATION_SHA),versioning_reference=dict(path=str(VERSIONING),sha256=VERSIONING_SHA),generator_contract_reference=dict(path=str(CONTRACT),sha256=CONTRACT_SHA),membership_scope_reference=dict(path=str(SCOPE),sha256=SCOPE_SHA),input_schema=INPUT_SCHEMA,output_schema=OUTPUT_SCHEMA)
 exact(registration,expected,'Only the fixed registered computation entry is supported')
 return expected

def fixed_computation():
 blob=COMPUTATION.read_bytes();require(sha256(blob).hexdigest()==COMPUTATION_SHA,'Frozen computation source');require(sha256(VERSIONING.read_bytes()).hexdigest()==VERSIONING_SHA,'Frozen dependency source')
 module=types.ModuleType('_private_persisted_fresh_snapshot_computation');module.__file__=str(COMPUTATION)
 exec(compile(blob,str(COMPUTATION),'exec'),module.__dict__)
 return module

def calendar_evidence(envelope,observation_refs,observation_id,at,s):
 require(type(envelope)is dict and set(envelope)=={'document','publication','readback','reference','publication_reference','readback_reference','reader_reference'},'Full calendar envelope')
 for k in ('reference','publication_reference','readback_reference','reader_reference'):ref(envelope[k],s)
 d,p,a=(envelope[k]for k in ('document','publication','readback'));e=d['evidence']
 first=d['schema']in ('SOURCE_BOUND_FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_V1','SOURCE_BOUND_FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_V2')
 if first:
  version=d['schema'].rsplit('_',1)[1]
  schemas=tuple(name+'_'+version for name in ('FIRST_PERSISTED_OBSERVATION_CANDIDATE_CALENDAR_SNAPSHOT_EVIDENCE','FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_PUBLICATION','FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_INDEPENDENT_READBACK'))
  for obj in (d,p,e):exact(obj['adapter_schema'],'FIRST_V1_SCOPED_SNAPSHOT_EQUIVALENCE_BRIDGE_V1','First snapshot adapter')
 else:
  exact(d['schema'],'SOURCE_BOUND_PERSISTED_CANDIDATE_CALENDAR_V2','Explicit later V2 calendar')
  schemas=('PERSISTED_OBSERVATION_CANDIDATE_CALENDAR_EVIDENCE_V2','PERSISTED_CANDIDATE_CALENDAR_PUBLICATION_V2','PERSISTED_CANDIDATE_CALENDAR_INDEPENDENT_READBACK_V2')
 exact((e['schema'],p['schema'],a['schema']),schemas,'No calendar version relabel')
 exact(p['status'],'PUBLISHED_CONDITIONAL_EVIDENCE_NOT_SEAL_AUTHORITY','Calendar publication');exact(a['status'],'PASS','Calendar independent readback')
 exact(p['result_reference'],envelope['reference'],'Calendar publication reference');exact(a['result_reference'],envelope['reference'],'Calendar audited result');exact(a['publication_reference'],envelope['publication_reference'],'Calendar audited publication');exact(a['reader_sha256'],envelope['reader_reference']['sha256'],'Calendar reader')
 exact(d['source_hashes'],p['source_hashes'],'Calendar published sources')
 for obj in (d,p,a):permissions(obj);claims(obj,s)
 permissions(e)
 for r in (envelope['reference'],envelope['publication_reference'],envelope['reader_reference']):associated(a['source_hashes'],r)
 for path,h in d['source_hashes'].items():associated(a['source_hashes'],dict(path=path,sha256=h))
 exact(e['selected_observation_id'],observation_id,'Selected observation identity');exact(e['input_references']['observation'],observation_refs,'Original observation refs')
 exact(e['status'],'CONDITIONAL_CALENDAR_PREREQUISITES_ONLY','Blocked calendar cannot compute');require(e['calendar_prerequisites_conditionally_satisfied']is True and e['monthly_coordinate']is True,'Conditional calendar and month coordinate');exact(e['reasons'],[],'No calendar blocker waived')
 require(e['original_seal_status']=='NOT_ATTEMPTED'and e['later_observed_sessions']==[],'No retry/backfill')
 rows=e['known_typed_rows_preserved'];require(type(rows)is list and len(rows)>=66,'Complete typed rows');selected=e['selected_existing_row'];exact(selected,rows[-1],'Latest existing observation')
 require(len(rows)==66 if first else len(rows)>=67,'First versus later calendar boundary')
 previous=''
 for i,row in enumerate(rows):
  require(type(row)is dict and type(row['sequence'])is int and row['sequence']==i+1,'Complete strict row sequence');day(row['session']);require(row['session']>previous,'Strict uncompressed date order');previous=row['session']
  require(row['kind']in ('SEALED_PARENT_OBSERVED_SESSION','MISSED_OBSERVATION','PROSPECTIVE_OBSERVED_SESSION'),'Typed original date role')
 prefix=rows[:65]
 exact(sum(row['kind']=='MISSED_OBSERVATION'for row in prefix),5,'Original prefix five gaps retained')
 exact(sum(row['kind']=='SEALED_PARENT_OBSERVED_SESSION'for row in prefix),60,'Original prefix sixty observed rows retained')
 months={}
 for i,row in enumerate(rows):
  require(row['seal_status']in ('SEALED','NOT_ATTEMPTED','FAILED','UNKNOWN'),'Original seal state retained')
  if row['kind']=='MISSED_OBSERVATION':
   exact(row['seal_status'],'NOT_ATTEMPTED','A gap is not a seal attempt')
   if i>=65:
    pointer=row['evidence_reference'];require(type(pointer)is dict and set(pointer)=={'path','sha256','json_pointer'},'Complete gap evidence pointer')
    token=pointer['json_pointer'];require(type(token)is str and token.startswith('/')and all(part.split('~')[j][:1]in ('0','1')for part in token.split('/')for j in range(1,len(part.split('~')))),'Canonical gap JSON pointer')
    ref({k:pointer[k]for k in ('path','sha256')},s)
  else:months.setdefault(row['session'][:7],row['session'])
 exact(e['first_actual_observed_session_by_month'],months,'All actual observations, including failed and unknown, retain month first')
 exact(months[selected['session'][:7]],selected['session'],'Gaps do not consume month; earlier actual observations do')
 require(selected['kind']=='PROSPECTIVE_OBSERVED_SESSION'and selected['seal_status']=='NOT_ATTEMPTED','Persisted observation only')
 timing=e['timing'];require(utc(timing['publication_check'])<=utc(timing['seal_evaluation_at_utc'])<=at<utc(timing['conservative_deadline_utc']),'Current computation time before deadline')
 require(utc(timing['conservative_close_utc'])<=at,'Not before close')
 return e

def day(value):
 require(type(value)is str,'Canonical date string');d=date.fromisoformat(value);require(d.isoformat()==value and d.weekday()<5,'Canonical ISO weekday');return d
def validate_price_rows(rows,volume):
 previous=''
 for row in rows:
  day(row['Date']);require(row['Date']>previous,'Unique ascending source dates');previous=row['Date']
  require('Close'in row and(not volume or'Volume'in row),'Required numeric fields')
  for key in [k for k in ('Open','High','Low','Close','Volume')if k in row]:
   value=row[key];require(type(value)in (int,float,str),'No bool or nonnumeric financial values')
   try:n=Decimal(str(value))
   except Exception as error:raise ValueError('Invalid numeric field')from error
   require(n.is_finite()and(n>=0 if key=='Volume'else n>0),'Finite positive price/nonnegative Volume')
   require(math.isfinite(float(n))and(key=='Volume'or float(n)>0),'Representable positive finite frozen-float input')

def build_all_ndx_snapshot(module,membership,frames,target,e,original,contract,start,versions,paths):
 # New full-universe logic. Never call the legacy two-industry-track builder.
 pd=module.pd;decision=e['selected_existing_row']['session'];cutoff=utc(e['timing']['conservative_close_utc']);dt=pd.Timestamp(decision);ic=contract['input_contract'];exclusions=[];members=[];seen_tickers=set()
 for row in membership:
  for key in ('ticker','security_id','issuer_id'):
   require(type(row[key])is str and row[key]and row[key].strip()==row[key],'Explicit identity coordinates')
  require(row['ticker']==row['ticker'].upper()and row['ticker']not in seen_tickers,'Unambiguous ticker-to-SID projection');seen_tickers.add(row['ticker'])
  exact(row['selection_date'],decision,'Membership decision date');day(row['membership_effective_from'])
  end=row['membership_effective_to']
  if end is not None:day(end);require(end>row['membership_effective_from'],'Half-open membership interval')
  available=utc(row['evidence_available_timestamp_utc']);ref(row['membership_evidence_reference'],{})
  require(row['membership_status']in ('VERIFIED_POINT_IN_TIME_MEMBER','NONMEMBER','UNKNOWN'),'Explicit membership status')
  reasons=[]
  if row['membership_status']!='VERIFIED_POINT_IN_TIME_MEMBER':reasons.append('MEMBERSHIP_'+row['membership_status'])
  if available>cutoff:reasons.append('MEMBERSHIP_EVIDENCE_AFTER_DECISION_CLOSE')
  if row['membership_effective_from']>decision or(end is not None and decision>=end):reasons.append('MEMBERSHIP_NOT_EFFECTIVE_ON_DECISION')
  if reasons:exclusions.append(dict(security_id=row['security_id'],ticker=row['ticker'],stage='MEMBERSHIP',reasons=reasons,original_row=deepcopy(row)))
  else:members.append(deepcopy(row))
 series={};nominal={};inventories=[];bad={};tickers=sorted(set(original)|{r['ticker']for r in members})
 for ticker in tickers:
  if ticker not in frames['adjusted_prices']or ticker not in frames['nominal_prices']:bad[ticker]=['MISSING_ADJUSTED_OR_NOMINAL_PRICE_FRAME'];continue
  try:
   a,ai=module._close_series(frames['adjusted_prices'][ticker],ticker,dt)
   n,ni=module._nominal_close_and_liquidity(frames['nominal_prices'][ticker],ticker,dt,liquidity_lookback_rows=ic['nominal_price_liquidity_lookback_rows'])
  except ValueError as error:bad[ticker]=['PRICE_REQUIREMENT_NOT_MET',str(error)];continue
  series[ticker]=a;nominal[ticker]=n;inventories.append(dict(ai,**ni))
 good=[];liquidity=[];by_ticker={r['ticker']:r for r in inventories}
 for row in members:
  ticker=row['ticker']
  if ticker in bad:exclusions.append(dict(security_id=row['security_id'],ticker=ticker,stage='PRICE',reasons=bad[ticker],original_row=deepcopy(row)));continue
  if by_ticker[ticker]['median_dollar_volume_usd']<ic['minimum_median_dollar_volume_usd']:
   item=dict(security_id=row['security_id'],ticker=ticker,stage='LIQUIDITY',reasons=['MEDIAN_DOLLAR_VOLUME_BELOW_PREREGISTERED_MINIMUM'],original_row=deepcopy(row));exclusions.append(item);liquidity.append(deepcopy(item));continue
  good.append(row)
 issuer_counts={}
 for row in good:issuer_counts[row['issuer_id']]=issuer_counts.get(row['issuer_id'],0)+1
 coefficients=[1]
 for issuer in sorted(issuer_counts):
  multiplicity=issuer_counts[issuer];updated=[0]*(len(coefficients)+1)
  for k,count in enumerate(coefficients):updated[k]+=count;updated[k+1]+=multiplicity*count
  coefficients=updated
 jobs=[dict(universe=UNIVERSE,holding_count=k,eligible_security_count=len(good),eligible_issuer_count=len(issuer_counts),one_security_per_issuer_required=True,theoretical_security_combinations=coefficients[k],theoretical_issuer_subsets=math.comb(len(issuer_counts),k),search_completion_status='PLANNED_NOT_EXECUTED',job_search_class='EXACT_ENUMERATION'if coefficients[k]<=contract['search_contract']['exact_enumeration_max_feasible_combinations']else'MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND',global_optimality_claimed=False,evaluation_tracks=list(EVALUATION_TRACKS))for k in range(1,len(coefficients))]
 base=dict(universe=UNIVERSE,research_track='portfolio_optimization',industry_filter_applied=False,full_membership_inventory_preserved=deepcopy(membership),membership_input_security_count=len(membership),eligible_securities=pd.DataFrame(good),exclusions=exclusions,liquidity_exclusions=liquidity,price_requirement_failures=bad,risk_validation_blockers=[dict(security_id=r['security_id'],reason='MISSING_RISK_CHAIN')for r in good if not r.get('risk_chain')or r.get('risk_chain')=='unclassified'],job_plan=pd.DataFrame(jobs),universe_denominators=[dict(universe=UNIVERSE,security_count=len(good),issuer_count=len(issuer_counts),planned_k_count=len(jobs),theoretical_security_combination_count=sum(coefficients[1:]),issuer_share_class_multiplicities=issuer_counts)],decision_date=decision,execution_date=None,decision_close_timestamp_utc=e['timing']['conservative_close_utc'],computation_started_at_utc=start,conservative_seal_deadline_utc=e['timing']['conservative_deadline_utc'],source_versions=versions,source_paths=paths,price_input_inventory=pd.DataFrame(inventories),training_adjusted_close=None,training_nominal_close=None,target_012922_aligned=None)
 if not good or any(t in bad for t in original):return dict(base,status='BLOCKED_INPUT_REQUIREMENTS_NO_SNAPSHOT',blocking_reasons=['NO_ELIGIBLE_SECURITIES_OR_REQUIRED_CONTROL_PRICE_MISSING'])
 panel=sorted(set(original)|{r['ticker']for r in good});prices=pd.concat([series[t]for t in panel],axis=1,join='inner').dropna().tail(ic['training_lookback_rows']);nom=pd.concat([nominal[t]for t in panel],axis=1,join='inner').dropna().tail(ic['training_lookback_rows'])
 if len(prices)<ic['minimum_common_adjusted_price_rows']or prices.index.max()!=dt or nom.empty or nom.index.max()!=dt:return dict(base,status='BLOCKED_INPUT_REQUIREMENTS_NO_SNAPSHOT',blocking_reasons=['COMMON_HISTORY_INSUFFICIENT'])
 nav,navdates,asof=module._target_series(target,dt);aligned=nav.reindex(prices.index).ffill();aligned_dates=navdates.reindex(prices.index).ffill()
 if aligned.isna().any():return dict(base,status='BLOCKED_INPUT_REQUIREMENTS_NO_SNAPSHOT',blocking_reasons=['NAV_BACKWARD_ALIGNMENT_INSUFFICIENT'])
 for frame in (prices,nom):frame.insert(0,'Date',frame.index.date.astype(str))
 base.update(training_adjusted_close=prices.reset_index(drop=True),training_nominal_close=nom.reset_index(drop=True),target_012922_aligned=pd.DataFrame(dict(Date=prices.index.date.astype(str),Close=aligned.values,source_date=pd.DatetimeIndex(aligned_dates).date.astype(str))),target_012922_asof_date=asof)
 return dict(base,status='FRESH_INPUT_SNAPSHOT_COMPUTED_NOT_SEALED',blocking_reasons=[])

def table_projection(value,s):
 require(type(value)is dict and set(value)=={'rows','source_reference','projection_sha256','metadata_preserved'},'Complete data projection')
 ref(value['source_reference'],s);rows=value['rows'];require(type(rows)is list and rows and len(rows)<=1000000 and all(type(r)is dict for r in rows),'Bounded complete table rows')
 exact(digest(rows),value['projection_sha256'],'Projection content identity');require(type(value['metadata_preserved'])is dict,'Original source limitations')
 return deepcopy(rows)

def json_safe(value,pd):
 if isinstance(value,pd.DataFrame):return dict(columns=list(value.columns),rows=[{k:json_safe(v,pd)for k,v in row.items()}for row in value.to_dict('records')])
 if type(value)is dict:return {k:json_safe(v,pd)for k,v in value.items()}
 if type(value)is list:return [json_safe(v,pd)for v in value]
 if value is None or type(value)in (str,int,bool):return value
 if type(value)is float:require(math.isfinite(value),'Nonfinite computed result');return value
 if isinstance(value,pd.Timestamp):return value.isoformat()
 # Do not stringify unknown objects or silently convert giant integer tokens.
 raise ValueError('RAW_SERIALIZATION_FAILURE: unsupported result type '+type(value).__name__)

def execute_fresh_input_snapshot(*,execution_input,registration,execution_started_at_utc):
 registered=validate_registration(registration);at=utc(execution_started_at_utc);x=execution_input
 require(type(x)is dict and set(x)=={'schema','observation_id','observation_references','calendar','candidate_data_references','input_versions','input_references','generator_contract_bytes','membership_scope_bytes','expected_membership_security_ids','eligible_membership','adjusted_prices','nominal_prices','target_nav','frozen_original8_tickers','evidence_sidecars'},'Complete execution input schema')
 exact(x['schema'],INPUT_SCHEMA,'Execution input version');s={}
 require(set(x['observation_references'])=={'payload_reference','receipt_reference','audit_reference','reader_reference'},'Observation four roles')
 for r in x['observation_references'].values():ref(r,s)
 require(type(x['observation_id'])is str and len(x['observation_id'])==64 and set(x['observation_id'])<=set('0123456789abcdef'),'Observation digest')
 e=calendar_evidence(x['calendar'],x['observation_references'],x['observation_id'],at,s)
 refs=x['candidate_data_references'];exact(sorted(refs),sorted(ROLES),'All candidate data domains')
 for r in refs.values():ref(r,s)
 exact(x['input_references'],refs,'One-to-one input references');exact(x['input_versions'],{k:r['sha256']for k,r in refs.items()},'One-to-one source versions')
 exact(refs['membership_scope'],registered['membership_scope_reference'],'Explicit all-NDX scope reference');require(type(x['membership_scope_bytes'])is bytes and sha256(x['membership_scope_bytes']).hexdigest()==SCOPE_SHA,'Frozen authorized full-NDX scope bytes')
 exact(refs['generator_contract'],registered['generator_contract_reference'],'Frozen preregistered numeric contract reference')
 require(type(x['generator_contract_bytes'])is bytes and sha256(x['generator_contract_bytes']).hexdigest()==CONTRACT_SHA,'Original contract bytes, no parameter overrides')
 ids=x['expected_membership_security_ids'];require(type(ids)is list and ids and all(type(v)is str and v for v in ids)and len(set(ids))==len(ids),'Explicit full membership projection denominator')
 require(type(x['evidence_sidecars'])is dict and set(x['evidence_sidecars'])==set(ROLES),'Preserve every data-domain evidence object')
 for role,item in x['evidence_sidecars'].items():
  require(type(item)is dict and set(item)=={'reference','original_evidence'},'Evidence wrapper');exact(item['reference'],refs[role],'Evidence source role');require(type(item['original_evidence'])is dict,'Original evidence preserved')
 original=x['frozen_original8_tickers'];require(type(original)is list and len(original)==8 and len(set(original))==8 and all(type(t)is str and t and t==t.strip().upper()for t in original),'Exactly eight original control tickers')
 require(type(x['adjusted_prices'])is dict and type(x['nominal_prices'])is dict,'Explicit ticker frames')
 membership=table_projection(x['eligible_membership'],s);exact(x['eligible_membership']['source_reference'],refs['membership'],'Membership projection ref')
 for row in membership:ref(row['membership_evidence_reference'],s)
 exact(sorted(row['security_id']for row in membership),sorted(ids),'Every declared membership SID present once');require(all('universe_track'not in row for row in membership),'Legacy industry-track rows cannot be relabelled full NDX')
 tickers=set(original)|{row['ticker']for row in membership}
 require(set(x['adjusted_prices'])<=tickers and set(x['nominal_prices'])<=tickers,'No foreign price columns; missing recorded explicitly')
 module=fixed_computation();pd=module.pd;contract=module.yaml.safe_load(x['generator_contract_bytes']);ic=contract['input_contract']
 frames={}
 for role in ('adjusted_prices','nominal_prices'):
  frames[role]={}
  for ticker,projection in x[role].items():
   exact(projection['source_reference'],refs[role],'Explicit price bundle reference');records=table_projection(projection,s);validate_price_rows(records,role=='nominal_prices');frames[role][ticker]=pd.DataFrame(records)
 exact(x['target_nav']['source_reference'],refs['target_nav'],'NAV projection reference');target_records=table_projection(x['target_nav'],s);validate_price_rows(target_records,False);target=pd.DataFrame(target_records)
 versions={**x['input_versions'],'calendar':x['calendar']['reference']['sha256'],'computation':COMPUTATION_SHA,'executor':registered['executor_reference']['sha256']}
 paths={**{k:r['path']for k,r in refs.items()},'calendar':x['calendar']['reference']['path'],'computation':str(COMPUTATION),'executor':str(SOURCE)}
 snapshot=build_all_ndx_snapshot(module,membership,frames,target,e,original,contract,execution_started_at_utc,versions,paths)
 result=json_safe(snapshot,pd);denominators=result['universe_denominators']
 input_identity=deepcopy(x);input_identity['generator_contract_bytes']={'sha256':CONTRACT_SHA,'byte_count':len(x['generator_contract_bytes'])};input_identity['membership_scope_bytes']={'sha256':SCOPE_SHA,'byte_count':len(x['membership_scope_bytes'])}
 for role in ('executor_reference','computation_reference','versioning_reference','generator_contract_reference','membership_scope_reference'):ref(registered[role],s)
 output=dict(schema=OUTPUT_SCHEMA,status=result['status'],operation='FRESH_INPUT_SNAPSHOT_ONLY',observation_id=x['observation_id'],input_content_sha256=digest(input_identity),calendar_evidence_preserved=deepcopy(e),evidence_sidecars_preserved=deepcopy(x['evidence_sidecars']),projection_metadata_preserved=dict(eligible=deepcopy(x['eligible_membership']['metadata_preserved']),adjusted={t:deepcopy(v['metadata_preserved'])for t,v in x['adjusted_prices'].items()},nominal={t:deepcopy(v['metadata_preserved'])for t,v in x['nominal_prices'].items()},nav=deepcopy(x['target_nav']['metadata_preserved'])),registration_claim_preserved=deepcopy(registered),source_hash_claims=s,snapshot=result,universe_denominators=denominators,planned_evaluation_tracks=list(EVALUATION_TRACKS),industry_filter_applied=False,complete_universe_verified=False,original_control_ticker_order_preserved=deepcopy(original),execution_clock_role='CALLER_SUPPLIED_RESEARCH_COORDINATE_NOT_EXECUTOR_ENTRY_ATTESTATION',execution_started_at_utc=execution_started_at_utc,source_authentication_role='FUTURE_COORDINATOR_MUST_BIND_ALL_PROJECTION_AND_EVIDENCE_BYTES',numeric_semantics='FROZEN_PANDAS_FLOAT_SNAPSHOT_NOT_EXACT_DECIMAL_ECONOMICS',**FLAGS)
 encoded(output)
 output['input_references_preserved']=deepcopy(x['input_references']);output['input_versions_preserved']=deepcopy(x['input_versions']);output['calendar_envelope_references']={k:deepcopy(x['calendar'][k])for k in ('reference','publication_reference','readback_reference','reader_reference')}
 require(sha256(SOURCE.read_bytes()).hexdigest()==LOADED_SHA and sha256(COMPUTATION.read_bytes()).hexdigest()==COMPUTATION_SHA and sha256(VERSIONING.read_bytes()).hexdigest()==VERSIONING_SHA,'Post-computation fixed code drift')
 return output
