"""Registered local V3/V4/V5 source capture; create-only, no network or observations."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
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
    require(type(sha256) is str and len(sha256) == 64 and
            all(char in '0123456789abcdef' for char in sha256), 'Pending immutable anchor')
    return dict(path=path, sha256=sha256)


def merge(sources, item):
    require(type(item) is dict and set(item) == {'path', 'sha256'}, 'Exact reference fields')
    reference(item['path'], item['sha256'])
    require(item['path'] not in sources or sources[item['path']] == item['sha256'], 'Source conflict')
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


def parent_namespaces(parent_refs):
    folder=Path(parent_refs['reference']['path']).parent
    require(Path(parent_refs['reference']['path'])==folder/'history.json' and
        Path(parent_refs['publication_reference']['path'])==folder/'publication.json', 'Parent artifact names')
    audit=Path(parent_refs['readback_reference']['path']).parent
    require(Path(parent_refs['readback_reference']['path'])==audit/'independent_readback.json', 'Parent audit artifact name')
    document = decode(consume(parent_refs['reference'], {}))
    schema = document['history']['schema']
    require(schema in ('PROSPECTIVE_GAP_EXTENSION_HISTORY_V3',
                       'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V4',
                       'PROSPECTIVE_GAP_EXTENSION_HISTORY_V5'), 'Supported true parent namespace')
    artifacts = {'started.json','history.json','publication.json'}
    if schema == 'PROSPECTIVE_GAP_EXTENSION_HISTORY_V5':
        artifacts |= {ticker + suffix for ticker in ('QQQ', 'SPY')
                      for suffix in ('.accounted_prefix.csv', '.prefix_evidence.json')}
    namespace(folder, artifacts |
        ({'independent_readback.json'} if audit==folder else set()))
    if audit!=folder: namespace(audit, ('started.json','independent_readback.json'))


def guard(sources, parent_refs, inventories=()):
    parent_namespaces(parent_refs)
    for kind, refs in inventories:
        if kind == 'parent': parent_namespaces(refs)
        else: capture_namespaces(refs)
    live = {path.resolve() for path in CURRENT.values()}
    for path, sha256 in list(sources.items()):
        require(Path(path).resolve() not in live, 'No persistent mutable cache source claim')
        consume(reference(path, sha256), {})


def guard_current(sources, parent_refs, live, inventories=()):
    guard(sources, parent_refs, inventories)
    for item in live.values():
        consume(item, {}, allow_current=True)


def configured(bound):
    return {key: reference(str(ROOT / path), sha256) for key, (path, sha256) in bound.items()}


def load_parent(parent_refs, sources):
    parent = dict(parent_refs)
    for role, key in (('document', 'reference'), ('publication', 'publication_reference'),
                      ('readback', 'readback_reference')):
        parent[role] = decode(consume(parent_refs[key], sources))
        for path, sha256 in parent[role]['source_hashes'].items():
            merge(sources, reference(path, sha256))
    consume(parent_refs['reader_reference'], sources)
    for path,digest_value in list(sources.items()): consume(reference(path,digest_value),sources)
    return parent


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


def pin_namespace(folder, names, sources):
    namespace(folder, names)
    for path in safe(folder).iterdir():
        path = safe(path)
        require(path.is_file() and path.stat().st_size <= 64 * 1024**2, 'Bounded upstream inventory file')
        consume(reference(str(path), digest(path.read_bytes())), sources)


def capture_namespaces(refs, sources=None):
    folder = Path(refs['reference']['path']).parent
    audit = Path(refs['readback_reference']['path']).parent
    require(Path(refs['reference']['path']) == folder / 'capture.json' and
            Path(refs['publication_reference']['path']) == folder / 'publication.json' and
            Path(refs['readback_reference']['path']) == audit / 'independent_readback.json',
            'Original capture artifact names')
    captured_names = ('started.json', 'QQQ.csv', 'SPY.csv', 'New_York.tzif', 'capture.json', 'publication.json')
    audit_names = ('started.json', 'independent_readback.json')
    if sources is None:
        namespace(folder, captured_names)
        namespace(audit, audit_names)
    else:
        pin_namespace(folder, captured_names, sources)
        pin_namespace(audit, audit_names, sources)


def private_evidence_core(raw, core, prefix_raw, gap_raw):
    modules = core._private_dependency_modules
    prefix = compile_private(PREFIX_CORE[0], prefix_raw, PREFIX_CORE[1], [
        ('from backtest import ndx_forward_source_capture_scoped_research as scoped_parser',
         'scoped_parser', modules['scoped'])])
    require(prefix.SCOPED_PARSER_SHA256 == DEPENDENCIES['scoped'][1] and
            prefix.BASE_PARSER_SHA256 == DEPENDENCIES['base'][1], 'Prefix parser dependency binding')
    gap = compile_private(GAP_CORE[0], gap_raw, GAP_CORE[1], [
        ('from backtest import ndx_accounted_source_prefix_research_v1 as prefix_core', 'prefix_core', prefix),
        ('from backtest import ndx_forward_source_capture_scoped_research as scoped_parser', 'scoped_parser', modules['scoped']),
        ('from backtest import ndx_prospective_history_parent_view_research_v5 as parent_view', 'parent_view', modules['parent_view']),
        ('from backtest import ndx_prospective_observation_parent_history_research as compact', 'compact', modules['compact_helpers'])])
    return prefix, gap


def verify_prior_capture(history, prior, core, sources, inventories):
    refs = history['capture_references']
    capture_namespaces(refs, sources)
    inventories.append(('capture', deepcopy(refs)))
    capture = load_parent(refs, sources)
    document, publication, audit = (capture[key] for key in ('document', 'publication', 'readback'))
    version = {'SOURCE_BOUND_FORWARD_CAPTURE_V4': 'V4', 'SOURCE_BOUND_FORWARD_CAPTURE_V5': 'V5'}.get(document.get('schema'))
    require(version is not None, 'Original capture true V4/V5 schema')
    require(publication['schema'] == 'FORWARD_CAPTURE_PUBLICATION_' + version and
            publication['status'] == 'PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION', 'Original capture publication contract')
    require(audit['schema'] == 'FORWARD_CAPTURE_INDEPENDENT_READBACK_' + version and
            audit['status'] == 'PURE_FORWARD_CAPTURE_READBACK_PASS', 'Original capture readback contract')
    core.exact(publication['capture_reference'], refs['reference'])
    core.exact(publication['source_hashes'], document['source_hashes'])
    core.exact(audit['capture_reference'], refs['reference'])
    core.exact(audit['publication_reference'], refs['publication_reference'])
    core.exact(audit['reader_sha256'], refs['reader_reference']['sha256'])
    core.exact(document['parent_references'], history['parent_references'])
    core.exact(audit['parent_references'], history['parent_references'])
    core.exact(audit['input_references'], document['input_references'])
    for obj in (document, publication, audit):
        for field in FLAGS:
            require(obj.get(field) is False, 'Original capture authority ' + field)
    for path, claim in document['source_hashes'].items():
        require(audit['source_hashes'].get(path) == claim, 'Original capture readback source closure')
    for role in ('reference', 'publication_reference', 'reader_reference'):
        item = refs[role]
        require(audit['source_hashes'].get(item['path']) == item['sha256'], 'Original capture readback reference closure')
    producer = audit['producer_reference']
    merge({}, producer)
    require(audit['source_hashes'].get(producer['path']) == producer['sha256'], 'Original capture producer reference closure')
    for field in ('capture_started_at', 'capture_completed_at'):
        core.exact(document[field], history[field])
    artifacts = document['captured_artifacts']
    require(type(artifacts) is dict and set(artifacts) == {'QQQ', 'SPY', 'tzif'}, 'Original capture artifact roles')
    folder = Path(refs['reference']['path']).parent
    for ticker in ('QQQ', 'SPY'):
        core.exact(artifacts[ticker], history['full_capture_source_references'][ticker])
        require(Path(artifacts[ticker]['path']) == folder / (ticker + '.csv'), 'Original capture snapshot path')
    core.exact(artifacts['tzif'], history['tzif_reference'])
    require(Path(artifacts['tzif']['path']) == folder / 'New_York.tzif', 'Original capture TZif path')
    previous = core.parent_view.inspect_parent_history_v5(prior)
    rebuilt = core.plan_parent_capture(parent=prior,
        source_bytes={t: consume(artifacts[t], sources) for t in ('QQQ', 'SPY')},
        source_references={t: artifacts[t] for t in ('QQQ', 'SPY')},
        accounted_baseline_bytes={t: consume(previous['accounted_baseline_references'][t], sources) for t in ('QQQ', 'SPY')},
        actual_baseline_bytes={t: consume(previous['baseline_references'][t], sources) for t in ('QQQ', 'SPY')},
        capture_started_at=document['capture_started_at'], capture_completed_at=document['capture_completed_at'],
        tzif_bytes=consume(artifacts['tzif'], sources), tzif_reference=artifacts['tzif'])
    if version == 'V4':
        # Project the archived plan's versioned fields; the parent remains its true envelope.
        rebuilt['schema'] = 'FORWARD_PARENT_CAPTURE_PLAN_V4'
        for field in ('actual_parent_schema', 'parent_full_capture_source_references',
                      'parent_pending_source_sessions', 'parent_excluded_not_completed_source_sessions'):
            rebuilt.pop(field)
        rebuilt['dependency_sha256'].pop('legacy_view')
        rebuilt['dependency_sha256']['parent_view'] = DEPENDENCIES['legacy_view'][1]
    core.exact(document['plan'], rebuilt, 'Original capture complete plan replay')
    diagnostic = document['current_cache_references']
    require(type(diagnostic) is dict and set(diagnostic) == {'QQQ', 'SPY'}, 'Original capture diagnostic source pair')
    for ticker, item in diagnostic.items():
        merge({}, item)
        core.exact(item['sha256'], artifacts[ticker]['sha256'], 'Original capture diagnostic snapshot SHA')
    core.exact(document, dict(schema='SOURCE_BOUND_FORWARD_CAPTURE_' + version, plan=rebuilt,
        parent_references=history['parent_references'], input_references=document['input_references'],
        captured_artifacts=artifacts, current_cache_references=diagnostic,
        current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',
        capture_started_at=history['capture_started_at'], capture_completed_at=history['capture_completed_at'],
        clock_captured_by_runner=True, external_clock_attestation_verified=False,
        quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',
        source_hashes=document['source_hashes'], **FLAGS), 'Original capture complete wrapper contract')
    core.exact(publication, dict(schema='FORWARD_CAPTURE_PUBLICATION_' + version,
        status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION', capture_reference=refs['reference'],
        source_hashes=document['source_hashes'], **FLAGS), 'Original capture complete publication contract')
    require(audit.get('external_clock_attestation_verified') is False, 'Original capture external clock authority')
    nested = {}
    for value in (document['input_references'], document['parent_references'], artifacts, rebuilt):
        core.inventory_references(value, nested)
    for path, claim in nested.items():
        require(document['source_hashes'].get(path) == claim, 'Original capture nested reference closure')
    nested = {}
    core.inventory_references(audit, nested)
    for path, claim in nested.items():
        require(audit['source_hashes'].get(path) == claim, 'Original capture audit nested reference closure')
    core.exact(document['plan']['source_evidence'], history['source_evidence'])
    counts = dict(status=rebuilt['status'], parent_typed_row_count=len(rebuilt['known_typed_rows']),
        parent_actual_observation_count=len(rebuilt['observations']),
        parent_observed_count=sum(row['kind'] != 'MISSED_OBSERVATION' for row in rebuilt['known_typed_rows']),
        parent_gap_count=sum(row['kind'] == 'MISSED_OBSERVATION' for row in rebuilt['known_typed_rows']),
        candidate_session=rebuilt['candidate_session'], diagnostic_count=len(rebuilt['diagnostics']),
        snapshot_counts={t: rebuilt['source_evidence'][t]['original_row_count'] for t in ('QQQ', 'SPY')})
    core.exact(audit['counts'], counts)
    for field in ('entire_plan_independently_reconstructed', 'snapshot_bytes_verified'):
        require(audit.get(field) is True, 'Original capture readback evidence role')
    for field in ('producer_called', 'capture_core_called', 'current_live_cache_read_or_reverified'):
        require(audit.get(field) is False, 'Original capture readback execution role')


def verify_parent_chain(parent, core, prefix_core, gap_core, sources):
    """Replay supplied V5 artifacts against originals without granting authority."""
    visited, inventories = set(), []
    for depth in range(MAX_PARENT_DEPTH):
        item = parent['reference']
        identity = (str(safe(item['path']).resolve()).casefold(), item['sha256'])
        require(identity not in visited, 'Parent reference cycle')
        visited.add(identity)
        refs = {role: parent[role] for role in ('reference', 'publication_reference', 'readback_reference', 'reader_reference')}
        parent_namespaces(refs)
        inventories.append(('parent', deepcopy(refs)))
        for folder in {Path(refs['reference']['path']).parent, Path(refs['readback_reference']['path']).parent}:
            pin_namespace(folder, {path.name for path in folder.iterdir()}, sources)
        normalized = core.parent_view.inspect_parent_history_v5(parent)
        if normalized['parent_schema'] != 'PROSPECTIVE_GAP_EXTENSION_HISTORY_V5':
            return inventories
        history = parent['document']['history']
        folder = Path(parent['reference']['path']).parent
        for ticker in ('QQQ', 'SPY'):
            core.exact(history['accounted_prefix_references'][ticker]['path'],
                       str(folder / (ticker + '.accounted_prefix.csv')), 'Parent prefix artifact path')
            core.exact(history['accounted_prefix_evidence_references'][ticker]['path'],
                       str(folder / (ticker + '.prefix_evidence.json')), 'Parent prefix evidence artifact path')
        parent_namespaces(history['parent_references'])
        prior = load_parent(history['parent_references'], sources)
        previous = core.parent_view.inspect_parent_history_v5(prior)
        core.exact(core.parent_view.parent_state_for_gap(previous), history['prior_state_preserved'],
                   'Original parent normalized state must match preserved state')
        verify_prior_capture(history, prior, core, sources, inventories)
        known = [row['session'] for row in history['known_typed_rows']]
        for ticker in ('QQQ', 'SPY'):
            expected, evidence = prefix_core.derive_accounted_prefix(
                source_bytes=consume(history['full_capture_source_references'][ticker], sources),
                source_reference=history['full_capture_source_references'][ticker], accounted_sessions=known, scope_start=known[0])
            require(consume(history['accounted_prefix_references'][ticker], sources) == expected,
                    'Original accounted prefix bytes')
            require(consume(history['accounted_prefix_evidence_references'][ticker], sources) == gap_core.prefix_evidence_bytes(evidence),
                    'Complete original prefix evidence artifact')
            core.exact(history['accounted_prefix_evidence'][ticker], gap_core.prefix_evidence_summary(evidence))
        replay = gap_core.extend_gap_history(parent=prior, capture_references=history['capture_references'],
            source_bytes={t: consume(history['full_capture_source_references'][t], sources) for t in ('QQQ', 'SPY')},
            source_references=history['full_capture_source_references'],
            accounted_baseline_bytes={t: consume(previous['accounted_baseline_references'][t], sources) for t in ('QQQ', 'SPY')},
            actual_baseline_bytes={t: consume(previous['baseline_references'][t], sources) for t in ('QQQ', 'SPY')},
            prefix_references=history['accounted_prefix_references'],
            prefix_evidence_references=history['accounted_prefix_evidence_references'],
            capture_started_at=history['capture_started_at'], capture_completed_at=history['capture_completed_at'],
            tzif_bytes=consume(history['tzif_reference'], sources), tzif_reference=history['tzif_reference'])
        core.exact(history, replay, 'Entire original gap history replay')
        parent = prior
    raise ValueError('Parent chain maximum depth exceeded')


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


def run(*, registration_path, registration_sha256, execute=False):
    require(execute is True, 'Explicit registered V5 source capture')
    # All configured/passed anchors validate before any source IO.
    regcore_ref=reference(str(REGISTRATION_CORE[0]),REGISTRATION_CORE[1])
    refcore_ref=reference(str(REFERENCE_CORE[0]),REFERENCE_CORE[1])
    registration_ref=reference(str(registration_path),registration_sha256)
    dependency_refs=configured(DEPENDENCIES)
    prefix_ref=reference(str(PREFIX_CORE[0]),PREFIX_CORE[1])
    gap_ref=reference(str(GAP_CORE[0]),GAP_CORE[1])
    runtime_ref=reference(str(SOURCE),LOADED_SHA)
    sources={};consume(runtime_ref,sources)
    refcore=compile_private(REFERENCE_CORE[0],consume(refcore_ref,sources),REFERENCE_CORE[1])
    regcore=compile_private(REGISTRATION_CORE[0],consume(regcore_ref,sources),REGISTRATION_CORE[1], [
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',refcore)])
    require(regcore.REFERENCE_KERNEL_SHA256==REFERENCE_CORE[1], 'Registration reference kernel binding')
    registration=decode(consume(registration_ref,sources))
    registered=regcore.prepare_forward_capture_runtime(registration=registration,registration_reference=registration_ref,
        runtime_reference=runtime_ref,dependency_references=dependency_refs,research_root=str(RESEARCH))
    output=safe(registered['output_directory']);require(not output.exists(), 'Create-only namespace; no retry')
    parent_refs=registered['parent']
    raw={key:consume(item,sources)for key,item in dependency_refs.items()}
    core=private_core(raw)
    prefix_core,gap_core=private_evidence_core(raw,core,consume(prefix_ref,sources),consume(gap_ref,sources))
    parent_namespaces(parent_refs)
    parent=load_parent(parent_refs,sources)
    parent_chain_inventories=verify_parent_chain(parent,core,prefix_core,gap_core,sources)
    history=core.parent_view.inspect_parent_history_v5(parent)
    baselines={ticker:consume(history['accounted_baseline_references'][ticker],sources)for ticker in ('QQQ','SPY')}
    actual_baselines={ticker:consume(history['baseline_references'][ticker],sources)for ticker in ('QQQ','SPY')}
    timezone_reference=history['tzif_reference'];timezone_bytes=consume(timezone_reference,sources)
    # Pin inventory bytes too; exact inventory alone cannot detect START drift.
    parent_namespaces(parent_refs)
    folders={Path(parent_refs[key]['path']).parent for key in ('reference','readback_reference')}
    for folder in folders:
        for file in folder.iterdir():
            file=safe(file)
            require(file.is_file() and file.stat().st_size<=64*1024**2, 'Bounded parent inventory file')
            consume(reference(str(file),digest(file.read_bytes())),sources)
    inputs=dict(dependencies=dependency_refs,registration=registration_ref,runtime=runtime_ref,
        registration_core=regcore_ref,reference_core=refcore_ref,prefix_core=prefix_ref,gap_core=gap_ref,tzif=timezone_reference)
    guard(sources, parent_refs, parent_chain_inventories)
    resource_gate(output.anchor)
    safe(output).mkdir(parents=True, exist_ok=False)
    try:
        started_ref = save(output / 'started.json', dict(schema='FORWARD_CAPTURE_STARTED_V5',
             parent_references=parent_refs, input_references=inputs, source_hashes=dict(sources),
             retry_allowed=False, **FLAGS))
        guard(sources, parent_refs, parent_chain_inventories)
        start = now()
        current = {ticker: read_current(CURRENT[ticker]) for ticker in ('QQQ', 'SPY')}
        end = now()
        live = {ticker: reference(str(CURRENT[ticker]), digest(value)) for ticker, value in current.items()}
        guard_current(sources, parent_refs, live, parent_chain_inventories)
        snapshots = {ticker: save_bytes(output / (ticker + '.csv'), value)
                     for ticker, value in current.items()}
        timezone_snapshot = save_bytes(output / 'New_York.tzif', timezone_bytes)
        for item in (*snapshots.values(), timezone_snapshot):
            merge(sources, item)
        plan = core.plan_parent_capture(parent=parent, source_bytes=current,
            source_references=snapshots, accounted_baseline_bytes=baselines,
            actual_baseline_bytes=actual_baselines, capture_started_at=start,
            capture_completed_at=end, tzif_bytes=timezone_bytes, tzif_reference=timezone_snapshot)
        require(plan['schema'] == 'FORWARD_PARENT_CAPTURE_PLAN_V5', 'Exact plan schema')
        require(plan['status'] in ('NO_NEW_SESSION', 'ONE_NEW_SESSION_CAPTURE_CANDIDATE',
                                  'BLOCKED_SOURCE_DIAGNOSTICS'), 'Exact plan status')
        for field in FLAGS:
            if field != 'network_quote_refresh_performed':
                require(plan.get(field) is False, 'Strict plan authority ' + field)
        for path, sha256 in plan['source_reference_claims'].items():
            require(sources.get(path) == sha256, 'Plan claim outside immutable source closure')
        guard_current(sources, parent_refs, live, parent_chain_inventories)
        capture = save(output / 'capture.json', dict(schema='SOURCE_BOUND_FORWARD_CAPTURE_V5',
            plan=plan, parent_references=parent_refs, input_references=inputs,
            captured_artifacts=dict(snapshots, tzif=timezone_snapshot), current_cache_references=live,
            current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',
            capture_started_at=start, capture_completed_at=end, clock_captured_by_runner=True,
            external_clock_attestation_verified=False, quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',
            source_hashes=dict(sources), **FLAGS))
        publication = save(output / 'publication.json', dict(schema='FORWARD_CAPTURE_PUBLICATION_V5',
            status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION', capture_reference=capture,
            source_hashes=dict(sources), **FLAGS))
        guard_current(sources, parent_refs, live, parent_chain_inventories)
        for item in (started_ref, capture, publication):
            consume(item, {})
        namespace(output, ('started.json', 'QQQ.csv', 'SPY.csv', 'New_York.tzif', 'capture.json', 'publication.json'))
        return dict(capture_reference=capture, publication_reference=publication)
    except BaseException as error:
        save(output / 'failure.json', dict(status='FAILED_DO_NOT_CONSUME', error_type=type(error).__name__,
            retry_allowed=False, **FLAGS))
        raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    parser.add_argument('--registration-path',required=True);parser.add_argument('--registration-sha256',required=True)
    args=parser.parse_args();print(json.dumps(run(registration_path=args.registration_path,
        registration_sha256=args.registration_sha256,execute=args.execute)))
