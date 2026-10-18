"""Independent first V1 SNAPSHOT calendar evidence readback. No producer/core execution."""
import argparse,base64,hashlib,json,os,shutil
from copy import deepcopy
from datetime import date,datetime,time,timedelta,timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PRODUCER=ROOT/'scripts/ndx_first_persisted_candidate_calendar_20261003.py'
PRODUCER_SHA='0aec79a5098c998bfb99cc87881fe20efc96bdc682b834d717e32a33dfa18f07'
CORE=ROOT/'backtest/ndx_first_persisted_candidate_calendar_research.py'
CORE_SHA='74be1e9adfaf7ba11562b6d32fec124228a64c26df4a958b48e966843940c384'
PARENT=ROOT/'data/cache/research/first_persisted_candidate_calendar_20261003_v1'
OUTPUT=ROOT/'data/cache/research/first_persisted_candidate_calendar_independent_readback_20261003_v1'
RESULT_SHA=None;PUBLICATION_SHA=None
ROLES=('reference','publication_reference','readback_reference','reader_reference')
OBS_ROLES=('payload_reference','receipt_reference','audit_reference','reader_reference')
GENESIS_BOUND={'reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\gap_monthly_policy_20261002_v1\\policy.json', 'd04c7cd9181eb5585c7ddbd880b02947ec135552944a6f90b5e1fd39bb21b946'), 'publication_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\gap_monthly_policy_20261002_v1\\publication.json', '23af1d2798f4c7d5e33142a97319dead34a533606b98304da7b7c9deeb65f76d'), 'readback_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\gap_monthly_policy_history_input_readback_20261003_v1\\independent_readback.json', 'f11e5e1722b54724ffccaccb5a2c21ea945cbc9c9d96c458d064e11566833cd6'), 'reader_reference': ('E:\\Git\\us_ratchet\\scripts\\ndx_gap_monthly_policy_history_input_readback_20261003.py', '80ac03fb2dae11a96d4cd060ee1eb0c30731aab271fe793ece7fb52743d99b6e')};HISTORY_BOUND={'reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\prospective_observation_parent_history_20261003_v1\\history.json', 'bd0eb3bb1ed5a4103af964e4c2016caf8e5abf45caf799ffbf786642bc7a4a33'), 'publication_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\prospective_observation_parent_history_20261003_v1\\publication.json', '648f6937e7ff876a824bab96a654461b411dccd6b4c7a6a19217d0bdd09fbcf6'), 'readback_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\prospective_observation_parent_history_independent_readback_20261003_v1\\independent_readback.json', 'c6f9a113b1b5f00128befa74a415e6604012d47ac17eb7db2048dafa8a31a86a'), 'reader_reference': ('E:\\Git\\us_ratchet\\scripts\\ndx_prospective_observation_parent_history_independent_readback_20261003.py', '876094538679db3216f69cf3035101baf91498d5296512cbef4b2911486d7aef')};CAPTURE_BOUND={'reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\forward_source_capture_oct02_20261003_v1\\capture.json', 'a1a2b89c71ba651215cca153ccc6cea8e88a09a7a83949e523efdc5316c95882'), 'publication_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\forward_source_capture_oct02_20261003_v1\\publication.json', '4cea5fddd57b0b1371bf6941f2e7d855890e868a1bb8513fc3994886ab61a82e'), 'readback_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\forward_source_capture_oct02_independent_readback_20261003_v1\\independent_readback.json', '850601204fb50bb9cebbefcb4c9594a37b5bece71e5d2be26fb15f79e38881a8'), 'reader_reference': ('E:\\Git\\us_ratchet\\scripts\\ndx_forward_source_capture_oct02_independent_readback_20261003.py', 'b3e0377ea39c89b73c1cfdfdb3874ab68b151ec1c96c28f898df82164e7d218d')};OBSERVATION_BOUND={'payload_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\prospective_observation_receipt_20261003_v1\\observation_payload.json', '06cf063ebc03f3808ff33d3a95f065cd6d789f30463ee46d26aef7fb69f9992a'), 'receipt_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\prospective_observation_receipt_20261003_v1\\receipt.json', 'bde85f8e661ef1caba47ea69bb04f36e073ce5729f058959878571e5d228c248'), 'audit_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\prospective_observation_receipt_20261003_v1\\independent_readback.json', '1c6f13cac2d33c776a61e51f320b58d96960d547cdd7d3b6e04e21a1022fe64a'), 'reader_reference': ('E:\\Git\\us_ratchet\\scripts\\ndx_prospective_observation_independent_readback_20261003.py', 'bc0d13435950ce5230551fca7daf7f4e43b6c33942ecf5cfc3dc28930d4b2e53')}
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

 for p,h in s.items():
  path=Path(p);need(not is_live(path),'Persistent live source');need(path.is_file()and not path.is_symlink()and not(path.parent/'failure.json').exists(),'Failed/nonregular source');need(sha(path.read_bytes())==h,'Source drift')
def load(r,s):
 merge(s,r);need(sha(SOURCE.read_bytes())==LOADED,'Loaded reader changed');path=Path(r['path']);need(not is_live(path),'Persistent live source');need(path.is_file()and not path.is_symlink()and not(path.parent/'failure.json').exists(),'Failed/nonregular source');raw=path.read_bytes();need(sha(raw)==r['sha256'],'Source drift');return raw
def configured(mapping,roles):
 same(sorted(mapping),sorted(roles));out={}
 for k,v in mapping.items():need(type(v)is tuple and len(v)==2,'Pending input anchor');out[k]=reference(str(ROOT/v[0]),v[1])
 return out

def is_live(path):
 p=Path(path).resolve();return p.parent.as_posix().lower().endswith('/data/cache')and p.suffix.lower()=='.csv'
def bridge(capture):
 c,p,a=capture['document'],capture['publication'],capture['readback'];original=c['source_hashes'];same(original,p['source_hashes']);same(original,a['capture_original_source_hashes_preserved']);rows=[];excluded=set()
 for ticker in ('QQQ','SPY'):
  old=c['input_references']['current_'+ticker];new=c['captured_artifacts'][ticker];merge({},old);merge({},new);same(old['path'],str(ROOT/'data/cache'/f'{ticker}.csv'),'Fixed current locator');same(new['path'],str(Path(capture['reference']['path']).parent/f'{ticker}.csv'),'Fixed snapshot locator');same(old['sha256'],new['sha256']);associated(original,old);associated(a['source_hashes'],new);excluded.add(old['path']);rows.append(dict(ticker=ticker,original_current_reference=deepcopy(old),snapshot_reference=deepcopy(new)))
 same(sorted(p for p in original if is_live(p)),sorted(excluded),'Only two bridged live declarations');need(not any(is_live(p)for p in a['source_hashes']),'Audit permanent sources')
 for p,h in original.items():
  if p not in excluded:associated(a['source_hashes'],reference(p,h))
 return dict(schema='FIRST_V1_SCOPED_SNAPSHOT_EQUIVALENCE_BRIDGE_V1',rows=rows,capture_reference=deepcopy(capture['reference']),publication_reference=deepcopy(capture['publication_reference']),readback_reference=deepcopy(capture['readback_reference']),current_live_cache_reopened=False,full_transitive_source_closure_reverified=False)

def inspect(docs,tz,result,pub,started,refs,result_ref,started_ref,base):
 """Independent metadata and calendar reconstruction, consumes no files."""
 h,c,o,g=docs['history'],docs['capture'],docs['observation'],docs['genesis'];hd=h['document'];cd=c['document'];gd=g['document'];ga=g['readback'];p=o['payload'];r=o['receipt'];a=o['audit'];source_claims={};br=bridge(c);excluded={x['original_current_reference']['path']for x in br['rows']}
 schemas={
 'history':('PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2','PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2','PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V2','PUBLISHED_OBSERVATION_HISTORY_NO_SEAL','history_reference'),
 'capture':('FORWARD_SOURCE_CAPTURE_SCOPED_PAYLOAD_V1','FORWARD_SOURCE_CAPTURE_SCOPED_PUBLICATION_V1','SCOPED_FORWARD_CAPTURE_INDEPENDENT_READBACK_V1','PUBLISHED_CURRENT_CACHE_CAPTURE_NOT_CALENDAR_APPEND','capture_reference'),
 'genesis':('SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1','GAP_MONTHLY_POLICY_PUBLICATION_V1','GAP_MONTHLY_POLICY_HISTORY_INPUT_READBACK_V1','PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL','policy_reference')}
 for kind,env in (('history',h),('capture',c),('genesis',g)):
  ds,ps,rs,status,key=schemas[kind];same(env['document']['schema'],ds);same(env['publication']['schema'],ps);same(env['readback']['schema'],rs);same(env['publication']['status'],status);same(env['readback']['status'],'PASS');same(env['publication'][key],env['reference']);same(env['readback'][key],env['reference']);same(env['readback']['publication_reference'],env['publication_reference']);same(env['readback']['reader_sha256'],env['reader_reference']['sha256']);same(env['document']['source_hashes'],env['publication']['source_hashes'])
  for k in ROLES:merge(source_claims,env[k])
  for obj in (env['document'],env['publication'],env['readback']):
   false(obj,FALSE[:4])
   for path,hs in obj['source_hashes'].items():
    if kind=='capture'and obj is not env['readback']and path in excluded:continue
    need(not is_live(path),'Unbridged live source');merge(source_claims,reference(path,hs))
  for k in ('reference','publication_reference','reader_reference'):associated(env['readback']['source_hashes'],env[k])
  for path,hs in env['document']['source_hashes'].items():
   if not(kind=='capture'and path in excluded):associated(env['readback']['source_hashes'],reference(path,hs))
 same(hd['genesis_preserved'],g);same(hd['parent_history_reference'],g['reference']);same(hd['parent_readback_reference'],g['readback_reference']);count(gd['new_observation_count'],0);same(gd['projection_inputs']['new_prospective_observations'],[]);same(gd['policy_id'],POLICY)
 same(hd['policy_id'],POLICY);rows=hd['known_typed_rows'];need(type(rows)is list and len(rows)==66,'Complete history');months={};previous='';seen=set()
 for i,row in enumerate(rows):
  same(sorted(row),sorted(('sequence','session','kind','evidence_reference','seal_status')));count(row['sequence'],i+1);day(row['session']);need(row['session']>previous,'Ordered sessions');previous=row['session'];need(row['kind']in ('SEALED_PARENT_OBSERVED_SESSION','MISSED_OBSERVATION','PROSPECTIVE_OBSERVED_SESSION'),'Row kind');need(row['seal_status']in ('NOT_ATTEMPTED','UNKNOWN','FAILED','SEALED'),'Seal state')
  er=row['evidence_reference'];same(sorted(er),['json_pointer','path','sha256']);need(type(er['json_pointer'])is str and er['json_pointer'].startswith('/'),'Pointer');merge(source_claims,{k:er[k]for k in ('path','sha256')});need(enc(er)not in seen,'Unique row pointer');seen.add(enc(er))
  if row['kind']=='MISSED_OBSERVATION':same(row['seal_status'],'NOT_ATTEMPTED')
  else:months.setdefault(row['session'][:7],row['session'])
 genesis=gd['projection_inputs']['known_rows'];count(len(genesis),65);same(rows[:65],genesis);count(sum(x['kind']=='MISSED_OBSERVATION'for x in genesis),5);count(sum(x['kind']=='SEALED_PARENT_OBSERVED_SESSION'for x in genesis),60);same(ga['known_typed_rows_preserved'],genesis);same(ga['counts'],dict(known_rows=65,observed_rows=60,gap_rows=5,new_observation_count=0))
 entries=hd['observations'];attempts=hd['parent_attempt_inventory'];need(type(entries)is list and type(attempts)is list,'Lists');count(len(entries),len(rows)-65);count(len(attempts),len(entries));count(hd['observation_count'],len(entries));ids=set()
 for j,e in enumerate(entries):
  same(e['schema'],'COMPACT_OBSERVATION_REFERENCE_ENTRY_V1');need(e['original_payload_embedded']is False,'Compact only');count(e['sequence'],66+j);same(e['session'],rows[65+j]['session']);same(rows[65+j]['kind'],'PROSPECTIVE_OBSERVED_SESSION');same(e['observation_id'],sha(enc(e['observation_identity'])));need(e['observation_id']not in ids,'Unique ID');ids.add(e['observation_id'])
  for k in OBS_ROLES:merge(source_claims,e[k])
  same(rows[65+j]['evidence_reference'],dict(e['payload_reference'],json_pointer='/observation_identity'));same(attempts[j],dict(observation_id=e['observation_id'],session=e['session'],status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',payload_reference=e['payload_reference'],receipt_reference=e['receipt_reference'],independent_readback_reference=e['audit_reference']))
 same(hd['source_reference_claims'],hd['source_hashes']);same(hd['first_actual_observed_session_by_month'],months);same(hd['last_accounted_session'],rows[-1]['session']);same(hd['baseline_references'],entries[-1]['captured_baseline_references']);hc=h['readback']['counts'];count(hc['typed_row_count'],len(rows));count(hc['observation_count'],len(entries));count(hc['new_observation_count'],1);same(hc['first_actual_observed_session_by_month'],months)
 for k in OBS_ROLES:merge(source_claims,o[k])
 for obj in (p,r,a):false(obj,FALSE[:4]);need(obj['live_mutation_allowed']is False,'No live authority');claims(source_claims,obj)
 same(p['source_hashes'],r['source_hashes'],'Payload/receipt source maps exact')
 for path,hs in p['source_hashes'].items():associated(a['source_hashes'],reference(path,hs))
 same(p['schema'],'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1');same(r['schema'],'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1');same(a['schema'],'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1');same(a['status'],'PASS');same(r['status'],'PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY')
 for obj in (p,r):need('writer_adapter_schema'not in obj,'V1 adapter identity')
 need(a['writer_called']is False and a['old_audit_repeated']is False,'Independent observation');same(r['payload_reference'],o['payload_reference']);same(a['payload_reference'],o['payload_reference']);same(a['receipt_reference'],o['receipt_reference']);same(a['reader_sha256'],o['reader_reference']['sha256'])
 for k in ('payload_reference','receipt_reference','reader_reference'):associated(a['source_hashes'],o[k])
 matches=[j for j,e in enumerate(entries)if e['observation_id']==p['observation_id']];count(len(matches),1);j=matches[0];e=entries[j];pos=65+j;selected=rows[pos];session=p['session'];day(session);need(session>='2026-10-01','Activation');count(p['sequence'],pos+1)
 for k in OBS_ROLES:same(e[k],o[k]);associated(hd['source_hashes'],o[k]);associated(h['readback']['source_hashes'],o[k])
 same(e['observation_identity'],p['observation_identity']);same(r['observation_id'],e['observation_id']);same(e['session'],session);same(p['kind'],'PROSPECTIVE_OBSERVED_SESSION');same(p['initial_seal_status'],'NOT_ATTEMPTED');same(p['known_typed_rows_preserved'],rows[:pos]);same(p['parent_attempt_inventory_preserved'],attempts[:j]);count(a['counts']['parent_observed_count'],pos-5);count(a['counts']['parent_gap_count'],5);count(a['counts']['new_observation_count'],1)
 for role,obj in (('payload',p),('receipt',r),('audit',a)):
  same(e['original_source_hash_claims'][role],obj['source_hashes'])
  for path,hs in obj['source_hashes'].items():associated(hd['source_hashes'],reference(path,hs));associated(h['readback']['source_hashes'],reference(path,hs))
 for k in ('initial_seal_status','month_first_actual_observation','first_actual_observed_session_of_month'):same(e[k],p[k])
 same(e['timing_classification'],r['timing_classification']);same(e['payload_timing_classification'],p['timing_classification']);plan=cd['plan'];inner=plan['capture_plan'];false(plan,FALSE[:4]);same(plan['schema'],'FORWARD_SOURCE_CAPTURE_SCOPED_PLAN_V1');same(inner['schema'],'FORWARD_SOURCE_CAPTURE_PLANNING_V1');same(inner['accounted_prefix_dates'],[x['session']for x in rows[:65]]);same(inner['status'],'NEW_SOURCE_DATES_REQUIRE_REVIEW');same(inner['new_source_dates'],[session]);same(inner['revisions'],[]);same(inner['excluded_unfinished_source_dates'],[]);same(inner['unmatched_new_source_dates_by_ticker'],dict(QQQ=[],SPY=[]));need(inner['source_suffix_asymmetry_blocks_timeliness_candidate']is False,'Symmetric append')
 caprefs={k:c[k]for k in ROLES};original_refs=dict(parent=g['reference'],parent_publication=g['publication_reference'],parent_readback=g['readback_reference'],capture=c['reference'],capture_publication=c['publication_reference']);same(p['input_references'],original_refs);need('input_references'not in r and 'parent_history_reference'not in a,'Original V1 shape')
 for rr in original_refs.values():associated(p['source_hashes'],rr);associated(r['source_hashes'],rr);associated(a['source_hashes'],rr)
 same(p['observation_identity'],dict(parent_reference=g['reference'],capture_reference=c['reference'],session=session));same(p['parent_readback_reference'],g['readback_reference']);same(cd['input_references']['frontier'],gd['frontier_reference']);ca=c['readback'];need(ca['current_live_cache_reopened']is False and ca['producer_called']is False and ca['old_audit_called']is False,'Immutable capture audit');same(ca['new_source_dates'],[session]);count(ca['revision_count'],0);count(ca['accounted_prefix_count'],65)
 baseline={t:cd['input_references']['baseline_'+t]for t in ('QQQ','SPY')};same(baseline,g['baseline_references']);same(baseline,ga['baseline_references']);same(e['captured_baseline_references'],{t:cd['captured_artifacts'][t]for t in ('QQQ','SPY')});same(e['previous_baseline_references'],baseline)
 for ticker in ('QQQ','SPY'):
  cur=cd['captured_artifacts'][ticker];old=baseline[ticker];saved=p['full_original_sources_preserved'][ticker]
  for role,rr in (('sources',cur),('baseline_sources',old)):same(saved[role]['reference'],rr);associated(p['source_hashes'],rr);associated(a['source_hashes'],rr);merge(source_claims,rr)
  associated(ca['source_hashes'],cur);newrows=saved['sources']['rows'];oldrows=saved['baseline_sources']['rows'];need(type(newrows)is list and type(oldrows)is list and newrows,'Original rows');count(len(newrows),len(oldrows)+1);same(newrows[:-1],oldrows);same([x['Date']for x in oldrows if x['Date']>=rows[0]['session']],[x['session']for x in rows[:pos]]);same(newrows[-1],p['selected_original_rows'][ticker]);same(newrows[-1]['Date'],session);same(p['source_row_locations'][ticker],dict(original_data_row_index=len(newrows)-1,reference=cur))
 tzref=cd['captured_artifacts']['tzif'];merge(source_claims,tzref);associated(ca['source_hashes'],tzref);same(p['tzif_reference'],tzref);need(type(tz)is bytes and 0<len(tz)<=100000 and sha(tz)==tzref['sha256'],'Bound TZif');same(p['tzif_bytes_base64'],base64.b64encode(tz).decode());zone=ZoneInfo.from_file(BytesIO(tz),key='America/New_York');d=day(session);close=datetime.combine(d,time(16),zone).astimezone(timezone.utc);following=d+timedelta(days=1)
 while following.weekday()>4:following+=timedelta(days=1)
 deadline=datetime.combine(following,time(9,30),zone).astimezone(timezone.utc)
 same(p['capture_started_at_utc'],cd['capture_started_at_utc']);same(p['capture_completed_at_utc'],cd['observed_at_utc']);same(ca['capture_started_at_utc'],cd['capture_started_at_utc']);same(ca['observed_at_utc'],cd['observed_at_utc']);same(p['conservative_close_utc'],close.isoformat());same(p['conservative_deadline_utc'],deadline.isoformat())
 cs,ce,ws,we,pc=map(utc,(p['capture_started_at_utc'],p['capture_completed_at_utc'],p['writer_started_at_utc'],p['writer_completed_at_utc'],r['publication_check_at_utc']));need(close<=cs<=ce<=ws<=we<=pc,'Saved clock order');same(p['timing_classification'],'LATE_OBSERVATION'if we>=deadline else'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW');same(r['timing_classification'],'LATE_OBSERVATION'if pc>=deadline else p['timing_classification']);same(a['counts']['timing_classification'],r['timing_classification']);same(r['publication_time_role'],'AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE')
 same(ca['status_observed'],inner['status']);need(type(inner['classifications'])is list and len(inner['classifications'])==1,'One capture classification');classification=inner['classifications'][0]
 for k,v in dict(session=session,classification='TIMELINESS_REVIEW_CANDIDATE_ONLY'if ce<deadline else'MISSED_SEAL_DEADLINE',capture_started_at_utc=cd['capture_started_at_utc'],observed_at_utc=cd['observed_at_utc'],conservative_close_utc=close.isoformat(),conservative_next_weekday_open_utc=deadline.isoformat()).items():same(classification[k],v)
 same(inner['timeliness_candidate'],classification if ce<deadline else None);same(ca['candidate'],inner['timeliness_candidate'])
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
 expected=dict(schema='FIRST_PERSISTED_OBSERVATION_CANDIDATE_CALENDAR_SNAPSHOT_EVIDENCE_V1',adapter_schema=br['schema'],original_source_claims_preserved=deepcopy(cd['source_hashes']),snapshot_equivalence_bridge=br,current_live_cache_reopened=False,full_transitive_source_closure_reverified=False,policy_id=POLICY,status='BLOCKED'if reasons else'CONDITIONAL_CALENDAR_PREREQUISITES_ONLY',calendar_prerequisites_conditionally_satisfied=not reasons,reasons=reasons,lineage_blockers=['SEAL_STATUS_EVENT_HISTORY_NOT_BOUND','NEW_CANDIDATE_GENERATOR_AND_COHORT_CONSUMER_NOT_BOUND'],known_typed_rows_preserved=rows,parent_attempt_inventory_preserved=attempts,selected_observation_id=p['observation_id'],selected_existing_row=selected,selected_compact_entry=e,first_actual_observed_session_by_month=months,monthly_coordinate=monthly,original_seal_status=selected['seal_status'],later_observed_sessions=[x['session']for x in rows[pos+1:]if x['kind']!='MISSED_OBSERVATION'],input_references=dict(refs,tzif=tzref),timing=dict(capture_start=p['capture_started_at_utc'],capture_end=p['capture_completed_at_utc'],writer_start=p['writer_started_at_utc'],writer_end=p['writer_completed_at_utc'],publication_check=r['publication_check_at_utc'],publication_time_role=r['publication_time_role'],seal_evaluation_at_utc=evaluation,conservative_close_utc=close.isoformat(),conservative_deadline_utc=deadline.isoformat()),source_hash_claims=source_claims,scope='STRUCTURAL_REFERENCE_AND_CONDITIONAL_CLOCK_CHECKS_NOT_BYTE_AUTHENTICATION_OR_SEAL_AUTHORITY',**dict.fromkeys(FALSE[:18],False))
 core_ref=reference(str(CORE),CORE_SHA)
 same(started,dict(schema='FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_STARTED_V1',input_references=refs,core_reference=core_ref,source_hashes=base,started_at_utc=started['started_at_utc'],retry_allowed=False,**dict.fromkeys(FALSE,False)),'Complete started record')
 expected_result=dict(schema='SOURCE_BOUND_FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_V1',adapter_schema=br['schema'],original_source_claims_preserved=deepcopy(cd['source_hashes']),snapshot_equivalence_bridge=br,current_live_cache_reopened=False,full_transitive_source_closure_reverified=False,evidence=expected,input_references=refs,core_reference=core_ref,source_hashes=base,started_reference=started_ref,evaluation_at_utc=evaluation,evaluation_clock_read_by_runner=True,external_clock_attestation_verified=False,evaluation_time_role='BEFORE_CONDITIONAL_EVALUATION_NOT_ACTUAL_SEAL_OR_FINAL_DURABLE_COMPLETION',**dict.fromkeys(FALSE,False));same(result,expected_result,'Complete independent result')
 same(pub,dict(schema='FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_PUBLICATION_V1',adapter_schema=br['schema'],original_source_claims_preserved=deepcopy(cd['source_hashes']),snapshot_equivalence_bridge=br,current_live_cache_reopened=False,full_transitive_source_closure_reverified=False,status='PUBLISHED_CONDITIONAL_EVIDENCE_NOT_SEAL_AUTHORITY',result_reference=result_ref,source_hashes=base,**dict.fromkeys(FALSE,False)),'Complete publication')
 for path,hs in source_claims.items():associated(base,reference(path,hs))
 return dict(typed_row_count=len(rows),observed_count=len(rows)-5,gap_count=5,observation_count=len(entries),selected_sequence=pos+1,monthly_coordinate=monthly,status=expected['status'],reason_count=len(reasons))

def readback(*,execute=False):
 need(execute is True,'Explicit execute');result_ref=reference(str(PARENT/'result.json'),RESULT_SHA);pub_ref=reference(str(PARENT/'publication.json'),PUBLICATION_SHA)
 refs=dict(genesis=configured(GENESIS_BOUND,ROLES),history=configured(HISTORY_BOUND,ROLES),observation=configured(OBSERVATION_BOUND,OBS_ROLES),capture=configured(CAPTURE_BOUND,ROLES));base={};merge(base,reference(str(PRODUCER),PRODUCER_SHA));merge(base,reference(str(CORE),CORE_SHA));docs={}
 for kind,rr in refs.items():
  env=dict(rr)
  for k in rr:merge(base,rr[k])
  pairs=(('payload_reference','payload'),('receipt_reference','receipt'),('audit_reference','audit'))if kind=='observation'else(('reference','document'),('publication_reference','publication'),('readback_reference','readback'))
  for role,key in pairs:
   env[key]=decode(load(rr[role],base))
   if kind!='capture'or key=='readback':claims(base,env[key])
  if kind=='genesis':env['baseline_references']=deepcopy(env['readback']['baseline_references'])
  load(rr['reader_reference'],base);docs[kind]=env
 br=bridge(docs['capture']);excluded={x['original_current_reference']['path']for x in br['rows']}
 for path,hs in docs['capture']['document']['source_hashes'].items():
  if path not in excluded:merge(base,reference(path,hs))
 for row in br['rows']:load(row['snapshot_reference'],base)
 tz=load(docs['capture']['document']['captured_artifacts']['tzif'],base);guard(base);sources=dict(base);result=decode(load(result_ref,sources));pub=decode(load(pub_ref,sources));started_ref=result['started_reference'];same(started_ref['path'],str(PARENT/'started.json'));started=decode(load(started_ref,sources));same(sorted(x.name for x in PARENT.iterdir()),['publication.json','result.json','started.json']);merge(sources,reference(str(SOURCE),LOADED));need(not OUTPUT.exists(),'Create-only no retry');need(shutil.disk_usage(OUTPUT.anchor).free>=5*1024**3,'Resource stop');OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  counts=inspect(docs,tz,result,pub,started,refs,result_ref,started_ref,base);guard(sources)
  report=dict(schema='FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_INDEPENDENT_READBACK_V1',status='PASS',result_reference=result_ref,publication_reference=pub_ref,started_reference=started_ref,input_references=refs,reader_sha256=LOADED,source_hashes=sources,counts=counts,producer_or_core_called=False,prior_audit_repeated=False,external_clock_authenticated=False,**dict.fromkeys(FALSE,False));raw=enc(report);need(shutil.disk_usage(OUTPUT.anchor).free>=5*1024**3+len(raw),'Resource stop');path=OUTPUT/'independent_readback.json'
  with path.open('xb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
  guard(sources);same(sorted(x.name for x in PARENT.iterdir()),['publication.json','result.json','started.json']);need(path.read_bytes()==raw,'Saved report bytes');same(sorted(x.name for x in OUTPUT.iterdir()),['independent_readback.json']);return reference(str(path),sha(raw))
 except BaseException as error:
  with(OUTPUT/'failure.json').open('xb')as f:f.write(enc(dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),retry_allowed=False)));f.flush();os.fsync(f.fileno())
  raise
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=parser.parse_args().execute)))
