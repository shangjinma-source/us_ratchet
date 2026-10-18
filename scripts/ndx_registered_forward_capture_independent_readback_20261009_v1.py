"""Registered V3/V4 snapshot readback. Independent plan, shared parent checker.

Never calls a producer/capture kernel or reads current caches. Producer is pinned;
each run requires external immutable artifact references.
"""
import argparse
from copy import deepcopy
from datetime import datetime,date,time,timezone
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
PRODUCER=ROOT/'scripts/ndx_registered_forward_capture_runtime_20261009_v1.py'
PRODUCER_SHA='e7850782dcc4c230353281935ebc428a7c02349a00cea89731ed16ea27e49190'
REGISTRATION_CORE=(ROOT/'backtest/ndx_forward_capture_runtime_registration_research_v1.py','e04169b111d2788e3dadba657a6c4823d2b0665de17a81e0c84bb9169990abde')
REFERENCE_CORE=(ROOT/'backtest/ndx_compact_history_runtime_registration_research_v1.py','d0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')
DEPENDENCIES={
 'capture_core':('backtest/ndx_forward_parent_capture_research_v4.py','56175bb45b25aa899dc0f9fdd07d0eac2cabfd2f0640a177f596582b7b08a951'),
 'parent_view':('backtest/ndx_prospective_observation_parent_history_research_v4.py','06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'),
 'compact_helpers':('backtest/ndx_prospective_observation_parent_history_research.py','1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'),
 'base':('backtest/ndx_forward_source_capture_research.py','30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'),
 'scoped':('backtest/ndx_forward_source_capture_scoped_research.py','9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee')}
CSV_READER=(ROOT/'scripts/ndx_variable_prefix_capture_independent_readback_20261003.py','aed7b71289fb30473cedefda00c6377c0700bea115e5d99328c1c20dd4572dbe')
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
    view=parent_checker.inspect_parent_history_v4(parent);days=[r['session']for r in view['known_typed_rows']]
    sources=deepcopy(view['source_hashes'])
    for pair in (source_bytes,source_references,accounted_baseline_bytes,actual_baseline_bytes,
                 view['accounted_baseline_references'],view['baseline_references']):
        require(type(pair)is dict and set(pair)=={'QQQ','SPY'},'Exact source pair')
    begin,end=utc(capture_started_at),utc(capture_completed_at);require(begin<=end,'Capture clock reversal')
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
    return dict(schema='FORWARD_PARENT_CAPTURE_PLAN_V4',status='BLOCKED_SOURCE_DIAGNOSTICS'if diagnostics else
        'ONE_NEW_SESSION_CAPTURE_CANDIDATE'if candidate else 'NO_NEW_SESSION',diagnostics=diagnostics,candidate_session=candidate,
        policy_id=view['policy_id'],parent_references={role:deepcopy(parent[role])for role in ROLES},
        known_typed_rows=deepcopy(view['known_typed_rows']),observations=deepcopy(view['observations']),parent_attempt_inventory=deepcopy(view['parent_attempt_inventory']),
        first_actual_observed_session_by_month=deepcopy(view['first_actual_observed_session_by_month']),
        baseline_references=deepcopy(view['baseline_references']),baseline_role=view['baseline_role'],
        accounted_baseline_references=deepcopy(view['accounted_baseline_references']),accounted_baseline_role='FULL_SAVED_CSV_SCOPE_EQUALS_ALL_KNOWN_TYPED_SESSIONS',
        last_accounted_session=view['last_accounted_session'],last_observed_session=view['last_observed_session'],source_evidence=evidence,
        source_reference_claims=sources,capture_started_at=begin.isoformat(),capture_completed_at=end.isoformat(),tzif_reference=deepcopy(tzif_reference),
        candidate_conservative_close_utc=close(candidate).isoformat()if candidate else None,
        timing_semantics='CALLER_SUPPLIED_CLOCK_CONSERVATIVE_16_NY_CLOSE_NOT_AUTHENTICATED_EXCHANGE_CALENDAR',late_observation_classification_deferred_to_payload_core=True,
        authentication_role='STRUCTURAL_DECLARATIONS_AND_SUPPLIED_BYTES_ONLY_NO_IO_AUTHENTICATION',raw_source_bytes_embedded=False,
        dependency_sha256={role:DEPENDENCIES[key][1]for role,key in [('scoped','scoped'),('base','base'),('parent_view','parent_view'),('compact_helpers','compact_helpers')]},
        **dict.fromkeys(PURE_FALSE,False))


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
    namespace(folder,{'started.json','history.json','publication.json'}|({'independent_readback.json'}if folder==audit else set()))
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


def readback(*,registration_path,registration_sha256,capture_reference,publication_reference,output_directory,execute=False):
    require(execute is True,'Explicit registered capture readback')
    producer_ref=reference(str(PRODUCER),PRODUCER_SHA);registration_ref=reference(str(registration_path),registration_sha256)
    merge({},capture_reference);merge({},publication_reference)
    regref=reference(str(REGISTRATION_CORE[0]),REGISTRATION_CORE[1]);refref=reference(str(REFERENCE_CORE[0]),REFERENCE_CORE[1])
    deps={key:reference(str(ROOT/path),digest)for key,(path,digest)in DEPENDENCIES.items()}
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
    for item in (producer_ref,registration_ref,regref,refref,*deps.values(),*registered['parent'].values()):
        source=refcore.canonical_path(item['path']);require(source!=out and out not in source.parents,'Readback aliases input')
    exact(capture_reference['path'],str(capture_folder/'capture.json'));exact(publication_reference['path'],str(capture_folder/'publication.json'))
    raw={key:consume(item,initial)for key,item in deps.items()}
    helper=private_module(ROOT/DEPENDENCIES['compact_helpers'][0],raw['compact_helpers'],DEPENDENCIES['compact_helpers'][1])
    parent_checker=private_module(ROOT/DEPENDENCIES['parent_view'][0],raw['parent_view'],DEPENDENCIES['parent_view'][1],[
        ('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',helper)])
    parent=deepcopy(registered['parent'])
    for key,role in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:
        parent[key]=decode(consume(parent[role],initial))
        for path,digest in parent[key]['source_hashes'].items():consume(reference(path,digest),initial)
    consume(parent['reader_reference'],initial);view=parent_checker.inspect_parent_history_v4(parent)
    accounted={t:consume(view['accounted_baseline_references'][t],initial)for t in ('QQQ','SPY')}
    actual={t:consume(view['baseline_references'][t],initial)for t in ('QQQ','SPY')}
    originaltz=view['tzif_reference'];consume(originaltz,initial);parent_inventories(registered['parent'],initial)
    inputs=dict(dependencies=deps,registration=registration_ref,runtime=producer_ref,registration_core=regref,reference_core=refref,tzif=originaltz)
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
    csvref=reference(str(CSV_READER[0]),CSV_READER[1]);csv_rows=private_module(CSV_READER[0],consume(csvref,sources),CSV_READER[1]).csv_rows
    expected=reconstruct_plan(parent=parent,source_bytes=snapshots,source_references={t:artifacts[t]for t in ('QQQ','SPY')},
        accounted_baseline_bytes=accounted,actual_baseline_bytes=actual,capture_started_at=d['capture_started_at'],capture_completed_at=d['capture_completed_at'],
        tzif_bytes=tz,tzif_reference=artifacts['tzif'],parent_checker=parent_checker,csv_rows=csv_rows)
    exact(d,dict(schema='SOURCE_BOUND_FORWARD_CAPTURE_V4',plan=expected,parent_references=registered['parent'],input_references=inputs,
        captured_artifacts=artifacts,current_cache_references=d['current_cache_references'],
        current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',
        capture_started_at=d['capture_started_at'],capture_completed_at=d['capture_completed_at'],clock_captured_by_runner=True,
        external_clock_attestation_verified=False,quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',
        source_hashes=expected_sources,**dict.fromkeys(FALSE_FIELDS,False)))
    exact(p,dict(schema='FORWARD_CAPTURE_PUBLICATION_V4',status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION',capture_reference=capture_reference,
        source_hashes=expected_sources,**dict.fromkeys(FALSE_FIELDS,False)))
    startpath=safe(capture_folder/'started.json');require(startpath.is_file()and startpath.stat().st_size<=64*1024**2,'Bounded publisher start')
    rawstart=startpath.read_bytes();startref=reference(str(startpath),sha(rawstart));consume(startref,sources)
    exact(decode(rawstart),dict(schema='FORWARD_CAPTURE_STARTED_V4',parent_references=registered['parent'],input_references=inputs,
        source_hashes=initial,retry_allowed=False,**dict.fromkeys(FALSE_FIELDS,False)))
    def final_guard():
        parent_inventories(registered['parent'],{});namespace(capture_folder,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'));guard(sources)
    final_guard();require(shutil.disk_usage(output.anchor).free>=5*1024**3,'Resource stop before namespace');output.mkdir(parents=True,exist_ok=False)
    try:
        own_started=save(output/'started.json',dict(schema='FORWARD_CAPTURE_READBACK_STARTED_V4',capture_reference=capture_reference,
            publication_reference=publication_reference,registration_reference=registration_ref,reader_sha256=LOADED_SHA,**dict.fromkeys(FALSE_FIELDS,False)))
        report=save(output/'independent_readback.json',dict(schema='FORWARD_CAPTURE_INDEPENDENT_READBACK_V4',status='PURE_FORWARD_CAPTURE_READBACK_PASS',
            capture_reference=capture_reference,publication_reference=publication_reference,parent_references=registered['parent'],input_references=inputs,
            producer_reference=producer_ref,reader_sha256=LOADED_SHA,source_hashes=sources,
            counts=dict(status=expected['status'],parent_typed_row_count=len(expected['known_typed_rows']),parent_actual_observation_count=len(expected['observations']),
                parent_observed_count=sum(row['kind']!='MISSED_OBSERVATION'for row in expected['known_typed_rows']),parent_gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in expected['known_typed_rows']),
                candidate_session=expected['candidate_session'],diagnostic_count=len(expected['diagnostics']),snapshot_counts={t:expected['source_evidence'][t]['original_row_count']for t in ('QQQ','SPY')}),
            entire_plan_independently_reconstructed=True,snapshot_bytes_verified=True,producer_called=False,capture_core_called=False,
            current_live_cache_read_or_reverified=False,external_clock_attestation_verified=False,
            shared_upstream_parent_checker_reference=deps['parent_view'],shared_parent_checker_called=True,
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
