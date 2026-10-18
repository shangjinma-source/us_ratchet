"""Registered V3/V4/V5 observation writer; immutable evidence, no candidate authority."""
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
from types import ModuleType, SimpleNamespace

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
 'parent_view':(ROOT/'backtest/ndx_prospective_history_parent_view_research_v5.py','32bcabfbc08a63607b650141f7295fc1ed12a3fdeeb081527c8b32d8cc250373'),
 'compact_helpers':(ROOT/'backtest/ndx_prospective_observation_parent_history_research.py','1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'),
 'capture_checker':(ROOT/'scripts/ndx_registered_forward_capture_independent_readback_20261009_v2.py','461cbb0d792001a4096a4c5a4caa701685b245b4989c2aa685f2c03e34ac6ca1'),
 'csv_reader':(ROOT/'backtest/ndx_capture_source_csv_independent_reconstruction_research_v1.py','c9dbb1c15c12d84910842874d1800d09c73d90893b91d54865826bf240ef9787')}
AUXILIARY_DEPENDENCIES={
 'legacy_view':(ROOT/'backtest/ndx_prospective_observation_parent_history_research_v4.py','06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'),
 'independent_prefix':(ROOT/'backtest/ndx_accounted_source_prefix_independent_reconstruction_research_v1.py','b66bf0824971a94d0ba4f7f65ae91b7f6ed898c1977503fcdd15bf1fe38473b5')}
ADAPTER='REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V5'
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


def validate_capture(parent,capture,checker,parent_checker,csv_rows,sources):
    """Shared upstream original checker, never its independent readback entry."""
    view=parent_checker.inspect_parent_history_v5(parent)
    c=capture['document'];plan=c['plan'];parents={role:parent[role]for role in ROLES}
    exact(c['schema'],'SOURCE_BOUND_FORWARD_CAPTURE_V5');exact(plan['schema'],'FORWARD_PARENT_CAPTURE_PLAN_V5')
    exact(plan['status'],'ONE_NEW_SESSION_CAPTURE_CANDIDATE');exact(plan['diagnostics'],[])
    exact(capture['reader_reference'],dict(path=str(DEPENDENCIES['capture_checker'][0]),sha256=DEPENDENCIES['capture_checker'][1]))
    producer=ref(dict(path=str(checker.PRODUCER),sha256=checker.PRODUCER_SHA))
    exact(c['input_references']['runtime'],producer)
    hostdeps={key:ref(dict(path=str(ROOT/path),sha256=digest))for key,(path,digest)in checker.DEPENDENCIES.items()}
    exact(c['input_references']['dependencies'],hostdeps)
    for key,binding in [('registration_core',checker.REGISTRATION_CORE),('reference_core',checker.REFERENCE_CORE),
            ('prefix_core',checker.PREFIX_CORE),('gap_core',checker.GAP_CORE)]:
        exact(c['input_references'][key],ref(dict(path=str(binding[0]),sha256=binding[1])))
    bridge=dict(capture_references={role:capture[role]for role in ROLES},parent_references=parents,
        capture_started_at=c['capture_started_at'],capture_completed_at=c['capture_completed_at'],
        full_capture_source_references={t:c['captured_artifacts'][t]for t in ('QQQ','SPY')},
        source_evidence=plan['source_evidence'],tzif_reference=c['captured_artifacts']['tzif'])
    checker.verify_prior_capture(bridge,parent,parent_checker,csv_rows,sources)
    session=plan['candidate_session'];require(type(session)is str and session>view['last_accounted_session'],'Next unique session')
    exact(plan['actual_parent_schema'],view['parent_schema'])
    for ticker in ('QQQ','SPY'):
        evidence=plan['source_evidence'][ticker];exact(evidence['new_session_dates'],[session])
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
    # Every host anchor is checked before the first immutable source read.
    regref=ref(dict(path=str(REGISTRATION_CORE[0]),sha256=REGISTRATION_CORE[1]))
    refref=ref(dict(path=str(REFERENCE_CORE[0]),sha256=REFERENCE_CORE[1]))
    registration_ref=ref(dict(path=str(registration_path),sha256=registration_sha256))
    deps={key:ref(dict(path=str(path),sha256=digest))for key,(path,digest)in DEPENDENCIES.items()}
    auxiliary={key:ref(dict(path=str(path),sha256=digest))for key,(path,digest)in AUXILIARY_DEPENDENCIES.items()}
    writer_ref=ref(dict(path=str(SOURCE),sha256=LOADED_SHA));ref(dict(path=str(CORE),sha256=CORE_SHA));sources={}
    consume(writer_ref,sources)
    reference_core=private_module(consume(refref,sources),REFERENCE_CORE[0],REFERENCE_CORE[1],'_registered_observation_refs_v2')
    registration_core=private_module(consume(regref,sources),REGISTRATION_CORE[0],REGISTRATION_CORE[1],'_registered_observation_registration_v2',[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',reference_core)])
    exact(registration_core.REFERENCE_KERNEL_SHA256,REFERENCE_CORE[1])
    registered=registration_core.prepare_observation_runtime(registration=decode(consume(registration_ref,sources)),
        registration_reference=registration_ref,runtime_reference=writer_ref,dependency_references=deps,research_root=str(RESEARCH))
    output=safe(registered['output_directory']);require(not output.exists(),'Exclusive attempt; no retry')
    parents,captures=registered['parent'],registered['capture']
    raw={key:consume(item,sources)for key,item in deps.items()};auxraw={key:consume(item,sources)for key,item in auxiliary.items()}
    helper=private_module(raw['compact_helpers'],DEPENDENCIES['compact_helpers'][0],DEPENDENCIES['compact_helpers'][1],'_registered_observation_helper_v2')
    legacy=private_module(auxraw['legacy_view'],AUXILIARY_DEPENDENCIES['legacy_view'][0],AUXILIARY_DEPENDENCIES['legacy_view'][1],'_registered_observation_legacy_v2',[
        ('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',helper)])
    exact(legacy.DEPENDENCY_SHA256,DEPENDENCIES['compact_helpers'][1])
    parent_checker=private_module(raw['parent_view'],DEPENDENCIES['parent_view'][0],DEPENDENCIES['parent_view'][1],'_registered_observation_parent_v2',[
        ('from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy','legacy',legacy)])
    exact(parent_checker.LEGACY_VIEW_SHA256,AUXILIARY_DEPENDENCIES['legacy_view'][1])
    checker=private_module(raw['capture_checker'],DEPENDENCIES['capture_checker'][0],DEPENDENCIES['capture_checker'][1],'_registered_capture_checks_v2')
    checker.CURRENT=CURRENT
    for key in ('parent_view','legacy_view','compact_helpers'):
        binding=AUXILIARY_DEPENDENCIES[key]if key in AUXILIARY_DEPENDENCIES else DEPENDENCIES[key]
        path,digest=checker.DEPENDENCIES[key];require(ROOT/path==binding[0]and digest==binding[1],'Fixed upstream host dependency')
    require(checker.CSV_READER==DEPENDENCIES['csv_reader'],'Fixed upstream CSV checker')
    require(checker.PRODUCER_SHA=='915fda6119f9ba1ce4e966a6557c18e2d0840dd7f40269dadc22bf2fd30b530f','Fixed capture producer')
    csv_rows=private_module(raw['csv_reader'],DEPENDENCIES['csv_reader'][0],DEPENDENCIES['csv_reader'][1],'_registered_capture_csv_v2').csv_rows
    prefix=private_module(auxraw['independent_prefix'],AUXILIARY_DEPENDENCIES['independent_prefix'][0],AUXILIARY_DEPENDENCIES['independent_prefix'][1],'_registered_independent_prefix_v2')
    parent=checker.load_parent_envelope(parents,sources)
    inventories=checker.verify_parent_chain(parent,parent_checker,SimpleNamespace(derive_accounted_prefix=prefix.reconstruct_accounted_prefix),csv_rows,sources)
    capture=envelope(captures,sources);session,view=validate_capture(parent,capture,checker,parent_checker,csv_rows,sources)
    inventories.append(('capture',captures));c=capture['document'];capture_folder=Path(captures['reference']['path']).parent
    # Recheck current capture registration against pinned producer host bindings.
    cr=c['input_references']['registration_core'];capture_registration=decode(consume(c['input_references']['registration'],sources))
    capture_reg=private_module(consume(cr,sources),cr['path'],cr['sha256'],'_upstream_capture_registration_v2',[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',reference_core)])
    exact(capture_reg.REFERENCE_KERNEL_SHA256,REFERENCE_CORE[1])
    capdeps={key:dict(path=str(ROOT/path),sha256=digest)for key,(path,digest)in checker.DEPENDENCIES.items()}
    cp=capture_reg.prepare_forward_capture_runtime(registration=capture_registration,registration_reference=c['input_references']['registration'],
        runtime_reference=dict(path=str(checker.PRODUCER),sha256=checker.PRODUCER_SHA),dependency_references=capdeps,research_root=str(RESEARCH))
    exact(cp['parent'],parents);exact(cp['output_directory'],str(capture_folder))
    value=dict(reference=captures['reference'],started_at_utc=c['capture_started_at'],completed_at_utc=c['capture_completed_at'],sources={},baseline_sources={})
    for ticker in ('QQQ','SPY'):
        for role,item in [('sources',c['captured_artifacts'][ticker]),('baseline_sources',view['accounted_baseline_references'][ticker])]:
            value[role][ticker]=dict(bytes=consume(item,sources),reference=deepcopy(item))
    tz=c['captured_artifacts']['tzif'];value['tzif']=dict(bytes=consume(tz,sources),reference=deepcopy(tz))
    attempts=attempt_inventory(parent,sources,output)
    def final_guard():
        for kind,bound in inventories:
            if kind=='parent':checker.parent_inventories(bound,{})
            else:
                checker.namespace(Path(bound['reference']['path']).parent,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'))
                checker.namespace(Path(bound['readback_reference']['path']).parent,('started.json','independent_readback.json'))
        exact(attempt_inventory(parent,{},output),attempts);guard(sources)
    final_guard()
    core=private_module(raw['payload_core'],CORE,CORE_SHA,'_registered_payload_core_v2')
    args=dict(parent_reference=parents['reference'],parent_readback_reference=parents['readback_reference'],
        known_typed_rows=deepcopy(view['known_typed_rows']),parent_attempt_inventory=deepcopy(view['parent_attempt_inventory']),capture=value,session=session)
    refs=dict(parent=parents,capture=captures,dependencies=deps,auxiliary_dependencies=auxiliary,registration=registration_ref,runtime=writer_ref,
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
            capture_checker_reference=checker_ref,shared_upstream_capture_checker_called=True,capture_readback_called=False,
            independent_prefix_checker_reference=refs['auxiliary_dependencies']['independent_prefix'],
            producer_prefix_core_called=False,gap_core_called=False,attempt_inventory_scope=INVENTORY_SCOPE,
            local_attempt_namespace_inventory=attempts,
            local_direct_child_inventory_scope=dict(root=str(RESEARCH),depth=1,semantic_writer_namespaces_scanned=True),
            external_parent_bound_attempt_inventory={path:deepcopy(value)for path,value in attempts.items()
                if Path(path).parent.parent!=RESEARCH},
            external_unregistered_attempt_discovery_performed=False)
        started_ref=save(output/'started.json',dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V5',writer_started_at_utc=start,**metadata,**FLAGS));final_guard()
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
