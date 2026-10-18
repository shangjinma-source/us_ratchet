"""Registered observation readback: independent payload arithmetic; audit V3 format.

V3 names the compatible evidence format, never an asserted parent version.
No writer or payload generator is imported or executed. Each run requires a
pinned writer and immutable external artifact references.
"""
import argparse,base64,csv,hashlib,io,json,os,shutil
from types import ModuleType
from copy import deepcopy
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESEARCH=ROOT/'data/cache/research'
CURRENT={t:ROOT/'data/cache'/f'{t}.csv'for t in ('QQQ','SPY')}
WRITER=ROOT/'scripts/ndx_registered_observation_writer_20261009_v1.py'
WRITER_SHA='8a346e221e7f8bddc9991a18cfa87c3a891dbb1b0c1afd136eb0bc64972d06bb'
REGISTRATION_CORE=(ROOT/'backtest/ndx_observation_runtime_registration_research_v1.py','1b2db6d83aa9e7dbd3229930b3d485b0256d43fefcb6f1503333f1ac3f8f8c99')
REFERENCE_CORE=(ROOT/'backtest/ndx_compact_history_runtime_registration_research_v1.py','d0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')
DEPENDENCIES={
 'payload_core':(ROOT/'backtest/ndx_prospective_observation_receipt_research.py','6a088c05321b9e9a407765190800acb9443f8f5de6f1c11d456d86f3e0415684'),
 'parent_view':(ROOT/'backtest/ndx_prospective_observation_parent_history_research_v4.py','06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'),
 'compact_helpers':(ROOT/'backtest/ndx_prospective_observation_parent_history_research.py','1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'),
 'capture_checker':(ROOT/'scripts/ndx_registered_forward_capture_independent_readback_20261009_v1.py','b44f2d2cd89f5ea4a64e268e86b409305e7e40673df6565f1d2ba8f9bdeb8cc2'),
 'csv_reader':(ROOT/'scripts/ndx_variable_prefix_capture_independent_readback_20261003.py','aed7b71289fb30473cedefda00c6377c0700bea115e5d99328c1c20dd4572dbe')}
CHECKER=tuple(map(str,DEPENDENCIES['capture_checker']))
ADAPTER='REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V4'
ROLES=('reference','publication_reference','readback_reference','reader_reference')
INVENTORY_SCOPE='LOCAL_RESEARCH_DIRECT_CHILD_WRITER_SCHEMAS_PLUS_BOUND_PARENT_EXTERNAL_ATTEMPT_NAMESPACES_NOT_FULL_FILESYSTEM_AUTHENTICATION'
FIELDS=['Date','Open','High','Low','Close','Volume']
PAYLOAD_FALSE=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','source_authenticity_verified','clock_authenticity_verified','parent_attempt_inventory_completeness_verified','receipt_published','old_calendar_mutated','exchange_holidays_verified','early_closes_verified','production_generator_authorized')
WRITER_FALSE=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','old_calendar_mutated','seal_status_event_created','network_capture_performed','production_generator_authorized','full_transitive_source_closure_reverified','future_independent_oos','partial_recovery_performed','filesystem_attempt_inventory_authenticated','source_authenticity_verified','clock_authenticity_verified','parent_attempt_inventory_completeness_verified')

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg="Independent exact evidence mismatch"):require(enc(a)==enc(b),msg)
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
    forbidden={(ROOT/'data/cache'/f'{t}.csv').resolve()for t in ('QQQ','SPY')}|{p.resolve()for p in CURRENT.values()}
    require(all(Path(p).resolve()not in forbidden for p in table),'Live cache is not permanent evidence')

def validate_capture(parent,capture,checker,parent_checker):
    view=parent_checker.inspect_parent_history_v4(parent)
    c,p,a=(capture[key]for key in ('document','publication','readback'))
    exact(c['schema'],'SOURCE_BOUND_FORWARD_CAPTURE_V4');exact(p['schema'],'FORWARD_CAPTURE_PUBLICATION_V4')
    exact(p['status'],'PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION')
    exact(a['schema'],'FORWARD_CAPTURE_INDEPENDENT_READBACK_V4');exact(a['status'],'PURE_FORWARD_CAPTURE_READBACK_PASS')
    for obj in (c,p,a):
        for flag in checker.FALSE_FIELDS:require(obj.get(flag)is False,'Strict capture authority '+flag)
    for obj in (p,a):exact(obj['capture_reference'],capture['reference'])
    exact(a['publication_reference'],capture['publication_reference']);exact(a['reader_sha256'],capture['reader_reference']['sha256'])
    exact(capture['reader_reference'],dict(zip(('path','sha256'),map(str,DEPENDENCIES['capture_checker']))))
    parents={key:parent[key]for key in ROLES};exact(c['parent_references'],parents);exact(a['parent_references'],parents)
    exact(c['source_hashes'],p['source_hashes'])
    for path,digest in c['source_hashes'].items():exact(a['source_hashes'].get(path),digest)
    for role in ('reference','publication_reference','reader_reference'):
        item=capture[role];exact(a['source_hashes'].get(item['path']),item['sha256'])
    for key in ('entire_plan_independently_reconstructed','snapshot_bytes_verified','shared_parent_checker_called'):
        require(a[key]is True,'Full independent capture readback')
    for key in ('producer_called','capture_core_called','current_live_cache_read_or_reverified','external_clock_attestation_verified'):
        require(a[key]is False,'No upstream execution or authentication inference')
    require(c['clock_captured_by_runner']is True and c['external_clock_attestation_verified']is False,'Runner clock record')
    exact(c['quote_source_type'],'EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH')
    exact(c['current_cache_verification_scope'],'CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE')
    exact(c['input_references'],a['input_references'])
    producer=dict(path=str(checker.PRODUCER),sha256=checker.PRODUCER_SHA)
    exact(a['producer_reference'],producer);exact(c['input_references']['runtime'],producer)
    dependencies={key:dict(path=str(ROOT/path),sha256=digest)for key,(path,digest)in checker.DEPENDENCIES.items()}
    exact(c['input_references']['dependencies'],dependencies)
    exact(c['input_references']['registration_core'],dict(path=str(checker.REGISTRATION_CORE[0]),sha256=checker.REGISTRATION_CORE[1]))
    exact(c['input_references']['reference_core'],dict(path=str(checker.REFERENCE_CORE[0]),sha256=checker.REFERENCE_CORE[1]))
    exact(c['input_references']['tzif'],view['tzif_reference'])
    exact(a['shared_upstream_parent_checker_reference'],dependencies['parent_view'])
    for item in (producer,*dependencies.values(),c['input_references']['registration'],c['input_references']['registration_core'],c['input_references']['reference_core']):
        exact(c['source_hashes'].get(item['path']),item['sha256'])
    plan=c['plan'];exact(plan['schema'],'FORWARD_PARENT_CAPTURE_PLAN_V4')
    exact(plan['status'],'ONE_NEW_SESSION_CAPTURE_CANDIDATE');exact(plan['diagnostics'],[])
    exact(plan['parent_references'],parents)
    for key in ('known_typed_rows','observations','parent_attempt_inventory','first_actual_observed_session_by_month',
        'baseline_references','baseline_role','accounted_baseline_references','accounted_baseline_role','last_accounted_session','last_observed_session'):
        exact(plan[key],view[key])
    session=plan['candidate_session'];require(type(session)is str and session>view['last_accounted_session'],'Next unique session')
    exact(a['counts'],dict(status=plan['status'],parent_typed_row_count=len(view['known_typed_rows']),
        parent_actual_observation_count=len(view['observations']),parent_observed_count=sum(row['kind']!='MISSED_OBSERVATION'for row in view['known_typed_rows']),
        parent_gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in view['known_typed_rows']),candidate_session=session,diagnostic_count=0,
        snapshot_counts={t:plan['source_evidence'][t]['original_row_count']for t in ('QQQ','SPY')}))
    exact(sorted(c['captured_artifacts']),['QQQ','SPY','tzif']);exact(plan['tzif_reference'],c['captured_artifacts']['tzif'])
    for ticker in ('QQQ','SPY'):
        evidence=plan['source_evidence'][ticker];exact(evidence['new_session_dates'],[session])
        exact(evidence['source_reference'],c['captured_artifacts'][ticker])
        exact(evidence['accounted_baseline_reference'],view['accounted_baseline_references'][ticker])
        exact(evidence['actual_baseline_reference'],view['baseline_references'][ticker])
        exact(c['current_cache_references'][ticker],dict(path=str(CURRENT[ticker]),sha256=c['captured_artifacts'][ticker]['sha256']))
    return session,view



def inspect(payload,receipt,started,docs,refs,payload_reference,blobs,session,checker,inventory,parent_checker):
    """All supplied blobs must come from wrapper-verified external byte references."""
    parent,capture_env=docs['parent'],docs['capture']
    actual_session,view=validate_capture(parent,capture_env,checker,parent_checker)
    exact(session,actual_session,'Captured session');known=view['known_typed_rows'];first=view['first_actual_observed_session_by_month']
    for role,env in (('parent',parent),('capture',capture_env)):exact(refs[role],{k:env[k]for k in ROLES},'Externally supplied envelope roles')
    dates=[r['session']for r in known];claims={}
    for r in known:ref({k:r['evidence_reference'][k]for k in ('path','sha256')},claims)
    prior_attempts=parent['document']['history']['parent_attempt_inventory']
    for a in prior_attempts:
        for k in ('payload_reference','receipt_reference','independent_readback_reference'):ref(a[k],claims)
    d=day(session);require(session>dates[-1],'New unique observation')
    capture=capture_env['document'];plan=capture['plan']
    exact(session,plan['candidate_session'],'Explicit captured candidate')
    require(payload['schema']=='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1' and receipt['schema']=='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1' and started['schema']=='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V4','Evidence schemas')
    require(receipt['status']=='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY','Persisted role')
    exact(receipt['payload_reference'],payload_reference,'External payload anchor');exact(payload['known_typed_rows_preserved'],known,'Entire original typed prefix');exact(payload['parent_attempt_inventory_preserved'],prior_attempts,'Entire resolved inventory')
    for r in (refs['parent']['reference'],refs['parent']['readback_reference'],refs['capture']['reference']):ref(r,claims)
    identity=dict(parent_reference=refs['parent']['reference'],capture_reference=refs['capture']['reference'],session=session)
    exact(payload['observation_identity'],identity,'Observation identity');identifier=sha(enc(identity));exact(payload['observation_id'],identifier,'Observation digest');exact(receipt['observation_id'],identifier,'Receipt same observation')
    exact(payload['session'],session,'Session');require(type(payload['sequence'])is int and payload['sequence']==len(known)+1,'Exact variable sequence');require(payload['kind']=='PROSPECTIVE_OBSERVED_SESSION' and payload['initial_seal_status']=='NOT_ATTEMPTED','No seal')
    exact(payload['parent_readback_reference'],refs['parent']['readback_reference'],'Parent audit')
    require(set(payload['full_original_sources_preserved'])==set(payload['selected_original_rows'])==set(payload['source_row_locations'])=={'QQQ','SPY'},'Two full sources')
    for ticker in ('QQQ','SPY'):
        exact(sorted(payload['full_original_sources_preserved'][ticker]),['baseline_sources','sources'],'Exact full-source roles')
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
        exact(obj['actual_parent_schema'],view['parent_schema'],'Actual parent version')
        exact(obj['local_direct_child_inventory_scope'],dict(root=str(RESEARCH),depth=1,semantic_writer_namespaces_scanned=True),'Local scope')
        exact(obj['external_parent_bound_attempt_inventory'],{path:value for path,value in inventory.items()if Path(path).parent.parent!=RESEARCH},'Bound external scope')
        require(obj['external_unregistered_attempt_discovery_performed']is False,'No external discovery')
    for obj in (started,receipt):exact(obj['source_hashes'],payload['source_hashes'],'Same source map');exact(obj['runtime'],payload['runtime'],'Same runtime claim')
    for obj,flags in ((payload,set(PAYLOAD_FALSE)|set(WRITER_FALSE)),(receipt,WRITER_FALSE),(started,WRITER_FALSE)):
        for k in flags:require(obj[k] is False,'No permission upgrade '+k)
    require(payload['payload_is_not_a_published_observation_receipt'] is True and payload['seal_status_history_not_created'] is True,'Payload boundary')
    return dict(parent_typed_row_count=len(known),parent_actual_observation_count=sum(r['kind']=='PROSPECTIVE_OBSERVED_SESSION'for r in known),parent_observed_count=sum(r['kind']!='MISSED_OBSERVATION'for r in known),parent_gap_count=sum(r['kind']=='MISSED_OBSERVATION'for r in known),new_observation_count=1,month_first_actual_observation=monthfirst==session,timing_classification=receipt['timing_classification'],clock_authenticity_verified=False,final_durable_completion_time_verified=False,candidate_seal_allowed=False,cohort_registration_allowed=False)


def decode(raw):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate JSON key');result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in()).throw(ValueError(x)))


def safe(path):
    path=Path(path);require(path.is_absolute(),'Absolute evidence path')
    for item in (path,*path.parents):require(not item.is_symlink()and not getattr(item,'is_junction',lambda:False)(),'Linked evidence path')
    return path


def consume(item,sources):
    ref(item,sources);path=safe(item['path']);no_live(sources)
    require(path.is_file()and path.stat().st_size<=64*1024**2 and not(path.parent/'failure.json').exists(),'Bounded nonfailed source')
    for previous,digest in sources.items():
        if Path(previous)==path:exact(digest,item['sha256'],'Alias digest')
    raw=path.read_bytes();exact(sha(raw),item['sha256'],'Immutable source SHA');return raw


def namespace(folder,names):
    entries=list(safe(folder).iterdir());exact(sorted(p.name for p in entries),sorted(names),'Exact evidence namespace')
    require(all(safe(p).is_file()for p in entries),'Regular namespace files')


def private_module(path,raw,digest,replacements=()):
    exact(sha(raw),digest,'Private source SHA');code=raw.decode('utf-8-sig')
    module=ModuleType('_independent_registered_observation_'+Path(path).stem);module.__file__=str(path)
    for line,key,value in replacements:
        require(code.count(line)==1,'Explicit private closure');code=code.replace(line,'');module.__dict__[key]=value
    exec(compile(code,str(path),'exec'),module.__dict__);return module


def envelope(refs,sources):
    env=deepcopy(refs)
    for key,role in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:
        env[key]=decode(consume(refs[role],sources));merge_claims(sources,env[key])
    consume(refs['reader_reference'],sources)
    for path,digest in list(sources.items()):consume(dict(path=path,sha256=digest),sources)
    return env


def attempt_inventory(parent,sources,output):
    """Discover local attempts; externally inspect only explicit parent entries."""
    entries=parent['document']['history']['observations'];allowed={e['payload_reference']['path']:e for e in entries}
    require(len(allowed)==len(entries),'Unique inherited attempts')
    local=list(safe(RESEARCH).iterdir());require(len(local)<=20000,'Bounded local namespace inventory')
    external={Path(e['payload_reference']['path']).parent for e in entries if Path(e['payload_reference']['path']).parent.parent!=RESEARCH}
    folders=local+sorted(external,key=str);found={}
    for folder in folders:
        safe(folder)
        if folder.resolve()==output.resolve()or not folder.is_dir():continue
        observed={}
        for name in ('started.json','observation_payload.json','receipt.json','failure.json'):
            path=safe(folder/name)
            if not path.exists():continue
            require(path.is_file()and path.stat().st_size<=64*1024**2,'Bounded attempt record')
            raw=path.read_bytes();observed[name]=(decode(raw),dict(path=str(path),sha256=sha(raw)))
        get=lambda name:observed.get(name,({},{}))[0]
        semantic=(get('started.json').get('schema','').startswith('PROSPECTIVE_OBSERVATION_WRITER_STARTED_')or
            get('observation_payload.json').get('schema')=='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1'or
            get('receipt.json').get('schema')=='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1'or
            get('failure.json').get('status')=='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY')
        if not semantic:
            require(folder not in external,'Inherited attempt not recognizable');continue
        require(set(observed)=={'started.json','observation_payload.json','receipt.json'}and not(folder/'failure.json').exists(),'Unresolved prior attempt')
        namespace(folder,('started.json','observation_payload.json','receipt.json','independent_readback.json'))
        payload,payload_ref=observed['observation_payload.json'];receipt,receipt_ref=observed['receipt.json']
        require(payload_ref['path']in allowed and payload_ref['path']not in found,'Unaccounted or duplicate attempt')
        entry=allowed[payload_ref['path']];exact(payload_ref,entry['payload_reference']);exact(receipt_ref,entry['receipt_reference'])
        exact(entry['audit_reference']['path'],str(folder/'independent_readback.json'),'Colocated inherited audit')
        audit=decode(consume(entry['audit_reference'],sources));exact(audit['source_hashes'],entry['original_source_hash_claims']['audit'])
        start=observed['started.json'][1];exact(audit['source_hashes'].get(start['path']),start['sha256'],'Inherited observed START hash')
        exact(payload['observation_id'],entry['observation_id']);exact(receipt['payload_reference'],payload_ref)
        found[payload_ref['path']]={name:item for name,(_,item)in observed.items()}
        for _,item in observed.values():ref(item,sources)
    exact(sorted(found),sorted(allowed),'Every parent-bound actual attempt');return found


def guard(sources):
    for path,digest in list(sources.items()):consume(dict(path=path,sha256=digest),{})


def load_inputs(registration_path,registration_sha256):
    writer_ref=dict(path=str(WRITER),sha256=WRITER_SHA);registration_ref=dict(path=str(registration_path),sha256=registration_sha256)
    regref=dict(zip(('path','sha256'),map(str,REGISTRATION_CORE)));refref=dict(zip(('path','sha256'),map(str,REFERENCE_CORE)))
    deps={key:dict(path=str(path),sha256=digest)for key,(path,digest)in DEPENDENCIES.items()}
    for item in (writer_ref,registration_ref,regref,refref,*deps.values()):ref(item,{})
    sources={};consume(writer_ref,sources)
    references=private_module(REFERENCE_CORE[0],consume(refref,sources),REFERENCE_CORE[1])
    registration_core=private_module(REGISTRATION_CORE[0],consume(regref,sources),REGISTRATION_CORE[1],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',references)])
    exact(registration_core.REFERENCE_KERNEL_SHA256,REFERENCE_CORE[1])
    registered=registration_core.prepare_observation_runtime(registration=decode(consume(registration_ref,sources)),
        registration_reference=registration_ref,runtime_reference=writer_ref,dependency_references=deps,research_root=str(RESEARCH))
    output=safe(registered['output_directory']);parents,captures=registered['parent'],registered['capture']
    raw={key:consume(item,sources)for key,item in deps.items()}
    helper=private_module(DEPENDENCIES['compact_helpers'][0],raw['compact_helpers'],DEPENDENCIES['compact_helpers'][1])
    parent_checker=private_module(DEPENDENCIES['parent_view'][0],raw['parent_view'],DEPENDENCIES['parent_view'][1],[
        ('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',helper)])
    exact(parent_checker.DEPENDENCY_SHA256,DEPENDENCIES['compact_helpers'][1])
    checker=private_module(DEPENDENCIES['capture_checker'][0],raw['capture_checker'],DEPENDENCIES['capture_checker'][1])
    csv_rows=private_module(DEPENDENCIES['csv_reader'][0],raw['csv_reader'],DEPENDENCIES['csv_reader'][1]).csv_rows
    parent=envelope(parents,sources);capture=envelope(captures,sources);session,view=validate_capture(parent,capture,checker,parent_checker)
    pf=Path(parents['reference']['path']).parent;cf=Path(captures['reference']['path']).parent;pa=Path(parents['readback_reference']['path']).parent;ca=Path(captures['readback_reference']['path']).parent
    for item,path in [(parents['reference'],pf/'history.json'),(parents['publication_reference'],pf/'publication.json'),
            (parents['readback_reference'],pa/'independent_readback.json'),(captures['reference'],cf/'capture.json'),
            (captures['publication_reference'],cf/'publication.json'),(captures['readback_reference'],ca/'independent_readback.json')]:exact(item['path'],str(path))
    groups=[(pf,{'started.json','history.json','publication.json'}|({'independent_readback.json'}if pa==pf else set())),
        (cf,{'started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'}),(ca,{'started.json','independent_readback.json'})]
    if pa!=pf:groups.append((pa,{'started.json','independent_readback.json'}))
    def namespaces(pin=False):
        for folder,names in groups:
            namespace(folder,names)
            if pin:
                for path in folder.iterdir():
                    require(safe(path).is_file()and path.stat().st_size<=64*1024**2,'Bounded upstream inventory')
                    consume(dict(path=str(path),sha256=sha(path.read_bytes())),sources)
    namespaces(True);c=capture['document']
    cr=c['input_references']['registration_core'];capture_registration=decode(consume(c['input_references']['registration'],sources))
    capture_reg=private_module(cr['path'],consume(cr,sources),cr['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',references)])
    exact(capture_reg.REFERENCE_KERNEL_SHA256,REFERENCE_CORE[1])
    cp=capture_reg.prepare_forward_capture_runtime(registration=capture_registration,registration_reference=c['input_references']['registration'],
        runtime_reference=c['input_references']['runtime'],dependency_references=c['input_references']['dependencies'],research_root=str(RESEARCH))
    exact(cp['parent'],parents);exact(cp['output_directory'],str(cf))
    blobs={}
    for t in ('QQQ','SPY','tzif'):
        item=c['captured_artifacts'][t];exact(item['path'],str(cf/('New_York.tzif'if t=='tzif'else t+'.csv')));blobs[item['path']]=consume(item,sources)
    for item in (*view['accounted_baseline_references'].values(),*view['baseline_references'].values()):blobs[item['path']]=consume(item,sources)
    plan=checker.reconstruct_plan(parent=parent,source_bytes={t:blobs[c['captured_artifacts'][t]['path']]for t in ('QQQ','SPY')},
        source_references={t:c['captured_artifacts'][t]for t in ('QQQ','SPY')},accounted_baseline_bytes={t:blobs[view['accounted_baseline_references'][t]['path']]for t in ('QQQ','SPY')},
        actual_baseline_bytes={t:blobs[view['baseline_references'][t]['path']]for t in ('QQQ','SPY')},capture_started_at=c['capture_started_at'],capture_completed_at=c['capture_completed_at'],
        tzif_bytes=blobs[c['captured_artifacts']['tzif']['path']],tzif_reference=c['captured_artifacts']['tzif'],parent_checker=parent_checker,csv_rows=csv_rows)
    exact(plan,c['plan'],'Whole saved capture plan');inventory=attempt_inventory(parent,sources,output)
    def final_guard():namespaces();exact(attempt_inventory(parent,{},output),inventory,'Attempt drift');guard(sources)
    final_guard();refs=dict(parent=parents,capture=captures,dependencies=deps,registration=registration_ref,runtime=writer_ref,
        registration_core=regref,reference_core=refref)
    return dict(parent=parent,capture=capture),refs,blobs,sources,checker,parent_checker,inventory,final_guard,output,session


def save(path,value):
    raw=enc(value)
    if path.name!='failure.json':require(shutil.disk_usage(path.anchor).free>=5*1024**3+len(raw),'Resource stop before write')
    with safe(path).open('xb')as stream:require(stream.write(raw)==len(raw),'Complete write');stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Durable saved bytes');return dict(path=str(path),sha256=sha(raw))


def readback(*,registration_path,registration_sha256,payload_reference,receipt_reference,execute=False):
    require(type(execute)is bool,'Explicit bool')
    if not execute:return dict(status='NOT_EXECUTED')
    for item in (payload_reference,receipt_reference):ref(item,{})
    docs,refs,blobs,producer_sources,checker,parent_checker,inventory,final_guard,output,session=load_inputs(registration_path,registration_sha256)
    exact(payload_reference['path'],str(output/'observation_payload.json'));exact(receipt_reference['path'],str(output/'receipt.json'))
    namespace(output,('started.json','observation_payload.json','receipt.json'))
    try:
        sources=deepcopy(producer_sources);payload=decode(consume(payload_reference,sources));receipt=decode(consume(receipt_reference,sources))
        sp=safe(output/'started.json');require(sp.is_file()and sp.stat().st_size<=64*1024**2,'Bounded writer START')
        sb=sp.read_bytes();sr=dict(path=str(sp),sha256=sha(sb));started=decode(consume(sr,sources))
        for obj in (payload,receipt,started):exact(obj['source_hashes'],producer_sources,'Whole producer source closure')
        counts=inspect(payload,receipt,started,docs,refs,payload_reference,blobs,session,checker,inventory,parent_checker)
        metadata={key:payload[key]for key in ('writer_adapter_schema','actual_parent_schema','input_references','source_hashes','runtime',
            'capture_checker_reference','attempt_inventory_scope','local_attempt_namespace_inventory','local_direct_child_inventory_scope',
            'external_parent_bound_attempt_inventory','external_unregistered_attempt_discovery_performed')}
        require(type(metadata['runtime'])is dict and set(metadata['runtime'])=={'python','executable','implementation'}and
            all(type(v)is str and 0<len(v)<10000 for v in metadata['runtime'].values()),'Bounded declared runtime')
        exact(started,dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V4',writer_started_at_utc=payload['writer_started_at_utc'],**metadata,**dict.fromkeys(WRITER_FALSE,False)))
        exact(receipt,dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY',
            observation_id=payload['observation_id'],payload_reference=payload_reference,publication_check_at_utc=receipt['publication_check_at_utc'],
            publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE',timing_classification=counts['timing_classification'],
            month_first_actual_observation=counts['month_first_actual_observation'],**metadata,**dict.fromkeys(WRITER_FALSE,False)))
        corekeys={'schema','observation_id','observation_identity','session','sequence','kind','initial_seal_status','month_first_actual_observation',
            'first_actual_observed_session_of_month','timing_classification','capture_started_at_utc','capture_completed_at_utc','writer_started_at_utc',
            'writer_completed_at_utc','conservative_close_utc','conservative_deadline_utc','selected_original_rows','source_row_locations',
            'full_original_sources_preserved','tzif_reference','tzif_bytes_base64','parent_readback_reference','known_typed_rows_preserved',
            'parent_attempt_inventory_preserved','source_hash_claims','payload_is_not_a_published_observation_receipt','seal_status_history_not_created'}
        exact(sorted(payload),sorted(corekeys|set(metadata)|set(PAYLOAD_FALSE)|set(WRITER_FALSE)|{'writer_interval_role'}),'Entire supported payload shape')
        final_guard();guard(sources)
        report=save(output/'independent_readback.json',dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3',status='PASS',
            writer_adapter_schema=ADAPTER,actual_parent_schema=metadata['actual_parent_schema'],payload_reference=payload_reference,receipt_reference=receipt_reference,
            parent_history_reference=refs['parent']['reference'],input_references=refs,started_current_bytes_reference=sr,started_external_sha_authenticated=False,
            reader_sha256=LOADED,source_hashes={**sources,str(SOURCE):LOADED},counts=counts,writer_called=False,payload_core_called=False,
            shared_upstream_capture_checker_reference=dict(zip(('path','sha256'),CHECKER)),shared_upstream_parent_checker_reference=refs['dependencies']['parent_view'],
            attempt_inventory_scope=INVENTORY_SCOPE,local_attempt_namespace_inventory=inventory,
            local_direct_child_inventory_scope=metadata['local_direct_child_inventory_scope'],external_parent_bound_attempt_inventory=metadata['external_parent_bound_attempt_inventory'],
            external_unregistered_attempt_discovery_performed=False,old_audit_repeated=False,exchange_holidays_verified=False,early_closes_verified=False,
            final_durable_completion_time_verified=False,**dict.fromkeys(WRITER_FALSE,False)))
        final_guard();guard(sources);consume(sr,{});consume(report,{});consume(dict(path=str(SOURCE),sha256=LOADED),{})
        namespace(output,('started.json','observation_payload.json','receipt.json','independent_readback.json'));return report
    except BaseException as error:
        if not(output/'failure.json').exists():save(output/'failure.json',dict(status='INDEPENDENT_READBACK_FAILED_NO_RETRY',error_type=type(error).__name__,retry_allowed=False,
            partial_evidence_preserved=True,**dict.fromkeys(WRITER_FALSE,False)))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    for name in ('registration-path','registration-sha256','payload-path','payload-sha256','receipt-path','receipt-sha256'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();print(json.dumps(readback(registration_path=args.registration_path,registration_sha256=args.registration_sha256,
        payload_reference=dict(path=args.payload_path,sha256=args.payload_sha256),receipt_reference=dict(path=args.receipt_path,sha256=args.receipt_sha256),execute=args.execute)))

