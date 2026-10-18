"""Independent V3 gap-parent observation readback; no writer or payload-core calls."""
import argparse,base64,csv,hashlib,io,json,os,shutil
from types import ModuleType
from copy import deepcopy
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASE=ROOT/'data/cache/research/prospective_observation_receipt_20261009_v3'
RESEARCH=ROOT/'data/cache/research'
CHECKER=(str(ROOT/'scripts/ndx_forward_gap_parent_capture_independent_readback_20261009_v3.py'),'3033e66b57b2ccfcf3bbdf091149f0c43c8c7d93387c087c5ba48fa17271cd45')
CSV_READER=(str(ROOT/'scripts/ndx_variable_prefix_capture_independent_readback_20261003.py'),'aed7b71289fb30473cedefda00c6377c0700bea115e5d99328c1c20dd4572dbe')
INVENTORY_SCOPE='LOCAL_RESEARCH_DIRECT_CHILD_WRITER_SCHEMA_NAMESPACES_NOT_FULL_FILESYSTEM_AUTHENTICATION'
WRITER=(str(ROOT/'scripts/ndx_prospective_observation_writer_v3_20261009.py'),None)
CORE=(str(ROOT/'backtest/ndx_prospective_observation_receipt_research.py'),'6a088c05321b9e9a407765190800acb9443f8f5de6f1c11d456d86f3e0415684')
CAPTURE_PRODUCER=None
CAPTURE_CORE=None
PARENT_BOUND={
 'reference':dict(path=str(ROOT/'data/cache/research/prospective_gap_history_20261009_v3/history.json'),sha256='600d15deb7cdcbc74fb13337c279d31c910d9389088ebc8668ea650779fdfd8a'),
 'publication_reference':dict(path=str(ROOT/'data/cache/research/prospective_gap_history_20261009_v3/publication.json'),sha256='3ff2cf28d954e64ed7a21af6d8b7ed5465c7cf2fe5c6fd7d057cd43e4cddfe10'),
 'readback_reference':dict(path=str(ROOT/'data/cache/research/prospective_gap_history_independent_readback_20261009_v3/independent_readback.json'),sha256='86e867fa73f28b9a436472eb27848a159a75e5de4bcf97e7a4b69b6a1be98912'),
 'reader_reference':dict(path=str(ROOT/'scripts/ndx_prospective_gap_history_independent_readback_20261009_v3.py'),sha256='2be765c5dafcb85366e4e84d3a8cbed2037a6924649695f3ab176764075791f8')}
CAPTURE_BOUND=dict.fromkeys(PARENT_BOUND)
PAYLOAD_SHA=None
RECEIPT_SHA=None
POLICY='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
ADAPTER='GAP_PARENT_PROSPECTIVE_OBSERVATION_WRITER_V3'
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
def private_checker(raw):
    require(sha(raw)==CHECKER[1],'Pinned upstream checker bytes')
    module=ModuleType('_observation_v3_upstream_checker');module.__file__=CHECKER[0]
    exec(compile(raw,CHECKER[0],'exec'),module.__dict__)
    return module


def validate_envelopes(parent,capture,checker):
    h,days,combined=checker.inspect_v3_parent(parent)
    c,p,a=(capture[k]for k in ('document','publication','readback'))
    for obj,want in ((c,'SOURCE_BOUND_FORWARD_GAP_PARENT_CAPTURE_V3'),
                     (p,'FORWARD_GAP_PARENT_CAPTURE_PUBLICATION_V3'),
                     (a,'FORWARD_GAP_PARENT_CAPTURE_INDEPENDENT_READBACK_V3')):
        exact(obj['schema'],want,'V3 envelope')
        checker.flags(obj,checker.FALSE_FIELDS)
        merge_claims(combined,obj)
    exact(p['status'],'PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION','Published capture')
    exact(a['status'],'PURE_FORWARD_GAP_CAPTURE_READBACK_PASS','V3 source readback')
    for obj in (p,a):exact(obj['capture_reference'],capture['reference'],'Capture association')
    exact(a['publication_reference'],capture['publication_reference'],'Audited publication')
    exact(a['reader_sha256'],capture['reader_reference']['sha256'],'Audited reader')
    exact(c['source_hashes'],p['source_hashes'],'Source closure')
    for path,digest in c['source_hashes'].items():bound(a['source_hashes'],dict(path=path,sha256=digest))
    for role in PARENT_BOUND:ref(capture[role],combined)
    for role in ('reference','publication_reference','reader_reference'):bound(a['source_hashes'],capture[role])
    parents={key:parent[key]for key in PARENT_BOUND}
    exact(c['parent_references'],parents,'Same parent');exact(a['parent_references'],parents,'Audited parent')
    for key in ('snapshot_bytes_verified','entire_plan_independently_reconstructed'):require(a[key]is True,'Full saved plan verified')
    for key in ('producer_called','new_pure_called','plan_gap_parent_capture_called','current_live_cache_read_or_reverified','external_clock_attestation_verified'):
        require(a[key]is False,'No upstream execution or source authentication')
    require(c['clock_captured_by_runner']is True and c['external_clock_attestation_verified']is False,'Recorded clock only')
    exact(c['quote_source_type'],'EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH','Source role')
    exact(c['current_cache_verification_scope'],'CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE','Mutable reference lifetime')
    exact(c['input_references']['pure'],CAPTURE_CORE,'Pinned capture planner')
    exact(a['input_references'],c['input_references'],'Audited inputs')
    exact(a['producer_reference'],CAPTURE_PRODUCER,'Audited producer')
    for item in (CAPTURE_CORE,CAPTURE_PRODUCER):bound(c['source_hashes'],item)
    plan=c['plan'];exact(plan['schema'],'FORWARD_GAP_PARENT_CAPTURE_PLAN_V3','Plan version')
    exact(plan['status'],'ONE_NEW_SESSION_CAPTURE_CANDIDATE','One source candidate')
    exact(plan['diagnostics'],[],'No blocking diagnostics');exact(plan['parent_references'],parents,'Plan parent')
    checker.flags(plan,{key for key in checker.FALSE_FIELDS if key!='network_quote_refresh_performed'})
    for key in ('known_typed_rows','observations','parent_attempt_inventory','first_actual_observed_session_by_month',
                'baseline_references','baseline_role','last_accounted_session','last_observed_session'):
        exact(plan[key],h[key],'Preserved parent '+key)
    exact(plan['accounted_baseline_references'],h['captured_source_references'],'Accounted baseline role')
    exact(plan['accounted_baseline_role'],'FULL_SAVED_CSV_SCOPE_EQUALS_ALL_KNOWN_TYPED_SESSIONS','Accounted baseline proof')
    session=plan['candidate_session'];day(session);require(session>days[-1],'Unique next observation')
    exact(a['counts'],dict(status=plan['status'],parent_typed_row_count=len(days),
          parent_actual_observation_count=len(h['observations']),parent_gap_count=sum(r['kind']=='MISSED_OBSERVATION'for r in h['known_typed_rows']),
          candidate_session=session,diagnostic_count=0,snapshot_counts={t:plan['source_evidence'][t]['original_row_count']for t in ('QQQ','SPY')}),'Capture counts')
    exact(sorted(c['captured_artifacts']),['QQQ','SPY','tzif'],'All source snapshots')
    exact(plan['tzif_reference'],c['captured_artifacts']['tzif'],'Timezone snapshot')
    exact(c['captured_artifacts']['tzif']['sha256'],h['tzif_reference']['sha256'],'Parent timezone binding')
    for key in ('capture_started_at','capture_completed_at'):exact(plan[key],c[key],'Capture interval')
    for ticker in ('QQQ','SPY'):
        e=plan['source_evidence'][ticker];item=c['captured_artifacts'][ticker]
        exact(e['source_reference'],item,'Original source');exact(e['new_session_dates'],[session],'Symmetric one session')
        exact(e['accounted_baseline_reference'],h['captured_source_references'][ticker],'Full accounted baseline')
        exact(e['actual_baseline_reference'],h['baseline_references'][ticker],'Historical actual baseline retained')
        exact(c['current_cache_references'][ticker],dict(path=str(ROOT/'data/cache'/f'{ticker}.csv'),sha256=item['sha256']),'Live diagnostic locator')
    no_live(combined)
    return h['known_typed_rows'],h['first_actual_observed_session_by_month']


def inspect(payload,receipt,started,docs,refs,payload_reference,blobs,session,checker,inventory):
    """All supplied blobs must come from wrapper-verified external byte references."""
    parent,capture_env=docs['parent'],docs['capture']
    known,first=validate_envelopes(parent,capture_env,checker)
    for role,env in (('parent',parent),('capture',capture_env)):exact(refs[role],{k:env[k]for k in PARENT_BOUND},'Externally supplied envelope roles')
    dates=[r['session']for r in known];claims={}
    for r in known:ref({k:r['evidence_reference'][k]for k in ('path','sha256')},claims)
    prior_attempts=parent['document']['history']['parent_attempt_inventory']
    for a in prior_attempts:
        for k in ('payload_reference','receipt_reference','independent_readback_reference'):ref(a[k],claims)
    d=day(session);require(session>dates[-1],'New unique observation')
    capture=capture_env['document'];plan=capture['plan']
    exact(session,plan['candidate_session'],'Explicit captured candidate')
    require(payload['schema']=='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1' and receipt['schema']=='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1' and started['schema']=='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V3','Evidence schemas')
    require(receipt['status']=='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY','Persisted role')
    exact(receipt['payload_reference'],payload_reference,'External payload anchor');exact(payload['known_typed_rows_preserved'],known,'Entire original typed prefix');exact(payload['parent_attempt_inventory_preserved'],prior_attempts,'Entire resolved inventory')
    for r in (refs['parent']['reference'],refs['parent']['readback_reference'],refs['capture']['reference']):ref(r,claims)
    identity=dict(parent_reference=refs['parent']['reference'],capture_reference=refs['capture']['reference'],session=session)
    exact(payload['observation_identity'],identity,'Observation identity');identifier=sha(enc(identity));exact(payload['observation_id'],identifier,'Observation digest');exact(receipt['observation_id'],identifier,'Receipt same observation')
    exact(payload['session'],session,'Session');require(type(payload['sequence'])is int and payload['sequence']==len(known)+1,'Exact variable sequence');require(payload['kind']=='PROSPECTIVE_OBSERVED_SESSION' and payload['initial_seal_status']=='NOT_ATTEMPTED','No seal')
    exact(payload['parent_readback_reference'],refs['parent']['readback_reference'],'Parent audit')
    require(set(payload['full_original_sources_preserved'])==set(payload['selected_original_rows'])==set(payload['source_row_locations'])=={'QQQ','SPY'},'Two full sources')
    for ticker in ('QQQ','SPY'):
        parsed={}
        for role in ('sources','baseline_sources'):
            reference=capture['captured_artifacts'][ticker] if role=='sources' else capture['plan']['accounted_baseline_references'][ticker];ref(reference,claims);blob=blobs[reference['path']];require(sha(blob)==reference['sha256'],'Original CSV hash')
            rows,diagnostics=parse_csv(blob,dates[0]);parsed[role]=rows
            exact(payload['full_original_sources_preserved'][ticker][role],dict(reference=reference,original_csv_bytes_base64=base64.b64encode(blob).decode(),rows=rows,required_scope_start=dates[0],outside_required_scope_diagnostics=diagnostics),'Full CSV and outside diagnostics')
        current=parsed['sources'];baseline=parsed['baseline_sources']
        require(blobs[capture['captured_artifacts'][ticker]['path']].startswith(blobs[plan['accounted_baseline_references'][ticker]['path']]),'Complete raw byte prefix unchanged')
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
    for obj in (payload,started,receipt):
        exact(obj['capture_checker_reference'],dict(zip(('path','sha256'),CHECKER)),'Pinned shared upstream checker')
        exact(obj['attempt_inventory_scope'],INVENTORY_SCOPE,'Bounded inventory scope')
        exact(obj['local_attempt_namespace_inventory'],inventory,'Prior namespace inventory')
    for obj in (started,receipt):exact(obj['source_hashes'],payload['source_hashes'],'Same source map');exact(obj['runtime'],payload['runtime'],'Same runtime claim')
    for obj,flags in ((payload,set(PAYLOAD_FALSE)|set(WRITER_FALSE)),(receipt,WRITER_FALSE),(started,WRITER_FALSE)):
        for k in flags:require(obj[k] is False,'No permission upgrade '+k)
    require(payload['payload_is_not_a_published_observation_receipt'] is True and payload['seal_status_history_not_created'] is True,'Payload boundary')
    return dict(parent_typed_row_count=len(known),parent_actual_observation_count=sum(r['kind']=='PROSPECTIVE_OBSERVED_SESSION'for r in known),parent_observed_count=sum(r['kind']!='MISSED_OBSERVATION'for r in known),parent_gap_count=sum(r['kind']=='MISSED_OBSERVATION'for r in known),new_observation_count=1,month_first_actual_observation=monthfirst==session,timing_classification=receipt['timing_classification'],clock_authenticity_verified=False,final_durable_completion_time_verified=False,candidate_seal_allowed=False,cohort_registration_allowed=False)

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
    ref(dict(zip(('path','sha256'),WRITER)),{})
    for item in (CAPTURE_PRODUCER,CAPTURE_CORE):require(item is not None,'Future capture code pending');ref(item,{})
    return dict(parent=deepcopy(PARENT_BOUND),capture=deepcopy(CAPTURE_BOUND))
def safe(path):
    path=Path(path)
    for ancestor in (path,*path.parents):require(not ancestor.is_symlink()and not getattr(ancestor,'is_junction',lambda:False)(),'Linked evidence')
    return path


def consume(r,sources):
    ref(r,sources);no_live(sources);p=safe(r['path'])
    require(p.is_file()and p.stat().st_size<=64*1024**2 and not(p.parent/'failure.json').exists(),'Bounded nonfailed evidence')
    raw=p.read_bytes();require(sha(raw)==r['sha256'],'Pinned bytes');return raw


def guard(sources):
    table=dict(sources);ref(dict(path=str(SOURCE),sha256=LOADED),table);no_live(table)
    for path,digest in table.items():consume(dict(path=path,sha256=digest),{})


def namespace(folder,names):
    entries=list(safe(folder).iterdir());exact(sorted(p.name for p in entries),sorted(names),'Exact immutable namespace')
    require(all(safe(p).is_file()for p in entries),'Regular evidence files')


def local_inventory(parent,sources):
    allowed={entry['payload_reference']['path']:entry for entry in parent['document']['history']['observations']}
    found={};folders=list(safe(RESEARCH).iterdir());require(len(folders)<=20000,'Inventory directory bound')
    for folder in folders:
        safe(folder)
        if not folder.is_dir()or folder.resolve()==BASE.resolve():continue
        records={}
        for name in ('started.json','observation_payload.json','receipt.json','failure.json'):
            path=safe(folder/name)
            if not path.exists():continue
            require(path.is_file()and path.stat().st_size<=64*1024**2,'Bounded inventory file')
            raw=path.read_bytes();records[name]=(decode(raw),dict(path=str(path),sha256=sha(raw)))
        def schema(name):return records.get(name,({},{}))[0].get('schema','')
        relevant=(schema('started.json').startswith('PROSPECTIVE_OBSERVATION_WRITER_STARTED_')or
                  schema('observation_payload.json')=='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1'or
                  schema('receipt.json')=='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1'or
                  records.get('failure.json',({},{}))[0].get('status')=='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY')
        if not relevant:continue
        exact(sorted(records),['observation_payload.json','receipt.json','started.json'],'Resolved prior attempt')
        payload,item=records['observation_payload.json'];receipt,receipt_ref=records['receipt.json']
        require(item['path']in allowed,'Unaccounted prior observation')
        entry=allowed[item['path']];exact(item,entry['payload_reference'],'Prior payload identity')
        exact(receipt_ref,entry['receipt_reference'],'Prior receipt identity')
        exact(payload['observation_id'],entry['observation_id'],'Prior observation ID')
        exact(receipt['payload_reference'],item,'Prior receipt binding')
        found[item['path']]={name:reference for name,(_,reference)in records.items()}
        for _,reference in records.values():ref(reference,sources)
    exact(sorted(found),sorted(allowed),'All prior attempts in local scope')
    return found


def load_inputs():
    refs=configured()
    sources=dict((WRITER,CORE,CHECKER,CSV_READER));docs={}
    checker=private_checker(consume(dict(zip(('path','sha256'),CHECKER)),sources))
    csv_rows=checker.private_csv_reader(consume(dict(zip(('path','sha256'),CSV_READER)),sources))
    for role,table in refs.items():
        env=deepcopy(table)
        for key,rkey in (('document','reference'),('publication','publication_reference'),('readback','readback_reference')):
            env[key]=decode(consume(table[rkey],sources));merge_claims(sources,env[key])
        consume(table['reader_reference'],sources);docs[role]=env
    validate_envelopes(docs['parent'],docs['capture'],checker)
    parent=docs['parent'];capture=docs['capture']['document'];h=parent['document']['history']
    pf=Path(refs['parent']['reference']['path']).parent;cf=Path(refs['capture']['reference']['path']).parent
    exact(refs['parent']['reference']['path'],str(pf/'history.json'),'Parent path');exact(refs['parent']['publication_reference']['path'],str(pf/'publication.json'),'Parent publication path')
    exact(refs['capture']['reference']['path'],str(cf/'capture.json'),'Capture path');exact(refs['capture']['publication_reference']['path'],str(cf/'publication.json'),'Capture publication path')
    def namespaces():
        namespace(pf,('started.json','history.json','publication.json'))
        namespace(Path(refs['parent']['readback_reference']['path']).parent,('started.json','independent_readback.json'))
        namespace(cf,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'))
        namespace(Path(refs['capture']['readback_reference']['path']).parent,('started.json','independent_readback.json'))
    namespaces();blobs={}
    for ticker in ('QQQ','SPY','tzif'):
        item=capture['captured_artifacts'][ticker]
        exact(item['path'],str(cf/(ticker+'.csv'if ticker!='tzif'else'New_York.tzif')),'Original snapshot location')
        blobs[item['path']]=consume(item,sources)
    for item in (*h['baseline_references'].values(),*h['captured_source_references'].values()):blobs[item['path']]=consume(item,sources)
    planned=checker.reconstruct_plan(parent=parent,source_bytes={t:blobs[capture['captured_artifacts'][t]['path']]for t in ('QQQ','SPY')},
        source_references={t:capture['captured_artifacts'][t]for t in ('QQQ','SPY')},
        accounted_baseline_bytes={t:blobs[h['captured_source_references'][t]['path']]for t in ('QQQ','SPY')},
        actual_baseline_bytes={t:blobs[h['baseline_references'][t]['path']]for t in ('QQQ','SPY')},
        capture_started_at=capture['capture_started_at'],capture_completed_at=capture['capture_completed_at'],
        tzif_bytes=blobs[capture['captured_artifacts']['tzif']['path']],tzif_reference=capture['captured_artifacts']['tzif'],csv_rows=csv_rows)
    exact(capture['plan'],planned,'Complete saved capture plan')
    inventory=local_inventory(parent,sources)
    def final_guard():namespaces();exact(local_inventory(parent,{}),inventory,'Inventory drift');guard(sources)
    final_guard();return docs,refs,blobs,sources,checker,inventory,final_guard


def save(path,obj):
    blob=enc(obj)
    if path.name!='failure.json':require(shutil.disk_usage(Path(BASE.anchor)).free>=5*1024**3+len(blob),'Resource stop before write')
    with safe(path).open('xb')as stream:require(stream.write(blob)==len(blob),'Complete write');stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==blob,'Saved readback bytes');return dict(path=str(path),sha256=sha(blob))
def readback(*,execute=False):
    require(type(execute)is bool,'Explicit execution bool')
    if not execute:return dict(status='NOT_EXECUTED')
    docs,refs,blobs,producer_sources,checker,inventory,final_guard=load_inputs()
    namespace(BASE,('started.json','observation_payload.json','receipt.json'))
    # Failure evidence is written only after proving this is an unread complete attempt.
    try:
        sources=deepcopy(producer_sources);pr=dict(path=str(BASE/'observation_payload.json'),sha256=PAYLOAD_SHA);rr=dict(path=str(BASE/'receipt.json'),sha256=RECEIPT_SHA)
        payload=decode(consume(pr,sources));receipt=decode(consume(rr,sources));sp=safe(BASE/'started.json');require(sp.is_file()and sp.stat().st_size<=64*1024**2,'Bounded started');sb=sp.read_bytes();sr=dict(path=str(BASE/'started.json'),sha256=sha(sb));started=decode(sb);ref(sr,sources)
        for obj in (payload,receipt,started):exact(obj['source_hashes'],producer_sources,'Independent complete producer source closure')
        counts=inspect(payload,receipt,started,docs,refs,pr,blobs,docs['capture']['document']['plan']['candidate_session'],checker,inventory)
        final_guard();guard(sources)
        report=dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3',status='PASS',payload_reference=pr,receipt_reference=rr,parent_history_reference=refs['parent']['reference'],input_references=refs,started_current_bytes_reference=sr,started_external_sha_authenticated=False,reader_sha256=LOADED,source_hashes={**sources,str(SOURCE):LOADED},counts=counts,writer_called=False,payload_core_called=False,shared_upstream_capture_checker_reference=dict(zip(('path','sha256'),CHECKER)),attempt_inventory_scope=INVENTORY_SCOPE,local_attempt_namespace_inventory=inventory,old_audit_repeated=False,exchange_holidays_verified=False,early_closes_verified=False,final_durable_completion_time_verified=False,**dict.fromkeys(WRITER_FALSE,False))
        output=save(BASE/'independent_readback.json',report);final_guard();guard(sources);namespace(BASE,('started.json','observation_payload.json','receipt.json','independent_readback.json'));require(sha(Path(output['path']).read_bytes())==output['sha256'],'Final output bytes');return output
    except BaseException as error:
        if not(BASE/'failure.json').exists():save(BASE/'failure.json',dict(status='INDEPENDENT_READBACK_FAILED_NO_RETRY',error_type=type(error).__name__,error=str(error),retry_allowed=False,partial_evidence_preserved=True,**dict.fromkeys(WRITER_FALSE,False)))
        raise
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=parser.parse_args().execute)))
