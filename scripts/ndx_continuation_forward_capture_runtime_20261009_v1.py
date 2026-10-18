"""Host-bound continuation capture publisher; whole parent replay before capture.

The shared reader verifies original ancestors; this producer calls only its
original capture business kernel and never creates an observation.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from pathlib import PureWindowsPath
import re
import shutil
from datetime import datetime, timezone
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESEARCH = ROOT / 'data/cache/research'
REGISTRATION_CORE = (ROOT / 'backtest/ndx_forward_capture_runtime_registration_research_v2.py', 'fc907ddff33988b3f3e29f4585c32ae7b2e743ea9f6abe29055772ce0f0876cd')
PREFIX_CORE = (ROOT / 'backtest/ndx_accounted_source_prefix_research_v1.py', '5602376c97e654ba665ba2d4f711ee73171364a17d977cc9588ad51c385d8c9b')
GAP_CORE = (ROOT / 'backtest/ndx_prospective_gap_history_research_v5.py', '11a8826b1c5f27201730afc1c482b29520fd2047115b4249fb003388f87a6592')
MAX_PARENT_DEPTH = 128
REFERENCE_CORE = (ROOT / 'backtest/ndx_compact_history_runtime_registration_research_v1.py',
    'd0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')
DEPENDENCIES = {
    'capture_core': ('backtest/ndx_forward_parent_capture_research_v5.py', 'ddd570ab3a79832ef6d530693ade9ac37b8f82c18b13efe322558099a04a7e5e'),
    'parent_view': ('backtest/ndx_prospective_history_parent_view_research_v5.py', '32bcabfbc08a63607b650141f7295fc1ed12a3fdeeb081527c8b32d8cc250373'),
    'legacy_view': ('backtest/ndx_prospective_observation_parent_history_research_v4.py', '06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'),
    'compact_helpers': ('backtest/ndx_prospective_observation_parent_history_research.py', '1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'),
    'base': ('backtest/ndx_forward_source_capture_research.py', '30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'),
    'scoped': ('backtest/ndx_forward_source_capture_scoped_research.py', '9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee'),
}
CURRENT = {ticker: ROOT / 'data/cache' / (ticker + '.csv') for ticker in ('QQQ', 'SPY')}
FLAGS = dict.fromkeys((
    'source_authenticity_verified', 'parent_history_authenticated_by_this_module',
    'clock_authenticity_verified', 'timeliness_verified',
    'filesystem_attempt_inventory_authenticated', 'observation_created',
    'candidate_seal_allowed', 'cohort_registration_allowed', 'point_in_time_verified',
    'promotion_allowed', 'live_mutation_allowed', 'future_independent_oos',
    'production_generator_authorized', 'old_calendar_mutated',
    'network_quote_refresh_performed', 'full_transitive_source_closure_reverified',
    'network_capture_performed', 'seal_event_created', 'partial_recovery_performed',
    'canonical_calendar_append_allowed', 'retrospective_backfill_allowed',
    'decision_eligible', 'exchange_holidays_and_early_closes_verified',
), False)
MIN_FREE = 5 * 1024**3



PAIR_BINDING_CORE = (ROOT / 'backtest/ndx_compact_implementation_pair_binding_research_v1.py', 'dde8b681612d2b4fc0993bb9b697dcefb0222036d3e1bb6f4aa5f2dd76d7e4ad')
CONSUMER_REGISTRY_CORE = (ROOT / 'backtest/ndx_continuation_consumer_role_registry_research_v1.py', '184479c5e0e6412265e00cc875af1f7902e4f500dc984ca2aaaf3251bc8c433b')
CONSUMER_METADATA_CORE = (ROOT / 'backtest/ndx_continuation_consumer_metadata_research_v1.py', 'b0d16b1b364d2c32e55d826c1f9d63dfffeb27df7bcabfe972efd029e8e2fdeb')
ANCESTRY_CONTRACT = (ROOT / 'backtest/ndx_compact_ancestry_contract_research_v2.py', '081ba024fa997c37c1f030fcec7d4d22ca6411eec652d15a5049b57d62a31a76')
LEGACY_ANCESTRY_CONTRACT = (ROOT / 'backtest/ndx_compact_ancestry_contract_research_v1.py', '1f50f4d5a893c163149bf69593880f73a1387293ee04b2ab9c0fcbb58090fc5e')
# Root binds the reviewed final R2 bytes once the optional-C IO source is frozen.
SHARED_ANCESTRY_VERIFIER = (ROOT / 'scripts/ndx_registered_compact_history_independent_readback_20261009_v2.py', '5ceec753c972ecb5047311331285e5c7ec0ec67c361709f51ba101584498dddf')
CONSUMER_ROLE = 'capture_publisher'


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


def private_core(raw):
    modules={}
    for key in ('base','scoped','compact_helpers','legacy_view','parent_view','capture_core'):
        substitutions=[]
        if key=='scoped': substitutions=[('from backtest import ndx_forward_source_capture_research as capture','capture',modules['base'])]
        if key=='legacy_view': substitutions=[('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',modules['compact_helpers'])]
        if key=='parent_view': substitutions=[('from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy','legacy',modules['legacy_view'])]
        if key=='capture_core': substitutions=[
            ('from backtest.ndx_forward_source_capture_scoped_research import scoped_csv','scoped_csv',modules['scoped'].scoped_csv),
            ('from backtest import ndx_prospective_history_parent_view_research_v5 as parent_view','parent_view',modules['parent_view'])]
        path,expected=DEPENDENCIES[key]
        modules[key]=compile_private(ROOT/path,raw[key],expected,substitutions)
    core=modules['capture_core']
    require(core.SCOPED_PARSER_SHA256==DEPENDENCIES['scoped'][1] and
        core.PARSER_DEPENDENCY_SHA256==DEPENDENCIES['base'][1] and
        core.PARENT_VIEW_SHA256==DEPENDENCIES['parent_view'][1] and
        core.LEGACY_VIEW_SHA256==DEPENDENCIES['legacy_view'][1] and
        core.COMPACT_HELPER_SHA256==DEPENDENCIES['compact_helpers'][1], 'Capture dependency declarations')
    require(modules['parent_view'].LEGACY_VIEW_SHA256==DEPENDENCIES['legacy_view'][1] and
        modules['parent_view'].COMPACT_HELPER_SHA256==DEPENDENCIES['compact_helpers'][1] and
        modules['legacy_view'].DEPENDENCY_SHA256==DEPENDENCIES['compact_helpers'][1], 'Parent view helper binding')
    core._private_dependency_modules = modules
    return core


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


def read_current(path):
    path = safe(path)
    require(path.is_file() and path.stat().st_size <= 32 * 1024**2, 'Bounded regular current cache')
    raw = path.read_bytes()
    require(0 < len(raw) <= 32 * 1024**2, 'Bounded nonempty current bytes')
    return raw


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


def run(*, registration_path, registration_sha256, implementation_pair_binding_path,
        implementation_pair_binding_sha256, consumer_role_registry_path,
        consumer_role_registry_sha256, execute=False):
    require(execute is True, 'Explicit continuation capture execution')
    # Validate every configured and host-supplied anchor before source IO. The
    # pending shared-reader pin intentionally prevents unreviewed execution.
    configured_refs = {key: reference(str(value[0]), value[1]) for key, value in dict(
        registration_core=REGISTRATION_CORE, reference_core=REFERENCE_CORE,
        pair_binding_core=PAIR_BINDING_CORE, consumer_registry_core=CONSUMER_REGISTRY_CORE,
        consumer_metadata_contract=CONSUMER_METADATA_CORE, ancestry_contract=ANCESTRY_CONTRACT,
        legacy_ancestry_contract=LEGACY_ANCESTRY_CONTRACT,
        shared_ancestry_verifier=SHARED_ANCESTRY_VERIFIER,
        prefix_core=PREFIX_CORE, gap_core=GAP_CORE).items()}
    registration_ref = reference(str(registration_path), registration_sha256)
    binding_ref = reference(str(implementation_pair_binding_path), implementation_pair_binding_sha256)
    registry_ref = reference(str(consumer_role_registry_path), consumer_role_registry_sha256)
    runtime_ref = reference(str(SOURCE), LOADED_SHA)
    dependencies = configured(DEPENDENCIES)
    sources = {}
    registration_core, metadata = host_modules(sources, configured_refs)
    registration = decode(consume(registration_ref, sources))
    registered = registration_core.prepare_forward_capture_runtime(registration=registration,
        registration_reference=registration_ref, runtime_reference=runtime_ref,
        dependency_references=dependencies, research_root=str(RESEARCH))
    output = safe(registered['output_directory'])
    require(not output.exists(), 'Create-only namespace; no retry')
    reader_ref = configured_refs['shared_ancestry_verifier']
    reader = compile_private(reader_ref['path'], consume(reader_ref, sources), reader_ref['sha256'])
    reader.RESEARCH = RESEARCH
    reader.CURRENT = CURRENT
    replay = reader.verify_saved_parent_ancestry(parent_references=registered['parent'],
        implementation_pair_binding_path=binding_ref['path'], implementation_pair_binding_sha256=binding_ref['sha256'],
        consumer_role_registry_path=registry_ref['path'], consumer_role_registry_sha256=registry_ref['sha256'], execute=True)
    require(replay.get('status') == 'READ_ONLY_WHOLE_ANCESTRY_RECONSTRUCTION_PASS', 'Whole original parent replay')
    context = dict(bound_pair=replay['bound_pair'], consumer_registry_view=replay['consumer_registry_view'],
        consumer_registry_core_reference=replay['consumer_registry_core_reference'],
        metadata_contract_reference=replay['consumer_metadata_contract_reference'])
    require(context['consumer_registry_view'] is not None, 'Explicit host consumer family')
    require(context['bound_pair']['binding_reference'] == binding_ref
        and context['bound_pair']['contract_reference'] == configured_refs['ancestry_contract']
        and context['bound_pair']['independent_reader_reference'] == reader_ref
        and context['consumer_registry_view']['registry_reference'] == registry_ref
        and context['consumer_registry_core_reference'] == configured_refs['consumer_registry_core']
        and context['metadata_contract_reference'] == configured_refs['consumer_metadata_contract'], 'Independently fixed host kernel associations')
    require(context['consumer_registry_view']['consumer_references'][CONSUMER_ROLE] == runtime_ref,
        'Exact capture publisher self role')
    header = metadata.expected_consumer_metadata(consumer_role=CONSUMER_ROLE, **context)
    for path, value in replay['sources'].items():
        merge(sources, reference(path, value))
    for item in (*configured_refs.values(), runtime_ref, binding_ref, registry_ref, *dependencies.values()):
        consume(item, sources)
    raw = {role: consume(item, sources) for role, item in dependencies.items()}
    core = private_core(raw)
    parent = replay['parent_envelope']
    require({role: parent[role] for role in registration_core.PARENT_ROLES} == registered['parent'], 'Original replayed parent refs')
    history = core.parent_view.inspect_parent_history_v5(parent)
    require(history == replay['parent_view'], 'Exact detached normalized parent')
    baselines = {ticker: consume(history['accounted_baseline_references'][ticker], sources) for ticker in ('QQQ', 'SPY')}
    actual_baselines = {ticker: consume(history['baseline_references'][ticker], sources) for ticker in ('QQQ', 'SPY')}
    timezone_ref = history['tzif_reference']
    timezone_bytes = consume(timezone_ref, sources)
    inputs = dict(dependencies=dependencies, registration=registration_ref, runtime=runtime_ref,
        registration_core=configured_refs['registration_core'], reference_core=configured_refs['reference_core'],
        prefix_core=configured_refs['prefix_core'], gap_core=configured_refs['gap_core'], tzif=timezone_ref,
        **metadata.continuation_input_references(registered_dependency_references=dependencies,
            consumer_role=CONSUMER_ROLE, **context))
    metadata.inspect_producer_input_references(inputs, consumer_role=CONSUMER_ROLE,
        registered_dependency_references=dependencies, **context)

    created_outputs = {}

    def final_guard(live=None):
        replay['final_guard']()
        for path, value in list(sources.items()):
            consume(reference(path, value), {})
        for item in (live or {}).values():
            consume(item, {}, allow_current=True)
        if output.exists():
            namespace(output, created_outputs)
        for item in created_outputs.values():
            consume(item, {})

    final_guard()
    resource_gate(output.anchor)
    safe(output).mkdir(parents=True, exist_ok=False)
    try:
        started_ref = save(output / 'started.json', dict(schema='FORWARD_CAPTURE_STARTED_V5',
            parent_references=registered['parent'], input_references=inputs, source_hashes=dict(sources),
            retry_allowed=False, **header, **FLAGS))
        created_outputs['started.json'] = started_ref
        final_guard()
        start = now()
        current = {ticker: read_current(CURRENT[ticker]) for ticker in ('QQQ', 'SPY')}
        end = now()
        live = {ticker: reference(str(CURRENT[ticker]), digest(value)) for ticker, value in current.items()}
        final_guard(live)
        snapshots = {}
        for ticker, value in current.items():
            final_guard(live)
            snapshots[ticker] = save_bytes(output / (ticker + '.csv'), value)
            created_outputs[ticker + '.csv'] = snapshots[ticker]
        final_guard(live)
        timezone_snapshot = save_bytes(output / 'New_York.tzif', timezone_bytes)
        created_outputs['New_York.tzif'] = timezone_snapshot
        for item in (*snapshots.values(), timezone_snapshot):
            merge(sources, item)
        plan = core.plan_parent_capture(parent=parent, source_bytes=current, source_references=snapshots,
            accounted_baseline_bytes=baselines, actual_baseline_bytes=actual_baselines,
            capture_started_at=start, capture_completed_at=end, tzif_bytes=timezone_bytes,
            tzif_reference=timezone_snapshot)
        require(plan['schema'] == 'FORWARD_PARENT_CAPTURE_PLAN_V5' and plan['status'] in
            ('NO_NEW_SESSION', 'ONE_NEW_SESSION_CAPTURE_CANDIDATE', 'BLOCKED_SOURCE_DIAGNOSTICS'), 'True original plan role')
        for key in FLAGS:
            if key != 'network_quote_refresh_performed':
                require(plan.get(key) is False, 'Strict plan authority ' + key)
        for path, value in plan['source_reference_claims'].items():
            require(sources.get(path) == value, 'Plan claims do not select source IO')
        final_guard(live)
        capture = save(output / 'capture.json', dict(schema='SOURCE_BOUND_FORWARD_CAPTURE_V5',
            plan=plan, parent_references=registered['parent'], input_references=inputs,
            captured_artifacts=dict(snapshots, tzif=timezone_snapshot), current_cache_references=live,
            current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',
            capture_started_at=start, capture_completed_at=end, clock_captured_by_runner=True,
            external_clock_attestation_verified=False, quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',
            source_hashes=dict(sources), **header, **FLAGS))
        created_outputs['capture.json'] = capture
        final_guard(live)
        publication = save(output / 'publication.json', dict(schema='FORWARD_CAPTURE_PUBLICATION_V5',
            status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION', capture_reference=capture,
            source_hashes=dict(sources), **header, **FLAGS))
        created_outputs['publication.json'] = publication
        final_guard(live)
        for item in (started_ref, capture, publication):
            consume(item, {})
        namespace(output, metadata.NAMESPACE_FILES[CONSUMER_ROLE])
        return dict(capture_reference=capture, publication_reference=publication)
    except BaseException as error:
        save(output / 'failure.json', dict(status='FAILED_DO_NOT_CONSUME', error_type=type(error).__name__,
            retry_allowed=False, **FLAGS))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('registration-path', 'registration-sha256', 'implementation-pair-binding-path',
            'implementation-pair-binding-sha256', 'consumer-role-registry-path', 'consumer-role-registry-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--execute', action='store_true')
    arguments = vars(parser.parse_args())
    print(json.dumps(run(**{key.replace('-', '_'): value for key, value in arguments.items()})))
