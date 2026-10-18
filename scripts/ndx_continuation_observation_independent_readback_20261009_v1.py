"""Independent continuation observation readback; full five-file format.

Payload arithmetic runs here, without loading any writer or payload generator.
The shared reader checks original ancestry and the registered capture only.
"""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
from types import ModuleType
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESEARCH = ROOT / 'data/cache/research'
CURRENT = {ticker: ROOT / 'data/cache' / (ticker + '.csv') for ticker in ('QQQ', 'SPY')}
CONSUMER_ROLE = 'observation_independent_reader'

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


MIN_FREE = 5 * 1024**3


PAIR_BINDING_CORE = (ROOT / 'backtest/ndx_compact_implementation_pair_binding_research_v1.py', 'dde8b681612d2b4fc0993bb9b697dcefb0222036d3e1bb6f4aa5f2dd76d7e4ad')


CONSUMER_REGISTRY_CORE = (ROOT / 'backtest/ndx_continuation_consumer_role_registry_research_v1.py', '184479c5e0e6412265e00cc875af1f7902e4f500dc984ca2aaaf3251bc8c433b')


CONSUMER_METADATA_CORE = (ROOT / 'backtest/ndx_continuation_consumer_metadata_research_v1.py', 'b0d16b1b364d2c32e55d826c1f9d63dfffeb27df7bcabfe972efd029e8e2fdeb')


ANCESTRY_CONTRACT = (ROOT / 'backtest/ndx_compact_ancestry_contract_research_v2.py', '081ba024fa997c37c1f030fcec7d4d22ca6411eec652d15a5049b57d62a31a76')


SHARED_ANCESTRY_VERIFIER = (ROOT / 'scripts/ndx_registered_compact_history_independent_readback_20261009_v2.py', '5ceec753c972ecb5047311331285e5c7ec0ec67c361709f51ba101584498dddf')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON ' + value)))


def reference(path, sha256):
    require(type(path) is str and path and path.strip() == path, 'Exact reference path')
    canonical_path(path)
    require(type(sha256) is str and len(sha256) == 64 and
            all(char in '0123456789abcdef' for char in sha256), 'Pending immutable anchor')
    return dict(path=path, sha256=sha256)


def canonical_path(value):
    path = PureWindowsPath(value)
    require(path.is_absolute() and re.fullmatch(r'[A-Za-z]:', path.drive) is not None,
        'Absolute local drive path')
    require(not any(part in ('.', '..') for part in value.replace('\\', '/').split('/')),
        'No relative path components')
    reserved = {'con', 'prn', 'aux', 'nul', *('com' + str(i) for i in range(1, 10)),
        *('lpt' + str(i) for i in range(1, 10))}
    for part in path.parts[1:]:
        require(not any(ord(char) < 32 or char in '<>:"|?*' for char in part)
            and not part.endswith((' ', '.')) and part.split('.')[0].casefold() not in reserved,
            'No ambiguous Windows source path')
    return str(path).casefold()


def merge(sources, item):
    require(type(item) is dict and set(item) == {'path', 'sha256'}, 'Exact reference fields')
    reference(item['path'], item['sha256'])
    require(item['path'] not in sources or sources[item['path']] == item['sha256'], 'Source conflict')
    identity = canonical_path(item['path'])
    require(all(canonical_path(path) != identity or path == item['path']
        for path in sources), 'No source path spelling aliases')
    sources[item['path']] = item['sha256']


def safe(path):
    path = Path(path)
    require(path.is_absolute(), 'Absolute source/output path')
    for ancestor in (path, *path.parents):
        require(not ancestor.is_symlink() and not getattr(ancestor, 'is_junction', lambda: False)(),
                'Linked source/output forbidden')
    return path


def consume(item, sources, *, allow_current=False):
    merge(sources, item)
    path = safe(item['path'])
    mutable = {value.resolve() for value in CURRENT.values()} | {
        (ROOT / 'data/cache' / (ticker + '.csv')).resolve() for ticker in ('QQQ', 'SPY')}
    require(allow_current or path.resolve() not in mutable, 'Mutable cache excluded before immutable source read')
    require(path.is_file() and path.stat().st_size <= 64 * 1024**2, 'Bounded regular source')
    require(not (path.parent / 'failure.json').exists(), 'Failed source namespace')
    raw = path.read_bytes()
    require(digest(raw) == item['sha256'], 'Source SHA changed')
    return raw


def namespace(folder, names):
    items = list(safe(folder).iterdir())
    require({item.name for item in items} == set(names), 'Exact namespace inventory')
    require(all(safe(item).is_file() for item in items), 'Regular namespace files')


def configured(bound):
    return {key: reference(str(ROOT / path), sha256) for key, (path, sha256) in bound.items()}


def compile_private(path, raw, expected, replacements=()):
    require(digest(raw)==expected, 'Private dependency SHA')
    module=ModuleType('_registered_capture_'+Path(path).stem);module.__file__=str(path)
    code=raw.decode('utf-8-sig')
    for line,attribute,value in replacements:
        require(code.count(line)==1, 'Explicit private dependency import')
        code=code.replace(line,'');module.__dict__[attribute]=value
    exec(compile(code,str(path),'exec'),module.__dict__)
    return module


def resource_gate(anchor,size=0):
    require(type(size) is int and size >= 0, 'Exact nonnegative reserve')
    require(shutil.disk_usage(Path(anchor)).free >= MIN_FREE + size, 'RESOURCE_STOP_BEFORE_WRITE')


def save_bytes(path, raw):
    if path.name != 'failure.json':
        resource_gate(path.anchor,len(raw))
    with safe(path).open('xb') as stream:
        require(stream.write(raw) == len(raw), 'Complete output write')
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'Durable saved bytes')
    return reference(str(path), digest(raw))


def save(path, value):
    return save_bytes(path, encode(value))


def now():
    return datetime.now(timezone.utc).isoformat()


def host_modules(sources, refs):
    """Privately load pinned metadata kernels; no artifact chooses code."""
    refcore = compile_private(REFERENCE_CORE[0], consume(refs['reference_core'], sources), REFERENCE_CORE[1])
    consumer = compile_private(CONSUMER_REGISTRY_CORE[0], consume(refs['consumer_registry_core'], sources),
        CONSUMER_REGISTRY_CORE[1], [
            ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references', 'references', refcore)])
    metadata = compile_private(CONSUMER_METADATA_CORE[0], consume(refs['consumer_metadata_contract'], sources),
        CONSUMER_METADATA_CORE[1], [
            ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references', 'references', refcore),
            ('from backtest import ndx_continuation_consumer_role_registry_research_v1 as consumer_registry', 'consumer_registry', consumer)])
    registration = compile_private(REGISTRATION_CORE[0], consume(refs['registration_core'], sources),
        REGISTRATION_CORE[1], [
            ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references', 'references', refcore)])
    require(registration.REFERENCE_KERNEL_SHA256 == REFERENCE_CORE[1], 'Registration reference kernel binding')
    return registration, metadata


def exact(left, right, message='Exact continuation observation evidence'):
    require(encode(left) == encode(right), message)


CHECKER=tuple(map(str,DEPENDENCIES['capture_checker']))


FIELDS=['Date','Open','High','Low','Close','Volume']


PAYLOAD_FALSE=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','source_authenticity_verified','clock_authenticity_verified','parent_attempt_inventory_completeness_verified','receipt_published','old_calendar_mutated','exchange_holidays_verified','early_closes_verified','production_generator_authorized')


WRITER_FALSE=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','old_calendar_mutated','seal_status_event_created','network_capture_performed','production_generator_authorized','full_transitive_source_closure_reverified','future_independent_oos','partial_recovery_performed','filesystem_attempt_inventory_authenticated','source_authenticity_verified','clock_authenticity_verified','parent_attempt_inventory_completeness_verified')


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


def continuation_observation_values(payload,receipt,started,parent,capture_env,refs,payload_reference,blobs,session,inventory,view):
    """All supplied blobs must come from wrapper-verified external byte references."""
    # Independent business formulas; no frozen observer IO/inspect entry is called.
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
    exact(payload['observation_identity'],identity,'Observation identity');identifier=digest(encode(identity));exact(payload['observation_id'],identifier,'Observation digest');exact(receipt['observation_id'],identifier,'Receipt same observation')
    exact(payload['session'],session,'Session');require(type(payload['sequence'])is int and payload['sequence']==len(known)+1,'Exact variable sequence');require(payload['kind']=='PROSPECTIVE_OBSERVED_SESSION' and payload['initial_seal_status']=='NOT_ATTEMPTED','No seal')
    exact(payload['parent_readback_reference'],refs['parent']['readback_reference'],'Parent audit')
    require(set(payload['full_original_sources_preserved'])==set(payload['selected_original_rows'])==set(payload['source_row_locations'])=={'QQQ','SPY'},'Two full sources')
    for ticker in ('QQQ','SPY'):
        exact(sorted(payload['full_original_sources_preserved'][ticker]),['baseline_sources','sources'],'Exact full-source roles')
        parsed={}
        for role in ('sources','baseline_sources'):
            reference=capture['captured_artifacts'][ticker] if role=='sources' else capture['plan']['accounted_baseline_references'][ticker];ref(reference,claims);blob=blobs[reference['path']];require(digest(blob)==reference['sha256'],'Original CSV hash')
            rows,diagnostics=parse_csv(blob,dates[0]);parsed[role]=rows
            exact(payload['full_original_sources_preserved'][ticker][role],dict(reference=reference,original_csv_bytes_base64=base64.b64encode(blob).decode(),rows=rows,required_scope_start=dates[0],outside_required_scope_diagnostics=diagnostics),'Full CSV and outside diagnostics')
        current=parsed['sources'];baseline=parsed['baseline_sources']
        require(blobs[capture['captured_artifacts'][ticker]['path']].startswith(blobs[plan['accounted_baseline_references'][ticker]['path']]),'Complete raw byte prefix unchanged')
        exact([r['Date'] for r in baseline if r['Date']>=dates[0]],dates,'Complete variable baseline');exact([r['Date'] for r in current if r['Date']>=dates[0]],dates+[session],'Variable prefix plus one')
        exact(plan['source_evidence'][ticker]['original_row_count'],len(current),'Snapshot row count')
        require(len(current)==len(baseline)+1,'Single new row');exact(current[:-1],baseline,'Entire historical prefix unchanged')
        exact(payload['selected_original_rows'][ticker],current[-1],'Actual source row');exact(payload['source_row_locations'][ticker],dict(original_data_row_index=len(current)-1,reference=capture['captured_artifacts'][ticker]),'Original row pointer')
    tzref=capture['captured_artifacts']['tzif'];ref(tzref,claims);tz=blobs[tzref['path']];require(digest(tz)==tzref['sha256'],'TZif bytes');exact(payload['tzif_reference'],tzref,'TZif reference');exact(payload['tzif_bytes_base64'],base64.b64encode(tz).decode(),'Full TZif')
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


def reference_tree(value, sources):
    if type(value) is dict and set(value) == {'path', 'sha256'}:
        consume(value, sources)
    elif type(value) is dict:
        for child in value.values():
            reference_tree(child, sources)


def readback(*, registration_path, registration_sha256, payload_reference, receipt_reference,
        implementation_pair_binding_path, implementation_pair_binding_sha256,
        consumer_role_registry_path, consumer_role_registry_sha256, execute=False):
    require(type(execute) is bool, 'Explicit execution bool')
    if not execute:
        return dict(status='NOT_EXECUTED')
    fixed = {key: reference(str(value[0]), value[1]) for key, value in dict(
        registration_core=REGISTRATION_CORE, reference_core=REFERENCE_CORE,
        pair_binding_core=PAIR_BINDING_CORE, consumer_registry_core=CONSUMER_REGISTRY_CORE,
        consumer_metadata_contract=CONSUMER_METADATA_CORE, ancestry_contract=ANCESTRY_CONTRACT,
        shared_ancestry_verifier=SHARED_ANCESTRY_VERIFIER).items()}
    registration_ref = reference(str(registration_path), registration_sha256)
    binding_ref = reference(str(implementation_pair_binding_path), implementation_pair_binding_sha256)
    registry_ref = reference(str(consumer_role_registry_path), consumer_role_registry_sha256)
    self_ref = reference(str(SOURCE), LOADED_SHA)
    for item in (payload_reference, receipt_reference):
        merge({}, item)
    dependencies = configured(DEPENDENCIES)
    auxiliary = configured(AUXILIARY_DEPENDENCIES)
    bootstrap_sources = {}
    registration_core, metadata = host_modules(bootstrap_sources, fixed)
    shared_ref = fixed['shared_ancestry_verifier']
    shared = compile_private(shared_ref['path'], consume(shared_ref, bootstrap_sources), shared_ref['sha256'])
    shared.RESEARCH = RESEARCH
    shared.CURRENT = CURRENT
    family = shared.inspect_host_continuation_family(implementation_pair_binding_path=binding_ref['path'],
        implementation_pair_binding_sha256=binding_ref['sha256'], consumer_role_registry_path=registry_ref['path'],
        consumer_role_registry_sha256=registry_ref['sha256'], execute=True)
    context = dict(bound_pair=family['bound_pair'], consumer_registry_view=family['consumer_registry_view'],
        consumer_registry_core_reference=family['consumer_registry_core_reference'],
        metadata_contract_reference=family['consumer_metadata_contract_reference'])
    require(context['consumer_registry_view'] is not None, 'Explicit host consumer family')
    exact(context['bound_pair']['binding_reference'], binding_ref)
    exact(context['bound_pair']['contract_reference'], fixed['ancestry_contract'])
    exact(context['bound_pair']['independent_reader_reference'], shared_ref)
    exact(context['consumer_registry_view']['registry_reference'], registry_ref)
    exact(context['consumer_registry_core_reference'], fixed['consumer_registry_core'])
    exact(context['metadata_contract_reference'], fixed['consumer_metadata_contract'])
    consumers = context['consumer_registry_view']['consumer_references']
    exact(consumers[CONSUMER_ROLE], self_ref)
    writer_ref = consumers['observation_writer']
    registered = registration_core.prepare_observation_runtime(registration=decode(consume(registration_ref, bootstrap_sources)),
        registration_reference=registration_ref, runtime_reference=writer_ref, dependency_references=dependencies,
        research_root=str(RESEARCH))
    output = safe(registered['output_directory'])
    exact(payload_reference['path'], str(output / 'observation_payload.json'))
    exact(receipt_reference['path'], str(output / 'receipt.json'))
    namespace(output, ('started.json', 'observation_payload.json', 'receipt.json'))
    replay = shared.verify_saved_parent_ancestry(parent_references=registered['parent'],
        implementation_pair_binding_path=binding_ref['path'], implementation_pair_binding_sha256=binding_ref['sha256'],
        consumer_role_registry_path=registry_ref['path'], consumer_role_registry_sha256=registry_ref['sha256'],
        consumer_writer_registration_reference=registration_ref, execute=True)
    exact(replay.get('status'), 'READ_ONLY_WHOLE_ANCESTRY_RECONSTRUCTION_PASS')
    exact(replay.get('verified_writer_registration_reference'), registration_ref)
    for key in ('bound_pair', 'consumer_registry_view', 'consumer_registry_core_reference', 'consumer_metadata_contract_reference'):
        exact(replay[key], family[key], 'Same separately inspected host context')
    initial = deepcopy(replay['writer_input_sources'])
    require(type(initial) is dict and initial, 'Independent writer initial closure')
    sources = {}
    for path, value in initial.items():
        consume(reference(path, value), sources)
    inputs = dict(parent=registered['parent'], capture=registered['capture'], dependencies=dependencies,
        auxiliary_dependencies=auxiliary, registration=registration_ref, runtime=writer_ref,
        registration_core=fixed['registration_core'], reference_core=fixed['reference_core'])
    inputs.update(metadata.continuation_input_references(registered_dependency_references=dependencies,
        consumer_role='observation_writer', **context))
    private_inputs = dict(runtime=self_ref, dependencies=dependencies, auxiliary_dependencies=auxiliary,
        independent_dependencies={}, registration_core=fixed['registration_core'], reference_core=fixed['reference_core'],
        pair_binding_core=fixed['pair_binding_core'], implementation_pair_binding=binding_ref,
        consumer_role_registry=registry_ref, ancestry_contract=fixed['ancestry_contract'],
        shared_ancestry_verifier=shared_ref, consumer_registry_core=fixed['consumer_registry_core'],
        consumer_metadata_contract=fixed['consumer_metadata_contract'])
    reference_tree(private_inputs, sources)
    payload = decode(consume(payload_reference, sources))
    receipt = decode(consume(receipt_reference, sources))
    started_path = output / 'started.json'
    require(started_path.is_file() and started_path.stat().st_size <= 64 * 1024**2, 'Bounded writer START')
    started_ref = reference(str(started_path), digest(started_path.read_bytes()))
    started = decode(consume(started_ref, sources))
    public_header = metadata.expected_consumer_metadata(consumer_role='observation_writer', **context)
    reader_header = metadata.expected_consumer_metadata(consumer_role=CONSUMER_ROLE, **context)
    view = replay['parent_view']
    parent = replay['parent_envelope']
    capture = replay['capture_envelope']
    attempts = deepcopy(replay['writer_prior_attempt_inventory'])
    exact({role: capture[role] for role in ROLES}, registered['capture'])
    exact(capture['document']['parent_references'], registered['parent'])
    exact(replay['capture_plan'], capture['document']['plan'])
    rt = payload['runtime']
    require(type(rt) is dict and set(rt) == {'python', 'executable', 'implementation'}
        and all(type(item) is str and 0 < len(item) < 10000 for item in rt.values()), 'Bounded runtime declaration')
    meta = dict(writer_adapter_schema=ADAPTER, actual_parent_schema=view['parent_schema'], input_references=inputs,
        source_hashes=initial, runtime=rt, capture_checker_reference=dependencies['capture_checker'],
        shared_upstream_capture_checker_called=True, capture_readback_called=False,
        independent_prefix_checker_reference=auxiliary['independent_prefix'], producer_prefix_core_called=False,
        gap_core_called=False, attempt_inventory_scope=INVENTORY_SCOPE, local_attempt_namespace_inventory=attempts,
        local_direct_child_inventory_scope=dict(root=str(RESEARCH), depth=1, semantic_writer_namespaces_scanned=True),
        external_parent_bound_attempt_inventory={path: records for path, records in attempts.items()
            if Path(path).parent.parent != RESEARCH}, external_unregistered_attempt_discovery_performed=False, **public_header)
    exact(started, dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V5',
        writer_started_at_utc=payload['writer_started_at_utc'], **meta, **FLAGS))
    blobs = {}
    for ticker in ('QQQ', 'SPY'):
        for item in (capture['document']['captured_artifacts'][ticker], view['accounted_baseline_references'][ticker],
                view['baseline_references'][ticker]):
            blobs[item['path']] = consume(item, sources)
    tzif = capture['document']['captured_artifacts']['tzif']
    blobs[tzif['path']] = consume(tzif, sources)
    counts = continuation_observation_values(payload, receipt, started, parent, capture, inputs,
        payload_reference, blobs, replay['capture_plan']['candidate_session'], attempts, view)
    exact(receipt, dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',
        status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY', observation_id=payload['observation_id'],
        payload_reference=payload_reference, publication_check_at_utc=receipt['publication_check_at_utc'],
        publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE',
        timing_classification=receipt['timing_classification'], month_first_actual_observation=payload['month_first_actual_observation'],
        **meta, **FLAGS))
    core_keys = {'schema','observation_id','observation_identity','session','sequence','kind','initial_seal_status',
        'month_first_actual_observation','first_actual_observed_session_of_month','timing_classification',
        'capture_started_at_utc','capture_completed_at_utc','writer_started_at_utc','writer_completed_at_utc',
        'conservative_close_utc','conservative_deadline_utc','selected_original_rows','source_row_locations',
        'full_original_sources_preserved','tzif_reference','tzif_bytes_base64','parent_readback_reference',
        'known_typed_rows_preserved','parent_attempt_inventory_preserved','source_hash_claims',
        'payload_is_not_a_published_observation_receipt','seal_status_history_not_created','writer_interval_role'}
    require(set(payload) == core_keys | set(meta) | set(PAYLOAD_FALSE) | set(FLAGS), 'Closed entire payload fields')
    for key, value in meta.items():
        exact(payload[key], value, 'Exact producer metadata ' + key)
    created = {name: item for name, item in (('started.json', started_ref),
        ('observation_payload.json', payload_reference), ('receipt.json', receipt_reference))}
    def final_guard():
        family['final_guard']()
        replay['final_guard']()
        for path, value in sources.items():
            consume(reference(path, value), {})
        namespace(output, created)
        for item in created.values():
            consume(item, {})
    final_guard()
    try:
        own = save(output / 'reader_started.json', dict(schema='PROSPECTIVE_OBSERVATION_CONTINUATION_READER_STARTED_V1',
            payload_reference=payload_reference, receipt_reference=receipt_reference,
            parent_history_reference=registered['parent']['reference'], input_references=inputs,
            reader_input_references=private_inputs, reader_sha256=LOADED_SHA, **reader_header, **FLAGS))
        created['reader_started.json'] = own
        consume(own, sources)
        final_guard()
        report = dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3', status='PASS',
            payload_reference=payload_reference, receipt_reference=receipt_reference,
            parent_history_reference=registered['parent']['reference'], input_references=inputs, reader_input_references=private_inputs,
            started_current_bytes_reference=started_ref, started_external_sha_authenticated=False,
            reader_sha256=LOADED_SHA, source_hashes=deepcopy(sources), counts=counts,
            writer_called=False, payload_core_called=False, shared_upstream_capture_checker_reference=dependencies['capture_checker'],
            attempt_inventory_scope=INVENTORY_SCOPE, local_attempt_namespace_inventory=attempts, old_audit_repeated=False,
            exchange_holidays_verified=False, early_closes_verified=False, final_durable_completion_time_verified=False,
            writer_adapter_schema=ADAPTER, actual_parent_schema=view['parent_schema'],
            shared_upstream_parent_checker_reference=dependencies['parent_view'],
            local_direct_child_inventory_scope=meta['local_direct_child_inventory_scope'],
            external_parent_bound_attempt_inventory=meta['external_parent_bound_attempt_inventory'],
            external_unregistered_attempt_discovery_performed=False, shared_upstream_capture_checker_called=True,
            capture_readback_called=False, independent_prefix_checker_reference=auxiliary['independent_prefix'],
            producer_prefix_core_called=False, gap_core_called=False,
            reader_started_reference_observed_not_external_anchor=own, reader_started_externally_authenticated=False,
            **reader_header, **FLAGS)
        final_guard()
        created['independent_readback.json'] = save(output / 'independent_readback.json', report)
        final_guard()
        return deepcopy(created['independent_readback.json'])
    except BaseException as error:
        save(output / 'failure.json', dict(status='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY',
            error_type=type(error).__name__, recorded_at_utc=now(), consumer_role=CONSUMER_ROLE,
            retry_allowed=False, **FLAGS))
        raise
