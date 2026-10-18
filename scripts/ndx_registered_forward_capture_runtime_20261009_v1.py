"""Registered local V3/V4 source capture; create-only, no network or observations."""
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
RESEARCH = ROOT / 'data/cache/research'
REGISTRATION_CORE = (ROOT / 'backtest/ndx_forward_capture_runtime_registration_research_v1.py', 'e04169b111d2788e3dadba657a6c4823d2b0665de17a81e0c84bb9169990abde')
REFERENCE_CORE = (ROOT / 'backtest/ndx_compact_history_runtime_registration_research_v1.py',
    'd0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')
DEPENDENCIES = {
    'capture_core': ('backtest/ndx_forward_parent_capture_research_v4.py', '56175bb45b25aa899dc0f9fdd07d0eac2cabfd2f0640a177f596582b7b08a951'),
    'parent_view': ('backtest/ndx_prospective_observation_parent_history_research_v4.py', '06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'),
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
    folder=Path(parent_refs['reference']['path']).parent
    require(Path(parent_refs['reference']['path'])==folder/'history.json' and
        Path(parent_refs['publication_reference']['path'])==folder/'publication.json', 'Parent artifact names')
    audit=Path(parent_refs['readback_reference']['path']).parent
    require(Path(parent_refs['readback_reference']['path'])==audit/'independent_readback.json', 'Parent audit artifact name')
    namespace(folder, {'started.json','history.json','publication.json'} |
        ({'independent_readback.json'} if audit==folder else set()))
    if audit!=folder: namespace(audit, ('started.json','independent_readback.json'))


def guard(sources, parent_refs):
    parent_namespaces(parent_refs)
    live = {path.resolve() for path in CURRENT.values()}
    for path, sha256 in list(sources.items()):
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
    for key in ('base','scoped','compact_helpers','parent_view','capture_core'):
        substitutions=[]
        if key=='scoped': substitutions=[('from backtest import ndx_forward_source_capture_research as capture','capture',modules['base'])]
        if key=='parent_view': substitutions=[('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',modules['compact_helpers'])]
        if key=='capture_core': substitutions=[
            ('from backtest.ndx_forward_source_capture_scoped_research import scoped_csv','scoped_csv',modules['scoped'].scoped_csv),
            ('from backtest import ndx_prospective_observation_parent_history_research_v4 as parent_view','parent_view',modules['parent_view'])]
        path,expected=DEPENDENCIES[key]
        modules[key]=compile_private(ROOT/path,raw[key],expected,substitutions)
    core=modules['capture_core']
    require(core.SCOPED_PARSER_SHA256==DEPENDENCIES['scoped'][1] and
        core.PARSER_DEPENDENCY_SHA256==DEPENDENCIES['base'][1] and
        core.PARENT_VIEW_SHA256==DEPENDENCIES['parent_view'][1] and
        core.COMPACT_HELPER_SHA256==DEPENDENCIES['compact_helpers'][1], 'Capture dependency declarations')
    require(modules['parent_view'].DEPENDENCY_SHA256==DEPENDENCIES['compact_helpers'][1], 'Parent view helper binding')
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


def run(*, registration_path, registration_sha256, execute=False):
    require(execute is True, 'Explicit registered V4 source capture')
    # All configured/passed anchors validate before any source IO.
    regcore_ref=reference(str(REGISTRATION_CORE[0]),REGISTRATION_CORE[1])
    refcore_ref=reference(str(REFERENCE_CORE[0]),REFERENCE_CORE[1])
    registration_ref=reference(str(registration_path),registration_sha256)
    dependency_refs=configured(DEPENDENCIES)
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
    core=private_core(raw);parent=load_parent(parent_refs,sources)
    history=core.parent_view.inspect_parent_history_v4(parent)
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
        registration_core=regcore_ref,reference_core=refcore_ref,tzif=timezone_reference)
    guard(sources, parent_refs)
    resource_gate(output.anchor)
    safe(output).mkdir(parents=True, exist_ok=False)
    try:
        started_ref = save(output / 'started.json', dict(schema='FORWARD_CAPTURE_STARTED_V4',
             parent_references=parent_refs, input_references=inputs, source_hashes=dict(sources),
             retry_allowed=False, **FLAGS))
        guard(sources, parent_refs)
        start = now()
        current = {ticker: read_current(CURRENT[ticker]) for ticker in ('QQQ', 'SPY')}
        end = now()
        live = {ticker: reference(str(CURRENT[ticker]), digest(value)) for ticker, value in current.items()}
        guard_current(sources, parent_refs, live)
        snapshots = {ticker: save_bytes(output / (ticker + '.csv'), value)
                     for ticker, value in current.items()}
        timezone_snapshot = save_bytes(output / 'New_York.tzif', timezone_bytes)
        for item in (*snapshots.values(), timezone_snapshot):
            merge(sources, item)
        plan = core.plan_parent_capture(parent=parent, source_bytes=current,
            source_references=snapshots, accounted_baseline_bytes=baselines,
            actual_baseline_bytes=actual_baselines, capture_started_at=start,
            capture_completed_at=end, tzif_bytes=timezone_bytes, tzif_reference=timezone_snapshot)
        require(plan['schema'] == 'FORWARD_PARENT_CAPTURE_PLAN_V4', 'Exact plan schema')
        require(plan['status'] in ('NO_NEW_SESSION', 'ONE_NEW_SESSION_CAPTURE_CANDIDATE',
                                  'BLOCKED_SOURCE_DIAGNOSTICS'), 'Exact plan status')
        for field in FLAGS:
            if field != 'network_quote_refresh_performed':
                require(plan.get(field) is False, 'Strict plan authority ' + field)
        for path, sha256 in plan['source_reference_claims'].items():
            require(sources.get(path) == sha256, 'Plan claim outside immutable source closure')
        guard_current(sources, parent_refs, live)
        capture = save(output / 'capture.json', dict(schema='SOURCE_BOUND_FORWARD_CAPTURE_V4',
            plan=plan, parent_references=parent_refs, input_references=inputs,
            captured_artifacts=dict(snapshots, tzif=timezone_snapshot), current_cache_references=live,
            current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',
            capture_started_at=start, capture_completed_at=end, clock_captured_by_runner=True,
            external_clock_attestation_verified=False, quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',
            source_hashes=dict(sources), **FLAGS))
        publication = save(output / 'publication.json', dict(schema='FORWARD_CAPTURE_PUBLICATION_V4',
            status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION', capture_reference=capture,
            source_hashes=dict(sources), **FLAGS))
        guard_current(sources, parent_refs, live)
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
