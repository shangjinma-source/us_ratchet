"""Registered V3/V4 observation writer; immutable evidence, no candidate authority."""
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
RESEARCH=ROOT/'data/cache/research'
CURRENT={t:ROOT/'data/cache'/f'{t}.csv'for t in ('QQQ','SPY')}
REGISTRATION_CORE=(ROOT/'backtest/ndx_observation_runtime_registration_research_v1.py',
    '1b2db6d83aa9e7dbd3229930b3d485b0256d43fefcb6f1503333f1ac3f8f8c99')
REFERENCE_CORE=(ROOT/'backtest/ndx_compact_history_runtime_registration_research_v1.py',
    'd0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')
CORE=ROOT/'backtest/ndx_prospective_observation_receipt_research.py'
CORE_SHA='6a088c05321b9e9a407765190800acb9443f8f5de6f1c11d456d86f3e0415684'
DEPENDENCIES={
 'payload_core':(CORE,CORE_SHA),
 'parent_view':(ROOT/'backtest/ndx_prospective_observation_parent_history_research_v4.py','06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'),
 'compact_helpers':(ROOT/'backtest/ndx_prospective_observation_parent_history_research.py','1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'),
 'capture_checker':(ROOT/'scripts/ndx_registered_forward_capture_independent_readback_20261009_v1.py','b44f2d2cd89f5ea4a64e268e86b409305e7e40673df6565f1d2ba8f9bdeb8cc2'),
 'csv_reader':(ROOT/'scripts/ndx_variable_prefix_capture_independent_readback_20261003.py','aed7b71289fb30473cedefda00c6377c0700bea115e5d99328c1c20dd4572dbe')}
ADAPTER='REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V4'
ROLES=('reference','publication_reference','readback_reference','reader_reference')
INVENTORY_SCOPE='LOCAL_RESEARCH_DIRECT_CHILD_WRITER_SCHEMAS_PLUS_BOUND_PARENT_EXTERNAL_ATTEMPT_NAMESPACES_NOT_FULL_FILESYSTEM_AUTHENTICATION'
FLAGS=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified',
 'promotion_allowed','live_mutation_allowed','old_calendar_mutated','seal_status_event_created',
 'network_capture_performed','production_generator_authorized','full_transitive_source_closure_reverified',
 'future_independent_oos','partial_recovery_performed','filesystem_attempt_inventory_authenticated',
 'source_authenticity_verified','clock_authenticity_verified','parent_attempt_inventory_completeness_verified'),False)


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(left,right):require(encode(left)==encode(right),'Exact registered observation evidence mismatch')
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
    require(path.is_absolute(),'Absolute evidence path')
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
    live={value.resolve()for value in CURRENT.values()}|{(ROOT/'data/cache'/f'{t}.csv').resolve()for t in ('QQQ','SPY')}
    require(path.resolve()not in live,'Mutable current cache is diagnostic only; forbidden before read')
    raw=path.read_bytes();require(sha(raw)==item['sha256'],'Source SHA changed');return raw


def guard(sources):
    live={path.resolve()for path in CURRENT.values()}
    for path,digest in {**sources,str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA}.items():
        require(Path(path).resolve()not in live,'No mutable cache source claim');consume(dict(path=path,sha256=digest),{})


def namespace(path,names):
    items=list(safe(path).iterdir());exact(sorted(item.name for item in items),sorted(names))
    require(all(safe(item).is_file()for item in items),'Regular namespace inventory')


def private_module(raw,path,expected,name,replacements=()):
    require(sha(raw)==expected,'Private source SHA')
    module=ModuleType(name);module.__file__=str(path);code=raw.decode('utf-8-sig')
    for line,attribute,value in replacements:
        require(code.count(line)==1,'Explicit private dependency import')
        code=code.replace(line,'');module.__dict__[attribute]=value
    exec(compile(code,str(path),'exec'),module.__dict__)
    return module


def envelope(refs,sources):
    result=deepcopy(refs)
    for key,role in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:
        result[key]=decode(consume(refs[role],sources))
        for path,digest in result[key]['source_hashes'].items():merge(sources,dict(path=path,sha256=digest))
    consume(refs['reader_reference'],sources)
    for path,digest in list(sources.items()):consume(dict(path=path,sha256=digest),sources)
    return result


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


def attempt_inventory(parent,sources,output):
    """Bounded local research inventory, not authenticated full-filesystem coverage."""
    h=parent['document']['history'];allowed={entry['payload_reference']['path']:entry for entry in h['observations']}
    found={};folders=list(safe(RESEARCH).iterdir());require(len(folders)<=20000,'Bounded research inventory')
    external={Path(entry['payload_reference']['path']).parent for entry in h['observations']
        if Path(entry['payload_reference']['path']).parent.parent!=RESEARCH}
    folders.extend(sorted(external,key=str))
    for folder in folders:
        if folder.resolve()==output.resolve():continue
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
        namespace(folder,('started.json','observation_payload.json','receipt.json','independent_readback.json'))
        audit=decode(consume(entry['audit_reference'],sources))
        exact(audit['source_hashes'],entry['original_source_hash_claims']['audit'])
        started_ref=observed['started.json'][1]
        require(audit['source_hashes'].get(started_ref['path'])==started_ref['sha256'],
            'Prior START must match inherited observed-byte audit association')
        exact(payload['observation_id'],entry['observation_id']);exact(receipt['payload_reference'],payload_ref)
        require(payload_ref['path']not in found,'Duplicate prior attempt')
        found[payload_ref['path']]={name:ref for name,(_,ref)in observed.items()}
        for _,item in observed.values():merge(sources,item)
    exact(sorted(found),sorted(allowed));return found


def load_inputs(registration_path,registration_sha256):
    regref=ref(dict(path=str(REGISTRATION_CORE[0]),sha256=REGISTRATION_CORE[1]))
    refref=ref(dict(path=str(REFERENCE_CORE[0]),sha256=REFERENCE_CORE[1]))
    registration_ref=ref(dict(path=str(registration_path),sha256=registration_sha256))
    deps={key:ref(dict(path=str(path),sha256=digest))for key,(path,digest)in DEPENDENCIES.items()}
    writer_ref=ref(dict(path=str(SOURCE),sha256=LOADED_SHA));sources={}
    consume(writer_ref,sources)
    reference_core=private_module(consume(refref,sources),REFERENCE_CORE[0],REFERENCE_CORE[1],'_registered_observation_refs')
    registration_core=private_module(consume(regref,sources),REGISTRATION_CORE[0],REGISTRATION_CORE[1],'_registered_observation_registration',[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',reference_core)])
    exact(registration_core.REFERENCE_KERNEL_SHA256,REFERENCE_CORE[1])
    registered=registration_core.prepare_observation_runtime(registration=decode(consume(registration_ref,sources)),
        registration_reference=registration_ref,runtime_reference=writer_ref,dependency_references=deps,research_root=str(RESEARCH))
    output=safe(registered['output_directory']);require(not output.exists(),'Exclusive attempt; no retry')
    parents,captures=registered['parent'],registered['capture']
    raw={key:consume(item,sources)for key,item in deps.items()}
    helper=private_module(raw['compact_helpers'],DEPENDENCIES['compact_helpers'][0],DEPENDENCIES['compact_helpers'][1],'_registered_observation_helper')
    parent_checker=private_module(raw['parent_view'],DEPENDENCIES['parent_view'][0],DEPENDENCIES['parent_view'][1],'_registered_observation_parent',[
        ('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',helper)])
    exact(parent_checker.DEPENDENCY_SHA256,DEPENDENCIES['compact_helpers'][1])
    checker=private_module(raw['capture_checker'],DEPENDENCIES['capture_checker'][0],DEPENDENCIES['capture_checker'][1],'_registered_capture_checks')
    csv_rows=private_module(raw['csv_reader'],DEPENDENCIES['csv_reader'][0],DEPENDENCIES['csv_reader'][1],'_registered_capture_csv').csv_rows
    parent=envelope(parents,sources);capture=envelope(captures,sources)
    session,view=validate_capture(parent,capture,checker,parent_checker);c=capture['document']
    parent_folder=Path(parents['reference']['path']).parent;capture_folder=Path(captures['reference']['path']).parent
    exact(parents['reference']['path'],str(parent_folder/'history.json'));exact(parents['publication_reference']['path'],str(parent_folder/'publication.json'))
    exact(captures['reference']['path'],str(capture_folder/'capture.json'));exact(captures['publication_reference']['path'],str(capture_folder/'publication.json'))
    def namespaces(pin=False):
        parent_audit=Path(parents['readback_reference']['path']).parent
        groups=[(parent_folder,{'started.json','history.json','publication.json'}|({'independent_readback.json'}if parent_audit==parent_folder else set())),
            (capture_folder,{'started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'}),
            (Path(captures['readback_reference']['path']).parent,{'started.json','independent_readback.json'})]
        if parent_audit!=parent_folder:groups.append((parent_audit,{'started.json','independent_readback.json'}))
        for folder,names in groups:
            namespace(folder,names)
            if pin:
                for file in folder.iterdir():
                    file=safe(file);require(file.is_file()and file.stat().st_size<=64*1024**2,'Bounded inventory evidence')
                    consume(dict(path=str(file),sha256=sha(file.read_bytes())),sources)
    namespaces(pin=True)
    # Revalidate the original capture registration against the pinned producer's host bindings.
    capture_registration=decode(consume(c['input_references']['registration'],sources))
    cr=c['input_references']['registration_core']
    capture_regcore=private_module(consume(cr,sources),cr['path'],cr['sha256'],'_registered_upstream_capture_registration',[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',reference_core)])
    exact(capture_regcore.REFERENCE_KERNEL_SHA256,REFERENCE_CORE[1])
    capture_plan=capture_regcore.prepare_forward_capture_runtime(registration=capture_registration,
        registration_reference=c['input_references']['registration'],runtime_reference=c['input_references']['runtime'],
        dependency_references=c['input_references']['dependencies'],research_root=str(RESEARCH))
    exact(capture_plan['parent'],parents);exact(capture_plan['output_directory'],str(capture_folder))
    value=dict(reference=captures['reference'],started_at_utc=c['capture_started_at'],completed_at_utc=c['capture_completed_at'],sources={},baseline_sources={})
    actual={}
    for ticker in ('QQQ','SPY'):
        exact(c['captured_artifacts'][ticker]['path'],str(capture_folder/f'{ticker}.csv'))
        for role,item in [('sources',c['captured_artifacts'][ticker]),('baseline_sources',view['accounted_baseline_references'][ticker])]:
            value[role][ticker]=dict(bytes=consume(item,sources),reference=deepcopy(item))
        actual[ticker]=consume(view['baseline_references'][ticker],sources)
    tz=c['captured_artifacts']['tzif'];exact(tz['path'],str(capture_folder/'New_York.tzif'))
    value['tzif']=dict(bytes=consume(tz,sources),reference=deepcopy(tz))
    planned=checker.reconstruct_plan(parent=parent,source_bytes={t:value['sources'][t]['bytes']for t in ('QQQ','SPY')},
        source_references={t:value['sources'][t]['reference']for t in ('QQQ','SPY')},
        accounted_baseline_bytes={t:value['baseline_sources'][t]['bytes']for t in ('QQQ','SPY')},actual_baseline_bytes=actual,
        capture_started_at=c['capture_started_at'],capture_completed_at=c['capture_completed_at'],tzif_bytes=value['tzif']['bytes'],
        tzif_reference=tz,parent_checker=parent_checker,csv_rows=csv_rows)
    exact(c['plan'],planned)
    attempts=attempt_inventory(parent,sources,output)
    def final_guard():
        namespaces();exact(attempt_inventory(parent,{},output),attempts);guard(sources)
    final_guard()
    core=private_module(raw['payload_core'],CORE,CORE_SHA,'_registered_payload_core')
    args=dict(parent_reference=parents['reference'],parent_readback_reference=parents['readback_reference'],
        known_typed_rows=deepcopy(view['known_typed_rows']),parent_attempt_inventory=deepcopy(view['parent_attempt_inventory']),capture=value,session=session)
    refs=dict(parent=parents,capture=captures,dependencies=deps,registration=registration_ref,runtime=writer_ref,
        registration_core=regref,reference_core=refref)
    return args,refs,sources,core,final_guard,attempts,deps['capture_checker'],view['parent_schema'],output


def resource_gate(anchor,size=0):
    require(type(size)is int and size>=0 and shutil.disk_usage(Path(anchor)).free>=5*1024**3+size,'Resource stop before write')


def save(path,value):
    raw=encode(value)
    if path.name!='failure.json':resource_gate(path.anchor,len(raw))
    with safe(path).open('xb')as stream:
        require(stream.write(raw)==len(raw),'Complete output write');stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Durable saved bytes');return dict(path=str(path),sha256=sha(raw))


def run(*,registration_path,registration_sha256,execute=False):
    require(type(execute)is bool,'Explicit bool')
    if not execute:return dict(status='NOT_EXECUTED')
    args,refs,sources,core,final_guard,attempts,checker_ref,parent_schema,output=load_inputs(registration_path,registration_sha256)
    resource_gate(output.anchor);safe(output).mkdir(parents=True,exist_ok=False)
    try:
        rt=runtime();start=now()
        metadata=dict(writer_adapter_schema=ADAPTER,actual_parent_schema=parent_schema,input_references=refs,source_hashes=deepcopy(sources),runtime=rt,
            capture_checker_reference=checker_ref,attempt_inventory_scope=INVENTORY_SCOPE,
            local_attempt_namespace_inventory=attempts,
            local_direct_child_inventory_scope=dict(root=str(RESEARCH),depth=1,semantic_writer_namespaces_scanned=True),
            external_parent_bound_attempt_inventory={path:deepcopy(value)for path,value in attempts.items()
                if Path(path).parent.parent!=RESEARCH},
            external_unregistered_attempt_discovery_performed=False)
        started_ref=save(output/'started.json',dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V4',writer_started_at_utc=start,**metadata,**FLAGS));final_guard()
        end=now();payload=core.prepare_observation_payload(**args,writer_started_at_utc=start,writer_completed_at_utc=end)
        for path,digest in payload['source_hash_claims'].items():require(sources.get(path)==digest,'Payload claim outside source closure')
        payload.update(metadata);payload.update(FLAGS)
        payload['writer_interval_role']='PRE_PAYLOAD_VALIDATION_INTERVAL_NOT_PUBLICATION_COMPLETION'
        out=save(output/'observation_payload.json',payload);final_guard();exact(runtime(),rt)
        check=now();require(core.utc(check)>=core.utc(end),'Publication clock reversal')
        late=payload['timing_classification']=='LATE_OBSERVATION'or core.utc(check)>=core.utc(payload['conservative_deadline_utc'])
        receipt=save(output/'receipt.json',dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',
            status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY',observation_id=payload['observation_id'],payload_reference=out,
            publication_check_at_utc=check,publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE',
            timing_classification='LATE_OBSERVATION'if late else payload['timing_classification'],
            month_first_actual_observation=payload['month_first_actual_observation'],**metadata,**FLAGS))
        final_guard();exact(runtime(),rt)
        for item in (started_ref,out,receipt):consume(item,{})
        namespace(output,('started.json','observation_payload.json','receipt.json'));return receipt
    except BaseException as error:
        save(output/'failure.json',dict(status='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY',error_type=type(error).__name__,
             recorded_at_utc=now(),observation_payload_must_not_be_discarded=(output/'observation_payload.json').exists(),retry_allowed=False,**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    parser.add_argument('--registration-path',required=True);parser.add_argument('--registration-sha256',required=True)
    args=parser.parse_args();print(json.dumps(run(registration_path=args.registration_path,registration_sha256=args.registration_sha256,execute=args.execute)))
