"""Pure observation payload preparation. No receipt is published by this module."""
import base64,csv,hashlib,io,json
from copy import deepcopy
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

FLAGS=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','source_authenticity_verified','clock_authenticity_verified','parent_attempt_inventory_completeness_verified','receipt_published','old_calendar_mutated','exchange_holidays_verified','early_closes_verified','production_generator_authorized'),False)
FIELDS=['Date','Open','High','Low','Close','Volume']
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def reference(r,claims):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'] and r['path']==r['path'].strip() and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Explicit external byte reference')
    require(r['path'] not in claims or claims[r['path']]==r['sha256'],'Conflicting reference');claims[r['path']]=r['sha256']
def utc(v):
    require(type(v) is str,'Explicit UTC');d=datetime.fromisoformat(v);require(d.tzinfo is not None and d.utcoffset()==timedelta(0),'Aware UTC');return d
def day(v):
    require(type(v) is str,'Explicit date');d=date.fromisoformat(v);require(d.isoformat()==v and d.weekday()<5,'Canonical weekday session');return d
def csv_rows(item,claims,scope_start):
    reference(item['reference'],claims);b=item['bytes'];require(type(b) is bytes and 0<len(b)<=32*1024*1024 and sha(b)==item['reference']['sha256'],'Consumed CSV bytes')
    reader=csv.DictReader(io.StringIO(b.decode('utf-8-sig'),newline=''));require(reader.fieldnames==FIELDS,'Exact CSV fields');rows=list(reader);require(0<len(rows)<=20000,'Bounded nonempty source rows')
    previous='';diagnostics=[]
    for row_index,row in enumerate(rows):
        require(set(row)==set(FIELDS) and all(type(v) is str and v for v in row.values()),'Complete original row');day(row['Date']);require(row['Date']>previous,'Unique ascending original dates');previous=row['Date']
        numbers={}
        for f in FIELDS[1:]:
            require(len(row[f])<=180,'Bounded numeric scalar');n=Decimal(row[f]);require(n.is_finite() and abs(n.as_tuple().exponent)<=160,'Finite numeric scalar');numbers[f]=n
        valid=all(numbers[f]>0 for f in ('Open','High','Low','Close')) and numbers['Low']<=min(numbers['Open'],numbers['Close'])<=max(numbers['Open'],numbers['Close'])<=numbers['High']
        if row['Date']>=scope_start:require(valid,'Complete internally consistent required OHLC')
        elif not valid:diagnostics.append(dict(original_data_row_index=row_index,session=row['Date'],issue='OUTSIDE_REQUIRED_SCOPE_OHLC_INCONSISTENCY',raw_row=deepcopy(row)))
        require(numbers['Volume']>=0 and numbers['Volume']==numbers['Volume'].to_integral_value(),'Nonnegative integer volume')
    return rows,diagnostics

def prepare_observation_payload(*,parent_reference,parent_readback_reference,known_typed_rows,parent_attempt_inventory,capture,session,writer_started_at_utc,writer_completed_at_utc):
    claims={};reference(parent_reference,claims);reference(parent_readback_reference,claims);reference(capture['reference'],claims)
    require(type(known_typed_rows) is list and 0<len(known_typed_rows)<20000,'Entire typed parent prefix');known=[];first={}
    for i,row in enumerate(known_typed_rows):
        d=row['session'];day(d);require(type(row['sequence']) is int and row['sequence']==i+1 and (not known or d>known[-1]),'Complete ordered sequence');known.append(d)
        require(row['kind'] in ('SEALED_PARENT_OBSERVED_SESSION','PROSPECTIVE_OBSERVED_SESSION','MISSED_OBSERVATION'),'Typed kind')
        require(row['seal_status'] in ('UNKNOWN','NOT_ATTEMPTED','FAILED','SEALED'),'Seal state retained')
        if row['kind']=='MISSED_OBSERVATION':require(row['seal_status']=='NOT_ATTEMPTED','Gap not sealed')
        else:first.setdefault(d[:7],d)
        pointer=row['evidence_reference'];reference({k:pointer[k] for k in ('path','sha256')},claims);require(type(pointer['json_pointer']) is str and pointer['json_pointer'].startswith('/') and len(pointer['json_pointer'])>1,'Original row pointer')
    require(type(parent_attempt_inventory) is list,'Explicit attempt inventory even when empty')
    ids=set();attempt_sessions=set()
    for attempt in parent_attempt_inventory:
        identifier=attempt['observation_id'];require(type(identifier) is str and len(identifier)==64 and all(c in '0123456789abcdef' for c in identifier) and identifier not in ids,'Unique attempt ID');ids.add(identifier)
        require(attempt['status']=='PERSISTED_AND_INDEPENDENTLY_READ_BACK','Partial attempt must be resolved before another observation')
        for k in ('payload_reference','receipt_reference','independent_readback_reference'):reference(attempt[k],claims)
        require(attempt['session'] in known and known_typed_rows[known.index(attempt['session'])]['kind']=='PROSPECTIVE_OBSERVED_SESSION','Completed attempts included in parent, never skipped')
        require(attempt['session'] not in attempt_sessions,'One persisted observation per session');attempt_sessions.add(attempt['session'])
        pointer=known_typed_rows[known.index(attempt['session'])]['evidence_reference'];exact(attempt['payload_reference'],{k:pointer[k] for k in ('path','sha256')},'Parent observation payload identity')
    require(attempt_sessions=={r['session'] for r in known_typed_rows if r['kind']=='PROSPECTIVE_OBSERVED_SESSION'},'Every new-schema parent observation has resolved receipt and readback')
    d=day(session);require(session>known[-1],'Exactly subsequent explicit observation')
    require(set(capture['sources'])==set(capture['baseline_sources'])=={'QQQ','SPY'},'Both full sources, never intersection')
    originals={};selected={};projections={}
    for ticker in ('QQQ','SPY'):
        current,current_diagnostics=csv_rows(capture['sources'][ticker],claims,known[0]);baseline,baseline_diagnostics=csv_rows(capture['baseline_sources'][ticker],claims,known[0])
        baseline_scope=[r for r in baseline if r['Date']>=known[0]];current_scope=[r for r in current if r['Date']>=known[0]]
        require([r['Date'] for r in baseline_scope]==known,'Baseline exact accounted prefix')
        require([r['Date'] for r in current_scope]==known+[session],'Exactly one new date and complete symmetric sources')
        exact(current[:len(baseline)],baseline,'Original prefix bytes interpreted rows cannot be revised or dropped')
        require(len(current)==len(baseline)+1,'No hidden new rows outside scope')
        selected[ticker]=deepcopy(current[-1]);projections[ticker]=dict(original_data_row_index=len(current)-1,reference=deepcopy(capture['sources'][ticker]['reference']))
        originals[ticker]={role:dict(reference=deepcopy(capture[role][ticker]['reference']),original_csv_bytes_base64=base64.b64encode(capture[role][ticker]['bytes']).decode(),rows=deepcopy(values),required_scope_start=known[0],outside_required_scope_diagnostics=deepcopy(current_diagnostics if role=='sources' else baseline_diagnostics)) for role,values in (('sources',current),('baseline_sources',baseline))}
    tz=capture['tzif'];reference(tz['reference'],claims);require(type(tz['bytes']) is bytes and len(tz['bytes'])<1024*1024 and sha(tz['bytes'])==tz['reference']['sha256'],'Bound TZif bytes')
    zone=ZoneInfo.from_file(io.BytesIO(tz['bytes']),key='America/New_York');close=datetime.combine(d,time(16),zone).astimezone(timezone.utc);following=d+timedelta(days=1)
    while following.weekday()>=5:following+=timedelta(days=1)
    deadline=datetime.combine(following,time(9,30),zone).astimezone(timezone.utc)
    start=utc(capture['started_at_utc']);end=utc(capture['completed_at_utc']);ws=utc(writer_started_at_utc);we=utc(writer_completed_at_utc)
    require(close<=start<=end<=ws<=we,'Capture after close; real writer interval cannot be backdated')
    late=not (end<deadline and we<deadline);coordinate=first.get(session[:7],session)==session
    identity=dict(parent_reference=deepcopy(parent_reference),capture_reference=deepcopy(capture['reference']),session=session)
    return dict(schema='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1',observation_id=sha(encoded(identity)),observation_identity=identity,session=session,sequence=len(known)+1,kind='PROSPECTIVE_OBSERVED_SESSION',initial_seal_status='NOT_ATTEMPTED',month_first_actual_observation=coordinate,first_actual_observed_session_of_month=first.get(session[:7],session),timing_classification='LATE_OBSERVATION' if late else 'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW',capture_started_at_utc=capture['started_at_utc'],capture_completed_at_utc=capture['completed_at_utc'],writer_started_at_utc=writer_started_at_utc,writer_completed_at_utc=writer_completed_at_utc,conservative_close_utc=close.isoformat(),conservative_deadline_utc=deadline.isoformat(),selected_original_rows=selected,source_row_locations=projections,full_original_sources_preserved=originals,tzif_reference=deepcopy(tz['reference']),tzif_bytes_base64=base64.b64encode(tz['bytes']).decode(),parent_readback_reference=deepcopy(parent_readback_reference),known_typed_rows_preserved=deepcopy(known_typed_rows),parent_attempt_inventory_preserved=deepcopy(parent_attempt_inventory),source_hash_claims=claims,payload_is_not_a_published_observation_receipt=True,seal_status_history_not_created=True,**FLAGS)
