"""Create-only compact V4 publisher driven by an immutable external registration.

No real observation is created here. An independently read observation is required.
The host selects an immutable implementation pair independently of daily input.
Pair and ancestry kernels remain pending until independently reviewed and bound.
"""
import argparse
from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
import base64
from copy import deepcopy
import csv
from decimal import Decimal
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
LEGACY_ANCESTRY_CONTRACT=(ROOT/'backtest/ndx_compact_ancestry_contract_research_v1.py','1f50f4d5a893c163149bf69593880f73a1387293ee04b2ab9c0fcbb58090fc5e')
CONSUMER_REGISTRY_CORE=(ROOT/'backtest/ndx_continuation_consumer_role_registry_research_v1.py','184479c5e0e6412265e00cc875af1f7902e4f500dc984ca2aaaf3251bc8c433b')
CONSUMER_METADATA_CONTRACT=(ROOT/'backtest/ndx_continuation_consumer_metadata_research_v1.py','b0d16b1b364d2c32e55d826c1f9d63dfffeb27df7bcabfe972efd029e8e2fdeb')
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


def immutable_regular_source(path):
    path=safe(path)
    require(path.is_file()and path.stat().st_size<=64*1024**2 and not(path.parent/'failure.json').exists(),'Bounded immutable nonfailed source')
    forbidden={(ROOT/'data/cache'/f'{ticker}.csv').resolve()for ticker in ('QQQ','SPY')}|{value.resolve()for value in CURRENT.values()}
    require(path.resolve()not in forbidden,'Mutable diagnostic cache forbidden before any source byte read')
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
        immutable_regular_source(item)
        consume(reference(item,sha(item.read_bytes())),sources)


def load_envelope(refs,roles,sources):
    result=deepcopy(refs)
    for key,role in roles:
        result[key]=decode(consume(refs[role],sources))
        claims=result[key]['source_hashes'];require(type(claims)is dict,'Complete source claim map')
        # Claim maps are declarations, never an IO discovery queue.
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
        audit=decode(consume(auditref,{}));names=observation_namespace_names(audit)
        local={};namespace(folder,names,local)
        audit=decode(consume(auditref,local));start=reference(folder/'started.json',local[str(folder/'started.json')])
        exact(audit['source_hashes'].get(start['path']),start['sha256'],'Parent-bound observed START')
        exact(reference(folder/'observation_payload.json',local[str(folder/'observation_payload.json')]),payload)
        exact(reference(folder/'receipt.json',local[str(folder/'receipt.json')]),receipt)
        records={'started.json':start,'observation_payload.json':payload,'receipt.json':receipt}
        if 'reader_started.json'in names:
            own=reference(folder/'reader_started.json',local[str(folder/'reader_started.json')]);exact(audit['source_hashes'].get(own['path']),own['sha256'],'Inherited reader START');records['reader_started.json']=own
        found[payload['path']]=records
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
    for path,digest in audited.items():consume(reference(path,digest),sources)


def parent_inventory(refs,checker,sources,inventories):
    checker.parent_inventories(refs,sources)
    folder=Path(refs['reference']['path']).parent;audit=Path(refs['readback_reference']['path']).parent
    for directory in {folder,audit}:
        pin_namespace(directory,tuple(path.name for path in directory.iterdir()),sources,inventories)


def compact_metadata(parent_schema,auxiliary,*,pair=None,consumer_registry_view=None):
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
    if consumer_registry_view is not None:metadata.update(compact_consumer_provenance(consumer_registry_view))
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
            auxiliary=auxiliary,registration_core=reference(*REGISTRATION_CORE),pair=pair,consumer_registry_view=modules.get('consumer_registry_view')))
        deps=inputs['registration_dependency_references']
        meta=compact_metadata(modules_parent_schema(prior),auxiliary,pair=pair,consumer_registry_view=modules.get('consumer_registry_view'))
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
    if not legacy and modules.get('consumer_registry_view')is not None:pairmeta.update(compact_consumer_provenance(modules['consumer_registry_view']))
    exact(auditstart,dict(schema='PROSPECTIVE_OBSERVATION_HISTORY_READBACK_STARTED_V4',history_reference=parent['reference'],publication_reference=parent['publication_reference'],
        registration_reference=inputs['registration'],reader_sha256=parent['reader_reference']['sha256'],**pairmeta,**FLAGS))


def modules_parent_schema(parent):return parent['document']['history']['schema']


def walk_parent_graph(parent,modules,sources,auxiliary):
    """One global visited/depth bound spans actual-V4 and gap-V5 original edges."""
    checker=modules['checker'];inventories=[];visited=set();current=parent;envelopes={}
    def register(envelope):
        modules['ancestry'].classify_parent_edge(envelope,bound_pair=modules['bound_pair'],legacy_implementations=modules['host_legacy'],**modules.get('ancestry_arguments',{}))
        envelopes[(envelope['reference']['path'],envelope['reference']['sha256'])]=envelope
    while True:
        key=(current['reference']['path'],current['reference']['sha256'])
        require(key not in visited and len(visited)<MAX_PARENT_DEPTH,'Global parent cycle/depth')
        register(current)
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
                    register(original)
                    if original['document']['history']['schema']==modules['view'].GAP_SCHEMA:verify_gap_outer(original,modules,sources)
            current=terminal
            # Terminal V4 was registered by the gap checker; process its outgoing actual edge below.
            view=modules['view'].inspect_parent_history_v5(current);schema=view['parent_schema']
        else:
            visited.add(key);parent_inventory({role:current[role]for role in ROLES},checker,sources,inventories)
        verify_baselines(view,sources)
        for entry in view['observations']:
            pin_namespace(Path(entry['payload_reference']['path']).parent,('started.json','observation_payload.json','receipt.json','independent_readback.json'),sources,inventories)
        if schema=='PROSPECTIVE_GAP_EXTENSION_HISTORY_V3':
            register(current)
            graph=modules['ancestry'].inspect_ancestry_graph({role:parent[role]for role in ROLES},envelopes,bound_pair=modules['bound_pair'],legacy_implementations=modules['host_legacy'],**modules.get('ancestry_arguments',{}))
            exact(graph['parent_node_count'],len(visited),'Graph and replay node count')
            return inventories,len(visited)
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
    for path,digest in audited.items():consume(reference(path,digest),sources)


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
        for name in ('started.json','observation_payload.json','receipt.json','reader_started.json','failure.json'):
            path=safe(folder/name)
            if not path.exists():continue
            require(path.is_file()and path.stat().st_size<=64*1024**2,'Bounded semantic attempt file')
            raw=path.read_bytes();records[name]=(decode(raw),reference(path,sha(raw)))
        get=lambda name:records.get(name,({},{}))[0]
        semantic=(get('started.json').get('schema','').startswith('PROSPECTIVE_OBSERVATION_WRITER_STARTED_')or get('observation_payload.json').get('schema')=='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1'or get('receipt.json').get('schema')=='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1'or get('reader_started.json').get('schema')=='PROSPECTIVE_OBSERVATION_CONTINUATION_READER_STARTED_V1'or get('failure.json').get('consumer_role')in ('observation_writer','observation_independent_reader')or get('failure.json').get('status')=='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY')
        if not semantic:require(folder not in external,'Explicit inherited attempt recognizable');continue
        require({'started.json','observation_payload.json','receipt.json'}<=set(records)<= {'started.json','observation_payload.json','receipt.json','reader_started.json'},'No partial or failed semantic attempt')
        payload=records['observation_payload.json'][1];require(payload['path']in allowed and payload['path']not in found,'Unregistered or duplicate semantic observation')
        expected=allowed[payload['path']];exact(payload,expected['payload_reference']);exact(records['receipt.json'][1],expected['receipt_reference'])
        audit=decode(consume(expected['audit_reference'],sources));names=observation_namespace_names(audit)
        require(set(records)==({'started.json','observation_payload.json','receipt.json'}|({'reader_started.json'}if 'reader_started.json'in names else set())),'Closed observed attempt record roles')
        pin_namespace(folder,names,sources,inventories)
        if 'reader_started.json'in names:
            ownpath=folder/'reader_started.json';ownref=reference(ownpath,sha(ownpath.read_bytes()));exact(audit['source_hashes'].get(ownref['path']),ownref['sha256'],'Current reader START');records['reader_started.json']=(decode(consume(ownref,sources)),ownref)
        start=records['started.json'][1]
        exact(audit['source_hashes'].get(start['path']),start['sha256'],'Whole semantic attempt START')
        found[payload['path']]={name:item for name,(_,item)in records.items()}
    exact(sorted(found),sorted(allowed),'All current bound actual attempts');return found


def preflight_original_graph(parent,observation,modules,sources):
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
    def anchored_namespace(refs,history=True):
        for item in refs.values():permit(item)
        for role in ('reference','readback_reference') if history else ('payload_reference',):
            folder=safe(Path(refs[role]['path']).parent)
            path=folder/'started.json'
            immutable_regular_source(path)
            permit(reference(path,sha(path.read_bytes())))
    current=parent;visited=set()
    while True:
        key=(current['reference']['path'],current['reference']['sha256'])
        require(key not in visited and len(visited)<MAX_PARENT_DEPTH,'Global preflight cycle/depth')
        visited.add(key)
        edge=modules['ancestry'].classify_parent_edge(current,bound_pair=modules['bound_pair'],legacy_implementations=modules['host_legacy'],**modules.get('ancestry_arguments',{}))
        envelopes[key]=current
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
    observations[observation['payload_reference']['path']]={role:observation[role]for role in OBSERVATION_ROLES}
    for refs in observations.values():
        continuation_reader=None if modules.get('consumer_registry_view')is None else modules['consumer_registry_view']['consumer_references']['observation_independent_reader']
        require(refs['reader_reference'] in [reference(*AUXILIARIES[key])for key in ('observation_reader','legacy_observer_v3','legacy_observer_v4')]+([continuation_reader]if continuation_reader else []),
            'Preflight known observation reader')
        original=observation_documents(refs,sources)
        require(original['audit'].get('schema')=='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3'and original['audit'].get('status')=='PASS','Preflight observation format')
        if refs['reader_reference']==continuation_reader:
            is_continuation(original['payload'],'observation_writer',modules);is_continuation(original['receipt'],'observation_writer',modules);is_continuation(original['audit'],'observation_independent_reader',modules)
            continuation_inputs(original['payload']['input_references'],'observation_writer',modules,{'parent','capture','registration','runtime','dependencies','auxiliary_dependencies','registration_core','reference_core'})
        else:
            require(not is_continuation(original['payload'],'observation_writer',modules),'Legacy observation cannot select a continuation writer')
        anchored_namespace(refs,False);observation_roles(original)
        if refs['reader_reference']==continuation_reader:
            own=immutable_regular_source(Path(refs['payload_reference']['path']).parent/'reader_started.json');permit(reference(own,sha(own.read_bytes())))
        captures[original['payload']['input_references']['capture']['reference']['path']]=original['payload']['input_references']['capture']
    for refs in captures.values():
        original=parent_documents(refs,sources);d=original['document'];inputs=d.get('input_references',{})
        schema=d.get('schema')
        if is_continuation(d,'capture_publisher',modules):
            require(schema=='SOURCE_BOUND_FORWARD_CAPTURE_V5','Continuation capture genuine schema')
            expected_runtime=modules['consumer_registry_view']['consumer_references']['capture_publisher']
            expected_reader=modules['consumer_registry_view']['consumer_references']['capture_independent_reader']
            continuation_inputs(inputs,'capture_publisher',modules,{'dependencies','registration','runtime','registration_core','reference_core','tzif','prefix_core','gap_core'})
            is_continuation(original['publication'],'capture_publisher',modules);is_continuation(original['readback'],'capture_independent_reader',modules)
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
    for item in (reference(*LEGACY_ANCESTRY_CONTRACT),reference(*CONSUMER_REGISTRY_CORE),reference(*CONSUMER_METADATA_CONTRACT)):permit(item)
    if modules.get('consumer_registry_view')is not None:
        permit(modules['consumer_registry_view']['registry_reference'])
        for item in modules['consumer_registry_view']['consumer_references'].values():permit(item)
        for role in ('capture_independent_reader','observation_independent_reader','gap_independent_reader'):
            def permit_constructed(value):
                if type(value)is dict:
                    if set(value)=={'path','sha256'}:permit(value)
                    else:
                        for child in value.values():permit_constructed(child)
            permit_constructed(reader_private_inputs(role,modules))
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
    for original in [*envelopes.values(),observation]:check_claims(original)
    for refs in observations.values():check_claims(observation_documents(refs,sources))
    for refs in captures.values():check_claims(parent_documents(refs,sources))
    modules['permitted_sources']=allowed
    modules['classified_envelopes']=envelopes
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
        reference(*PAIR_BINDING_CORE),reference(*REGISTRATION_CORE),reference(*LEGACY_ANCESTRY_CONTRACT),reference(*CONSUMER_REGISTRY_CORE),reference(*CONSUMER_METADATA_CONTRACT),registration]
    if modules.get('consumer_registry_view')is not None:fixed.extend([modules['consumer_registry_view']['registry_reference'],*modules['consumer_registry_view']['consumer_references'].values()])
    fixed.extend(reference(*value)for group in (DEPENDENCIES,AUXILIARIES,READER_ALGORITHMS)for value in group.values())
    for item in fixed:consume(item,initial)
    inventories,_=walk_parent_graph(prior,modules,initial,auxiliary)
    observation_originals(prior,observation,modules,initial,inventories,current=True)
    # Historical input reconstruction must not scan later legitimate attempts.
    # Bound prior/observation namespaces are already included by the replay.
    result=modules['core'].append_observation_history(parent=prior,observation=observation)
    for path,digest in result['source_hashes'].items():
        require(modules['permitted_sources'].get(path)==digest,'Derived history source requires original role')
        consume(reference(path,digest),initial)
    return initial


def publisher_dependencies():
    return {**{key:reference(*value)for key,value in DEPENDENCIES.items()},
        **{key:reference(*AUXILIARIES[key])for key in ('parent_view','legacy_view','capture_checker','observation_reader','csv_reader','independent_prefix')}}


def pair_inputs(*,parent,observation,registration,runtime,dependencies,auxiliary,registration_core,pair,consumer_registry_view=None):
    result=dict(parent=deepcopy(parent),observation=deepcopy(observation),registration=registration,runtime=runtime,
        dependencies=dependencies,registration_dependency_references={key:dependencies[key]for key in ('history_core','compact_helpers')},
        auxiliary_dependencies=auxiliary,registration_core=registration_core,
        implementation_pair_binding=pair['binding_reference'],ancestry_contract=pair['contract_reference'],pair_binding_core=reference(*PAIR_BINDING_CORE))
    if consumer_registry_view is not None:result.update(consumer_role_registry=consumer_registry_view['registry_reference'],consumer_registry_core=reference(*CONSUMER_REGISTRY_CORE),consumer_metadata_contract=reference(*CONSUMER_METADATA_CONTRACT))
    return result


def host_legacy_implementations():
    return [dict(parent_schema='PROSPECTIVE_GAP_EXTENSION_HISTORY_V3',input_role='pure',implementation_reference=reference(*TERMINAL_PURE),
            reader_reference=reference(*TERMINAL_READER),terminal_reference=reference(*TERMINAL_REFERENCE)),
        dict(parent_schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V4',input_role='runtime',implementation_reference=reference(*AUXILIARIES['legacy_compact_publisher']),reader_reference=reference(*AUXILIARIES['legacy_compact_reader'])),
        dict(parent_schema='PROSPECTIVE_GAP_EXTENSION_HISTORY_V5',input_role='runtime',implementation_reference=reference(*AUXILIARIES['gap_publisher']),reader_reference=reference(*AUXILIARIES['gap_reader']))]


# Continuation roles are selected only through an independently bound host C.
# No artifact field or source claim can extend this closed dispatch table.
def observation_namespace_names(audit):
    names=('started.json','observation_payload.json','receipt.json','independent_readback.json')
    if 'consumer_role'in audit:
        exact(audit['consumer_role'],'observation_independent_reader');exact(audit['continuation_adapter_schema'],'CONTINUATION_OBSERVATION_INDEPENDENT_READER_V1')
        names+=('reader_started.json',)
    return names


def compact_consumer_provenance(view):
    return dict(consumer_role_registry_reference=view['registry_reference'],
        consumer_registry_core_reference=reference(*CONSUMER_REGISTRY_CORE),
        consumer_metadata_contract_reference=reference(*CONSUMER_METADATA_CONTRACT))


def consumer_context(modules):
    require(modules.get('consumer_registry_view')is not None,'Independent host C required')
    return dict(bound_pair=modules['bound_pair'],consumer_registry_view=modules['consumer_registry_view'],
        consumer_registry_core_reference=reference(*CONSUMER_REGISTRY_CORE),metadata_contract_reference=reference(*CONSUMER_METADATA_CONTRACT))


def ancestry_arguments(modules):
    if modules.get('consumer_registry_view')is None:return {}
    return dict(consumer_registry_view=modules['consumer_registry_view'],
        consumer_registry_core_reference=reference(*CONSUMER_REGISTRY_CORE),metadata_contract_reference=reference(*CONSUMER_METADATA_CONTRACT),
        registered_gap_dependency_references=business_dependencies('gap_publisher',modules))


def business_dependencies(role,modules):
    if role.startswith('capture_'):
        return {key:reference(ROOT/path,digest)for key,(path,digest)in modules['checker'].DEPENDENCIES.items()}
    if role.startswith('observation_'):
        return {key:reference(*value)for key,value in modules['observer'].DEPENDENCIES.items()}
    require(role.startswith('gap_'),'Closed business role')
    result=business_dependencies('capture_publisher',modules);result.pop('capture_core')
    result.update(gap_core=reference(*modules['checker'].GAP_CORE),prefix_core=reference(*modules['checker'].PREFIX_CORE),capture_checker=reference(*AUXILIARIES['capture_checker']))
    return result


def reader_private_inputs(role,modules):
    context=consumer_context(modules);registry=context['consumer_registry_view'];pair=context['bound_pair']
    deps=business_dependencies(role,modules);aux={};independent={}
    if role=='capture_independent_reader':
        independent=dict(capture_plan_reconstructor=reference(*AUXILIARIES['capture_checker']),csv_reader=reference(*AUXILIARIES['csv_reader']))
        reg=reference(*modules['checker'].REGISTRATION_CORE)
    elif role=='observation_independent_reader':
        aux={key:reference(*value)for key,value in modules['observer'].AUXILIARY_DEPENDENCIES.items()};reg=reference(*modules['observer'].REGISTRATION_CORE)
    else:
        require(role=='gap_independent_reader','Closed private reader role');reg=reference(*AUXILIARIES['gap_registration'])
        independent=dict(independent_gap_reconstructor=reference(*READER_ALGORITHMS['independent_gap_reconstructor']),
            independent_prefix_reconstructor=reference(*AUXILIARIES['independent_prefix']),csv_reader=reference(*AUXILIARIES['csv_reader']))
    return dict(runtime=registry['consumer_references'][role],dependencies=deps,auxiliary_dependencies=aux,independent_dependencies=independent,
        registration_core=reg,reference_core=reference(*REGISTRATION_CORE),pair_binding_core=reference(*PAIR_BINDING_CORE),
        implementation_pair_binding=pair['binding_reference'],consumer_role_registry=registry['registry_reference'],ancestry_contract=pair['contract_reference'],
        shared_ancestry_verifier=pair['independent_reader_reference'],consumer_registry_core=reference(*CONSUMER_REGISTRY_CORE),consumer_metadata_contract=reference(*CONSUMER_METADATA_CONTRACT))


def is_continuation(value,role,modules):
    require(type(value)is dict,'Original metadata object')
    keys=set(('continuation_adapter_schema','consumer_role','implementation_pair_binding_reference','consumer_role_registry_reference','ancestry_contract_reference','shared_ancestry_verifier_reference','consumer_registry_core_reference','consumer_metadata_contract_reference'))
    input_markers={'consumer_role_registry','shared_ancestry_verifier','consumer_registry_core','consumer_metadata_contract','registration_dependency_references'}
    inputs=value.get('input_references',{})
    has=bool(keys&set(value))or bool(input_markers&set(inputs))
    # A pair-bound compact edge has its own distinct provenance contract.
    if value.get('compact_adapter_schema')==ADAPTER:return False
    if not has:return False
    modules['metadata_core'].inspect_consumer_metadata(value,expected_role=role,**consumer_context(modules))
    return True


def continuation_inputs(inputs,role,modules,basekeys):
    expected=modules['metadata_core'].continuation_input_references(registered_dependency_references=business_dependencies(role,modules),consumer_role=role,**consumer_context(modules))
    require(set(inputs)==set(basekeys)|set(expected),'Closed continuation public inputs')
    modules['metadata_core'].inspect_producer_input_references(inputs,consumer_role=role,registered_dependency_references=business_dependencies(role,modules),**consumer_context(modules))
    return expected


def add_references(value,sources):
    # Only code-constructed closed maps may reach this helper. Never pass input
    # metadata or a source claim map here to discover permission to perform IO.
    if type(value)is dict:
        if set(value)=={'path','sha256'}:consume(value,sources)
        else:
            for child in value.values():add_references(child,sources)


def family_seed_sources(modules):
    pair=modules['bound_pair'];result={}
    for item in (pair['publisher_reference'],pair['independent_reader_reference'],pair['binding_reference'],pair['contract_reference'],
            reference(*PAIR_BINDING_CORE),reference(*REGISTRATION_CORE),reference(*LEGACY_ANCESTRY_CONTRACT),reference(*CONSUMER_REGISTRY_CORE),reference(*CONSUMER_METADATA_CONTRACT)):
        consume(item,result)
    for group in (DEPENDENCIES,AUXILIARIES,READER_ALGORITHMS):
        for item in group.values():consume(reference(*item),result)
    if modules.get('consumer_registry_view')is not None:
        consume(modules['consumer_registry_view']['registry_reference'],result)
        for item in modules['consumer_registry_view']['consumer_references'].values():consume(item,result)
    return result


def verified_parent_sources(parent,modules):
    identity=(parent['reference']['path'],parent['reference']['sha256']);cache=modules.setdefault('verified_parent_source_cache',{})
    if identity not in cache:
        result=family_seed_sources(modules);inventories,_=walk_parent_graph(parent,modules,result,{key:reference(*value)for key,value in AUXILIARIES.items()})
        cache[identity]=(deepcopy(result),deepcopy(inventories))
    return deepcopy(cache[identity])


def consumer_initial_sources(parent,inputs,role,modules,extra_capture=None):
    result,inventories=verified_parent_sources(parent,modules)
    constructed=dict(runtime=modules['consumer_registry_view']['consumer_references'][role],dependencies=business_dependencies(role,modules),
        registration_core=inputs['registration_core'],reference_core=reference(*REGISTRATION_CORE),registration=inputs['registration'],
        **modules['metadata_core'].continuation_input_references(registered_dependency_references=business_dependencies(role,modules),consumer_role=role,**consumer_context(modules)))
    add_references(constructed,result)
    if role=='capture_publisher':
        for item in (reference(*modules['checker'].PREFIX_CORE),reference(*modules['checker'].GAP_CORE),modules['view'].inspect_parent_history_v5(parent)['tzif_reference']):consume(item,result)
    if role=='observation_writer':add_references({key:reference(*value)for key,value in modules['observer'].AUXILIARY_DEPENDENCIES.items()},result)
    if role=='gap_publisher':consume(reference(*AUXILIARIES['csv_reader']),result)
    if extra_capture is not None:capture_inventory(extra_capture,modules['checker'],result,inventories,modules)
    return result,inventories


def observed_reference(path,sources):
    path=immutable_regular_source(path)
    item=reference(path,sha(path.read_bytes()));return item,decode(consume(item,sources))


def reader_start_and_sources(envelope,inputs,role,flags,modules,producer_sources,output_refs,registration_ref,producer_start):
    meta=modules['metadata_core'].expected_consumer_metadata(consumer_role=role,**consumer_context(modules));private_inputs=reader_private_inputs(role,modules)
    folder=Path(envelope['audit_reference'if role=='observation_independent_reader'else 'readback_reference']['path']).parent
    name='reader_started.json'if role=='observation_independent_reader'else 'started.json'
    ownref,own=observed_reference(folder/name,{})
    schemas=dict(capture_independent_reader='FORWARD_CAPTURE_READBACK_STARTED_V5',gap_independent_reader='PROSPECTIVE_GAP_HISTORY_READBACK_STARTED_V5',observation_independent_reader='PROSPECTIVE_OBSERVATION_CONTINUATION_READER_STARTED_V1')
    expected=dict(schema=schemas[role],**output_refs,reader_sha256=private_inputs['runtime']['sha256'],input_references=inputs,reader_input_references=private_inputs,**meta,**flags)
    if registration_ref is not None:expected['registration_reference']=registration_ref
    exact(own,expected,'Whole continuation reader START')
    audited=deepcopy(producer_sources);add_references(private_inputs,audited)
    for item in (*output_refs.values(),producer_start,ownref):consume(item,audited)
    return dict(meta=meta,private_inputs=private_inputs,started_reference=ownref,source_hashes=audited)


def continuation_reader_fields(result):
    return dict(reader_input_references=result['private_inputs'],**result['meta'],
        reader_started_reference_observed_not_external_anchor=result['started_reference'],reader_started_externally_authenticated=False)


_legacy_capture_inventory=capture_inventory
_legacy_observation_originals=observation_originals
_legacy_verify_gap_outer=verify_gap_outer
_legacy_walk_parent_graph=walk_parent_graph


def capture_inventory(refs,checker,sources,inventories,modules):
    envelope=parent_documents(refs,sources);d,p,a=(envelope[key]for key in ('document','publication','readback'))
    if not is_continuation(d,'capture_publisher',modules):
        require(not is_continuation(p,'capture_publisher',modules)and not is_continuation(a,'capture_independent_reader',modules),'No mixed legacy capture metadata')
        return _legacy_capture_inventory(refs,checker,sources,inventories,modules)
    context=consumer_context(modules);cview=context['consumer_registry_view'];inputs=d['input_references']
    exact(refs['reader_reference'],cview['consumer_references']['capture_independent_reader'])
    producer=cview['consumer_references']['capture_publisher'];deps=business_dependencies('capture_publisher',modules)
    extension=continuation_inputs(inputs,'capture_publisher',modules,{'dependencies','registration','runtime','registration_core','reference_core','tzif','prefix_core','gap_core'})
    exact(inputs['registration_core'],reference(*checker.REGISTRATION_CORE));exact(inputs['reference_core'],reference(*REGISTRATION_CORE))
    exact(inputs['prefix_core'],reference(*checker.PREFIX_CORE));exact(inputs['gap_core'],reference(*checker.GAP_CORE))
    is_continuation(p,'capture_publisher',modules);is_continuation(a,'capture_independent_reader',modules)
    folder=Path(refs['reference']['path']).parent;af=Path(refs['readback_reference']['path']).parent
    for role,name in [('reference','capture.json'),('publication_reference','publication.json')]:exact(refs[role]['path'],str(folder/name))
    exact(refs['readback_reference']['path'],str(af/'independent_readback.json'))
    pin_namespace(folder,modules['metadata_core'].NAMESPACE_FILES['capture_publisher'],sources,inventories)
    pin_namespace(af,modules['metadata_core'].NAMESPACE_FILES['capture_independent_reader'],sources,inventories)
    parents=d['parent_references'];prior=checker.load_parent_envelope(parents,sources);view=modules['view'].inspect_parent_history_v5(prior)
    exact(inputs['tzif'],view['tzif_reference']);initial,ancestor_inventory=consumer_initial_sources(prior,inputs,'capture_publisher',modules)
    inventories.extend(ancestor_inventory)
    reg=private(inputs['registration_core']['path'],consume(inputs['registration_core'],initial),inputs['registration_core']['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',modules['references'])])
    registered=reg.prepare_forward_capture_runtime(registration=decode(consume(inputs['registration'],initial)),registration_reference=inputs['registration'],runtime_reference=producer,dependency_references=deps,research_root=str(folder.parent))
    exact(registered['parent'],parents);exact(registered['output_directory'],str(folder))
    artifacts=d['captured_artifacts'];require(set(artifacts)=={'QQQ','SPY','tzif'},'Closed captured artifact roles')
    for key,item in artifacts.items():exact(item['path'],str(folder/('New_York.tzif'if key=='tzif'else key+'.csv')))
    rows={t:consume(artifacts[t],sources)for t in ('QQQ','SPY')}
    plan=checker.reconstruct_plan(parent=prior,source_bytes=rows,source_references={t:artifacts[t]for t in ('QQQ','SPY')},
        accounted_baseline_bytes={t:consume(view['accounted_baseline_references'][t],initial)for t in ('QQQ','SPY')},actual_baseline_bytes={t:consume(view['baseline_references'][t],initial)for t in ('QQQ','SPY')},
        capture_started_at=d['capture_started_at'],capture_completed_at=d['capture_completed_at'],tzif_bytes=consume(artifacts['tzif'],sources),tzif_reference=artifacts['tzif'],parent_checker=modules['view'],csv_rows=modules['csv'].csv_rows)
    flags=dict.fromkeys(checker.FALSE_FIELDS,False);meta=modules['metadata_core'].expected_consumer_metadata(consumer_role='capture_publisher',**context)
    cache=d['current_cache_references'];require(set(cache)=={'QQQ','SPY'},'Closed diagnostic cache roles')
    for ticker,item in cache.items():
        require(set(item)=={'path','sha256'},'Closed diagnostic reference');reference(item['path'],item['sha256']);safe(item['path']);exact(item['sha256'],artifacts[ticker]['sha256'])
    published=deepcopy(initial)
    for item in artifacts.values():consume(item,published)
    startref,start=observed_reference(folder/'started.json',sources)
    exact(start,dict(schema='FORWARD_CAPTURE_STARTED_V5',parent_references=parents,input_references=inputs,source_hashes=initial,retry_allowed=False,**meta,**flags))
    exact(d,dict(schema='SOURCE_BOUND_FORWARD_CAPTURE_V5',plan=plan,parent_references=parents,input_references=inputs,captured_artifacts=artifacts,current_cache_references=cache,
        current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',capture_started_at=d['capture_started_at'],capture_completed_at=d['capture_completed_at'],
        clock_captured_by_runner=True,external_clock_attestation_verified=False,quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',source_hashes=published,**meta,**flags),'Whole continuation capture wrapper')
    exact(p,dict(schema='FORWARD_CAPTURE_PUBLICATION_V5',status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION',capture_reference=refs['reference'],source_hashes=published,**meta,**flags))
    read=reader_start_and_sources(envelope,inputs,'capture_independent_reader',flags,modules,published,
        dict(capture_reference=refs['reference'],publication_reference=refs['publication_reference']),inputs['registration'],startref)
    counts=dict(status=plan['status'],parent_typed_row_count=len(plan['known_typed_rows']),parent_actual_observation_count=len(plan['observations']),parent_observed_count=sum(row['kind']!='MISSED_OBSERVATION'for row in plan['known_typed_rows']),parent_gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in plan['known_typed_rows']),candidate_session=plan['candidate_session'],diagnostic_count=len(plan['diagnostics']),snapshot_counts={t:plan['source_evidence'][t]['original_row_count']for t in ('QQQ','SPY')})
    exact(a,dict(schema='FORWARD_CAPTURE_INDEPENDENT_READBACK_V5',status='PURE_FORWARD_CAPTURE_READBACK_PASS',capture_reference=refs['reference'],publication_reference=refs['publication_reference'],parent_references=parents,input_references=inputs,
        producer_reference=producer,reader_sha256=refs['reader_reference']['sha256'],source_hashes=read['source_hashes'],counts=counts,entire_plan_independently_reconstructed=True,snapshot_bytes_verified=True,producer_called=False,capture_core_called=False,current_live_cache_read_or_reverified=False,external_clock_attestation_verified=False,
        shared_upstream_parent_checker_reference=deps['parent_view'],shared_parent_checker_called=True,reconstruction_scope='INDEPENDENT_CAPTURE_PLAN_FROM_BOUND_PARENT_SHARED_PARENT_INSPECTOR_NOT_SOURCE_OR_CLOCK_AUTHENTICATION',
        started_reference_observed_not_external_anchor=startref,started_externally_authenticated=False,csv_reader_reference=reference(*AUXILIARIES['csv_reader']),csv_resource_semantics='MAX_8000000_SOURCE_BYTES_MAX_20000_DATA_ROWS_BLANK_RECORDS_EXCLUDED_NO_EXTRA_PHYSICAL_LINE_LIMIT',shared_legacy_parent_checker_reference=deps['legacy_view'],prefix_core_called_for_parent_evidence_only=False,gap_core_called=False,parent_chain_and_original_prefix_bytes_reverified=True,actual_parent_schema=view['parent_schema'],**continuation_reader_fields(read),**flags),'Whole continuation capture independent report')
    for path,digest in read['source_hashes'].items():consume(reference(path,digest),sources)
    return envelope


def replay_gap_history(parent,prior,modules,sources,inventories):
    h=parent['document']['history'];view=modules['view'].inspect_parent_history_v5(prior)
    capture_inventory(h['capture_references'],modules['checker'],sources,inventories,modules)
    capture=parent_documents(h['capture_references'],sources)['document']
    exact(capture['parent_references'],h['parent_references']);exact(capture['capture_started_at'],h['capture_started_at']);exact(capture['capture_completed_at'],h['capture_completed_at'])
    exact({t:capture['captured_artifacts'][t]for t in ('QQQ','SPY')},h['full_capture_source_references']);exact(capture['captured_artifacts']['tzif'],h['tzif_reference'])
    raw={t:consume(h['full_capture_source_references'][t],sources)for t in ('QQQ','SPY')}
    expected=modules['independent_gap'].reconstruct_gap_history(parent=prior,capture_references=h['capture_references'],source_bytes=raw,source_references=h['full_capture_source_references'],
        accounted_baseline_bytes={t:consume(view['accounted_baseline_references'][t],sources)for t in ('QQQ','SPY')},actual_baseline_bytes={t:consume(view['baseline_references'][t],sources)for t in ('QQQ','SPY')},
        prefix_references=h['accounted_prefix_references'],prefix_evidence_references=h['accounted_prefix_evidence_references'],capture_started_at=h['capture_started_at'],capture_completed_at=h['capture_completed_at'],tzif_bytes=consume(h['tzif_reference'],sources),tzif_reference=h['tzif_reference'],parent_checker=modules['view'],csv_rows=modules['csv'].csv_rows,prefix_checker=modules['prefix'])
    exact(h,expected,'Entire true V5 gap independent replay')
    folder=Path(parent['reference']['path']).parent
    for ticker in ('QQQ','SPY'):
        pref,evidence=modules['prefix'].reconstruct_accounted_prefix(source_bytes=raw[ticker],source_reference=h['full_capture_source_references'][ticker],accounted_sessions=[row['session']for row in h['known_typed_rows']],scope_start=h['known_typed_rows'][0]['session'])
        exact(h['accounted_prefix_references'][ticker]['path'],str(folder/(ticker+'.accounted_prefix.csv')));exact(h['accounted_prefix_evidence_references'][ticker]['path'],str(folder/(ticker+'.prefix_evidence.json')))
        require(consume(h['accounted_prefix_references'][ticker],sources)==pref and consume(h['accounted_prefix_evidence_references'][ticker],sources)==encode(evidence)+b'\n','Whole original prefix and evidence bytes')


def walk_parent_graph(parent,modules,sources,auxiliary):
    if modules.get('consumer_registry_view')is None:return _legacy_walk_parent_graph(parent,modules,sources,auxiliary)
    # One graph classifier and one global bound; no gap-segment depth reset.
    chain=[];envelopes={};current=parent;visited=set();inventories=[]
    while True:
        identity=(current['reference']['path'],current['reference']['sha256'])
        require(identity not in visited and len(visited)<MAX_PARENT_DEPTH,'Global actual/gap parent depth/cycle');visited.add(identity)
        edge=modules['ancestry'].classify_parent_edge(current,bound_pair=modules['bound_pair'],legacy_implementations=modules['host_legacy'],**modules['ancestry_arguments'])
        envelopes[identity]=current;chain.append((current,edge))
        if edge['kind']=='terminal':break
        current=modules['checker'].load_parent_envelope(edge['prior_references'],sources)
    modules['ancestry'].inspect_ancestry_graph({role:parent[role]for role in ROLES},envelopes,bound_pair=modules['bound_pair'],legacy_implementations=modules['host_legacy'],**modules['ancestry_arguments'])
    for current,edge in reversed(chain):
        refs={role:current[role]for role in ROLES};parent_inventory(refs,modules['checker'],sources,inventories)
        current_view=modules['view'].inspect_parent_history_v5(current);verify_baselines(current_view,sources)
        for entry in current_view['observations']:
            audit=decode(consume(entry['audit_reference'],sources))
            pin_namespace(Path(entry['payload_reference']['path']).parent,observation_namespace_names(audit),sources,inventories)
        if edge['kind']=='terminal':
            exact(current['reference'],reference(*TERMINAL_REFERENCE))
            for field in ('document','publication','readback'):
                for path,digest in current[field]['source_hashes'].items():consume(reference(path,digest),sources)
            continue
        prior=envelopes[(edge['prior_references']['reference']['path'],edge['prior_references']['reference']['sha256'])]
        if edge['kind']=='gap':replay_gap_history(current,prior,modules,sources,inventories);verify_gap_outer(current,modules,sources)
        else:
            observation=observation_documents(edge['observation_references'],sources);observation_originals(prior,observation,modules,sources,inventories)
            history=modules['core'].append_observation_history(parent=prior,observation=observation)
            exact(current['document']['history'],history,'Every actual edge whole producer arithmetic')
            verify_actual_outer(current,prior,history,modules,sources,auxiliary)
    return inventories,len(chain)


def verify_gap_outer(parent,modules,sources):
    d,p,a=(parent[key]for key in ('document','publication','readback'))
    if not is_continuation(d,'gap_publisher',modules):
        require(not is_continuation(p,'gap_publisher',modules)and not is_continuation(a,'gap_independent_reader',modules),'No mixed legacy gap metadata')
        return _legacy_verify_gap_outer(parent,modules,sources)
    context=consumer_context(modules);h=d['history'];inputs=d['input_references'];deps=business_dependencies('gap_publisher',modules)
    continuation_inputs(inputs,'gap_publisher',modules,{'parent','capture','registration','runtime','dependencies','registration_core','reference_core','csv_reader'})
    exact(inputs['parent'],h['parent_references']);exact(inputs['capture'],h['capture_references']);exact(inputs['registration_core'],reference(*AUXILIARIES['gap_registration']));exact(inputs['reference_core'],reference(*REGISTRATION_CORE));exact(inputs['csv_reader'],reference(*AUXILIARIES['csv_reader']))
    exact(parent['reader_reference'],context['consumer_registry_view']['consumer_references']['gap_independent_reader'])
    is_continuation(p,'gap_publisher',modules);is_continuation(a,'gap_independent_reader',modules)
    folder=Path(parent['reference']['path']).parent;prior=modules['checker'].load_parent_envelope(h['parent_references'],sources)
    initial,_=consumer_initial_sources(prior,inputs,'gap_publisher',modules,h['capture_references'])
    view=modules['view'].inspect_parent_history_v5(prior)
    for item in (*h['full_capture_source_references'].values(),*view['accounted_baseline_references'].values(),*view['baseline_references'].values(),h['tzif_reference']):consume(item,initial)
    plan=modules['gap_registration'].prepare_gap_runtime(registration=decode(consume(inputs['registration'],initial)),registration_reference=inputs['registration'],runtime_reference=inputs['runtime'],dependency_references=deps,research_root=str(folder.parent))
    exact(plan['parent'],h['parent_references']);exact(plan['capture'],h['capture_references']);exact(plan['output_directory'],str(folder))
    flags=dict.fromkeys(('source_authenticity_verified','parent_history_authenticated_by_this_module','clock_authenticity_verified','timeliness_verified','filesystem_attempt_inventory_authenticated','observation_created','candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','future_independent_oos','production_generator_authorized','old_calendar_mutated','network_quote_refresh_performed','full_transitive_source_closure_reverified','network_capture_performed','seal_event_created','partial_recovery_performed','canonical_calendar_append_allowed','retrospective_backfill_allowed','decision_eligible','exchange_holidays_and_early_closes_verified'),False)
    meta=modules['metadata_core'].expected_consumer_metadata(consumer_role='gap_publisher',**context)
    startref,start=observed_reference(folder/'started.json',sources)
    exact(start,dict(schema='PROSPECTIVE_GAP_HISTORY_STARTED_V5',input_references=inputs,source_hashes=initial,retry_allowed=False,shared_upstream_capture_checker_reference=deps['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,current_live_cache_read_or_reverified=False,**meta,**flags))
    published=deepcopy(initial)
    for item in (startref,*h['accounted_prefix_references'].values(),*h['accounted_prefix_evidence_references'].values()):consume(item,published)
    exact(d,dict(schema=modules['view'].WRAPPER_SCHEMA,history=h,input_references=inputs,source_hashes=published,shared_upstream_capture_checker_reference=deps['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,current_live_cache_read_or_reverified=False,**meta,**flags))
    exact(p,dict(schema=modules['view'].PUBLICATION_SCHEMA,status=modules['view'].PUBLICATION_STATUS,history_reference=parent['reference'],input_references=inputs,source_hashes=published,**meta,**flags))
    read=reader_start_and_sources(parent,inputs,'gap_independent_reader',flags,modules,published,dict(history_reference=parent['reference'],publication_reference=parent['publication_reference']),inputs['registration'],startref)
    exact(a,dict(schema=modules['view'].READBACK_SCHEMA,status=modules['view'].READBACK_STATUS,history_reference=parent['reference'],publication_reference=parent['publication_reference'],reader_sha256=parent['reader_reference']['sha256'],input_references=inputs,source_hashes=read['source_hashes'],counts=modules['view'].gap_counts(h),entire_history_independently_reconstructed=True,publisher_called=False,new_pure_called=False,producer_prefix_core_called=False,producer_scoped_parser_called=False,current_live_cache_read_or_reverified=False,snapshot_bytes_verified=True,
        independent_gap_reconstructor_reference=reference(*READER_ALGORITHMS['independent_gap_reconstructor']),independent_prefix_reconstructor_reference=reference(*AUXILIARIES['independent_prefix']),csv_reader_reference=reference(*AUXILIARIES['csv_reader']),shared_upstream_capture_checker_reference=deps['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,publisher_started_reference_observed_not_external_anchor=startref,publisher_started_externally_authenticated=False,reconstruction_scope='INDEPENDENT_ENTIRE_GAP_RESULT_AND_PREFIX_BYTES_SHARED_UPSTREAM_CAPTURE_CHECKER_NO_SOURCE_OR_CLOCK_AUTHENTICATION',**continuation_reader_fields(read),**flags))
    for path,digest in read['source_hashes'].items():consume(reference(path,digest),sources)


def observation_csv_rows(raw,scope):
    require(type(raw)is bytes and 0<len(raw)<=32000000,'Bounded original payload CSV')
    fields=['Date','Open','High','Low','Close','Volume'];reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''))
    exact(reader.fieldnames,fields);rows=list(reader);require(0<len(rows)<=20000,'Payload data row resource bound');previous='';diagnostics=[]
    for index,row in enumerate(rows):
        require(set(row)==set(fields)and all(type(value)is str and value for value in row.values()),'Entire original payload record')
        day=datetime.strptime(row['Date'],'%Y-%m-%d').date();require(day.isoformat()==row['Date']and day.weekday()<5 and row['Date']>previous,'Ordered unique weekday payload source');previous=row['Date']
        values={}
        for key in fields[1:]:
            require(len(row[key])<=180,'Business scalar bound');value=Decimal(row[key]);require(value.is_finite()and abs(value.as_tuple().exponent)<=160,'Finite business scalar');values[key]=value
        valid=all(values[key]>0 for key in fields[1:5])and values['Low']<=min(values['Open'],values['Close'])<=max(values['Open'],values['Close'])<=values['High']
        require(values['Volume']>=0 and values['Volume']==values['Volume'].to_integral_value(),'Integral business volume')
        if row['Date']>=scope:require(valid,'Business required-scope OHLC')
        elif not valid:diagnostics.append(dict(original_data_row_index=index,session=row['Date'],issue='OUTSIDE_REQUIRED_SCOPE_OHLC_INCONSISTENCY',raw_row=row))
    return rows,diagnostics


def continuation_observation_math(parent,observation,capture,started,modules,sources):
    # This branch does not call frozen5634.inspect or mutate its CHECKER. The
    # stored payload's entire business fields are rebuilt here from raw bytes.
    p,r=observation['payload'],observation['receipt'];view=modules['view'].inspect_parent_history_v5(parent);known=view['known_typed_rows'];days=[row['session']for row in known]
    c=capture['document'];plan=c['plan'];session=plan['candidate_session']
    require(plan['status']=='ONE_NEW_SESSION_CAPTURE_CANDIDATE'and plan['diagnostics']==[]and type(session)is str and session>days[-1],'Unique complete current source candidate')
    identity=dict(parent_reference=parent['reference'],capture_reference=capture['reference'],session=session);identifier=sha(encode(identity))
    fields=dict(schema='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1',observation_id=identifier,observation_identity=identity,session=session,sequence=len(known)+1,kind='PROSPECTIVE_OBSERVED_SESSION',initial_seal_status='NOT_ATTEMPTED',
        parent_readback_reference=parent['readback_reference'],known_typed_rows_preserved=known,parent_attempt_inventory_preserved=view['parent_attempt_inventory'],
        payload_is_not_a_published_observation_receipt=True,seal_status_history_not_created=True,writer_interval_role='PRE_PAYLOAD_VALIDATION_INTERVAL_NOT_PUBLICATION_COMPLETION',capture_started_at_utc=c['capture_started_at'],capture_completed_at_utc=c['capture_completed_at'],writer_started_at_utc=started['writer_started_at_utc'],writer_completed_at_utc=p['writer_completed_at_utc'])
    first=view['first_actual_observed_session_by_month'].get(session[:7],session);fields.update(first_actual_observed_session_of_month=first,month_first_actual_observation=first==session)
    claims={}
    def claim(item):
        item={key:item[key]for key in ('path','sha256')};require(item['path']not in claims or claims[item['path']]==item['sha256'],'Business claim conflict');claims[item['path']]=item['sha256']
    for row in known:claim(row['evidence_reference'])
    for attempt in view['parent_attempt_inventory']:
        for key in ('payload_reference','receipt_reference','independent_readback_reference'):claim(attempt[key])
    for item in (parent['reference'],parent['readback_reference'],capture['reference']):claim(item)
    full={};selected={};locations={}
    for ticker in ('QQQ','SPY'):
        full[ticker]={};parsed={};blobs={}
        for role,item in [('sources',c['captured_artifacts'][ticker]),('baseline_sources',view['accounted_baseline_references'][ticker])]:
            raw=consume(item,sources);rows,diagnostics=observation_csv_rows(raw,days[0]);parsed[role]=rows;blobs[role]=raw;claim(item)
            full[ticker][role]=dict(reference=item,original_csv_bytes_base64=base64.b64encode(raw).decode(),rows=rows,required_scope_start=days[0],outside_required_scope_diagnostics=diagnostics)
        current,baseline=parsed['sources'],parsed['baseline_sources']
        require(blobs['sources'].startswith(blobs['baseline_sources']),'Entire actual original raw byte prefix')
        exact(current[:-1],baseline);exact(len(current),len(baseline)+1);exact([row['Date']for row in baseline if row['Date']>=days[0]],days);exact([row['Date']for row in current if row['Date']>=days[0]],days+[session])
        exact(plan['source_evidence'][ticker]['original_row_count'],len(current));exact(plan['source_evidence'][ticker]['new_session_dates'],[session])
        selected[ticker]=current[-1];locations[ticker]=dict(original_data_row_index=len(current)-1,reference=c['captured_artifacts'][ticker])
    tzref=c['captured_artifacts']['tzif'];tz=consume(tzref,sources);claim(tzref)
    zone=ZoneInfo.from_file(io.BytesIO(tz),key='America/New_York');day=datetime.strptime(session,'%Y-%m-%d').date();following=day+timedelta(days=1)
    while following.weekday()>4:following+=timedelta(days=1)
    deadline=datetime.combine(following,time(9,30),zone).astimezone(timezone.utc)
    fields.update(full_original_sources_preserved=full,selected_original_rows=selected,source_row_locations=locations,tzif_reference=tzref,tzif_bytes_base64=base64.b64encode(tz).decode(),source_hash_claims=claims,conservative_close_utc=datetime.combine(day,time(16),zone).astimezone(timezone.utc).isoformat(),conservative_deadline_utc=deadline.isoformat(),timing_classification='LATE_OBSERVATION'if datetime.fromisoformat(p['writer_completed_at_utc'])>=deadline else 'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')
    for key,value in fields.items():exact(p[key],value,'Entire independent current payload field '+key)
    exact(r['observation_id'],identifier);exact(r['payload_reference'],observation['payload_reference']);verify_observation_timing(p,r,started,tz)
    return view,fields


def observation_originals(parent,observation,modules,sources,inventories,*,current=False):
    p,r,a=(observation[key]for key in ('payload','receipt','audit'))
    if not is_continuation(p,'observation_writer',modules):
        require(not is_continuation(r,'observation_writer',modules)and not is_continuation(a,'observation_independent_reader',modules),'No mixed legacy observation metadata')
        return _legacy_observation_originals(parent,observation,modules,sources,inventories,current=current)
    context=consumer_context(modules);inputs=p['input_references'];meta=modules['metadata_core'].expected_consumer_metadata(consumer_role='observation_writer',**context)
    continuation_inputs(inputs,'observation_writer',modules,{'parent','capture','registration','runtime','dependencies','auxiliary_dependencies','registration_core','reference_core'})
    exact(observation['reader_reference'],context['consumer_registry_view']['consumer_references']['observation_independent_reader']);is_continuation(r,'observation_writer',modules);is_continuation(a,'observation_independent_reader',modules)
    exact(inputs['parent'],{key:parent[key]for key in ROLES});exact(inputs['registration_core'],reference(*modules['observer'].REGISTRATION_CORE));exact(inputs['reference_core'],reference(*REGISTRATION_CORE))
    aux={key:reference(*value)for key,value in modules['observer'].AUXILIARY_DEPENDENCIES.items()};exact(inputs['auxiliary_dependencies'],aux)
    folder=Path(observation['payload_reference']['path']).parent
    for role,name in [('payload_reference','observation_payload.json'),('receipt_reference','receipt.json'),('audit_reference','independent_readback.json')]:exact(observation[role]['path'],str(folder/name))
    pin_namespace(folder,modules['metadata_core'].NAMESPACE_FILES['observation_independent_reader'],sources,inventories)
    startref,start=observed_reference(folder/'started.json',sources)
    capture_inventory(inputs['capture'],modules['checker'],sources,inventories,modules);capture=parent_documents(inputs['capture'],sources)
    exact(capture['document']['parent_references'],inputs['parent'])
    view,fields=continuation_observation_math(parent,observation,capture,start,modules,sources)
    initial,ancestors=consumer_initial_sources(parent,inputs,'observation_writer',modules,inputs['capture']);inventories.extend(ancestors)
    for item in (*view['baseline_references'].values(),*view['accounted_baseline_references'].values(),capture['document']['captured_artifacts']['tzif']):consume(item,initial)
    for ticker in ('QQQ','SPY'):consume(capture['document']['captured_artifacts'][ticker],initial)
    inventory=bound_attempt_inventory(view,folder.parent)
    for values in inventory.values():add_references(values,initial)
    reg=private(inputs['registration_core']['path'],consume(inputs['registration_core'],initial),inputs['registration_core']['sha256'],[('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',modules['references'])])
    registered=reg.prepare_observation_runtime(registration=decode(consume(inputs['registration'],initial)),registration_reference=inputs['registration'],runtime_reference=inputs['runtime'],dependency_references=business_dependencies('observation_writer',modules),research_root=str(folder.parent))
    exact(registered['parent'],inputs['parent']);exact(registered['capture'],inputs['capture']);exact(registered['output_directory'],str(folder))
    runtime=p['runtime'];require(type(runtime)is dict and set(runtime)=={'python','executable','implementation'}and all(type(v)is str and 0<len(v)<10000 for v in runtime.values()),'Declared bounded runtime only')
    metadata=dict(writer_adapter_schema='REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V5',actual_parent_schema=view['parent_schema'],input_references=inputs,source_hashes=initial,runtime=runtime,capture_checker_reference=reference(*AUXILIARIES['capture_checker']),attempt_inventory_scope=modules['observer'].INVENTORY_SCOPE,local_attempt_namespace_inventory=inventory,
        local_direct_child_inventory_scope=dict(root=str(folder.parent),depth=1,semantic_writer_namespaces_scanned=True),external_parent_bound_attempt_inventory={path:values for path,values in inventory.items()if Path(path).parent.parent!=folder.parent},external_unregistered_attempt_discovery_performed=False,
        shared_upstream_capture_checker_called=True,capture_readback_called=False,independent_prefix_checker_reference=aux['independent_prefix'],producer_prefix_core_called=False,gap_core_called=False,**meta)
    flags=dict.fromkeys(modules['observer'].WRITER_FALSE,False);payloadflags=dict.fromkeys(modules['observer'].PAYLOAD_FALSE,False)
    exact(start,dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V5',writer_started_at_utc=p['writer_started_at_utc'],**metadata,**flags))
    exact(p,{**fields,**metadata,**payloadflags,**flags},'Whole continuation original payload')
    exact(r,dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY',observation_id=p['observation_id'],payload_reference=observation['payload_reference'],publication_check_at_utc=r['publication_check_at_utc'],publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE',timing_classification=r['timing_classification'],month_first_actual_observation=p['month_first_actual_observation'],**metadata,**flags))
    read=reader_start_and_sources(observation,inputs,'observation_independent_reader',flags,modules,initial,dict(payload_reference=observation['payload_reference'],receipt_reference=observation['receipt_reference'],parent_history_reference=parent['reference']),None,startref)
    known=view['known_typed_rows'];counts=dict(parent_typed_row_count=len(known),parent_actual_observation_count=sum(row['kind']=='PROSPECTIVE_OBSERVED_SESSION'for row in known),parent_observed_count=sum(row['kind']!='MISSED_OBSERVATION'for row in known),parent_gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in known),new_observation_count=1,month_first_actual_observation=p['month_first_actual_observation'],timing_classification=r['timing_classification'],clock_authenticity_verified=False,final_durable_completion_time_verified=False,candidate_seal_allowed=False,cohort_registration_allowed=False)
    exact(a,dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3',status='PASS',payload_reference=observation['payload_reference'],receipt_reference=observation['receipt_reference'],parent_history_reference=parent['reference'],input_references=inputs,started_current_bytes_reference=startref,started_external_sha_authenticated=False,reader_sha256=observation['reader_reference']['sha256'],source_hashes=read['source_hashes'],counts=counts,writer_called=False,payload_core_called=False,shared_upstream_capture_checker_reference=reference(*AUXILIARIES['capture_checker']),attempt_inventory_scope=metadata['attempt_inventory_scope'],local_attempt_namespace_inventory=inventory,old_audit_repeated=False,exchange_holidays_verified=False,early_closes_verified=False,final_durable_completion_time_verified=False,
        writer_adapter_schema=metadata['writer_adapter_schema'],actual_parent_schema=view['parent_schema'],shared_upstream_parent_checker_reference=inputs['dependencies']['parent_view'],local_direct_child_inventory_scope=metadata['local_direct_child_inventory_scope'],external_parent_bound_attempt_inventory=metadata['external_parent_bound_attempt_inventory'],external_unregistered_attempt_discovery_performed=False,shared_upstream_capture_checker_called=True,capture_readback_called=False,independent_prefix_checker_reference=aux['independent_prefix'],producer_prefix_core_called=False,gap_core_called=False,**continuation_reader_fields(read),**flags),'Whole continuation observation report')
    for path,digest in read['source_hashes'].items():consume(reference(path,digest),sources)
    return start


def run(*,registration_path,registration_sha256,implementation_pair_binding_path,
        implementation_pair_binding_sha256,consumer_role_registry_path=None,consumer_role_registry_sha256=None,execute=False):
    require(type(execute)is bool,'Explicit bool')
    if not execute:return dict(status='NOT_EXECUTED')
    # Every fixed pin is validated before ANY source is read.
    regref=reference(*REGISTRATION_CORE);paircore=reference(*PAIR_BINDING_CORE);contract=reference(*ANCESTRY_CONTRACT)
    bindingref=reference(implementation_pair_binding_path,implementation_pair_binding_sha256)
    require((consumer_role_registry_path is None)==(consumer_role_registry_sha256 is None),'Complete independent host C anchor')
    consumerref=None if consumer_role_registry_path is None else reference(consumer_role_registry_path,consumer_role_registry_sha256)
    legacycontract=reference(*LEGACY_ANCESTRY_CONTRACT);consumerkernel=reference(*CONSUMER_REGISTRY_CORE);metakernel=reference(*CONSUMER_METADATA_CONTRACT)
    registration_ref=reference(registration_path,registration_sha256)
    dependencies={key:reference(*value)for key,value in DEPENDENCIES.items()}
    auxiliary={key:reference(*value)for key,value in AUXILIARIES.items()};runtime_ref=reference(SOURCE,LOADED_SHA)
    pairdeps=dict(publisher=publisher_dependencies(),independent_reader={key:reference(*value)for key,value in READER_ALGORITHMS.items()})
    hostlegacy=host_legacy_implementations()
    for item in (bindingref,registration_ref,consumerref):
        if item is not None:safe(item['path'])
    sources={};consume(runtime_ref,sources)
    reg=private(regref['path'],consume(regref,sources),regref['sha256'])
    binder=private(paircore['path'],consume(paircore,sources),paircore['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',reg)])
    consumer_core=private(consumerkernel['path'],consume(consumerkernel,sources),consumerkernel['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',reg)])
    metadata_core=private(metakernel['path'],consume(metakernel,sources),metakernel['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',reg),
        ('from backtest import ndx_continuation_consumer_role_registry_research_v1 as consumer_registry','consumer_registry',consumer_core)])
    legacy_ancestry=private(legacycontract['path'],consume(legacycontract,sources),legacycontract['sha256'],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as reference_kernel','reference_kernel',reg)])
    ancestry=private(contract['path'],consume(contract,sources),contract['sha256'],[
        ('from backtest import ndx_compact_ancestry_contract_research_v1 as legacy_contract','legacy_contract',legacy_ancestry),
        ('from backtest import ndx_continuation_consumer_metadata_research_v1 as consumer_metadata','consumer_metadata',metadata_core)])
    pair=binder.inspect_pair_binding(binding=decode(consume(bindingref,sources)),binding_reference=bindingref,
        host_binding_reference=bindingref,self_role='publisher',self_reference=runtime_ref,
        expected_contract_reference=contract,expected_algorithm_dependencies=pairdeps)
    consumer_view=None
    if consumerref is not None:
        consumer_view=consumer_core.inspect_consumer_roles(registry=decode(consume(consumerref,sources)),registry_reference=consumerref,host_registry_reference=consumerref,bound_pair=pair)
    # Peer/reader arithmetic is hashed, not executed by this publisher.
    consume(pair['independent_reader_reference'],sources)
    for item in pairdeps['independent_reader'].values():consume(item,sources)
    plan=reg.prepare_compact_history_runtime(registration=decode(consume(registration_ref,sources)),registration_reference=registration_ref,
        runtime_reference=runtime_ref,dependency_references=dependencies,research_root=str(RESEARCH))
    output=safe(plan['output_directory']);require(not output.exists(),'Create-only; no retry')
    modules=load_modules(dependencies,auxiliary,sources)
    modules.update(bound_pair=pair,ancestry=ancestry,host_legacy=hostlegacy,consumer_registry_view=consumer_view,metadata_core=metadata_core,consumer_core=consumer_core)
    modules['ancestry_arguments']=ancestry_arguments(modules)
    modules['independent_gap']=private(READER_ALGORITHMS['independent_gap_reconstructor'][0],consume(reference(*READER_ALGORITHMS['independent_gap_reconstructor']),sources),READER_ALGORITHMS['independent_gap_reconstructor'][1])
    if consumer_view is not None:
        for item in consumer_view['consumer_references'].values():consume(item,sources)
    parent=parent_documents(plan['parent'],sources)
    observation=observation_documents(plan['observation'],sources)
    preflight_original_graph(parent,observation,modules,sources)
    inventories,node_count=walk_parent_graph(parent,modules,sources,auxiliary)
    observation=observation_documents(plan['observation'],sources)
    observation_originals(parent,observation,modules,sources,inventories,current=True)
    current_inventory=current_attempt_inventory(parent,observation,sources,inventories)
    history=modules['core'].append_observation_history(parent=parent,observation=observation)
    for path,digest in history['source_hashes'].items():
        require(modules['permitted_sources'].get(path)==digest,'Current history source requires original role')
        consume(reference(path,digest),sources)
    def final_guard():
        exact(current_attempt_inventory(parent,observation,{},[]),current_inventory,'Current local semantic attempt drift')
        for folder,names in inventories:namespace(Path(folder),names,{})
        guard(sources)
    final_guard();require(shutil.disk_usage(output.anchor).free>=5*1024**3,'Resource stop before namespace')
    output.mkdir(parents=True,exist_ok=False)
    inputs=pair_inputs(parent=plan['parent'],observation=plan['observation'],registration=registration_ref,runtime=runtime_ref,
        dependencies=pairdeps['publisher'],auxiliary=auxiliary,registration_core=regref,pair=pair,consumer_registry_view=consumer_view)
    metadata=compact_metadata(modules_parent_schema(parent),auxiliary,pair=pair,consumer_registry_view=consumer_view)
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
        return dict(history_reference=history_ref,publication_reference=publication,implementation_pair_binding_reference=bindingref,
            ancestry_contract_reference=contract,independent_readback_required=True,**FLAGS)
    except BaseException as error:
        save(output/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,automatic_retry_allowed=False,**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration-path','registration-sha256','implementation-pair-binding-path','implementation-pair-binding-sha256'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--consumer-role-registry-path');parser.add_argument('--consumer-role-registry-sha256')
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(run(**vars(args))))
