"""Versioned variable-history observation writer; all future evidence pins fail closed.
The V1 payload/receipt formats are retained for compact-history compatibility.
Only the adapter/started schema is V2; future independent observation reader V2 is required.
"""
import argparse,hashlib,json,os,platform,sys,types,shutil
from copy import deepcopy
from datetime import date,datetime,timezone
from pathlib import Path
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_prospective_observation_receipt_research.py';CORE_SHA='6a088c05321b9e9a407765190800acb9443f8f5de6f1c11d456d86f3e0415684'
OUTPUT=ROOT/'data/cache/research/prospective_observation_receipt_20261003_v2'
PARENT_BOUND=dict.fromkeys(('reference','publication_reference','readback_reference','reader_reference'))
CAPTURE_BOUND=dict.fromkeys(('reference','publication_reference','readback_reference','reader_reference'))
CAPTURE_BOUND['reader_reference']=dict(path=str(ROOT/'scripts/ndx_variable_prefix_capture_independent_readback_20261003.py'),sha256='a376260adfd71fed73473594f2587e51f4afb8daa1be3e15793616119a1f7518')
CAPTURE_PRODUCER=(str(ROOT/'scripts/ndx_variable_prefix_source_capture_20261003.py'),'c6cb43b87ebde1acd603e736a970679f839981a73953c63cd6b987ad030d65b6')
CAPTURE_CORE=(str(ROOT/'backtest/ndx_variable_prefix_capture_research.py'),'9c76324fcbc8e5d57a1ef25566a59110acff32a58506c6d5b6947996e6c26039')
POLICY='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
ADAPTER='VARIABLE_PREFIX_OBSERVATION_WRITER_V2'
FLAGS=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','old_calendar_mutated','seal_status_event_created','network_capture_performed','production_generator_authorized','full_transitive_source_closure_reverified','future_independent_oos','partial_recovery_performed','filesystem_attempt_inventory_authenticated','source_authenticity_verified','clock_authenticity_verified'),False)
MIN_FREE=5*1024**3

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,msg):require(encode(a)==encode(b),msg)
def now():return datetime.now(timezone.utc).isoformat()
def runtime():return dict(python=sys.version,executable=sys.executable,implementation=platform.python_implementation())
def ref(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'] and r['path']==r['path'].strip() and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Exact external reference')
def load_json(b):
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    def invalid(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=invalid)
def guard(sources):
    no_live(sources)
    for p,h in {str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA}.items():require(p not in sources or sources[p]==h,'Loaded-source conflict')
    for p,h in {**sources,str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA}.items():
        require(not (Path(p).parent/'failure.json').exists(),'Failed immutable source namespace '+p)
        require(sha(Path(p).read_bytes())==h,'Source drift '+p)
def consume(r,sources):
    ref(r);require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Source hash conflict');b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed bytes');sources[r['path']]=r['sha256'];return b

def integer(value,expected):require(type(value)is int and value==expected,'Exact integer count')
def merge(s,r):
    ref(r);require(r['path']not in s or s[r['path']]==r['sha256'],'Source hash conflict');s[r['path']]=r['sha256']
def claims(s,obj):
    require(type(obj['source_hashes'])is dict,'Full source map')
    for p,h in obj['source_hashes'].items():merge(s,dict(path=p,sha256=h))
def configured(bound):
    require(set(bound)=={'reference','publication_reference','readback_reference','reader_reference'},'Complete four anchors')
    for r in bound.values():require(r is not None,'Future immutable anchors pending');ref(r)
    return deepcopy(bound)
def no_live(s):
    live={(ROOT/'data/cache'/f'{t}.csv').resolve()for t in ('QQQ','SPY')}
    require(all(Path(p).resolve()not in live for p in s),'UNSUPPORTED_LIVE_CACHE_PERMANENT_SOURCE_CLAIM')
def association(s,r):ref(r);require(s.get(r['path'])==r['sha256'],'Independent source association')
def evidence(envelope,schema,pub_schema,status,reference_key):
    d,p,a=envelope['document'],envelope['publication'],envelope['readback']
    exact(d['schema'],schema,'Document schema');exact(p['schema'],pub_schema,'Receipt schema');exact(p['status'],status,'Complete receipt')
    for obj in (p,a):exact(obj[reference_key],envelope['reference'],'Document reference')
    exact(a['publication_reference'],envelope['publication_reference'],'Audited publication');exact(a['reader_sha256'],envelope['reader_reference']['sha256'],'Pinned reader')
    exact(a['status'],'PASS','Independent PASS');exact(d['source_hashes'],p['source_hashes'],'Publication sources')
    for obj in (d,p,a):
        for k in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'):require(obj[k]is False,'No authority upgrade')
    for path,h in d['source_hashes'].items():association(a['source_hashes'],dict(path=path,sha256=h))
    for k in ('reference','publication_reference','reader_reference'):association(a['source_hashes'],envelope[k])

def validate_documents(parent,capture):
    evidence(parent,'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2','PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2','PUBLISHED_OBSERVATION_HISTORY_NO_SEAL','history_reference')
    h=parent['document'];ha=parent['readback'];exact(ha['schema'],'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V2','History audit schema');exact(h['policy_id'],POLICY,'Original month policy')
    known=h['known_typed_rows'];require(type(known)is list and 66<=len(known)<20000,'Full variable parent prefix');gen=h['genesis_preserved']['document']['projection_inputs']['known_rows'];integer(len(gen),65);exact(known[:65],gen,'Complete original prefix')
    integer(sum(r['kind']=='MISSED_OBSERVATION'for r in gen),5);integer(sum(r['kind']=='SEALED_PARENT_OBSERVED_SESSION'for r in gen),60)
    months={};previous=''
    for i,r in enumerate(known):
        integer(r['sequence'],i+1);day=r['session'];require(type(day)is str and date.fromisoformat(day).isoformat()==day and date.fromisoformat(day).weekday()<5 and day>previous,'Ordered full prefix');previous=day
        require(r['kind']in ('SEALED_PARENT_OBSERVED_SESSION','MISSED_OBSERVATION','PROSPECTIVE_OBSERVED_SESSION')and r['seal_status']in ('UNKNOWN','FAILED','NOT_ATTEMPTED','SEALED'),'Typed seal state')
        if r['kind']=='MISSED_OBSERVATION':exact(r['seal_status'],'NOT_ATTEMPTED','Gap is not observed')
        else:months.setdefault(day[:7],day)
        if i>=65:exact(r['kind'],'PROSPECTIVE_OBSERVED_SESSION','Later actual observation only')
    exact(h['last_accounted_session'],known[-1]['session'],'Last accounted');exact(h['first_actual_observed_session_by_month'],months,'First actual, even failed/unknown/late')
    attempts=h['parent_attempt_inventory'];require(type(attempts)is list,'Entire inventory');integer(len(attempts),len(known)-65);integer(h['observation_count'],len(attempts))
    for k,n in [('typed_row_count',len(known)),('observation_count',len(attempts)),('new_observation_count',1)]:integer(ha['counts'][k],n)
    exact(ha['counts']['first_actual_observed_session_by_month'],months,'Audited month map');exact(sorted(h['baseline_references']),['QQQ','SPY'],'Two baselines')
    for r in h['baseline_references'].values():association(ha['source_hashes'],r)
    evidence(capture,'SOURCE_BOUND_VARIABLE_PREFIX_CAPTURE_V1','VARIABLE_PREFIX_CAPTURE_PUBLICATION_V1','PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION','capture_reference')
    c=capture['document'];a=capture['readback'];plan=c['plan'];pr={k:parent[k]for k in PARENT_BOUND}
    require(a['snapshot_bytes_verified']is True and a['current_live_cache_read_or_reverified']is False and a['external_clock_attestation_verified']is False,'Independent snapshot not live cache authentication');exact(a['schema'],'VARIABLE_PREFIX_CAPTURE_INDEPENDENT_READBACK_V1','Capture audit schema');exact(c['parent_references'],pr,'Same complete parent');exact(a['parent_references'],pr,'Audit same parent')
    require(c['clock_captured_by_runner']is True and c['external_clock_attestation_verified']is False,'Recorded clock not attestation');exact(c['quote_source_type'],'EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH','Source role');exact(c['current_cache_verification_scope'],'CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE','Live reference lifetime')
    association(c['source_hashes'],dict(path=CAPTURE_PRODUCER[0],sha256=CAPTURE_PRODUCER[1]));exact(c['input_references']['core'],dict(path=CAPTURE_CORE[0],sha256=CAPTURE_CORE[1]),'Fixed capture planner');association(c['source_hashes'],c['input_references']['core'])
    exact(plan['schema'],'COMPACT_HISTORY_VARIABLE_PREFIX_CAPTURE_PLAN_V1','No disguised old frontier');exact(plan['status'],'ONE_NEW_SESSION_CANDIDATE_NOT_OBSERVED','Only one new candidate');exact(plan['diagnostics'],[],'No source diagnostics')
    for key,role in [('parent_history_reference','reference'),('parent_publication_reference','publication_reference'),('parent_readback_reference','readback_reference')]:exact(plan[key],parent[role],'Plan parent')
    exact(plan['known_typed_rows_preserved'],known,'All rows preserved');exact(plan['parent_attempt_inventory_preserved'],attempts,'All attempts preserved');exact(plan['baseline_references'],h['baseline_references'],'Baseline roles');exact(plan['first_actual_observed_session_by_month_preserved'],months,'Month map preserved')
    session=plan['candidate_session'];require(type(session)is str and date.fromisoformat(session).isoformat()==session and session>known[-1]['session'],'New explicit session');integer(plan['candidate_sequence'],len(known)+1)
    exact(plan['proposed_first_actual_session_of_month'],months.get(session[:7],session),'Proposed month first');exact(plan['scope_start'],known[0]['session'],'Scope');exact(plan['last_accounted_session'],known[-1]['session'],'Accounted cursor')
    exact(plan['timing_role'],'AFTER_CONSERVATIVE_1600_CLOSE_ONLY_NOT_DEADLINE_OR_TIMELY_RECEIPT_CERTIFICATION','Candidate is not timely receipt')
    for k in ('observation_created','timeliness_verified','candidate_seal_allowed','cohort_registration_allowed','future_independent_oos','filesystem_attempt_inventory_authenticated'):require(plan[k]is False,'No planner authority')
    exact(plan['capture_started_at'],c['capture_started_at'],'Capture start');exact(plan['capture_completed_at'],c['capture_completed_at'],'Capture end')
    counts=a['counts'];exact(counts['status'],plan['status'],'Audited status');exact(counts['candidate_session'],session,'Audited candidate');integer(counts['parent_typed_row_count'],len(known));integer(counts['parent_observed_count'],len(known)-5);integer(counts['parent_gap_count'],5);integer(counts['diagnostic_count'],0)
    exact(sorted(c['captured_artifacts']),['QQQ','SPY','tzif'],'Snapshot roles');exact(plan['tzif_reference'],c['captured_artifacts']['tzif'],'TZif snapshot')
    for t in ('QQQ','SPY'):
        e=plan['source_evidence'][t];r=c['captured_artifacts'][t];exact(e['source_reference'],r,'Original snapshot');exact(e['baseline_reference'],h['baseline_references'][t],'Original baseline');exact(e['new_session_dates'],[session],'Symmetric single new session');integer(counts['snapshot_counts'][t],e['original_row_count']);association(a['source_hashes'],r);association(c['source_hashes'],r)
        exact(c['current_cache_references'][t],dict(path=str(ROOT/'data/cache'/f'{t}.csv'),sha256=r['sha256']),'Retained cache diagnosis')
    s={}
    for envelope in (parent,capture):
        for k in PARENT_BOUND:merge(s,envelope[k])
        for key in ('document','publication','readback'):claims(s,envelope[key])
    no_live(s);return session

def namespace(path,names):
    items=list(path.iterdir());exact(sorted(p.name for p in items),sorted(names),'Complete immutable namespace');require(all(p.is_file()and not p.is_symlink()for p in items),'Regular evidence files')
def load_envelope(refs,s):
    env=deepcopy(refs)
    for key,role in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:
        require(not (Path(refs[role]['path']).parent/'failure.json').exists(),'Failed parent evidence');env[key]=load_json(consume(refs[role],s));claims(s,env[key])
    consume(refs['reader_reference'],s);return env

def load_inputs():
    pr=configured(PARENT_BOUND);cr=configured(CAPTURE_BOUND) # All artifact/parent future anchors before all filesystem access.
    s={str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA};guard(s);parent=load_envelope(pr,s);capture=load_envelope(cr,s);session=validate_documents(parent,capture)
    folder=Path(pr['reference']['path']).parent;exact(pr['reference']['path'],str(folder/'history.json'),'History location');exact(pr['publication_reference']['path'],str(folder/'publication.json'),'History publication');namespace(folder,('started.json','history.json','publication.json'))
    folder=Path(cr['reference']['path']).parent;exact(cr['reference']['path'],str(folder/'capture.json'),'Capture location');exact(cr['publication_reference']['path'],str(folder/'publication.json'),'Capture publication');namespace(folder,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'))
    c=capture['document'];value=dict(reference=cr['reference'],started_at_utc=c['capture_started_at'],completed_at_utc=c['capture_completed_at'],sources={},baseline_sources={})
    for t in ('QQQ','SPY'):
        exact(c['captured_artifacts'][t]['path'],str(folder/f'{t}.csv'),'Original snapshot location')
        for role,r in [('sources',c['captured_artifacts'][t]),('baseline_sources',parent['document']['baseline_references'][t])]:value[role][t]=dict(bytes=consume(r,s),reference=deepcopy(r))
    tr=c['captured_artifacts']['tzif'];exact(tr['path'],str(folder/'New_York.tzif'),'TZif location');value['tzif']=dict(bytes=consume(tr,s),reference=deepcopy(tr))
    no_live(s);guard(s);code=consume(dict(path=str(CORE),sha256=CORE_SHA),s);core=types.ModuleType('_variable_observation_payload');exec(compile(code,str(CORE),'exec'),core.__dict__)
    args=dict(parent_reference=pr['reference'],parent_readback_reference=pr['readback_reference'],known_typed_rows=deepcopy(parent['document']['known_typed_rows']),parent_attempt_inventory=deepcopy(parent['document']['parent_attempt_inventory']),capture=value,session=session)
    return args,dict(parent=pr,capture=cr),s,core

def resource_gate(n=0):
    require(type(n)is int and n>=0,'Exact bytes reserve');require(shutil.disk_usage(Path(OUTPUT.anchor)).free>=MIN_FREE+n,'RESOURCE_STOP_BEFORE_WRITE')
def save(path,v):
    b=encode(v)
    if path.name!='failure.json':resource_gate(len(b))
    with path.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Durable bytes');return dict(path=str(path),sha256=sha(b))
def run(*,execute=False):
    require(type(execute)is bool,'Explicit bool')
    if not execute:return dict(status='NOT_EXECUTED')
    args,refs,sources,core=load_inputs();require(not OUTPUT.exists(),'One exclusive attempt; no retry');resource_gate();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        rt=runtime();start=now();save(OUTPUT/'started.json',dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V2',writer_adapter_schema=ADAPTER,writer_started_at_utc=start,input_references=refs,source_hashes=deepcopy(sources),runtime=rt,**FLAGS));guard(sources)
        end=now();payload=core.prepare_observation_payload(**args,writer_started_at_utc=start,writer_completed_at_utc=end)
        for p,h in payload['source_hash_claims'].items():require(sources.get(p)==h,'Payload claim outside immutable closure')
        payload.update(writer_adapter_schema=ADAPTER,writer_interval_role='PRE_PAYLOAD_VALIDATION_INTERVAL_NOT_PUBLICATION_COMPLETION',input_references=deepcopy(refs),source_hashes=deepcopy(sources),runtime=rt)
        payload.update(FLAGS);out=save(OUTPUT/'observation_payload.json',payload);guard(sources);require(runtime()==rt,'Runtime drift')
        check=now();require(core.utc(check)>=core.utc(end),'Publication clock did not reverse');late=payload['timing_classification']=='LATE_OBSERVATION'or core.utc(check)>=core.utc(payload['conservative_deadline_utc'])
        receipt=save(OUTPUT/'receipt.json',dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',writer_adapter_schema=ADAPTER,status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY',observation_id=payload['observation_id'],payload_reference=out,publication_check_at_utc=check,publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE',timing_classification='LATE_OBSERVATION'if late else payload['timing_classification'],month_first_actual_observation=payload['month_first_actual_observation'],input_references=deepcopy(refs),source_hashes=deepcopy(sources),runtime=rt,**FLAGS))
        guard(sources);require(runtime()==rt,'Runtime drift')
        for r in (out,receipt):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final evidence bytes')
        namespace(OUTPUT,('started.json','observation_payload.json','receipt.json'));return receipt
    except BaseException as e:
        save(OUTPUT/'failure.json',dict(status='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY',error_type=type(e).__name__,error=str(e),recorded_at_utc=now(),observation_payload_must_not_be_discarded=(OUTPUT/'observation_payload.json').exists(),retry_allowed=False,**FLAGS));raise
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
