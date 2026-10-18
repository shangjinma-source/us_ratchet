"""Variable-prefix capture requirements, not an observation receipt or timeliness proof."""
from copy import deepcopy
from datetime import date,datetime,time,timezone
from hashlib import sha256
from io import BytesIO
import json
from zoneinfo import ZoneInfo
from backtest.ndx_forward_source_capture_scoped_research import scoped_csv

SCOPED_PARSER_SHA256='9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee'
PARSER_DEPENDENCY_SHA256='30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'
POLICY='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
FLAGS=dict.fromkeys(('source_authenticity_verified','parent_history_authenticated_by_this_module','clock_authenticity_verified','timeliness_verified','filesystem_attempt_inventory_authenticated','observation_created','candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','future_independent_oos','production_generator_authorized','partial_recovery_performed','missed_events_created'),False)

def require(ok,message):
    if not ok:raise ValueError(message)
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b):require(encoded(a)==encoded(b),'Exact value/type mismatch')
def digest(b):return sha256(b).hexdigest()
def ref(r):
    require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and r['path']and r['path'].strip()==r['path'],'Reference path')
    h=r['sha256'];require(type(h)is str and len(h)==64 and all(c in '0123456789abcdef'for c in h),'Reference hash');return r
def merge(s,r):
    ref(r);require(r['path']not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def claims(s,obj):
    require(type(obj['source_hashes'])is dict,'Source claims')
    for p,h in obj['source_hashes'].items():merge(s,dict(path=p,sha256=h))
def integer(x,n):require(type(x)is int and x==n,'Exact count')
def utc(s):
    require(type(s)is str,'UTC timestamp');v=datetime.fromisoformat(s.replace('Z','+00:00'));require(v.tzinfo is not None and v.utcoffset().total_seconds()==0,'Explicit UTC');return v

def inspect_parent(parent):
    s={}
    for k in ('reference','publication_reference','readback_reference','reader_reference'):merge(s,parent[k])
    h,p,a=parent['document'],parent['publication'],parent['readback']
    exact(h['schema'],'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2');exact(h['policy_id'],POLICY)
    exact(p['schema'],'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2');exact(p['status'],'PUBLISHED_OBSERVATION_HISTORY_NO_SEAL')
    exact(a['schema'],'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V2');exact(a['status'],'PASS')
    for o in (p,a):exact(o['history_reference'],parent['reference'])
    exact(a['publication_reference'],parent['publication_reference']);exact(a['reader_sha256'],parent['reader_reference']['sha256']);exact(h['source_hashes'],p['source_hashes'])
    for o in (h,p,a):
        claims(s,o)
        for k in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'):require(o[k]is False,'Parent authority')
    for path,hsh in h['source_hashes'].items():require(a['source_hashes'].get(path)==hsh,'Audit complete history source association')
    for k in ('reference','publication_reference','reader_reference'):
        r=parent[k];require(a['source_hashes'].get(r['path'])==r['sha256'],'Audit reference association')
    known=h['known_typed_rows'];require(type(known)is list and 66<=len(known)<20000,'Actual compact history prefix')
    months={};days=[]
    for i,row in enumerate(known):
        integer(row['sequence'],i+1);d=row['session'];require(type(d)is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5 and (not days or d>days[-1]),'Ordered weekday prefix');days.append(d)
        require(row['kind']in ('SEALED_PARENT_OBSERVED_SESSION','MISSED_OBSERVATION','PROSPECTIVE_OBSERVED_SESSION'),'Typed row')
        require(row['seal_status']in ('SEALED','NOT_ATTEMPTED','FAILED','UNKNOWN'),'Seal state')
        if row['kind']=='MISSED_OBSERVATION':exact(row['seal_status'],'NOT_ATTEMPTED')
        else:months.setdefault(d[:7],d)
    genesis=h['genesis_preserved']['document']['projection_inputs']['known_rows'];integer(len(genesis),65);exact(known[:65],genesis)
    integer(sum(r['kind']=='MISSED_OBSERVATION'for r in genesis),5);integer(sum(r['kind']=='SEALED_PARENT_OBSERVED_SESSION'for r in genesis),60)
    observations=h['observations'];attempts=h['parent_attempt_inventory'];require(type(observations)is list and type(attempts)is list,'Complete inventory')
    integer(len(observations),len(known)-65);integer(h['observation_count'],len(observations));integer(len(attempts),len(observations))
    seen=set()
    for i,(e,attempt)in enumerate(zip(observations,attempts)):
        exact(e['schema'],'COMPACT_OBSERVATION_REFERENCE_ENTRY_V1');require(e['original_payload_embedded']is False and not any(k in e for k in ('payload','receipt','audit','base64','original_csv_bytes_base64')),'Compact entries only')
        integer(e['sequence'],66+i);exact(e['session'],known[65+i]['session']);exact(known[65+i]['kind'],'PROSPECTIVE_OBSERVED_SESSION')
        require(e['observation_id']not in seen,'Duplicate observation');seen.add(e['observation_id']);exact(e['observation_id'],digest(encoded(e['observation_identity'])))
        exact(attempt,dict(observation_id=e['observation_id'],session=e['session'],status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',payload_reference=e['payload_reference'],receipt_reference=e['receipt_reference'],independent_readback_reference=e['audit_reference']))
        exact(known[65+i]['evidence_reference'],dict(e['payload_reference'],json_pointer='/observation_identity'))
    exact(h['last_accounted_session'],days[-1]);exact(h['first_actual_observed_session_by_month'],months)
    integer(a['counts']['typed_row_count'],len(known));integer(a['counts']['observation_count'],len(observations));integer(a['counts']['new_observation_count'],1);exact(a['counts']['first_actual_observed_session_by_month'],months)
    baseline=h['baseline_references'];exact(sorted(baseline),['QQQ','SPY']);exact(baseline,observations[-1]['captured_baseline_references'])
    for r in baseline.values():merge(s,r);require(a['source_hashes'].get(r['path'])==r['sha256'],'Audited latest baseline')
    return h,days,months,s

def plan_history_capture(*,parent,source_bytes,source_references,baseline_bytes,capture_started_at,capture_completed_at,tzif_bytes,tzif_reference):
    """Consume full parent envelope; retain only compact metadata and byte references."""
    h,days,months,s=inspect_parent(parent)
    for v in (source_bytes,source_references,baseline_bytes):require(type(v)is dict and set(v)=={'QQQ','SPY'},'Exact source pair')
    started,finished=utc(capture_started_at),utc(capture_completed_at);require(started<=finished,'Capture clock reversed')
    ref(tzif_reference);require(type(tzif_bytes)is bytes and 0<len(tzif_bytes)<=100000 and digest(tzif_bytes)==tzif_reference['sha256'],'TZif bytes');zone=ZoneInfo.from_file(BytesIO(tzif_bytes),key='America/New_York');merge(s,tzif_reference)
    diagnostics=[];evidence={};new_dates={}
    for ticker in ('QQQ','SPY'):
        current=ref(source_references[ticker]);baseline=h['baseline_references'][ticker]
        for raw,r in ((source_bytes[ticker],current),(baseline_bytes[ticker],baseline)):
            require(type(raw)is bytes and digest(raw)==r['sha256'],'Supplied byte SHA mismatch');merge(s,r)
        _,old=scoped_csv(baseline_bytes[ticker],days[0]);_,new=scoped_csv(source_bytes[ticker],days[0])
        original_prefix=[v['raw_csv_row']for v in new['original_rows'][:len(old['original_rows'])]]
        if original_prefix!=[v['raw_csv_row']for v in old['original_rows']]:diagnostics.append(dict(ticker=ticker,reason='FULL_ORIGINAL_PREFIX_CHANGED'))
        oldrows=[v for v in old['original_rows']if v['included_in_scoped_csv']];newrows=[v for v in new['original_rows']if v['included_in_scoped_csv']]
        if [v['session']for v in oldrows]!=days:diagnostics.append(dict(ticker=ticker,reason='BASELINE_NOT_EXACT_ACCOUNTED_PREFIX'))
        prior=[v for v in newrows if v['session']<=days[-1]]
        if [v['session']for v in prior]!=days:diagnostics.append(dict(ticker=ticker,reason='SOURCE_PARENT_PREFIX_MISSING_OR_EXTRA'))
        oldby={v['session']:v for v in oldrows};revised=[v['session']for v in prior if v['session']in oldby and v['raw_csv_row']!=oldby[v['session']]['raw_csv_row']]
        if revised:diagnostics.append(dict(ticker=ticker,reason='PARENT_SOURCE_REVISION',sessions=revised))
        new_dates[ticker]=[v['session']for v in newrows if v['session']>days[-1]]
        evidence[ticker]=dict(source_reference=deepcopy(current),baseline_reference=deepcopy(baseline),original_byte_count=new['original_byte_count'],original_row_count=new['original_row_count'],baseline_row_count=old['original_row_count'],excluded_before_scope_ohlc_diagnostics=new['excluded_before_scope_ohlc_diagnostics'],baseline_excluded_before_scope_ohlc_diagnostics=old['excluded_before_scope_ohlc_diagnostics'],new_session_dates=new_dates[ticker])
    if new_dates['QQQ']!=new_dates['SPY']:diagnostics.append(dict(reason='SOURCE_NEW_DATES_DISAGREE'))
    if any(len(v)>1 for v in new_dates.values()):diagnostics.append(dict(reason='MULTIPLE_UNACCOUNTED_SESSIONS'))
    candidate=new_dates['QQQ'][0]if not diagnostics and len(new_dates['QQQ'])==1 else None
    if candidate:
        close=datetime.combine(date.fromisoformat(candidate),time(16),tzinfo=zone).astimezone(timezone.utc)
        if started<close:
            diagnostics.append(dict(reason='CAPTURE_NOT_ENTIRELY_AFTER_CONSERVATIVE_CLOSE'));candidate=None
    return dict(schema='COMPACT_HISTORY_VARIABLE_PREFIX_CAPTURE_PLAN_V1',status='BLOCKED_SOURCE_DIAGNOSTICS'if diagnostics else ('ONE_NEW_SESSION_CANDIDATE_NOT_OBSERVED'if candidate else 'NO_NEW_SESSION'),parent_history_reference=deepcopy(parent['reference']),parent_publication_reference=deepcopy(parent['publication_reference']),parent_readback_reference=deepcopy(parent['readback_reference']),known_typed_rows_preserved=deepcopy(h['known_typed_rows']),parent_attempt_inventory_preserved=deepcopy(h['parent_attempt_inventory']),baseline_references=deepcopy(h['baseline_references']),source_evidence=evidence,source_reference_claims=s,scope_start=days[0],last_accounted_session=days[-1],candidate_session=candidate,candidate_sequence=len(days)+1 if candidate else None,first_actual_observed_session_by_month_preserved=months,proposed_first_actual_session_of_month=months.get(candidate[:7],candidate)if candidate else None,capture_started_at=capture_started_at,capture_completed_at=capture_completed_at,capture_completed_new_york=finished.astimezone(zone).isoformat(),capture_calendar_day_lag=(finished.astimezone(zone).date()-date.fromisoformat(candidate)).days if candidate else None,timing_role='AFTER_CONSERVATIVE_1600_CLOSE_ONLY_NOT_DEADLINE_OR_TIMELY_RECEIPT_CERTIFICATION',tzif_reference=deepcopy(tzif_reference),diagnostics=diagnostics,raw_bytes_embedded=False,authentication_role='CALLER_SUPPLIED_HISTORY_AUDIT_ASSERTIONS_NOT_FILE_AUTHENTICATION',**FLAGS)
