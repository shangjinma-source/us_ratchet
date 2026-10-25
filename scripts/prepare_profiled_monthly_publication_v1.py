"""Create-only current-profile monthly review; no adoption or target generation."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import os
import json

from core.strategy_account_ledger import canonical, require
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_continuous32_runtime import RUNTIME_PATHS
from data.strategy_profiled_ready_release import PROFILE_ADMISSION_SOURCES, validate_ready_release
from scripts.prepare_real_monthly_release import _read, _safe
from scripts.review_prepare_real_monthly_release import run as original_review
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_daily_market_capture_v3 import DailyMarketCaptureV3
from data.strategy_account_action_capture_v6 import StrategyAccountActionCaptureV6

CAPTURE_SOURCES = {
    'data/strategy_daily_market_capture_v3.py',
    'data/strategy_account_market_capture_v2.py',
    'data/strategy_account_action_capture_v6.py',
    'data/strategy_account_action_capture_v3.py',
    'data/strategy_rss_verified_transport_v3.py',
}


class MonthlyReviewMarketCapture(DailyMarketCaptureV3):
    """Root-relative timing references for the frozen ready receipt reader."""
    def __init__(self, *, root, **kwargs):
        self.review_root = Path(root).absolute()
        self.captured_package = None
        super().__init__(**kwargs)

    def capture(self, **kwargs):
        result = super().capture(**kwargs)
        directory = Path(kwargs['output_directory']).absolute()
        for mark in result['marks'].values():
            reference = mark['transport_timing_reference']
            old = reference['path']
            name = (directory/old).relative_to(self.review_root).as_posix()
            require(name not in result['files'] and '/' not in old,
                    'PROFILE_MARK_TIMING_PATH_CONFLICT')
            require(_safe(self.review_root, name).read_bytes() == result['files'][old],
                    'PROFILE_MARK_TIMING_READBACK')
            result['files'][name] = result['files'].pop(old)
            result['source_hashes'][name] = result['source_hashes'].pop(old)
            reference['path'] = name
        self.captured_package = result
        return result


class MonthlyReviewActionCapture(StrategyAccountActionCaptureV6):
    """Keep the V3 stage and expose the verified V6 closure to ready replay."""
    def __init__(self, *, market_capture, **kwargs):
        require(isinstance(market_capture, MonthlyReviewMarketCapture),
                'PROFILE_ACTION_MARKET_CLOSURE_REQUIRED')
        self.review_market = market_capture
        super().__init__(**kwargs)

    def capture(self, request, output_directory):
        directory = Path(output_directory)
        raw_directory = directory.with_name(directory.name+'-original-v6')
        result = super().capture(request, raw_directory)
        original = (raw_directory/'complete.json').read_bytes()
        stage = json.loads(original)
        require(stage['documents'] == result['documents'] and
                all(result['source_hashes'].get(p) == h for p,h in stage['source_hashes'].items()),
                'PROFILE_ACTION_STAGE_BINDING')
        final_raw = (raw_directory/'complete-v6.json').read_bytes()
        final = json.loads(final_raw)
        require(final['source_hashes'] == result['source_hashes'] and
                final['documents'] == result['documents'], 'PROFILE_ACTION_FINAL_BINDING')
        # The raw capture directory is never rewritten.  This separate directory
        # is explicitly a compatibility view of the complete, verified V6 package.
        directory.mkdir(exist_ok=False)
        def put(name, raw):
            with (directory/name).open('xb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            require((directory/name).read_bytes() == raw, 'PROFILE_ACTION_PROJECTION_READBACK')
        for name, raw in result['files'].items():
            require(name.startswith('strategy-action-capture/') and len(Path(name).parts) == 2,
                    'PROFILE_ACTION_PROJECTION_PATH')
            require((raw_directory/Path(name).name).read_bytes() == raw,
                    'PROFILE_ACTION_ORIGINAL_CHANGED')
            put(Path(name).name, raw)
        originals = {}
        for label, raw in (('v3-stage', original), ('v6-final', final_raw)):
            digest = sha256(raw).hexdigest()
            name = digest+'.'+label+'.json'
            logical = 'strategy-action-capture/'+name
            require(logical not in result['files'], 'PROFILE_ACTION_PROJECTION_CONFLICT')
            put(name, raw)
            result['files'][logical] = raw
            result['source_hashes'][logical] = digest
            originals[label] = dict(path=logical, sha256=digest)
        require(len(result['files']) <= 2000 and sum(map(len, result['files'].values())) <= 128*1024*1024,
                'PROFILE_ACTION_PROJECTION_BUDGET')
        put('started.json', (raw_directory/'started.json').read_bytes())
        projected = canonical(dict(stage, source_hashes=result['source_hashes'],
            schema='MONTHLY_ACTION_V6_READY_PROJECTION_V1',
            original_directory=raw_directory.name,
            original_receipts=originals,
            original_v3_complete_sha256=sha256(original).hexdigest(),
            original_v6_complete_sha256=sha256(final_raw).hexdigest()))
        put('complete.json', projected)
        require((raw_directory/'complete.json').read_bytes() == original and
                (raw_directory/'complete-v6.json').read_bytes() == final_raw,
                'PROFILE_ACTION_ORIGINAL_CHANGED')
        # Bind projection bytes in the provider's outer evidence closure.  It
        # must not enter its own action source map (which would self-reference).
        # The frozen ready reader verifies every outer pin on adoption/replay.
        package = self.review_market.captured_package
        require(type(package) is dict, 'PROFILE_MARKET_PACKAGE_REQUIRED')
        name = (directory/'complete.json').absolute().relative_to(self.review_market.review_root).as_posix()
        require(name not in package['files'], 'PROFILE_ACTION_OUTER_PIN_CONFLICT')
        package['files'][name] = projected
        package['source_hashes'][name] = sha256(projected).hexdigest()
        return result


def prepare(*, root, snapshot, new_entry, output_directory, clock,
            validate_code, market_capture=None, action_capture=None):
    root = Path(root).absolute()
    output = _safe(root, output_directory)
    require(not output.exists() and output.parent.is_dir(), 'PROFILE_PUBLICATION_OUTPUT_CONFLICT')
    validate_code()
    require(RUNTIME_PATHS | PROFILE_ADMISSION_SOURCES <= set(new_entry['runtime_pins']),
            'PROFILE_PUBLICATION_RUNTIME_PINS_REQUIRED')
    registry = _read(root, snapshot['registry_path'], snapshot['registry_sha256'])
    archive = _read(root, snapshot['archive_path'], snapshot['archive_sha256'])
    require(archive['schema'] in {'REAL_STRATEGY_RUNTIME_ARCHIVE_V1',
            'PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1'}, 'PROFILE_PUBLICATION_ARCHIVE_SCHEMA')
    profiles = deepcopy(registry.get('profiles', []))
    if registry['schema'] == 'PROFILED_MONTHLY_RELEASES_V1':
        ref = registry['original_registry']; registry = _read(root, ref['path'], ref['sha256'])
    require(registry['schema'] == 'REAL_STRATEGY_MONTHLY_RELEASES_V1', 'PROFILE_PUBLICATION_REGISTRY_SCHEMA')
    originals = []
    for row in archive['entries']:
        value = _read(root, row['configuration_path'], row['configuration_sha256'])
        require(value['schema'] in {'REAL_STRATEGY_RUNTIME_V1', 'REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1'},
                'PROFILE_PUBLICATION_UNKNOWN_ARCHIVE_RUNTIME')
        if value['schema'] == 'REAL_STRATEGY_RUNTIME_V1': originals.append(row)
    output.mkdir(exist_ok=False)
    def put(name, value):
        raw = canonical(value)
        with (output/name).open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        return dict(path=(Path(output_directory)/name).as_posix(), sha256=sha256(raw).hexdigest())
    put('started.json', dict(snapshot=snapshot, new_entry=new_entry, started_at=clock().isoformat()))
    try:
        # Same verified transports as the current daily provider.  Identity is
        # the new month's pinned identity, not a current-price inference.
        if market_capture is None:
            market_capture = MonthlyReviewMarketCapture(root=root, identity_resolver=PinnedStrategyIdentity(
                root, new_entry['identity_manifest'], new_entry['identity_sha256']), clock=clock)
        if action_capture is None:
            action_capture = MonthlyReviewActionCapture(market_capture=market_capture, clock=clock)
        reg = put('original-registry.json', registry)
        arc = put('original-archive.json', dict(schema='REAL_STRATEGY_RUNTIME_ARCHIVE_V1', entries=originals))
        base = original_review(root=root, registry_path=reg['path'], registry_sha256=reg['sha256'],
            archive_path=arc['path'], archive_sha256=arc['sha256'], new_entry=deepcopy(new_entry),
            output_directory=(Path(output_directory)/'base-review').as_posix(), clock=clock,
            market_capture=market_capture, action_capture=action_capture)
        base_path = (Path(output_directory)/'base-review/ready.json').as_posix()
        base_ref = dict(path=base_path, sha256=sha256(_safe(root, base_path).read_bytes()).hexdigest())
        original = _read(root,
            base['files']['runtime']['path'], base['files']['runtime']['sha256'])
        runtime = put('runtime.json', dict(original, schema='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1', selector_profile=PROFILE_ID))
        assignment = dict(target_month=original['target_month'], selector_profile=PROFILE_ID)
        require(not [r for r in profiles if r['target_month'] == assignment['target_month'] and r != assignment],
                'PROFILE_PUBLICATION_ASSIGNMENT_CONFLICT')
        if assignment not in profiles: profiles.append(assignment)
        reg = put('registry.json', dict(schema='PROFILED_MONTHLY_RELEASES_V1',
            original_registry=base['files']['registry'], profiles=profiles))
        base_archive = _read(root, base['files']['archive']['path'], base['files']['archive']['sha256'])
        entries = deepcopy(archive['entries'])
        for row in base_archive['entries'] + [dict(configuration_path=runtime['path'], configuration_sha256=runtime['sha256'])]:
            if row not in entries: entries.append(row)
        require(len(entries) <= 100, 'PROFILE_PUBLICATION_ARCHIVE_BUDGET')
        arc = put('archive.json', dict(schema='PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1', entries=entries))
        ready = dict(schema='PROFILED_READY_RELEASE_V1', status='READY_FOR_REVIEW_NOT_ACTIVATED',
                     base_ready=base_ref, registry=reg, archive=arc, runtime=runtime)
        # Validate a staged receipt before publishing the sole ready marker.
        stage = put('review-candidate.json', ready)
        from data.strategy_account_runtime import ScopedAccountStore
        accounts = ScopedAccountStore(root/'data/strategy_account/real_strategy.sqlite3', clock=clock)
        checked = validate_ready_release(root=root, receipt_path=stage['path'], receipt_sha256=stage['sha256'],
            account_state=accounts.read(), clock=clock)
        require(checked['account_revision'] == base['account_revision'], 'PROFILE_PUBLICATION_ACCOUNT_CHANGED')
        for kind in ('registry', 'archive'):
            _read(root, snapshot[kind+'_path'], snapshot[kind+'_sha256'])
        validate_code()
        return dict(status='PROFILED_MONTHLY_READY_NOT_ADOPTED', ready=put('ready.json', ready),
                    account_writes=False, target_created=False, orders_created=False)
    except Exception:
        put('failed.json', dict(status='BLOCKED', automatic_retry=False))
        raise
