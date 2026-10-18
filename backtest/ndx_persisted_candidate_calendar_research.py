"""Persisted observation V2 to conditional candidate calendar; pure, never a seal."""
from copy import deepcopy
from datetime import date,datetime,time,timedelta,timezone
from hashlib import sha256
from io import BytesIO
from zoneinfo import ZoneInfo
import base64,json
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

def envelope(env,kind,claims):
 schemas={
 'history':('PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2','PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2','PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V2','PUBLISHED_OBSERVATION_HISTORY_NO_SEAL','history_reference'),
 'capture':('SOURCE_BOUND_VARIABLE_PREFIX_CAPTURE_V1','VARIABLE_PREFIX_CAPTURE_PUBLICATION_V1','VARIABLE_PREFIX_CAPTURE_INDEPENDENT_READBACK_V1','PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION','capture_reference')}
 ds,ps,as_,status,key=schemas[kind];d,p,a=env['document'],env['publication'],env['readback']
 for name in ENVELOPE_REFS:ref(env[name],claims)
 exact(d['schema'],ds,'Supported '+kind+' document');exact(p['schema'],ps,'Publication version');exact(a['schema'],as_,'Independent readback version');exact(p['status'],status,'Publication status');exact(a['status'],'PASS','External successful readback')
 exact(p[key],env['reference'],'Published reference');exact(a[key],env['reference'],'Audited reference');exact(a['publication_reference'],env['publication_reference'],'Audited publication');exact(a['reader_sha256'],env['reader_reference']['sha256'],'Audited reader');exact(d['source_hashes'],p['source_hashes'],'Published source map')
 for obj in (d,p,a):permissions(obj);claims_of(obj,claims)
 for name in ('reference','publication_reference','reader_reference'):association(a['source_hashes'],env[name])
 for path,h in d['source_hashes'].items():association(a['source_hashes'],dict(path=path,sha256=h))
 return d,p,a

def prepare_persisted_candidate_evidence(*,history,observation,capture,tzif_bytes,seal_evaluation_at_utc):
 """All envelope references are caller claims, never file or clock authentication.

 History already contains the selected observation. No row is removed/re-appended.
 Separate seal-state event inventory is deliberately not inferred from this input.
 """
 claims={};h,_,ha=envelope(history,'history',claims);c,_,ca=envelope(capture,'capture',claims)
 exact(h['policy_id'],POLICY,'User first-observed policy');rows=h['known_typed_rows'];require(type(rows)is list and 66<=len(rows)<20000,'Full compact history');months={};previous='';pointers=set()
 for i,row in enumerate(rows):
  exact(sorted(row),sorted(('sequence','session','kind','evidence_reference','seal_status')),'Typed fields');integer(row['sequence'],i+1);d=row['session'];day(d);require(d>previous,'Ordered unique complete history');previous=d
  require(row['kind']in ('SEALED_PARENT_OBSERVED_SESSION','MISSED_OBSERVATION','PROSPECTIVE_OBSERVED_SESSION'),'Typed observation');require(row['seal_status']in ('NOT_ATTEMPTED','UNKNOWN','FAILED','SEALED'),'Original seal status')
  pointer=row['evidence_reference'];require(type(pointer)is dict and set(pointer)=={'path','sha256','json_pointer'}and type(pointer['json_pointer'])is str and pointer['json_pointer'].startswith('/'),'Evidence pointer');ref({k:pointer[k]for k in ('path','sha256')},claims);identity=enc(pointer);require(identity not in pointers,'Unique evidence pointer');pointers.add(identity)
  if row['kind']=='MISSED_OBSERVATION':exact(row['seal_status'],'NOT_ATTEMPTED','Gap not sealed')
  else:months.setdefault(d[:7],d)
 genesis=h['genesis_preserved']['document']['projection_inputs']['known_rows'];integer(len(genesis),65);exact(rows[:65],genesis,'All genesis rows preserved');integer(sum(r['kind']=='MISSED_OBSERVATION'for r in genesis),5);integer(sum(r['kind']=='SEALED_PARENT_OBSERVED_SESSION'for r in genesis),60)
 entries=h['observations'];attempts=h['parent_attempt_inventory'];integer(len(entries),len(rows)-65);integer(len(attempts),len(entries));integer(h['observation_count'],len(entries));ids=set()
 for j,(entry,attempt)in enumerate(zip(entries,attempts)):
  exact(entry['schema'],'COMPACT_OBSERVATION_REFERENCE_ENTRY_V1','Compact reference schema');require(entry['original_payload_embedded']is False,'No embedded replacement payload');integer(entry['sequence'],66+j);exact(entry['session'],rows[65+j]['session'],'Existing observed date');exact(rows[65+j]['kind'],'PROSPECTIVE_OBSERVED_SESSION','Existing observed kind');exact(entry['observation_id'],digest(entry['observation_identity']),'Observation identity digest');require(entry['observation_id']not in ids,'Unique observation');ids.add(entry['observation_id'])
  for k in OBS_REFS:ref(entry[k],claims)
  exact(rows[65+j]['evidence_reference'],dict(entry['payload_reference'],json_pointer='/observation_identity'),'Existing payload pointer')
  exact(attempt,dict(observation_id=entry['observation_id'],session=entry['session'],status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',payload_reference=entry['payload_reference'],receipt_reference=entry['receipt_reference'],independent_readback_reference=entry['audit_reference']),'Every existing observation has resolved receipt')
 exact(h['first_actual_observed_session_by_month'],months,'Month coordinate uses all observed states');exact(h['last_accounted_session'],rows[-1]['session'],'Complete history cursor');integer(ha['counts']['typed_row_count'],len(rows));integer(ha['counts']['observation_count'],len(entries));integer(ha['counts']['new_observation_count'],1);exact(ha['counts']['first_actual_observed_session_by_month'],months,'Audited month coordinates');exact(h['baseline_references'],entries[-1]['captured_baseline_references'],'Latest history baseline')
 p,receipt,audit=observation['payload'],observation['receipt'],observation['audit']
 for k in OBS_REFS:ref(observation[k],claims)
 exact(p['writer_adapter_schema'],'VARIABLE_PREFIX_OBSERVATION_WRITER_V2','Explicit V2 payload adapter');exact(receipt['writer_adapter_schema'],'VARIABLE_PREFIX_OBSERVATION_WRITER_V2','Explicit V2 receipt adapter')
 exact(p['schema'],'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1','Original payload schema, not research assertion');exact(receipt['schema'],'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1','Real durable receipt');exact(receipt['status'],'PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY','Receipt status');exact(audit['schema'],'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V2','Only explicit V2 observation reader supported');exact(audit['status'],'PASS','Actual observation independent audit')
 for obj in (p,receipt,audit):permissions(obj);claims_of(obj,claims)
 exact(p['source_hashes'],receipt['source_hashes'],'Payload/receipt source maps exact')
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
 plan=c['plan'];permissions(plan)
 for k in ('observation_created','timeliness_verified','future_independent_oos','filesystem_attempt_inventory_authenticated'):require(plan[k]is False,'No capture planner authority')
 exact(plan['schema'],'COMPACT_HISTORY_VARIABLE_PREFIX_CAPTURE_PLAN_V1','Explicit variable capture only');exact(plan['status'],'ONE_NEW_SESSION_CANDIDATE_NOT_OBSERVED','Single saved capture');exact(plan['diagnostics'],[],'No revisions or mismatched days');exact(plan['candidate_session'],session,'Same capture session');integer(plan['candidate_sequence'],position+1);exact(plan['known_typed_rows_preserved'],rows[:position],'Capture complete prior prefix');exact(plan['parent_attempt_inventory_preserved'],attempts[:j],'Capture complete prior attempts');exact(c['parent_references'],p['input_references']['parent'],'Capture parent association')
 caprefs={k:capture[k]for k in ENVELOPE_REFS};exact(p['input_references']['capture'],caprefs,'Observation capture four refs');exact(receipt['input_references'],p['input_references'],'Receipt eight refs');exact(audit['input_references'],p['input_references'],'Audit eight refs');exact(p['observation_identity'],dict(parent_reference=c['parent_references']['reference'],capture_reference=capture['reference'],session=session),'Parent/capture identity');exact(p['parent_readback_reference'],c['parent_references']['readback_reference'],'Parent audit identity');exact(audit['parent_history_reference'],c['parent_references']['reference'],'Reader parent identity')
 require(ca['snapshot_bytes_verified']is True and ca['current_live_cache_read_or_reverified']is False and ca['external_clock_attestation_verified']is False,'Audited permanent snapshot role');exact(ca['parent_references'],c['parent_references'],'Audited parent roles')
 for k,v in (('status',plan['status']),('parent_typed_row_count',position),('parent_observed_count',position-5),('parent_gap_count',5),('candidate_session',session),('diagnostic_count',0)):exact(ca['counts'][k],v,'Audited capture counts')
 exact(entry['captured_baseline_references'],{t:c['captured_artifacts'][t]for t in ('QQQ','SPY')},'Compact captured baseline');exact(entry['previous_baseline_references'],plan['baseline_references'],'Compact previous baseline')
 for ticker in ('QQQ','SPY'):
  current=c['captured_artifacts'][ticker];base=plan['baseline_references'][ticker];saved=p['full_original_sources_preserved'][ticker]
  exact(saved['sources']['reference'],current,'Original snapshot reference');exact(saved['baseline_sources']['reference'],base,'Original baseline reference');exact(plan['source_evidence'][ticker]['source_reference'],current,'Plan snapshot ref');exact(plan['source_evidence'][ticker]['baseline_reference'],base,'Plan baseline ref');exact(plan['source_evidence'][ticker]['new_session_dates'],[session],'Single symmetrical date');ref(current,claims);ref(base,claims);association(ca['source_hashes'],current)
  for source in (current,base):association(p['source_hashes'],source);association(audit['source_hashes'],source)
  current_rows=saved['sources']['rows'];old_rows=saved['baseline_sources']['rows'];require(type(current_rows)is list and type(old_rows)is list and current_rows and len(current_rows)==len(old_rows)+1,'Stored single-row append');exact(current_rows[:-1],old_rows,'All original price rows retained, not decoded again');exact([r['Date']for r in old_rows if r['Date']>=rows[0]['session']],[r['session']for r in rows[:position]],'Full baseline dates');exact(current_rows[-1],p['selected_original_rows'][ticker],'Selected saved source row');exact(current_rows[-1]['Date'],session,'Selected row date');exact(p['source_row_locations'][ticker],dict(original_data_row_index=len(current_rows)-1,reference=current),'Original source pointer')
 tzref=c['captured_artifacts']['tzif'];ref(tzref,claims);association(ca['source_hashes'],tzref);exact(p['tzif_reference'],tzref,'Same TZif');require(type(tzif_bytes)is bytes and 0<len(tzif_bytes)<=100000 and sha256(tzif_bytes).hexdigest()==tzref['sha256'],'Consumed exact TZif');exact(p['tzif_bytes_base64'],base64.b64encode(tzif_bytes).decode(),'Saved TZif bytes');zone=ZoneInfo.from_file(BytesIO(tzif_bytes),key='America/New_York')
 close=datetime.combine(day(session),time(16),zone).astimezone(timezone.utc);following=day(session)+timedelta(days=1)
 while following.weekday()>=5:following+=timedelta(days=1)
 deadline=datetime.combine(following,time(9,30),zone).astimezone(timezone.utc)
 exact(p['capture_started_at_utc'],c['capture_started_at'],'Capture start');exact(p['capture_completed_at_utc'],c['capture_completed_at'],'Capture end');exact(plan['capture_started_at'],c['capture_started_at'],'Plan start');exact(plan['capture_completed_at'],c['capture_completed_at'],'Plan end');exact(p['conservative_close_utc'],close.isoformat(),'Bound regular close');exact(p['conservative_deadline_utc'],deadline.isoformat(),'Bound conservative deadline')
 cs,ce,ws,we,pc=map(utc,(p['capture_started_at_utc'],p['capture_completed_at_utc'],p['writer_started_at_utc'],p['writer_completed_at_utc'],receipt['publication_check_at_utc']));require(close<=cs<=ce<=ws<=we<=pc,'Non-backdated saved receipt interval');exact(p['timing_classification'],'LATE_OBSERVATION'if we>=deadline else'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW','Payload timing classification');exact(receipt['timing_classification'],'LATE_OBSERVATION'if pc>=deadline else p['timing_classification'],'Receipt timing classification');exact(audit['counts']['timing_classification'],receipt['timing_classification'],'Audited receipt timing');exact(receipt['publication_time_role'],'AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE','Not final durable clock')
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
 satisfied=not reasons
 return dict(schema='PERSISTED_OBSERVATION_CANDIDATE_CALENDAR_EVIDENCE_V2',policy_id=POLICY,status='CONDITIONAL_CALENDAR_PREREQUISITES_ONLY'if satisfied else'BLOCKED',calendar_prerequisites_conditionally_satisfied=satisfied,reasons=reasons,lineage_blockers=['SEAL_STATUS_EVENT_HISTORY_NOT_BOUND','NEW_CANDIDATE_GENERATOR_AND_COHORT_CONSUMER_NOT_BOUND'],known_typed_rows_preserved=deepcopy(rows),parent_attempt_inventory_preserved=deepcopy(attempts),selected_observation_id=p['observation_id'],selected_existing_row=deepcopy(selected),selected_compact_entry=deepcopy(entry),first_actual_observed_session_by_month=deepcopy(months),monthly_coordinate=monthly,original_seal_status=selected['seal_status'],later_observed_sessions=[r['session']for r in rows[position+1:]if r['kind']!='MISSED_OBSERVATION'],input_references=dict(history={k:deepcopy(history[k])for k in ENVELOPE_REFS},observation={k:deepcopy(observation[k])for k in OBS_REFS},capture=deepcopy(caprefs),tzif=deepcopy(tzref)),timing=dict(capture_start=p['capture_started_at_utc'],capture_end=p['capture_completed_at_utc'],writer_start=p['writer_started_at_utc'],writer_end=p['writer_completed_at_utc'],publication_check=receipt['publication_check_at_utc'],publication_time_role=receipt['publication_time_role'],seal_evaluation_at_utc=seal_evaluation_at_utc,conservative_close_utc=close.isoformat(),conservative_deadline_utc=deadline.isoformat()),source_hash_claims=claims,scope='STRUCTURAL_REFERENCE_AND_CONDITIONAL_CLOCK_CHECKS_NOT_BYTE_AUTHENTICATION_OR_SEAL_AUTHORITY',**dict.fromkeys(FALSE,False))
