"""Create-only local source capture for the independently read V3 gap parent."""
import argparse
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
OUTPUT = ROOT / 'data/cache/research/forward_gap_parent_source_capture_20261009_v3'
PURE = ROOT / 'backtest/ndx_forward_gap_parent_capture_research_v3.py'
PURE_SHA = 'e179a621023a478ff0824d41243ceafaceb0aa2bc6b9a80998f7c03f0d5721f8'
PARENT_BOUND = {
    'reference': ('data/cache/research/prospective_gap_history_20261009_v3/history.json', '600d15deb7cdcbc74fb13337c279d31c910d9389088ebc8668ea650779fdfd8a'),
    'publication_reference': ('data/cache/research/prospective_gap_history_20261009_v3/publication.json', '3ff2cf28d954e64ed7a21af6d8b7ed5465c7cf2fe5c6fd7d057cd43e4cddfe10'),
    'readback_reference': ('data/cache/research/prospective_gap_history_independent_readback_20261009_v3/independent_readback.json', '86e867fa73f28b9a436472eb27848a159a75e5de4bcf97e7a4b69b6a1be98912'),
    'reader_reference': ('scripts/ndx_prospective_gap_history_independent_readback_20261009_v3.py', '2be765c5dafcb85366e4e84d3a8cbed2037a6924649695f3ab176764075791f8'),
}
DEPENDENCIES = {
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
    for ancestor in (path, *path.parents):
        require(not ancestor.is_symlink() and not getattr(ancestor, 'is_junction', lambda: False)(),
                'Linked source/output forbidden')
    return path


def consume(item, sources):
    merge(sources, item)
    path = safe(item['path'])
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
    namespace(Path(parent_refs['reference']['path']).parent,
              ('started.json', 'history.json', 'publication.json'))
    namespace(Path(parent_refs['readback_reference']['path']).parent,
              ('started.json', 'independent_readback.json'))


def guard(sources, parent_refs):
    parent_namespaces(parent_refs)
    live = {path.resolve() for path in CURRENT.values()}
    for path, sha256 in sources.items():
        require(Path(path).resolve() not in live, 'No persistent mutable cache source claim')
        consume(reference(path, sha256), {})


def guard_current(sources, parent_refs, live):
    guard(sources, parent_refs)
    for item in live.values():
        consume(item, {})


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
    return parent


def private_core(raw):
    modules = {}
    imports = {
        'scoped': ('from backtest import ndx_forward_source_capture_research as capture', 'capture', 'base'),
        'pure': ('from backtest.ndx_forward_source_capture_scoped_research import scoped_csv', 'scoped_csv', 'scoped'),
    }
    for key in ('base', 'scoped', 'pure'):
        path = PURE if key == 'pure' else ROOT / DEPENDENCIES[key][0]
        expected = PURE_SHA if key == 'pure' else DEPENDENCIES[key][1]
        require(digest(raw[key]) == expected, 'Private dependency SHA')
        module = ModuleType('_gap_parent_capture_' + key)
        module.__file__ = str(path)
        code = raw[key].decode('utf-8-sig')
        if key in imports:
            line, attribute, dependency = imports[key]
            require(code.count(line) == 1, 'Explicit private import ' + key)
            code = code.replace(line, '')
            module.__dict__[attribute] = modules[dependency].scoped_csv if key == 'pure' else modules[dependency]
        exec(compile(code, str(path), 'exec'), module.__dict__)
        modules[key] = module
    require(modules['pure'].SCOPED_PARSER_SHA256 == DEPENDENCIES['scoped'][1] and
            modules['pure'].PARSER_DEPENDENCY_SHA256 == DEPENDENCIES['base'][1], 'Parser declarations')
    return modules['pure']


def resource_gate(size=0):
    require(type(size) is int and size >= 0, 'Exact nonnegative reserve')
    require(shutil.disk_usage(Path(OUTPUT.anchor)).free >= MIN_FREE + size, 'RESOURCE_STOP_BEFORE_WRITE')


def save_bytes(path, raw):
    if path.name != 'failure.json':
        resource_gate(len(raw))
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


def run(*, execute=False):
    require(execute is True, 'Explicit V3 source capture')
    pure_reference = reference(str(PURE), PURE_SHA)
    parent_refs = configured(PARENT_BOUND)
    dependency_refs = configured(DEPENDENCIES)
    require(not OUTPUT.exists(), 'Create-only namespace; no retry')
    sources = {str(SOURCE): LOADED_SHA}
    raw = {key: consume(item, sources) for key, item in dependency_refs.items()}
    raw['pure'] = consume(pure_reference, sources)
    parent = load_parent(parent_refs, sources)
    history = parent['document']['history']
    baselines = {ticker: consume(history['captured_source_references'][ticker], sources)
                 for ticker in ('QQQ', 'SPY')}
    actual_baselines = {ticker: consume(history['baseline_references'][ticker], sources)
                        for ticker in ('QQQ', 'SPY')}
    timezone_reference = history['tzif_reference']
    timezone_bytes = consume(timezone_reference, sources)
    core = private_core(raw)
    inputs = dict(dependency_refs, pure=pure_reference, tzif=timezone_reference)
    guard(sources, parent_refs)
    resource_gate()
    safe(OUTPUT).mkdir(parents=True, exist_ok=False)
    try:
        save(OUTPUT / 'started.json', dict(schema='FORWARD_GAP_PARENT_CAPTURE_STARTED_V3',
             parent_references=parent_refs, input_references=inputs, source_hashes=dict(sources),
             retry_allowed=False, **FLAGS))
        guard(sources, parent_refs)
        start = now()
        current = {ticker: read_current(CURRENT[ticker]) for ticker in ('QQQ', 'SPY')}
        end = now()
        live = {ticker: reference(str(CURRENT[ticker]), digest(value)) for ticker, value in current.items()}
        guard_current(sources, parent_refs, live)
        snapshots = {ticker: save_bytes(OUTPUT / (ticker + '.csv'), value)
                     for ticker, value in current.items()}
        timezone_snapshot = save_bytes(OUTPUT / 'New_York.tzif', timezone_bytes)
        for item in (*snapshots.values(), timezone_snapshot):
            merge(sources, item)
        plan = core.plan_gap_parent_capture(parent=parent, source_bytes=current,
            source_references=snapshots, accounted_baseline_bytes=baselines,
            actual_baseline_bytes=actual_baselines, capture_started_at=start,
            capture_completed_at=end, tzif_bytes=timezone_bytes, tzif_reference=timezone_snapshot)
        require(plan['schema'] == 'FORWARD_GAP_PARENT_CAPTURE_PLAN_V3', 'Exact plan schema')
        require(plan['status'] in ('NO_NEW_SESSION', 'ONE_NEW_SESSION_CAPTURE_CANDIDATE',
                                  'BLOCKED_SOURCE_DIAGNOSTICS'), 'Exact plan status')
        for field in FLAGS:
            if field != 'network_quote_refresh_performed':
                require(plan.get(field) is False, 'Strict plan authority ' + field)
        for path, sha256 in plan['source_reference_claims'].items():
            require(sources.get(path) == sha256, 'Plan claim outside immutable source closure')
        guard_current(sources, parent_refs, live)
        capture = save(OUTPUT / 'capture.json', dict(schema='SOURCE_BOUND_FORWARD_GAP_PARENT_CAPTURE_V3',
            plan=plan, parent_references=parent_refs, input_references=inputs,
            captured_artifacts=dict(snapshots, tzif=timezone_snapshot), current_cache_references=live,
            current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',
            capture_started_at=start, capture_completed_at=end, clock_captured_by_runner=True,
            external_clock_attestation_verified=False, quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',
            source_hashes=dict(sources), **FLAGS))
        publication = save(OUTPUT / 'publication.json', dict(schema='FORWARD_GAP_PARENT_CAPTURE_PUBLICATION_V3',
            status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION', capture_reference=capture,
            source_hashes=dict(sources), **FLAGS))
        guard_current(sources, parent_refs, live)
        for item in (capture, publication):
            consume(item, {})
        namespace(OUTPUT, ('started.json', 'QQQ.csv', 'SPY.csv', 'New_York.tzif', 'capture.json', 'publication.json'))
        return dict(capture_reference=capture, publication_reference=publication)
    except BaseException as error:
        save(OUTPUT / 'failure.json', dict(status='FAILED_DO_NOT_CONSUME', error_type=type(error).__name__,
            retry_allowed=False, **FLAGS))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    print(json.dumps(run(execute=parser.parse_args().execute)))
