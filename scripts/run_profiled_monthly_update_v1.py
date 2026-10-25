"""Versioned monthly source preparation then profiled adoption. Dry-run default."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import argparse
import json
from core.strategy_account_ledger import require
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_bounded_source_gate_v1 import BoundedSourceGateV1
from data.strategy_profiled_server_preparation import SOURCES as PROFILE_SOURCES
from data.strategy_profiled_release_activation import ProfiledMonthlyReleaseActivation
from data.strategy_continuous32_upgrade_handoff import upgrade_handoff_snapshot_provider
from data.strategy_continuous32_runtime import RUNTIME_PATHS
from data.strategy_profiled_ready_release import PROFILE_ADMISSION_SOURCES
from scripts.prepare_real_monthly_release import _read, _safe
from scripts.run_scheduled_real_monthly_update import REQUIRED_SOURCE_PATHS as OLD_SOURCES
from scripts.run_real_monthly_market_preparation import run as produce
from scripts.build_real_monthly_release_entry import build
from scripts.update_profiled_monthly_release_v1 import update
from scripts.prepare_profiled_monthly_publication_v1 import CAPTURE_SOURCES

SOURCES = OLD_SOURCES | PROFILE_SOURCES | CAPTURE_SOURCES | {
    'scripts/prepare_profiled_monthly_publication_v1.py',
    'scripts/update_profiled_monthly_release_v1.py',
    'scripts/run_profiled_monthly_update_v1.py',
    'data/strategy_continuous32_upgrade_handoff.py',
    'data/strategy_bounded_source_gate_v1.py'}


def run(*, root, config_path, config_sha256, execute=False, clock=None,
        market_capture=None, action_capture=None):
    root = Path(root).absolute(); clock = clock or (lambda:datetime.now(timezone.utc))
    config = _read(root, config_path, config_sha256)
    require(set(config) == {'schema','source_schedule','preparation','upgrade','source_pins','output_directory'}
            and config['schema'] == 'PROFILED_MONTHLY_SCHEDULE_V1', 'PROFILE_SCHEDULE_FIELDS')
    require(SOURCES <= set(config['source_pins']), 'PROFILE_SCHEDULE_SOURCE_SCOPE')
    gate = BoundedSourceGateV1(root=root, source_pins=config['source_pins'],
        configuration_pins={config_path:config_sha256, **{config[k]['path']:config[k]['sha256']
                           for k in ('source_schedule','preparation','upgrade')}})
    gate()
    def load(ref): return _read(root, ref['path'], ref['sha256'])
    scheduled = load(config['source_schedule']); preparation = load(config['preparation'])
    require(scheduled['schema'] == 'SCHEDULED_REAL_MONTHLY_UPDATE_V1' and
            Path(scheduled['root']).resolve() == root.resolve(), 'PROFILE_SOURCE_SCHEDULE_REQUIRED')
    require(preparation['schema'] == 'PROFILED_SERVER_PREPARATION_V2', 'PROFILE_PREPARATION_REQUIRED')
    for document in (scheduled, preparation):
        require(all(config['source_pins'].get(p) == h for p,h in document['source_pins'].items()),
                'PROFILE_CHILD_PIN_MISMATCH')
    coordinator = _read(root, scheduled['coordinator_config'], scheduled['coordinator_sha256'])
    settings = _read(root, coordinator['settings_path'], coordinator['settings_sha256'])
    boundary = _read(root, settings['calendar_path'], settings['fixed_source_hashes'][settings['calendar_path']])
    calendar = _read(root, settings['schedule_path'], settings['fixed_source_hashes'][settings['schedule_path']])
    closing = datetime.fromisoformat(boundary['decision_close_at'])
    opening = datetime.fromisoformat(boundary['active_open_at'])
    sessions = [(datetime.fromisoformat(r['open_at']), datetime.fromisoformat(r['close_at'])) for r in calendar['sessions']]
    require(closing < opening and any(a == opening for a,b in sessions), 'PROFILE_SCHEDULE_CALENDAR')
    last = [None]
    def now():
        value = clock(); require(value.utcoffset() is not None and
            (last[0] is None or value >= last[0]), 'PROFILE_SCHEDULE_CLOCK')
        last[0] = value; gate(); return value
    current = now()
    arguments = {k:scheduled[k] for k in ('coordinator_config','coordinator_sha256',
        'bootstrap_config','bootstrap_sha256','policy_path','policy_sha256')}
    for k in ('coordinator_config','bootstrap_config'): arguments[k] = str(_safe(root, arguments[k]))
    arguments.update(output_directory=scheduled['market_output_directory'], clock=now)
    if current < closing:
        return dict(status='WAITING_SESSION_CLOSE', account_writes=False, target_created=False, http_calls=0)
    if current < opening:
        prepared = produce(**arguments, execute=execute)
        if prepared.get('status') not in {'PREFLIGHT_ONLY', 'WAITING_SESSION_CLOSE',
                                         'MARKET_PUBLICATION_READY_NOT_ACTIVATED'}:
            return dict(status='BLOCKED', reason='PROFILE_MARKET_PREPARATION_NOT_READY',
                        preparation=prepared, automatic_retry=False, account_writes=False)
        return dict(status='MARKET_PREPARATION_PHASE', result=prepared,
                    account_writes=False, target_created=False)
    complete = _safe(root, scheduled['market_output_directory']+'/complete.json')
    if not complete.is_file():
        return dict(status='MISSED_PREPARATION_WINDOW', automatic_retry=False, account_writes=False)
    # Saved source closure is revalidated; never capture a missed historical window.
    market = produce(**arguments, execute=False)
    require(market.get('status') != 'WAITING_REVIEW', 'PROFILE_SOURCE_REVIEW_REQUIRED')
    output = _safe(root, config['output_directory'])
    require(output != complete.parent and output not in complete.parents and complete.parent not in output.parents,
            'PROFILE_OUTPUT_OVERLAP')
    fresh = not output.exists()
    def review_clock():
        value = now()
        require(any(a+timedelta(minutes=30) <= value < b for a,b in sessions), 'PROFILE_REGULAR_REVIEW_WINDOW')
        return value
    if execute and fresh and not any(a+timedelta(minutes=30) <= current < b for a,b in sessions):
        return dict(status='WAITING_REGULAR_REVIEW_WINDOW', account_writes=False, http_calls=0)
    used_clock = review_clock if execute and fresh else now
    activation = ProfiledMonthlyReleaseActivation(root=root, initial_snapshot=preparation['initial_snapshot'],
        legacy_anchor=preparation['legacy_anchor'], validate_code=gate, clock=used_clock)
    targets = StrategyMonthlyTargetStore(root/'data/strategy_account/monthly_targets.sqlite3')
    snapshot = upgrade_handoff_snapshot_provider(root=root, package_path=config['upgrade']['path'],
        package_sha256=config['upgrade']['sha256'], base_provider=activation.snapshot,
        target_provider=targets.current, validate_code=gate)
    entry = build(root=root, complete_path=complete.relative_to(root).as_posix(),
        complete_sha256=sha256(complete.read_bytes()).hexdigest(),
        descriptor_path=scheduled['descriptor_path'], descriptor_sha256=scheduled['descriptor_sha256'])
    for path in RUNTIME_PATHS | PROFILE_ADMISSION_SOURCES:
        entry['runtime_pins'][path] = config['source_pins'][path]
    gate()
    return update(root=root, entry=entry, output_directory=config['output_directory'], activation=activation,
        snapshot_provider=snapshot, validate_code=gate, clock=used_clock, execute=execute,
        market_capture=market_capture, action_capture=action_capture)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('root','config-path','config-sha256'): parser.add_argument('--'+key,required=True)
    parser.add_argument('--execute',action='store_true')
    try: result=run(**vars(parser.parse_args(argv)))
    except Exception as error:
        result=dict(status='BLOCKED', reason=str(error) if isinstance(error,ValueError) else 'PROFILE_MONTHLY_FAILED',automatic_retry=False)
    print(json.dumps(result,ensure_ascii=False)); return 2 if result['status'] in {'BLOCKED','MISSED_PREPARATION_WINDOW'} else 0


if __name__=='__main__': raise SystemExit(main())
