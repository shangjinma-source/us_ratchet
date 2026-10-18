"""V5 capture independent reconstruction; shared normalized parent inspector.

The IO adapter requires a frozen publisher anchor before any source read.
No producer or capture kernel is imported or executed.
"""
import argparse
from copy import deepcopy
from datetime import datetime,date,time,timezone,timedelta
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
from types import ModuleType
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESEARCH=ROOT/'data/cache/research'
CURRENT={t:ROOT/'data/cache'/f'{t}.csv'for t in ('QQQ','SPY')}
PRODUCER=ROOT/'scripts/ndx_registered_forward_capture_runtime_20261009_v2.py'
PRODUCER_SHA='915fda6119f9ba1ce4e966a6557c18e2d0840dd7f40269dadc22bf2fd30b530f'
REGISTRATION_CORE=(ROOT/'backtest/ndx_forward_capture_runtime_registration_research_v2.py','fc907ddff33988b3f3e29f4585c32ae7b2e743ea9f6abe29055772ce0f0876cd')
REFERENCE_CORE=(ROOT/'backtest/ndx_compact_history_runtime_registration_research_v1.py','d0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')
DEPENDENCIES={
 'capture_core':('backtest/ndx_forward_parent_capture_research_v5.py','ddd570ab3a79832ef6d530693ade9ac37b8f82c18b13efe322558099a04a7e5e'),
 'parent_view':('backtest/ndx_prospective_history_parent_view_research_v5.py','32bcabfbc08a63607b650141f7295fc1ed12a3fdeeb081527c8b32d8cc250373'),
 'legacy_view':('backtest/ndx_prospective_observation_parent_history_research_v4.py','06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'),
 'compact_helpers':('backtest/ndx_prospective_observation_parent_history_research.py','1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'),
 'base':('backtest/ndx_forward_source_capture_research.py','30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'),
 'scoped':('backtest/ndx_forward_source_capture_scoped_research.py','9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee')}
PREFIX_CORE=(ROOT/'backtest/ndx_accounted_source_prefix_research_v1.py','5602376c97e654ba665ba2d4f711ee73171364a17d977cc9588ad51c385d8c9b')
GAP_CORE=(ROOT/'backtest/ndx_prospective_gap_history_research_v5.py','11a8826b1c5f27201730afc1c482b29520fd2047115b4249fb003388f87a6592')
MAX_PARENT_DEPTH=128
CSV_READER=(ROOT/'backtest/ndx_capture_source_csv_independent_reconstruction_research_v1.py','c9dbb1c15c12d84910842874d1800d09c73d90893b91d54865826bf240ef9787')
ROLES=('reference','publication_reference','readback_reference','reader_reference')
PURE_FALSE=('source_authenticity_verified','parent_history_authenticated_by_this_module','clock_authenticity_verified',
 'timeliness_verified','filesystem_attempt_inventory_authenticated','observation_created','candidate_seal_allowed',
 'cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','future_independent_oos',
 'production_generator_authorized','old_calendar_mutated','full_transitive_source_closure_reverified','network_capture_performed',
 'seal_event_created','partial_recovery_performed','canonical_calendar_append_allowed','retrospective_backfill_allowed',
 'decision_eligible','exchange_holidays_and_early_closes_verified')
FALSE_FIELDS=PURE_FALSE+('network_quote_refresh_performed',)


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(left,right):require(encode(left)==encode(right),'Independent exact value mismatch')


def decode(raw):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate JSON key');result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in()).throw(ValueError(v)))


def reference(path,digest):
    require(type(path)is str and path and path.strip()==path and '\x00'not in path,'Reference path')
    require(type(digest)is str and re.fullmatch('[0-9a-f]{64}',digest)is not None,'Pending immutable anchor')
    return dict(path=path,sha256=digest)


def merge(sources,item):
    require(type(item)is dict and set(item)=={'path','sha256'},'Exact reference')
    reference(item['path'],item['sha256'])
    require(item['path']not in sources or sources[item['path']]==item['sha256'],'Source conflict')
    sources[item['path']]=item['sha256']


def utc(value):
    require(type(value)is str,'UTC clock string');parsed=datetime.fromisoformat(value)
    require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds()==0,'Explicit UTC clock')
    return parsed.astimezone(timezone.utc)


def private_module(path,raw,digest,replacements=()):
    exact(sha(raw),digest);code=raw.decode('utf-8-sig')
    module=ModuleType('_independent_registered_capture_'+Path(path).stem);module.__file__=str(path)
    for line,attribute,value in replacements:
        require(code.count(line)==1,'Explicit private closure');code=code.replace(line,'');module.__dict__[attribute]=value
    exec(compile(code,str(path),'exec'),module.__dict__);return module


def reconstruct_plan(*,parent,source_bytes,source_references,accounted_baseline_bytes,actual_baseline_bytes,
        capture_started_at,capture_completed_at,tzif_bytes,tzif_reference,parent_checker,csv_rows):
    view=parent_checker.inspect_parent_history_v5(parent);days=[r['session']for r in view['known_typed_rows']]
    previous_suffix=view['pending_source_sessions']+view['excluded_not_completed_source_sessions']
    previous_full_dates=days+[item['session']for item in previous_suffix]
    sources=deepcopy(view['source_hashes'])
    for pair in (source_bytes,source_references,accounted_baseline_bytes,actual_baseline_bytes,
                 view['accounted_baseline_references'],view['baseline_references']):
        require(type(pair)is dict and set(pair)=={'QQQ','SPY'},'Exact source pair')
    begin,end=utc(capture_started_at),utc(capture_completed_at);require(begin<=end,'Capture clock reversal')
    require(all(begin>=utc(item['capture_completed_at_utc'])for item in previous_suffix),'Capture clock precedes saved source suffix')
    merge(sources,tzif_reference);exact(tzif_reference['sha256'],view['tzif_reference']['sha256']);exact(sha(tzif_bytes),tzif_reference['sha256'])
    zone=ZoneInfo.from_file(BytesIO(tzif_bytes),key='America/New_York')
    close=lambda session:datetime.combine(date.fromisoformat(session),time(16),zone).astimezone(timezone.utc)
    require(begin>=close(days[-1]),'Capture precedes accounted close')
    diagnostics=[];evidence={};new={}
    for ticker in ('QQQ','SPY'):
        old,actual,current=accounted_baseline_bytes[ticker],actual_baseline_bytes[ticker],source_bytes[ticker]
        for raw,item in ((old,view['accounted_baseline_references'][ticker]),(actual,view['baseline_references'][ticker]),(current,source_references[ticker])):
            merge(sources,item);require(type(raw)is bytes,'Raw CSV bytes');exact(sha(raw),item['sha256'])
        oldrows,_=csv_rows(old,days[0]);actualrows,_=csv_rows(actual,days[0]);rows,issues=csv_rows(current,days[0])
        scoped=lambda values:[row['Date']for row in values if row['Date']>=days[0]]
        require(scoped(oldrows)==days,'BASELINE_HAS_UNACCOUNTED_SUFFIX')
        require(old.startswith(actual)and scoped(actualrows)==[day for day in days if day<=view['last_observed_session']],'Complete last actual baseline prefix')
        currentdays=scoped(rows)
        if not current.startswith(old)or currentdays[:len(days)]!=days:diagnostics.append(dict(reason='ACCOUNTED_BASELINE_PREFIX_REVISED',ticker=ticker))
        if previous_suffix and currentdays[:len(previous_full_dates)]!=previous_full_dates:diagnostics.append(dict(reason='PREVIOUSLY_CAPTURED_SOURCE_SESSIONS_WITHDRAWN_OR_CHANGED',ticker=ticker))
        new[ticker]=currentdays[len(days):]if currentdays[:len(days)]==days else []
        evidence[ticker]=dict(source_reference=deepcopy(source_references[ticker]),
            accounted_baseline_reference=deepcopy(view['accounted_baseline_references'][ticker]),actual_baseline_reference=deepcopy(view['baseline_references'][ticker]),
            original_row_count=len(rows),source_session_dates=currentdays,new_session_dates=new[ticker],full_accounted_bytes_prefix_matches=current.startswith(old),
            included_original_row_indexes=[i for i,row in enumerate(rows)if row['Date']>=days[0]],
            excluded_original_row_indexes=[i for i,row in enumerate(rows)if row['Date']<days[0]],excluded_before_scope_ohlc_diagnostics=issues)
    if new['QQQ']!=new['SPY']:diagnostics.append(dict(reason='ASYMMETRIC_NEW_SESSION_DATES'))
    if any(len(values)>1 for values in new.values()):diagnostics.append(dict(reason='MULTIPLE_UNACCOUNTED_SESSIONS'))
    candidate=new['QQQ'][0]if not diagnostics and len(new['QQQ'])==1 else None
    if candidate and begin<close(candidate):diagnostics.append(dict(reason='SOURCE_SESSION_NOT_COMPLETED_AT_CAPTURE_START'));candidate=None
    return dict(schema='FORWARD_PARENT_CAPTURE_PLAN_V5',status='BLOCKED_SOURCE_DIAGNOSTICS'if diagnostics else
        'ONE_NEW_SESSION_CAPTURE_CANDIDATE'if candidate else 'NO_NEW_SESSION',diagnostics=diagnostics,candidate_session=candidate,
        policy_id=view['policy_id'],parent_references={role:deepcopy(parent[role])for role in ROLES},actual_parent_schema=view['parent_schema'],
        parent_full_capture_source_references=deepcopy(view['full_capture_source_references']),
        parent_pending_source_sessions=deepcopy(view['pending_source_sessions']),parent_excluded_not_completed_source_sessions=deepcopy(view['excluded_not_completed_source_sessions']),
        known_typed_rows=deepcopy(view['known_typed_rows']),observations=deepcopy(view['observations']),parent_attempt_inventory=deepcopy(view['parent_attempt_inventory']),
        first_actual_observed_session_by_month=deepcopy(view['first_actual_observed_session_by_month']),
        baseline_references=deepcopy(view['baseline_references']),baseline_role=view['baseline_role'],
        accounted_baseline_references=deepcopy(view['accounted_baseline_references']),accounted_baseline_role='FULL_SAVED_CSV_SCOPE_EQUALS_ALL_KNOWN_TYPED_SESSIONS',
        last_accounted_session=view['last_accounted_session'],last_observed_session=view['last_observed_session'],source_evidence=evidence,
        source_reference_claims=sources,capture_started_at=begin.isoformat(),capture_completed_at=end.isoformat(),tzif_reference=deepcopy(tzif_reference),
        candidate_conservative_close_utc=close(candidate).isoformat()if candidate else None,
        timing_semantics='CALLER_SUPPLIED_CLOCK_CONSERVATIVE_16_NY_CLOSE_NOT_AUTHENTICATED_EXCHANGE_CALENDAR',late_observation_classification_deferred_to_payload_core=True,
        authentication_role='STRUCTURAL_DECLARATIONS_AND_SUPPLIED_BYTES_ONLY_NO_IO_AUTHENTICATION',raw_source_bytes_embedded=False,
        dependency_sha256={role:DEPENDENCIES[key][1]for role,key in [('scoped','scoped'),('base','base'),('parent_view','parent_view'),('legacy_view','legacy_view'),('compact_helpers','compact_helpers')]},
        **dict.fromkeys(PURE_FALSE,False))


def private_parent_checker(raw):
    """Privately compile only shared parent inspectors, never capture planning."""
    helper=private_module(ROOT/DEPENDENCIES['compact_helpers'][0],raw['compact_helpers'],DEPENDENCIES['compact_helpers'][1])
    legacy=private_module(ROOT/DEPENDENCIES['legacy_view'][0],raw['legacy_view'],DEPENDENCIES['legacy_view'][1],[
        ('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',helper)])
    return private_module(ROOT/DEPENDENCIES['parent_view'][0],raw['parent_view'],DEPENDENCIES['parent_view'][1],[
        ('from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy','legacy',legacy)])


def safe(path):
    path=Path(path);require(path.is_absolute(),'Absolute source/output path')
    for item in (path,*path.parents):require(not item.is_symlink()and not getattr(item,'is_junction',lambda:False)(),'Linked source/output path')
    return path


def consume(item,sources):
    merge(sources,item);path=safe(item['path'])
    require(path.is_file()and path.stat().st_size<=64*1024**2 and not(path.parent/'failure.json').exists(),'Bounded nonfailed source')
    forbidden={p.resolve()for p in CURRENT.values()}|{(ROOT/'data/cache'/f'{t}.csv').resolve()for t in ('QQQ','SPY')}
    require(path.resolve()not in forbidden,'No current cache read or permanent claim')
    for old,digest in sources.items():
        if Path(old)==path:exact(digest,item['sha256'])
    raw=path.read_bytes();exact(sha(raw),item['sha256']);return raw


def namespace(folder,names):
    items=list(safe(folder).iterdir());exact(sorted(p.name for p in items),sorted(names))
    require(all(safe(p).is_file()for p in items),'Regular namespace inventory')


def parent_inventories(refs,sources):
    folder=Path(refs['reference']['path']).parent;audit=Path(refs['readback_reference']['path']).parent
    exact(refs['reference']['path'],str(folder/'history.json'));exact(refs['publication_reference']['path'],str(folder/'publication.json'))
    exact(refs['readback_reference']['path'],str(audit/'independent_readback.json'))
    document=decode(consume(refs['reference'],{}));schema=document['history']['schema']
    require(schema in ('PROSPECTIVE_GAP_EXTENSION_HISTORY_V3','PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V4','PROSPECTIVE_GAP_EXTENSION_HISTORY_V5'),'True supported parent schema')
    names={'started.json','history.json','publication.json'}
    if schema=='PROSPECTIVE_GAP_EXTENSION_HISTORY_V5':names|={ticker+suffix for ticker in ('QQQ','SPY')for suffix in ('.accounted_prefix.csv','.prefix_evidence.json')}
    namespace(folder,names|({'independent_readback.json'}if folder==audit else set()))
    if folder!=audit:namespace(audit,('started.json','independent_readback.json'))
    for parent in {folder,audit}:
        for path in parent.iterdir():
            require(safe(path).is_file()and path.stat().st_size<=64*1024**2,'Bounded parent inventory')
            consume(reference(str(path),sha(path.read_bytes())),sources)


def guard(sources):
    for path,digest in list(sources.items()):consume(reference(path,digest),{})


def save(path,value):
    raw=encode(value)
    if path.name!='failure.json':require(shutil.disk_usage(path.anchor).free>=5*1024**3+len(raw),'Resource stop before write')
    with safe(path).open('xb')as stream:
        require(stream.write(raw)==len(raw),'Complete write');stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Durable saved bytes');return reference(str(path),sha(raw))


def load_parent_envelope(refs,sources):
    require(type(refs)is dict and set(refs)==set(ROLES),'Four upstream parent references')
    result=deepcopy(refs)
    for field,role in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:
        result[field]=decode(consume(refs[role],sources))
        for path,digest in result[field]['source_hashes'].items():consume(reference(path,digest),sources)
    consume(refs['reader_reference'],sources)
    return result


def private_prefix_checker(raw,sources):
    base=private_module(ROOT/DEPENDENCIES['base'][0],raw['base'],DEPENDENCIES['base'][1])
    scoped=private_module(ROOT/DEPENDENCIES['scoped'][0],raw['scoped'],DEPENDENCIES['scoped'][1],[
        ('from backtest import ndx_forward_source_capture_research as capture','capture',base)])
    return private_module(PREFIX_CORE[0],consume(reference(str(PREFIX_CORE[0]),PREFIX_CORE[1]),sources),PREFIX_CORE[1],[
        ('from backtest import ndx_forward_source_capture_scoped_research as scoped_parser','scoped_parser',scoped)])


def require_nested_reference_closure(value,sources):
    if type(value)is dict:
        if 'path'in value and 'sha256'in value:
            item=reference(value['path'],value['sha256']);exact(sources.get(item['path']),item['sha256'])
        for child in value.values():require_nested_reference_closure(child,sources)
    elif type(value)is list:
        for child in value:require_nested_reference_closure(child,sources)


def verify_prior_capture(h,prior,parent_checker,csv_rows,sources):
    refs=h['capture_references'];docs={}
    for key,role in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:
        docs[key]=decode(consume(refs[role],sources))
        for path,digest in docs[key]['source_hashes'].items():consume(reference(path,digest),sources)
    consume(refs['reader_reference'],sources)
    d,p,a=(docs[key]for key in ('document','publication','readback'))
    version={ 'SOURCE_BOUND_FORWARD_CAPTURE_V4':'V4','SOURCE_BOUND_FORWARD_CAPTURE_V5':'V5'}.get(d.get('schema'))
    require(version is not None,'Original capture genuine V4/V5 schema')
    exact(p['schema'],'FORWARD_CAPTURE_PUBLICATION_'+version);exact(p['status'],'PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION')
    exact(p['capture_reference'],refs['reference']);exact(p['source_hashes'],d['source_hashes'])
    exact(a['schema'],'FORWARD_CAPTURE_INDEPENDENT_READBACK_'+version);exact(a['status'],'PURE_FORWARD_CAPTURE_READBACK_PASS')
    exact(a['capture_reference'],refs['reference']);exact(a['publication_reference'],refs['publication_reference'])
    exact(a['reader_sha256'],refs['reader_reference']['sha256'])
    exact(d['parent_references'],h['parent_references']);exact(a['parent_references'],h['parent_references'])
    exact(d['plan']['parent_references'],h['parent_references'])
    for field in ('capture_started_at','capture_completed_at'):exact(d[field],h[field]);exact(d['plan'][field],h[field])
    exact(d['plan']['source_evidence'],h['source_evidence'])
    for item in (d,p,a):
        for field in FALSE_FIELDS:require(item.get(field)is False,'Upstream capture strict authority '+field)
    artifacts=d['captured_artifacts'];require(set(artifacts)=={'QQQ','SPY','tzif'},'Exact original capture artifacts')
    for ticker in ('QQQ','SPY'):exact(artifacts[ticker],h['full_capture_source_references'][ticker])
    exact(artifacts['tzif'],h['tzif_reference'])
    view=parent_checker.inspect_parent_history_v5(prior)
    rebuilt=reconstruct_plan(parent=prior,source_bytes={t:consume(artifacts[t],sources)for t in ('QQQ','SPY')},
        source_references={t:artifacts[t]for t in ('QQQ','SPY')},
        accounted_baseline_bytes={t:consume(view['accounted_baseline_references'][t],sources)for t in ('QQQ','SPY')},
        actual_baseline_bytes={t:consume(view['baseline_references'][t],sources)for t in ('QQQ','SPY')},
        capture_started_at=d['capture_started_at'],capture_completed_at=d['capture_completed_at'],
        tzif_bytes=consume(artifacts['tzif'],sources),tzif_reference=artifacts['tzif'],parent_checker=parent_checker,csv_rows=csv_rows)
    if version=='V4':
        rebuilt['schema']='FORWARD_PARENT_CAPTURE_PLAN_V4'
        for field in ('actual_parent_schema','parent_full_capture_source_references','parent_pending_source_sessions','parent_excluded_not_completed_source_sessions'):rebuilt.pop(field)
        rebuilt['dependency_sha256'].pop('legacy_view');rebuilt['dependency_sha256']['parent_view']=DEPENDENCIES['legacy_view'][1]
    exact(d['plan'],rebuilt)
    for field in ('input_references','parent_references','captured_artifacts','plan'):require_nested_reference_closure(d[field],d['source_hashes'])
    require_nested_reference_closure(a,a['source_hashes'])
    for path,digest in d['source_hashes'].items():exact(a['source_hashes'].get(path),digest)
    for role in ('reference','publication_reference','reader_reference'):
        exact(a['source_hashes'].get(refs[role]['path']),refs[role]['sha256'])
    diagnostic=d['current_cache_references'];require(type(diagnostic)is dict and set(diagnostic)=={'QQQ','SPY'},'Original diagnostic pair')
    for ticker,item in diagnostic.items():merge({},item);exact(item['sha256'],artifacts[ticker]['sha256'])
    exact(d,dict(schema='SOURCE_BOUND_FORWARD_CAPTURE_'+version,plan=rebuilt,parent_references=h['parent_references'],
        input_references=d['input_references'],captured_artifacts=artifacts,current_cache_references=d['current_cache_references'],
        current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',
        capture_started_at=h['capture_started_at'],capture_completed_at=h['capture_completed_at'],clock_captured_by_runner=True,
        external_clock_attestation_verified=False,quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',
        source_hashes=d['source_hashes'],**dict.fromkeys(FALSE_FIELDS,False)))
    exact(p,dict(schema='FORWARD_CAPTURE_PUBLICATION_'+version,status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION',
        capture_reference=refs['reference'],source_hashes=d['source_hashes'],**dict.fromkeys(FALSE_FIELDS,False)))
    exact(a['input_references'],d['input_references']);require(a.get('external_clock_attestation_verified')is False,'No upstream external clock authentication')
    counts=dict(status=rebuilt['status'],parent_typed_row_count=len(rebuilt['known_typed_rows']),parent_actual_observation_count=len(rebuilt['observations']),
        parent_observed_count=sum(row['kind']!='MISSED_OBSERVATION'for row in rebuilt['known_typed_rows']),
        parent_gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in rebuilt['known_typed_rows']),candidate_session=rebuilt['candidate_session'],
        diagnostic_count=len(rebuilt['diagnostics']),snapshot_counts={t:rebuilt['source_evidence'][t]['original_row_count']for t in ('QQQ','SPY')})
    exact(a['counts'],counts)
    for field in ('entire_plan_independently_reconstructed','snapshot_bytes_verified'):require(a.get(field)is True,'Capture readback evidence role')
    for field in ('producer_called','capture_core_called','current_live_cache_read_or_reverified'):require(a.get(field)is False,'Capture readback no execution')
    folder=Path(refs['reference']['path']).parent;audit=Path(refs['readback_reference']['path']).parent
    exact(refs['reference']['path'],str(folder/'capture.json'));exact(refs['publication_reference']['path'],str(folder/'publication.json'))
    exact(refs['readback_reference']['path'],str(audit/'independent_readback.json'))
    for ticker in ('QQQ','SPY'):exact(artifacts[ticker]['path'],str(folder/(ticker+'.csv')))
    exact(artifacts['tzif']['path'],str(folder/'New_York.tzif'))
    namespace(folder,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'))
    namespace(audit,('started.json','independent_readback.json'))
    for directory in (folder,audit):
        for path in directory.iterdir():
            path=safe(path);require(path.is_file()and path.stat().st_size<=64*1024**2,'Bounded upstream capture inventory')
            consume(reference(str(path),sha(path.read_bytes())),sources)


def verify_parent_chain(parent,parent_checker,prefix_checker,csv_rows,sources):
    """Independent original parent/prefix/timing checks; never calls gap append."""
    visited=set();inventories=[]
    for depth in range(MAX_PARENT_DEPTH):
        key=(parent['reference']['path'],parent['reference']['sha256']);require(key not in visited,'Parent reference cycle');visited.add(key)
        parent_refs={role:parent[role]for role in ROLES};parent_inventories(parent_refs,sources);inventories.append(('parent',parent_refs))
        view=parent_checker.inspect_parent_history_v5(parent)
        if view['parent_schema']!='PROSPECTIVE_GAP_EXTENSION_HISTORY_V5':return inventories
        h=parent['document']['history'];prior=load_parent_envelope(h['parent_references'],sources)
        previous=parent_checker.inspect_parent_history_v5(prior)
        exact(parent_checker.parent_state_for_gap(previous),h['prior_state_preserved'])
        verify_prior_capture(h,prior,parent_checker,csv_rows,sources);inventories.append(('capture',h['capture_references']))
        days=[row['session']for row in h['known_typed_rows']]
        history_folder=Path(parent['reference']['path']).parent
        for ticker in ('QQQ','SPY'):
            exact(h['accounted_prefix_references'][ticker]['path'],str(history_folder/(ticker+'.accounted_prefix.csv')))
            exact(h['accounted_prefix_evidence_references'][ticker]['path'],str(history_folder/(ticker+'.prefix_evidence.json')))
            full=consume(h['full_capture_source_references'][ticker],sources)
            prefix=consume(h['accounted_prefix_references'][ticker],sources)
            raw=consume(h['accounted_prefix_evidence_references'][ticker],sources)
            expected,evidence=prefix_checker.derive_accounted_prefix(source_bytes=full,source_reference=h['full_capture_source_references'][ticker],
                accounted_sessions=days,scope_start=days[0])
            require(prefix==expected and raw==encode(evidence)+b'\n','Exact original prefix and full evidence artifact')
            exact(parent_checker.prefix_evidence_summary(evidence),h['accounted_prefix_evidence'][ticker])
        zone=ZoneInfo.from_file(BytesIO(consume(h['tzif_reference'],sources)),key='America/New_York')
        begin,end=utc(h['capture_started_at']),utc(h['capture_completed_at'])
        categories=[[],[],[]]
        for index,session in enumerate(h['source_evidence']['QQQ']['new_session_dates']):
            day=date.fromisoformat(session);following=day+timedelta(days=1)
            while following.weekday()>4:following+=timedelta(days=1)
            close=datetime.combine(day,time(16),zone).astimezone(timezone.utc)
            deadline=datetime.combine(following,time(9,30),zone).astimezone(timezone.utc)
            category=2 if begin<close else 0 if begin>=deadline and end>=deadline else 1
            item=dict(session=session,conservative_close_utc=close.isoformat(),conservative_next_weekday_open_utc=deadline.isoformat(),
                capture_started_at_utc=begin.isoformat(),capture_completed_at_utc=end.isoformat(),source_session_pointer_by_ticker={
                    t:'/plan/source_evidence/'+t+'/new_session_dates/'+str(index)for t in ('QQQ','SPY')},counts_as_observed_session=False,
                consumes_month_first_opportunity=False,decision_eligible=False,classification=(
                    'MISSED_CONSERVATIVE_NEXT_OPEN_DEADLINE','DEADLINE_NOT_PASSED_FOR_ENTIRE_CAPTURE_INTERVAL','SOURCE_ROW_NOT_COMPLETED_AT_CAPTURE_START')[category])
            categories[category].append(item)
        for field,items in zip(('gap_classifications','pending_source_sessions','excluded_not_completed_source_sessions'),categories):exact(h[field],items)
        expected_sources=deepcopy(previous['source_hashes'])
        for item in (*h['capture_references'].values(),h['tzif_reference'],*h['full_capture_source_references'].values(),
                *previous['accounted_baseline_references'].values(),*previous['baseline_references'].values(),
                *h['accounted_prefix_references'].values(),*h['accounted_prefix_evidence_references'].values()):merge(expected_sources,item)
        known=deepcopy(previous['known_typed_rows'])
        for index,item in enumerate(categories[0]):known.append(dict(sequence=len(known)+1,session=item['session'],kind='MISSED_OBSERVATION',
            seal_status='NOT_ATTEMPTED',evidence_reference=dict(h['capture_references']['reference'],json_pointer='/plan/source_evidence/QQQ/new_session_dates/'+str(index))))
        gap_flags=dict.fromkeys(set(parent_checker.legacy.WRAPPER_FALSE)|set(parent_checker.legacy.compact.FLAGS),False)
        exact(h,dict(schema='PROSPECTIVE_GAP_EXTENSION_HISTORY_V5',status='GAP_EXTENSION_RESEARCH_ONLY'if categories[0]else'NO_EXPIRED_SESSION_TO_APPEND',
            policy_id=previous['policy_id'],parent_references=previous['parent_references'],capture_references=h['capture_references'],
            parent_state_reference=prior['reference'],prior_state_preserved=parent_checker.parent_state_for_gap(previous),known_typed_rows=known,
            known_typed_rows_preserved=previous['known_typed_rows'],observations=previous['observations'],parent_attempt_inventory=previous['parent_attempt_inventory'],
            first_actual_observed_session_by_month=previous['first_actual_observed_session_by_month'],genesis_preserved=previous['genesis_preserved'],
            baseline_references=previous['baseline_references'],baseline_role=previous['baseline_role'],full_capture_source_references=h['full_capture_source_references'],
            full_capture_source_role=parent_checker.FULL_CAPTURE_ROLE,accounted_prefix_references=h['accounted_prefix_references'],
            accounted_prefix_evidence=h['accounted_prefix_evidence'],accounted_prefix_evidence_references=h['accounted_prefix_evidence_references'],
            accounted_prefix_role=parent_checker.ACCOUNTED_PREFIX_ROLE,source_evidence=h['source_evidence'],gap_classifications=categories[0],
            pending_source_sessions=categories[1],excluded_not_completed_source_sessions=categories[2],last_observed_session=previous['last_observed_session'],
            last_accounted_session=known[-1]['session'],typed_row_count=len(known),parent_typed_row_count=previous['typed_row_count'],
            parent_actual_observation_count=previous['observation_count'],observation_count=previous['observation_count'],gap_count=previous['gap_count']+len(categories[0]),
            new_observation_count=0,new_missed_observation_count=len(categories[0]),capture_started_at=begin.isoformat(),capture_completed_at=end.isoformat(),
            tzif_reference=h['tzif_reference'],source_hashes=expected_sources,source_reference_claims=expected_sources,raw_source_bytes_embedded=False,**gap_flags))
        parent=prior
    raise ValueError('Parent chain maximum depth exceeded')


def readback(*,registration_path,registration_sha256,capture_reference,publication_reference,output_directory,execute=False):
    require(type(execute)is bool,'Explicit execution bool')
    if not execute:return dict(status='NOT_EXECUTED')
    producer_ref=reference(str(PRODUCER),PRODUCER_SHA);registration_ref=reference(str(registration_path),registration_sha256)
    merge({},capture_reference);merge({},publication_reference)
    prefixref=reference(str(PREFIX_CORE[0]),PREFIX_CORE[1]);gapref=reference(str(GAP_CORE[0]),GAP_CORE[1])
    regref=reference(str(REGISTRATION_CORE[0]),REGISTRATION_CORE[1]);refref=reference(str(REFERENCE_CORE[0]),REFERENCE_CORE[1])
    deps={key:reference(str(ROOT/path),digest)for key,(path,digest)in DEPENDENCIES.items()}
    csvref=reference(str(CSV_READER[0]),CSV_READER[1])
    initial={};consume(producer_ref,initial)
    refcore=private_module(REFERENCE_CORE[0],consume(refref,initial),REFERENCE_CORE[1])
    regcore=private_module(REGISTRATION_CORE[0],consume(regref,initial),REGISTRATION_CORE[1],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',refcore)])
    exact(regcore.REFERENCE_KERNEL_SHA256,REFERENCE_CORE[1])
    registration=decode(consume(registration_ref,initial));registered=regcore.prepare_forward_capture_runtime(registration=registration,
        registration_reference=registration_ref,runtime_reference=producer_ref,dependency_references=deps,research_root=str(RESEARCH))
    capture_folder=Path(registered['output_directory']);output=safe(output_directory)
    out=refcore.canonical_path(str(output));require(out.parent==refcore.canonical_path(str(RESEARCH))and
        out!=refcore.canonical_path(str(capture_folder))and not output.exists(),'Independent create-only namespace')
    require(re.fullmatch('[a-z][a-z0-9_]{2,119}',out.name)is not None,'Stable readback namespace')
    for item in (producer_ref,registration_ref,regref,refref,prefixref,gapref,*deps.values(),*registered['parent'].values()):
        source=refcore.canonical_path(item['path']);require(source!=out and out not in source.parents,'Readback aliases input')
    exact(capture_reference['path'],str(capture_folder/'capture.json'));exact(publication_reference['path'],str(capture_folder/'publication.json'))
    raw={key:consume(item,initial)for key,item in deps.items()}
    parent_checker=private_parent_checker(raw)
    prefix_checker=private_prefix_checker(raw,initial);consume(gapref,initial)
    csv_rows=private_module(CSV_READER[0],consume(csvref,{}),CSV_READER[1]).csv_rows
    parent=deepcopy(registered['parent'])
    for key,role in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:
        parent[key]=decode(consume(parent[role],initial))
        for path,digest in parent[key]['source_hashes'].items():consume(reference(path,digest),initial)
    consume(parent['reader_reference'],initial);view=parent_checker.inspect_parent_history_v5(parent)
    accounted={t:consume(view['accounted_baseline_references'][t],initial)for t in ('QQQ','SPY')}
    actual={t:consume(view['baseline_references'][t],initial)for t in ('QQQ','SPY')}
    parent_chain_inventories=verify_parent_chain(parent,parent_checker,prefix_checker,csv_rows,initial)
    originaltz=view['tzif_reference'];consume(originaltz,initial);parent_inventories(registered['parent'],initial)
    inputs=dict(dependencies=deps,registration=registration_ref,runtime=producer_ref,registration_core=regref,reference_core=refref,prefix_core=prefixref,gap_core=gapref,tzif=originaltz)
    sources=dict(initial);sources[str(SOURCE)]=LOADED_SHA
    d=decode(consume(capture_reference,sources));p=decode(consume(publication_reference,sources))
    artifacts=d['captured_artifacts'];exact(sorted(artifacts),['QQQ','SPY','tzif'])
    expected_sources=deepcopy(initial)
    for key,item in artifacts.items():
        exact(item['path'],str(capture_folder/('New_York.tzif'if key=='tzif'else key+'.csv')));merge(expected_sources,item)
    snapshots={t:consume(artifacts[t],sources)for t in ('QQQ','SPY')};tz=consume(artifacts['tzif'],sources)
    exact(artifacts['tzif']['sha256'],originaltz['sha256'])
    exact(sorted(d['current_cache_references']),['QQQ','SPY'])
    for ticker in ('QQQ','SPY'):exact(d['current_cache_references'][ticker],reference(str(CURRENT[ticker]),artifacts[ticker]['sha256']))
    csv_rows=private_module(CSV_READER[0],consume(csvref,sources),CSV_READER[1]).csv_rows
    expected=reconstruct_plan(parent=parent,source_bytes=snapshots,source_references={t:artifacts[t]for t in ('QQQ','SPY')},
        accounted_baseline_bytes=accounted,actual_baseline_bytes=actual,capture_started_at=d['capture_started_at'],capture_completed_at=d['capture_completed_at'],
        tzif_bytes=tz,tzif_reference=artifacts['tzif'],parent_checker=parent_checker,csv_rows=csv_rows)
    exact(d,dict(schema='SOURCE_BOUND_FORWARD_CAPTURE_V5',plan=expected,parent_references=registered['parent'],input_references=inputs,
        captured_artifacts=artifacts,current_cache_references=d['current_cache_references'],
        current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',
        capture_started_at=d['capture_started_at'],capture_completed_at=d['capture_completed_at'],clock_captured_by_runner=True,
        external_clock_attestation_verified=False,quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',
        source_hashes=expected_sources,**dict.fromkeys(FALSE_FIELDS,False)))
    exact(p,dict(schema='FORWARD_CAPTURE_PUBLICATION_V5',status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION',capture_reference=capture_reference,
        source_hashes=expected_sources,**dict.fromkeys(FALSE_FIELDS,False)))
    startpath=safe(capture_folder/'started.json');require(startpath.is_file()and startpath.stat().st_size<=64*1024**2,'Bounded publisher start')
    rawstart=startpath.read_bytes();startref=reference(str(startpath),sha(rawstart));consume(startref,sources)
    exact(decode(rawstart),dict(schema='FORWARD_CAPTURE_STARTED_V5',parent_references=registered['parent'],input_references=inputs,
        source_hashes=initial,retry_allowed=False,**dict.fromkeys(FALSE_FIELDS,False)))
    def final_guard():
        for kind,refs in parent_chain_inventories:
            if kind=='parent':parent_inventories(refs,{})
            else:
                namespace(Path(refs['reference']['path']).parent,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'))
                namespace(Path(refs['readback_reference']['path']).parent,('started.json','independent_readback.json'))
        parent_inventories(registered['parent'],{});namespace(capture_folder,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'));guard(sources)
    final_guard();require(shutil.disk_usage(output.anchor).free>=5*1024**3,'Resource stop before namespace');output.mkdir(parents=True,exist_ok=False)
    try:
        own_started=save(output/'started.json',dict(schema='FORWARD_CAPTURE_READBACK_STARTED_V5',capture_reference=capture_reference,
            publication_reference=publication_reference,registration_reference=registration_ref,reader_sha256=LOADED_SHA,**dict.fromkeys(FALSE_FIELDS,False)))
        report=save(output/'independent_readback.json',dict(schema='FORWARD_CAPTURE_INDEPENDENT_READBACK_V5',status='PURE_FORWARD_CAPTURE_READBACK_PASS',
            capture_reference=capture_reference,publication_reference=publication_reference,parent_references=registered['parent'],input_references=inputs,
            producer_reference=producer_ref,reader_sha256=LOADED_SHA,source_hashes=sources,
            counts=dict(status=expected['status'],parent_typed_row_count=len(expected['known_typed_rows']),parent_actual_observation_count=len(expected['observations']),
                parent_observed_count=sum(row['kind']!='MISSED_OBSERVATION'for row in expected['known_typed_rows']),parent_gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in expected['known_typed_rows']),
                candidate_session=expected['candidate_session'],diagnostic_count=len(expected['diagnostics']),snapshot_counts={t:expected['source_evidence'][t]['original_row_count']for t in ('QQQ','SPY')}),
            entire_plan_independently_reconstructed=True,snapshot_bytes_verified=True,producer_called=False,capture_core_called=False,
            csv_reader_reference=csvref,csv_resource_semantics='MAX_8000000_SOURCE_BYTES_MAX_20000_DATA_ROWS_BLANK_RECORDS_EXCLUDED_NO_EXTRA_PHYSICAL_LINE_LIMIT',
            current_live_cache_read_or_reverified=False,external_clock_attestation_verified=False,
            shared_upstream_parent_checker_reference=deps['parent_view'],shared_legacy_parent_checker_reference=deps['legacy_view'],shared_parent_checker_called=True,prefix_core_called_for_parent_evidence_only=any(kind=='capture'for kind,refs in parent_chain_inventories),gap_core_called=False,
            parent_chain_and_original_prefix_bytes_reverified=True,
            actual_parent_schema=view['parent_schema'],
            reconstruction_scope='INDEPENDENT_CAPTURE_PLAN_FROM_BOUND_PARENT_SHARED_PARENT_INSPECTOR_NOT_SOURCE_OR_CLOCK_AUTHENTICATION',
            started_reference_observed_not_external_anchor=startref,started_externally_authenticated=False,**dict.fromkeys(FALSE_FIELDS,False)))
        final_guard();consume(own_started,{});consume(report,{});namespace(output,('started.json','independent_readback.json'));return report
    except BaseException as error:
        save(output/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,automatic_retry_allowed=False,**dict.fromkeys(FALSE_FIELDS,False)));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration-path','registration-sha256','capture-path','capture-sha256','publication-path','publication-sha256','output-directory'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(readback(registration_path=args.registration_path,registration_sha256=args.registration_sha256,
        capture_reference=reference(args.capture_path,args.capture_sha256),publication_reference=reference(args.publication_path,args.publication_sha256),
        output_directory=args.output_directory,execute=args.execute)))
