"""Create-only gap-history extension from pinned, independently read saved inputs."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PURE = ROOT / 'backtest/ndx_prospective_gap_history_research_v3.py'
PURE_SHA = '12690e619763ff32ff601d0d0f4071f41d7ecf5e921d19601c58ab5802ed5c63'
OUTPUT = ROOT / 'data/cache/research/prospective_gap_history_20261009_v3'
PARENT_BOUND = {
    'reference': ('data/cache/research/prospective_observation_parent_history_20261003_v1/history.json', 'bd0eb3bb1ed5a4103af964e4c2016caf8e5abf45caf799ffbf786642bc7a4a33'),
    'publication_reference': ('data/cache/research/prospective_observation_parent_history_20261003_v1/publication.json', '648f6937e7ff876a824bab96a654461b411dccd6b4c7a6a19217d0bdd09fbcf6'),
    'readback_reference': ('data/cache/research/prospective_observation_parent_history_independent_readback_20261003_v1/independent_readback.json', 'c6f9a113b1b5f00128befa74a415e6604012d47ac17eb7db2048dafa8a31a86a'),
    'reader_reference': ('scripts/ndx_prospective_observation_parent_history_independent_readback_20261003.py', '876094538679db3216f69cf3035101baf91498d5296512cbef4b2911486d7aef'),
}
CAPTURE_BOUND = {
    'reference': ('data/cache/research/variable_prefix_source_capture_20261003_v1/capture.json', '435c1129792aaec3a52c7d156a39f34cf594838e1d406a833ddd55dc86ae878e'),
    'publication_reference': ('data/cache/research/variable_prefix_source_capture_20261003_v1/publication.json', '16bd9eaf7da6e36eaa1b2d927e0749ea77c5f5885b5eddd28daa069f4171cadf'),
    'readback_reference': ('data/cache/research/variable_prefix_capture_independent_readback_20261003_v1/independent_readback.json', '20dbef63741bb9e75372fbec435ddaa6883f2ee54241d6d79536073526715e1d'),
    'reader_reference': ('scripts/ndx_variable_prefix_capture_independent_readback_20261003.py', 'aed7b71289fb30473cedefda00c6377c0700bea115e5d99328c1c20dd4572dbe'),
}
FALSE_FLAGS = dict.fromkeys((
    'observation_created', 'candidate_seal_allowed', 'cohort_registration_allowed',
    'point_in_time_verified', 'promotion_allowed', 'future_independent_oos',
    'live_mutation_allowed', 'old_calendar_mutated', 'network_capture_performed',
    'source_authenticity_verified', 'clock_authenticity_verified',
    'filesystem_attempt_inventory_authenticated', 'full_transitive_source_closure_reverified',
), False)

DEPENDENCIES = {
    'base': ('backtest/ndx_forward_source_capture_research.py', '30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'),
    'scoped': ('backtest/ndx_forward_source_capture_scoped_research.py', '9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee'),
    'core': ('backtest/ndx_variable_prefix_capture_research.py', '9c76324fcbc8e5d57a1ef25566a59110acff32a58506c6d5b6947996e6c26039'),
}
SOURCE_NAMESPACES = {
    'prospective_observation_parent_history_20261003_v1': {'history.json', 'publication.json', 'started.json'},
    'prospective_observation_parent_history_independent_readback_20261003_v1': {'independent_readback.json', 'started.json'},
    'variable_prefix_source_capture_20261003_v1': {'capture.json', 'publication.json', 'started.json', 'QQQ.csv', 'SPY.csv', 'New_York.tzif'},
    'variable_prefix_capture_independent_readback_20261003_v1': {'independent_readback.json', 'started.json'},
}


def guard_namespaces():
    for name, expected in SOURCE_NAMESPACES.items():
        folder = safe(ROOT / 'data/cache/research' / name)
        items = list(folder.iterdir())
        require({item.name for item in items} == expected, 'Exact source namespace ' + name)
        require(all(safe(item).is_file() for item in items), 'Regular source namespace')


def private_pure(pure_bytes, sources):
    modules = {}
    replacements = {
        'scoped': ('from backtest import ndx_forward_source_capture_research as capture', 'capture', 'base'),
        'core': ('from backtest.ndx_forward_source_capture_scoped_research import scoped_csv', 'scoped_csv', 'scoped'),
        'pure': ('from backtest import ndx_variable_prefix_capture_research as capture_core', 'capture_core', 'core'),
    }
    for key in ('base', 'scoped', 'core', 'pure'):
        if key == 'pure':
            path, raw = PURE, pure_bytes
        else:
            relative, expected = DEPENDENCIES[key]
            path = ROOT / relative
            raw = consume(reference(path, expected), sources)
        module = ModuleType('_gap_history_' + key)
        module.__file__ = str(path)
        code = raw.decode('utf-8-sig')
        if key in replacements:
            line, attribute, dependency = replacements[key]
            require(code.count(line) == 1, 'Explicit dependency import ' + key)
            code = code.replace(line, '')
            module.__dict__[attribute] = (modules[dependency].scoped_csv if key == 'core' else modules[dependency])
        exec(compile(code, str(path), 'exec'), module.__dict__)
        modules[key] = module
    require(modules['pure'].DEPENDENCY_SHA256 == {key: value[1] for key, value in DEPENDENCIES.items()},
            'Exact private dependency declarations')
    return modules['pure']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('utf-8')


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError('Nonfinite JSON ' + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def reference(path, sha256):
    require(type(sha256) is str and len(sha256) == 64 and
            set(sha256) <= set('0123456789abcdef'), 'Pending immutable source SHA')
    return {'path': str(path), 'sha256': sha256}


def safe(path):
    path = Path(path)
    for ancestor in (path, *path.parents):
        require(not ancestor.is_symlink() and not getattr(ancestor, 'is_junction', lambda: False)(),
                'No linked source or output')
    return path


def merge(sources, item):
    require(type(item) is dict and set(item) == {'path', 'sha256'}, 'Exact source reference')
    reference(item['path'], item['sha256'])
    path = str(item['path'])
    require(path not in sources or sources[path] == item['sha256'], 'Conflicting source SHA')
    sources[path] = item['sha256']


def consume(item, sources):
    merge(sources, item)
    path = safe(item['path'])
    require(path.is_file() and path.stat().st_size <= 64 * 1024**2, 'Bounded regular source')
    require(not (path.parent / 'failure.json').exists(), 'Failed source namespace')
    raw = path.read_bytes()
    require(digest(raw) == item['sha256'], 'Source bytes changed')
    return raw


def guard(sources):
    guard_namespaces()
    live = {(ROOT / 'data/cache' / (ticker + '.csv')).resolve() for ticker in ('QQQ', 'SPY')}
    for path, sha256 in sources.items():
        require(Path(path).resolve() not in live, 'No permanent mutable cache claim')
        require(digest(safe(path).read_bytes()) == sha256, 'Source drift')
        require(not (Path(path).parent / 'failure.json').exists(), 'Failed source namespace')


def load_envelope(bound, sources):
    require(set(bound) == {'reference', 'publication_reference', 'readback_reference', 'reader_reference'},
            'Complete four input anchors')
    result = {key: reference(ROOT / path, sha256) for key, (path, sha256) in bound.items()}
    for role, key in (('document', 'reference'), ('publication', 'publication_reference'),
                      ('readback', 'readback_reference')):
        result[role] = decode(consume(result[key], sources))
        for path, sha256 in result[role]['source_hashes'].items():
            merge(sources, reference(path, sha256))
    consume(result['reader_reference'], sources)
    return result


def save(path, value):
    raw = encode(value)
    if path.name != 'failure.json':
        require(shutil.disk_usage(Path(OUTPUT.anchor)).free >= 5 * 1024**3 + len(raw),
                'Resource stop before output write')
    with safe(path).open('xb') as stream:
        require(stream.write(raw) == len(raw), 'Complete output write')
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'Durable saved bytes')
    return reference(path, digest(raw))


def run(*, execute=False):
    require(execute is True, 'Explicit gap-history publication')
    pure_reference = reference(PURE, PURE_SHA)
    require(not OUTPUT.exists(), 'Create-only namespace, no retry')
    sources = {str(SOURCE): LOADED_SHA}
    pure_bytes = consume(pure_reference, sources)
    parent = load_envelope(PARENT_BOUND, sources)
    capture = load_envelope(CAPTURE_BOUND, sources)
    guard(sources)
    source_bytes = {ticker: consume(capture['document']['captured_artifacts'][ticker], sources)
                    for ticker in ('QQQ', 'SPY')}
    baseline_bytes = {ticker: consume(parent['document']['baseline_references'][ticker], sources)
                      for ticker in ('QQQ', 'SPY')}
    tzif_bytes = consume(capture['document']['captured_artifacts']['tzif'], sources)
    pure = private_pure(pure_bytes, sources)
    history = pure.extend_gap_history(parent=parent, capture=capture, source_bytes=source_bytes,
                                     baseline_bytes=baseline_bytes, tzif_bytes=tzif_bytes)
    for key in FALSE_FLAGS:
        require(history[key] is False, 'Exact false authority ' + key)
    inputs = {'parent': {key: parent[key] for key in PARENT_BOUND},
              'capture': {key: capture[key] for key in CAPTURE_BOUND}, 'pure': pure_reference}
    guard(sources)
    require(shutil.disk_usage(Path(OUTPUT.anchor)).free >= 5 * 1024**3,
            'Resource stop before output namespace')
    safe(OUTPUT).mkdir(parents=True, exist_ok=False)
    try:
        started = save(OUTPUT / 'started.json', dict(schema='PROSPECTIVE_GAP_HISTORY_STARTED_V3',
                       input_references=inputs, source_hashes=sources, **FALSE_FLAGS))
        document = save(OUTPUT / 'history.json', dict(history=history, input_references=inputs,
                        source_hashes=sources, schema='SOURCE_BOUND_PROSPECTIVE_GAP_HISTORY_V3', **FALSE_FLAGS))
        publication = save(OUTPUT / 'publication.json', dict(
            schema='PROSPECTIVE_GAP_HISTORY_PUBLICATION_V3',
            status='PUBLISHED_GAP_EXTENSION_PENDING_INDEPENDENT_READBACK',
            history_reference=document, started_reference=started, input_references=inputs,
            source_hashes=sources, **FALSE_FLAGS))
        guard(sources)
        require({path.name for path in OUTPUT.iterdir()} == {'started.json', 'history.json', 'publication.json'},
                'Exact published namespace')
        return publication
    except BaseException as error:
        save(OUTPUT / 'failure.json', {'status': 'FAILED_DO_NOT_CONSUME',
             'error_type': type(error).__name__, 'retry_allowed': False, **FALSE_FLAGS})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    print(json.dumps(run(execute=parser.parse_args().execute)))
