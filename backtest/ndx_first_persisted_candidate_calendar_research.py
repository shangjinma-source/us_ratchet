"""First persisted observation V1 to conditional candidate calendar; pure, never a seal."""
from copy import deepcopy
from datetime import date,datetime,time,timedelta,timezone
from hashlib import sha256
from io import BytesIO
from zoneinfo import ZoneInfo
import base64,json,posixpath
POLICY='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
ENVELOPE_REFS=('reference','publication_reference','readback_reference','reader_reference')
OBS_REFS=('payload_reference','receipt_reference','audit_reference','reader_reference')
FALSE=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','source_evidence_authenticated','observation_receipt_authenticated','clock_authenticity_verified','final_durable_completion_time_verified','seal_attempt_history_authenticated','production_lineage_ready','old_calendar_mutated','old_generator_called','observation_created','seal_event_created','future_independent_oos','exchange_holidays_verified','early_closes_verified')

def require(ok,message):
 if not ok:raise ValueError(message)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(enc(a)==enc(b),message)
def digest(v):return sha256(enc(v)).hexdigest()
def integer(v,n):require(type(v)is int and v==n,'Strict count/sequence')
def ref(r,claims):
 require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and r['path']and r['path'].strip()==r['path'],'External reference')
 h=r['sha256'];require(type(h)is str and len(h)==64 and all(c in '0123456789abcdef'for c in h),'SHA format');require(r['path']not in claims or claims[r['path']]==h,'Source conflict');claims[r['path']]=h

def association(table,r):require(table.get(r['path'])==r['sha256'],'Audit/source reference association')
def claims_of(obj,claims):
 require(type(obj['source_hashes'])is dict,'Source claims mapping')
 for p,h in obj['source_hashes'].items():ref(dict(path=p,sha256=h),claims)
def permissions(obj):
 for key in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'):require(obj[key]is False,'No source authority upgrade')
def utc(s):
 require(type(s)is str,'Explicit UTC');t=datetime.fromisoformat(s.replace('Z','+00:00'));require(t.tzinfo is not None and t.utcoffset()==timedelta(0),'Aware UTC');return t
def day(s):
 require(type(s)is str,'Session string');d=date.fromisoformat(s);require(d.isoformat()==s and d.weekday()<5,'Canonical weekday');return d

BRIDGE_SCHEMA='FIRST_V1_SCOPED_SNAPSHOT_EQUIVALENCE_BRIDGE_V1'
def normalized_path(path):return posixpath.normpath(path.replace('\\','/'))
def is_live_cache(path):
 parts=normalized_path(path).lower().split('/')
 return len(parts)>=3 and parts[-3:-1]==['data','cache'] and parts[-1].endswith('.csv')
def snapshot_bridge(env):
 c,p,a=env['document'],env['publication'],env['readback'];original=c['source_hashes']
 exact(p['source_hashes'],original,'Capture publication original claims');exact(a['capture_original_source_hashes_preserved'],original,'Audit preserved full original capture claims')
 rows=[];roots=set();capture_dir=posixpath.dirname(normalized_path(env['reference']['path']))
 for ticker in ('QQQ','SPY'):
  current=c['input_references']['current_'+ticker];snapshot=c['captured_artifacts'][ticker]
  ref(current,{});ref(snapshot,{});path=normalized_path(current['path']);suffix='/data/cache/'+ticker+'.csv'
  require(path.endswith(suffix),'Exact original current ticker role');roots.add(path[:-len(suffix)])
  exact(normalized_path(snapshot['path']),capture_dir+'/'+ticker+'.csv','Same capture namespace snapshot')
  require(not is_live_cache(snapshot['path']),'Snapshot is not live cache');exact(current['sha256'],snapshot['sha256'],'Original bytes and saved snapshot SHA equality')
  association(original,current);association(a['source_hashes'],snapshot)
  rows.append(dict(ticker=ticker,original_current_reference=deepcopy(current),snapshot_reference=deepcopy(snapshot)))
 integer(len(roots),1);exact(sorted(path for path in original if is_live_cache(path)),sorted(row['original_current_reference']['path']for row in rows),'Only two original live claims')
 require(not any(is_live_cache(path)for path in a['source_hashes']),'Independent audit source map is permanent')
 bridge_paths={row['original_current_reference']['path']for row in rows}
 for path,h in original.items():
  if path not in bridge_paths:association(a['source_hashes'],dict(path=path,sha256=h))
 return dict(schema=BRIDGE_SCHEMA,rows=rows,capture_reference=deepcopy(env['reference']),publication_reference=deepcopy(env['publication_reference']),readback_reference=deepcopy(env['readback_reference']),current_live_cache_reopened=False,full_transitive_source_closure_reverified=False)

def envelope(env,kind,claims):
 schemas={
 'history':('PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2','PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2','PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V2','PUBLISHED_OBSERVATION_HISTORY_NO_SEAL','history_reference'),
 'capture':('FORWARD_SOURCE_CAPTURE_SCOPED_PAYLOAD_V1','FORWARD_SOURCE_CAPTURE_SCOPED_PUBLICATION_V1','SCOPED_FORWARD_CAPTURE_INDEPENDENT_READBACK_V1','PUBLISHED_CURRENT_CACHE_CAPTURE_NOT_CALENDAR_APPEND','capture_reference'),
 'genesis':('SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1','GAP_MONTHLY_POLICY_PUBLICATION_V1','GAP_MONTHLY_POLICY_HISTORY_INPUT_READBACK_V1','PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL','policy_reference')}
 ds,ps,as_,status,key=schemas[kind];d,p,a=env['document'],env['publication'],env['readback']
 for name in ENVELOPE_REFS:ref(env[name],claims)
 exact(d['schema'],ds,'Supported '+kind+' document');exact(p['schema'],ps,'Publication version');exact(a['schema'],as_,'Independent readback version');exact(p['status'],status,'Publication status');exact(a['status'],'PASS','External successful readback')
 exact(p[key],env['reference'],'Published reference');exact(a[key],env['reference'],'Audited reference');exact(a['publication_reference'],env['publication_reference'],'Audited publication');exact(a['reader_sha256'],env['reader_reference']['sha256'],'Audited reader');exact(d['source_hashes'],p['source_hashes'],'Published source map')
 bridge=snapshot_bridge(env)if kind=='capture'else None
 excluded={row['original_current_reference']['path']for row in bridge['rows']}if bridge else set()
 for obj in (d,p,a):
  permissions(obj)
  for path,h in obj['source_hashes'].items():
   if kind=='capture'and obj is not a and path in excluded:continue
   require(not is_live_cache(path),'Live source claim outside explicit capture bridge');ref(dict(path=path,sha256=h),claims)
 for name in ('reference','publication_reference','reader_reference'):association(a['source_hashes'],env[name])
 for path,h in d['source_hashes'].items():
  if path not in excluded:association(a['source_hashes'],dict(path=path,sha256=h))
 return d,p,a

def prepare_first_persisted_candidate_evidence(*,history,genesis,observation,capture,tzif_bytes,seal_evaluation_at_utc):
 """All envelope references are caller claims, never file or clock authentication.

 First history already contains exactly the selected V1 observation. No row is removed/re-appended.
 Separate seal-state event inventory is deliberately not inferred from this input.
 """
 claims={};h,_,ha=envelope(history,'history',claims);c,_,ca=envelope(capture,'capture',claims);g,_,ga=envelope(genesis,'genesis',claims)
 exact(h['genesis_preserved'],genesis,'Exact externally supplied genesis');exact(h['parent_history_reference'],genesis['reference'],'First history parent is original genesis');exact(h['parent_readback_reference'],genesis['readback_reference'],'Genesis readback')
 integer(g['new_observation_count'],0);exact(g['projection_inputs']['new_prospective_observations'],[],'No invented genesis observation');exact(g['policy_id'],POLICY,'Genesis policy')
 exact(h['policy_id'],POLICY,'User first-observed policy');rows=h['known_typed_rows'];require(type(rows)is list and len(rows)==66,'Full compact history');months={};previous='';pointers=set()
 for i,row in enumerate(rows):
  exact(sorted(row),sorted(('sequence','session','kind','evidence_reference','seal_status')),'Typed fields');integer(row['sequence'],i+1);d=row['session'];day(d);require(d>previous,'Ordered unique complete history');previous=d
  require(row['kind']in ('SEALED_PARENT_OBSERVED_SESSION','MISSED_OBSERVATION','PROSPECTIVE_OBSERVED_SESSION'),'Typed observation');require(row['seal_status']in ('NOT_ATTEMPTED','UNKNOWN','FAILED','SEALED'),'Original seal status')
  pointer=row['evidence_reference'];require(type(pointer)is dict and set(pointer)=={'path','sha256','json_pointer'}and type(pointer['json_pointer'])is str and pointer['json_pointer'].startswith('/'),'Evidence pointer');ref({k:pointer[k]for k in ('path','sha256')},claims);identity=enc(pointer);require(identity not in pointers,'Unique evidence pointer');pointers.add(identity)
  if row['kind']=='MISSED_OBSERVATION':exact(row['seal_status'],'NOT_ATTEMPTED','Gap not sealed')
  else:months.setdefault(d[:7],d)
 genesis_rows=g['projection_inputs']['known_rows'];integer(len(genesis_rows),65);exact(rows[:65],genesis_rows,'All genesis rows preserved');integer(sum(r['kind']=='MISSED_OBSERVATION'for r in genesis_rows),5);integer(sum(r['kind']=='SEALED_PARENT_OBSERVED_SESSION'for r in genesis_rows),60)
 exact(ga['known_typed_rows_preserved'],genesis_rows,'Genesis readback prefix');exact(ga['counts'],dict(known_rows=65,observed_rows=60,gap_rows=5,new_observation_count=0),'Genesis counts')
 entries=h['observations'];attempts=h['parent_attempt_inventory'];integer(len(entries),len(rows)-65);integer(len(attempts),len(entries));integer(h['observation_count'],len(entries));ids=set()
 for j,(entry,attempt)in enumerate(zip(entries,attempts)):
  exact(entry['schema'],'COMPACT_OBSERVATION_REFERENCE_ENTRY_V1','Compact reference schema');require(entry['original_payload_embedded']is False,'No embedded replacement payload');integer(entry['sequence'],66+j);exact(entry['session'],rows[65+j]['session'],'Existing observed date');exact(rows[65+j]['kind'],'PROSPECTIVE_OBSERVED_SESSION','Existing observed kind');exact(entry['observation_id'],digest(entry['observation_identity']),'Observation identity digest');require(entry['observation_id']not in ids,'Unique observation');ids.add(entry['observation_id'])
  for k in OBS_REFS:ref(entry[k],claims)
  exact(rows[65+j]['evidence_reference'],dict(entry['payload_reference'],json_pointer='/observation_identity'),'Existing payload pointer')
  exact(attempt,dict(observation_id=entry['observation_id'],session=entry['session'],status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',payload_reference=entry['payload_reference'],receipt_reference=entry['receipt_reference'],independent_readback_reference=entry['audit_reference']),'Every existing observation has resolved receipt')
 exact(h['first_actual_observed_session_by_month'],months,'Month coordinate uses all observed states');exact(h['last_accounted_session'],rows[-1]['session'],'Complete history cursor');integer(ha['counts']['typed_row_count'],len(rows));integer(ha['counts']['observation_count'],len(entries));integer(ha['counts']['new_observation_count'],1);exact(ha['counts']['first_actual_observed_session_by_month'],months,'Audited month coordinates');exact(h['baseline_references'],entries[-1]['captured_baseline_references'],'Latest history baseline');exact(h['source_reference_claims'],h['source_hashes'],'Compact source declarations agree')
 p,receipt,audit=observation['payload'],observation['receipt'],observation['audit']
 for k in OBS_REFS:ref(observation[k],claims)
 require('writer_adapter_schema'not in p and 'writer_adapter_schema'not in receipt,'V1 cannot impersonate V2 adapter')
 exact(p['schema'],'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1','Original payload schema, not research assertion');exact(receipt['schema'],'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1','Real durable receipt');exact(receipt['status'],'PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY','Receipt status');exact(audit['schema'],'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1','Only explicit first V1 observation reader supported');exact(audit['status'],'PASS','Actual observation independent audit')
 for obj in (p,receipt,audit):
  permissions(obj);claims_of(obj,claims);require(obj['live_mutation_allowed']is False,'No live authority')
 exact(p['source_hashes'],receipt['source_hashes'],'Original writer payload/receipt source maps')
 for path,hsh in p['source_hashes'].items():association(audit['source_hashes'],dict(path=path,sha256=hsh))
 require(audit['writer_called']is False and audit['old_audit_repeated']is False,'Independent observation readback')
 exact(receipt['payload_reference'],observation['payload_reference'],'Receipt payload');exact(audit['payload_reference'],observation['payload_reference'],'Audit payload');exact(audit['receipt_reference'],observation['receipt_reference'],'Audit receipt');exact(audit['reader_sha256'],observation['reader_reference']['sha256'],'Audit reader')
 for k in ('payload_reference','receipt_reference','reader_reference'):association(audit['source_hashes'],observation[k])
 matches=[(j,e)for j,e in enumerate(entries)if e['observation_id']==p['observation_id']];integer(len(matches),1);j,entry=matches[0];position=65+j;selected=rows[position];session=p['session'];day(session);require(session>='2026-10-01','No preactivation backfill')
 for k in OBS_REFS:
  exact(entry[k],observation[k],'Selected compact reference, not arbitrary PASS');association(h['source_hashes'],observation[k]);association(ha['source_hashes'],observation[k])
 exact(entry['observation_identity'],p['observation_identity'],'Saved identity');exact(receipt['observation_id'],entry['observation_id'],'Receipt ID');exact(entry['session'],session,'Selected existing session');integer(p['sequence'],position+1);exact(p['kind'],'PROSPECTIVE_OBSERVED_SESSION','Persisted observed type');exact(p['initial_seal_status'],'NOT_ATTEMPTED','Payload did not seal')
 exact(p['known_typed_rows_preserved'],rows[:position],'Entire prior prefix unchanged');exact(p['parent_attempt_inventory_preserved'],attempts[:j],'Entire prior attempt inventory');integer(audit['counts']['parent_observed_count'],position-5);integer(audit['counts']['parent_gap_count'],5);integer(audit['counts']['new_observation_count'],1)
 for role,obj in (('payload',p),('receipt',receipt),('audit',audit)):
  exact(entry['original_source_hash_claims'][role],obj['source_hashes'],'Compact original source claims')
  for path,hsh in obj['source_hashes'].items():
   association(h['source_hashes'],dict(path=path,sha256=hsh));association(ha['source_hashes'],dict(path=path,sha256=hsh))
 for key in ('initial_seal_status','month_first_actual_observation','first_actual_observed_session_of_month'):exact(entry[key],p[key],'Compact payload field '+key)
 exact(entry['timing_classification'],receipt['timing_classification'],'Compact receipt timing');exact(entry['payload_timing_classification'],p['timing_classification'],'Compact payload timing')
 plan=c['plan'];inner=plan['capture_plan'];permissions(plan)
 exact(plan['schema'],'FORWARD_SOURCE_CAPTURE_SCOPED_PLAN_V1','Explicit scoped capture');exact(inner['schema'],'FORWARD_SOURCE_CAPTURE_PLANNING_V1','Original scoped planning')
 exact(inner['accounted_prefix_dates'],[r['session']for r in rows[:65]],'Complete captured genesis prefix');exact(inner['status'],'NEW_SOURCE_DATES_REQUIRE_REVIEW','Scoped status is not observation authority');exact(inner['new_source_dates'],[session],'Exactly one new date');exact(inner['revisions'],[],'No silently revised baseline');exact(inner['excluded_unfinished_source_dates'],[],'No unfinished extra rows');exact(inner['unmatched_new_source_dates_by_ticker'],dict(QQQ=[],SPY=[]),'Symmetrical new dates')
 require(inner['source_suffix_asymmetry_blocks_timeliness_candidate']is False,'No asymmetric candidate')
 caprefs={k:capture[k]for k in ENVELOPE_REFS}
 original_refs=dict(parent=genesis['reference'],parent_publication=genesis['publication_reference'],parent_readback=genesis['readback_reference'],capture=capture['reference'],capture_publication=capture['publication_reference'])
 exact(p['input_references'],original_refs,'Original V1 five roles');require('input_references'not in receipt and 'parent_history_reference'not in audit,'Do not invent V2 receipt/audit fields')
 for r in original_refs.values():association(p['source_hashes'],r);association(receipt['source_hashes'],r);association(audit['source_hashes'],r)
 exact(p['observation_identity'],dict(parent_reference=genesis['reference'],capture_reference=capture['reference'],session=session),'First parent identity');exact(p['parent_readback_reference'],genesis['readback_reference'],'Original genesis readback')
 exact(c['input_references']['frontier'],g['frontier_reference'],'Same original frontier')
 require(ca['current_live_cache_reopened']is False and ca['producer_called']is False and ca['old_audit_called']is False,'Independent immutable scoped capture role')
 exact(ca['new_source_dates'],[session],'Readback new date');integer(ca['revision_count'],0);integer(ca['accounted_prefix_count'],65)
 baseline={t:c['input_references']['baseline_'+t]for t in ('QQQ','SPY')}
 exact(baseline,genesis['baseline_references'],'Genesis baseline refs');exact(baseline,ga['baseline_references'],'Genesis audited baseline refs')
 exact(entry['captured_baseline_references'],{t:c['captured_artifacts'][t]for t in ('QQQ','SPY')},'Compact captured baseline');exact(entry['previous_baseline_references'],baseline,'Compact previous baseline')
 for ticker in ('QQQ','SPY'):
  current=c['captured_artifacts'][ticker];base=baseline[ticker];saved=p['full_original_sources_preserved'][ticker]
  exact(saved['sources']['reference'],current,'Original snapshot reference');exact(saved['baseline_sources']['reference'],base,'Original baseline reference');ref(current,claims);ref(base,claims);association(ca['source_hashes'],current)
  for source in (current,base):association(p['source_hashes'],source);association(audit['source_hashes'],source)
  current_rows=saved['sources']['rows'];old_rows=saved['baseline_sources']['rows'];require(type(current_rows)is list and type(old_rows)is list and current_rows and len(current_rows)==len(old_rows)+1,'Stored single-row append');exact(current_rows[:-1],old_rows,'All original price rows retained, not decoded again');exact([r['Date']for r in old_rows if r['Date']>=rows[0]['session']],[r['session']for r in rows[:position]],'Full baseline dates');exact(current_rows[-1],p['selected_original_rows'][ticker],'Selected saved source row');exact(current_rows[-1]['Date'],session,'Selected row date');exact(p['source_row_locations'][ticker],dict(original_data_row_index=len(current_rows)-1,reference=current),'Original source pointer')
 tzref=c['captured_artifacts']['tzif'];ref(tzref,claims);association(ca['source_hashes'],tzref);exact(p['tzif_reference'],tzref,'Same TZif');require(type(tzif_bytes)is bytes and 0<len(tzif_bytes)<=100000 and sha256(tzif_bytes).hexdigest()==tzref['sha256'],'Consumed exact TZif');exact(p['tzif_bytes_base64'],base64.b64encode(tzif_bytes).decode(),'Saved TZif bytes');zone=ZoneInfo.from_file(BytesIO(tzif_bytes),key='America/New_York')
 close=datetime.combine(day(session),time(16),zone).astimezone(timezone.utc);following=day(session)+timedelta(days=1)
 while following.weekday()>=5:following+=timedelta(days=1)
 deadline=datetime.combine(following,time(9,30),zone).astimezone(timezone.utc)
 exact(p['capture_started_at_utc'],c['capture_started_at_utc'],'Capture start');exact(p['capture_completed_at_utc'],c['observed_at_utc'],'Capture end');exact(ca['capture_started_at_utc'],c['capture_started_at_utc'],'Audited start');exact(ca['observed_at_utc'],c['observed_at_utc'],'Audited end');exact(p['conservative_close_utc'],close.isoformat(),'Bound regular close');exact(p['conservative_deadline_utc'],deadline.isoformat(),'Bound conservative deadline')
 cs,ce,ws,we,pc=map(utc,(p['capture_started_at_utc'],p['capture_completed_at_utc'],p['writer_started_at_utc'],p['writer_completed_at_utc'],receipt['publication_check_at_utc']));require(close<=cs<=ce<=ws<=we<=pc,'Non-backdated saved receipt interval');exact(p['timing_classification'],'LATE_OBSERVATION'if we>=deadline else'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW','Payload timing classification');exact(receipt['timing_classification'],'LATE_OBSERVATION'if pc>=deadline else p['timing_classification'],'Receipt timing classification');exact(audit['counts']['timing_classification'],receipt['timing_classification'],'Audited receipt timing');exact(receipt['publication_time_role'],'AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE','Not final durable clock')
 exact(ca['status_observed'],inner['status'],'Original readback capture status')
 expected_class='TIMELINESS_REVIEW_CANDIDATE_ONLY'if ce<deadline else'MISSED_SEAL_DEADLINE'
 require(type(inner['classifications'])is list and len(inner['classifications'])==1,'Single original classification')
 classification=inner['classifications'][0]
 for key,value in dict(session=session,classification=expected_class,capture_started_at_utc=c['capture_started_at_utc'],observed_at_utc=c['observed_at_utc'],conservative_close_utc=close.isoformat(),conservative_next_weekday_open_utc=deadline.isoformat()).items():exact(classification[key],value,'Original capture classification '+key)
 exact(inner['timeliness_candidate'],classification if ce<deadline else None,'Capture candidate remains provisional');exact(ca['candidate'],inner['timeliness_candidate'],'Readback provisional candidate')
 monthly=months[session[:7]]==session
 for obj in (p,receipt):exact(obj['month_first_actual_observation'],monthly,'Saved actual month coordinate')
 exact(p['first_actual_observed_session_of_month'],months[session[:7]],'First observed, not first successful');exact(audit['counts']['month_first_actual_observation'],monthly,'Audited coordinate')
 seal=None if seal_evaluation_at_utc is None else utc(seal_evaluation_at_utc);reasons=[]
 if not monthly:reasons.append('NOT_FIRST_ACTUAL_OBSERVATION_OF_MONTH')
 if position!=len(rows)-1:reasons.append('LATER_OBSERVED_SESSION_NO_BACKFILL')
 if selected['seal_status']!='NOT_ATTEMPTED':reasons.append('PRIOR_SEAL_STATE_DOES_NOT_AUTHORIZE_NEW_ATTEMPT')
 if not cs<=ce<deadline:reasons.append('CAPTURE_OUTSIDE_CONSERVATIVE_WINDOW')
 if pc>=deadline:reasons.append('PERSISTED_OBSERVATION_PUBLICATION_CHECK_LATE')
 if seal is None:reasons.append('SEAL_CLOCK_NOT_SUPPLIED')
 elif not pc<=seal<deadline:reasons.append('SEAL_EVALUATION_OUTSIDE_CONSERVATIVE_WINDOW')
 require(not any(is_live_cache(path)for path in claims),'Only permanent cumulative sources');bridge=snapshot_bridge(capture)
 satisfied=not reasons
 return dict(schema='FIRST_PERSISTED_OBSERVATION_CANDIDATE_CALENDAR_SNAPSHOT_EVIDENCE_V1',adapter_schema=BRIDGE_SCHEMA,original_source_claims_preserved=deepcopy(c['source_hashes']),snapshot_equivalence_bridge=bridge,current_live_cache_reopened=False,full_transitive_source_closure_reverified=False,policy_id=POLICY,status='CONDITIONAL_CALENDAR_PREREQUISITES_ONLY'if satisfied else'BLOCKED',calendar_prerequisites_conditionally_satisfied=satisfied,reasons=reasons,lineage_blockers=['SEAL_STATUS_EVENT_HISTORY_NOT_BOUND','NEW_CANDIDATE_GENERATOR_AND_COHORT_CONSUMER_NOT_BOUND'],known_typed_rows_preserved=deepcopy(rows),parent_attempt_inventory_preserved=deepcopy(attempts),selected_observation_id=p['observation_id'],selected_existing_row=deepcopy(selected),selected_compact_entry=deepcopy(entry),first_actual_observed_session_by_month=deepcopy(months),monthly_coordinate=monthly,original_seal_status=selected['seal_status'],later_observed_sessions=[r['session']for r in rows[position+1:]if r['kind']!='MISSED_OBSERVATION'],input_references=dict(genesis={k:deepcopy(genesis[k])for k in ENVELOPE_REFS},history={k:deepcopy(history[k])for k in ENVELOPE_REFS},observation={k:deepcopy(observation[k])for k in OBS_REFS},capture=deepcopy(caprefs),tzif=deepcopy(tzref)),timing=dict(capture_start=p['capture_started_at_utc'],capture_end=p['capture_completed_at_utc'],writer_start=p['writer_started_at_utc'],writer_end=p['writer_completed_at_utc'],publication_check=receipt['publication_check_at_utc'],publication_time_role=receipt['publication_time_role'],seal_evaluation_at_utc=seal_evaluation_at_utc,conservative_close_utc=close.isoformat(),conservative_deadline_utc=deadline.isoformat()),source_hash_claims=claims,scope='STRUCTURAL_REFERENCE_AND_CONDITIONAL_CLOCK_CHECKS_NOT_BYTE_AUTHENTICATION_OR_SEAL_AUTHORITY',**dict.fromkeys(FALSE,False))
