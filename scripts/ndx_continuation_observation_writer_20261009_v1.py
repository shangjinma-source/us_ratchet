"""Host-bound continuation observation writer; immutable research evidence only.

The shared reader replays original ancestors and the exact registered capture.
This runtime executes only the original fixed payload kernel for new business.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import platform
import re
import shutil
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESEARCH = ROOT / 'data/cache/research'
CURRENT = {ticker: ROOT / 'data/cache' / (ticker + '.csv') for ticker in ('QQQ', 'SPY')}
CONSUMER_ROLE = 'observation_writer'

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


def runtime():
    return dict(python=sys.version, executable=sys.executable, implementation=platform.python_implementation())


def run(*, registration_path, registration_sha256, implementation_pair_binding_path,
        implementation_pair_binding_sha256, consumer_role_registry_path,
        consumer_role_registry_sha256, execute=False):
    require(type(execute) is bool, 'Explicit execution bool')
    if not execute:
        return dict(status='NOT_EXECUTED')
    configured_refs = {key: reference(str(value[0]), value[1]) for key, value in dict(
        registration_core=REGISTRATION_CORE, reference_core=REFERENCE_CORE,
        pair_binding_core=PAIR_BINDING_CORE, consumer_registry_core=CONSUMER_REGISTRY_CORE,
        consumer_metadata_contract=CONSUMER_METADATA_CORE, ancestry_contract=ANCESTRY_CONTRACT,
        shared_ancestry_verifier=SHARED_ANCESTRY_VERIFIER).items()}
    dependencies = configured(DEPENDENCIES)
    auxiliary = configured(AUXILIARY_DEPENDENCIES)
    registration_ref = reference(str(registration_path), registration_sha256)
    binding_ref = reference(str(implementation_pair_binding_path), implementation_pair_binding_sha256)
    registry_ref = reference(str(consumer_role_registry_path), consumer_role_registry_sha256)
    self_ref = reference(str(SOURCE), LOADED_SHA)
    sources = {}
    registration_core, metadata = host_modules(sources, configured_refs)
    exact(registration_core.REFERENCE_KERNEL_SHA256, REFERENCE_CORE[1])
    registered = registration_core.prepare_observation_runtime(
        registration=decode(consume(registration_ref, sources)), registration_reference=registration_ref,
        runtime_reference=self_ref, dependency_references=dependencies, research_root=str(RESEARCH))
    output = safe(registered['output_directory'])
    require(not output.exists(), 'Create-only observation namespace; no retry')
    shared_ref = configured_refs['shared_ancestry_verifier']
    shared = compile_private(shared_ref['path'], consume(shared_ref, sources), shared_ref['sha256'])
    shared.RESEARCH = RESEARCH
    shared.CURRENT = CURRENT
    replay = shared.verify_saved_parent_ancestry(parent_references=registered['parent'],
        implementation_pair_binding_path=binding_ref['path'], implementation_pair_binding_sha256=binding_ref['sha256'],
        consumer_role_registry_path=registry_ref['path'], consumer_role_registry_sha256=registry_ref['sha256'],
        consumer_writer_registration_reference=registration_ref, execute=True)
    exact(replay.get('status'), 'READ_ONLY_WHOLE_ANCESTRY_RECONSTRUCTION_PASS')
    exact(replay.get('verified_writer_registration_reference'), registration_ref)
    context = dict(bound_pair=replay['bound_pair'], consumer_registry_view=replay['consumer_registry_view'],
        consumer_registry_core_reference=replay['consumer_registry_core_reference'],
        metadata_contract_reference=replay['consumer_metadata_contract_reference'])
    require(context['consumer_registry_view'] is not None, 'Explicit host consumer family')
    exact(context['bound_pair']['binding_reference'], binding_ref)
    exact(context['bound_pair']['contract_reference'], configured_refs['ancestry_contract'])
    exact(context['bound_pair']['independent_reader_reference'], shared_ref)
    exact(context['consumer_registry_view']['registry_reference'], registry_ref)
    exact(context['consumer_registry_core_reference'], configured_refs['consumer_registry_core'])
    exact(context['metadata_contract_reference'], configured_refs['consumer_metadata_contract'])
    exact(context['consumer_registry_view']['consumer_references'][CONSUMER_ROLE], self_ref)
    header = metadata.expected_consumer_metadata(consumer_role=CONSUMER_ROLE, **context)
    inputs = dict(parent=registered['parent'], capture=registered['capture'], dependencies=dependencies,
        auxiliary_dependencies=auxiliary, registration=registration_ref, runtime=self_ref,
        registration_core=configured_refs['registration_core'], reference_core=configured_refs['reference_core'])
    inputs.update(metadata.continuation_input_references(registered_dependency_references=dependencies,
        consumer_role=CONSUMER_ROLE, **context))
    initial = replay['writer_input_sources']
    require(type(initial) is dict and initial, 'Independent exact writer source closure')
    for item in (*configured_refs.values(), self_ref, registration_ref, binding_ref, registry_ref,
            *dependencies.values(), *auxiliary.values()):
        require(initial.get(item['path']) == item['sha256'], 'Fixed writer input absent from derived closure')
    sources = {}
    for path, value in initial.items():
        consume(reference(path, value), sources)
    capture = replay['capture_envelope']
    plan = replay['capture_plan']
    view = replay['parent_view']
    attempts = deepcopy(replay['writer_prior_attempt_inventory'])
    exact({role: capture[role] for role in ROLES}, registered['capture'])
    exact(capture['document']['parent_references'], registered['parent'])
    exact(plan, capture['document']['plan'])
    exact(plan['status'], 'ONE_NEW_SESSION_CAPTURE_CANDIDATE')
    exact(plan['diagnostics'], [])
    session = plan['candidate_session']
    value = dict(reference=registered['capture']['reference'], started_at_utc=capture['document']['capture_started_at'],
        completed_at_utc=capture['document']['capture_completed_at'], sources={}, baseline_sources={})
    for ticker in ('QQQ', 'SPY'):
        for role, item in (('sources', capture['document']['captured_artifacts'][ticker]),
                ('baseline_sources', view['accounted_baseline_references'][ticker])):
            value[role][ticker] = dict(bytes=consume(item, sources), reference=deepcopy(item))
    tzif = capture['document']['captured_artifacts']['tzif']
    value['tzif'] = dict(bytes=consume(tzif, sources), reference=deepcopy(tzif))
    exact(sources, initial, 'Payload IO cannot enlarge independently derived closure')
    core = compile_private(CORE, consume(dependencies['payload_core'], sources), CORE_SHA)
    args = dict(parent_reference=registered['parent']['reference'], parent_readback_reference=registered['parent']['readback_reference'],
        known_typed_rows=deepcopy(view['known_typed_rows']), parent_attempt_inventory=deepcopy(view['parent_attempt_inventory']),
        capture=value, session=session)
    created = {}
    def final_guard():
        replay['final_guard']()
        for path, value in sources.items():
            consume(reference(path, value), {})
        if output.exists():
            namespace(output, created)
        for item in created.values():
            consume(item, {})
    final_guard()
    resource_gate(output.anchor)
    output.mkdir(parents=True, exist_ok=False)
    try:
        rt = runtime()
        start = now()
        meta = dict(writer_adapter_schema=ADAPTER, actual_parent_schema=view['parent_schema'], input_references=inputs,
            source_hashes=deepcopy(sources), runtime=rt, capture_checker_reference=dependencies['capture_checker'],
            shared_upstream_capture_checker_called=True, capture_readback_called=False,
            independent_prefix_checker_reference=auxiliary['independent_prefix'], producer_prefix_core_called=False,
            gap_core_called=False, attempt_inventory_scope=INVENTORY_SCOPE, local_attempt_namespace_inventory=attempts,
            local_direct_child_inventory_scope=dict(root=str(RESEARCH), depth=1, semantic_writer_namespaces_scanned=True),
            external_parent_bound_attempt_inventory={path: deepcopy(records) for path, records in attempts.items()
                if Path(path).parent.parent != RESEARCH}, external_unregistered_attempt_discovery_performed=False, **header)
        created['started.json'] = save(output / 'started.json', dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V5',
            writer_started_at_utc=start, **meta, **FLAGS))
        final_guard()
        end = now()
        payload = core.prepare_observation_payload(**args, writer_started_at_utc=start, writer_completed_at_utc=end)
        for path, value in payload['source_hash_claims'].items():
            require(sources.get(path) == value, 'Payload claim outside independent closure')
        payload.update(meta)
        payload.update(FLAGS)
        payload['writer_interval_role'] = 'PRE_PAYLOAD_VALIDATION_INTERVAL_NOT_PUBLICATION_COMPLETION'
        final_guard()
        created['observation_payload.json'] = save(output / 'observation_payload.json', payload)
        final_guard()
        exact(runtime(), rt)
        check = now()
        require(core.utc(check) >= core.utc(end), 'Publication clock reversal')
        late = payload['timing_classification'] == 'LATE_OBSERVATION' or core.utc(check) >= core.utc(payload['conservative_deadline_utc'])
        final_guard()
        created['receipt.json'] = save(output / 'receipt.json', dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',
            status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY', observation_id=payload['observation_id'],
            payload_reference=created['observation_payload.json'], publication_check_at_utc=check,
            publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE',
            timing_classification='LATE_OBSERVATION' if late else payload['timing_classification'],
            month_first_actual_observation=payload['month_first_actual_observation'], **meta, **FLAGS))
        final_guard()
        exact(runtime(), rt)
        namespace(output, ('started.json', 'observation_payload.json', 'receipt.json'))
        return deepcopy(created['receipt.json'])
    except BaseException as error:
        save(output / 'failure.json', dict(status='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY',
            error_type=type(error).__name__, recorded_at_utc=now(), consumer_role=CONSUMER_ROLE,
            observation_payload_must_not_be_discarded=(output / 'observation_payload.json').exists(), retry_allowed=False, **FLAGS))
        raise
