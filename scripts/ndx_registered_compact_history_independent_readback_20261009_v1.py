"""Registered compact V4 readback. Independent append formula, shared parent checks.

No publisher, new/old append algorithm or observation writer is called.
Producer is pinned; each run requires external immutable artifact references.
"""
import argparse
import base64
from copy import deepcopy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import ModuleType

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESEARCH=ROOT/'data/cache/research'
PRODUCER=ROOT/'scripts/ndx_registered_compact_history_runtime_20261009_v1.py'
PRODUCER_SHA='cf9ac506c5a7603c9b5addf6d319dbf48038ab2bf32c649057129f02df6b6fa6'
REGISTRATION_CORE=(ROOT/'backtest/ndx_compact_history_runtime_registration_research_v1.py','d0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')
DEPENDENCIES={
 'history_core':(ROOT/'backtest/ndx_prospective_observation_parent_history_research_v4.py','06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'),
 'compact_helpers':(ROOT/'backtest/ndx_prospective_observation_parent_history_research.py','1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0')}
CSV_READER=(ROOT/'scripts/ndx_variable_prefix_capture_independent_readback_20261003.py','aed7b71289fb30473cedefda00c6377c0700bea115e5d99328c1c20dd4572dbe')
ROLES=('reference','publication_reference','readback_reference','reader_reference')
OBS_ROLES=('payload_reference','receipt_reference','audit_reference','reader_reference')
WRAPPER_FALSE=('source_authenticity_verified','clock_authenticity_verified','filesystem_attempt_inventory_authenticated',
 'point_in_time_verified','candidate_seal_allowed','cohort_registration_allowed','promotion_allowed',
 'live_mutation_allowed','future_independent_oos','observation_created','old_calendar_mutated',
 'network_capture_performed','full_transitive_source_closure_reverified')
HISTORY_FALSE=WRAPPER_FALSE+('parent_history_authenticated_by_this_module','timeliness_verified',
 'production_generator_authorized','seal_event_created','partial_recovery_performed','canonical_calendar_append_allowed',
 'retrospective_backfill_allowed','decision_eligible','accounted_baseline_scope_verified','full_source_byte_prefix_verified','gap_append_supported')
OPTIONAL_FALSE=set(HISTORY_FALSE)|{'receipt_published','exchange_holidays_verified','early_closes_verified',
 'parent_attempt_inventory_completeness_verified','seal_status_event_created','final_durable_completion_time_verified'}
COUNT_KEYS=('parent_typed_row_count','parent_actual_observation_count','typed_row_count','observation_count',
 'new_observation_count','gap_count','last_observed_session','last_accounted_session','first_actual_observed_session_by_month')


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
    require(type(digest)is str and len(digest)==64 and all(c in '0123456789abcdef'for c in digest),'Pending immutable anchor')
    require(type(path)is str and path and path.strip()==path and '\x00'not in path,'Reference path')
    return dict(path=path,sha256=digest)


def merge(sources,item):
    require(type(item)is dict and set(item)=={'path','sha256'},'Exact reference fields')
    reference(item['path'],item['sha256'])
    require(item['path']not in sources or sources[item['path']]==item['sha256'],'Conflicting source claim')
    sources[item['path']]=item['sha256']


def collect(value,sources):
    if type(value)is dict:
        if 'path'in value and 'sha256'in value:merge(sources,{key:value[key]for key in ('path','sha256')})
        for key,item in value.items():
            if key in ('source_hashes','source_reference_claims'):
                require(type(item)is dict,'Source map')
                for path,digest in item.items():merge(sources,reference(path,digest))
            else:collect(item,sources)
    elif type(value)is list:
        for item in value:collect(item,sources)


def flags(value,mandatory):
    for key in mandatory:require(value.get(key)is False,'Strict false '+key)
    for key in OPTIONAL_FALSE.intersection(value):require(value[key]is False,'Optional authority '+key)


def integer(value,expected):require(type(value)is int and value==expected,'Exact integer')


def private_module(path,raw,expected,injected=None,remove=None):
    exact(sha(raw),expected);text=raw.decode('utf-8-sig')
    if remove is not None:
        require(text.count(remove)==1,'Private import closure');text=text.replace(remove,'')
    module=ModuleType('_independent_registered_'+Path(path).stem);module.__file__=str(path)
    module.__dict__.update(injected or {});exec(compile(text,str(path),'exec'),module.__dict__)
    return module


def reconstruct_history(*,parent,observation,parent_checker,csv_rows,blobs):
    """Shared upstream structure check; current append reconstructed independently."""
    view=parent_checker.inspect_parent_history_v4(parent)
    known=deepcopy(view['known_typed_rows']);oldknown=deepcopy(known)
    entries=deepcopy(view['observations']);attempts=deepcopy(view['parent_attempt_inventory'])
    sources=deepcopy(view['source_hashes'])
    require(type(observation)is dict and set(observation)==set(OBS_ROLES)|{'payload','receipt','audit'},'Complete observation')
    for role in OBS_ROLES:merge(sources,observation[role])
    p,r,a=(observation[key]for key in ('payload','receipt','audit'))
    for item in (p,r,a):
        collect(item,sources);flags(item,('source_authenticity_verified','clock_authenticity_verified',
            'filesystem_attempt_inventory_authenticated','candidate_seal_allowed','cohort_registration_allowed',
            'point_in_time_verified','promotion_allowed','live_mutation_allowed','future_independent_oos','production_generator_authorized'))
    exact(p['schema'],'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1');exact(r['schema'],'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1')
    exact(r['status'],'PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY')
    exact(a['schema'],'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3');exact(a['status'],'PASS')
    require(a['writer_called']is False and a['payload_core_called']is False and a['old_audit_repeated']is False,'Independent observation role')
    exact(r['payload_reference'],observation['payload_reference']);exact(a['payload_reference'],observation['payload_reference'])
    exact(a['receipt_reference'],observation['receipt_reference']);exact(a['reader_sha256'],observation['reader_reference']['sha256'])
    exact(a['parent_history_reference'],parent['reference']);exact(p['source_hashes'],r['source_hashes'])
    for path,digest in p['source_hashes'].items():exact(a['source_hashes'].get(path),digest)
    for role in ('payload_reference','receipt_reference','reader_reference'):
        item=observation[role];exact(a['source_hashes'].get(item['path']),item['sha256'])
    exact(p['known_typed_rows_preserved'],known);exact(p['parent_attempt_inventory_preserved'],attempts)
    exact(p['parent_readback_reference'],parent['readback_reference'])
    parent_refs={role:parent[role]for role in ROLES}
    for item in (p,r,a):exact(item['input_references']['parent'],parent_refs)
    capture=p['input_references']['capture'];require(set(capture)==set(ROLES),'Capture four anchors')
    for role in ROLES:merge(sources,capture[role])
    for item in (r,a):exact(item['input_references']['capture'],capture)
    for item in (*parent_refs.values(),*capture.values()):exact(p['source_hashes'].get(item['path']),item['sha256'])
    session=p['session'];d=date.fromisoformat(session)
    require(d.isoformat()==session and d.weekday()<5 and session>known[-1]['session'],'New canonical session')
    identity=dict(parent_reference=parent['reference'],capture_reference=capture['reference'],session=session)
    exact(p['observation_identity'],identity);identifier=sha(encode(identity))
    exact(p['observation_id'],identifier);exact(r['observation_id'],identifier)
    require(identifier not in {entry['observation_id']for entry in entries},'Unique observation')
    integer(p['sequence'],len(known)+1);exact(p['kind'],'PROSPECTIVE_OBSERVED_SESSION');exact(p['initial_seal_status'],'NOT_ATTEMPTED')
    first=view['first_actual_observed_session_by_month'].get(session[:7],session)
    exact(p['first_actual_observed_session_of_month'],first)
    for item in (p,r):exact(item['month_first_actual_observation'],first==session)
    for item in (p,r):require(item['timing_classification']in ('LATE_OBSERVATION','WITHIN_CONSERVATIVE_OBSERVATION_WINDOW'),'Timing class')
    require(p['timing_classification']!='LATE_OBSERVATION'or r['timing_classification']=='LATE_OBSERVATION','No late upgrade')
    counts=a['counts'];flags(counts,())
    for key,n in [('parent_typed_row_count',len(known)),('parent_actual_observation_count',len(entries)),
        ('parent_observed_count',sum(row['kind']!='MISSED_OBSERVATION'for row in known)),
        ('parent_gap_count',sum(row['kind']=='MISSED_OBSERVATION'for row in known)),('new_observation_count',1)]:integer(counts[key],n)
    exact(counts['month_first_actual_observation'],r['month_first_actual_observation']);exact(counts['timing_classification'],r['timing_classification'])
    tz=p['tzif_reference'];merge(sources,tz);exact(tz['sha256'],view['tzif_reference']['sha256'])
    exact(p['source_hashes'].get(tz['path']),tz['sha256']);exact(sha(base64.b64decode(p['tzif_bytes_base64'],validate=True)),tz['sha256'])
    require(blobs[tz['path']]==base64.b64decode(p['tzif_bytes_base64'],validate=True),'Original saved TZif bytes')
    require(set(p['full_original_sources_preserved'])=={'QQQ','SPY'},'Complete source pair')
    captured,previous={},{}
    for ticker in ('QQQ','SPY'):
        parts=p['full_original_sources_preserved'][ticker];exact(sorted(parts),['baseline_sources','sources'])
        values={}
        for role in ('baseline_sources','sources'):
            part=parts[role];item=part['reference'];merge(sources,item)
            exact(p['source_hashes'].get(item['path']),item['sha256'])
            raw=blobs[item['path']];exact(sha(raw),item['sha256'])
            require(raw==base64.b64decode(part['original_csv_bytes_base64'],validate=True),'Saved CSV equals payload original bytes')
            rows,_=csv_rows(raw,known[0]['session']);exact(rows,part['rows']);exact(part['required_scope_start'],known[0]['session'])
            values[role]=(raw,rows)
        old,current=values['baseline_sources'],values['sources']
        exact(parts['baseline_sources']['reference'],view['accounted_baseline_references'][ticker])
        require(current[0].startswith(old[0]),'Complete accounted byte prefix')
        scoped=lambda rows:[row['Date']for row in rows if row['Date']>=known[0]['session']]
        exact(scoped(old[1]),[row['session']for row in known]);exact(scoped(current[1]),[row['session']for row in known]+[session])
        exact(current[1][:-1],old[1])
        actualref=view['baseline_references'][ticker];actual=blobs[actualref['path']]
        exact(sha(actual),actualref['sha256']);require(old[0].startswith(actual),'Complete last actual byte prefix')
        actualrows,_=csv_rows(actual,known[0]['session'])
        exact(scoped(actualrows),[row['session']for row in known if row['session']<=view['last_observed_session']])
        captured[ticker]=deepcopy(parts['sources']['reference']);previous[ticker]=deepcopy(parts['baseline_sources']['reference'])
    known.append(dict(sequence=p['sequence'],session=session,kind='PROSPECTIVE_OBSERVED_SESSION',seal_status='NOT_ATTEMPTED',
        evidence_reference=dict(observation['payload_reference'],json_pointer='/observation_identity')))
    months={}
    for row in known:
        if row['kind']!='MISSED_OBSERVATION':months.setdefault(row['session'][:7],row['session'])
    entry={key:deepcopy(p[key])for key in ('observation_id','session','sequence','observation_identity','initial_seal_status',
        'month_first_actual_observation','first_actual_observed_session_of_month')}
    entry.update(schema='COMPACT_OBSERVATION_REFERENCE_ENTRY_V1',original_payload_embedded=False,
        timing_classification=r['timing_classification'],payload_timing_classification=p['timing_classification'],
        captured_baseline_references=captured,previous_baseline_references=previous,
        original_source_hash_claims={key:deepcopy(observation[key]['source_hashes'])for key in ('payload','receipt','audit')})
    entry.update({role:deepcopy(observation[role])for role in OBS_ROLES});entries.append(entry)
    attempts.append(dict(observation_id=identifier,session=session,status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',
        payload_reference=deepcopy(observation['payload_reference']),receipt_reference=deepcopy(observation['receipt_reference']),
        independent_readback_reference=deepcopy(observation['audit_reference'])))
    return dict(schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V4',status='APPENDED_ONE_RESEARCH_OBSERVATION_NO_SEAL',
        policy_id='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH',parent_references=deepcopy(parent_refs),
        observation_references={role:deepcopy(observation[role])for role in OBS_ROLES},genesis_preserved=deepcopy(view['genesis_preserved']),
        known_typed_rows=known,known_typed_rows_preserved=oldknown,observations=entries,parent_attempt_inventory=attempts,
        parent_typed_row_count=len(oldknown),parent_actual_observation_count=len(entries)-1,typed_row_count=len(known),
        observation_count=len(entries),new_observation_count=1,gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in known),
        first_actual_observed_session_by_month=months,baseline_references=deepcopy(captured),
        baseline_role='LAST_ACTUAL_OBSERVATION_BASELINE_NOT_LAST_ACCOUNTED',accounted_baseline_references=deepcopy(captured),
        accounted_baseline_role='FULL_SAVED_CSV_SCOPE_EQUALS_ALL_KNOWN_TYPED_SESSIONS',last_observed_session=session,
        last_accounted_session=session,tzif_reference=deepcopy(tz),source_hashes=deepcopy(sources),source_reference_claims=deepcopy(sources),
        observation_storage='COMPACT_EXTERNAL_REFERENCES_NO_CSV_ROWS_OR_BASE64',
        authentication_role='STRUCTURAL_DECLARATIONS_ONLY_BYTES_AND_SCOPE_AUTHENTICATION_REMAIN_EXTERNAL',
        raw_source_bytes_embedded=False,dependency_sha256=DEPENDENCIES['compact_helpers'][1],**dict.fromkeys(HISTORY_FALSE,False))


def safe(path):
    path=Path(path);require(path.is_absolute(),'Absolute evidence path')
    for item in (path,*path.parents):require(not item.is_symlink()and not getattr(item,'is_junction',lambda:False)(),'Linked evidence path')
    return path


def consume(item,sources):
    require(type(item)is dict and set(item)=={'path','sha256'},'Exact IO reference')
    reference(item['path'],item['sha256']);path=safe(item['path'])
    require(path.is_file()and path.stat().st_size<=64*1024**2 and not(path.parent/'failure.json').exists(),'Bounded nonfailed source')
    require(path.resolve()not in {(ROOT/'data/cache'/f'{t}.csv').resolve()for t in ('QQQ','SPY')},'No mutable cache source')
    for old,digest in sources.items():
        if Path(old)==path:exact(digest,item['sha256'])
    raw=path.read_bytes();exact(sha(raw),item['sha256']);sources[str(path)]=item['sha256'];return raw


def guard(sources):
    for path,digest in list(sources.items()):consume(reference(path,digest),{})


def namespace(folder,names,sources):
    items=list(safe(folder).iterdir());exact(sorted(item.name for item in items),sorted(names))
    for item in items:
        require(safe(item).is_file()and item.stat().st_size<=64*1024**2,'Bounded namespace file')
        raw=item.read_bytes();consume(reference(str(item),sha(raw)),sources)


def envelope(refs,roles,sources):
    result=deepcopy(refs)
    for key,role in roles:
        result[key]=decode(consume(refs[role],sources))
        for path,digest in result[key]['source_hashes'].items():consume(reference(path,digest),sources)
    consume(refs['reader_reference'],sources);return result


def save(path,value):
    raw=encode(value)
    if path.name!='failure.json':require(shutil.disk_usage(path.anchor).free>=5*1024**3+len(raw),'Resource stop before write')
    with safe(path).open('xb')as stream:
        require(stream.write(raw)==len(raw),'Complete write');stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Durable saved bytes');return reference(str(path),sha(raw))


def readback(*,registration_path,registration_sha256,history_reference,publication_reference,output_directory,execute=False):
    require(execute is True,'Explicit compact independent readback')
    producer_ref=reference(str(PRODUCER),PRODUCER_SHA);registration_ref=reference(str(registration_path),registration_sha256)
    merge({},history_reference);merge({},publication_reference)
    regcore_ref=reference(str(REGISTRATION_CORE[0]),REGISTRATION_CORE[1])
    dependencies={key:reference(str(path),digest)for key,(path,digest)in DEPENDENCIES.items()}
    producer_sources={};consume(producer_ref,producer_sources)
    regcore=private_module(REGISTRATION_CORE[0],consume(regcore_ref,producer_sources),REGISTRATION_CORE[1])
    registration=decode(consume(registration_ref,producer_sources))
    plan=regcore.prepare_compact_history_runtime(registration=registration,registration_reference=registration_ref,
        runtime_reference=producer_ref,dependency_references=dependencies,research_root=str(RESEARCH))
    output=safe(output_directory);outcanon=regcore.canonical_path(str(output));rootcanon=regcore.canonical_path(str(RESEARCH))
    require(outcanon.parent==rootcanon and outcanon!=regcore.canonical_path(plan['output_directory'])and not output.exists(),'Independent create-only output namespace')
    require(output.name.isascii()and output.name[0].islower()and all(c.islower()or c.isdigit()or c=='_'for c in output.name)and 3<=len(output.name)<=120,'Stable readback namespace')
    producer_output=Path(plan['output_directory'])
    exact(history_reference['path'],str(producer_output/'history.json'));exact(publication_reference['path'],str(producer_output/'publication.json'))
    for item in (registration_ref,producer_ref,*dependencies.values(),*plan['parent'].values(),*plan['observation'].values()):
        source=regcore.canonical_path(item['path']);require(source!=outcanon and outcanon not in source.parents,'Readback aliases an input')
    helper=private_module(DEPENDENCIES['compact_helpers'][0],consume(dependencies['compact_helpers'],producer_sources),DEPENDENCIES['compact_helpers'][1])
    parent_checker=private_module(DEPENDENCIES['history_core'][0],consume(dependencies['history_core'],producer_sources),DEPENDENCIES['history_core'][1],
        dict(compact=helper),'from backtest import ndx_prospective_observation_parent_history_research as compact')
    parent=envelope(plan['parent'],(('document','reference'),('publication','publication_reference'),('readback','readback_reference')),producer_sources)
    observation=envelope(plan['observation'],(('payload','payload_reference'),('receipt','receipt_reference'),('audit','audit_reference')),producer_sources)
    parent_folder=Path(parent['reference']['path']).parent;audit_folder=Path(parent['readback_reference']['path']).parent
    exact(parent['reference']['path'],str(parent_folder/'history.json'));exact(parent['publication_reference']['path'],str(parent_folder/'publication.json'))
    observation_folder=Path(observation['payload_reference']['path']).parent
    for role,name in [('payload_reference','observation_payload.json'),('receipt_reference','receipt.json'),('audit_reference','independent_readback.json')]:exact(observation[role]['path'],str(observation_folder/name))
    def upstream_inventories():
        namespace(parent_folder,{'started.json','history.json','publication.json'}|({'independent_readback.json'}if audit_folder==parent_folder else set()),producer_sources)
        if audit_folder!=parent_folder:namespace(audit_folder,('started.json','independent_readback.json'),producer_sources)
        namespace(observation_folder,('started.json','observation_payload.json','receipt.json','independent_readback.json'),producer_sources)
    upstream_inventories()
    blobs={}
    for path,digest in observation['payload']['source_hashes'].items():blobs[path]=consume(reference(path,digest),producer_sources)
    view=parent_checker.inspect_parent_history_v4(parent)
    for item in (*view['baseline_references'].values(),*view['accounted_baseline_references'].values()):blobs[item['path']]=consume(item,producer_sources)
    sources=dict(producer_sources);sources[str(SOURCE)]=LOADED_SHA
    csvref=reference(str(CSV_READER[0]),CSV_READER[1]);csv_rows=private_module(CSV_READER[0],consume(csvref,sources),CSV_READER[1]).csv_rows
    expected=reconstruct_history(parent=parent,observation=observation,parent_checker=parent_checker,csv_rows=csv_rows,blobs=blobs)
    for path,digest in expected['source_hashes'].items():consume(reference(path,digest),producer_sources)
    for path,digest in producer_sources.items():merge(sources,reference(path,digest))
    inputs=dict(parent=deepcopy(plan['parent']),observation=deepcopy(plan['observation']),registration=registration_ref,
        runtime=producer_ref,dependencies=dependencies,registration_core=regcore_ref)
    d=decode(consume(history_reference,sources));p=decode(consume(publication_reference,sources))
    exact(d,dict(schema='SOURCE_BOUND_PROSPECTIVE_OBSERVATION_HISTORY_V4',history=expected,input_references=inputs,
        source_hashes=producer_sources,**dict.fromkeys(WRAPPER_FALSE,False)))
    counts={key:expected[key]for key in COUNT_KEYS}
    exact(p,dict(schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V4',status='PUBLISHED_OBSERVATION_HISTORY_NO_SEAL',
        history_reference=history_reference,input_references=inputs,counts=counts,source_hashes=producer_sources,**dict.fromkeys(WRAPPER_FALSE,False)))
    started_path=safe(producer_output/'started.json');require(started_path.is_file()and started_path.stat().st_size<=64*1024**2,'Bounded publisher start')
    raw=started_path.read_bytes();started_ref=reference(str(started_path),sha(raw));consume(started_ref,sources)
    exact(decode(raw),dict(schema='PROSPECTIVE_OBSERVATION_HISTORY_STARTED_V4',input_references=inputs,source_hashes=producer_sources,**dict.fromkeys(WRAPPER_FALSE,False)))
    def final_guard():
        upstream_inventories();namespace(producer_output,('started.json','history.json','publication.json'),sources);guard(sources)
    final_guard();require(shutil.disk_usage(output.anchor).free>=5*1024**3,'Resource stop before namespace');output.mkdir(parents=True,exist_ok=False)
    try:
        save(output/'started.json',dict(schema='PROSPECTIVE_OBSERVATION_HISTORY_READBACK_STARTED_V4',history_reference=history_reference,
            publication_reference=publication_reference,registration_reference=registration_ref,reader_sha256=LOADED_SHA,**dict.fromkeys(WRAPPER_FALSE,False)))
        report=save(output/'independent_readback.json',dict(schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V4',
            status='PURE_COMPACT_HISTORY_READBACK_PASS',history_reference=history_reference,publication_reference=publication_reference,
            input_references=inputs,reader_sha256=LOADED_SHA,source_hashes=sources,counts=counts,
            entire_history_independently_reconstructed=True,publisher_called=False,new_pure_called=False,current_live_cache_read_or_reverified=False,
            shared_upstream_parent_checker_reference=dependencies['history_core'],shared_parent_checker_called=True,
            append_algorithm_called=False,reconstruction_scope='CURRENT_V4_RESULT_FROM_BOUND_PARENT_AND_INDEPENDENT_APPEND_FORMULA_SHARED_PARENT_CHECKER',
            started_reference_observed_not_external_anchor=started_ref,started_externally_authenticated=False,**dict.fromkeys(WRAPPER_FALSE,False)))
        final_guard();consume(report,{});namespace(output,('started.json','independent_readback.json'),{});return report
    except BaseException as error:
        save(output/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,automatic_retry_allowed=False,**dict.fromkeys(WRAPPER_FALSE,False)));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration-path','registration-sha256','history-path','history-sha256','publication-path','publication-sha256','output-directory'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(readback(registration_path=args.registration_path,registration_sha256=args.registration_sha256,
        history_reference=reference(args.history_path,args.history_sha256),publication_reference=reference(args.publication_path,args.publication_sha256),
        output_directory=args.output_directory,execute=args.execute)))
