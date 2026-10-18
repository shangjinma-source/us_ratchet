"""Host-bound independent continuation capture reconstruction.

The shared reader verifies ancestors. Capture arithmetic uses the frozen
independent 461 plan formula and c9 CSV parser; producer code never executes.
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
CONSUMER_ROLE = 'capture_independent_reader'


CAPTURE_PLAN_RECONSTRUCTOR = (ROOT / 'scripts/ndx_registered_forward_capture_independent_readback_20261009_v2.py', '461cbb0d792001a4096a4c5a4caa701685b245b4989c2aa685f2c03e34ac6ca1')
CSV_READER = (ROOT / 'backtest/ndx_capture_source_csv_independent_reconstruction_research_v1.py', 'c9dbb1c15c12d84910842874d1800d09c73d90893b91d54865826bf240ef9787')


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


def exact(left, right, message):
    require(encode(left) == encode(right), message)


def private_parent_checker(raw):
    helper = compile_private(ROOT / DEPENDENCIES['compact_helpers'][0], raw['compact_helpers'], DEPENDENCIES['compact_helpers'][1])
    legacy = compile_private(ROOT / DEPENDENCIES['legacy_view'][0], raw['legacy_view'], DEPENDENCIES['legacy_view'][1], [
        ('from backtest import ndx_prospective_observation_parent_history_research as compact', 'compact', helper)])
    return compile_private(ROOT / DEPENDENCIES['parent_view'][0], raw['parent_view'], DEPENDENCIES['parent_view'][1], [
        ('from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy', 'legacy', legacy)])


def readback(*, registration_path, registration_sha256, capture_reference, publication_reference,
        output_directory, implementation_pair_binding_path, implementation_pair_binding_sha256,
        consumer_role_registry_path, consumer_role_registry_sha256, execute=False):
    require(type(execute) is bool, 'Explicit bool')
    if not execute:
        return dict(status='NOT_EXECUTED')
    fixed = {key: reference(str(value[0]), value[1]) for key, value in dict(
        registration_core=REGISTRATION_CORE, reference_core=REFERENCE_CORE,
        pair_binding_core=PAIR_BINDING_CORE, consumer_registry_core=CONSUMER_REGISTRY_CORE,
        consumer_metadata_contract=CONSUMER_METADATA_CORE, ancestry_contract=ANCESTRY_CONTRACT,
        legacy_ancestry_contract=LEGACY_ANCESTRY_CONTRACT, shared_ancestry_verifier=SHARED_ANCESTRY_VERIFIER,
        prefix_core=PREFIX_CORE, gap_core=GAP_CORE).items()}
    independent = dict(capture_plan_reconstructor=reference(str(CAPTURE_PLAN_RECONSTRUCTOR[0]), CAPTURE_PLAN_RECONSTRUCTOR[1]),
        csv_reader=reference(str(CSV_READER[0]), CSV_READER[1]))
    registration_ref = reference(str(registration_path), registration_sha256)
    binding_ref = reference(str(implementation_pair_binding_path), implementation_pair_binding_sha256)
    registry_ref = reference(str(consumer_role_registry_path), consumer_role_registry_sha256)
    self_ref = reference(str(SOURCE), LOADED_SHA)
    merge({}, capture_reference)
    merge({}, publication_reference)
    output = safe(output_directory)
    output_key = PureWindowsPath(str(output))
    require(output_key.parent == PureWindowsPath(str(RESEARCH))
        and re.fullmatch(r'[a-z][a-z0-9_]{2,119}', output_key.name) is not None
        and not output.exists(), 'Independent create-only direct namespace')
    dependencies = configured(DEPENDENCIES)
    bootstrap_sources = {}
    registration_core, metadata = host_modules(bootstrap_sources, fixed)
    shared_ref = fixed['shared_ancestry_verifier']
    shared = compile_private(shared_ref['path'], consume(shared_ref, bootstrap_sources), shared_ref['sha256'])
    shared.RESEARCH = RESEARCH
    shared.CURRENT = CURRENT
    family_args = dict(implementation_pair_binding_path=binding_ref['path'], implementation_pair_binding_sha256=binding_ref['sha256'],
        consumer_role_registry_path=registry_ref['path'], consumer_role_registry_sha256=registry_ref['sha256'], execute=True)
    family = shared.inspect_host_continuation_family(**family_args)
    context = dict(bound_pair=family['bound_pair'], consumer_registry_view=family['consumer_registry_view'],
        consumer_registry_core_reference=family['consumer_registry_core_reference'],
        metadata_contract_reference=family['consumer_metadata_contract_reference'])
    require(context['consumer_registry_view'] is not None, 'Explicit host continuation family')
    pair, consumers = context['bound_pair'], context['consumer_registry_view']
    exact(pair['binding_reference'], binding_ref, 'Independent host pair')
    exact(pair['contract_reference'], fixed['ancestry_contract'], 'Fixed ancestry contract')
    exact(pair['independent_reader_reference'], shared_ref, 'Fixed complete ancestry verifier')
    exact(consumers['registry_reference'], registry_ref, 'Independent host consumer registry')
    exact(context['consumer_registry_core_reference'], fixed['consumer_registry_core'], 'Fixed role kernel')
    exact(context['metadata_contract_reference'], fixed['consumer_metadata_contract'], 'Fixed metadata kernel')
    exact(consumers['consumer_references'][CONSUMER_ROLE], self_ref, 'Exact reader self role')
    producer_ref = consumers['consumer_references']['capture_publisher']
    producer_header = metadata.expected_consumer_metadata(consumer_role='capture_publisher', **context)
    reader_header = metadata.expected_consumer_metadata(consumer_role=CONSUMER_ROLE, **context)
    registration = decode(consume(registration_ref, bootstrap_sources))
    registered = registration_core.prepare_forward_capture_runtime(registration=registration,
        registration_reference=registration_ref, runtime_reference=producer_ref,
        dependency_references=dependencies, research_root=str(RESEARCH))
    capture_folder = safe(registered['output_directory'])
    require(capture_folder != output, 'Distinct producer/reader namespaces')
    exact(capture_reference['path'], str(capture_folder / 'capture.json'), 'Original capture filename')
    exact(publication_reference['path'], str(capture_folder / 'publication.json'), 'Original publication filename')
    namespace(capture_folder, metadata.NAMESPACE_FILES['capture_publisher'])
    documents = {}
    sources = {}
    for name, item in (('capture', capture_reference), ('publication', publication_reference)):
        documents[name] = decode(consume(item, sources))
        metadata.inspect_consumer_metadata(documents[name], expected_role='capture_publisher', **context)
    document, publication = documents['capture'], documents['publication']
    document_keys = {'schema', 'plan', 'parent_references', 'input_references', 'captured_artifacts',
        'current_cache_references', 'current_cache_verification_scope', 'capture_started_at', 'capture_completed_at',
        'clock_captured_by_runner', 'external_clock_attestation_verified', 'quote_source_type', 'source_hashes',
        *metadata.METADATA_KEYS, *FLAGS}
    publication_keys = {'schema', 'status', 'capture_reference', 'source_hashes', *metadata.METADATA_KEYS, *FLAGS}
    require(set(document) == document_keys and set(publication) == publication_keys, 'Closed continuation capture wrappers')
    expected_input_keys = {'dependencies', 'registration', 'runtime', 'registration_core', 'reference_core',
        'prefix_core', 'gap_core', 'tzif', 'registration_dependency_references', 'implementation_pair_binding',
        'consumer_role_registry', 'ancestry_contract', 'shared_ancestry_verifier', 'consumer_registry_core', 'consumer_metadata_contract'}
    require(type(document['input_references']) is dict and set(document['input_references']) == expected_input_keys,
        'Closed original producer common input')
    metadata.inspect_producer_input_references(document['input_references'], consumer_role='capture_publisher',
        registered_dependency_references=dependencies, **context)
    exact(document['parent_references'], registered['parent'], 'Original registered parent')
    replay = shared.verify_saved_parent_ancestry(parent_references=registered['parent'], **family_args)
    require(replay.get('status') == 'READ_ONLY_WHOLE_ANCESTRY_RECONSTRUCTION_PASS', 'Whole original parent reconstruction')
    exact(replay['bound_pair'], pair, 'Same host pair between preflight and replay')
    exact(replay['consumer_registry_view'], consumers, 'Same host consumer roles between preflight and replay')
    parent = replay['parent_envelope']
    initial = {}
    for path, value in replay['sources'].items():
        merge(initial, reference(path, value))
    for item in (*fixed.values(), producer_ref, registration_ref, binding_ref, registry_ref, *dependencies.values()):
        consume(item, initial)
    raw = {role: consume(item, initial) for role, item in dependencies.items()}
    checker = private_parent_checker(raw)
    view = checker.inspect_parent_history_v5(parent)
    exact(view, replay['parent_view'], 'Original normalized parent evidence')
    accounted = {ticker: consume(view['accounted_baseline_references'][ticker], initial) for ticker in ('QQQ', 'SPY')}
    actual = {ticker: consume(view['baseline_references'][ticker], initial) for ticker in ('QQQ', 'SPY')}
    original_timezone = view['tzif_reference']
    consume(original_timezone, initial)
    inputs = dict(dependencies=dependencies, registration=registration_ref, runtime=producer_ref,
        registration_core=fixed['registration_core'], reference_core=fixed['reference_core'],
        prefix_core=fixed['prefix_core'], gap_core=fixed['gap_core'], tzif=original_timezone,
        **metadata.continuation_input_references(registered_dependency_references=dependencies,
            consumer_role='capture_publisher', **context))
    exact(document['input_references'], inputs, 'Whole independently reconstructed producer input')
    artifacts = document['captured_artifacts']
    require(type(artifacts) is dict and set(artifacts) == {'QQQ', 'SPY', 'tzif'}, 'Closed saved snapshot roles')
    expected_sources = deepcopy(initial)
    for key, item in artifacts.items():
        merge({}, item)
        exact(item['path'], str(capture_folder / ('New_York.tzif' if key == 'tzif' else key + '.csv')), 'Code-fixed snapshot filename')
        merge(expected_sources, item)
    for path, value in expected_sources.items():
        merge(sources, reference(path, value))
    snapshots = {ticker: consume(artifacts[ticker], sources) for ticker in ('QQQ', 'SPY')}
    timezone_bytes = consume(artifacts['tzif'], sources)
    exact(artifacts['tzif']['sha256'], original_timezone['sha256'], 'Original timezone bytes')
    exact(document['current_cache_references'],
        {ticker: reference(str(CURRENT[ticker]), artifacts[ticker]['sha256']) for ticker in ('QQQ', 'SPY')}, 'Diagnostic current refs only')
    csv_module = compile_private(CSV_READER[0], consume(independent['csv_reader'], sources), CSV_READER[1])
    formula = compile_private(CAPTURE_PLAN_RECONSTRUCTOR[0], consume(independent['capture_plan_reconstructor'], sources), CAPTURE_PLAN_RECONSTRUCTOR[1])
    expected = formula.reconstruct_plan(parent=parent, source_bytes=snapshots,
        source_references={ticker: artifacts[ticker] for ticker in ('QQQ', 'SPY')},
        accounted_baseline_bytes=accounted, actual_baseline_bytes=actual,
        capture_started_at=document['capture_started_at'], capture_completed_at=document['capture_completed_at'],
        tzif_bytes=timezone_bytes, tzif_reference=artifacts['tzif'], parent_checker=checker, csv_rows=csv_module.csv_rows)
    exact(document, dict(schema='SOURCE_BOUND_FORWARD_CAPTURE_V5', plan=expected, parent_references=registered['parent'],
        input_references=inputs, captured_artifacts=artifacts, current_cache_references=document['current_cache_references'],
        current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',
        capture_started_at=document['capture_started_at'], capture_completed_at=document['capture_completed_at'],
        clock_captured_by_runner=True, external_clock_attestation_verified=False,
        quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH', source_hashes=expected_sources,
        **producer_header, **FLAGS), 'Whole independent continuation capture')
    exact(publication, dict(schema='FORWARD_CAPTURE_PUBLICATION_V5', status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION',
        capture_reference=capture_reference, source_hashes=expected_sources, **producer_header, **FLAGS), 'Whole independent publication')
    startpath = safe(capture_folder / 'started.json')
    require(startpath.is_file() and startpath.stat().st_size <= 64 * 1024**2, 'Bounded producer START')
    startbytes = startpath.read_bytes()
    startref = reference(str(startpath), digest(startbytes))
    consume(startref, sources)
    exact(decode(startbytes), dict(schema='FORWARD_CAPTURE_STARTED_V5', parent_references=registered['parent'],
        input_references=inputs, source_hashes=initial, retry_allowed=False, **producer_header, **FLAGS), 'Whole independent producer START')
    private_inputs = dict(runtime=self_ref, dependencies=dependencies, auxiliary_dependencies={},
        independent_dependencies=independent, registration_core=fixed['registration_core'], reference_core=fixed['reference_core'],
        pair_binding_core=fixed['pair_binding_core'], implementation_pair_binding=binding_ref, consumer_role_registry=registry_ref,
        ancestry_contract=fixed['ancestry_contract'], shared_ancestry_verifier=shared_ref,
        consumer_registry_core=fixed['consumer_registry_core'], consumer_metadata_contract=fixed['consumer_metadata_contract'])
    consume(self_ref, sources)
    created_outputs = {}

    def final_guard():
        family['final_guard']()
        replay['final_guard']()
        namespace(capture_folder, metadata.NAMESPACE_FILES['capture_publisher'])
        for path, value in list(sources.items()):
            consume(reference(path, value), {})
        if output.exists():
            namespace(output, created_outputs)
        for item in created_outputs.values():
            consume(item, {})

    final_guard()
    resource_gate(output.anchor)
    output.mkdir(parents=True, exist_ok=False)
    try:
        own_start = save(output / 'started.json', dict(schema='FORWARD_CAPTURE_READBACK_STARTED_V5',
            capture_reference=capture_reference, publication_reference=publication_reference,
            registration_reference=registration_ref, reader_sha256=LOADED_SHA,
            input_references=inputs, reader_input_references=private_inputs, **reader_header, **FLAGS))
        created_outputs['started.json'] = own_start
        merge(sources, own_start)
        final_guard()
        report = save(output / 'independent_readback.json', dict(schema='FORWARD_CAPTURE_INDEPENDENT_READBACK_V5',
            status='PURE_FORWARD_CAPTURE_READBACK_PASS', capture_reference=capture_reference,
            publication_reference=publication_reference, parent_references=registered['parent'], input_references=inputs,
            reader_input_references=private_inputs, producer_reference=producer_ref, reader_sha256=LOADED_SHA,
            source_hashes=dict(sources), counts=dict(status=expected['status'], parent_typed_row_count=len(expected['known_typed_rows']),
                parent_actual_observation_count=len(expected['observations']),
                parent_observed_count=sum(row['kind'] != 'MISSED_OBSERVATION' for row in expected['known_typed_rows']),
                parent_gap_count=sum(row['kind'] == 'MISSED_OBSERVATION' for row in expected['known_typed_rows']),
                candidate_session=expected['candidate_session'], diagnostic_count=len(expected['diagnostics']),
                snapshot_counts={ticker: expected['source_evidence'][ticker]['original_row_count'] for ticker in ('QQQ', 'SPY')}),
            entire_plan_independently_reconstructed=True, snapshot_bytes_verified=True, producer_called=False, capture_core_called=False,
            csv_reader_reference=independent['csv_reader'],
            csv_resource_semantics='MAX_8000000_SOURCE_BYTES_MAX_20000_DATA_ROWS_BLANK_RECORDS_EXCLUDED_NO_EXTRA_PHYSICAL_LINE_LIMIT',
            current_live_cache_read_or_reverified=False, external_clock_attestation_verified=False,
            shared_upstream_parent_checker_reference=dependencies['parent_view'],
            shared_legacy_parent_checker_reference=dependencies['legacy_view'], shared_parent_checker_called=True,
            prefix_core_called_for_parent_evidence_only=False, gap_core_called=False,
            parent_chain_and_original_prefix_bytes_reverified=True, actual_parent_schema=view['parent_schema'],
            reconstruction_scope='INDEPENDENT_CAPTURE_PLAN_FROM_BOUND_PARENT_SHARED_PARENT_INSPECTOR_NOT_SOURCE_OR_CLOCK_AUTHENTICATION',
            started_reference_observed_not_external_anchor=startref, started_externally_authenticated=False,
            reader_started_reference_observed_not_external_anchor=own_start, reader_started_externally_authenticated=False,
            **reader_header, **FLAGS))
        created_outputs['independent_readback.json'] = report
        final_guard()
        return report
    except BaseException as error:
        save(output / 'failure.json', dict(status='FAILED_DO_NOT_CONSUME', error_type=type(error).__name__,
            automatic_retry_allowed=False, **FLAGS))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('registration-path', 'registration-sha256', 'capture-path', 'capture-sha256',
            'publication-path', 'publication-sha256', 'output-directory', 'implementation-pair-binding-path',
            'implementation-pair-binding-sha256', 'consumer-role-registry-path', 'consumer-role-registry-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--execute', action='store_true')
    arguments = vars(parser.parse_args())
    arguments['capture_reference'] = reference(arguments.pop('capture_path'), arguments.pop('capture_sha256'))
    arguments['publication_reference'] = reference(arguments.pop('publication_path'), arguments.pop('publication_sha256'))
    print(json.dumps(readback(**arguments)))
