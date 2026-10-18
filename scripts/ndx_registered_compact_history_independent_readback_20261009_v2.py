"""Independent whole-ancestry compact readback with host-selected implementation pair.

Metadata validators share the published contract. Actual and gap arithmetic are
reconstructed by independently pinned kernels; publisher algorithms are never executed.
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

PAIR_BINDING_CORE=(ROOT/'backtest/ndx_compact_implementation_pair_binding_research_v1.py','dde8b681612d2b4fc0993bb9b697dcefb0222036d3e1bb6f4aa5f2dd76d7e4ad')
ANCESTRY_CONTRACT=(ROOT/'backtest/ndx_compact_ancestry_contract_research_v2.py','081ba024fa997c37c1f030fcec7d4d22ca6411eec652d15a5049b57d62a31a76')
LEGACY_ANCESTRY=(ROOT/'backtest/ndx_compact_ancestry_contract_research_v1.py','1f50f4d5a893c163149bf69593880f73a1387293ee04b2ab9c0fcbb58090fc5e')
CONSUMER_ROLE_CORE=(ROOT/'backtest/ndx_continuation_consumer_role_registry_research_v1.py','184479c5e0e6412265e00cc875af1f7902e4f500dc984ca2aaaf3251bc8c433b')
CONSUMER_METADATA_CORE=(ROOT/'backtest/ndx_continuation_consumer_metadata_research_v1.py','b0d16b1b364d2c32e55d826c1f9d63dfffeb27df7bcabfe972efd029e8e2fdeb')
READER_ALGORITHMS={
 'history_reconstructor':(ROOT/'backtest/ndx_compact_actual_independent_reconstruction_research_v1.py','65a09eaf32118b7958ec7ebcd7fb71880c5a8f2ca437b247ee79bc869eb0f5a0'),
 'legacy_history_reconstructor':AUXILIARIES['legacy_compact_reader'],
 'independent_gap_reconstructor':(ROOT/'backtest/ndx_gap_history_independent_reconstruction_research_v1.py','7c05552f8015af34b7eb2a215929258b0e83edc4b7ed9edaba494e45dfea8cd3'),
 **{key:AUXILIARIES[key] for key in ('parent_view','legacy_view','capture_checker','observation_reader','csv_reader','independent_prefix')},
 'compact_helpers':DEPENDENCIES['compact_helpers']}
TERMINAL_REFERENCE=(ROOT/'data/cache/research/prospective_gap_history_20261009_v3/history.json','600d15deb7cdcbc74fb13337c279d31c910d9389088ebc8668ea650779fdfd8a')
TERMINAL_PURE=(ROOT/'backtest/ndx_prospective_gap_history_research_v3.py','12690e619763ff32ff601d0d0f4071f41d7ecf5e921d19601c58ab5802ed5c63')
TERMINAL_READER=(ROOT/'scripts/ndx_prospective_gap_history_independent_readback_20261009_v3.py','2be765c5dafcb85366e4e84d3a8cbed2037a6924649695f3ab176764075791f8')

CURRENT={ticker:ROOT/'data/cache'/(ticker+'.csv')for ticker in ('QQQ','SPY')}
ADAPTER='HOST_PAIR_BOUND_REGISTERED_COMPACT_ACTUAL_RUNTIME_V3'
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
        require(type(result[key]['source_hashes'])is dict,'Complete source claim map; not an IO queue')
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


def observation_namespace_files(observation,modules):
    p,r,a=(observation[key]for key in ('payload','receipt','audit'))
    if continuation_header(p,r,a):
        for value,role in ((p,'observation_writer'),(r,'observation_writer'),(a,'observation_independent_reader')):
            continuation_metadata(value,role,modules)
        exact(observation['reader_reference'],modules['consumer_registry']['consumer_references']['observation_independent_reader'])
        exact(a['reader_input_references'],reader_private_inputs('observation_independent_reader',modules))
        return ('started.json','observation_payload.json','receipt.json','reader_started.json','independent_readback.json')
    return ('started.json','observation_payload.json','receipt.json','independent_readback.json')


def observation_originals(parent,observation,modules,sources,inventories,*,current=False):
    """Replay saved original evidence only; never run a writer or readback entry."""
    p,r,a=(observation[key]for key in ('payload','receipt','audit'))
    if continuation_header(p,r,a):return verify_continuation_observation(parent,observation,modules,sources,inventories,current=current)
    reader=observation['reader_reference'];allowed=[reference(*AUXILIARIES[key])for key in ('observation_reader','legacy_observer_v3','legacy_observer_v4')]
    require(reader in allowed,'Explicit supported original observation-reader role')
    consume(reader,sources)
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
        capture_inventory(refs['capture'],modules['checker'],sources,inventories,modules)
        modules['checker'].verify_prior_capture(bridge,parent,modules['view'],modules['csv'].csv_rows,sources)
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
            capture_inventory(p['input_references']['capture'],modules['checker'],sources,inventories,modules)
            modules['checker'].verify_prior_capture(bridge,parent,modules['view'],modules['csv'].csv_rows,sources)
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


def bound_attempt_inventory(view,research,thin=False,modules=None):
    found={}
    for entry in view['observations']:
        payload=entry['payload_reference'];folder=Path(payload['path']).parent
        if thin and folder.parent!=ROOT/'data/cache/research':continue
        receipt=entry['receipt_reference'];auditref=entry['audit_reference']
        require(receipt['path']==str(folder/'receipt.json')and auditref['path']==str(folder/'independent_readback.json'),'Bounded inherited namespace')
        local={};audit=decode(consume(auditref,local))
        names=('started.json','observation_payload.json','receipt.json','independent_readback.json')
        if continuation_header(audit):
            require(modules is not None,'Host context for inherited continuation attempt')
            original=observation_documents({role:entry[role]for role in OBSERVATION_ROLES},local)
            names=observation_namespace_files(original,modules)
        namespace(folder,names,local)
        start=reference(folder/'started.json',local[str(folder/'started.json')])
        exact(audit['source_hashes'].get(start['path']),start['sha256'],'Parent-bound observed START')
        exact(reference(folder/'observation_payload.json',local[str(folder/'observation_payload.json')]),payload)
        exact(reference(folder/'receipt.json',local[str(folder/'receipt.json')]),receipt)
        found[payload['path']]={'started.json':start,'observation_payload.json':payload,'receipt.json':receipt}
        if 'reader_started.json'in names:
            own=reference(folder/'reader_started.json',local[str(folder/'reader_started.json')]);exact(audit['source_hashes'].get(own['path']),own['sha256'])
            found[payload['path']]['reader_started.json']=own
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
    inventory=bound_attempt_inventory(view,Path(observation['payload_reference']['path']).parent.parent,thin,modules)
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
    original=parent_documents(refs,sources)
    if continuation_header(*(original[key]for key in ('document','publication','readback'))):
        return verify_continuation_capture(refs,original,modules,sources,inventories)
    folder=Path(refs['reference']['path']).parent;audit=Path(refs['readback_reference']['path']).parent
    pin_namespace(folder,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'),sources,inventories)
    pin_namespace(audit,('started.json','independent_readback.json'),sources,inventories)
    envelope=parent_documents(refs,sources);d,p,a=(envelope[key]for key in ('document','publication','readback'));inputs=d['input_references'];plan=d['plan']
    modern=d['schema']=='SOURCE_BOUND_FORWARD_CAPTURE_V5'
    require(modern or d['schema']=='SOURCE_BOUND_FORWARD_CAPTURE_V4','Supported original capture format')
    version='V5'if modern else 'V4';flags=dict.fromkeys(checker.FALSE_FIELDS,False)
    expected_reader=reference(*AUXILIARIES['capture_checker'])if modern else reference(ROOT/'scripts/ndx_registered_forward_capture_independent_readback_20261009_v1.py','b44f2d2cd89f5ea4a64e268e86b409305e7e40673df6565f1d2ba8f9bdeb8cc2')
    exact(refs['reader_reference'],expected_reader)
    consume(expected_reader,sources)
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
    for path,digest in initial.items():consume(reference(path,digest),sources)


def parent_inventory(refs,checker,sources,inventories):
    checker.parent_inventories(refs,sources)
    folder=Path(refs['reference']['path']).parent;audit=Path(refs['readback_reference']['path']).parent
    for directory in {folder,audit}:
        pin_namespace(directory,tuple(path.name for path in directory.iterdir()),sources,inventories)


def compact_metadata(parent_schema,auxiliary,*,pair=None,consumer=None):
    metadata=dict(compact_adapter_schema=ADAPTER,actual_parent_schema=parent_schema,
        parent_graph_verification_scope=GRAPH_SCOPE,shared_upstream_capture_checker_reference=auxiliary['capture_checker'],
        shared_upstream_capture_checker_called=True,capture_readback_called=False,
        shared_observation_reader_reference=auxiliary['observation_reader'],observation_readback_called=False,
        independent_prefix_checker_reference=auxiliary['independent_prefix'],producer_prefix_core_called=False)
    require(pair is not None,'Explicit host-bound implementation pair')
    metadata.update(implementation_pair_binding_reference=pair['binding_reference'],
        ancestry_contract_reference=pair['contract_reference'],
        implementation_pair_reader_reference=pair['independent_reader_reference'],
        shared_ancestry_contract_called=True,shared_ancestry_contract_scope='EDGE_ASSOCIATIONS_ONLY',
        peer_algorithm_called=False,implementation_pair_approval_authenticated=False)
    if consumer is not None:
        metadata.update(consumer_role_registry_reference=consumer['registry_reference'],
            consumer_registry_core_reference=reference(*CONSUMER_ROLE_CORE),consumer_metadata_contract_reference=reference(*CONSUMER_METADATA_CORE))
    return metadata


def verify_actual_outer(parent,prior,history,modules,sources,auxiliary):
    core=modules['core'];pair=modules['bound_pair']
    d,p,a=(parent[key]for key in ('document','publication','readback'));inputs=d['input_references']
    exact(inputs['parent'],{role:prior[role]for role in ROLES});exact(inputs['observation'],history['observation_references'])
    exact(p['input_references'],inputs);exact(a['input_references'],inputs)
    exact(p['source_hashes'],d['source_hashes'])
    folder=Path(parent['reference']['path']).parent
    startref=reference(folder/'started.json',sha((folder/'started.json').read_bytes()))
    start=decode(consume(startref,sources))
    legacy=inputs['runtime']==reference(*AUXILIARIES['legacy_compact_publisher'])
    if legacy:
        deps=dict(history_core=reference(*AUXILIARIES['legacy_view']),compact_helpers=reference(*DEPENDENCIES['compact_helpers']))
        exact(inputs['dependencies'],deps);exact(inputs['registration_core'],reference(*REGISTRATION_CORE))
        exact(sorted(inputs),sorted({'parent','observation','registration','runtime','dependencies','registration_core'}))
        meta={};initial=d['source_hashes']
    else:
        exact(parent['reader_reference'],pair['independent_reader_reference'],'Host pair reader, never artifact-selected')
        exact(inputs,pair_inputs(parent=history['parent_references'],observation=history['observation_references'],
            registration=inputs['registration'],runtime=pair['publisher_reference'],dependencies=pair['algorithm_dependency_references']['publisher'],
            auxiliary=auxiliary,registration_core=reference(*REGISTRATION_CORE),pair=pair,consumer=modules.get('consumer_registry')))
        deps=inputs['registration_dependency_references']
        meta=compact_metadata(modules_parent_schema(prior),auxiliary,pair=pair,consumer=modules.get('consumer_registry'))
        cache=modules.setdefault('pair_initial_source_cache',{})
        identity=(parent['reference']['path'],parent['reference']['sha256'])
        if identity not in cache:
            observed=observation_documents(history['observation_references'],sources)
            cache[identity]=derive_pair_initial_sources(prior,observed,inputs['registration'],modules,auxiliary)
        initial=deepcopy(cache[identity])
        expected_published=dict(initial);expected_published[startref['path']]=startref['sha256']
        exact(d['source_hashes'],expected_published,'Whole host-derived pair publisher source closure')
    registered=modules['references'].prepare_compact_history_runtime(registration=decode(consume(inputs['registration'],sources)),
        registration_reference=inputs['registration'],runtime_reference=inputs['runtime'],dependency_references=deps,research_root=str(folder.parent))
    exact(registered['parent'],inputs['parent']);exact(registered['observation'],inputs['observation']);exact(registered['output_directory'],str(folder))
    exact(start,dict(schema='PROSPECTIVE_OBSERVATION_HISTORY_STARTED_V4',input_references=inputs,source_hashes=initial,**meta,**FLAGS))
    exact(d,dict(schema=core.WRAPPER_SCHEMA,history=history,input_references=inputs,source_hashes=d['source_hashes'],**meta,**FLAGS))
    exact(p,dict(schema=core.PUBLICATION_SCHEMA,status=core.PUBLICATION_STATUS,history_reference=parent['reference'],input_references=inputs,
        counts=core.history_counts_v4(history),source_hashes=d['source_hashes'],**meta,**FLAGS))
    audited=dict(d['source_hashes'])
    for item in (parent['reference'],parent['publication_reference'],parent['reader_reference'],startref):audited[item['path']]=item['sha256']
    if legacy:
        exact(parent['reader_reference'],reference(*AUXILIARIES['legacy_compact_reader']))
        audited[str(AUXILIARIES['legacy_csv_reader'][0])]=AUXILIARIES['legacy_csv_reader'][1]
        reader_meta=dict(shared_upstream_parent_checker_reference=deps['history_core'],shared_parent_checker_called=True,
            append_algorithm_called=False,reconstruction_scope='CURRENT_V4_RESULT_FROM_BOUND_PARENT_AND_INDEPENDENT_APPEND_FORMULA_SHARED_PARENT_CHECKER')
    else:
        # R uses independently fixed 65a/6a17 arithmetic; P never executes it.
        reader_meta=dict(shared_upstream_parent_checker_reference=auxiliary['parent_view'],shared_parent_checker_called=True,
            append_algorithm_called=False,reconstruction_scope='HOST_PAIR_BOUND_WHOLE_ACTUAL_V4_AND_GAP_V5_GRAPH_INDEPENDENT_ACTUAL_ARITHMETIC',
            **meta)
    expected=dict(schema=core.READBACK_SCHEMA,status=core.READBACK_STATUS,history_reference=parent['reference'],publication_reference=parent['publication_reference'],
        input_references=inputs,reader_sha256=parent['reader_reference']['sha256'],source_hashes=audited,counts=core.history_counts_v4(history),
        entire_history_independently_reconstructed=True,publisher_called=False,new_pure_called=False,current_live_cache_read_or_reverified=False,
        started_reference_observed_not_external_anchor=startref,started_externally_authenticated=False,**reader_meta,**FLAGS)
    exact(a,expected)
    auditfolder=Path(parent['readback_reference']['path']).parent
    auditstart=decode(consume(reference(auditfolder/'started.json',sha((auditfolder/'started.json').read_bytes())),sources))
    pairmeta={} if legacy else dict(implementation_pair_binding_reference=pair['binding_reference'],ancestry_contract_reference=pair['contract_reference'])
    if not legacy and modules.get('consumer_registry') is not None:
        pairmeta.update({key:meta[key]for key in ('consumer_role_registry_reference','consumer_registry_core_reference','consumer_metadata_contract_reference')})
    exact(auditstart,dict(schema='PROSPECTIVE_OBSERVATION_HISTORY_READBACK_STARTED_V4',history_reference=parent['reference'],publication_reference=parent['publication_reference'],
        registration_reference=inputs['registration'],reader_sha256=parent['reader_reference']['sha256'],**pairmeta,**FLAGS))


def modules_parent_schema(parent):return parent['document']['history']['schema']


def walk_parent_graph(parent,modules,sources,auxiliary):
    """Classify every original node before claims; replay oldest first."""
    envelopes={};current=parent
    while True:
        key=(current['reference']['path'],current['reference']['sha256'])
        require(key not in envelopes and len(envelopes)<MAX_PARENT_DEPTH,'Global ancestry cycle/depth')
        edge=modules['ancestry'].classify_parent_edge(current,bound_pair=modules['bound_pair'],legacy_implementations=modules['host_legacy'],**consumer_graph_context(modules))
        consume(current['reader_reference'],sources);envelopes[key]=current
        if edge['kind']=='terminal':break
        current=parent_documents(edge['prior_references'],sources)
    graph=modules['ancestry'].inspect_ancestry_graph({role:parent[role]for role in ROLES},envelopes,
        bound_pair=modules['bound_pair'],legacy_implementations=modules['host_legacy'],**consumer_graph_context(modules))
    inventories=[]
    for edge in graph['work_items']:
        refs=edge['child_references'];current=envelopes[(refs['reference']['path'],refs['reference']['sha256'])]
        view=modules['view'].inspect_parent_history_v5(current)
        if edge['kind']=='terminal':
            # This entire immutable root is independently host-pinned, including its maps.
            for field in ('document','publication','readback'):
                for path,digest in current[field]['source_hashes'].items():consume(reference(path,digest),sources)
            parent_inventory(refs,modules['checker'],sources,inventories)
        else:
            prior=envelopes[(edge['prior_references']['reference']['path'],edge['prior_references']['reference']['sha256'])]
            if edge['kind']=='gap':
                capture_inventory(edge['capture_references'],modules['checker'],sources,inventories,modules)
                verify_gap_outer(current,modules,sources)
            else:
                observation=observation_documents(edge['observation_references'],sources)
                observation_originals(prior,observation,modules,sources,inventories)
                history=modules['core'].reconstruct_actual(parent=prior,observation=observation)
                exact(current['document']['history'],history,'Independent whole actual ancestor')
                verify_actual_outer(current,prior,history,modules,sources,auxiliary)
            parent_inventory(refs,modules['checker'],sources,inventories)
        modules['verified_parents'].add((refs['reference']['path'],refs['reference']['sha256']))
        verify_baselines(view,sources)
        for entry in view['observations']:
            pin_namespace(Path(entry['payload_reference']['path']).parent,observation_namespace_files(observation_documents({role:entry[role]for role in OBSERVATION_ROLES},sources),modules),sources,inventories)
    return inventories,graph['parent_node_count']


def verify_gap_outer(parent,modules,sources):
    if continuation_header(*(parent[key]for key in ('document','publication','readback'))):return verify_continuation_gap(parent,modules,sources)
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
    source_refs=h['full_capture_source_references']
    rebuilt=modules['gap'].reconstruct_gap_history(parent=prior,capture_references=h['capture_references'],
        source_bytes={t:consume(source_refs[t],sources)for t in ('QQQ','SPY')},source_references=source_refs,
        accounted_baseline_bytes={t:consume(previous['accounted_baseline_references'][t],sources)for t in ('QQQ','SPY')},
        actual_baseline_bytes={t:consume(previous['baseline_references'][t],sources)for t in ('QQQ','SPY')},
        prefix_references=h['accounted_prefix_references'],prefix_evidence_references=h['accounted_prefix_evidence_references'],
        capture_started_at=h['capture_started_at'],capture_completed_at=h['capture_completed_at'],
        tzif_bytes=consume(h['tzif_reference'],sources),tzif_reference=h['tzif_reference'],
        parent_checker=modules['view'],csv_rows=modules['csv'].csv_rows,prefix_checker=modules['prefix'])
    exact(h,rebuilt,'Entire gap ancestor independently reconstructed')
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
    for path,digest in initial.items():consume(reference(path,digest),sources)


def load_modules(dependencies,auxiliary,sources):
    raw={key:consume(item,sources)for key,item in dependencies.items()};auxraw={key:consume(item,sources)for key,item in auxiliary.items()}
    helper=private(dependencies['compact_helpers']['path'],raw['compact_helpers'],dependencies['compact_helpers']['sha256'])
    legacy=private(auxiliary['legacy_view']['path'],auxraw['legacy_view'],auxiliary['legacy_view']['sha256'],[
        ('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',helper)])
    view=private(auxiliary['parent_view']['path'],auxraw['parent_view'],auxiliary['parent_view']['sha256'],[
        ('from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy','legacy',legacy)])
    independent={key:private(item['path'],consume(item,sources),item['sha256'])
        for key,item in {key:reference(*READER_ALGORITHMS[key])for key in
            ('history_reconstructor','legacy_history_reconstructor','independent_gap_reconstructor')}.items()}
    core=SimpleNamespace(**{key:getattr(legacy,key)for key in
        ('SCHEMA','WRAPPER_SCHEMA','PUBLICATION_SCHEMA','PUBLICATION_STATUS','READBACK_SCHEMA','READBACK_STATUS','history_counts_v4')})
    def reconstruct(*,parent,observation):
        blobs={path:consume(reference(path,digest),sources)for path,digest in observation['payload']['source_hashes'].items()}
        v=view.inspect_parent_history_v5(parent)
        for item in (*v['baseline_references'].values(),*v['accounted_baseline_references'].values()):blobs[item['path']]=consume(item,sources)
        return independent['history_reconstructor'].reconstruct_compact_actual(parent=parent,observation=observation,blobs=blobs,
            parent_checker=view,csv_rows=csvreader.csv_rows,independent_formula=independent['legacy_history_reconstructor'])
    core.reconstruct_actual=reconstruct
    checker=private(auxiliary['capture_checker']['path'],auxraw['capture_checker'],auxiliary['capture_checker']['sha256']);checker.CURRENT=CURRENT
    thinchecker=private(auxiliary['legacy_capture_checker_v3']['path'],auxraw['legacy_capture_checker_v3'],auxiliary['legacy_capture_checker_v3']['sha256'])
    observer=private(auxiliary['observation_reader']['path'],auxraw['observation_reader'],auxiliary['observation_reader']['sha256'])
    prefix=private(auxiliary['independent_prefix']['path'],auxraw['independent_prefix'],auxiliary['independent_prefix']['sha256'])
    csvreader=private(auxiliary['csv_reader']['path'],auxraw['csv_reader'],auxiliary['csv_reader']['sha256'])
    references=private(str(REGISTRATION_CORE[0]),consume(reference(*REGISTRATION_CORE),sources),REGISTRATION_CORE[1])
    gapreg=private(auxiliary['gap_registration']['path'],auxraw['gap_registration'],auxiliary['gap_registration']['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',references)])
    legacygapreader=private(auxiliary['gap_reader']['path'],auxraw['gap_reader'],auxiliary['gap_reader']['sha256'])
    return dict(core=core,view=view,legacy=legacy,checker=checker,observer=observer,prefix=prefix,csv=csvreader,gap_registration=gapreg,references=references,thinchecker=thinchecker,gap=independent['independent_gap_reconstructor'],legacy_gap_reader=legacygapreader)


def current_attempt_inventory(parent,observation,sources,inventories,*,research_root=None,modules=None,reserved_writer=None):
    """Only local direct children plus explicit inherited external attempt dirs."""
    research=Path(RESEARCH if research_root is None else research_root)
    entries=parent['document']['history']['observations']
    allowed={entry['payload_reference']['path']:{role:entry[role]for role in OBSERVATION_ROLES}for entry in entries}
    if observation is not None:allowed[observation['payload_reference']['path']]={key:observation[key]for key in OBSERVATION_ROLES}
    local=list(safe(research).iterdir());require(len(local)<=20000,'Bounded local semantic inventory')
    external={Path(path).parent for path in allowed if Path(path).parent.parent!=research}
    found={}
    for folder in [*local,*sorted(external,key=str)]:
        folder=safe(folder)
        if not folder.is_dir():continue
        if reserved_writer is not None and folder==reserved_writer['output']:
            verify_reserved_writer_phase(reserved_writer,parent,modules,sources,inventories)
            continue
        records={}
        for name in ('started.json','observation_payload.json','receipt.json','reader_started.json','failure.json'):
            path=safe(folder/name)
            if not path.exists():continue
            require(path.is_file()and path.stat().st_size<=64*1024**2,'Bounded semantic attempt file')
            raw=path.read_bytes();records[name]=(decode(raw),reference(path,sha(raw)))
        get=lambda name:records.get(name,({},{}))[0]
        semantic=(get('started.json').get('schema','').startswith('PROSPECTIVE_OBSERVATION_WRITER_STARTED_')or get('observation_payload.json').get('schema')=='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1'or get('receipt.json').get('schema')=='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1'or get('reader_started.json').get('schema')=='PROSPECTIVE_OBSERVATION_CONTINUATION_READER_STARTED_V1'or get('failure.json').get('consumer_role')in('observation_writer','observation_independent_reader')or get('failure.json').get('status')=='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY')
        if not semantic:require(folder not in external,'Explicit inherited attempt recognizable');continue
        is_continuation=continuation_header(get('started.json'),get('observation_payload.json'),get('receipt.json'))
        expected_records={'started.json','observation_payload.json','receipt.json'}|({'reader_started.json'}if is_continuation else set())
        require(set(records)==expected_records,'No partial or failed semantic attempt')
        payload=records['observation_payload.json'][1];require(payload['path']in allowed and payload['path']not in found,'Unregistered or duplicate semantic observation')
        expected=allowed[payload['path']];exact(payload,expected['payload_reference']);exact(records['receipt.json'][1],expected['receipt_reference'])
        names=('started.json','observation_payload.json','receipt.json','independent_readback.json')
        if is_continuation:
            require(modules is not None,'Host context for continuation semantic attempt')
            names=observation_namespace_files(observation_documents(expected,sources),modules)
        pin_namespace(folder,names,sources,inventories)
        audit=decode(consume(expected['audit_reference'],sources));start=records['started.json'][1]
        exact(audit['source_hashes'].get(start['path']),start['sha256'],'Whole semantic attempt START')
        if is_continuation:
            own=records['reader_started.json'][1];exact(audit['source_hashes'].get(own['path']),own['sha256'],'Whole independent reader START')
        found[payload['path']]={name:item for name,(_,item)in records.items()}
    exact(sorted(found),sorted(allowed),'All current bound actual attempts');return found


def preflight_original_graph(parent,observation,modules,sources,*,current_capture_references=None):
    """Classify all parent edges before permitting any claimed-source read.

    Only explicit original reference roles discover artifacts. Source maps never
    extend this allowlist. The terminal is independently host-byte-bound.
    """
    envelopes={};observations={};captures={};allowed=dict(sources)
    def permit(item):
        simple={key:item[key]for key in ('path','sha256')}
        reference(simple['path'],simple['sha256']);safe(simple['path'])
        require(simple['path']not in allowed or allowed[simple['path']]==simple['sha256'],'Preflight source conflict')
        allowed[simple['path']]=simple['sha256']
    def pair_refs(values,roles):
        require(type(values)is dict and set(values)==set(roles),'Closed explicit source-reference roles')
        for item in values.values():permit(item)
    def parent_roles(original):
        # Read the validated normalized state, never arbitrary wrapper fields.
        view=modules['view'].inspect_parent_history_v5(original)
        for field in ('baseline_references','accounted_baseline_references','full_capture_source_references',
                'accounted_prefix_references','accounted_prefix_evidence_references'):
            values=view.get(field)
            if values:pair_refs(values,('QQQ','SPY'))
        permit(view['tzif_reference'])
        for row in view['known_typed_rows']:permit(row['evidence_reference'])
        for entry in view['observations']:
            for role in OBSERVATION_ROLES:permit(entry[role])
            for field in ('captured_baseline_references','previous_baseline_references'):
                if entry.get(field):pair_refs(entry[field],('QQQ','SPY'))
        for entry in view['parent_attempt_inventory']:
            for role in ('payload_reference','receipt_reference','independent_readback_reference'):permit(entry[role])
        inputs=original['document']['input_references']
        if 'registration'in inputs:permit(inputs['registration'])
    def observation_roles(original):
        payload=original['payload'];inputs=payload['input_references']
        if 'registration'in inputs:permit(inputs['registration'])
        parts=payload['full_original_sources_preserved']
        require(type(parts)is dict and set(parts)=={'QQQ','SPY'},'Explicit payload source pair')
        for ticker in ('QQQ','SPY'):
            require(type(parts[ticker])is dict and set(parts[ticker])=={'sources','baseline_sources'},'Closed payload source roles')
            for role in ('sources','baseline_sources'):permit(parts[ticker][role]['reference'])
        permit(payload['tzif_reference'])
    def capture_roles(original):
        doc=original['document'];inputs=doc['input_references']
        if 'registration'in inputs:permit(inputs['registration'])
        pair_refs(doc['captured_artifacts'],('QQQ','SPY','tzif'))
    def permit_tree(value):
        if type(value)is dict:
            if set(value)=={'path','sha256'}:permit(value);return
            for child in value.values():permit_tree(child)
    def anchored_namespace(refs,history=True,continuation=False):
        for item in refs.values():permit(item)
        for role in ('reference','readback_reference') if history else ('payload_reference',):
            folder=safe(Path(refs[role]['path']).parent)
            path=folder/'started.json'
            require(path.is_file()and path.stat().st_size<=64*1024**2,'Bounded explicit START')
            permit(reference(path,sha(path.read_bytes())))
        if continuation and not history:
            path=safe(Path(refs['payload_reference']['path']).parent/'reader_started.json')
            require(path.is_file()and path.stat().st_size<=64*1024**2,'Bounded independent observation START')
            permit(reference(path,sha(path.read_bytes())))
    if current_capture_references is not None:captures[current_capture_references['reference']['path']]=current_capture_references
    current=parent;visited=set()
    while True:
        key=(current['reference']['path'],current['reference']['sha256'])
        require(key not in visited and len(visited)<MAX_PARENT_DEPTH,'Global preflight cycle/depth')
        visited.add(key)
        edge=modules['ancestry'].classify_parent_edge(current,bound_pair=modules['bound_pair'],legacy_implementations=modules['host_legacy'],**consumer_graph_context(modules))
        envelopes[key]=current
        if edge['kind']=='gap'and continuation_header(current['document'],current['publication'],current['readback']):
            expected_private=reader_private_inputs('gap_independent_reader',modules)
            exact(current['readback']['reader_input_references'],expected_private)
            permit_tree(expected_private)
        refs={role:current[role]for role in ROLES};anchored_namespace(refs)
        parent_roles(current)
        if edge['kind']=='terminal':
            # This map comes from the exact host-fixed terminal bytes, not a
            # dynamically chosen parent or an unauthenticated claim traversal.
            exact(current['reference'],reference(*TERMINAL_REFERENCE))
            for field in ('document','publication','readback'):
                for path,digest in current[field]['source_hashes'].items():permit(reference(path,digest))
            break
        if edge['kind']=='actual':observations[edge['observation_references']['payload_reference']['path']]=edge['observation_references']
        else:captures[edge['capture_references']['reference']['path']]=edge['capture_references']
        current=parent_documents(edge['prior_references'],sources)
    if observation is not None:observations[observation['payload_reference']['path']]={role:observation[role]for role in OBSERVATION_ROLES}
    for refs in observations.values():
        original=observation_documents(refs,sources)
        continuing=continuation_header(*(original[key]for key in ('payload','receipt','audit')))
        if continuing:
            observation_namespace_files(original,modules)
            permit_tree(reader_private_inputs('observation_independent_reader',modules))
        else:
            require(refs['reader_reference']in[reference(*AUXILIARIES[key])for key in ('observation_reader','legacy_observer_v3','legacy_observer_v4')],
                'Preflight known observation reader')
        require(original['audit'].get('schema')=='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3'and original['audit'].get('status')=='PASS','Preflight observation format')
        anchored_namespace(refs,False,continuing);observation_roles(original)
        captures[original['payload']['input_references']['capture']['reference']['path']]=original['payload']['input_references']['capture']
    for refs in captures.values():
        original=parent_documents(refs,sources);d=original['document'];inputs=d.get('input_references',{})
        schema=d.get('schema')
        continuing=continuation_header(*(original[key]for key in ('document','publication','readback')))
        if continuing:
            require(schema=='SOURCE_BOUND_FORWARD_CAPTURE_V5','Continuation genuine capture V5')
            for key,role in (('document','capture_publisher'),('publication','capture_publisher'),('readback','capture_independent_reader')):
                continuation_metadata(original[key],role,modules)
            expected_runtime=modules['consumer_registry']['consumer_references']['capture_publisher']
            expected_reader=modules['consumer_registry']['consumer_references']['capture_independent_reader']
            exact(original['readback']['reader_input_references'],reader_private_inputs('capture_independent_reader',modules))
            permit_tree(reader_private_inputs('capture_independent_reader',modules))
        elif schema=='SOURCE_BOUND_FORWARD_CAPTURE_V5':
            expected_runtime=reference(modules['checker'].PRODUCER,modules['checker'].PRODUCER_SHA)
            expected_reader=reference(*AUXILIARIES['capture_checker'])
        elif schema=='SOURCE_BOUND_FORWARD_CAPTURE_V4':
            expected_runtime=reference(ROOT/'scripts/ndx_registered_forward_capture_runtime_20261009_v1.py','e7850782dcc4c230353281935ebc428a7c02349a00cea89731ed16ea27e49190')
            expected_reader=reference(ROOT/'scripts/ndx_registered_forward_capture_independent_readback_20261009_v1.py','b44f2d2cd89f5ea4a64e268e86b409305e7e40673df6565f1d2ba8f9bdeb8cc2')
        else:
            require(schema=='SOURCE_BOUND_FORWARD_GAP_PARENT_CAPTURE_V3','Preflight supported capture format')
            expected_runtime=None;expected_reader=reference(*AUXILIARIES['legacy_capture_checker_v3'])
        exact(refs['reader_reference'],expected_reader,'Preflight capture reader role')
        if expected_runtime is not None:
            exact(inputs.get('runtime'),expected_runtime,'Preflight capture runtime role');permit(expected_runtime)
        anchored_namespace(refs);capture_roles(original)
    for item in (modules['bound_pair']['publisher_reference'],modules['bound_pair']['independent_reader_reference'],
            modules['bound_pair']['binding_reference'],modules['bound_pair']['contract_reference'],reference(*PAIR_BINDING_CORE),reference(*REGISTRATION_CORE)):
        permit(item)
    for group in (DEPENDENCIES,AUXILIARIES,READER_ALGORITHMS):
        for item in group.values():permit(reference(*item))
    for path,digest in modules['family_sources'].items():permit(reference(path,digest))
    # Fixed host closures of the explicitly supported upstream formats.
    checker=modules['checker'];observer=modules['observer']
    for path,digest in checker.DEPENDENCIES.values():permit(reference(ROOT/path,digest))
    for item in (checker.PREFIX_CORE,checker.GAP_CORE,checker.REGISTRATION_CORE,observer.REGISTRATION_CORE):permit(reference(*item))
    permit(reference(observer.WRITER,observer.WRITER_SHA))
    for group in (observer.DEPENDENCIES,observer.AUXILIARY_DEPENDENCIES):
        for item in group.values():permit(reference(*item))
    # Reject source-only extras before private helper paths can consume them.
    def check_claims(value):
        if type(value)is dict:
            if 'source_hashes'in value:
                require(type(value['source_hashes'])is dict,'Exact source declaration map')
                for path,digest in value['source_hashes'].items():
                    require(allowed.get(path)==digest,'Source declaration has no independently discovered role: '+path)
            for key,child in value.items():
                if key not in ('source_hashes','current_cache_references'):check_claims(child)
        elif type(value)is list:
            for child in value:check_claims(child)
    for original in [*envelopes.values(),*([observation]if observation is not None else [])]:check_claims(original)
    for refs in observations.values():check_claims(observation_documents(refs,sources))
    for refs in captures.values():check_claims(parent_documents(refs,sources))
    modules['permitted_sources']=allowed
    def claimed_consume(item,output):
        require(allowed.get(item['path'])==item['sha256'],'Unclassified source declaration cannot select IO')
        return consume(item,output)
    def original_parent(refs,output):
        key=(refs['reference']['path'],refs['reference']['sha256'])
        require(key in envelopes,'Private helper cannot discover an unclassified parent')
        original=envelopes[key]
        exact({role:original[role]for role in ROLES},refs,'Cached four original anchors')
        for item in refs.values():claimed_consume(item,output)
        # Claims are consumed only after the entire graph has passed role gates
        # and each source has an explicit discovered role (or fixed root bytes).
        for field in ('document','publication','readback'):
            for path,digest in original[field]['source_hashes'].items():claimed_consume(reference(path,digest),output)
        return deepcopy(original)
    modules['checker'].load_parent_envelope=original_parent
    modules['checker'].consume=claimed_consume
    return envelopes


def derive_pair_initial_sources(prior,observation,registration,modules,auxiliary):
    """Independently replay this ancestor's actual input scope, not its claims."""
    pair=modules['bound_pair'];initial={}
    fixed=[pair['publisher_reference'],pair['independent_reader_reference'],pair['binding_reference'],pair['contract_reference'],
        reference(*PAIR_BINDING_CORE),reference(*REGISTRATION_CORE),reference(*ANCESTRY_CONTRACT),reference(*LEGACY_ANCESTRY),
        reference(*CONSUMER_ROLE_CORE),reference(*CONSUMER_METADATA_CORE),registration]
    consumer=modules.get('consumer_registry')
    if consumer is not None:fixed.extend([consumer['registry_reference'],*consumer['consumer_references'].values()])
    fixed.extend(reference(*value)for group in (DEPENDENCIES,AUXILIARIES,READER_ALGORITHMS)for value in group.values())
    for item in fixed:consume(item,initial)
    inventories,_=walk_parent_graph(prior,modules,initial,auxiliary)
    observation_originals(prior,observation,modules,initial,inventories,current=True)
    # Historical inventory is already bound by original observation START and
    # explicit parent/observation namespaces. Later legitimate descendants must
    # not be treated as unregistered by replaying an old global scan.
    result=modules['core'].reconstruct_actual(parent=prior,observation=observation)
    for path,digest in result['source_hashes'].items():
        require(modules['permitted_sources'].get(path)==digest,'Derived history source requires original role')
        consume(reference(path,digest),initial)
    return initial


def publisher_dependencies():
    return {**{key:reference(*value)for key,value in DEPENDENCIES.items()},
        **{key:reference(*AUXILIARIES[key])for key in ('parent_view','legacy_view','capture_checker','observation_reader','csv_reader','independent_prefix')}}


def pair_inputs(*,parent,observation,registration,runtime,dependencies,auxiliary,registration_core,pair,consumer=None):
    result=dict(parent=deepcopy(parent),observation=deepcopy(observation),registration=registration,runtime=runtime,
        dependencies=dependencies,registration_dependency_references={key:dependencies[key]for key in ('history_core','compact_helpers')},
        auxiliary_dependencies=auxiliary,registration_core=registration_core,
        implementation_pair_binding=pair['binding_reference'],ancestry_contract=pair['contract_reference'],pair_binding_core=reference(*PAIR_BINDING_CORE))
    if consumer is not None:result.update(consumer_role_registry=consumer['registry_reference'],consumer_registry_core=reference(*CONSUMER_ROLE_CORE),consumer_metadata_contract=reference(*CONSUMER_METADATA_CORE))
    return result


def host_legacy_implementations():
    return [dict(parent_schema='PROSPECTIVE_GAP_EXTENSION_HISTORY_V3',input_role='pure',implementation_reference=reference(*TERMINAL_PURE),
            reader_reference=reference(*TERMINAL_READER),terminal_reference=reference(*TERMINAL_REFERENCE)),
        dict(parent_schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V4',input_role='runtime',implementation_reference=reference(*AUXILIARIES['legacy_compact_publisher']),reader_reference=reference(*AUXILIARIES['legacy_compact_reader'])),
        dict(parent_schema='PROSPECTIVE_GAP_EXTENSION_HISTORY_V5',input_role='runtime',implementation_reference=reference(*AUXILIARIES['gap_publisher']),reader_reference=reference(*AUXILIARIES['gap_reader']))]


def consumer_context(modules):
    require(modules.get('consumer_registry') is not None,'Independent host consumer registry required')
    return dict(bound_pair=modules['bound_pair'],consumer_registry_view=modules['consumer_registry'],
        consumer_registry_core_reference=reference(*CONSUMER_ROLE_CORE),metadata_contract_reference=reference(*CONSUMER_METADATA_CORE))


def consumer_graph_context(modules):
    if modules.get('consumer_registry') is None:return {}
    context=consumer_context(modules);context.pop('bound_pair')
    return dict(context,registered_gap_dependency_references={key:reference(ROOT/path,digest)
        for key,(path,digest)in modules['legacy_gap_reader'].DEPENDENCIES.items()})


def continuation_metadata(value,role,modules):
    return modules['consumer_metadata'].inspect_consumer_metadata(value,expected_role=role,**consumer_context(modules))


def continuation_header(*values):
    return any(type(value)is dict and any(key in value for key in
        ('continuation_adapter_schema','consumer_role','implementation_pair_binding_reference','consumer_role_registry_reference',
         'ancestry_contract_reference','shared_ancestry_verifier_reference','consumer_registry_core_reference','consumer_metadata_contract_reference'))for value in values)


def reader_private_inputs(role,modules):
    consumer=modules['consumer_registry'];pair=modules['bound_pair']
    helper={'capture_independent_reader':modules['checker'],'observation_independent_reader':modules['observer'],
        'gap_independent_reader':modules['legacy_gap_reader']}[role]
    def refs(group):return {key:reference(ROOT/path,digest)for key,(path,digest)in group.items()}
    independent={}
    if role=='capture_independent_reader':
        independent=dict(capture_plan_reconstructor=reference(*AUXILIARIES['capture_checker']),csv_reader=reference(*AUXILIARIES['csv_reader']))
    elif role=='gap_independent_reader':
        independent=dict(independent_gap_reconstructor=reference(*helper.INDEPENDENT_GAP),
            independent_prefix_reconstructor=reference(*helper.INDEPENDENT_PREFIX),csv_reader=reference(*helper.CSV_READER))
    return dict(runtime=consumer['consumer_references'][role],dependencies=refs(helper.DEPENDENCIES),
        auxiliary_dependencies=refs(getattr(helper,'AUXILIARY_DEPENDENCIES',{})),independent_dependencies=independent,
        registration_core=reference(*helper.REGISTRATION_CORE),reference_core=reference(*REGISTRATION_CORE),
        pair_binding_core=reference(*PAIR_BINDING_CORE),implementation_pair_binding=pair['binding_reference'],
        consumer_role_registry=consumer['registry_reference'],ancestry_contract=pair['contract_reference'],
        shared_ancestry_verifier=pair['independent_reader_reference'],consumer_registry_core=reference(*CONSUMER_ROLE_CORE),
        consumer_metadata_contract=reference(*CONSUMER_METADATA_CORE))


def consume_reference_tree(value,sources):
    # Only call on a host-constructed exact metadata/input object.
    if type(value)is dict:
        if set(value)=={'path','sha256'}:consume(value,sources);return
        for child in value.values():consume_reference_tree(child,sources)
    elif type(value)in (tuple,list):
        for child in value:consume_reference_tree(child,sources)


def load_host_family(*,implementation_pair_binding_path,implementation_pair_binding_sha256,
        consumer_role_registry_path=None,consumer_role_registry_sha256=None):
    require((consumer_role_registry_path is None)==(consumer_role_registry_sha256 is None),'Complete optional host consumer registry anchors')
    regref=reference(*REGISTRATION_CORE);paircore=reference(*PAIR_BINDING_CORE);contract=reference(*ANCESTRY_CONTRACT)
    legacycontract=reference(*LEGACY_ANCESTRY);consumerref=reference(*CONSUMER_ROLE_CORE);metadataref=reference(*CONSUMER_METADATA_CORE)
    bindingref=reference(implementation_pair_binding_path,implementation_pair_binding_sha256);selfref=reference(SOURCE,LOADED_SHA)
    cref=None if consumer_role_registry_path is None else reference(consumer_role_registry_path,consumer_role_registry_sha256)
    dependencies={key:reference(*value)for key,value in DEPENDENCIES.items()};auxiliary={key:reference(*value)for key,value in AUXILIARIES.items()}
    pairdeps=dict(publisher=publisher_dependencies(),independent_reader={key:reference(*value)for key,value in READER_ALGORITHMS.items()})
    sources={}
    reg=private(regref['path'],consume(regref,sources),regref['sha256'])
    binder=private(paircore['path'],consume(paircore,sources),paircore['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',reg)])
    registrykernel=private(consumerref['path'],consume(consumerref,sources),consumerref['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',reg)])
    metadata=private(metadataref['path'],consume(metadataref,sources),metadataref['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',reg),
        ('from backtest import ndx_continuation_consumer_role_registry_research_v1 as consumer_registry','consumer_registry',registrykernel)])
    legacy=private(legacycontract['path'],consume(legacycontract,sources),legacycontract['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as reference_kernel','reference_kernel',reg)])
    ancestry=private(contract['path'],consume(contract,sources),contract['sha256'],[
        ('from backtest import ndx_compact_ancestry_contract_research_v1 as legacy_contract','legacy_contract',legacy),
        ('from backtest import ndx_continuation_consumer_metadata_research_v1 as consumer_metadata','consumer_metadata',metadata)])
    pair=binder.inspect_pair_binding(binding=decode(consume(bindingref,sources)),binding_reference=bindingref,host_binding_reference=bindingref,
        self_role='independent_reader',self_reference=selfref,expected_contract_reference=contract,expected_algorithm_dependencies=pairdeps)
    consumer=None
    if cref is not None:
        consumer=registrykernel.inspect_consumer_roles(registry=decode(consume(cref,sources)),registry_reference=cref,
            host_registry_reference=cref,bound_pair=pair)
    consume(pair['publisher_reference'],sources);consume(selfref,sources)
    if consumer is not None:
        for item in consumer['consumer_references'].values():consume(item,sources)
    for item in pairdeps['independent_reader'].values():consume(item,sources)
    modules=load_modules(dependencies,auxiliary,sources)
    modules.update(bound_pair=pair,ancestry=ancestry,host_legacy=host_legacy_implementations(),verified_parents=set(),
        consumer_registry=consumer,consumer_metadata=metadata,consumer_registry_kernel=registrykernel)
    modules['family_sources']=deepcopy(sources)
    return dict(regref=regref,bindingref=bindingref,contract=contract,dependencies=dependencies,auxiliary=auxiliary,
        pairdeps=pairdeps,sources=sources,reg=reg,pair=pair,modules=modules)


def continuation_parent_sources(parent,modules):
    """Rebuild a producer's original input scope without scanning later attempts."""
    identity=(parent['reference']['path'],parent['reference']['sha256'])
    cache=modules.setdefault('continuation_parent_sources',{})
    if identity not in cache:
        initial=deepcopy(modules['family_sources'])
        auxiliary={key:reference(*value)for key,value in AUXILIARIES.items()}
        inventories,_=walk_parent_graph(parent,modules,initial,auxiliary)
        view=modules['view'].inspect_parent_history_v5(parent)
        verify_baselines(view,initial)
        cache[identity]=(deepcopy(initial),deepcopy(inventories))
    return deepcopy(cache[identity])


def continuation_expected_inputs(inputs,role,helper,modules,original_keys):
    dependencies={key:reference(ROOT/path,digest)for key,(path,digest)in helper.DEPENDENCIES.items()}
    expected={key:inputs[key]for key in original_keys}
    expected.update(runtime=modules['consumer_registry']['consumer_references'][role],dependencies=dependencies,
        registration_core=reference(*helper.REGISTRATION_CORE),reference_core=reference(*REGISTRATION_CORE))
    expected.update(modules['consumer_metadata'].continuation_input_references(
        registered_dependency_references=dependencies,consumer_role=role,**consumer_context(modules)))
    exact(inputs,expected,'Closed continuation producer input roles')
    modules['consumer_metadata'].inspect_producer_input_references(inputs,consumer_role=role,
        registered_dependency_references=dependencies,**consumer_context(modules))
    return expected


def verify_continuation_capture(refs,original,modules,sources,inventories):
    """Verify new capture originals; execute only the pinned independent plan formula."""
    d,p,a=(original[key]for key in ('document','publication','readback'))
    for value,role in ((d,'capture_publisher'),(p,'capture_publisher'),(a,'capture_independent_reader')):
        continuation_metadata(value,role,modules)
    checker=modules['checker'];consumer=modules['consumer_registry']['consumer_references']
    exact(refs['reader_reference'],consumer['capture_independent_reader'])
    folder=Path(refs['reference']['path']).parent;auditfolder=Path(refs['readback_reference']['path']).parent
    exact(refs['reference']['path'],str(folder/'capture.json'));exact(refs['publication_reference']['path'],str(folder/'publication.json'))
    exact(refs['readback_reference']['path'],str(auditfolder/'independent_readback.json'))
    pin_namespace(folder,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'),sources,inventories)
    pin_namespace(auditfolder,('started.json','independent_readback.json'),sources,inventories)
    inputs=continuation_expected_inputs(d['input_references'],'capture_publisher',checker,modules,
        ('dependencies','registration','runtime','registration_core','reference_core','prefix_core','gap_core','tzif'))
    exact(inputs['prefix_core'],reference(*checker.PREFIX_CORE));exact(inputs['gap_core'],reference(*checker.GAP_CORE))
    prior=parent_documents(d['parent_references'],sources);view=modules['view'].inspect_parent_history_v5(prior)
    initial,_=continuation_parent_sources(prior,modules)
    consume_reference_tree(inputs,initial)
    registration=private(inputs['registration_core']['path'],consume(inputs['registration_core'],initial),inputs['registration_core']['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',modules['references'])])
    registered=registration.prepare_forward_capture_runtime(registration=decode(consume(inputs['registration'],initial)),
        registration_reference=inputs['registration'],runtime_reference=consumer['capture_publisher'],
        dependency_references=inputs['dependencies'],research_root=str(folder.parent))
    exact(registered['parent'],d['parent_references']);exact(registered['output_directory'],str(folder));exact(inputs['tzif'],view['tzif_reference'])
    artifacts=d['captured_artifacts'];exact(sorted(artifacts),['QQQ','SPY','tzif'])
    for ticker in ('QQQ','SPY'):exact(artifacts[ticker]['path'],str(folder/(ticker+'.csv')))
    exact(artifacts['tzif']['path'],str(folder/'New_York.tzif'));exact(artifacts['tzif']['sha256'],view['tzif_reference']['sha256'])
    exact(sorted(d['current_cache_references']),['QQQ','SPY'])
    for ticker in ('QQQ','SPY'):
        exact(d['current_cache_references'][ticker],reference(CURRENT[ticker],artifacts[ticker]['sha256']))
    rebuilt=checker.reconstruct_plan(parent=prior,source_bytes={ticker:consume(artifacts[ticker],sources)for ticker in ('QQQ','SPY')},
        source_references={ticker:artifacts[ticker]for ticker in ('QQQ','SPY')},
        accounted_baseline_bytes={ticker:consume(view['accounted_baseline_references'][ticker],initial)for ticker in ('QQQ','SPY')},
        actual_baseline_bytes={ticker:consume(view['baseline_references'][ticker],initial)for ticker in ('QQQ','SPY')},
        capture_started_at=d['capture_started_at'],capture_completed_at=d['capture_completed_at'],
        tzif_bytes=consume(artifacts['tzif'],sources),tzif_reference=artifacts['tzif'],parent_checker=modules['view'],csv_rows=modules['csv'].csv_rows)
    exact(d['plan'],rebuilt,'Entire continuation capture plan independently reconstructed')
    flags=dict.fromkeys(checker.FALSE_FIELDS,False)
    producer_header=modules['consumer_metadata'].expected_consumer_metadata(consumer_role='capture_publisher',**consumer_context(modules))
    reader_header=modules['consumer_metadata'].expected_consumer_metadata(consumer_role='capture_independent_reader',**consumer_context(modules))
    startref=reference(folder/'started.json',sha((folder/'started.json').read_bytes()))
    exact(decode(consume(startref,sources)),dict(schema='FORWARD_CAPTURE_STARTED_V5',parent_references=d['parent_references'],
        input_references=inputs,source_hashes=initial,retry_allowed=False,**producer_header,**flags))
    published=deepcopy(initial)
    for item in artifacts.values():consume(item,published)
    exact(d,dict(schema='SOURCE_BOUND_FORWARD_CAPTURE_V5',plan=rebuilt,parent_references=d['parent_references'],input_references=inputs,
        captured_artifacts=artifacts,current_cache_references=d['current_cache_references'],
        current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',
        capture_started_at=d['capture_started_at'],capture_completed_at=d['capture_completed_at'],clock_captured_by_runner=True,
        external_clock_attestation_verified=False,quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',source_hashes=published,**producer_header,**flags))
    exact(p,dict(schema='FORWARD_CAPTURE_PUBLICATION_V5',status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION',capture_reference=refs['reference'],source_hashes=published,**producer_header,**flags))
    privateinputs=reader_private_inputs('capture_independent_reader',modules)
    ownref=reference(auditfolder/'started.json',sha((auditfolder/'started.json').read_bytes()))
    audited=deepcopy(published);consume_reference_tree(privateinputs,audited)
    for item in (refs['reference'],refs['publication_reference'],startref,ownref):consume(item,audited)
    exact(decode(consume(ownref,sources)),dict(schema='FORWARD_CAPTURE_READBACK_STARTED_V5',capture_reference=refs['reference'],
        publication_reference=refs['publication_reference'],registration_reference=inputs['registration'],reader_sha256=refs['reader_reference']['sha256'],
        input_references=inputs,reader_input_references=privateinputs,**reader_header,**flags))
    exact(a,dict(schema='FORWARD_CAPTURE_INDEPENDENT_READBACK_V5',status='PURE_FORWARD_CAPTURE_READBACK_PASS',
        capture_reference=refs['reference'],publication_reference=refs['publication_reference'],parent_references=d['parent_references'],input_references=inputs,
        reader_input_references=privateinputs,producer_reference=inputs['runtime'],reader_sha256=refs['reader_reference']['sha256'],source_hashes=audited,
        counts=dict(status=rebuilt['status'],parent_typed_row_count=len(rebuilt['known_typed_rows']),parent_actual_observation_count=len(rebuilt['observations']),
            parent_observed_count=sum(row['kind']!='MISSED_OBSERVATION'for row in rebuilt['known_typed_rows']),parent_gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in rebuilt['known_typed_rows']),
            candidate_session=rebuilt['candidate_session'],diagnostic_count=len(rebuilt['diagnostics']),snapshot_counts={ticker:rebuilt['source_evidence'][ticker]['original_row_count']for ticker in ('QQQ','SPY')}),
        entire_plan_independently_reconstructed=True,snapshot_bytes_verified=True,producer_called=False,capture_core_called=False,current_live_cache_read_or_reverified=False,
        external_clock_attestation_verified=False,shared_upstream_parent_checker_reference=inputs['dependencies']['parent_view'],shared_parent_checker_called=True,
        reconstruction_scope='INDEPENDENT_CAPTURE_PLAN_FROM_BOUND_PARENT_SHARED_PARENT_INSPECTOR_NOT_SOURCE_OR_CLOCK_AUTHENTICATION',
        started_reference_observed_not_external_anchor=startref,started_externally_authenticated=False,
        csv_reader_reference=reference(*AUXILIARIES['csv_reader']),csv_resource_semantics='MAX_8000000_SOURCE_BYTES_MAX_20000_DATA_ROWS_BLANK_RECORDS_EXCLUDED_NO_EXTRA_PHYSICAL_LINE_LIMIT',
        shared_legacy_parent_checker_reference=inputs['dependencies']['legacy_view'],prefix_core_called_for_parent_evidence_only=False,
        gap_core_called=False,parent_chain_and_original_prefix_bytes_reverified=True,actual_parent_schema=view['parent_schema'],
        reader_started_reference_observed_not_external_anchor=ownref,reader_started_externally_authenticated=False,**reader_header,**flags))
    for path,digest in audited.items():consume(reference(path,digest),sources)
    return rebuilt


def verify_continuation_gap(parent,modules,sources):
    """Reconstruct every gap value and prefix byte using independent algorithms."""
    d,p,a=(parent[key]for key in ('document','publication','readback'))
    for value,role in ((d,'gap_publisher'),(p,'gap_publisher'),(a,'gap_independent_reader')):continuation_metadata(value,role,modules)
    helper=modules['legacy_gap_reader'];h=d['history'];inputs=continuation_expected_inputs(d['input_references'],'gap_publisher',helper,modules,
        ('parent','capture','registration','runtime','dependencies','registration_core','reference_core','csv_reader'))
    exact(inputs['parent'],h['parent_references']);exact(inputs['capture'],h['capture_references'])
    exact(inputs['csv_reader'],reference(*AUXILIARIES['csv_reader']))
    exact(parent['reader_reference'],modules['consumer_registry']['consumer_references']['gap_independent_reader'])
    prior=parent_documents(h['parent_references'],sources);previous=modules['view'].inspect_parent_history_v5(prior)
    initial,inventory=continuation_parent_sources(prior,modules);consume_reference_tree(inputs,initial)
    capture=parent_documents(h['capture_references'],initial)
    capture_inventory(h['capture_references'],modules['checker'],initial,inventory,modules)
    cap=capture['document'];exact(cap['parent_references'],h['parent_references'])
    exact(h['full_capture_source_references'],{ticker:cap['captured_artifacts'][ticker]for ticker in ('QQQ','SPY')})
    exact(h['capture_started_at'],cap['capture_started_at']);exact(h['capture_completed_at'],cap['capture_completed_at'])
    exact(h['tzif_reference'],cap['captured_artifacts']['tzif'])
    folder=Path(parent['reference']['path']).parent;auditfolder=Path(parent['readback_reference']['path']).parent
    registration=modules['gap_registration'].prepare_gap_runtime(registration=decode(consume(inputs['registration'],initial)),
        registration_reference=inputs['registration'],runtime_reference=inputs['runtime'],dependency_references=inputs['dependencies'],research_root=str(folder.parent))
    exact(registration['parent'],h['parent_references']);exact(registration['capture'],h['capture_references']);exact(registration['output_directory'],str(folder))
    source_refs=h['full_capture_source_references']
    rebuilt=modules['gap'].reconstruct_gap_history(parent=prior,capture_references=h['capture_references'],
        source_bytes={ticker:consume(source_refs[ticker],initial)for ticker in ('QQQ','SPY')},source_references=source_refs,
        accounted_baseline_bytes={ticker:consume(previous['accounted_baseline_references'][ticker],initial)for ticker in ('QQQ','SPY')},
        actual_baseline_bytes={ticker:consume(previous['baseline_references'][ticker],initial)for ticker in ('QQQ','SPY')},
        prefix_references=h['accounted_prefix_references'],prefix_evidence_references=h['accounted_prefix_evidence_references'],
        capture_started_at=h['capture_started_at'],capture_completed_at=h['capture_completed_at'],
        tzif_bytes=consume(h['tzif_reference'],initial),tzif_reference=h['tzif_reference'],parent_checker=modules['view'],csv_rows=modules['csv'].csv_rows,prefix_checker=modules['prefix'])
    exact(h,rebuilt,'Entire continuation gap ancestor independently reconstructed')
    flags=dict.fromkeys(('source_authenticity_verified','parent_history_authenticated_by_this_module','clock_authenticity_verified','timeliness_verified',
        'filesystem_attempt_inventory_authenticated','observation_created','candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed',
        'live_mutation_allowed','future_independent_oos','production_generator_authorized','old_calendar_mutated','network_quote_refresh_performed','full_transitive_source_closure_reverified',
        'network_capture_performed','seal_event_created','partial_recovery_performed','canonical_calendar_append_allowed','retrospective_backfill_allowed','decision_eligible','exchange_holidays_and_early_closes_verified'),False)
    pubmeta=modules['consumer_metadata'].expected_consumer_metadata(consumer_role='gap_publisher',**consumer_context(modules))
    readmeta=modules['consumer_metadata'].expected_consumer_metadata(consumer_role='gap_independent_reader',**consumer_context(modules))
    startref=reference(folder/'started.json',sha((folder/'started.json').read_bytes()))
    upstream=dict(shared_upstream_capture_checker_reference=inputs['dependencies']['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,current_live_cache_read_or_reverified=False)
    exact(decode(consume(startref,sources)),dict(schema='PROSPECTIVE_GAP_HISTORY_STARTED_V5',input_references=inputs,source_hashes=initial,retry_allowed=False,**upstream,**pubmeta,**flags))
    published=deepcopy(initial)
    for item in (startref,*h['accounted_prefix_references'].values(),*h['accounted_prefix_evidence_references'].values()):consume(item,published)
    exact(d,dict(schema=modules['view'].WRAPPER_SCHEMA,history=rebuilt,input_references=inputs,source_hashes=published,**upstream,**pubmeta,**flags))
    exact(p,dict(schema=modules['view'].PUBLICATION_SCHEMA,status=modules['view'].PUBLICATION_STATUS,history_reference=parent['reference'],input_references=inputs,source_hashes=published,**pubmeta,**flags))
    privateinputs=reader_private_inputs('gap_independent_reader',modules)
    ownref=reference(auditfolder/'started.json',sha((auditfolder/'started.json').read_bytes()))
    audited=deepcopy(published);consume_reference_tree(privateinputs,audited)
    for item in (parent['reference'],parent['publication_reference'],ownref):consume(item,audited)
    exact(decode(consume(ownref,sources)),dict(schema='PROSPECTIVE_GAP_HISTORY_READBACK_STARTED_V5',history_reference=parent['reference'],
        publication_reference=parent['publication_reference'],registration_reference=inputs['registration'],reader_sha256=parent['reader_reference']['sha256'],
        input_references=inputs,reader_input_references=privateinputs,**readmeta,**flags))
    exact(a,dict(schema=modules['view'].READBACK_SCHEMA,status=modules['view'].READBACK_STATUS,history_reference=parent['reference'],publication_reference=parent['publication_reference'],
        reader_sha256=parent['reader_reference']['sha256'],input_references=inputs,reader_input_references=privateinputs,source_hashes=audited,counts=modules['view'].gap_counts(rebuilt),
        entire_history_independently_reconstructed=True,publisher_called=False,new_pure_called=False,producer_prefix_core_called=False,producer_scoped_parser_called=False,
        current_live_cache_read_or_reverified=False,snapshot_bytes_verified=True,independent_gap_reconstructor_reference=privateinputs['independent_dependencies']['independent_gap_reconstructor'],
        independent_prefix_reconstructor_reference=privateinputs['independent_dependencies']['independent_prefix_reconstructor'],csv_reader_reference=privateinputs['independent_dependencies']['csv_reader'],
        shared_upstream_capture_checker_reference=inputs['dependencies']['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,
        publisher_started_reference_observed_not_external_anchor=startref,publisher_started_externally_authenticated=False,
        reconstruction_scope='INDEPENDENT_ENTIRE_GAP_RESULT_AND_PREFIX_BYTES_SHARED_UPSTREAM_CAPTURE_CHECKER_NO_SOURCE_OR_CLOCK_AUTHENTICATION',
        reader_started_reference_observed_not_external_anchor=ownref,reader_started_externally_authenticated=False,**readmeta,**flags))
    for path,digest in audited.items():consume(reference(path,digest),sources)


def continuation_observation_values(payload,receipt,started,parent,capture_env,refs,payload_reference,blobs,session,inventory,modules):
    """All supplied blobs must come from wrapper-verified external byte references."""
    # Independent business formulas; no frozen observer IO/inspect entry is called.
    helper=modules['observer'];parse_csv=helper.parse_csv;day=helper.day;utc=helper.utc;enc=helper.enc;ref=helper.ref
    ADAPTER=helper.ADAPTER;CHECKER=helper.CHECKER;INVENTORY_SCOPE=helper.INVENTORY_SCOPE
    RESEARCH=Path(payload['local_direct_child_inventory_scope']['root']);PAYLOAD_FALSE=helper.PAYLOAD_FALSE;WRITER_FALSE=helper.WRITER_FALSE
    view=modules['view'].inspect_parent_history_v5(parent)
    actual_session=capture_env['document']['plan']['candidate_session']
    exact(capture_env['document']['plan']['status'],'ONE_NEW_SESSION_CAPTURE_CANDIDATE')
    exact(capture_env['document']['plan']['diagnostics'],[])
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
    require(payload['schema']=='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1' and receipt['schema']=='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1' and started['schema']=='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V5','Evidence schemas')
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
        require(obj['shared_upstream_capture_checker_called']is True and obj['capture_readback_called']is False,'Shared upstream role only')
        require(obj['producer_prefix_core_called']is False and obj['gap_core_called']is False,'No producer prefix or gap execution')
        exact(obj['independent_prefix_checker_reference'],refs['auxiliary_dependencies']['independent_prefix'],'Independent prefix host role')
    for obj in (started,receipt):exact(obj['source_hashes'],payload['source_hashes'],'Same source map');exact(obj['runtime'],payload['runtime'],'Same runtime claim')
    for obj,flags in ((payload,set(PAYLOAD_FALSE)|set(WRITER_FALSE)),(receipt,WRITER_FALSE),(started,WRITER_FALSE)):
        for k in flags:require(obj[k] is False,'No permission upgrade '+k)
    require(payload['payload_is_not_a_published_observation_receipt'] is True and payload['seal_status_history_not_created'] is True,'Payload boundary')
    return dict(parent_typed_row_count=len(known),parent_actual_observation_count=sum(r['kind']=='PROSPECTIVE_OBSERVED_SESSION'for r in known),parent_observed_count=sum(r['kind']!='MISSED_OBSERVATION'for r in known),parent_gap_count=sum(r['kind']=='MISSED_OBSERVATION'for r in known),new_observation_count=1,month_first_actual_observation=monthfirst==session,timing_classification=receipt['timing_classification'],clock_authenticity_verified=False,final_durable_completion_time_verified=False,candidate_seal_allowed=False,cohort_registration_allowed=False)


def verify_continuation_observation_producer(parent,observation,modules,sources,inventories):
    """Whole writer originals and independent business math; no reader output required."""
    p,r=(observation[key]for key in ('payload','receipt'));helper=modules['observer']
    for value in (p,r):continuation_metadata(value,'observation_writer',modules)
    folder=Path(observation['payload_reference']['path']).parent
    for role,name in (('payload_reference','observation_payload.json'),('receipt_reference','receipt.json')):
        exact(observation[role]['path'],str(folder/name))
    refs=continuation_expected_inputs(p['input_references'],'observation_writer',helper,modules,
        ('parent','capture','dependencies','auxiliary_dependencies','registration','runtime','registration_core','reference_core'))
    exact(refs['parent'],{role:parent[role]for role in ROLES})
    exact(refs['auxiliary_dependencies'],{key:reference(*value)for key,value in helper.AUXILIARY_DEPENDENCIES.items()})
    initial,_=continuation_parent_sources(parent,modules);consume_reference_tree(refs,initial)
    registration=private(refs['registration_core']['path'],consume(refs['registration_core'],initial),refs['registration_core']['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',modules['references'])])
    registered=registration.prepare_observation_runtime(registration=decode(consume(refs['registration'],initial)),registration_reference=refs['registration'],
        runtime_reference=refs['runtime'],dependency_references=refs['dependencies'],research_root=str(folder.parent))
    exact(registered['parent'],refs['parent']);exact(registered['capture'],refs['capture']);exact(registered['output_directory'],str(folder))
    captured=parent_documents(refs['capture'],initial)
    capture_inventory(refs['capture'],modules['checker'],initial,inventories,modules)
    exact(captured['document']['parent_references'],refs['parent'])
    view=modules['view'].inspect_parent_history_v5(parent)
    inventory=bound_attempt_inventory(view,folder.parent,False,modules)
    for records in inventory.values():
        for item in records.values():consume(item,initial)
    blobs={}
    for ticker in ('QQQ','SPY'):
        for item in (captured['document']['captured_artifacts'][ticker],view['accounted_baseline_references'][ticker],view['baseline_references'][ticker]):
            blobs[item['path']]=consume(item,initial)
    tz=captured['document']['captured_artifacts']['tzif'];blobs[tz['path']]=consume(tz,initial)
    startref=reference(folder/'started.json',sha((folder/'started.json').read_bytes()));started=decode(consume(startref,sources))
    pubmeta=modules['consumer_metadata'].expected_consumer_metadata(consumer_role='observation_writer',**consumer_context(modules))
    readmeta=modules['consumer_metadata'].expected_consumer_metadata(consumer_role='observation_independent_reader',**consumer_context(modules))
    continuation_metadata(started,'observation_writer',modules)
    flags=dict.fromkeys(helper.WRITER_FALSE,False)
    runtime=p['runtime']
    require(type(runtime)is dict and set(runtime)=={'python','executable','implementation'}and all(type(value)is str and 0<len(value)<10000 for value in runtime.values()),'Bounded declared observation runtime')
    metadata=dict(writer_adapter_schema=helper.ADAPTER,input_references=refs,source_hashes=initial,runtime=runtime,
        capture_checker_reference=reference(*AUXILIARIES['capture_checker']),attempt_inventory_scope=helper.INVENTORY_SCOPE,
        local_attempt_namespace_inventory=inventory,actual_parent_schema=view['parent_schema'],
        local_direct_child_inventory_scope=dict(root=str(folder.parent),depth=1,semantic_writer_namespaces_scanned=True),
        external_parent_bound_attempt_inventory={path:value for path,value in inventory.items()if Path(path).parent.parent!=folder.parent},
        external_unregistered_attempt_discovery_performed=False,shared_upstream_capture_checker_called=True,capture_readback_called=False,
        independent_prefix_checker_reference=reference(*AUXILIARIES['independent_prefix']),producer_prefix_core_called=False,gap_core_called=False,**pubmeta)
    exact(started,dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V5',writer_started_at_utc=p['writer_started_at_utc'],**metadata,**flags))
    counts=continuation_observation_values(p,r,started,parent,captured,refs,observation['payload_reference'],blobs,p['session'],inventory,modules)
    exact(r,dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY',
        observation_id=p['observation_id'],payload_reference=observation['payload_reference'],publication_check_at_utc=r['publication_check_at_utc'],
        publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE',timing_classification=r['timing_classification'],
        month_first_actual_observation=p['month_first_actual_observation'],**metadata,**flags))
    corekeys={'schema','observation_id','observation_identity','session','sequence','kind','initial_seal_status','month_first_actual_observation',
        'first_actual_observed_session_of_month','timing_classification','capture_started_at_utc','capture_completed_at_utc','writer_started_at_utc','writer_completed_at_utc',
        'conservative_close_utc','conservative_deadline_utc','selected_original_rows','source_row_locations','full_original_sources_preserved','tzif_reference','tzif_bytes_base64',
        'parent_readback_reference','known_typed_rows_preserved','parent_attempt_inventory_preserved','source_hash_claims',
        'payload_is_not_a_published_observation_receipt','seal_status_history_not_created','writer_interval_role'}
    exact(sorted(p),sorted(corekeys|set(metadata)|set(helper.PAYLOAD_FALSE)|set(flags)))
    for key,value in metadata.items():exact(p[key],value,'Whole continuation observation metadata '+key)
    return dict(refs=refs,initial=initial,view=view,inventory=inventory,startref=startref,started=started,
        counts=counts,metadata=metadata,flags=flags)


def verify_continuation_observation(parent,observation,modules,sources,inventories,*,current=False):
    """Verify the real five-file format without legacy IO adapters or projections."""
    p,r,a=(observation[key]for key in ('payload','receipt','audit'));helper=modules['observer']
    names=observation_namespace_files(observation,modules)
    folder=Path(observation['payload_reference']['path']).parent
    for role,name in (('payload_reference','observation_payload.json'),('receipt_reference','receipt.json'),('audit_reference','independent_readback.json')):
        exact(observation[role]['path'],str(folder/name))
    pin_namespace(folder,names,sources,inventories)
    producer=verify_continuation_observation_producer(parent,observation,modules,sources,inventories)
    refs,initial,view,inventory,startref,started,counts,metadata,flags=(producer[key]for key in
        ('refs','initial','view','inventory','startref','started','counts','metadata','flags'))
    ownref=reference(folder/'reader_started.json',sha((folder/'reader_started.json').read_bytes()))
    readmeta=modules['consumer_metadata'].expected_consumer_metadata(consumer_role='observation_independent_reader',**consumer_context(modules))
    privateinputs=reader_private_inputs('observation_independent_reader',modules)
    exact(decode(consume(ownref,sources)),dict(schema='PROSPECTIVE_OBSERVATION_CONTINUATION_READER_STARTED_V1',payload_reference=observation['payload_reference'],
        receipt_reference=observation['receipt_reference'],parent_history_reference=parent['reference'],input_references=refs,reader_input_references=privateinputs,
        reader_sha256=observation['reader_reference']['sha256'],**readmeta,**flags))
    audited=deepcopy(initial);consume_reference_tree(privateinputs,audited)
    for item in (observation['payload_reference'],observation['receipt_reference'],startref,ownref):consume(item,audited)
    exact(a,dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3',status='PASS',payload_reference=observation['payload_reference'],
        receipt_reference=observation['receipt_reference'],parent_history_reference=parent['reference'],input_references=refs,reader_input_references=privateinputs,
        started_current_bytes_reference=startref,started_external_sha_authenticated=False,reader_sha256=observation['reader_reference']['sha256'],source_hashes=audited,counts=counts,
        writer_called=False,payload_core_called=False,shared_upstream_capture_checker_reference=metadata['capture_checker_reference'],attempt_inventory_scope=helper.INVENTORY_SCOPE,
        local_attempt_namespace_inventory=inventory,old_audit_repeated=False,exchange_holidays_verified=False,early_closes_verified=False,final_durable_completion_time_verified=False,
        writer_adapter_schema=helper.ADAPTER,actual_parent_schema=view['parent_schema'],shared_upstream_parent_checker_reference=refs['dependencies']['parent_view'],
        local_direct_child_inventory_scope=metadata['local_direct_child_inventory_scope'],external_parent_bound_attempt_inventory=metadata['external_parent_bound_attempt_inventory'],
        external_unregistered_attempt_discovery_performed=False,shared_upstream_capture_checker_called=True,capture_readback_called=False,
        independent_prefix_checker_reference=metadata['independent_prefix_checker_reference'],producer_prefix_core_called=False,gap_core_called=False,
        reader_started_reference_observed_not_external_anchor=ownref,reader_started_externally_authenticated=False,**readmeta,**flags))
    for path,digest in audited.items():consume(reference(path,digest),sources)
    return started


def prepare_writer_reservation(registration_reference,parent,modules,sources,research):
    """Only one independently host-supplied registration may reserve a writer path."""
    consumer_context(modules)
    regref=reference(registration_reference['path'],registration_reference['sha256'])
    exact(registration_reference,regref)
    helper=modules['observer'];core=reference(*helper.REGISTRATION_CORE)
    kernel=private(core['path'],consume(core,sources),core['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',modules['references'])])
    deps={key:reference(*value)for key,value in helper.DEPENDENCIES.items()}
    plan=kernel.prepare_observation_runtime(registration=decode(consume(regref,sources)),registration_reference=regref,
        runtime_reference=modules['consumer_registry']['consumer_references']['observation_writer'],dependency_references=deps,research_root=str(research))
    exact(plan['parent'],{role:parent[role]for role in ROLES},'Reserved writer has exactly this verified root')
    output=safe(plan['output_directory'])
    require(output.parent==safe(research),'Reserved writer direct child')
    return dict(registration_reference=regref,plan=plan,output=output,observed={},phase=-1,initial_checked=False)


def initialize_writer_reservation(state,parent,modules,sources,inventories):
    helper=modules['observer'];plan=state['plan'];context=consumer_context(modules)
    inputs=dict(parent=plan['parent'],capture=plan['capture'],dependencies=plan['dependency_references'],
        auxiliary_dependencies={key:reference(*value)for key,value in helper.AUXILIARY_DEPENDENCIES.items()},
        registration=state['registration_reference'],runtime=plan['runtime_reference'],registration_core=reference(*helper.REGISTRATION_CORE),
        reference_core=reference(*REGISTRATION_CORE),**modules['consumer_metadata'].continuation_input_references(
            registered_dependency_references=plan['dependency_references'],consumer_role='observation_writer',**context))
    initial,_=continuation_parent_sources(parent,modules);consume_reference_tree(inputs,initial)
    capture=parent_documents(plan['capture'],initial)
    capture_inventory(plan['capture'],modules['checker'],initial,inventories,modules)
    cap=capture['document'];exact(cap['parent_references'],plan['parent'])
    view=modules['view'].inspect_parent_history_v5(parent)
    artifacts=cap['captured_artifacts'];blobs={}
    for ticker in ('QQQ','SPY'):
        for item in (artifacts[ticker],view['accounted_baseline_references'][ticker],view['baseline_references'][ticker]):
            blobs[item['path']]=consume(item,initial)
    blobs[artifacts['tzif']['path']]=consume(artifacts['tzif'],initial)
    rebuilt=modules['checker'].reconstruct_plan(parent=parent,source_bytes={ticker:blobs[artifacts[ticker]['path']]for ticker in ('QQQ','SPY')},
        source_references={ticker:artifacts[ticker]for ticker in ('QQQ','SPY')},
        accounted_baseline_bytes={ticker:blobs[view['accounted_baseline_references'][ticker]['path']]for ticker in ('QQQ','SPY')},
        actual_baseline_bytes={ticker:blobs[view['baseline_references'][ticker]['path']]for ticker in ('QQQ','SPY')},
        capture_started_at=cap['capture_started_at'],capture_completed_at=cap['capture_completed_at'],tzif_bytes=blobs[artifacts['tzif']['path']],
        tzif_reference=artifacts['tzif'],parent_checker=modules['view'],csv_rows=modules['csv'].csv_rows)
    exact(cap['plan'],rebuilt,'Reserved current capture entire independent formula')
    exact(rebuilt['status'],'ONE_NEW_SESSION_CAPTURE_CANDIDATE');exact(rebuilt['diagnostics'],[])
    inventory=bound_attempt_inventory(view,state['output'].parent,False,modules)
    for records in inventory.values():
        for item in records.values():consume(item,initial)
    base=dict(writer_adapter_schema=helper.ADAPTER,input_references=inputs,source_hashes=deepcopy(initial),
        capture_checker_reference=reference(*AUXILIARIES['capture_checker']),attempt_inventory_scope=helper.INVENTORY_SCOPE,
        local_attempt_namespace_inventory=inventory,actual_parent_schema=view['parent_schema'],
        local_direct_child_inventory_scope=dict(root=str(state['output'].parent),depth=1,semantic_writer_namespaces_scanned=True),
        external_parent_bound_attempt_inventory={path:value for path,value in inventory.items()if Path(path).parent.parent!=state['output'].parent},
        external_unregistered_attempt_discovery_performed=False,shared_upstream_capture_checker_called=True,capture_readback_called=False,
        independent_prefix_checker_reference=reference(*AUXILIARIES['independent_prefix']),producer_prefix_core_called=False,gap_core_called=False,
        **modules['consumer_metadata'].expected_consumer_metadata(consumer_role='observation_writer',**context))
    state.update(inputs=inputs,capture=capture,view=view,initial=initial,inventory=inventory,metadata_base=base)
    for path,digest in initial.items():consume(reference(path,digest),sources)


def verify_reserved_writer_phase(state,parent,modules,sources,inventories):
    """Monotonic fixed-file states; this is never a general path exclusion."""
    folder=safe(state['output']);helper=modules['observer']
    stages=((),('started.json',),('started.json','observation_payload.json'),
        ('started.json','observation_payload.json','receipt.json'),
        ('started.json','observation_payload.json','receipt.json','reader_started.json'),
        ('started.json','observation_payload.json','receipt.json','reader_started.json','independent_readback.json'))
    files=[] if not folder.exists()else list(folder.iterdir())
    if folder.exists():require(folder.is_dir(),'Reserved writer namespace must be a directory')
    names={item.name for item in files}
    require(any(names==set(stage)for stage in stages),'Reserved writer fixed stages; extra/failure file refused')
    phase=next(index for index,stage in enumerate(stages)if names==set(stage))
    require(phase>=state['phase'],'Reserved writer phase cannot regress')
    if not state['initial_checked']:require(phase in(0,3),'Initial reserved writer is absent or complete writer three')
    require(bool(files)or not folder.exists(),'An empty pre-existing writer directory is not absent')
    original={};refs={}
    for item in files:
        require(safe(item).is_file()and item.stat().st_size<=64*1024**2,'Bounded regular reserved writer file')
        raw=item.read_bytes();ref=reference(item,sha(raw));original[item.name]=decode(raw);refs[item.name]=ref
        if item.name in state['observed']:exact(ref,state['observed'][item.name],'Observed reserved output is immutable')
    flags=dict.fromkeys(helper.WRITER_FALSE,False)
    if phase>=1:
        started=original['started.json'];continuation_metadata(started,'observation_writer',modules)
        runtime=started['runtime']
        require(type(runtime)is dict and set(runtime)=={'python','executable','implementation'}and all(type(value)is str and 0<len(value)<10000 for value in runtime.values()),'Reserved declared runtime')
        helper.utc(started['writer_started_at_utc'])
        metadata=dict(state['metadata_base'],runtime=runtime)
        exact(started,dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V5',writer_started_at_utc=started['writer_started_at_utc'],**metadata,**flags))
    if phase>=2:
        payload=original['observation_payload.json'];continuation_metadata(payload,'observation_writer',modules)
        exact(payload['schema'],'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1')
        for key,value in metadata.items():exact(payload[key],value,'Reserved payload association '+key)
        exact(payload['session'],state['capture']['document']['plan']['candidate_session'])
        exact(payload['parent_readback_reference'],parent['readback_reference'])
        identity=dict(parent_reference=parent['reference'],capture_reference=state['plan']['capture']['reference'],session=payload['session'])
        exact(payload['observation_identity'],identity);exact(payload['observation_id'],sha(helper.enc(identity)))
        exact(payload['writer_started_at_utc'],started['writer_started_at_utc'])
        exact(payload['capture_started_at_utc'],state['capture']['document']['capture_started_at'])
        exact(payload['capture_completed_at_utc'],state['capture']['document']['capture_completed_at'])
        for key in set(helper.PAYLOAD_FALSE)|set(flags):require(payload[key]is False,'Reserved payload strict false '+key)
    if phase>=3:
        observation=dict(payload_reference=refs['observation_payload.json'],receipt_reference=refs['receipt.json'],
            payload=original['observation_payload.json'],receipt=original['receipt.json'])
        producer=verify_continuation_observation_producer(parent,observation,modules,sources,inventories)
        exact(producer['refs'],state['inputs']);exact(producer['initial'],state['initial'])
    if phase>=4:
        privateinputs=reader_private_inputs('observation_independent_reader',modules)
        readmeta=modules['consumer_metadata'].expected_consumer_metadata(consumer_role='observation_independent_reader',**consumer_context(modules))
        exact(original['reader_started.json'],dict(schema='PROSPECTIVE_OBSERVATION_CONTINUATION_READER_STARTED_V1',payload_reference=refs['observation_payload.json'],
            receipt_reference=refs['receipt.json'],parent_history_reference=parent['reference'],input_references=state['inputs'],reader_input_references=privateinputs,
            reader_sha256=modules['consumer_registry']['consumer_references']['observation_independent_reader']['sha256'],**readmeta,**flags))
    if phase==5:
        observation.update(audit_reference=refs['independent_readback.json'],audit=original['independent_readback.json'],
            reader_reference=modules['consumer_registry']['consumer_references']['observation_independent_reader'])
        verify_continuation_observation(parent,observation,modules,sources,inventories,current=True)
    state['observed'].update(refs);state['phase']=phase;state['initial_checked']=True
    return phase



def inspect_host_continuation_family(*,implementation_pair_binding_path,implementation_pair_binding_sha256,
        consumer_role_registry_path,consumer_role_registry_sha256,execute=False):
    """Inspect host-selected family declarations and pinned bytes, without parent IO."""
    require(type(execute)is bool,'Explicit bool')
    if not execute:return dict(status='NOT_EXECUTED')
    require(consumer_role_registry_path is not None and consumer_role_registry_sha256 is not None,'Independent continuation registry required')
    host=load_host_family(implementation_pair_binding_path=implementation_pair_binding_path,
        implementation_pair_binding_sha256=implementation_pair_binding_sha256,
        consumer_role_registry_path=consumer_role_registry_path,consumer_role_registry_sha256=consumer_role_registry_sha256)
    modules=host['modules'];sources=deepcopy(host['sources'])
    def final_guard():guard(sources)
    final_guard()
    return dict(status='HOST_CONTINUATION_FAMILY_INSPECTED_NOT_AUTHENTICATED',bound_pair=deepcopy(modules['bound_pair']),
        consumer_registry_view=deepcopy(modules['consumer_registry']),consumer_registry_core_reference=reference(*CONSUMER_ROLE_CORE),
        consumer_metadata_contract_reference=reference(*CONSUMER_METADATA_CORE),sources=deepcopy(sources),final_guard=final_guard,**FLAGS)


def readback(*,registration_path,registration_sha256,history_reference,publication_reference,
        output_directory,implementation_pair_binding_path,implementation_pair_binding_sha256,
        consumer_role_registry_path=None,consumer_role_registry_sha256=None,execute=False):
    require(type(execute)is bool,'Explicit bool')
    if not execute:return dict(status='NOT_EXECUTED')
    registration_ref=reference(registration_path,registration_sha256)
    reference(history_reference['path'],history_reference['sha256']);reference(publication_reference['path'],publication_reference['sha256'])
    host=load_host_family(implementation_pair_binding_path=implementation_pair_binding_path,
        implementation_pair_binding_sha256=implementation_pair_binding_sha256,
        consumer_role_registry_path=consumer_role_registry_path,consumer_role_registry_sha256=consumer_role_registry_sha256)
    regref,bindingref,contract,dependencies,auxiliary,pairdeps,sources,reg,pair,modules=(host[key]for key in
        ('regref','bindingref','contract','dependencies','auxiliary','pairdeps','sources','reg','pair','modules'))
    producer=pair['publisher_reference']
    plan=reg.prepare_compact_history_runtime(registration=decode(consume(registration_ref,sources)),registration_reference=registration_ref,
        runtime_reference=producer,dependency_references=dependencies,research_root=str(RESEARCH))
    output=safe(output_directory);outcanon=reg.canonical_path(str(output));folder=safe(plan['output_directory'])
    require(outcanon.parent==reg.canonical_path(str(RESEARCH))and outcanon!=reg.canonical_path(str(folder))and not output.exists(),'Independent create-only namespace')
    require(output.name.isascii()and output.name[0].islower()and all(c.islower()or c.isdigit()or c=='_'for c in output.name)and 3<=len(output.name)<=120,'Stable readback namespace')
    exact(history_reference['path'],str(folder/'history.json'));exact(publication_reference['path'],str(folder/'publication.json'))
    parent=parent_documents(plan['parent'],sources)
    observation=observation_documents(plan['observation'],sources)
    preflight_original_graph(parent,observation,modules,sources)
    inventories,node_count=walk_parent_graph(parent,modules,sources,auxiliary)
    observation_originals(parent,observation,modules,sources,inventories,current=True)
    current_inventory=current_attempt_inventory(parent,observation,sources,inventories,modules=modules)
    history=modules['core'].reconstruct_actual(parent=parent,observation=observation)
    for path,digest in history['source_hashes'].items():consume(reference(path,digest),sources)
    initial=deepcopy(sources)
    inputs=pair_inputs(parent=plan['parent'],observation=plan['observation'],registration=registration_ref,runtime=producer,
        dependencies=pairdeps['publisher'],auxiliary=auxiliary,registration_core=regref,pair=pair,consumer=modules.get('consumer_registry'))
    meta=compact_metadata(modules_parent_schema(parent),auxiliary,pair=pair,consumer=modules.get('consumer_registry'))
    startpath=folder/'started.json';require(startpath.is_file()and startpath.stat().st_size<=64*1024**2,'Bounded publisher START')
    startref=reference(startpath,sha(startpath.read_bytes()))
    exact(decode(consume(startref,sources)),dict(schema='PROSPECTIVE_OBSERVATION_HISTORY_STARTED_V4',input_references=inputs,source_hashes=initial,**meta,**FLAGS))
    published=deepcopy(initial);published[startref['path']]=startref['sha256']
    require(consume(history_reference,sources)==encode(dict(schema=modules['core'].WRAPPER_SCHEMA,history=history,input_references=inputs,source_hashes=published,**meta,**FLAGS)),'Entire canonical compact wrapper')
    counts=modules['core'].history_counts_v4(history)
    require(consume(publication_reference,sources)==encode(dict(schema=modules['core'].PUBLICATION_SCHEMA,status=modules['core'].PUBLICATION_STATUS,
        history_reference=history_reference,input_references=inputs,counts=counts,source_hashes=published,**meta,**FLAGS)),'Entire canonical compact publication')
    for path in sources:
        item=reg.canonical_path(path);require(item!=outcanon and outcanon not in item.parents,'Readback namespace aliases source')
    def final_guard():
        exact(current_attempt_inventory(parent,observation,{},[],modules=modules),current_inventory,'Semantic current attempt drift')
        for directory,names in inventories:namespace(Path(directory),names,{})
        namespace(folder,('started.json','history.json','publication.json'),{})
        guard(sources)
    final_guard();require(shutil.disk_usage(output.anchor).free>=5*1024**3,'Resource stop before namespace')
    output.mkdir(parents=True,exist_ok=False)
    try:
        save(output/'started.json',dict(schema='PROSPECTIVE_OBSERVATION_HISTORY_READBACK_STARTED_V4',history_reference=history_reference,
            publication_reference=publication_reference,registration_reference=registration_ref,reader_sha256=LOADED_SHA,
            implementation_pair_binding_reference=bindingref,ancestry_contract_reference=contract,
            **({key:meta[key]for key in ('consumer_role_registry_reference','consumer_registry_core_reference','consumer_metadata_contract_reference')}if modules.get('consumer_registry')is not None else{}),**FLAGS))
        report=save(output/'independent_readback.json',dict(schema=modules['core'].READBACK_SCHEMA,status=modules['core'].READBACK_STATUS,
            history_reference=history_reference,publication_reference=publication_reference,input_references=inputs,reader_sha256=LOADED_SHA,
            source_hashes=sources,counts=counts,entire_history_independently_reconstructed=True,publisher_called=False,new_pure_called=False,
            current_live_cache_read_or_reverified=False,shared_upstream_parent_checker_reference=auxiliary['parent_view'],shared_parent_checker_called=True,
            append_algorithm_called=False,reconstruction_scope='HOST_PAIR_BOUND_WHOLE_ACTUAL_V4_AND_GAP_V5_GRAPH_INDEPENDENT_ACTUAL_ARITHMETIC',
            started_reference_observed_not_external_anchor=startref,started_externally_authenticated=False,**meta,**FLAGS))
        final_guard();consume(report,{});namespace(output,('started.json','independent_readback.json'),{})
        return report
    except BaseException as error:
        save(output/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,automatic_retry_allowed=False,**FLAGS));raise


def verify_saved_parent_ancestry(*,parent_references,implementation_pair_binding_path,
        implementation_pair_binding_sha256,consumer_role_registry_path=None,consumer_role_registry_sha256=None,
        consumer_writer_registration_reference=None,consumer_capture_references=None,execute=False):
    """Read-only complete replay for fixed-host consumers; never creates artifacts.

    The caller supplies the binding path AND hash independently of input files.
    The returned guard must run immediately before the consumer publishes its
    own artifact. Shared metadata associations never grant source authenticity.
    """
    require(type(execute)is bool,'Explicit bool')
    if not execute:return dict(status='NOT_EXECUTED')
    host=load_host_family(implementation_pair_binding_path=implementation_pair_binding_path,
        implementation_pair_binding_sha256=implementation_pair_binding_sha256,
        consumer_role_registry_path=consumer_role_registry_path,consumer_role_registry_sha256=consumer_role_registry_sha256)
    bindingref,contract,sources,modules,auxiliary=(host[key]for key in ('bindingref','contract','sources','modules','auxiliary'))
    parent=parent_documents(parent_references,sources);research=Path(RESEARCH)
    reserved=None if consumer_writer_registration_reference is None else prepare_writer_reservation(
        consumer_writer_registration_reference,parent,modules,sources,research)
    selected_capture=None if reserved is None else reserved['plan']['capture']
    if consumer_capture_references is not None:
        consumer_context(modules)
        exact(sorted(consumer_capture_references),sorted(ROLES),'Closed explicit consumer capture anchors')
        for item in consumer_capture_references.values():exact(item,reference(item['path'],item['sha256']))
        if selected_capture is not None:exact(consumer_capture_references,selected_capture,'Consumer capture cannot replace registered writer capture')
        selected_capture=deepcopy(consumer_capture_references)
    preflight_original_graph(parent,None,modules,sources,current_capture_references=selected_capture)
    inventories,node_count=walk_parent_graph(parent,modules,sources,auxiliary)
    current_capture=None
    if selected_capture is not None and reserved is None:
        current_capture=parent_documents(selected_capture,sources)
        capture_inventory(selected_capture,modules['checker'],sources,inventories,modules)
        cap=current_capture['document'];view=modules['view'].inspect_parent_history_v5(parent)
        exact(cap['parent_references'],parent_references,'Explicit current capture has this verified parent')
        artifacts=cap['captured_artifacts']
        reconstructed=modules['checker'].reconstruct_plan(parent=parent,
            source_bytes={ticker:consume(artifacts[ticker],sources)for ticker in ('QQQ','SPY')},
            source_references={ticker:artifacts[ticker]for ticker in ('QQQ','SPY')},
            accounted_baseline_bytes={ticker:consume(view['accounted_baseline_references'][ticker],sources)for ticker in ('QQQ','SPY')},
            actual_baseline_bytes={ticker:consume(view['baseline_references'][ticker],sources)for ticker in ('QQQ','SPY')},
            capture_started_at=cap['capture_started_at'],capture_completed_at=cap['capture_completed_at'],
            tzif_bytes=consume(artifacts['tzif'],sources),tzif_reference=artifacts['tzif'],parent_checker=modules['view'],csv_rows=modules['csv'].csv_rows)
        exact(cap['plan'],reconstructed,'Entire explicit current capture plan independently reconstructed')
    if reserved is not None:
        initialize_writer_reservation(reserved,parent,modules,sources,inventories)
        verify_reserved_writer_phase(reserved,parent,modules,sources,inventories)
    current_inventory=current_attempt_inventory(parent,None,sources,inventories,research_root=research,modules=modules,reserved_writer=reserved)
    def final_guard():
        if reserved is not None:verify_reserved_writer_phase(reserved,parent,modules,sources,inventories)
        exact(current_attempt_inventory(parent,None,{},[],research_root=research,modules=modules,reserved_writer=reserved),current_inventory,'Semantic current attempt drift')
        for directory,names in inventories:namespace(Path(directory),names,{})
        guard(sources)
    final_guard()
    return dict(status='READ_ONLY_WHOLE_ANCESTRY_RECONSTRUCTION_PASS',parent_references=deepcopy(parent_references),
        implementation_pair_binding_reference=bindingref,ancestry_contract_reference=contract,
        parent_node_count=node_count,sources=deepcopy(sources),inventories=deepcopy(inventories),
        bound_pair=deepcopy(modules['bound_pair']),consumer_registry_view=deepcopy(modules.get('consumer_registry')),
        consumer_registry_core_reference=reference(*CONSUMER_ROLE_CORE),consumer_metadata_contract_reference=reference(*CONSUMER_METADATA_CORE),
        parent_envelope=deepcopy(parent),parent_view=deepcopy(modules['view'].inspect_parent_history_v5(parent)),
        verified_writer_registration_reference=None if reserved is None else deepcopy(reserved['registration_reference']),
        capture_envelope=deepcopy(current_capture)if reserved is None else deepcopy(reserved['capture']),
        capture_plan=(None if current_capture is None else deepcopy(current_capture['document']['plan']))if reserved is None else deepcopy(reserved['capture']['document']['plan']),
        writer_prior_attempt_inventory=None if reserved is None else deepcopy(reserved['inventory']),
        writer_input_sources=None if reserved is None else deepcopy(reserved['initial']),
        final_guard=final_guard,entire_history_independently_reconstructed=True,publisher_called=False,
        new_pure_called=False,current_live_cache_read_or_reverified=False,**FLAGS)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration-path','registration-sha256','history-path','history-sha256','publication-path','publication-sha256','output-directory','implementation-pair-binding-path','implementation-pair-binding-sha256'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--consumer-role-registry-path');parser.add_argument('--consumer-role-registry-sha256')
    parser.add_argument('--execute',action='store_true');args=vars(parser.parse_args())
    args['history_reference']=reference(args.pop('history_path'),args.pop('history_sha256'))
    args['publication_reference']=reference(args.pop('publication_path'),args.pop('publication_sha256'))
    print(json.dumps(readback(**args)))
