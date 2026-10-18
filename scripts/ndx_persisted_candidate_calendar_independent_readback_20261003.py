"""Independent persisted-calendar evidence readback. No producer/core execution."""
import argparse,base64,hashlib,json,os,shutil
from copy import deepcopy
from datetime import date,datetime,time,timedelta,timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PRODUCER=ROOT/'scripts/ndx_persisted_candidate_calendar_20261003.py'
PRODUCER_SHA='c10c5a92bef50ca8208da796d7b0370eaf174a30e85e1536865c73e880f87801'
CORE=ROOT/'backtest/ndx_persisted_candidate_calendar_research.py'
CORE_SHA='ec6243c2832538e27f2ee2a2cec1aac580be3ab6265944a6d931c2b1f7aaa500'
PARENT=ROOT/'data/cache/research/persisted_candidate_calendar_20261003_v1'
OUTPUT=ROOT/'data/cache/research/persisted_candidate_calendar_independent_readback_20261003_v1'
RESULT_SHA=None;PUBLICATION_SHA=None
ROLES=('reference','publication_reference','readback_reference','reader_reference')
OBS_ROLES=('payload_reference','receipt_reference','audit_reference','reader_reference')
HISTORY_BOUND=dict.fromkeys(ROLES);CAPTURE_BOUND=dict.fromkeys(ROLES);OBSERVATION_BOUND=dict.fromkeys(OBS_ROLES)
FALSE=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','source_evidence_authenticated','observation_receipt_authenticated','clock_authenticity_verified','final_durable_completion_time_verified','seal_attempt_history_authenticated','production_lineage_ready','old_calendar_mutated','old_generator_called','observation_created','seal_event_created','future_independent_oos','exchange_holidays_verified','early_closes_verified','capture_called','observation_writer_called','history_append_called','old_audit_repeated','network_called')
POLICY='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
def need(ok,msg):
 if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def same(a,b,msg='Exact metadata'):need(enc(a)==enc(b),msg)
def count(v,n):need(type(v)is int and v==n,'Exact integer count')
def reference(p,h):
 need(type(p)is str and p.strip()==p and p and type(h)is str and len(h)==64 and all(c in '0123456789abcdef'for c in h),'Pending or invalid reference');return dict(path=p,sha256=h)
def merge(s,r):
 same(sorted(r),['path','sha256']);reference(r['path'],r['sha256']);need(r['path']not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def claims(s,obj):
 need(type(obj['source_hashes'])is dict,'Source table')
 for p,h in obj['source_hashes'].items():merge(s,reference(p,h))
def associated(s,r):need(s.get(r['path'])==r['sha256'],'Source association')
def false(obj,keys=FALSE):
 for k in keys:need(obj[k]is False,'Authority/type '+k)
def utc(s):
 need(type(s)is str,'UTC string');t=datetime.fromisoformat(s.replace('Z','+00:00'));need(t.utcoffset()==timedelta(0),'UTC required');return t
def day(s):
 d=date.fromisoformat(s);need(d.isoformat()==s and d.weekday()<5,'Canonical session');return d
def decode(raw):
 def pairs(xs):
  d={}
  for k,v in xs:need(k not in d,'Duplicate key');d[k]=v
  return d
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def guard(s):
 need(sha(SOURCE.read_bytes())==LOADED,'Loaded reader changed')
 forbidden={(ROOT/'data/cache'/f'{t}.csv').resolve()for t in ('QQQ','SPY')}
 for p,h in s.items():
  path=Path(p);need(path.resolve()not in forbidden,'Persistent live source');need(path.is_file()and not path.is_symlink()and not(path.parent/'failure.json').exists(),'Failed/nonregular source');need(sha(path.read_bytes())==h,'Source drift')
def load(r,s):
 merge(s,r);need(sha(SOURCE.read_bytes())==LOADED,'Loaded reader changed');path=Path(r['path'])
 forbidden={(ROOT/'data/cache'/f'{t}.csv').resolve()for t in ('QQQ','SPY')}
 need(path.resolve()not in forbidden,'Persistent live source');need(path.is_file()and not path.is_symlink()and not(path.parent/'failure.json').exists(),'Failed/nonregular source')
 raw=path.read_bytes();need(sha(raw)==r['sha256'],'Source drift');return raw
def configured(mapping,roles):
 same(sorted(mapping),sorted(roles));out={}
 for k,v in mapping.items():need(type(v)is tuple and len(v)==2,'Pending input anchor');out[k]=reference(str(ROOT/v[0]),v[1])
 return out

def inspect(docs,tz,result,pub,started,refs,result_ref,started_ref,base):
 """Independent metadata and calendar reconstruction, consumes no files."""
 h,c,o=docs['history'],docs['capture'],docs['observation'];hd=h['document'];cd=c['document'];p=o['payload'];r=o['receipt'];a=o['audit'];source_claims={}
 for kind,env in (('history',h),('capture',c)):
  prefix='PROSPECTIVE_OBSERVATION_PARENT_HISTORY'if kind=='history'else'VARIABLE_PREFIX_CAPTURE';version='V2'if kind=='history'else'V1';key='history_reference'if kind=='history'else'capture_reference'
  same(env['document']['schema'],prefix+'_'+version if kind=='history'else'SOURCE_BOUND_VARIABLE_PREFIX_CAPTURE_V1');same(env['publication']['schema'],prefix+'_PUBLICATION_'+version);same(env['readback']['schema'],prefix+'_INDEPENDENT_READBACK_'+version)
  same(env['publication']['status'],'PUBLISHED_OBSERVATION_HISTORY_NO_SEAL'if kind=='history'else'PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION');same(env['readback']['status'],'PASS')
  same(env['publication'][key],env['reference']);same(env['readback'][key],env['reference']);same(env['readback']['publication_reference'],env['publication_reference']);same(env['readback']['reader_sha256'],env['reader_reference']['sha256']);same(env['document']['source_hashes'],env['publication']['source_hashes'])
  for k in ROLES:merge(source_claims,env[k])
  for obj in (env['document'],env['publication'],env['readback']):false(obj,FALSE[:4]);claims(source_claims,obj)
  for k in ('reference','publication_reference','reader_reference'):associated(env['readback']['source_hashes'],env[k])
  for path,hs in env['document']['source_hashes'].items():associated(env['readback']['source_hashes'],reference(path,hs))
 same(hd['policy_id'],POLICY);rows=hd['known_typed_rows'];need(type(rows)is list and 66<=len(rows)<20000,'Complete history');months={};previous='';seen=set()
 for i,row in enumerate(rows):
  same(sorted(row),sorted(('sequence','session','kind','evidence_reference','seal_status')));count(row['sequence'],i+1);day(row['session']);need(row['session']>previous,'Ordered sessions');previous=row['session'];need(row['kind']in ('SEALED_PARENT_OBSERVED_SESSION','MISSED_OBSERVATION','PROSPECTIVE_OBSERVED_SESSION'),'Row kind');need(row['seal_status']in ('NOT_ATTEMPTED','UNKNOWN','FAILED','SEALED'),'Seal state')
  er=row['evidence_reference'];same(sorted(er),['json_pointer','path','sha256']);need(type(er['json_pointer'])is str and er['json_pointer'].startswith('/'),'Pointer');merge(source_claims,{k:er[k]for k in ('path','sha256')});need(enc(er)not in seen,'Unique row pointer');seen.add(enc(er))
  if row['kind']=='MISSED_OBSERVATION':same(row['seal_status'],'NOT_ATTEMPTED')
  else:months.setdefault(row['session'][:7],row['session'])
 genesis=hd['genesis_preserved']['document']['projection_inputs']['known_rows'];count(len(genesis),65);same(rows[:65],genesis);count(sum(x['kind']=='MISSED_OBSERVATION'for x in genesis),5);count(sum(x['kind']=='SEALED_PARENT_OBSERVED_SESSION'for x in genesis),60)
 entries=hd['observations'];attempts=hd['parent_attempt_inventory'];need(type(entries)is list and type(attempts)is list,'Lists');count(len(entries),len(rows)-65);count(len(attempts),len(entries));count(hd['observation_count'],len(entries));ids=set()
 for j,e in enumerate(entries):
  same(e['schema'],'COMPACT_OBSERVATION_REFERENCE_ENTRY_V1');need(e['original_payload_embedded']is False,'Compact only');count(e['sequence'],66+j);same(e['session'],rows[65+j]['session']);same(rows[65+j]['kind'],'PROSPECTIVE_OBSERVED_SESSION');same(e['observation_id'],sha(enc(e['observation_identity'])));need(e['observation_id']not in ids,'Unique ID');ids.add(e['observation_id'])
  for k in OBS_ROLES:merge(source_claims,e[k])
  same(rows[65+j]['evidence_reference'],dict(e['payload_reference'],json_pointer='/observation_identity'));same(attempts[j],dict(observation_id=e['observation_id'],session=e['session'],status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',payload_reference=e['payload_reference'],receipt_reference=e['receipt_reference'],independent_readback_reference=e['audit_reference']))
 same(hd['first_actual_observed_session_by_month'],months);same(hd['last_accounted_session'],rows[-1]['session']);same(hd['baseline_references'],entries[-1]['captured_baseline_references']);hc=h['readback']['counts'];count(hc['typed_row_count'],len(rows));count(hc['observation_count'],len(entries));count(hc['new_observation_count'],1);same(hc['first_actual_observed_session_by_month'],months)
 for k in OBS_ROLES:merge(source_claims,o[k])
 for obj in (p,r,a):false(obj,FALSE[:4]);claims(source_claims,obj)
 same(p['source_hashes'],r['source_hashes'],'Payload/receipt source maps exact')
 for path,hs in p['source_hashes'].items():associated(a['source_hashes'],reference(path,hs))
 same(p['schema'],'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1');same(r['schema'],'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1');same(a['schema'],'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V2');same(a['status'],'PASS');same(r['status'],'PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY')
 for obj in (p,r):same(obj['writer_adapter_schema'],'VARIABLE_PREFIX_OBSERVATION_WRITER_V2')
 need(a['writer_called']is False and a['old_audit_repeated']is False,'Independent observation');same(r['payload_reference'],o['payload_reference']);same(a['payload_reference'],o['payload_reference']);same(a['receipt_reference'],o['receipt_reference']);same(a['reader_sha256'],o['reader_reference']['sha256'])
 for k in ('payload_reference','receipt_reference','reader_reference'):associated(a['source_hashes'],o[k])
 matches=[j for j,e in enumerate(entries)if e['observation_id']==p['observation_id']];count(len(matches),1);j=matches[0];e=entries[j];pos=65+j;selected=rows[pos];session=p['session'];day(session);need(session>='2026-10-01','Activation');count(p['sequence'],pos+1)
 for k in OBS_ROLES:same(e[k],o[k]);associated(hd['source_hashes'],o[k]);associated(h['readback']['source_hashes'],o[k])
 same(e['observation_identity'],p['observation_identity']);same(r['observation_id'],e['observation_id']);same(e['session'],session);same(p['kind'],'PROSPECTIVE_OBSERVED_SESSION');same(p['initial_seal_status'],'NOT_ATTEMPTED');same(p['known_typed_rows_preserved'],rows[:pos]);same(p['parent_attempt_inventory_preserved'],attempts[:j]);count(a['counts']['parent_observed_count'],pos-5);count(a['counts']['parent_gap_count'],5);count(a['counts']['new_observation_count'],1)
 for role,obj in (('payload',p),('receipt',r),('audit',a)):
  same(e['original_source_hash_claims'][role],obj['source_hashes'])
  for path,hs in obj['source_hashes'].items():associated(hd['source_hashes'],reference(path,hs));associated(h['readback']['source_hashes'],reference(path,hs))
 for k in ('initial_seal_status','month_first_actual_observation','first_actual_observed_session_of_month'):same(e[k],p[k])
 same(e['timing_classification'],r['timing_classification']);same(e['payload_timing_classification'],p['timing_classification']);plan=cd['plan'];false(plan,FALSE[:4]);false(plan,('observation_created','timeliness_verified','future_independent_oos','filesystem_attempt_inventory_authenticated'));same(plan['schema'],'COMPACT_HISTORY_VARIABLE_PREFIX_CAPTURE_PLAN_V1');same(plan['status'],'ONE_NEW_SESSION_CANDIDATE_NOT_OBSERVED');same(plan['diagnostics'],[]);same(plan['candidate_session'],session);count(plan['candidate_sequence'],pos+1);same(plan['known_typed_rows_preserved'],rows[:pos]);same(plan['parent_attempt_inventory_preserved'],attempts[:j]);same(cd['parent_references'],p['input_references']['parent'])
 caprefs={k:c[k]for k in ROLES};same(p['input_references']['capture'],caprefs);same(r['input_references'],p['input_references']);same(a['input_references'],p['input_references']);same(p['observation_identity'],dict(parent_reference=cd['parent_references']['reference'],capture_reference=c['reference'],session=session));same(p['parent_readback_reference'],cd['parent_references']['readback_reference']);same(a['parent_history_reference'],cd['parent_references']['reference'])
 ca=c['readback'];need(ca['snapshot_bytes_verified']is True and ca['current_live_cache_read_or_reverified']is False and ca['external_clock_attestation_verified']is False,'Snapshot role');same(ca['parent_references'],cd['parent_references'])
 for k,v in dict(status=plan['status'],parent_typed_row_count=pos,parent_observed_count=pos-5,parent_gap_count=5,candidate_session=session,diagnostic_count=0).items():same(ca['counts'][k],v)
 same(e['captured_baseline_references'],{t:cd['captured_artifacts'][t]for t in ('QQQ','SPY')});same(e['previous_baseline_references'],plan['baseline_references'])
 for ticker in ('QQQ','SPY'):
  cur=cd['captured_artifacts'][ticker];old=plan['baseline_references'][ticker];saved=p['full_original_sources_preserved'][ticker]
  for role,rr in (('sources',cur),('baseline_sources',old)):same(saved[role]['reference'],rr);associated(p['source_hashes'],rr);associated(a['source_hashes'],rr);merge(source_claims,rr)
  same(plan['source_evidence'][ticker]['source_reference'],cur);same(plan['source_evidence'][ticker]['baseline_reference'],old);same(plan['source_evidence'][ticker]['new_session_dates'],[session]);associated(ca['source_hashes'],cur)
  newrows=saved['sources']['rows'];oldrows=saved['baseline_sources']['rows'];need(type(newrows)is list and type(oldrows)is list and newrows,'Original rows');count(len(newrows),len(oldrows)+1);same(newrows[:-1],oldrows);same([x['Date']for x in oldrows if x['Date']>=rows[0]['session']],[x['session']for x in rows[:pos]]);same(newrows[-1],p['selected_original_rows'][ticker]);same(newrows[-1]['Date'],session);same(p['source_row_locations'][ticker],dict(original_data_row_index=len(newrows)-1,reference=cur))
 tzref=cd['captured_artifacts']['tzif'];merge(source_claims,tzref);associated(ca['source_hashes'],tzref);same(p['tzif_reference'],tzref);need(type(tz)is bytes and 0<len(tz)<=100000 and sha(tz)==tzref['sha256'],'Bound TZif');same(p['tzif_bytes_base64'],base64.b64encode(tz).decode());zone=ZoneInfo.from_file(BytesIO(tz),key='America/New_York');d=day(session);close=datetime.combine(d,time(16),zone).astimezone(timezone.utc);following=d+timedelta(days=1)
 while following.weekday()>4:following+=timedelta(days=1)
 deadline=datetime.combine(following,time(9,30),zone).astimezone(timezone.utc)
 same(p['capture_started_at_utc'],cd['capture_started_at']);same(p['capture_completed_at_utc'],cd['capture_completed_at']);same(plan['capture_started_at'],cd['capture_started_at']);same(plan['capture_completed_at'],cd['capture_completed_at']);same(p['conservative_close_utc'],close.isoformat());same(p['conservative_deadline_utc'],deadline.isoformat())
 cs,ce,ws,we,pc=map(utc,(p['capture_started_at_utc'],p['capture_completed_at_utc'],p['writer_started_at_utc'],p['writer_completed_at_utc'],r['publication_check_at_utc']));need(close<=cs<=ce<=ws<=we<=pc,'Saved clock order');same(p['timing_classification'],'LATE_OBSERVATION'if we>=deadline else'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW');same(r['timing_classification'],'LATE_OBSERVATION'if pc>=deadline else p['timing_classification']);same(a['counts']['timing_classification'],r['timing_classification']);same(r['publication_time_role'],'AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE')
 monthly=months[session[:7]]==session
 for obj in (p,r):same(obj['month_first_actual_observation'],monthly)
 same(p['first_actual_observed_session_of_month'],months[session[:7]]);same(a['counts']['month_first_actual_observation'],monthly)
 evaluation=result['evaluation_at_utc'];seal=utc(evaluation);need(utc(started['started_at_utc'])<=seal,'Evaluation before start');reasons=[]
 if not monthly:reasons.append('NOT_FIRST_ACTUAL_OBSERVATION_OF_MONTH')
 if pos!=len(rows)-1:reasons.append('LATER_OBSERVED_SESSION_NO_BACKFILL')
 if selected['seal_status']!='NOT_ATTEMPTED':reasons.append('PRIOR_SEAL_STATE_DOES_NOT_AUTHORIZE_NEW_ATTEMPT')
 if not cs<=ce<deadline:reasons.append('CAPTURE_OUTSIDE_CONSERVATIVE_WINDOW')
 if pc>=deadline:reasons.append('PERSISTED_OBSERVATION_PUBLICATION_CHECK_LATE')
 if not pc<=seal<deadline:reasons.append('SEAL_EVALUATION_OUTSIDE_CONSERVATIVE_WINDOW')
 expected=dict(schema='PERSISTED_OBSERVATION_CANDIDATE_CALENDAR_EVIDENCE_V2',policy_id=POLICY,status='BLOCKED'if reasons else'CONDITIONAL_CALENDAR_PREREQUISITES_ONLY',calendar_prerequisites_conditionally_satisfied=not reasons,reasons=reasons,lineage_blockers=['SEAL_STATUS_EVENT_HISTORY_NOT_BOUND','NEW_CANDIDATE_GENERATOR_AND_COHORT_CONSUMER_NOT_BOUND'],known_typed_rows_preserved=rows,parent_attempt_inventory_preserved=attempts,selected_observation_id=p['observation_id'],selected_existing_row=selected,selected_compact_entry=e,first_actual_observed_session_by_month=months,monthly_coordinate=monthly,original_seal_status=selected['seal_status'],later_observed_sessions=[x['session']for x in rows[pos+1:]if x['kind']!='MISSED_OBSERVATION'],input_references=dict(refs,tzif=tzref),timing=dict(capture_start=p['capture_started_at_utc'],capture_end=p['capture_completed_at_utc'],writer_start=p['writer_started_at_utc'],writer_end=p['writer_completed_at_utc'],publication_check=r['publication_check_at_utc'],publication_time_role=r['publication_time_role'],seal_evaluation_at_utc=evaluation,conservative_close_utc=close.isoformat(),conservative_deadline_utc=deadline.isoformat()),source_hash_claims=source_claims,scope='STRUCTURAL_REFERENCE_AND_CONDITIONAL_CLOCK_CHECKS_NOT_BYTE_AUTHENTICATION_OR_SEAL_AUTHORITY',**dict.fromkeys(FALSE[:18],False))
 core_ref=reference(str(CORE),CORE_SHA)
 same(started,dict(schema='PERSISTED_CANDIDATE_CALENDAR_STARTED_V2',input_references=refs,core_reference=core_ref,source_hashes=base,started_at_utc=started['started_at_utc'],retry_allowed=False,**dict.fromkeys(FALSE,False)),'Complete started record')
 expected_result=dict(schema='SOURCE_BOUND_PERSISTED_CANDIDATE_CALENDAR_V2',evidence=expected,input_references=refs,core_reference=core_ref,source_hashes=base,started_reference=started_ref,evaluation_at_utc=evaluation,evaluation_clock_read_by_runner=True,external_clock_attestation_verified=False,evaluation_time_role='BEFORE_CONDITIONAL_EVALUATION_NOT_ACTUAL_SEAL_OR_FINAL_DURABLE_COMPLETION',**dict.fromkeys(FALSE,False));same(result,expected_result,'Complete independent result')
 same(pub,dict(schema='PERSISTED_CANDIDATE_CALENDAR_PUBLICATION_V2',status='PUBLISHED_CONDITIONAL_EVIDENCE_NOT_SEAL_AUTHORITY',result_reference=result_ref,source_hashes=base,**dict.fromkeys(FALSE,False)),'Complete publication')
 for path,hs in source_claims.items():associated(base,reference(path,hs))
 return dict(typed_row_count=len(rows),observed_count=len(rows)-5,gap_count=5,observation_count=len(entries),selected_sequence=pos+1,monthly_coordinate=monthly,status=expected['status'],reason_count=len(reasons))

def readback(*,execute=False):
 need(execute is True,'Explicit execute');result_ref=reference(str(PARENT/'result.json'),RESULT_SHA);pub_ref=reference(str(PARENT/'publication.json'),PUBLICATION_SHA)
 refs=dict(history=configured(HISTORY_BOUND,ROLES),observation=configured(OBSERVATION_BOUND,OBS_ROLES),capture=configured(CAPTURE_BOUND,ROLES));base={};merge(base,reference(str(PRODUCER),PRODUCER_SHA));merge(base,reference(str(CORE),CORE_SHA));docs={}
 for kind,rr in refs.items():
  env=dict(rr)
  for k in rr:merge(base,rr[k])
  pairs=(('payload_reference','payload'),('receipt_reference','receipt'),('audit_reference','audit'))if kind=='observation'else(('reference','document'),('publication_reference','publication'),('readback_reference','readback'))
  for role,key in pairs:env[key]=decode(load(rr[role],base));claims(base,env[key])
  load(rr['reader_reference'],base);docs[kind]=env
 tz=load(docs['capture']['document']['captured_artifacts']['tzif'],base);guard(base);sources=dict(base);result=decode(load(result_ref,sources));pub=decode(load(pub_ref,sources));started_ref=result['started_reference'];same(started_ref['path'],str(PARENT/'started.json'));started=decode(load(started_ref,sources));same(sorted(x.name for x in PARENT.iterdir()),['publication.json','result.json','started.json']);merge(sources,reference(str(SOURCE),LOADED));need(not OUTPUT.exists(),'Create-only no retry');need(shutil.disk_usage(OUTPUT.anchor).free>=5*1024**3,'Resource stop');OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  counts=inspect(docs,tz,result,pub,started,refs,result_ref,started_ref,base);guard(sources)
  report=dict(schema='PERSISTED_CANDIDATE_CALENDAR_INDEPENDENT_READBACK_V2',status='PASS',result_reference=result_ref,publication_reference=pub_ref,started_reference=started_ref,input_references=refs,reader_sha256=LOADED,source_hashes=sources,counts=counts,producer_or_core_called=False,prior_audit_repeated=False,external_clock_authenticated=False,**dict.fromkeys(FALSE,False));raw=enc(report);need(shutil.disk_usage(OUTPUT.anchor).free>=5*1024**3+len(raw),'Resource stop');path=OUTPUT/'independent_readback.json'
  with path.open('xb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
  guard(sources);same(sorted(x.name for x in PARENT.iterdir()),['publication.json','result.json','started.json']);need(path.read_bytes()==raw,'Saved report bytes');same(sorted(x.name for x in OUTPUT.iterdir()),['independent_readback.json']);return reference(str(path),sha(raw))
 except BaseException as error:
  with(OUTPUT/'failure.json').open('xb')as f:f.write(enc(dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),retry_allowed=False)));f.flush();os.fsync(f.fileno())
  raise
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=parser.parse_args().execute)))
