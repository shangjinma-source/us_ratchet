"""Independent receipt evidence inspection. No writer/core import or clock authority."""
import base64,csv,hashlib,io,json,os
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
WRITER=ROOT/'scripts/ndx_prospective_observation_writer_20261003.py';WRITER_SHA='07a2f5dddc2d62ef9efa0f59282207d5d377cb40787ff25eb4e4b421de614adc'
BASE=ROOT/'data/cache/research/prospective_observation_receipt_20261003_v1'
BOUND={'parent':dict(path=str(ROOT/'data/cache/research/gap_monthly_policy_20261002_v1/policy.json'),sha256='d04c7cd9181eb5585c7ddbd880b02947ec135552944a6f90b5e1fd39bb21b946'), 'parent_publication':dict(path=str(ROOT/'data/cache/research/gap_monthly_policy_20261002_v1/publication.json'),sha256='23af1d2798f4c7d5e33142a97319dead34a533606b98304da7b7c9deeb65f76d'), 'parent_readback':dict(path=str(ROOT/'data/cache/research/gap_monthly_policy_history_input_readback_20261003_v1/independent_readback.json'),sha256='f11e5e1722b54724ffccaccb5a2c21ea945cbc9c9d96c458d064e11566833cd6'), 'capture':dict(path=str(ROOT/'data/cache/research/forward_source_capture_oct02_20261003_v1/capture.json'),sha256='a1a2b89c71ba651215cca153ccc6cea8e88a09a7a83949e523efdc5316c95882'), 'capture_publication':dict(path=str(ROOT/'data/cache/research/forward_source_capture_oct02_20261003_v1/publication.json'),sha256='4cea5fddd57b0b1371bf6941f2e7d855890e868a1bb8513fc3994886ab61a82e')}
SESSION='2026-10-02';PARENT_READBACK_SCHEMA='GAP_MONTHLY_POLICY_HISTORY_INPUT_READBACK_V1'
FIELDS=['Date','Open','High','Low','Close','Volume']
PAYLOAD_FALSE=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','source_authenticity_verified','clock_authenticity_verified','parent_attempt_inventory_completeness_verified','receipt_published','old_calendar_mutated','exchange_holidays_verified','early_closes_verified','production_generator_authorized')
WRITER_FALSE=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','old_calendar_mutated','seal_status_event_created','network_capture_performed','production_generator_authorized','full_transitive_source_closure_reverified')
def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def utc(s):
    require(type(s) is str,'UTC string');v=datetime.fromisoformat(s);require(v.tzinfo is not None and v.utcoffset()==timedelta(0),'Aware UTC');return v
def day(s):
    require(type(s) is str,'Date string');v=date.fromisoformat(s);require(v.isoformat()==s and v.weekday()<5,'Canonical weekday');return v
def ref(r,claims):
    require(type(r) is dict and set(r)=={'path','sha256'},'Byte reference');p=r['path'];h=r['sha256']
    require(type(p) is str and p and p==p.strip() and type(h) is str and len(h)==64 and all(c in '0123456789abcdef' for c in h),'Canonical reference')
    require(p not in claims or claims[p]==h,'Conflicting source');claims[p]=h
def parse_csv(blob,start):
    reader=csv.DictReader(io.StringIO(blob.decode('utf-8-sig'),newline=''));require(reader.fieldnames==FIELDS,'CSV header');rows=list(reader);require(0<len(rows)<=20000,'CSV row bound');previous='';diagnostics=[]
    for i,r in enumerate(rows):
        require(set(r)==set(FIELDS) and all(type(x) is str and x for x in r.values()),'Full original row');day(r['Date']);require(r['Date']>previous,'Ascending unique source');previous=r['Date']
        n={}
        for k in FIELDS[1:]:
            require(len(r[k])<=180,'Scalar length');n[k]=Decimal(r[k]);require(n[k].is_finite() and abs(n[k].as_tuple().exponent)<=160,'Finite scalar')
        valid=all(n[k]>0 for k in FIELDS[1:5]) and n['Low']<=min(n['Open'],n['Close'])<=max(n['Open'],n['Close'])<=n['High']
        require(n['Volume']>=0 and n['Volume']==n['Volume'].to_integral_value(),'Integer volume')
        if r['Date']>=start:require(valid,'Required-scope OHLC')
        elif not valid:diagnostics.append(dict(original_data_row_index=i,session=r['Date'],issue='OUTSIDE_REQUIRED_SCOPE_OHLC_INCONSISTENCY',raw_row=r))
    return rows,diagnostics

def inspect(payload,receipt,started,docs,refs,payload_reference,blobs,session):
    """All supplied blobs must come from wrapper-verified external byte references."""
    known=docs['parent']['projection_inputs']['known_rows'];require(type(known) is list and len(known)==65,'Complete65 prefix')
    require(type(docs['parent']['new_observation_count']) is int and docs['parent']['new_observation_count']==0 and docs['parent']['projection_inputs']['new_prospective_observations']==[],'No omitted prospective receipt')
    first={};dates=[];claims={}
    for i,r in enumerate(known):
        day(r['session']);require(type(r['sequence']) is int and r['sequence']==i+1 and (not dates or r['session']>dates[-1]),'Typed sequence');dates.append(r['session'])
        require(r['kind'] in ('SEALED_PARENT_OBSERVED_SESSION','MISSED_OBSERVATION') and r['seal_status'] in ('UNKNOWN','NOT_ATTEMPTED','FAILED','SEALED'),'Original typed state')
        if r['kind']=='MISSED_OBSERVATION':require(r['seal_status']=='NOT_ATTEMPTED','Gap state')
        else:first.setdefault(r['session'][:7],r['session'])
        ref({k:r['evidence_reference'][k] for k in ('path','sha256')},claims)
    require(sum(r['kind']=='SEALED_PARENT_OBSERVED_SESSION' for r in known)==60,'Original60 plus5 gaps')
    d=day(session);require(session>dates[-1],'New unique observation')
    p=docs['parent'];capture=docs['capture'];plan=capture['plan']['capture_plan']
    require(p['schema']=='SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1' and p['policy_id']=='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH','Parent policy')
    exact(plan['accounted_prefix_dates'],dates,'Capture full prefix');exact(plan['new_source_dates'],[session],'Old capture not a new observation');exact(plan['revisions'],[],'No revision')
    exact(capture['input_references']['frontier'],p['frontier_reference'],'Same frontier')
    require(payload['schema']=='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1' and receipt['schema']=='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1' and started['schema']=='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V1','Evidence schemas')
    require(receipt['status']=='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY','Persisted role')
    exact(receipt['payload_reference'],payload_reference,'External payload anchor');exact(payload['known_typed_rows_preserved'],known,'Entire original typed prefix');exact(payload['parent_attempt_inventory_preserved'],[],'First writer only')
    for k in ('parent','parent_readback','capture'):ref(refs[k],claims)
    identity=dict(parent_reference=refs['parent'],capture_reference=refs['capture'],session=session)
    exact(payload['observation_identity'],identity,'Observation identity');identifier=sha(enc(identity));exact(payload['observation_id'],identifier,'Observation digest');exact(receipt['observation_id'],identifier,'Receipt same observation')
    exact(payload['session'],session,'Session');exact(payload['sequence'],66,'Sequence');require(payload['kind']=='PROSPECTIVE_OBSERVED_SESSION' and payload['initial_seal_status']=='NOT_ATTEMPTED','No seal')
    exact(payload['parent_readback_reference'],refs['parent_readback'],'Parent audit')
    require(set(payload['full_original_sources_preserved'])==set(payload['selected_original_rows'])==set(payload['source_row_locations'])=={'QQQ','SPY'},'Two full sources')
    for ticker in ('QQQ','SPY'):
        parsed={}
        for role in ('sources','baseline_sources'):
            reference=capture['captured_artifacts'][ticker] if role=='sources' else capture['input_references']['baseline_'+ticker];ref(reference,claims);blob=blobs[reference['path']];require(sha(blob)==reference['sha256'],'Original CSV hash')
            rows,diagnostics=parse_csv(blob,dates[0]);parsed[role]=rows
            exact(payload['full_original_sources_preserved'][ticker][role],dict(reference=reference,original_csv_bytes_base64=base64.b64encode(blob).decode(),rows=rows,required_scope_start=dates[0],outside_required_scope_diagnostics=diagnostics),'Full CSV and outside diagnostics')
        current=parsed['sources'];baseline=parsed['baseline_sources']
        exact([r['Date'] for r in baseline if r['Date']>=dates[0]],dates,'Baseline65');exact([r['Date'] for r in current if r['Date']>=dates[0]],dates+[session],'Current66')
        require(len(current)==len(baseline)+1,'Single new row');exact(current[:-1],baseline,'Entire historical prefix unchanged')
        exact(payload['selected_original_rows'][ticker],current[-1],'Actual source row');exact(payload['source_row_locations'][ticker],dict(original_data_row_index=len(current)-1,reference=capture['captured_artifacts'][ticker]),'Original row pointer')
    tzref=capture['captured_artifacts']['tzif'];ref(tzref,claims);tz=blobs[tzref['path']];require(sha(tz)==tzref['sha256'],'TZif bytes');exact(payload['tzif_reference'],tzref,'TZif reference');exact(payload['tzif_bytes_base64'],base64.b64encode(tz).decode(),'Full TZif')
    zone=ZoneInfo.from_file(io.BytesIO(tz),key='America/New_York');close=datetime.combine(d,time(16),zone).astimezone(timezone.utc);following=d+timedelta(days=1)
    while following.weekday()>4:following+=timedelta(days=1)
    deadline=datetime.combine(following,time(9,30),zone).astimezone(timezone.utc)
    exact(payload['capture_started_at_utc'],capture['capture_started_at_utc'],'Full capture start');exact(payload['capture_completed_at_utc'],capture['observed_at_utc'],'Full capture end');exact(payload['writer_started_at_utc'],started['writer_started_at_utc'],'Writer start')
    cs,ce,ws,we,pc=map(utc,[payload['capture_started_at_utc'],payload['capture_completed_at_utc'],payload['writer_started_at_utc'],payload['writer_completed_at_utc'],receipt['publication_check_at_utc']]);require(close<=cs<=ce<=ws<=we<=pc,'Actual two-stage interval order')
    exact(payload['conservative_close_utc'],close.isoformat(),'Close');exact(payload['conservative_deadline_utc'],deadline.isoformat(),'DST/weekend deadline')
    exact(payload['timing_classification'],'LATE_OBSERVATION' if we>=deadline else 'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW','Payload timing');exact(receipt['timing_classification'],'LATE_OBSERVATION' if pc>=deadline else payload['timing_classification'],'Publication check timing')
    require(payload['writer_interval_role']=='PRE_PAYLOAD_VALIDATION_INTERVAL_NOT_PUBLICATION_COMPLETION' and receipt['publication_time_role']=='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE','No invented durable timestamp')
    monthfirst=first.get(session[:7],session)
    exact(payload['first_actual_observed_session_of_month'],monthfirst,'Actual observed, not first market day');exact(payload['month_first_actual_observation'],monthfirst==session,'Month coordinate');exact(receipt['month_first_actual_observation'],monthfirst==session,'Late still consumes month')
    exact(payload['source_hash_claims'],claims,'Complete original claims')
    for obj in (payload,started):exact(obj['input_references'],refs,'Hard input roles')
    for obj in (started,receipt):exact(obj['source_hashes'],payload['source_hashes'],'Same source map');exact(obj['runtime'],payload['runtime'],'Same runtime claim')
    for obj,flags in ((payload,PAYLOAD_FALSE),(receipt,WRITER_FALSE),(started,WRITER_FALSE)):
        for k in flags:require(obj[k] is False,'No permission upgrade '+k)
    require(payload['payload_is_not_a_published_observation_receipt'] is True and payload['seal_status_history_not_created'] is True,'Payload boundary')
    return dict(parent_observed_count=60,parent_gap_count=5,new_observation_count=1,month_first_actual_observation=monthfirst==session,timing_classification=receipt['timing_classification'],clock_authenticity_verified=False,final_durable_completion_time_verified=False,candidate_seal_allowed=False,cohort_registration_allowed=False)

def consume(r,sources):
    ref(r,sources);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed hash');return b
def decode(b):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=invalid)
def guard(sources):
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source changed')
def readback(receipt_reference,payload_reference,*,execute=False):
    require(execute is True and SESSION is not None and PARENT_READBACK_SCHEMA is not None and all(r is not None for r in BOUND.values()),'Future capture and parent audit anchors pending')
    require(Path(receipt_reference['path'])==BASE/'receipt.json' and Path(payload_reference['path'])==BASE/'observation_payload.json','Fixed evidence directory');require({p.name for p in BASE.iterdir()}=={'started.json','observation_payload.json','receipt.json'},'No failed/partial/previous readback')
    sources={str(SOURCE):LOADED,str(WRITER):WRITER_SHA};guard(sources);receipt=decode(consume(receipt_reference,sources));payload=decode(consume(payload_reference,sources));docs={k:decode(consume(r,sources)) for k,r in BOUND.items()}
    startedbytes=(BASE/'started.json').read_bytes();started=decode(startedbytes);sources[str(BASE/'started.json')]=sha(startedbytes)
    for role in ('parent','capture'):require(not (Path(BOUND[role]['path']).parent/'failure.json').exists(),'Failed parent')
    for pubrole,objrole,key,status in [('parent_publication','parent','policy_reference','PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL'),('capture_publication','capture','capture_reference','PUBLISHED_CURRENT_CACHE_CAPTURE_NOT_CALENDAR_APPEND')]:
        exact(docs[pubrole][key],BOUND[objrole],'Parent publication');exact(docs[pubrole]['source_hashes'],docs[objrole]['source_hashes'],'Parent source map');require(docs[pubrole]['status']==status,'Successful parent')
    audit=docs['parent_readback'];require(audit['schema']==PARENT_READBACK_SCHEMA and audit['status']=='PASS','Independent parent');exact(audit['policy_reference'],BOUND['parent'],'Parent audit ref');exact(audit['publication_reference'],BOUND['parent_publication'],'Parent receipt ref')
    for obj in docs.values():
        for k in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'):require(obj[k] is False,'Parent flags')
    blobs={};capture=docs['capture']
    for r in list(capture['captured_artifacts'].values())+[capture['input_references']['baseline_'+t] for t in ('QQQ','SPY')]:blobs[r['path']]=consume(r,sources)
    counts=inspect(payload,receipt,started,docs,BOUND,payload_reference,blobs,SESSION)
    require(payload['source_hashes'].get(str(WRITER))==WRITER_SHA,'Writer source anchor')
    for p,h in payload['source_hashes'].items():ref(dict(path=p,sha256=h),sources)
    guard(sources);report=dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1',status='PASS',receipt_reference=receipt_reference,payload_reference=payload_reference,reader_sha256=LOADED,source_hashes=sources,counts=counts,started_reference_role='CURRENT_BYTES_STRUCTURALLY_MATCHED_NOT_EXTERNALLY_ANCHORED',writer_called=False,old_audit_repeated=False,**dict.fromkeys(WRITER_FALSE,False))
    require({p.name for p in BASE.iterdir()}=={'started.json','observation_payload.json','receipt.json'},'Concurrent mutation');output=BASE/'independent_readback.json';b=enc(report)
    with output.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    guard(sources);require(output.read_bytes()==b and {p.name for p in BASE.iterdir()}=={'started.json','observation_payload.json','receipt.json','independent_readback.json'},'Final bytes and directory');return dict(path=str(output),sha256=sha(b))
