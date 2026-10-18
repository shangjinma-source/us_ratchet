"""Thin V3 observation adapter. Future capture pins deliberately remain pending."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
from types import ModuleType

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_prospective_observation_receipt_research.py'
CORE_SHA='6a088c05321b9e9a407765190800acb9443f8f5de6f1c11d456d86f3e0415684'
CHECKER=ROOT/'scripts/ndx_forward_gap_parent_capture_independent_readback_20261009_v3.py'
CHECKER_SHA='3033e66b57b2ccfcf3bbdf091149f0c43c8c7d93387c087c5ba48fa17271cd45'
CSV_READER=ROOT/'scripts/ndx_variable_prefix_capture_independent_readback_20261003.py'
CSV_READER_SHA='aed7b71289fb30473cedefda00c6377c0700bea115e5d99328c1c20dd4572dbe'
OUTPUT=ROOT/'data/cache/research/prospective_observation_receipt_20261009_v3'
RESEARCH=ROOT/'data/cache/research'
ADAPTER='GAP_PARENT_PROSPECTIVE_OBSERVATION_WRITER_V3'
ROLES=('reference','publication_reference','readback_reference','reader_reference')
PARENT_BOUND={
 'reference':dict(path=str(ROOT/'data/cache/research/prospective_gap_history_20261009_v3/history.json'),sha256='600d15deb7cdcbc74fb13337c279d31c910d9389088ebc8668ea650779fdfd8a'),
 'publication_reference':dict(path=str(ROOT/'data/cache/research/prospective_gap_history_20261009_v3/publication.json'),sha256='3ff2cf28d954e64ed7a21af6d8b7ed5465c7cf2fe5c6fd7d057cd43e4cddfe10'),
 'readback_reference':dict(path=str(ROOT/'data/cache/research/prospective_gap_history_independent_readback_20261009_v3/independent_readback.json'),sha256='86e867fa73f28b9a436472eb27848a159a75e5de4bcf97e7a4b69b6a1be98912'),
 'reader_reference':dict(path=str(ROOT/'scripts/ndx_prospective_gap_history_independent_readback_20261009_v3.py'),sha256='2be765c5dafcb85366e4e84d3a8cbed2037a6924649695f3ab176764075791f8')}
CAPTURE_BOUND=dict.fromkeys(ROLES)
CAPTURE_PRODUCER=None
CAPTURE_CORE=None
FLAGS=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified',
 'promotion_allowed','live_mutation_allowed','old_calendar_mutated','seal_status_event_created',
 'network_capture_performed','production_generator_authorized','full_transitive_source_closure_reverified',
 'future_independent_oos','partial_recovery_performed','filesystem_attempt_inventory_authenticated',
 'source_authenticity_verified','clock_authenticity_verified'),False)


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(left,right):require(encode(left)==encode(right),'Exact V3 evidence mismatch')
def now():return datetime.now(timezone.utc).isoformat()
def runtime():return dict(python=sys.version,executable=sys.executable,implementation=platform.python_implementation())


def ref(item):
    require(type(item)is dict and set(item)=={'path','sha256'},'Pending immutable reference')
    require(type(item['path'])is str and item['path'] and item['path'].strip()==item['path'] and '\x00'not in item['path'],'Reference path')
    require(type(item['sha256'])is str and len(item['sha256'])==64 and all(c in '0123456789abcdef'for c in item['sha256']),'Pending immutable SHA')
    return item


def merge(sources,item):
    ref(item);require(item['path']not in sources or sources[item['path']]==item['sha256'],'Conflicting source path')
    sources[item['path']]=item['sha256']


def configured(bound):
    require(type(bound)is dict and set(bound)==set(ROLES),'Complete four anchors')
    for item in bound.values():ref(item)
    return deepcopy(bound)


def safe(path):
    path=Path(path)
    for item in (path,*path.parents):
        require(not item.is_symlink()and not getattr(item,'is_junction',lambda:False)(),'Linked evidence path')
    return path


def decode(raw):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate JSON key');result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda value:(_ for _ in()).throw(ValueError(value)))


def consume(item,sources):
    merge(sources,item);path=safe(item['path'])
    require(path.is_file()and path.stat().st_size<=64*1024**2 and not(path.parent/'failure.json').exists(),'Bounded nonfailed source')
    raw=path.read_bytes();require(sha(raw)==item['sha256'],'Source SHA changed');return raw


def guard(sources):
    live={(ROOT/'data/cache'/f'{ticker}.csv').resolve()for ticker in ('QQQ','SPY')}
    for path,digest in {**sources,str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA}.items():
        require(Path(path).resolve()not in live,'No mutable cache source claim');consume(dict(path=path,sha256=digest),{})


def namespace(path,names):
    items=list(safe(path).iterdir());exact(sorted(item.name for item in items),sorted(names))
    require(all(safe(item).is_file()for item in items),'Regular namespace inventory')


def private_module(raw,path,expected,name):
    require(sha(raw)==expected,'Private source SHA')
    module=ModuleType(name);module.__file__=str(path)
    exec(compile(raw.decode('utf-8-sig'),str(path),'exec'),module.__dict__)
    return module


def envelope(refs,sources):
    result=deepcopy(refs)
    for key,role in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:
        result[key]=decode(consume(refs[role],sources))
        for path,digest in result[key]['source_hashes'].items():merge(sources,dict(path=path,sha256=digest))
    consume(refs['reader_reference'],sources);return result


def validate_capture(parent,capture,checker):
    h,days,_=checker.inspect_v3_parent(parent)
    c,p,a=(capture[key]for key in ('document','publication','readback'))
    exact(c['schema'],'SOURCE_BOUND_FORWARD_GAP_PARENT_CAPTURE_V3')
    exact(p['schema'],'FORWARD_GAP_PARENT_CAPTURE_PUBLICATION_V3')
    exact(p['status'],'PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION')
    exact(a['schema'],'FORWARD_GAP_PARENT_CAPTURE_INDEPENDENT_READBACK_V3')
    exact(a['status'],'PURE_FORWARD_GAP_CAPTURE_READBACK_PASS')
    for obj in (c,p,a):checker.flags(obj,checker.FALSE_FIELDS)
    for obj in (p,a):exact(obj['capture_reference'],capture['reference'])
    exact(a['publication_reference'],capture['publication_reference'])
    exact(a['reader_sha256'],capture['reader_reference']['sha256'])
    parents={key:parent[key]for key in ROLES};exact(c['parent_references'],parents);exact(a['parent_references'],parents)
    exact(c['source_hashes'],p['source_hashes'])
    for path,digest in c['source_hashes'].items():exact(a['source_hashes'].get(path),digest)
    for role in ('reference','publication_reference','reader_reference'):
        item=capture[role];exact(a['source_hashes'].get(item['path']),item['sha256'])
    for key in ('entire_plan_independently_reconstructed','snapshot_bytes_verified'):require(a[key]is True,'Independent full capture readback')
    for key in ('producer_called','new_pure_called','plan_gap_parent_capture_called','current_live_cache_read_or_reverified','external_clock_attestation_verified'):
        require(a[key]is False,'No upstream execution/authentication inference')
    require(c['clock_captured_by_runner']is True and c['external_clock_attestation_verified']is False,'Runner clock recording')
    exact(c['quote_source_type'],'EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH')
    exact(c['current_cache_verification_scope'],'CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE')
    exact(c['input_references']['pure'],CAPTURE_CORE)
    exact(a['input_references'],c['input_references']);exact(a['producer_reference'],CAPTURE_PRODUCER)
    for item in (CAPTURE_PRODUCER,CAPTURE_CORE):exact(c['source_hashes'].get(item['path']),item['sha256'])
    plan=c['plan'];exact(plan['schema'],'FORWARD_GAP_PARENT_CAPTURE_PLAN_V3')
    exact(plan['status'],'ONE_NEW_SESSION_CAPTURE_CANDIDATE');exact(plan['diagnostics'],[])
    exact(plan['parent_references'],parents)
    for key in ('known_typed_rows','observations','parent_attempt_inventory','first_actual_observed_session_by_month',
                'baseline_references','baseline_role','last_accounted_session','last_observed_session'):
        exact(plan[key],h[key])
    exact(plan['accounted_baseline_references'],h['captured_source_references'])
    exact(plan['accounted_baseline_role'],'FULL_SAVED_CSV_SCOPE_EQUALS_ALL_KNOWN_TYPED_SESSIONS')
    session=plan['candidate_session'];require(type(session)is str and session>days[-1],'Unique future session')
    exact(a['counts'],dict(status=plan['status'],parent_typed_row_count=len(days),
        parent_actual_observation_count=len(h['observations']),parent_gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in h['known_typed_rows']),
        candidate_session=session,diagnostic_count=0,snapshot_counts={ticker:plan['source_evidence'][ticker]['original_row_count']for ticker in ('QQQ','SPY')}))
    exact(sorted(c['captured_artifacts']),['QQQ','SPY','tzif']);exact(plan['tzif_reference'],c['captured_artifacts']['tzif'])
    for ticker in ('QQQ','SPY'):
        e=plan['source_evidence'][ticker];exact(e['new_session_dates'],[session])
        exact(e['source_reference'],c['captured_artifacts'][ticker]);exact(e['accounted_baseline_reference'],h['captured_source_references'][ticker])
        exact(e['actual_baseline_reference'],h['baseline_references'][ticker])
        exact(c['current_cache_references'][ticker],dict(path=str(ROOT/'data/cache'/f'{ticker}.csv'),sha256=c['captured_artifacts'][ticker]['sha256']))
    return session


def attempt_inventory(parent,sources):
    """Bounded local research inventory, not authenticated full-filesystem coverage."""
    h=parent['document']['history'];allowed={entry['payload_reference']['path']:entry for entry in h['observations']}
    found={};folders=list(safe(RESEARCH).iterdir());require(len(folders)<=20000,'Bounded research inventory')
    for folder in folders:
        if folder.resolve()==OUTPUT.resolve():continue
        require(not folder.is_symlink()and not getattr(folder,'is_junction',lambda:False)(),'Linked research inventory')
        if not folder.is_dir():continue
        observed={}
        for name in ('started.json','observation_payload.json','receipt.json','failure.json'):
            path=safe(folder/name)
            if not path.exists():continue
            require(path.is_file()and path.stat().st_size<=64*1024**2,'Bounded attempt evidence')
            raw=path.read_bytes();obj=decode(raw);observed[name]=(obj,dict(path=str(path),sha256=sha(raw)))
        writer_start=observed.get('started.json',({},{}))[0].get('schema','').startswith('PROSPECTIVE_OBSERVATION_WRITER_STARTED_')
        writer_payload=observed.get('observation_payload.json',({},{}))[0].get('schema')=='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1'
        writer_receipt=observed.get('receipt.json',({},{}))[0].get('schema')=='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1'
        writer_failure=observed.get('failure.json',({},{}))[0].get('status')=='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY'
        if not(writer_start or writer_payload or writer_receipt or writer_failure):continue
        require(not(folder/'failure.json').exists()and set(observed)=={'started.json','observation_payload.json','receipt.json'},'UNRESOLVED_PRIOR_ATTEMPT_NO_NAMESPACE_BYPASS')
        payload,payload_ref=observed['observation_payload.json'];receipt,receipt_ref=observed['receipt.json']
        require(payload_ref['path']in allowed,'UNACCOUNTED_PRIOR_OBSERVATION_ATTEMPT')
        entry=allowed[payload_ref['path']];exact(payload_ref,entry['payload_reference']);exact(receipt_ref,entry['receipt_reference'])
        exact(payload['observation_id'],entry['observation_id']);exact(receipt['payload_reference'],payload_ref)
        require(payload_ref['path']not in found,'Duplicate prior attempt')
        found[payload_ref['path']]={name:ref for name,(_,ref)in observed.items()}
        for _,item in observed.values():merge(sources,item)
    exact(sorted(found),sorted(allowed));return found


def load_inputs():
    parents=configured(PARENT_BOUND);captures=configured(CAPTURE_BOUND)
    ref(CAPTURE_PRODUCER);ref(CAPTURE_CORE) # All future pins precede all IO.
    sources={str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA}
    checker_ref=dict(path=str(CHECKER),sha256=CHECKER_SHA)
    checker=private_module(consume(checker_ref,sources),CHECKER,CHECKER_SHA,'_v3_capture_checks')
    csv_rows=checker.private_csv_reader(consume(dict(path=str(CSV_READER),sha256=CSV_READER_SHA),sources))
    parent=envelope(parents,sources);capture=envelope(captures,sources)
    session=validate_capture(parent,capture,checker);h=parent['document']['history'];c=capture['document']
    parent_folder=Path(parents['reference']['path']).parent;capture_folder=Path(captures['reference']['path']).parent
    exact(parents['reference']['path'],str(parent_folder/'history.json'));exact(parents['publication_reference']['path'],str(parent_folder/'publication.json'))
    exact(captures['reference']['path'],str(capture_folder/'capture.json'));exact(captures['publication_reference']['path'],str(capture_folder/'publication.json'))
    def namespaces():
        namespace(parent_folder,('started.json','history.json','publication.json'))
        namespace(Path(parents['readback_reference']['path']).parent,('started.json','independent_readback.json'))
        namespace(capture_folder,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'))
        namespace(Path(captures['readback_reference']['path']).parent,('started.json','independent_readback.json'))
    namespaces()
    value=dict(reference=captures['reference'],started_at_utc=c['capture_started_at'],completed_at_utc=c['capture_completed_at'],sources={},baseline_sources={})
    actual={}
    for ticker in ('QQQ','SPY'):
        exact(c['captured_artifacts'][ticker]['path'],str(capture_folder/f'{ticker}.csv'))
        for role,item in [('sources',c['captured_artifacts'][ticker]),('baseline_sources',h['captured_source_references'][ticker])]:
            value[role][ticker]=dict(bytes=consume(item,sources),reference=deepcopy(item))
        actual[ticker]=consume(h['baseline_references'][ticker],sources)
    tz=c['captured_artifacts']['tzif'];exact(tz['path'],str(capture_folder/'New_York.tzif'))
    value['tzif']=dict(bytes=consume(tz,sources),reference=deepcopy(tz))
    planned=checker.reconstruct_plan(parent=parent,source_bytes={t:value['sources'][t]['bytes']for t in ('QQQ','SPY')},
        source_references={t:value['sources'][t]['reference']for t in ('QQQ','SPY')},
        accounted_baseline_bytes={t:value['baseline_sources'][t]['bytes']for t in ('QQQ','SPY')},actual_baseline_bytes=actual,
        capture_started_at=c['capture_started_at'],capture_completed_at=c['capture_completed_at'],
        tzif_bytes=value['tzif']['bytes'],tzif_reference=tz,csv_rows=csv_rows)
    exact(c['plan'],planned)
    attempts=attempt_inventory(parent,sources)
    def final_guard():
        namespaces();exact(attempt_inventory(parent,{}),attempts);guard(sources)
    final_guard()
    core=private_module(consume(dict(path=str(CORE),sha256=CORE_SHA),sources),CORE,CORE_SHA,'_v3_payload_core')
    args=dict(parent_reference=parents['reference'],parent_readback_reference=parents['readback_reference'],
        known_typed_rows=deepcopy(h['known_typed_rows']),parent_attempt_inventory=deepcopy(h['parent_attempt_inventory']),capture=value,session=session)
    return args,dict(parent=parents,capture=captures),sources,core,final_guard,attempts,checker_ref


def resource_gate(size=0):
    require(type(size)is int and size>=0 and shutil.disk_usage(Path(OUTPUT.anchor)).free>=5*1024**3+size,'Resource stop before write')


def save(path,value):
    raw=encode(value)
    if path.name!='failure.json':resource_gate(len(raw))
    with safe(path).open('xb')as stream:
        require(stream.write(raw)==len(raw),'Complete output write');stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Durable saved bytes');return dict(path=str(path),sha256=sha(raw))


def run(*,execute=False):
    require(type(execute)is bool,'Explicit bool')
    if not execute:return dict(status='NOT_EXECUTED')
    configured(PARENT_BOUND);configured(CAPTURE_BOUND);ref(CAPTURE_PRODUCER);ref(CAPTURE_CORE)
    require(not OUTPUT.exists(),'Exclusive attempt no retry')
    args,refs,sources,core,final_guard,attempts,checker_ref=load_inputs()
    resource_gate();safe(OUTPUT).mkdir(parents=True,exist_ok=False)
    try:
        rt=runtime();start=now()
        metadata=dict(writer_adapter_schema=ADAPTER,input_references=refs,source_hashes=deepcopy(sources),runtime=rt,
            capture_checker_reference=checker_ref,attempt_inventory_scope='LOCAL_RESEARCH_DIRECT_CHILD_WRITER_SCHEMA_NAMESPACES_NOT_FULL_FILESYSTEM_AUTHENTICATION',
            local_attempt_namespace_inventory=attempts)
        save(OUTPUT/'started.json',dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V3',writer_started_at_utc=start,**metadata,**FLAGS));final_guard()
        end=now();payload=core.prepare_observation_payload(**args,writer_started_at_utc=start,writer_completed_at_utc=end)
        for path,digest in payload['source_hash_claims'].items():require(sources.get(path)==digest,'Payload claim outside source closure')
        payload.update(metadata);payload.update(FLAGS)
        payload['writer_interval_role']='PRE_PAYLOAD_VALIDATION_INTERVAL_NOT_PUBLICATION_COMPLETION'
        out=save(OUTPUT/'observation_payload.json',payload);final_guard();exact(runtime(),rt)
        check=now();require(core.utc(check)>=core.utc(end),'Publication clock reversal')
        late=payload['timing_classification']=='LATE_OBSERVATION'or core.utc(check)>=core.utc(payload['conservative_deadline_utc'])
        receipt=save(OUTPUT/'receipt.json',dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',
            status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY',observation_id=payload['observation_id'],payload_reference=out,
            publication_check_at_utc=check,publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE',
            timing_classification='LATE_OBSERVATION'if late else payload['timing_classification'],
            month_first_actual_observation=payload['month_first_actual_observation'],**metadata,**FLAGS))
        final_guard();exact(runtime(),rt)
        for item in (out,receipt):consume(item,{})
        namespace(OUTPUT,('started.json','observation_payload.json','receipt.json'));return receipt
    except BaseException as error:
        save(OUTPUT/'failure.json',dict(status='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY',error_type=type(error).__name__,
             recorded_at_utc=now(),observation_payload_must_not_be_discarded=(OUTPUT/'observation_payload.json').exists(),retry_allowed=False,**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(run(execute=parser.parse_args().execute)))
