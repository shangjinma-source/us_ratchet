"""Independent variable-prefix observation readback; no writer, prepare or old-audit calls."""
import argparse,base64,csv,hashlib,io,json,os
from copy import deepcopy
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASE=ROOT/'data/cache/research/prospective_observation_receipt_20261003_v2'
WRITER=(str(ROOT/'scripts/ndx_prospective_observation_writer_v2_20261003.py'),'2bb34a707938b1417b118a41f42a18df96c12b37e0f77a96c5a1bec7d8e48e06')
CORE=(str(ROOT/'backtest/ndx_prospective_observation_receipt_research.py'),'6a088c05321b9e9a407765190800acb9443f8f5de6f1c11d456d86f3e0415684')
CAPTURE_PRODUCER=(str(ROOT/'scripts/ndx_variable_prefix_source_capture_20261003.py'),'c6cb43b87ebde1acd603e736a970679f839981a73953c63cd6b987ad030d65b6')
CAPTURE_CORE=(str(ROOT/'backtest/ndx_variable_prefix_capture_research.py'),'9c76324fcbc8e5d57a1ef25566a59110acff32a58506c6d5b6947996e6c26039')
PARENT_BOUND=dict.fromkeys(('reference','publication_reference','readback_reference','reader_reference'))
CAPTURE_BOUND=dict.fromkeys(PARENT_BOUND)
CAPTURE_BOUND['reader_reference']={'path':str(ROOT/'scripts/ndx_variable_prefix_capture_independent_readback_20261003.py'),'sha256':'a376260adfd71fed73473594f2587e51f4afb8daa1be3e15793616119a1f7518'}
PAYLOAD_SHA=None
RECEIPT_SHA=None
POLICY='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
ADAPTER='VARIABLE_PREFIX_OBSERVATION_WRITER_V2'
FIELDS=['Date','Open','High','Low','Close','Volume']
PAYLOAD_FALSE=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','source_authenticity_verified','clock_authenticity_verified','parent_attempt_inventory_completeness_verified','receipt_published','old_calendar_mutated','exchange_holidays_verified','early_closes_verified','production_generator_authorized')
WRITER_FALSE=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','old_calendar_mutated','seal_status_event_created','network_capture_performed','production_generator_authorized','full_transitive_source_closure_reverified','future_independent_oos','partial_recovery_performed','filesystem_attempt_inventory_authenticated','source_authenticity_verified','clock_authenticity_verified')
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
    require(type(blob)is bytes and len(blob)<=32000000,'Bounded original bytes')
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

def merge_claims(target,obj):
    require(type(obj['source_hashes'])is dict,'Source table')
    for p,h in obj['source_hashes'].items():ref(dict(path=p,sha256=h),target)
def bound(table,r):
    ref(r,{});exact(table.get(r['path']),r['sha256'],'Source association')
def no_live(table):
    forbidden={(ROOT/'data/cache'/f'{t}.csv').resolve()for t in ('QQQ','SPY')}
    require(all(Path(p).resolve()not in forbidden for p in table),'Live cache is not permanent evidence')
def validate_envelopes(parent,capture):
    """Validate supplied sealed envelopes, never re-execute their producers/audits."""
    combined={}
    for env,schema,pub_schema,audit_schema,status,key in (
      (parent,'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2','PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2','PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V2','PUBLISHED_OBSERVATION_HISTORY_NO_SEAL','history_reference'),
      (capture,'SOURCE_BOUND_VARIABLE_PREFIX_CAPTURE_V1','VARIABLE_PREFIX_CAPTURE_PUBLICATION_V1','VARIABLE_PREFIX_CAPTURE_INDEPENDENT_READBACK_V1','PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION','capture_reference')):
        d,p,a=(env[k]for k in ('document','publication','readback'))
        for obj,want in ((d,schema),(p,pub_schema),(a,audit_schema)):exact(obj['schema'],want,'Versioned envelope')
        exact(p['status'],status,'Published status');exact(a['status'],'PASS','External readback')
        exact(p[key],env['reference'],'Publication document');exact(a[key],env['reference'],'Audit document');exact(a['publication_reference'],env['publication_reference'],'Audit receipt');exact(a['reader_sha256'],env['reader_reference']['sha256'],'Audit code')
        exact(p['source_hashes'],d['source_hashes'],'Publication source closure')
        for role in PARENT_BOUND:ref(env[role],combined)
        for obj in (d,p,a):
            merge_claims(combined,obj)
            for flag in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'):require(obj[flag]is False,'No authority')
        for path,h in d['source_hashes'].items():bound(a['source_hashes'],dict(path=path,sha256=h))
        for role in ('reference','publication_reference','reader_reference'):bound(a['source_hashes'],env[role])
    no_live(combined)
    h=parent['document'];known=h['known_typed_rows'];exact(h['policy_id'],POLICY,'Month policy')
    require(type(known)is list and 66<=len(known)<20000,'Variable history after first observation')
    original=h['genesis_preserved']['document']['projection_inputs']['known_rows'];exact(known[:65],original,'Immutable genesis')
    require(len(original)==65 and sum(r['kind']=='MISSED_OBSERVATION'for r in original)==5 and sum(r['kind']=='SEALED_PARENT_OBSERVED_SESSION'for r in original)==60,'Genesis kinds')
    months={};previous=''
    for i,r in enumerate(known):
        exact(r['sequence'],i+1,'Typed integer sequence');day(r['session']);require(r['session']>previous,'Ordered sessions');previous=r['session']
        require(r['seal_status']in ('NOT_ATTEMPTED','UNKNOWN','FAILED','SEALED'),'Original seal state')
        require(r['kind']in ('MISSED_OBSERVATION','SEALED_PARENT_OBSERVED_SESSION','PROSPECTIVE_OBSERVED_SESSION'),'Typed kind')
        if r['kind']=='MISSED_OBSERVATION':exact(r['seal_status'],'NOT_ATTEMPTED','Gap not observed')
        else:months.setdefault(r['session'][:7],r['session'])
        ref({k:r['evidence_reference'][k]for k in ('path','sha256')},combined)
        if i>=65:exact(r['kind'],'PROSPECTIVE_OBSERVED_SESSION','Later observed row')
    entries=h['observations'];attempts=h['parent_attempt_inventory'];require(type(entries)is list and type(attempts)is list,'Full inventory')
    exact(len(entries),len(known)-65,'All observations');exact(len(attempts),len(entries),'All attempts');exact(h['observation_count'],len(entries),'Observation count')
    ids=set()
    for r,e,a in zip(known[65:],entries,attempts):
        require(e['observation_id']not in ids,'Unique observation');ids.add(e['observation_id'])
        exact(r['session'],e['session'],'Entry session');exact(r['evidence_reference'],dict(e['payload_reference'],json_pointer='/observation_identity'),'Entry pointer')
        exact(a,dict(observation_id=e['observation_id'],session=e['session'],status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',payload_reference=e['payload_reference'],receipt_reference=e['receipt_reference'],independent_readback_reference=e['audit_reference']),'Resolved complete attempt')
        for k in ('payload_reference','receipt_reference','audit_reference','reader_reference'):bound(h['source_hashes'],e[k])
    exact(h['baseline_references'],entries[-1]['captured_baseline_references'],'Last persisted baseline');exact(sorted(h['baseline_references']),['QQQ','SPY'],'Baseline roles')
    exact(h['last_accounted_session'],previous,'Cursor');exact(h['first_actual_observed_session_by_month'],months,'Actual first observations')
    ha=parent['readback']['counts']
    for k,n in (('typed_row_count',len(known)),('observation_count',len(entries)),('new_observation_count',1)):exact(ha[k],n,'History audit counts')
    exact(ha['first_actual_observed_session_by_month'],months,'Audited coordinates')
    for r in h['baseline_references'].values():bound(parent['readback']['source_hashes'],r)
    c=capture['document'];p=c['plan'];a=capture['readback'];pr={k:parent[k]for k in PARENT_BOUND}
    exact(c['parent_references'],pr,'Capture parent');exact(a['parent_references'],pr,'Capture audit parent')
    require(a['snapshot_bytes_verified']is True and a['current_live_cache_read_or_reverified']is False and a['external_clock_attestation_verified']is False,'Snapshot scope')
    require(c['clock_captured_by_runner']is True and c['external_clock_attestation_verified']is False,'Saved clock claim only')
    exact(c['quote_source_type'],'EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH','Quote role');exact(c['current_cache_verification_scope'],'CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE','Cache scope')
    bound(c['source_hashes'],dict(zip(('path','sha256'),CAPTURE_PRODUCER)));exact(c['input_references']['core'],dict(zip(('path','sha256'),CAPTURE_CORE)),'Capture core');bound(c['source_hashes'],c['input_references']['core'])
    exact(p['schema'],'COMPACT_HISTORY_VARIABLE_PREFIX_CAPTURE_PLAN_V1','Variable plan');exact(p['status'],'ONE_NEW_SESSION_CANDIDATE_NOT_OBSERVED','One candidate');exact(p['diagnostics'],[],'No blocking diagnosis')
    for k,role in (('parent_history_reference','reference'),('parent_publication_reference','publication_reference'),('parent_readback_reference','readback_reference')):exact(p[k],parent[role],'Plan parent')
    for k,v in (('known_typed_rows_preserved',known),('parent_attempt_inventory_preserved',attempts),('baseline_references',h['baseline_references']),('first_actual_observed_session_by_month_preserved',months),('scope_start',known[0]['session']),('last_accounted_session',previous)):exact(p[k],v,'Preserved prefix')
    session=p['candidate_session'];day(session);require(session>previous,'New session');exact(p['candidate_sequence'],len(known)+1,'Candidate ordinal');exact(p['proposed_first_actual_session_of_month'],months.get(session[:7],session),'Proposed first actual')
    exact(p['timing_role'],'AFTER_CONSERVATIVE_1600_CLOSE_ONLY_NOT_DEADLINE_OR_TIMELY_RECEIPT_CERTIFICATION','Timing scope')
    for flag in ('observation_created','timeliness_verified','candidate_seal_allowed','cohort_registration_allowed','future_independent_oos','filesystem_attempt_inventory_authenticated'):require(p[flag]is False,'No planner authority')
    for k in ('capture_started_at','capture_completed_at'):exact(p[k],c[k],'Capture interval')
    counts=a['counts']
    for k,v in (('status',p['status']),('candidate_session',session),('parent_typed_row_count',len(known)),('parent_observed_count',len(known)-5),('parent_gap_count',5),('diagnostic_count',0)):exact(counts[k],v,'Capture audited counts')
    exact(sorted(c['captured_artifacts']),['QQQ','SPY','tzif'],'All snapshots');exact(p['tzif_reference'],c['captured_artifacts']['tzif'],'Timezone snapshot')
    for t in ('QQQ','SPY'):
        e=p['source_evidence'][t];r=c['captured_artifacts'][t]
        exact(e['source_reference'],r,'Snapshot role');exact(e['baseline_reference'],h['baseline_references'][t],'Baseline role');exact(e['new_session_dates'],[session],'Symmetric new date');exact(counts['snapshot_counts'][t],e['original_row_count'],'Snapshot counts')
        bound(c['source_hashes'],r);bound(a['source_hashes'],r);exact(c['current_cache_references'][t],dict(path=str(ROOT/'data/cache'/f'{t}.csv'),sha256=r['sha256']),'Retained live locator only')
    return known,months

def inspect(payload,receipt,started,docs,refs,payload_reference,blobs,session):
    """All supplied blobs must come from wrapper-verified external byte references."""
    parent,capture_env=docs['parent'],docs['capture']
    known,first=validate_envelopes(parent,capture_env)
    for role,env in (('parent',parent),('capture',capture_env)):exact(refs[role],{k:env[k]for k in PARENT_BOUND},'Externally supplied envelope roles')
    dates=[r['session']for r in known];claims={}
    for r in known:ref({k:r['evidence_reference'][k]for k in ('path','sha256')},claims)
    inventory=parent['document']['parent_attempt_inventory']
    for a in inventory:
        for k in ('payload_reference','receipt_reference','independent_readback_reference'):ref(a[k],claims)
    d=day(session);require(session>dates[-1],'New unique observation')
    capture=capture_env['document'];plan=capture['plan']
    exact(session,plan['candidate_session'],'Explicit captured candidate')
    require(payload['schema']=='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1' and receipt['schema']=='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1' and started['schema']=='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V2','Evidence schemas')
    require(receipt['status']=='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY','Persisted role')
    exact(receipt['payload_reference'],payload_reference,'External payload anchor');exact(payload['known_typed_rows_preserved'],known,'Entire original typed prefix');exact(payload['parent_attempt_inventory_preserved'],inventory,'Entire resolved inventory')
    for r in (refs['parent']['reference'],refs['parent']['readback_reference'],refs['capture']['reference']):ref(r,claims)
    identity=dict(parent_reference=refs['parent']['reference'],capture_reference=refs['capture']['reference'],session=session)
    exact(payload['observation_identity'],identity,'Observation identity');identifier=sha(enc(identity));exact(payload['observation_id'],identifier,'Observation digest');exact(receipt['observation_id'],identifier,'Receipt same observation')
    exact(payload['session'],session,'Session');require(type(payload['sequence'])is int and payload['sequence']==len(known)+1,'Exact variable sequence');require(payload['kind']=='PROSPECTIVE_OBSERVED_SESSION' and payload['initial_seal_status']=='NOT_ATTEMPTED','No seal')
    exact(payload['parent_readback_reference'],refs['parent']['readback_reference'],'Parent audit')
    require(set(payload['full_original_sources_preserved'])==set(payload['selected_original_rows'])==set(payload['source_row_locations'])=={'QQQ','SPY'},'Two full sources')
    for ticker in ('QQQ','SPY'):
        parsed={}
        for role in ('sources','baseline_sources'):
            reference=capture['captured_artifacts'][ticker] if role=='sources' else parent['document']['baseline_references'][ticker];ref(reference,claims);blob=blobs[reference['path']];require(sha(blob)==reference['sha256'],'Original CSV hash')
            rows,diagnostics=parse_csv(blob,dates[0]);parsed[role]=rows
            exact(payload['full_original_sources_preserved'][ticker][role],dict(reference=reference,original_csv_bytes_base64=base64.b64encode(blob).decode(),rows=rows,required_scope_start=dates[0],outside_required_scope_diagnostics=diagnostics),'Full CSV and outside diagnostics')
        current=parsed['sources'];baseline=parsed['baseline_sources']
        exact([r['Date'] for r in baseline if r['Date']>=dates[0]],dates,'Complete variable baseline');exact([r['Date'] for r in current if r['Date']>=dates[0]],dates+[session],'Variable prefix plus one')
        exact(plan['source_evidence'][ticker]['original_row_count'],len(current),'Snapshot row count')
        require(len(current)==len(baseline)+1,'Single new row');exact(current[:-1],baseline,'Entire historical prefix unchanged')
        exact(payload['selected_original_rows'][ticker],current[-1],'Actual source row');exact(payload['source_row_locations'][ticker],dict(original_data_row_index=len(current)-1,reference=capture['captured_artifacts'][ticker]),'Original row pointer')
    tzref=capture['captured_artifacts']['tzif'];ref(tzref,claims);tz=blobs[tzref['path']];require(sha(tz)==tzref['sha256'],'TZif bytes');exact(payload['tzif_reference'],tzref,'TZif reference');exact(payload['tzif_bytes_base64'],base64.b64encode(tz).decode(),'Full TZif')
    zone=ZoneInfo.from_file(io.BytesIO(tz),key='America/New_York');close=datetime.combine(d,time(16),zone).astimezone(timezone.utc);following=d+timedelta(days=1)
    while following.weekday()>4:following+=timedelta(days=1)
    deadline=datetime.combine(following,time(9,30),zone).astimezone(timezone.utc)
    exact(payload['capture_started_at_utc'],capture['capture_started_at'],'Full capture start');exact(payload['capture_completed_at_utc'],capture['capture_completed_at'],'Full capture end');exact(payload['writer_started_at_utc'],started['writer_started_at_utc'],'Writer start')
    cs,ce,ws,we,pc=map(utc,[payload['capture_started_at_utc'],payload['capture_completed_at_utc'],payload['writer_started_at_utc'],payload['writer_completed_at_utc'],receipt['publication_check_at_utc']]);require(close<=cs<=ce<=ws<=we<=pc,'Actual two-stage interval order')
    exact(payload['conservative_close_utc'],close.isoformat(),'Close');exact(payload['conservative_deadline_utc'],deadline.isoformat(),'DST/weekend deadline')
    exact(payload['timing_classification'],'LATE_OBSERVATION' if we>=deadline else 'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW','Payload timing');exact(receipt['timing_classification'],'LATE_OBSERVATION' if pc>=deadline else payload['timing_classification'],'Publication check timing')
    require(payload['writer_interval_role']=='PRE_PAYLOAD_VALIDATION_INTERVAL_NOT_PUBLICATION_COMPLETION' and receipt['publication_time_role']=='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE','No invented durable timestamp')
    monthfirst=first.get(session[:7],session)
    exact(payload['first_actual_observed_session_of_month'],monthfirst,'Actual observed, not first market day');exact(payload['month_first_actual_observation'],monthfirst==session,'Month coordinate');exact(receipt['month_first_actual_observation'],monthfirst==session,'Late still consumes month')
    exact(payload['source_hash_claims'],claims,'Complete original claims')
    for obj in (payload,started,receipt):exact(obj['input_references'],refs,'Hard eight input roles');exact(obj['writer_adapter_schema'],ADAPTER,'Versioned writer adapter')
    for obj in (started,receipt):exact(obj['source_hashes'],payload['source_hashes'],'Same source map');exact(obj['runtime'],payload['runtime'],'Same runtime claim')
    for obj,flags in ((payload,set(PAYLOAD_FALSE)|set(WRITER_FALSE)),(receipt,WRITER_FALSE),(started,WRITER_FALSE)):
        for k in flags:require(obj[k] is False,'No permission upgrade '+k)
    require(payload['payload_is_not_a_published_observation_receipt'] is True and payload['seal_status_history_not_created'] is True,'Payload boundary')
    return dict(parent_observed_count=len(known)-5,parent_gap_count=5,new_observation_count=1,month_first_actual_observation=monthfirst==session,timing_classification=receipt['timing_classification'],clock_authenticity_verified=False,final_durable_completion_time_verified=False,candidate_seal_allowed=False,cohort_registration_allowed=False)

def decode(blob):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def invalid(value):raise ValueError('Nonfinite JSON')
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=invalid)
def configured():
    for table in (PARENT_BOUND,CAPTURE_BOUND):
        exact(sorted(table),sorted(('reference','publication_reference','readback_reference','reader_reference')),'Four immutable anchors')
        for r in table.values():require(r is not None,'Future evidence anchors pending');ref(r,{})
    for h in (PAYLOAD_SHA,RECEIPT_SHA):
        require(h is not None,'Future observation anchors pending');ref(dict(path='configured',sha256=h),{})
    return dict(parent=deepcopy(PARENT_BOUND),capture=deepcopy(CAPTURE_BOUND))
def consume(r,sources):
    ref(r,sources);no_live(sources);p=Path(r['path']);require(not p.is_symlink() and not(p.parent/'failure.json').exists(),'Failed or indirect source namespace');blob=p.read_bytes();require(sha(blob)==r['sha256'],'Pinned bytes');return blob
def guard(sources):
    s=deepcopy(sources);ref(dict(path=str(SOURCE),sha256=LOADED),s);no_live(s)
    for p,h in s.items():consume(dict(path=p,sha256=h),{})
def namespace(folder,names):
    entries=list(folder.iterdir());exact(sorted(p.name for p in entries),sorted(names),'Exact immutable namespace');require(all(p.is_file()and not p.is_symlink()for p in entries),'Regular evidence files')
def load_inputs():
    refs=configured() # All future artifact pins before filesystem access.
    sources=dict((WRITER,CORE));docs={}
    for role,table in refs.items():
        env=deepcopy(table)
        for key,rkey in (('document','reference'),('publication','publication_reference'),('readback','readback_reference')):
            env[key]=decode(consume(table[rkey],sources));merge_claims(sources,env[key])
        consume(table['reader_reference'],sources);docs[role]=env
    validate_envelopes(docs['parent'],docs['capture'])
    folder=Path(refs['parent']['reference']['path']).parent
    exact(refs['parent']['reference']['path'],str(folder/'history.json'),'History path');exact(refs['parent']['publication_reference']['path'],str(folder/'publication.json'),'History receipt path');namespace(folder,('started.json','history.json','publication.json'))
    folder=Path(refs['capture']['reference']['path']).parent
    exact(refs['capture']['reference']['path'],str(folder/'capture.json'),'Capture path');exact(refs['capture']['publication_reference']['path'],str(folder/'publication.json'),'Capture receipt path');namespace(folder,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'))
    blobs={};capture=docs['capture']['document']
    for t in ('QQQ','SPY','tzif'):
        r=capture['captured_artifacts'][t];exact(r['path'],str(folder/(f'{t}.csv'if t!='tzif'else'New_York.tzif')),'Permanent snapshot location');blobs[r['path']]=consume(r,sources)
    for r in docs['parent']['document']['baseline_references'].values():blobs[r['path']]=consume(r,sources)
    guard(sources);return docs,refs,blobs,sources
def save(path,obj):
    blob=enc(obj)
    with path.open('xb')as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==blob,'Saved readback bytes');return dict(path=str(path),sha256=sha(blob))
def readback(*,execute=False):
    require(type(execute)is bool,'Explicit execution bool')
    if not execute:return dict(status='NOT_EXECUTED')
    docs,refs,blobs,producer_sources=load_inputs()
    namespace(BASE,('started.json','observation_payload.json','receipt.json'))
    # Failure evidence is written only after proving this is an unread complete attempt.
    try:
        sources=deepcopy(producer_sources);pr=dict(path=str(BASE/'observation_payload.json'),sha256=PAYLOAD_SHA);rr=dict(path=str(BASE/'receipt.json'),sha256=RECEIPT_SHA)
        payload=decode(consume(pr,sources));receipt=decode(consume(rr,sources));sb=(BASE/'started.json').read_bytes();sr=dict(path=str(BASE/'started.json'),sha256=sha(sb));started=decode(sb);ref(sr,sources)
        for obj in (payload,receipt,started):exact(obj['source_hashes'],producer_sources,'Independent complete producer source closure')
        counts=inspect(payload,receipt,started,docs,refs,pr,blobs,docs['capture']['document']['plan']['candidate_session'])
        guard(sources)
        report=dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V2',status='PASS',payload_reference=pr,receipt_reference=rr,parent_history_reference=refs['parent']['reference'],input_references=refs,started_current_bytes_reference=sr,started_external_sha_authenticated=False,reader_sha256=LOADED,source_hashes={**sources,str(SOURCE):LOADED},counts=counts,writer_called=False,old_audit_repeated=False,exchange_holidays_verified=False,early_closes_verified=False,final_durable_completion_time_verified=False,**dict.fromkeys(WRITER_FALSE,False))
        output=save(BASE/'independent_readback.json',report);guard(sources);namespace(BASE,('started.json','observation_payload.json','receipt.json','independent_readback.json'));require(sha(Path(output['path']).read_bytes())==output['sha256'],'Final output bytes');return output
    except BaseException as error:
        if not(BASE/'failure.json').exists():save(BASE/'failure.json',dict(status='INDEPENDENT_READBACK_FAILED_NO_RETRY',error_type=type(error).__name__,error=str(error),retry_allowed=False,partial_evidence_preserved=True,**dict.fromkeys(WRITER_FALSE,False)))
        raise
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=parser.parse_args().execute)))
