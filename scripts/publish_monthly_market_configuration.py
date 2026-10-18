"""Publish a conditional monthly configuration from completed capture evidence.

No fetching, selection, account writes or service activation. The explicit review
is a caller declaration of known contradictions, not exhaustive certification.
"""
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json

from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require, stamp
from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration
from data.current_quantity_v2_monthly_training import compile_saved_training, _daily
from scripts.prepare_monthly_captured_training import build


def publish(*, preparation_arguments, supplemental_hashes, calendar_path,
            schedule_path, identities_path, held_bar_sources, review_path, output_directory):
    root = Path(preparation_arguments['root']).resolve()
    clock = preparation_arguments['clock']
    now = stamp(clock())
    reader = MonthlyFileConfiguration(root=root, path='unused.json',
                                      sha256_value='0'*64, clock=clock)
    # Existing preparation validates receipts, complete domain and raw overlap.
    manifest, compiled, _ = build(**preparation_arguments)
    pins = dict(manifest['source_hashes'])
    for path, digest in supplemental_hashes.items():
        require(path not in pins or pins[path] == digest, 'MONTHLY_SOURCE_CONFLICT')
        pins[path] = digest
    package = reader._package(pins)
    files = package['files']
    for path in (calendar_path, schedule_path, identities_path, review_path):
        require(path in files, 'PUBLISH_SOURCE_MISSING')
    calendar, schedule, identities, review = [json.loads(files[p]) for p in
        (calendar_path, schedule_path, identities_path, review_path)]
    day = manifest['decision_date']
    require(calendar.get('training_dates') == manifest['training_dates'],
            'COMPILER_CALENDAR_TRAINING_BINDING')
    for value in (day, calendar['decision_date'], calendar['active_date']):
        require(date.fromisoformat(value).isoformat() == value, 'INVALID_PUBLISH_DATE')
    require(calendar['decision_date'] == day and
            calendar['target_month'] == calendar['active_date'][:7] > day[:7],
            'PUBLISH_MONTH_BOUNDARY_MISMATCH')
    require(schedule['schema'] == 'SCHEDULED_REGULAR_SESSIONS_V1', 'PUBLISH_SCHEDULE_REQUIRED')
    sessions = schedule['sessions']; days = [s['date'] for s in sessions]
    require(days == sorted(set(days)) == schedule['calendar'], 'PUBLISH_SCHEDULE_INVALID')
    require(day in days and days.index(day)+1 < len(days) and
            days[days.index(day)+1] == calendar['active_date'], 'PUBLISH_MONTH_BOUNDARY_MISMATCH')
    closing = sessions[days.index(day)]['close_at']
    opening = sessions[days.index(calendar['active_date'])]['open_at']
    capture_plan = json.loads(files[preparation_arguments['plan_path']])
    capture_schedule = json.loads(files[capture_plan['calendar_path']])
    captured_session = next(s for s in capture_schedule['sessions'] if s['date'] == day)
    for session in (sessions[days.index(day)], sessions[days.index(calendar['active_date'])]):
        require(all(stamp(session[k]).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                    == session['date'] for k in ('open_at', 'close_at'))
                and stamp(session['open_at']) < stamp(session['close_at']), 'PUBLISH_SESSION_TIME_MISMATCH')
    require(all(stamp(captured_session[k]) == stamp(sessions[days.index(day)][k])
                for k in ('open_at', 'close_at')), 'PUBLISH_CAPTURE_SCHEDULE_MISMATCH')
    require(stamp(closing) == stamp(calendar['decision_close_at']) <= now and
            stamp(opening) == stamp(calendar['active_open_at']) > stamp(closing),
            'PUBLISH_CALENDAR_TIME_MISMATCH')
    for doc in (calendar, schedule):
        refs = doc.get('source_references', list(doc.get('source_hashes', {})))
        require(refs and all(p in pins for p in refs), 'PUBLISH_CALENDAR_SOURCE_MISSING')
        require(all(pins.get(p) == h for p, h in doc.get('source_hashes', {}).items()),
                'PUBLISH_CALENDAR_SOURCE_CHANGED')
    require(set(review) == {'schema','decision_date','reviewed_at','source_references','reviewed_members','unresolved'}
            and review['schema'] == 'MONTHLY_KNOWN_SOURCE_REVIEW_V1'
            and review['decision_date'] == day
            and stamp(closing) <= stamp(review['reviewed_at']) <= now
            and review['source_references']
            and all(p in pins for p in review['source_references'])
            and type(review['unresolved']) is list, 'PUBLISH_REVIEW_REQUIRED')
    members = {r['ticker'] for r in manifest['candidates']}
    require(type(review['reviewed_members']) is list and len(review['reviewed_members']) == len(members)
            and set(review['reviewed_members']) == members, 'PUBLISH_REVIEW_DOMAIN_INCOMPLETE')
    sids = {r['security_id'] for r in manifest['candidates'] if r['security_id']}
    issuers = {r.get('issuer_id') for r in manifest['candidates']} - {None}
    for gap in review['unresolved']:
        require(set(gap) == {'ticker','security_id','issuer_id','reason','source_references'}
                and type(gap['reason']) is str and gap['reason']
                and gap['source_references']
                and all(p in review['source_references'] for p in gap['source_references']),
                'PUBLISH_REVIEW_INVALID')
        require(not (gap['ticker'] in members or gap['security_id'] in sids or
                     gap['issuer_id'] in issuers), 'KNOWN_SOURCE_CONTRADICTION')
    domain = set(compiled['input']['search_arguments']['prices'])
    require(domain | set(held_bar_sources) <= set(identities['securities']), 'PUBLISH_IDENTITIES_MISSING')
    for sid, path in held_bar_sources.items():
        require(path in files, 'PUBLISH_HELD_SOURCE_MISSING')
        _, closes = _daily(files[path], identities['securities'][sid]['ticker'])
        require(closes.get(day) is not None, 'PUBLISH_HELD_CLOSE_MISSING')
    for row in manifest['candidates']:
        if row['security_id'] in domain:
            identity = identities['securities'][row['security_id']]
            require(identity['ticker'] == row['ticker'] and identity['issuer_id'] == row['issuer_id'],
                    'PUBLISH_IDENTITY_MISMATCH')
    # No output is created until evidence and explicit contradiction review pass.
    reader._read(preparation_arguments['plan_path'], preparation_arguments['plan_sha256'])
    output = Path(output_directory)
    require(not output.is_absolute() and '..' not in output.parts, 'INVALID_OUTPUT_PATH')
    destination = root/output
    require(destination.resolve().is_relative_to(root) and not destination.exists(), 'CREATE_ONLY_OUTPUT_EXISTS')
    destination.mkdir(parents=True, exist_ok=False)
    manifest_path = (output/'manifest.json').as_posix()
    manifest['source_hashes'] = dict(pins)
    raw = canonical(manifest)
    with (root/manifest_path).open('xb') as stream: stream.write(raw)
    pins[manifest_path] = sha256(raw).hexdigest()
    config = dict(schema='QUANTITY_V2_MONTHLY_SERVER_INPUTS_V2', account_reviews=[],
        market_entries=[dict(target_month=calendar['target_month'], decision_date=day,
            source_hashes=pins, manifest_path=manifest_path, calendar_path=calendar_path,
            identities_path=identities_path, held_bar_sources=held_bar_sources)])
    raw = canonical(config); path = (output/'configuration.json').as_posix()
    with (root/path).open('xb') as stream: stream.write(raw)
    digest = sha256(raw).hexdigest()
    # Target-month clock is solely a reader routing probe, not a historical clock claim.
    probe = MonthlyFileConfiguration(root=root, path=path, sha256_value=digest,
                                    clock=lambda: stamp(calendar['active_open_at']))
    supplied = probe.market_reader(None)
    validated = compile_saved_training(supplied['source_package'], supplied['manifest_path'])
    return dict(status='PUBLISHED_CONDITIONAL_NOT_ACTIVATED', config_path=path,
        config_sha256=digest, compiler_status=validated['status'],
        reader_probe_clock_basis='TARGET_MONTH_ROUTING_ONLY', published_at=now.isoformat(),
        search_calls=0, account_writes=False, service_activated=False)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--request-sha256', required=True)
    parser.add_argument('--experimental-domain', action='store_true', help='Use the explicit fixed experimental domain; not production admission.')
    args = parser.parse_args(argv)
    try:
        clock = lambda: datetime.now(timezone.utc)
        reader = MonthlyFileConfiguration(root=args.root, path=args.request,
            sha256_value=args.request_sha256, clock=clock)
        request = json.loads(reader._read(args.request, args.request_sha256, 1024*1024))
        require(type(request) is dict and set(request) == {
            'preparation_arguments','supplemental_hashes','calendar_path','schedule_path',
            'identities_path','held_bar_sources','review_path','output_directory'}, 'INVALID_PUBLISH_REQUEST')
        preparation = request['preparation_arguments']
        require(type(preparation) is dict and set(preparation) == {
            'previous_manifest_path','previous_manifest_sha256','capture_index_path',
            'capture_index_sha256','plan_path','plan_sha256'}, 'INVALID_PUBLISH_REQUEST')
        # root and clock can only come from CLI/server context, never request JSON.
        preparation.update(root=Path(args.root), clock=clock)
        if args.experimental_domain:
            from scripts.monthly_experimental_domain_capture import prepare
            preparation['plan_validator'] = prepare
        result = publish(**request)
    except Exception as error:
        # Exceptions can contain absolute paths, URLs or arbitrary source bytes.
        # Emit no exception text; fixed reason classes remain machine-readable.
        reason = 'PUBLISH_VALIDATION_FAILED'
        if isinstance(error, OSError): reason = 'PUBLISH_FILE_IO_FAILED'
        if str(error) == 'KNOWN_SOURCE_CONTRADICTION': reason = 'KNOWN_SOURCE_CONTRADICTION'
        if str(error) == 'CREATE_ONLY_OUTPUT_EXISTS': reason = 'CREATE_ONLY_OUTPUT_EXISTS'
        result = dict(status='BLOCKED', reason=reason, search_calls=0,
                      account_writes=False, service_activated=False)
        if args.experimental_domain: result['domain_mode'] = 'EXPERIMENTAL_FIXED_DOMAIN_NOT_PRODUCTION_ADMISSION'
        print(json.dumps(result, ensure_ascii=False)); return 1
    if args.experimental_domain: result['domain_mode'] = 'EXPERIMENTAL_FIXED_DOMAIN_NOT_PRODUCTION_ADMISSION'
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
