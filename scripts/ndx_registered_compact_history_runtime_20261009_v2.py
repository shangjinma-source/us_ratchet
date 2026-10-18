"""Create-only compact V4 publisher driven by an immutable external registration.

No real observation is created here. An independently read observation is required.
The append core anchor is pending. No publication may execute until it is bound.
"""
import argparse
from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
import base64
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
from types import ModuleType,SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESEARCH = ROOT / 'data/cache/research'
REGISTRATION_CORE = (ROOT / 'backtest/ndx_compact_history_runtime_registration_research_v1.py', 'd0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')
DEPENDENCIES = {
    'history_core': (ROOT / 'backtest/ndx_prospective_observation_compact_append_research_v2.py', '44225869dba5f852809c02390bc455c07fa3596383bf8b5fc992352f03bdddf9'),
    'compact_helpers': (ROOT / 'backtest/ndx_prospective_observation_parent_history_research.py',
        '1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'),
}

AUXILIARIES={
 'legacy_capture_checker_v3':(ROOT/'scripts/ndx_forward_gap_parent_capture_independent_readback_20261009_v3.py','3033e66b57b2ccfcf3bbdf091149f0c43c8c7d93387c087c5ba48fa17271cd45'),
 'parent_view':(ROOT/'backtest/ndx_prospective_history_parent_view_research_v5.py','32bcabfbc08a63607b650141f7295fc1ed12a3fdeeb081527c8b32d8cc250373'),
 'legacy_view':(ROOT/'backtest/ndx_prospective_observation_parent_history_research_v4.py','06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'),
 'capture_checker':(ROOT/'scripts/ndx_registered_forward_capture_independent_readback_20261009_v2.py','461cbb0d792001a4096a4c5a4caa701685b245b4989c2aa685f2c03e34ac6ca1'),
 'observation_reader':(ROOT/'scripts/ndx_registered_observation_independent_readback_20261009_v2.py','5634b2a6ad7b74534eed2c5a215e5f16946cb2cca40ecad52218cec32a665e61'),
 'csv_reader':(ROOT/'backtest/ndx_capture_source_csv_independent_reconstruction_research_v1.py','c9dbb1c15c12d84910842874d1800d09c73d90893b91d54865826bf240ef9787'),
 'independent_prefix':(ROOT/'backtest/ndx_accounted_source_prefix_independent_reconstruction_research_v1.py','b66bf0824971a94d0ba4f7f65ae91b7f6ed898c1977503fcdd15bf1fe38473b5'),
 'legacy_observer_v3':(ROOT/'scripts/ndx_prospective_observation_independent_readback_v3_20261009.py','fc9ca159559a499d5239dfffb330e194556d49cc639d7939beb58f1483ee8936'),
 'legacy_observer_v4':(ROOT/'scripts/ndx_registered_observation_independent_readback_20261009_v1.py','adb3f44b610262a7629b5b9129f85e447952254fb6fb67721d48e574bfc057da'),
 'legacy_compact_publisher':(ROOT/'scripts/ndx_registered_compact_history_runtime_20261009_v1.py','cf9ac506c5a7603c9b5addf6d319dbf48038ab2bf32c649057129f02df6b6fa6'),
 'gap_publisher':(ROOT/'scripts/ndx_registered_gap_history_runtime_20261009_v1.py','05d2a8d216aabd031c1325f8b63ce2b21b3e4020d6b23c6c131e6afb563daeed'),
 'gap_reader':(ROOT/'scripts/ndx_registered_gap_history_independent_readback_20261009_v1.py','cbf8f093a933ed07c8da541b5fb04ff0515a6850cd61dee3ce0a19bcfcf4e2eb'),
 'legacy_compact_reader':(ROOT/'scripts/ndx_registered_compact_history_independent_readback_20261009_v1.py','6a17d3ad5758ff72feeaa653088b3b94819d5096b5ec005690351a6981917e0f'),
 'legacy_csv_reader':(ROOT/'scripts/ndx_variable_prefix_capture_independent_readback_20261003.py','aed7b71289fb30473cedefda00c6377c0700bea115e5d99328c1c20dd4572dbe'),
 'gap_registration':(ROOT/'backtest/ndx_gap_runtime_registration_research_v1.py','6ad72acda28688cb25383bd4385da437ae7733060cb096341120178cd9e90092')}
CURRENT={ticker:ROOT/'data/cache'/(ticker+'.csv')for ticker in ('QQQ','SPY')}
ADAPTER='TRUE_V5_PARENT_REGISTERED_COMPACT_ACTUAL_RUNTIME_V2'
GRAPH_SCOPE='BOUND_ACTUAL_V4_AND_GAP_V5_PARENT_EDGES_WITH_GLOBAL_DEPTH_AND_FINAL_NAMESPACES_NOT_EXTERNAL_AUTHENTICATION'
MAX_PARENT_DEPTH=128
ROLES=('reference','publication_reference','readback_reference','reader_reference')
OBSERVATION_ROLES=('payload_reference','receipt_reference','audit_reference','reader_reference')

FLAGS = dict.fromkeys(('source_authenticity_verified','clock_authenticity_verified',
    'filesystem_attempt_inventory_authenticated','point_in_time_verified','candidate_seal_allowed',
    'cohort_registration_allowed','promotion_allowed','live_mutation_allowed','future_independent_oos',
    'observation_created','old_calendar_mutated','network_capture_performed',
    'full_transitive_source_closure_reverified'),False)


def require(condition, message):
    if not condition: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def reference(path, digest):
    require(type(digest) is str and len(digest)==64 and set(digest)<=set('0123456789abcdef'),
        'Pending immutable anchor')
    return dict(path=str(path),sha256=digest)


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def decode(raw):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate JSON key');result[key]=value
        return result
    def invalid(value): raise ValueError('Nonfinite JSON '+value)
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)


def safe(path):
    path=Path(path)
    require(path.is_absolute(),'Absolute source/output path')
    for ancestor in (path,*path.parents):
        require(not ancestor.is_symlink() and not getattr(ancestor,'is_junction',lambda:False)(),
            'No linked source or output')
    return path


def consume(item,sources):
    require(type(item)is dict and set(item)=={'path','sha256'},'Exact source reference')
    reference(item['path'],item['sha256']);path=safe(item['path'])
    require(path.is_file() and path.stat().st_size<=64*1024**2,'Bounded regular source')
    require(not (path.parent/'failure.json').exists(),'Failed source namespace')
    require(path.resolve() not in {(ROOT/'data/cache'/f'{t}.csv').resolve() for t in ('QQQ','SPY')},
        'Immutable saved sources only')
    require(path.resolve() not in {value.resolve()for value in CURRENT.values()},'Mutable diagnostic cache forbidden before source read')
    for old,digest in sources.items():
        if Path(old)==path: require(digest==item['sha256'],'Conflicting path alias')
    raw=path.read_bytes();require(sha(raw)==item['sha256'],'Source bytes changed')
    sources[str(path)]=item['sha256'];return raw


def guard(sources):
    for path,digest in list(sources.items()):consume(reference(path,digest),{})


def namespace(folder,expected,sources):
    folder=safe(folder);items=list(folder.iterdir())
    require({item.name for item in items}==set(expected),'Exact immutable namespace '+str(folder))
    for item in items:
        require(safe(item).is_file()and item.stat().st_size<=64*1024**2,'Bounded regular namespace file')
        consume(reference(item,sha(item.read_bytes())),sources)


def load_envelope(refs,roles,sources):
    result=deepcopy(refs)
    for key,role in roles:
        result[key]=decode(consume(refs[role],sources))
        claims=result[key]['source_hashes'];require(type(claims)is dict,'Complete source claim map')
        for path,digest in claims.items():consume(reference(path,digest),sources)
    consume(refs['reader_reference'],sources)
    return result


def compile_private(path,raw,injected=None,import_line=None):
    code=raw.decode('utf-8-sig');module=ModuleType('_registered_compact_'+Path(path).stem)
    module.__file__=str(path)
    if import_line is not None:
        require(code.count(import_line)==1,'One explicit private dependency import')
        code=code.replace(import_line,'')
    module.__dict__.update(injected or {})
    exec(compile(code,str(path),'exec'),module.__dict__)
    return module


def csv_scope(raw,start):
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''))
    require(reader.fieldnames==['Date','Open','High','Low','Close','Volume'],'Saved CSV schema')
    rows=list(reader);dates=[row['Date'] for row in rows]
    require(dates==sorted(set(dates)),'Unique ordered source sessions')
    return [day for day in dates if day>=start]


def verify_baselines(view,sources):
    known=[row['session'] for row in view['known_typed_rows']]
    actual=[row['session'] for row in view['known_typed_rows'] if row['session']<=view['last_observed_session']]
    for ticker in ('QQQ','SPY'):
        old=consume(view['baseline_references'][ticker],sources)
        accounted=consume(view['accounted_baseline_references'][ticker],sources)
        require(csv_scope(old,known[0])==actual,'Exact last actual baseline scope')
        require(csv_scope(accounted,known[0])==known,'Exact accounted baseline scope')
        require(accounted.startswith(old),'Complete last-actual byte prefix')


def save(path,value):
    raw=encode(value)
    if path.name!='failure.json':
        require(shutil.disk_usage(path.anchor).free>=5*1024**3+len(raw),'Resource stop before write')
    with safe(path).open('xb') as stream:
        require(stream.write(raw)==len(raw),'Complete write');stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Durable saved bytes')
    return reference(path,sha(raw))


def private(path,raw,digest,replacements=()):
    require(sha(raw)==digest,'Private source SHA')
    code=raw.decode('utf-8-sig');module=ModuleType('_compact_v2_'+Path(path).stem);module.__file__=str(path)
    for line,key,value in replacements:
        require(code.count(line)==1,'One explicit private import');code=code.replace(line,'');module.__dict__[key]=value
    exec(compile(code,str(path),'exec'),module.__dict__);return module


def exact(left,right,message='Exact versioned original evidence'):
    require(encode(left)==encode(right),message)


def pin_namespace(folder,names,sources,inventories):
    namespace(folder,names,sources);item=(str(folder),tuple(sorted(names)))
    if item not in inventories:inventories.append(item)


def parent_documents(refs,sources):
    return load_envelope(refs,(('document','reference'),('publication','publication_reference'),('readback','readback_reference')),sources)


def observation_documents(refs,sources):
    return load_envelope(refs,(('payload','payload_reference'),('receipt','receipt_reference'),('audit','audit_reference')),sources)


def observation_originals(parent,observation,modules,sources,inventories,*,current=False):
    """Replay saved original evidence only; never run a writer or readback entry."""
    p,r,a=(observation[key]for key in ('payload','receipt','audit'))
    reader=observation['reader_reference'];allowed=[reference(*AUXILIARIES[key])for key in ('observation_reader','legacy_observer_v3','legacy_observer_v4')]
    require(reader in allowed,'Explicit supported original observation-reader role')
    if current:exact(reader,reference(*AUXILIARIES['observation_reader']))
    folder=Path(observation['payload_reference']['path']).parent
    for role,name in [('payload_reference','observation_payload.json'),('receipt_reference','receipt.json'),('audit_reference','independent_readback.json')]:
        exact(observation[role]['path'],str(folder/name))
    pin_namespace(folder,('started.json','observation_payload.json','receipt.json','independent_readback.json'),sources,inventories)
    startpath=folder/'started.json';startref=reference(startpath,sha(startpath.read_bytes()));started=decode(consume(startref,sources))
    exact(a['source_hashes'].get(startref['path']),startref['sha256'],'Original observed START association')
    exact(a['payload_reference'],observation['payload_reference']);exact(a['receipt_reference'],observation['receipt_reference'])
    exact(a['reader_sha256'],reader['sha256']);exact(a['parent_history_reference'],parent['reference'])
    view=modules['view'].inspect_parent_history_v5(parent);verify_baselines(view,sources)
    blobs={}
    for ticker in ('QQQ','SPY'):
        parts=p['full_original_sources_preserved'][ticker];exact(sorted(parts),['baseline_sources','sources'])
        for role,part in parts.items():
            raw=consume(part['reference'],sources);blobs[part['reference']['path']]=raw
            require(raw==base64.b64decode(part['original_csv_bytes_base64'],validate=True),'Original CSV bytes not merely same cells')
            rows,diagnostics=modules['observer'].parse_csv(raw,view['known_typed_rows'][0]['session'])
            exact(rows,part['rows']);exact(diagnostics,part['outside_required_scope_diagnostics'])
    tz=p['tzif_reference'];blobs[tz['path']]=consume(tz,sources)
    require(blobs[tz['path']]==base64.b64decode(p['tzif_bytes_base64'],validate=True),'Saved original TZif')
    verify_observation_timing(p,r,started,blobs[tz['path']])
    if reader==reference(*AUXILIARIES['observation_reader']):
        # Share only the frozen reader's pure current-payload arithmetic, not its IO entry/scanner.
        helper=modules['observer'];refs=p['input_references'];capture=parent_documents(refs['capture'],sources)
        bridge=dict(capture_references=refs['capture'],parent_references=refs['parent'],capture_started_at=capture['document']['capture_started_at'],
            capture_completed_at=capture['document']['capture_completed_at'],full_capture_source_references={t:capture['document']['captured_artifacts'][t]for t in ('QQQ','SPY')},
            source_evidence=capture['document']['plan']['source_evidence'],tzif_reference=capture['document']['captured_artifacts']['tzif'])
        modules['checker'].verify_prior_capture(bridge,parent,modules['view'],modules['csv'].csv_rows,sources)
        capture_inventory(refs['capture'],modules['checker'],sources,inventories,modules)
        for item in (*view['baseline_references'].values(),*view['accounted_baseline_references'].values()):blobs[item['path']]=consume(item,sources)
        helper.RESEARCH=Path(p['local_direct_child_inventory_scope']['root'])
        helper.CURRENT={t:Path(capture['document']['current_cache_references'][t]['path'])for t in ('QQQ','SPY')}
        counts=helper.inspect(p,r,started,dict(parent=parent,capture=capture),refs,observation['payload_reference'],blobs,p['session'],
            modules['checker'],p['local_attempt_namespace_inventory'],modules['view'])
        exact(a['counts'],counts)
        exact(refs['runtime'],dict(path=str(helper.WRITER),sha256=helper.WRITER_SHA),'Fixed original writer')
        exact(p['writer_adapter_schema'],helper.ADAPTER);exact(p['actual_parent_schema'],view['parent_schema'])
    else:
        if reader==reference(*AUXILIARIES['legacy_observer_v3']):
            verify_thin_capture(parent,observation,modules,sources,inventories)
        else:
            captures=parent_documents(p['input_references']['capture'],sources);c=captures['document']
            bridge=dict(capture_references=p['input_references']['capture'],parent_references=p['input_references']['parent'],capture_started_at=c['capture_started_at'],capture_completed_at=c['capture_completed_at'],full_capture_source_references={t:c['captured_artifacts'][t]for t in ('QQQ','SPY')},source_evidence=c['plan']['source_evidence'],tzif_reference=c['captured_artifacts']['tzif'])
            modules['checker'].verify_prior_capture(bridge,parent,modules['view'],modules['csv'].csv_rows,sources)
            capture_inventory(p['input_references']['capture'],modules['checker'],sources,inventories,modules)
        # Original audit is externally byte-bound provenance; its entry is never executed.
        require(a['schema']=='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3'and a['status']=='PASS','Legacy readback role')
        for key in ('writer_called','payload_core_called','old_audit_repeated'):require(a[key]is False,'Legacy independent role')
    captured=parent_documents(p['input_references']['capture'],sources)['document']
    require(captured['plan']['status']=='ONE_NEW_SESSION_CAPTURE_CANDIDATE'and captured['plan']['candidate_session']==p['session']and captured['plan']['diagnostics']==[],'Explicit original unique actual candidate')
    exact(p['capture_started_at_utc'],captured['capture_started_at']);exact(p['capture_completed_at_utc'],captured['capture_completed_at'])
    exact(p['tzif_reference'],captured['captured_artifacts']['tzif'])
    claims={}
    def claim(item):
        simple={key:item[key]for key in ('path','sha256')}
        require(simple['path']not in claims or claims[simple['path']]==simple['sha256'],'Consistent original claim')
        claims[simple['path']]=simple['sha256']
    for row in view['known_typed_rows']:claim(row['evidence_reference'])
    for entry in view['parent_attempt_inventory']:
        for key in ('payload_reference','receipt_reference','independent_readback_reference'):claim(entry[key])
    for item in (parent['reference'],parent['readback_reference'],p['input_references']['capture']['reference']):claim(item)
    for ticker in ('QQQ','SPY'):
        parts=p['full_original_sources_preserved'][ticker]
        exact(parts['sources']['reference'],captured['captured_artifacts'][ticker]);exact(parts['baseline_sources']['reference'],view['accounted_baseline_references'][ticker])
        for part in parts.values():claim(part['reference'])
    claim(p['tzif_reference']);exact(p['source_hash_claims'],claims,'Exact original payload provenance')
    require(p['payload_is_not_a_published_observation_receipt']is True and p['seal_status_history_not_created']is True,'Payload evidence boundary')
    exact(p['writer_interval_role'],'PRE_PAYLOAD_VALIDATION_INTERVAL_NOT_PUBLICATION_COMPLETION')
    verify_observation_outer(parent,observation,started,startref,view,modules,sources)
    return started


def verify_observation_timing(payload,receipt,started,tzif):
    def utc(value):
        require(type(value)is str,'Original UTC string');parsed=datetime.fromisoformat(value)
        require(parsed.tzinfo is not None and parsed.utcoffset()==timedelta(0),'Aware original UTC');return parsed
    session=datetime.strptime(payload['session'],'%Y-%m-%d').date();require(session.isoformat()==payload['session']and session.weekday()<5,'Original weekday session')
    zone=ZoneInfo.from_file(io.BytesIO(tzif),key='America/New_York');close=datetime.combine(session,time(16),zone).astimezone(timezone.utc)
    following=session+timedelta(days=1)
    while following.weekday()>4:following+=timedelta(days=1)
    deadline=datetime.combine(following,time(9,30),zone).astimezone(timezone.utc)
    begin,end,ws,we,pc=map(utc,[payload['capture_started_at_utc'],payload['capture_completed_at_utc'],payload['writer_started_at_utc'],payload['writer_completed_at_utc'],receipt['publication_check_at_utc']])
    require(close<=begin<=end<=ws<=we<=pc,'Original full capture/writer/receipt interval')
    exact(started['writer_started_at_utc'],payload['writer_started_at_utc']);exact(payload['conservative_close_utc'],close.isoformat());exact(payload['conservative_deadline_utc'],deadline.isoformat())
    exact(payload['timing_classification'],'LATE_OBSERVATION'if we>=deadline else 'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')
    exact(receipt['timing_classification'],'LATE_OBSERVATION'if pc>=deadline else payload['timing_classification'])


def bound_attempt_inventory(view,research,thin=False):
    found={}
    for entry in view['observations']:
        payload=entry['payload_reference'];folder=Path(payload['path']).parent
        if thin and folder.parent!=ROOT/'data/cache/research':continue
        receipt=entry['receipt_reference'];auditref=entry['audit_reference']
        require(receipt['path']==str(folder/'receipt.json')and auditref['path']==str(folder/'independent_readback.json'),'Bounded inherited namespace')
        local={};namespace(folder,('started.json','observation_payload.json','receipt.json','independent_readback.json'),local)
        audit=decode(consume(auditref,local));start=reference(folder/'started.json',local[str(folder/'started.json')])
        exact(audit['source_hashes'].get(start['path']),start['sha256'],'Parent-bound observed START')
        exact(reference(folder/'observation_payload.json',local[str(folder/'observation_payload.json')]),payload)
        exact(reference(folder/'receipt.json',local[str(folder/'receipt.json')]),receipt)
        found[payload['path']]={'started.json':start,'observation_payload.json':payload,'receipt.json':receipt}
    return found


def verify_observation_outer(parent,observation,started,startref,view,modules,sources):
    """Exact declared formats; inherited legacy audits are not re-executed."""
    p,r,a=(observation[key]for key in ('payload','receipt','audit'));refs=p['input_references']
    reader=observation['reader_reference'];helper=modules['observer']
    thin=reader==reference(*AUXILIARIES['legacy_observer_v3'])
    latest=reader==reference(*AUXILIARIES['observation_reader'])
    writerflags={key:False for key in helper.WRITER_FALSE if not(thin and key=='parent_attempt_inventory_completeness_verified')}
    keys=['writer_adapter_schema','input_references','source_hashes','runtime','capture_checker_reference','attempt_inventory_scope','local_attempt_namespace_inventory']
    if not thin:keys+=['actual_parent_schema','local_direct_child_inventory_scope','external_parent_bound_attempt_inventory','external_unregistered_attempt_discovery_performed']
    if latest:keys+=['shared_upstream_capture_checker_called','capture_readback_called','independent_prefix_checker_reference','producer_prefix_core_called','gap_core_called']
    exact(sorted(refs),sorted(['parent','capture']if thin else ['parent','capture','dependencies','registration','runtime','registration_core','reference_core']+(['auxiliary_dependencies']if latest else [])))
    if not thin:
        dependencies={key:reference(*value)for key,value in helper.DEPENDENCIES.items()}
        writerref=reference(helper.WRITER,helper.WRITER_SHA)
        if not latest:
            dependencies.update(parent_view=reference(*AUXILIARIES['legacy_view']),capture_checker=reference(ROOT/'scripts/ndx_registered_forward_capture_independent_readback_20261009_v1.py','b44f2d2cd89f5ea4a64e268e86b409305e7e40673df6565f1d2ba8f9bdeb8cc2'),csv_reader=reference(*AUXILIARIES['legacy_csv_reader']))
            writerref=reference(ROOT/'scripts/ndx_registered_observation_writer_20261009_v1.py','8a346e221e7f8bddc9991a18cfa87c3a891dbb1b0c1afd136eb0bc64972d06bb')
        exact(refs['runtime'],writerref);exact(refs['dependencies'],dependencies)
        exact(refs['registration_core'],reference(*helper.REGISTRATION_CORE));exact(refs['reference_core'],reference(*REGISTRATION_CORE))
        if latest:exact(refs['auxiliary_dependencies'],{key:reference(*value)for key,value in helper.AUXILIARY_DEPENDENCIES.items()})
        raw=consume(refs['registration_core'],sources)
        registration=private(refs['registration_core']['path'],raw,refs['registration_core']['sha256'],[('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',modules['references'])])
        plan=registration.prepare_observation_runtime(registration=decode(consume(refs['registration'],sources)),registration_reference=refs['registration'],runtime_reference=writerref,dependency_references=dependencies,research_root=str(Path(observation['payload_reference']['path']).parent.parent))
        exact(plan['parent'],refs['parent']);exact(plan['capture'],refs['capture']);exact(plan['output_directory'],str(Path(observation['payload_reference']['path']).parent))
    else:
        writerref=reference(ROOT/'scripts/ndx_prospective_observation_writer_v3_20261009.py','00e5491007a94444bc635760d2195e0246a918350a502f7049960fb402bdea62')
        exact(p['source_hashes'].get(writerref['path']),writerref['sha256'],'Fixed thin writer original provenance')
    metadata={key:p[key]for key in keys}
    inventory=bound_attempt_inventory(view,Path(observation['payload_reference']['path']).parent.parent,thin)
    exact(metadata['local_attempt_namespace_inventory'],inventory,'Original attempt identities independently derived from parent entries')
    if not thin:
        research=Path(observation['payload_reference']['path']).parent.parent
        exact(metadata['local_direct_child_inventory_scope'],dict(root=str(research),depth=1,semantic_writer_namespaces_scanned=True))
        exact(metadata['external_parent_bound_attempt_inventory'],{path:value for path,value in inventory.items()if Path(path).parent.parent!=research})
    require(type(metadata['runtime'])is dict and set(metadata['runtime'])=={'python','executable','implementation'}and all(type(v)is str and 0<len(v)<10000 for v in metadata['runtime'].values()),'Declared runtime format')
    producer_sources={}
    def original_source(item):
        consume(item,producer_sources)
    for item in (writerref,reference(*helper.DEPENDENCIES['payload_core'])):original_source(item)
    if thin:
        original_source(reference(*AUXILIARIES['legacy_capture_checker_v3']));original_source(reference(*AUXILIARIES['legacy_csv_reader']))
    else:
        for item in (refs['registration'],refs['registration_core'],refs['reference_core'],*refs['dependencies'].values(),*refs.get('auxiliary_dependencies',{}).values()):original_source(item)
    captured=parent_documents(refs['capture'],{})
    for envelope,anchors in ((parent,refs['parent']),(captured,refs['capture'])):
        for item in anchors.values():original_source(item)
        for field in ('document','publication','readback'):
            for path,digest in envelope[field]['source_hashes'].items():original_source(reference(path,digest))
    if latest:
        for role in ('reference','readback_reference'):
            folder=Path(refs['capture'][role]['path']).parent
            for path in folder.iterdir():original_source(reference(path,sha(path.read_bytes())))
    for records in inventory.values():
        for item in records.values():original_source(item)
    exact(p['source_hashes'],producer_sources,'Whole original observation producer source closure')
    adapter='GAP_PARENT_PROSPECTIVE_OBSERVATION_WRITER_V3'if thin else 'REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V5'if latest else 'REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V4'
    exact(metadata['writer_adapter_schema'],adapter)
    exact(refs['parent'],{role:parent[role]for role in ROLES})
    if not thin:exact(metadata['actual_parent_schema'],view['parent_schema']);require(metadata['external_unregistered_attempt_discovery_performed']is False,'Bounded external attempt discovery')
    checkerref=(dict(zip(('path','sha256'),helper.CHECKER))if latest else
        reference(ROOT/'scripts/ndx_forward_gap_parent_capture_independent_readback_20261009_v3.py','3033e66b57b2ccfcf3bbdf091149f0c43c8c7d93387c087c5ba48fa17271cd45')if thin else
        reference(ROOT/'scripts/ndx_registered_forward_capture_independent_readback_20261009_v1.py','b44f2d2cd89f5ea4a64e268e86b409305e7e40673df6565f1d2ba8f9bdeb8cc2'))
    exact(metadata['capture_checker_reference'],checkerref)
    scope='LOCAL_RESEARCH_DIRECT_CHILD_WRITER_SCHEMA_NAMESPACES_NOT_FULL_FILESYSTEM_AUTHENTICATION'if thin else helper.INVENTORY_SCOPE
    exact(metadata['attempt_inventory_scope'],scope)
    if latest:
        exact(metadata['independent_prefix_checker_reference'],reference(*AUXILIARIES['independent_prefix']))
        for key,value in [('shared_upstream_capture_checker_called',True),('capture_readback_called',False),('producer_prefix_core_called',False),('gap_core_called',False)]:require(metadata[key]is value,'Declared shared role')
    version='V3'if thin else 'V5'if latest else 'V4'
    exact(started,dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_'+version,writer_started_at_utc=p['writer_started_at_utc'],**metadata,**writerflags))
    exact(r,dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY',observation_id=p['observation_id'],payload_reference=observation['payload_reference'],
        publication_check_at_utc=r['publication_check_at_utc'],publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE',timing_classification=r['timing_classification'],month_first_actual_observation=p['month_first_actual_observation'],**metadata,**writerflags))
    corekeys={'schema','observation_id','observation_identity','session','sequence','kind','initial_seal_status','month_first_actual_observation','first_actual_observed_session_of_month','timing_classification','capture_started_at_utc','capture_completed_at_utc','writer_started_at_utc','writer_completed_at_utc','conservative_close_utc','conservative_deadline_utc','selected_original_rows','source_row_locations','full_original_sources_preserved','tzif_reference','tzif_bytes_base64','parent_readback_reference','known_typed_rows_preserved','parent_attempt_inventory_preserved','source_hash_claims','payload_is_not_a_published_observation_receipt','seal_status_history_not_created','writer_interval_role'}
    exact(sorted(p),sorted(corekeys|set(metadata)|set(helper.PAYLOAD_FALSE)|set(writerflags)))
    for key in set(helper.PAYLOAD_FALSE)|set(writerflags):require(p[key]is False,'No payload authority')
    known=view['known_typed_rows'];monthfirst=view['first_actual_observed_session_by_month'].get(p['session'][:7],p['session'])
    counts=dict(parent_typed_row_count=len(known),parent_actual_observation_count=sum(row['kind']=='PROSPECTIVE_OBSERVED_SESSION'for row in known),parent_observed_count=sum(row['kind']!='MISSED_OBSERVATION'for row in known),parent_gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in known),new_observation_count=1,month_first_actual_observation=monthfirst==p['session'],timing_classification=r['timing_classification'],clock_authenticity_verified=False,final_durable_completion_time_verified=False,candidate_seal_allowed=False,cohort_registration_allowed=False)
    audited=dict(p['source_hashes'])
    for item in (observation['payload_reference'],observation['receipt_reference'],startref,reader):audited[item['path']]=item['sha256']
    expected=dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3',status='PASS',payload_reference=observation['payload_reference'],receipt_reference=observation['receipt_reference'],parent_history_reference=parent['reference'],input_references=refs,started_current_bytes_reference=startref,started_external_sha_authenticated=False,reader_sha256=reader['sha256'],source_hashes=audited,counts=counts,writer_called=False,payload_core_called=False,shared_upstream_capture_checker_reference=checkerref,attempt_inventory_scope=scope,local_attempt_namespace_inventory=metadata['local_attempt_namespace_inventory'],old_audit_repeated=False,exchange_holidays_verified=False,early_closes_verified=False,final_durable_completion_time_verified=False,**writerflags)
    if not thin:expected.update(writer_adapter_schema=adapter,actual_parent_schema=view['parent_schema'],shared_upstream_parent_checker_reference=refs['dependencies']['parent_view'],local_direct_child_inventory_scope=metadata['local_direct_child_inventory_scope'],external_parent_bound_attempt_inventory=metadata['external_parent_bound_attempt_inventory'],external_unregistered_attempt_discovery_performed=False)
    if latest:expected.update(shared_upstream_capture_checker_called=True,capture_readback_called=False,independent_prefix_checker_reference=metadata['independent_prefix_checker_reference'],producer_prefix_core_called=False,gap_core_called=False)
    exact(a,expected,'Whole original observation audit')


def verify_thin_capture(parent,observation,modules,sources,inventories):
    checker=modules['thinchecker'];refs=observation['payload']['input_references']['capture'];capture=parent_documents(refs,sources)
    d,p,a=(capture[key]for key in ('document','publication','readback'));folder=Path(refs['reference']['path']).parent;af=Path(refs['readback_reference']['path']).parent
    exact(refs['reader_reference'],reference(*AUXILIARIES['legacy_capture_checker_v3']))
    pin_namespace(folder,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'),sources,inventories);pin_namespace(af,('started.json','independent_readback.json'),sources,inventories)
    parents={role:parent[role]for role in ROLES};view=modules['view'].inspect_parent_history_v5(parent)
    producer=reference(checker.PRODUCER,checker.PRODUCER_SHA);pure=reference(checker.PURE,checker.PURE_SHA)
    dependencies={key:reference(ROOT/path,digest)for key,(path,digest)in checker.DEPENDENCIES.items()};inputs=dict(dependencies,pure=pure,tzif=view['tzif_reference'])
    initial={}
    for item in (producer,pure,*dependencies.values(),*parents.values()):consume(item,initial)
    for obj in (parent['document'],parent['publication'],parent['readback']):
        for path,digest in obj['source_hashes'].items():consume(reference(path,digest),initial)
    for item in (*view['accounted_baseline_references'].values(),*view['baseline_references'].values(),view['tzif_reference']):consume(item,initial)
    artifacts=d['captured_artifacts'];exact(sorted(artifacts),['QQQ','SPY','tzif']);expected_sources=dict(initial)
    for key,item in artifacts.items():exact(item['path'],str(folder/('New_York.tzif'if key=='tzif'else key+'.csv')));expected_sources[item['path']]=item['sha256']
    expected=checker.reconstruct_plan(parent=parent,source_bytes={t:consume(artifacts[t],sources)for t in ('QQQ','SPY')},source_references={t:artifacts[t]for t in ('QQQ','SPY')},accounted_baseline_bytes={t:consume(view['accounted_baseline_references'][t],sources)for t in ('QQQ','SPY')},actual_baseline_bytes={t:consume(view['baseline_references'][t],sources)for t in ('QQQ','SPY')},capture_started_at=d['capture_started_at'],capture_completed_at=d['capture_completed_at'],tzif_bytes=consume(artifacts['tzif'],sources),tzif_reference=artifacts['tzif'],csv_rows=modules['csv'].csv_rows)
    exact(artifacts['tzif']['sha256'],view['tzif_reference']['sha256']);flags=dict.fromkeys(checker.FALSE_FIELDS,False)
    exact(sorted(d['current_cache_references']),['QQQ','SPY'])
    for t in ('QQQ','SPY'):exact(d['current_cache_references'][t],reference(ROOT/'data/cache'/f'{t}.csv',artifacts[t]['sha256']))
    exact(d,dict(schema='SOURCE_BOUND_FORWARD_GAP_PARENT_CAPTURE_V3',plan=expected,parent_references=parents,input_references=inputs,captured_artifacts=artifacts,current_cache_references=d['current_cache_references'],current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',capture_started_at=d['capture_started_at'],capture_completed_at=d['capture_completed_at'],clock_captured_by_runner=True,external_clock_attestation_verified=False,quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',source_hashes=expected_sources,**flags))
    exact(p,dict(schema='FORWARD_GAP_PARENT_CAPTURE_PUBLICATION_V3',status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION',capture_reference=refs['reference'],source_hashes=expected_sources,**flags))
    startref=reference(folder/'started.json',sha((folder/'started.json').read_bytes()))
    exact(decode(consume(startref,sources)),dict(schema='FORWARD_GAP_PARENT_CAPTURE_STARTED_V3',parent_references=parents,input_references=inputs,source_hashes=initial,retry_allowed=False,**flags))
    audited=dict(expected_sources)
    for item in (refs['reference'],refs['publication_reference'],refs['reader_reference'],startref,reference(*AUXILIARIES['legacy_csv_reader'])):audited[item['path']]=item['sha256']
    exact(a,dict(schema='FORWARD_GAP_PARENT_CAPTURE_INDEPENDENT_READBACK_V3',status='PURE_FORWARD_GAP_CAPTURE_READBACK_PASS',capture_reference=refs['reference'],publication_reference=refs['publication_reference'],parent_references=parents,input_references=inputs,producer_reference=producer,reader_sha256=refs['reader_reference']['sha256'],source_hashes=audited,
        counts=dict(status=expected['status'],parent_typed_row_count=len(expected['known_typed_rows']),parent_actual_observation_count=len(expected['observations']),parent_gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in expected['known_typed_rows']),candidate_session=expected['candidate_session'],diagnostic_count=len(expected['diagnostics']),snapshot_counts={t:expected['source_evidence'][t]['original_row_count']for t in ('QQQ','SPY')}),
        entire_plan_independently_reconstructed=True,producer_called=False,new_pure_called=False,snapshot_bytes_verified=True,plan_gap_parent_capture_called=False,current_live_cache_read_or_reverified=False,external_clock_attestation_verified=False,started_reference_observed_not_external_anchor=startref,started_externally_authenticated=False,verification_scope='FIXED_PARENT_FOUR_ANCHORS_SAVED_BYTES_AND_INDEPENDENT_PLAN_FORMULA_NOT_SOURCE_OR_CLOCK_AUTHENTICATION',**flags))
    exact(decode(consume(reference(af/'started.json',sha((af/'started.json').read_bytes())),sources)),dict(schema='FORWARD_GAP_PARENT_CAPTURE_READBACK_STARTED_V3',capture_reference=refs['reference'],publication_reference=refs['publication_reference'],reader_sha256=refs['reader_reference']['sha256'],**flags))


def capture_inventory(refs,checker,sources,inventories,modules):
    folder=Path(refs['reference']['path']).parent;audit=Path(refs['readback_reference']['path']).parent
    pin_namespace(folder,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'),sources,inventories)
    pin_namespace(audit,('started.json','independent_readback.json'),sources,inventories)
    envelope=parent_documents(refs,sources);d,p,a=(envelope[key]for key in ('document','publication','readback'));inputs=d['input_references'];plan=d['plan']
    modern=d['schema']=='SOURCE_BOUND_FORWARD_CAPTURE_V5'
    require(modern or d['schema']=='SOURCE_BOUND_FORWARD_CAPTURE_V4','Supported original capture format')
    version='V5'if modern else 'V4';flags=dict.fromkeys(checker.FALSE_FIELDS,False)
    expected_reader=reference(*AUXILIARIES['capture_checker'])if modern else reference(ROOT/'scripts/ndx_registered_forward_capture_independent_readback_20261009_v1.py','b44f2d2cd89f5ea4a64e268e86b409305e7e40673df6565f1d2ba8f9bdeb8cc2')
    exact(refs['reader_reference'],expected_reader)
    dependencies={key:reference(ROOT/path,digest)for key,(path,digest)in checker.DEPENDENCIES.items()}
    producer=reference(checker.PRODUCER,checker.PRODUCER_SHA);regref=reference(*checker.REGISTRATION_CORE)
    expected_keys={'dependencies','registration','runtime','registration_core','reference_core','tzif'}
    if not modern:
        dependencies.pop('legacy_view');dependencies.update(capture_core=reference(ROOT/'backtest/ndx_forward_parent_capture_research_v4.py','56175bb45b25aa899dc0f9fdd07d0eac2cabfd2f0640a177f596582b7b08a951'),parent_view=reference(*AUXILIARIES['legacy_view']))
        producer=reference(ROOT/'scripts/ndx_registered_forward_capture_runtime_20261009_v1.py','e7850782dcc4c230353281935ebc428a7c02349a00cea89731ed16ea27e49190')
        regref=reference(ROOT/'backtest/ndx_forward_capture_runtime_registration_research_v1.py','e04169b111d2788e3dadba657a6c4823d2b0665de17a81e0c84bb9169990abde')
    else:
        expected_keys|={'prefix_core','gap_core'}
        exact(inputs['prefix_core'],reference(*checker.PREFIX_CORE));exact(inputs['gap_core'],reference(*checker.GAP_CORE))
    exact(sorted(inputs),sorted(expected_keys));exact(inputs['runtime'],producer);exact(inputs['registration_core'],regref);exact(inputs['reference_core'],reference(*REGISTRATION_CORE));exact(inputs['dependencies'],dependencies)
    initial={}
    for item in (producer,regref,reference(*REGISTRATION_CORE),inputs['registration'],*dependencies.values()):consume(item,initial)
    if modern:
        for item in (inputs['prefix_core'],inputs['gap_core']):consume(item,initial)
    registration=private(regref['path'],consume(regref,initial),regref['sha256'],[('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',modules['references'])])
    registered=registration.prepare_forward_capture_runtime(registration=decode(consume(inputs['registration'],initial)),registration_reference=inputs['registration'],runtime_reference=producer,dependency_references=dependencies,research_root=str(folder.parent))
    exact(registered['parent'],d['parent_references']);exact(registered['output_directory'],str(folder))
    prior=checker.load_parent_envelope(d['parent_references'],initial);priorview=modules['view'].inspect_parent_history_v5(prior)
    for item in (*priorview['accounted_baseline_references'].values(),*priorview['baseline_references'].values(),priorview['tzif_reference']):consume(item,initial)
    if modern:checker.verify_parent_chain(prior,modules['view'],SimpleNamespace(derive_accounted_prefix=modules['prefix'].reconstruct_accounted_prefix),modules['csv'].csv_rows,initial)
    checker.parent_inventories(d['parent_references'],initial);exact(inputs['tzif'],priorview['tzif_reference'])
    expected_sources=dict(initial)
    for item in d['captured_artifacts'].values():expected_sources[item['path']]=item['sha256']
    exact(d['source_hashes'],expected_sources,'Whole original capture initial source closure')
    startref=reference(folder/'started.json',sha((folder/'started.json').read_bytes()))
    exact(decode(consume(startref,sources)),dict(schema='FORWARD_CAPTURE_STARTED_'+version,parent_references=d['parent_references'],input_references=inputs,source_hashes=initial,retry_allowed=False,**flags))
    audited=dict(d['source_hashes'])
    csvref=reference(*AUXILIARIES['csv_reader'if modern else 'legacy_csv_reader'])
    for item in (expected_reader,csvref,refs['reference'],refs['publication_reference'],startref):audited[item['path']]=item['sha256']
    expected=dict(schema='FORWARD_CAPTURE_INDEPENDENT_READBACK_'+version,status='PURE_FORWARD_CAPTURE_READBACK_PASS',capture_reference=refs['reference'],publication_reference=refs['publication_reference'],parent_references=d['parent_references'],input_references=inputs,
        producer_reference=inputs['runtime'],reader_sha256=expected_reader['sha256'],source_hashes=audited,
        counts=dict(status=plan['status'],parent_typed_row_count=len(plan['known_typed_rows']),parent_actual_observation_count=len(plan['observations']),parent_observed_count=sum(row['kind']!='MISSED_OBSERVATION'for row in plan['known_typed_rows']),parent_gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in plan['known_typed_rows']),candidate_session=plan['candidate_session'],diagnostic_count=len(plan['diagnostics']),snapshot_counts={t:plan['source_evidence'][t]['original_row_count']for t in ('QQQ','SPY')}),
        entire_plan_independently_reconstructed=True,snapshot_bytes_verified=True,producer_called=False,capture_core_called=False,current_live_cache_read_or_reverified=False,external_clock_attestation_verified=False,shared_upstream_parent_checker_reference=inputs['dependencies']['parent_view'],shared_parent_checker_called=True,
        reconstruction_scope='INDEPENDENT_CAPTURE_PLAN_FROM_BOUND_PARENT_SHARED_PARENT_INSPECTOR_NOT_SOURCE_OR_CLOCK_AUTHENTICATION',started_reference_observed_not_external_anchor=startref,started_externally_authenticated=False,**flags)
    if modern:
        prior=checker.load_parent_envelope(d['parent_references'],sources)
        expected.update(csv_reader_reference=csvref,csv_resource_semantics='MAX_8000000_SOURCE_BYTES_MAX_20000_DATA_ROWS_BLANK_RECORDS_EXCLUDED_NO_EXTRA_PHYSICAL_LINE_LIMIT',shared_legacy_parent_checker_reference=inputs['dependencies']['legacy_view'],prefix_core_called_for_parent_evidence_only=prior['document']['history']['schema']=='PROSPECTIVE_GAP_EXTENSION_HISTORY_V5',gap_core_called=False,parent_chain_and_original_prefix_bytes_reverified=True,actual_parent_schema=prior['document']['history']['schema'])
    exact(a,expected,'Whole original capture audit')
    exact(decode(consume(reference(audit/'started.json',sha((audit/'started.json').read_bytes())),sources)),dict(schema='FORWARD_CAPTURE_READBACK_STARTED_'+version,capture_reference=refs['reference'],publication_reference=refs['publication_reference'],registration_reference=inputs['registration'],reader_sha256=expected_reader['sha256'],**flags))


def parent_inventory(refs,checker,sources,inventories):
    checker.parent_inventories(refs,sources)
    folder=Path(refs['reference']['path']).parent;audit=Path(refs['readback_reference']['path']).parent
    for directory in {folder,audit}:
        pin_namespace(directory,tuple(path.name for path in directory.iterdir()),sources,inventories)


def compact_metadata(parent_schema,auxiliary):
    return dict(compact_adapter_schema=ADAPTER,actual_parent_schema=parent_schema,
        parent_graph_verification_scope=GRAPH_SCOPE,shared_upstream_capture_checker_reference=auxiliary['capture_checker'],
        shared_upstream_capture_checker_called=True,capture_readback_called=False,
        shared_observation_reader_reference=auxiliary['observation_reader'],observation_readback_called=False,
        independent_prefix_checker_reference=auxiliary['independent_prefix'],producer_prefix_core_called=False)


def verify_actual_outer(parent,prior,history,modules,sources,auxiliary):
    core=modules['core']
    d,p,a=(parent[key]for key in ('document','publication','readback'));inputs=d['input_references']
    exact(inputs['parent'],{role:prior[role]for role in ROLES});exact(inputs['observation'],history['observation_references'])
    exact(p['input_references'],inputs);exact(a['input_references'],inputs)
    exact(p['source_hashes'],d['source_hashes'])
    folder=Path(parent['reference']['path']).parent;start=decode(consume(reference(folder/'started.json',sha((folder/'started.json').read_bytes())),sources))
    if inputs['runtime']==reference(*AUXILIARIES['legacy_compact_publisher']):
        exact(inputs['dependencies'],dict(history_core=reference(*AUXILIARIES['legacy_view']),compact_helpers=reference(*DEPENDENCIES['compact_helpers'])))
        exact(inputs['registration_core'],reference(*REGISTRATION_CORE))
        registered=modules['references'].prepare_compact_history_runtime(registration=decode(consume(inputs['registration'],sources)),registration_reference=inputs['registration'],runtime_reference=inputs['runtime'],dependency_references=inputs['dependencies'],research_root=str(folder.parent))
        exact(registered['parent'],inputs['parent']);exact(registered['observation'],inputs['observation']);exact(registered['output_directory'],str(folder))
        meta={};exact(sorted(inputs),sorted({'parent','observation','registration','runtime','dependencies','registration_core'}))
        exact(start,dict(schema='PROSPECTIVE_OBSERVATION_HISTORY_STARTED_V4',input_references=inputs,source_hashes=d['source_hashes'],**FLAGS))
    else:
        exact(inputs['runtime'],reference(SOURCE,LOADED_SHA));exact(inputs['auxiliary_dependencies'],auxiliary)
        meta=compact_metadata(modules_parent_schema(prior),auxiliary)
        expected_sources=dict(d['source_hashes']);expected_sources.pop(str(folder/'started.json'),None)
        exact(start,dict(schema='PROSPECTIVE_OBSERVATION_HISTORY_STARTED_V4',input_references=inputs,source_hashes=expected_sources,**meta,**FLAGS))
    exact(d,dict(schema=core.WRAPPER_SCHEMA,history=history,input_references=inputs,source_hashes=d['source_hashes'],**meta,**FLAGS))
    exact(p,dict(schema=core.PUBLICATION_SCHEMA,status=core.PUBLICATION_STATUS,history_reference=parent['reference'],input_references=inputs,
        counts=core.history_counts_v4(history),source_hashes=d['source_hashes'],**meta,**FLAGS))
    audited=dict(d['source_hashes'])
    for item in (parent['reference'],parent['publication_reference'],parent['reader_reference'],reference(folder/'started.json',sha((folder/'started.json').read_bytes()))):audited[item['path']]=item['sha256']
    if not meta:
        exact(parent['reader_reference'],reference(*AUXILIARIES['legacy_compact_reader']))
        audited[str(AUXILIARIES['legacy_csv_reader'][0])]=AUXILIARIES['legacy_csv_reader'][1]
        expected=dict(schema=core.READBACK_SCHEMA,status=core.READBACK_STATUS,history_reference=parent['reference'],publication_reference=parent['publication_reference'],
            input_references=inputs,reader_sha256=parent['reader_reference']['sha256'],source_hashes=audited,counts=core.history_counts_v4(history),
            entire_history_independently_reconstructed=True,publisher_called=False,new_pure_called=False,current_live_cache_read_or_reverified=False,
            shared_upstream_parent_checker_reference=inputs['dependencies']['history_core'],shared_parent_checker_called=True,append_algorithm_called=False,
            reconstruction_scope='CURRENT_V4_RESULT_FROM_BOUND_PARENT_AND_INDEPENDENT_APPEND_FORMULA_SHARED_PARENT_CHECKER',
            started_reference_observed_not_external_anchor=reference(folder/'started.json',sha((folder/'started.json').read_bytes())),started_externally_authenticated=False,**FLAGS)
        exact(a,expected)
    else:
        raise ValueError('Future compact V2 independent reader role is not yet bound')
    auditfolder=Path(parent['readback_reference']['path']).parent
    auditstart=decode(consume(reference(auditfolder/'started.json',sha((auditfolder/'started.json').read_bytes())),sources))
    exact(auditstart,dict(schema='PROSPECTIVE_OBSERVATION_HISTORY_READBACK_STARTED_V4',history_reference=parent['reference'],publication_reference=parent['publication_reference'],
        registration_reference=inputs['registration'],reader_sha256=parent['reader_reference']['sha256'],**FLAGS))


def modules_parent_schema(parent):return parent['document']['history']['schema']


def walk_parent_graph(parent,modules,sources,auxiliary):
    """One global visited/depth bound spans actual-V4 and gap-V5 original edges."""
    checker=modules['checker'];inventories=[];visited=set();current=parent
    while True:
        key=(current['reference']['path'],current['reference']['sha256'])
        require(key not in visited and len(visited)<MAX_PARENT_DEPTH,'Global parent cycle/depth')
        view=modules['view'].inspect_parent_history_v5(current);schema=view['parent_schema']
        if schema==modules['view'].GAP_SCHEMA:
            # The fixed checker may traverse a contiguous gap segment; register every returned node globally.
            segment=checker.verify_parent_chain(current,modules['view'],SimpleNamespace(derive_accounted_prefix=modules['prefix'].reconstruct_accounted_prefix),modules['csv'].csv_rows,sources)
            terminal=None
            for kind,refs in segment:
                if kind=='capture':capture_inventory(refs,checker,sources,inventories,modules);continue
                item=(refs['reference']['path'],refs['reference']['sha256'])
                require(item not in visited and len(visited)<MAX_PARENT_DEPTH,'Global gap/actual cycle/depth')
                visited.add(item);parent_inventory(refs,checker,sources,inventories);terminal=checker.load_parent_envelope(refs,sources)
            require(terminal is not None,'Gap segment terminal')
            # Original wrappers/START metadata are also checked for every gap node, not just h.
            for kind,bound in segment:
                if kind=='parent':
                    original=checker.load_parent_envelope(bound,sources)
                    if original['document']['history']['schema']==modules['view'].GAP_SCHEMA:verify_gap_outer(original,modules,sources)
            current=terminal
            # Terminal V4 was registered by the gap checker; process its outgoing actual edge below.
            view=modules['view'].inspect_parent_history_v5(current);schema=view['parent_schema']
        else:
            visited.add(key);parent_inventory({role:current[role]for role in ROLES},checker,sources,inventories)
        verify_baselines(view,sources)
        for entry in view['observations']:
            pin_namespace(Path(entry['payload_reference']['path']).parent,('started.json','observation_payload.json','receipt.json','independent_readback.json'),sources,inventories)
        if schema=='PROSPECTIVE_GAP_EXTENSION_HISTORY_V3':return inventories,len(visited)
        require(schema==modules['core'].SCHEMA,'Known actual or gap parent edge')
        h=current['document']['history'];prior=checker.load_parent_envelope(h['parent_references'],sources)
        require((prior['reference']['path'],prior['reference']['sha256'])not in visited,'Actual parent cycle')
        observation=observation_documents(h['observation_references'],sources)
        observation_originals(prior,observation,modules,sources,inventories)
        replay=modules['core'].append_observation_history(parent=prior,observation=observation)
        exact(h,replay,'Whole actual child replay from TRUE original prior and observation')
        verify_actual_outer(current,prior,h,modules,sources,auxiliary)
        current=prior


def verify_gap_outer(parent,modules,sources):
    d,p,a=(parent[key]for key in ('document','publication','readback'));h=d['history'];inputs=d['input_references']
    checker=modules['checker'];legacy=modules['legacy'];folder=Path(parent['reference']['path']).parent
    startref=reference(folder/'started.json',sha((folder/'started.json').read_bytes()));start=decode(consume(startref,sources))
    exact(inputs['parent'],h['parent_references']);exact(inputs['capture'],h['capture_references'])
    exact(p['input_references'],inputs);exact(a['input_references'],inputs);exact(p['source_hashes'],d['source_hashes'])
    exact(parent['reader_reference'],reference(*AUXILIARIES['gap_reader']))
    exact(inputs['runtime'],reference(*AUXILIARIES['gap_publisher']));exact(inputs['registration_core'],reference(*AUXILIARIES['gap_registration']))
    exact(inputs['reference_core'],reference(*REGISTRATION_CORE));exact(inputs['csv_reader'],reference(*AUXILIARIES['csv_reader']))
    expected_deps={key:reference(ROOT/path,digest)for key,(path,digest)in checker.DEPENDENCIES.items()if key not in ('capture_core',)}
    expected_deps.update(gap_core=reference(*checker.GAP_CORE),prefix_core=reference(*checker.PREFIX_CORE),capture_checker=reference(*AUXILIARIES['capture_checker']))
    exact(inputs['dependencies'],expected_deps)
    exact(sorted(inputs),sorted({'parent','capture','registration','runtime','dependencies','registration_core','reference_core','csv_reader'}))
    initial={}
    for item in (inputs['runtime'],inputs['registration_core'],inputs['reference_core'],inputs['registration'],*expected_deps.values(),inputs['csv_reader']):consume(item,initial)
    registration=decode(consume(inputs['registration'],initial))
    plan=modules['gap_registration'].prepare_gap_runtime(registration=registration,registration_reference=inputs['registration'],runtime_reference=inputs['runtime'],dependency_references=expected_deps,research_root=str(folder.parent))
    exact(plan['parent'],h['parent_references']);exact(plan['capture'],h['capture_references']);exact(plan['output_directory'],str(folder))
    prior=checker.load_parent_envelope(h['parent_references'],initial)
    checker.verify_parent_chain(prior,modules['view'],SimpleNamespace(derive_accounted_prefix=modules['prefix'].reconstruct_accounted_prefix),modules['csv'].csv_rows,initial)
    checker.verify_prior_capture(h,prior,modules['view'],modules['csv'].csv_rows,initial)
    previous=modules['view'].inspect_parent_history_v5(prior)
    for item in (*h['full_capture_source_references'].values(),*previous['accounted_baseline_references'].values(),*previous['baseline_references'].values(),h['tzif_reference']):consume(item,initial)
    gapflags=dict.fromkeys(('source_authenticity_verified','parent_history_authenticated_by_this_module','clock_authenticity_verified','timeliness_verified',
        'filesystem_attempt_inventory_authenticated','observation_created','candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed',
        'live_mutation_allowed','future_independent_oos','production_generator_authorized','old_calendar_mutated','network_quote_refresh_performed','full_transitive_source_closure_reverified',
        'network_capture_performed','seal_event_created','partial_recovery_performed','canonical_calendar_append_allowed','retrospective_backfill_allowed','decision_eligible','exchange_holidays_and_early_closes_verified'),False)
    exact(start,dict(schema='PROSPECTIVE_GAP_HISTORY_STARTED_V5',input_references=inputs,source_hashes=initial,retry_allowed=False,
        shared_upstream_capture_checker_reference=expected_deps['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,current_live_cache_read_or_reverified=False,**gapflags))
    published=dict(initial)
    for item in (startref,*h['accounted_prefix_references'].values(),*h['accounted_prefix_evidence_references'].values()):published[item['path']]=item['sha256']
    exact(d,dict(schema=modules['view'].WRAPPER_SCHEMA,history=h,input_references=inputs,source_hashes=published,
        shared_upstream_capture_checker_reference=expected_deps['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,current_live_cache_read_or_reverified=False,**gapflags))
    exact(p,dict(schema=modules['view'].PUBLICATION_SCHEMA,status=modules['view'].PUBLICATION_STATUS,history_reference=parent['reference'],input_references=inputs,source_hashes=published,**gapflags))
    # Exact supported registered audit shape; fixed source references are independently hash-guarded.
    audited=dict(published)
    for field in ('independent_gap_reconstructor_reference','independent_prefix_reconstructor_reference','csv_reader_reference'):
        item=a[field];consume(item,sources);audited[item['path']]=item['sha256']
    exact(a['independent_prefix_reconstructor_reference'],reference(*AUXILIARIES['independent_prefix']));exact(a['csv_reader_reference'],reference(*AUXILIARIES['csv_reader']))
    exact(a['independent_gap_reconstructor_reference'],reference(ROOT/'backtest/ndx_gap_history_independent_reconstruction_research_v1.py','7c05552f8015af34b7eb2a215929258b0e83edc4b7ed9edaba494e45dfea8cd3'))
    for item in (parent['reference'],parent['publication_reference'],parent['reader_reference']):audited[item['path']]=item['sha256']
    exact(a,dict(schema=modules['view'].READBACK_SCHEMA,status=modules['view'].READBACK_STATUS,history_reference=parent['reference'],publication_reference=parent['publication_reference'],reader_sha256=parent['reader_reference']['sha256'],
        input_references=inputs,source_hashes=audited,counts=modules['view'].gap_counts(h),entire_history_independently_reconstructed=True,publisher_called=False,new_pure_called=False,
        producer_prefix_core_called=False,producer_scoped_parser_called=False,current_live_cache_read_or_reverified=False,snapshot_bytes_verified=True,
        independent_gap_reconstructor_reference=a['independent_gap_reconstructor_reference'],independent_prefix_reconstructor_reference=a['independent_prefix_reconstructor_reference'],csv_reader_reference=a['csv_reader_reference'],
        shared_upstream_capture_checker_reference=expected_deps['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,publisher_started_reference_observed_not_external_anchor=startref,
        publisher_started_externally_authenticated=False,reconstruction_scope='INDEPENDENT_ENTIRE_GAP_RESULT_AND_PREFIX_BYTES_SHARED_UPSTREAM_CAPTURE_CHECKER_NO_SOURCE_OR_CLOCK_AUTHENTICATION',**gapflags))
    auditfolder=Path(parent['readback_reference']['path']).parent
    auditstart=decode(consume(reference(auditfolder/'started.json',sha((auditfolder/'started.json').read_bytes())),sources))
    exact(auditstart,dict(schema='PROSPECTIVE_GAP_HISTORY_READBACK_STARTED_V5',history_reference=parent['reference'],publication_reference=parent['publication_reference'],
        registration_reference=inputs['registration'],reader_sha256=parent['reader_reference']['sha256'],**gapflags))


def load_modules(dependencies,auxiliary,sources):
    raw={key:consume(item,sources)for key,item in dependencies.items()};auxraw={key:consume(item,sources)for key,item in auxiliary.items()}
    helper=private(dependencies['compact_helpers']['path'],raw['compact_helpers'],dependencies['compact_helpers']['sha256'])
    legacy=private(auxiliary['legacy_view']['path'],auxraw['legacy_view'],auxiliary['legacy_view']['sha256'],[
        ('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',helper)])
    view=private(auxiliary['parent_view']['path'],auxraw['parent_view'],auxiliary['parent_view']['sha256'],[
        ('from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy','legacy',legacy)])
    core=private(dependencies['history_core']['path'],raw['history_core'],dependencies['history_core']['sha256'],[
        ('from backtest import ndx_prospective_history_parent_view_research_v5 as parent_view','parent_view',view),
        ('from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy','legacy',legacy)])
    exact(core.ADAPTER_DEPENDENCY_SHA256,dict(parent_view=auxiliary['parent_view']['sha256'],legacy_view=auxiliary['legacy_view']['sha256'],compact_helpers=dependencies['compact_helpers']['sha256']))
    checker=private(auxiliary['capture_checker']['path'],auxraw['capture_checker'],auxiliary['capture_checker']['sha256']);checker.CURRENT=CURRENT
    thinchecker=private(auxiliary['legacy_capture_checker_v3']['path'],auxraw['legacy_capture_checker_v3'],auxiliary['legacy_capture_checker_v3']['sha256'])
    observer=private(auxiliary['observation_reader']['path'],auxraw['observation_reader'],auxiliary['observation_reader']['sha256'])
    prefix=private(auxiliary['independent_prefix']['path'],auxraw['independent_prefix'],auxiliary['independent_prefix']['sha256'])
    csvreader=private(auxiliary['csv_reader']['path'],auxraw['csv_reader'],auxiliary['csv_reader']['sha256'])
    references=private(str(REGISTRATION_CORE[0]),consume(reference(*REGISTRATION_CORE),sources),REGISTRATION_CORE[1])
    gapreg=private(auxiliary['gap_registration']['path'],auxraw['gap_registration'],auxiliary['gap_registration']['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',references)])
    return dict(core=core,view=view,legacy=legacy,checker=checker,observer=observer,prefix=prefix,csv=csvreader,gap_registration=gapreg,references=references,thinchecker=thinchecker)


def current_attempt_inventory(parent,observation,sources,inventories):
    """Only local direct children plus explicit inherited external attempt dirs."""
    entries=parent['document']['history']['observations']
    allowed={entry['payload_reference']['path']:dict(payload_reference=entry['payload_reference'],receipt_reference=entry['receipt_reference'],audit_reference=entry['audit_reference'])for entry in entries}
    allowed[observation['payload_reference']['path']]={key:observation[key]for key in ('payload_reference','receipt_reference','audit_reference')}
    local=list(safe(RESEARCH).iterdir());require(len(local)<=20000,'Bounded local semantic inventory')
    external={Path(path).parent for path in allowed if Path(path).parent.parent!=RESEARCH}
    found={}
    for folder in [*local,*sorted(external,key=str)]:
        folder=safe(folder)
        if not folder.is_dir():continue
        records={}
        for name in ('started.json','observation_payload.json','receipt.json','failure.json'):
            path=safe(folder/name)
            if not path.exists():continue
            require(path.is_file()and path.stat().st_size<=64*1024**2,'Bounded semantic attempt file')
            raw=path.read_bytes();records[name]=(decode(raw),reference(path,sha(raw)))
        get=lambda name:records.get(name,({},{}))[0]
        semantic=(get('started.json').get('schema','').startswith('PROSPECTIVE_OBSERVATION_WRITER_STARTED_')or get('observation_payload.json').get('schema')=='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1'or get('receipt.json').get('schema')=='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1'or get('failure.json').get('status')=='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY')
        if not semantic:require(folder not in external,'Explicit inherited attempt recognizable');continue
        require(set(records)=={'started.json','observation_payload.json','receipt.json'},'No partial or failed semantic attempt')
        payload=records['observation_payload.json'][1];require(payload['path']in allowed and payload['path']not in found,'Unregistered or duplicate semantic observation')
        expected=allowed[payload['path']];exact(payload,expected['payload_reference']);exact(records['receipt.json'][1],expected['receipt_reference'])
        pin_namespace(folder,('started.json','observation_payload.json','receipt.json','independent_readback.json'),sources,inventories)
        audit=decode(consume(expected['audit_reference'],sources));start=records['started.json'][1]
        exact(audit['source_hashes'].get(start['path']),start['sha256'],'Whole semantic attempt START')
        found[payload['path']]={name:item for name,(_,item)in records.items()}
    exact(sorted(found),sorted(allowed),'All current bound actual attempts');return found


def run(*,registration_path,registration_sha256,execute=False):
    require(type(execute)is bool,'Explicit bool')
    if not execute:return dict(status='NOT_EXECUTED')
    regref=reference(*REGISTRATION_CORE);registration_ref=reference(registration_path,registration_sha256)
    dependencies={key:reference(*value)for key,value in DEPENDENCIES.items()}
    auxiliary={key:reference(*value)for key,value in AUXILIARIES.items()};runtime_ref=reference(SOURCE,LOADED_SHA)
    sources={};consume(runtime_ref,sources)
    reg=private(regref['path'],consume(regref,sources),regref['sha256'])
    plan=reg.prepare_compact_history_runtime(registration=decode(consume(registration_ref,sources)),registration_reference=registration_ref,
        runtime_reference=runtime_ref,dependency_references=dependencies,research_root=str(RESEARCH))
    output=safe(plan['output_directory']);require(not output.exists(),'Create-only; no retry')
    modules=load_modules(dependencies,auxiliary,sources)
    parent=parent_documents(plan['parent'],sources)
    inventories,node_count=walk_parent_graph(parent,modules,sources,auxiliary)
    observation=observation_documents(plan['observation'],sources)
    observation_originals(parent,observation,modules,sources,inventories,current=True)
    current_inventory=current_attempt_inventory(parent,observation,sources,inventories)
    history=modules['core'].append_observation_history(parent=parent,observation=observation)
    for path,digest in history['source_hashes'].items():consume(reference(path,digest),sources)
    def final_guard():
        exact(current_attempt_inventory(parent,observation,{},[]),current_inventory,'Current local semantic attempt drift')
        for folder,names in inventories:namespace(Path(folder),names,{})
        guard(sources)
    final_guard();require(shutil.disk_usage(output.anchor).free>=5*1024**3,'Resource stop before namespace')
    output.mkdir(parents=True,exist_ok=False)
    inputs=dict(parent=deepcopy(plan['parent']),observation=deepcopy(plan['observation']),registration=registration_ref,runtime=runtime_ref,
        dependencies=dependencies,auxiliary_dependencies=auxiliary,registration_core=regref)
    metadata=compact_metadata(modules_parent_schema(parent),auxiliary)
    try:
        started=save(output/'started.json',dict(schema='PROSPECTIVE_OBSERVATION_HISTORY_STARTED_V4',input_references=inputs,source_hashes=deepcopy(sources),**metadata,**FLAGS))
        sources[started['path']]=started['sha256']
        history_ref=save(output/'history.json',dict(schema=modules['core'].WRAPPER_SCHEMA,history=history,input_references=inputs,source_hashes=deepcopy(sources),**metadata,**FLAGS))
        final_guard()
        publication=save(output/'publication.json',dict(schema=modules['core'].PUBLICATION_SCHEMA,status=modules['core'].PUBLICATION_STATUS,history_reference=history_ref,
            input_references=inputs,counts=modules['core'].history_counts_v4(history),source_hashes=deepcopy(sources),**metadata,**FLAGS))
        final_guard()
        for item in (started,history_ref,publication):consume(item,{})
        namespace(output,('started.json','history.json','publication.json'),{})
        return dict(history_reference=history_ref,publication_reference=publication,independent_readback_required=True,**FLAGS)
    except BaseException as error:
        save(output/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,automatic_retry_allowed=False,**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--registration-path',required=True);parser.add_argument('--registration-sha256',required=True);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();print(json.dumps(run(registration_path=args.registration_path,registration_sha256=args.registration_sha256,execute=args.execute)))
