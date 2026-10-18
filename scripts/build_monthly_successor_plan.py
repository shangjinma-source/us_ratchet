"""Pure fixed-domain successor plans, with replay-verified completed lineage.

No HTTP, portfolio search, account access, or publication. The separate schema
requires explicit validator dispatch; the original experimental validator stays
unchanged. All calendars are caller-pinned evidence, never weekday guesses.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require
from scripts.monthly_experimental_domain_capture import prepare as original_prepare, SCHEMA as ORIGINAL_SCHEMA
from scripts.prepare_monthly_captured_training import build as rebuild

SCHEMA = 'EXPERIMENTAL_SUCCESSOR_DOMAIN_CAPTURE_PLAN_V1'


def utc_now():
    return datetime.now(timezone.utc)


def read(root, path, expected):
    relative = Path(path)
    require(not relative.is_absolute() and '..' not in relative.parts, 'SUCCESSOR_RELATIVE_PATH_REQUIRED')
    target = root / relative
    require(not target.is_symlink() and target.resolve().is_relative_to(root) and target.is_file()
            and target.stat().st_size <= 32 * 1024 * 1024, 'SUCCESSOR_SOURCE_UNAVAILABLE')
    raw = target.read_bytes()
    require(sha256(raw).hexdigest() == expected, 'SUCCESSOR_SOURCE_CHANGED')
    return json.loads(raw)


def completed_previous(root, manifest_path, manifest_sha256, receipt_path, receipt_sha256, clock, depth=0):
    require(depth < 24, 'SUCCESSOR_LINEAGE_DEPTH_LIMIT')
    manifest = read(root, manifest_path, manifest_sha256)
    receipt = read(root, receipt_path, receipt_sha256)
    require(receipt['result']['status'] == 'READY_CONDITIONAL', 'SUCCESSOR_PREPARATION_INCOMPLETE')
    outputs = receipt['output_hashes']
    require(outputs.get(str((root / manifest_path).resolve())) == manifest_sha256,
            'SUCCESSOR_MANIFEST_NOT_COMPLETED_OUTPUT')
    for path, digest in outputs.items():
        absolute = Path(path)
        require(absolute.is_absolute() and absolute.resolve().is_relative_to(root), 'SUCCESSOR_OUTPUT_OUTSIDE_ROOT')
        read(root, absolute.relative_to(root).as_posix(), digest)
    at = datetime.fromisoformat(receipt['at'])
    require(at.tzinfo is not None and at <= clock(), 'SUCCESSOR_FUTURE_COMPLETION')
    arguments = receipt['binding']['inputs']
    require(set(arguments) == {'previous_manifest_path', 'previous_manifest_sha256', 'capture_index_path',
                              'capture_index_sha256', 'plan_path', 'plan_sha256'}, 'SUCCESSOR_RECEIPT_INPUTS')
    previous_plan = read(root, arguments['plan_path'], arguments['plan_sha256'])
    require(previous_plan['schema'] in (ORIGINAL_SCHEMA, SCHEMA), 'SUCCESSOR_LINEAGE_SCHEMA')
    validator = lambda p, h, **kw: prepare(p, h, _depth=depth+1, **kw)
    derived, compiled, _ = rebuild(**arguments, root=root, clock=lambda: at, plan_validator=validator)
    require(compiled['status'] == 'READY_CONDITIONAL' and derived == manifest,
            'SUCCESSOR_COMPLETED_MANIFEST_REPLAY_MISMATCH')
    return manifest, previous_plan


def calendar(root, path, pins):
    require(path in pins and pins, 'SUCCESSOR_CALENDAR_PINS_REQUIRED')
    documents = {name: read(root, name, digest) for name, digest in pins.items()
                 if name == path}
    # Evidence can be HTML/PDF; verify bytes without treating it as JSON.
    for name, digest in pins.items():
        target = root / name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts
                and target.resolve().is_relative_to(root) and not target.is_symlink()
                and target.is_file() and target.stat().st_size <= 32*1024*1024
                and sha256(target.read_bytes()).hexdigest() == digest, 'SUCCESSOR_CALENDAR_SOURCE_CHANGED')
    value = documents[path]
    days = value['calendar']; rows = value['sessions']
    require(value['schema'] == 'SCHEDULED_REGULAR_SESSIONS_V1' and days == sorted(set(days))
            and [row['date'] for row in rows] == days
            and value['source_hashes'] and all(pins.get(p) == h for p, h in value['source_hashes'].items()),
            'SUCCESSOR_CALENDAR_INVALID')
    for row in rows:
        times = [datetime.fromisoformat(row[key]) for key in ('open_at', 'close_at')]
        require(row['timezone'] == 'America/New_York' and all(t.tzinfo is not None
                and t.astimezone(ZoneInfo('America/New_York')).date().isoformat() == row['date']
                and t.utcoffset() == t.astimezone(ZoneInfo('America/New_York')).utcoffset() for t in times)
                and times[0] < times[1], 'SUCCESSOR_CALENDAR_SESSION_INVALID')
    return value


def prepare(plan_path, plan_sha256, *, root, clock=utc_now, _depth=0):
    root = Path(root).resolve()
    plan = read(root, plan_path, plan_sha256)
    if plan['schema'] == ORIGINAL_SCHEMA:
        return original_prepare(plan_path, plan_sha256, root=root, clock=clock)
    require(plan['schema'] == SCHEMA and set(plan) == {'schema', 'status', 'domain_path',
        'domain_source_hashes', 'calendar_path', 'calendar_source_hashes', 'session', 'history_start_date',
        'securities', 'output_directory', 'previous_manifest_path', 'previous_manifest_sha256',
        'previous_completion_path', 'previous_completion_sha256'}, 'SUCCESSOR_PLAN_FIELDS')
    old, ancestor = completed_previous(root, plan['previous_manifest_path'], plan['previous_manifest_sha256'],
        plan['previous_completion_path'], plan['previous_completion_sha256'], clock, _depth)
    require(all(plan[key] == ancestor[key] for key in ('domain_path', 'domain_source_hashes', 'securities')),
            'SUCCESSOR_FIXED_DOMAIN_CHANGED')
    schedule = calendar(root, plan['calendar_path'], plan['calendar_source_hashes'])
    require(plan['session'] in schedule['calendar'] and old['decision_date'] < plan['session']
            and plan['history_start_date'] <= old['training_dates'][0], 'SUCCESSOR_DATES_INVALID')
    require(not Path(plan['output_directory']).is_absolute() and '..' not in Path(plan['output_directory']).parts
            and (root / plan['output_directory']).resolve().is_relative_to(root)
            and (root / plan['output_directory']).resolve() != root, 'SUCCESSOR_OUTPUT_INVALID')
    closing = datetime.fromisoformat(next(r['close_at'] for r in schedule['sessions'] if r['date'] == plan['session']))
    plan['membership_source_hashes'] = dict(plan['domain_source_hashes'])
    # Bind the verified completion itself into the downstream training source closure.
    plan['membership_source_hashes'][plan['previous_completion_path']] = plan['previous_completion_sha256']
    return plan, dict(status='SUCCESSOR_PLAN_VALIDATED', ready_after_close=clock() >= closing,
        session_close_at=closing.isoformat(), http_calls=0, search_calls=0,
        point_in_time_membership_verified=False, new_membership_observation=False)


def build_next_plan(*, root, previous_manifest_path, previous_manifest_sha256,
                    previous_completion_path, previous_completion_sha256,
                    calendar_path, calendar_source_hashes, output_directory, clock=utc_now,
                    completed_target_month=None):
    root = Path(root).resolve()
    old, ancestor = completed_previous(root, previous_manifest_path, previous_manifest_sha256,
        previous_completion_path, previous_completion_sha256, clock)
    schedule = calendar(root, calendar_path, calendar_source_hashes)
    rows = schedule['sessions']; previous_day = old['decision_date']
    require(previous_day in schedule['calendar'], 'SUCCESSOR_PRIOR_SESSION_NOT_IN_CALENDAR')
    pairs = [(a, b) for a, b in zip(rows, rows[1:])
             if a['date'] > previous_day and a['date'][:7] != b['date'][:7]
             and (completed_target_month is None or b['date'][:7] > completed_target_month)]
    require(pairs, 'SUCCESSOR_NEXT_MONTH_BOUNDARY_UNAVAILABLE')
    decision, active = pairs[0]
    if completed_target_month is not None:
        month = date.fromisoformat(completed_target_month+'-01')
        require(month.strftime('%Y-%m') == completed_target_month, 'SUCCESSOR_COMPLETED_MONTH_INVALID')
        next_month = date(month.year+(month.month==12), 1 if month.month==12 else month.month+1, 1).strftime('%Y-%m')
        require(active['date'][:7] == next_month and decision['date'][:7] == completed_target_month,
                'SUCCESSOR_MISSING_NEXT_MONTH_CALENDAR')
    dates = (old['training_dates'] + [r['date'] for r in rows if previous_day < r['date'] <= decision['date']])[-253:]
    require(len(dates) == 253 and dates == sorted(set(dates)), 'SUCCESSOR_TRAINING_CALENDAR_INVALID')
    prefix = Path(output_directory)
    require(not prefix.is_absolute() and '..' not in prefix.parts and prefix.as_posix() not in ('', '.'),
            'SUCCESSOR_OUTPUT_INVALID')
    locator = lambda name: (prefix / name).as_posix()
    plan = {key: deepcopy(ancestor[key]) for key in ('domain_path', 'domain_source_hashes', 'securities')}
    plan.update(schema=SCHEMA, status='FIXED_OBSERVED_DOMAIN_NOT_PIT', calendar_path=calendar_path,
        calendar_source_hashes=calendar_source_hashes, session=decision['date'], history_start_date=dates[0],
        output_directory=locator('capture'), previous_manifest_path=previous_manifest_path,
        previous_manifest_sha256=previous_manifest_sha256, previous_completion_path=previous_completion_path,
        previous_completion_sha256=previous_completion_sha256)
    # Capture overlap must include the entire previous window for coordinate checks.
    plan['history_start_date'] = old['training_dates'][0]
    boundary = dict(decision_date=decision['date'], target_month=active['date'][:7], active_date=active['date'],
        decision_close_at=decision['close_at'], active_open_at=active['open_at'], training_dates=dates,
        source_references=[calendar_path])
    artifacts = {locator('capture_plan.json'): canonical(plan), locator('boundary.json'): canonical(boundary)}
    pins = {p: sha256(raw).hexdigest() for p, raw in artifacts.items()}
    settings = dict(root=str(root), plan_path=locator('capture_plan.json'), plan_sha256=pins[locator('capture_plan.json')],
        previous_manifest_path=previous_manifest_path, previous_manifest_sha256=previous_manifest_sha256,
        capture_index_path=locator('capture/completion_index.json'), preparation_output=locator('prepared'),
        publish_output=locator('published'), publish_request=locator('publish_request.json'),
        calendar_path=locator('boundary.json'), schedule_path=calendar_path,
        fixed_source_hashes={**calendar_source_hashes, locator('boundary.json'): pins[locator('boundary.json')]})
    artifacts[locator('settings.json')] = canonical(settings)
    return dict(status='SUCCESSOR_PLAN_CANDIDATE', target_month=active['date'][:7],
                artifacts=artifacts, validator='scripts.build_monthly_successor_plan.prepare',
                http_calls=0, search_calls=0, account_writes=False, published=False)
