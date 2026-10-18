"""Gap-aware conditional calendar evidence; never a persisted observation receipt."""
from copy import deepcopy
from datetime import date,datetime,time,timedelta,timezone
from io import BytesIO
from zoneinfo import ZoneInfo
import hashlib
import json

POLICY='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
FLAGS=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','oos_recovery_completed','source_evidence_authenticated','observation_receipt_authenticated','authentic_clock_verified','exchange_holidays_verified','early_closes_verified','old_calendar_mutated','old_generator_called','new_observation_receipt_created','production_lineage_ready'),False)

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def day(value):
    require(type(value) is str,'Date required');d=date.fromisoformat(value);require(d.isoformat()==value and d.weekday()<5,'Canonical weekday date');return d
def utc(value):
    require(type(value) is str,'Explicit UTC required');d=datetime.fromisoformat(value);require(d.tzinfo is not None and d.utcoffset()==timedelta(0),'Aware UTC required');return d
def ref(value,claims,pointer=False):
    require(type(value) is dict and {'path','sha256'}<=set(value),'Reference required');p=value['path'];h=value['sha256']
    require(type(p) is str and p and p==p.strip() and type(h) is str and len(h)==64 and all(c in '0123456789abcdef' for c in h),'Reference fields')
    require(p not in claims or claims[p]==h,'Conflicting source SHA');claims[p]=h
    if pointer:
        q=value.get('json_pointer');require(type(q) is str and q.startswith('/') and len(q)>1,'Explicit row pointer')
        require(all('~' not in part.replace('~0','').replace('~1','') for part in q.split('/')[1:]),'Pointer escapes')

def prepare_candidate_calendar_evidence(*,policy_id,known_typed_rows,new_observation_evidence,decision_session,capture_reference,clock_evidence,source_references):
    """Research future-row assertions remain unauthenticated even if every gate passes.

    The source-bound current wrapper never supplies new observations. A future
    production receipt writer/verifier is an independent, still absent contract.
    """
    require(policy_id==POLICY and type(policy_id) is str,'Explicit first-actual policy')
    require(type(known_typed_rows) is list and known_typed_rows and type(new_observation_evidence) is list and len(known_typed_rows)+len(new_observation_evidence)<=20000,'Complete bounded typed prefix')
    claims={};ref(capture_reference,claims);ref(source_references['coverage_reference'],claims)
    for r in source_references['references']:ref(r,claims)
    tzif=clock_evidence['tzif_bytes'];require(type(tzif) is bytes and 0<len(tzif)<1024*1024,'Bounded TZif bytes');ref(clock_evidence['tzif_reference'],claims);require(sha(tzif)==clock_evidence['tzif_reference']['sha256'],'Consumed TZif SHA')
    zone=ZoneInfo.from_file(BytesIO(tzif),key='America/New_York')
    seal_clock=clock_evidence['seal_evaluation_at_utc'];seal_at=None if seal_clock is None else utc(seal_clock)
    combined=deepcopy(known_typed_rows);new_by={}
    for evidence in new_observation_evidence:
        require(evidence['evidence_kind']=='RESEARCH_SUPPLIED_OBSERVATION_NOT_AUTHENTICATED','No fake production receipt schema')
        row=evidence['typed_row'];require(row['kind']=='PROSPECTIVE_OBSERVED_SESSION','Only explicit observed assertions in new list')
        ref(evidence['capture_reference'],claims);ref(evidence['observation_reference'],claims,True);exact(row['evidence_reference'],evidence['observation_reference'],'Observed row evidence pointer')
        start=utc(evidence['capture_started_at_utc']);end=utc(evidence['capture_completed_at_utc']);require(start<=end,'Ordered capture interval')
        require(set(evidence['source_rows'])=={'QQQ','SPY'},'Both original observation rows')
        for t,r in evidence['source_rows'].items():
            require(type(r) is dict and set(r)=={'Date','Open','High','Low','Close','Volume'} and all(type(v) is str and v for v in r.values()) and r['Date']==row['session'],'Complete same-date original QQQ/SPY row')
        require(row['session'] not in new_by,'Duplicate new observation');new_by[row['session']]=deepcopy(evidence);combined.append(deepcopy(row))
    months={};projection=[];previous='';pointers=set()
    for i,row in enumerate(combined):
        require(type(row) is dict and set(row)=={'sequence','session','kind','evidence_reference','seal_status'},'Independent typed row schema')
        require(type(row['sequence']) is int and row['sequence']==i+1,'Typed sequence is consecutive and not old ledger sequence');day(row['session']);require(row['session']>previous,'Ascending unique full prefix');previous=row['session']
        require(row['kind'] in ('SEALED_PARENT_OBSERVED_SESSION','MISSED_OBSERVATION','PROSPECTIVE_OBSERVED_SESSION') and type(row['kind']) is str,'Typed kind, not old-v2 origin')
        require(type(row['seal_status']) is str and row['seal_status'] in ('UNKNOWN','NOT_ATTEMPTED','FAILED','SEALED'),'Explicit original seal state')
        gap=row['kind']=='MISSED_OBSERVATION';require(not gap or row['seal_status']=='NOT_ATTEMPTED','Gap cannot be sealed')
        ref(row['evidence_reference'],claims,True);identity=tuple(row['evidence_reference'][k] for k in ('path','sha256','json_pointer'));require(identity not in pointers,'Duplicate evidence row pointer');pointers.add(identity)
        month=months.setdefault(row['session'][:7],dict(month=row['session'][:7],first_observed_session=None,observed_count=0,missed_count=0))
        first=not gap and month['first_observed_session'] is None
        if gap:month['missed_count']+=1
        else:
            month['observed_count']+=1
            if first:month['first_observed_session']=row['session']
        projection.append(dict(input_row=deepcopy(row),monthly_coordinate=first,first_actual_observed_session=month['first_observed_session'],seal_outcome_used_to_select_coordinate=False))
    source_dates=source_references['complete_source_session_dates'];require(type(source_dates) is dict and set(source_dates)=={'QQQ','SPY'},'Full source dates, not just intersection')
    known_dates=[r['session'] for r in known_typed_rows];all_dates=[r['session'] for r in combined]
    for ticker,values in source_dates.items():
        require(type(values) is list and len(values)<=20000 and values==sorted(set(values)),'Source dates ordered unique')
        for d in values:day(d)
        require(values[:len(known_dates)]==known_dates,'Each source preserves entire known typed prefix')
    require(type(source_references['revisions']) is list,'Explicit retained revisions')
    symmetric=source_dates['QQQ']==source_dates['SPY'];coverage=symmetric and source_dates['QQQ']==all_dates
    reasons=[]
    if not symmetric:reasons.append('SOURCE_SUFFIX_ASYMMETRY')
    if not coverage:reasons.append('UNACCOUNTED_SOURCE_DATES_OR_MISSING_OBSERVATION_ROWS')
    if source_references['revisions']:reasons.append('SOURCE_REVISION_REQUIRES_ADJUDICATION')
    if not new_observation_evidence:reasons.append('NO_NEW_OBSERVATION_EVIDENCE')
    decision=None;timing=None;monthly=None;evidence_status='NO_NEW_OBSERVATION_EVIDENCE';sealstatus=None
    if decision_session is not None:
        day(decision_session);require(decision_session>='2026-10-01','No retrospective preactivation candidate')
        matching=[r for r in projection if r['input_row']['session']==decision_session]
        if not matching or decision_session not in new_by:reasons.append('DECISION_HAS_NO_NEW_OBSERVATION_RECEIPT')
        else:
            decision=matching[0];monthly=decision['monthly_coordinate'];ev=new_by[decision_session];evidence_status='RESEARCH_SUPPLIED_NOT_PRODUCTION_AUTHENTICATED';sealstatus=decision['input_row']['seal_status']
            if not monthly:reasons.append('NOT_FIRST_ACTUAL_OBSERVATION_OF_MONTH')
            if sealstatus!='NOT_ATTEMPTED':reasons.append('PRIOR_SEAL_STATE_DOES_NOT_AUTHORIZE_NEW_ATTEMPT')
            if any(d>decision_session for d in all_dates) or any(d>decision_session for values in source_dates.values() for d in values):reasons.append('LATER_KNOWN_SESSION_NO_BACKFILL')
            session=day(decision_session);close=datetime.combine(session,time(16),zone).astimezone(timezone.utc);following=session+timedelta(days=1)
            while following.weekday()>=5:following+=timedelta(days=1)
            deadline=datetime.combine(following,time(9,30),zone).astimezone(timezone.utc);start=utc(ev['capture_started_at_utc']);end=utc(ev['capture_completed_at_utc'])
            capturetimely=close<=start<=end<deadline;sealtimely=seal_at is not None and close<=end<=seal_at<deadline
            if not capturetimely:reasons.append('CAPTURE_INTERVAL_OUTSIDE_CONSERVATIVE_WINDOW')
            if seal_at is None:reasons.append('SEAL_CLOCK_NOT_SUPPLIED_RECHECK_AT_ACTUAL_SEAL')
            elif not sealtimely:reasons.append('SEAL_EVALUATION_OUTSIDE_CONSERVATIVE_WINDOW')
            timing=dict(capture_started_at_utc=ev['capture_started_at_utc'],capture_completed_at_utc=ev['capture_completed_at_utc'],conservative_close_utc=close.isoformat(),conservative_next_weekday_open_utc=deadline.isoformat(),seal_evaluation_at_utc=seal_clock,capture_interval_conditionally_timely=capturetimely,seal_clock_conditionally_timely=sealtimely,timezone_rules_sha256=sha(tzif),conservative_regular_16_close_not_exchange_holiday_or_early_close_certification=True)
    else:reasons.append('NO_DECISION_REQUESTED')
    satisfied=decision is not None and not reasons
    return dict(schema='GAP_AWARE_CANDIDATE_CALENDAR_EVIDENCE_V1',policy_id=POLICY,status='CONDITIONAL_RESEARCH_PREREQUISITES_ONLY' if satisfied else 'BLOCKED',known_typed_rows_preserved=deepcopy(known_typed_rows),complete_typed_rows=combined,projection=projection,months=list(months.values()),new_observation_evidence_preserved=deepcopy(new_observation_evidence),decision_session=decision_session,monthly_coordinate=monthly,observation_evidence_status=evidence_status,timing_status=timing,source_revision_status='UNCHANGED_SAVED_ROWS' if not source_references['revisions'] else 'UNRESOLVED_REVISION',lineage_status='NEW_RESEARCH_SCHEMA_INCOMPATIBLE_WITH_OLD_V2_V3_PRODUCTION_LOADERS',reasons=reasons,selected_row=deepcopy(decision['input_row']) if satisfied else None,original_seal_status=sealstatus,calendar_prerequisites_conditionally_satisfied=satisfied,capture_reference=deepcopy(capture_reference),source_references_preserved=deepcopy(source_references),clock_evidence_preserved={k:deepcopy(v) for k,v in clock_evidence.items() if k!='tzif_bytes'},source_hash_claims=claims,production_receipt_contract='NOT_DEFINED_THIS_MODULE_DOES_NOT_CREATE_ONE',**FLAGS)
