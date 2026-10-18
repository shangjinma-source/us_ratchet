"""Read-only inventory, NOT annual return validation or an execution simulator.

Consumes an existing captured-training manifest and an explicitly supplied calendar
document. Observed minute captures are inventoried, never extrapolated to a year.
"""
import argparse
import gzip
import io
from collections import Counter
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
METHOD_FILES = ('backtest/return_priority_fresh_cash_quantity_search_v2.py',
                'data/current_research_capital_decision_v2.py',
                'data/current_quantity_v2_current_cash_plan.py',
                'data/current_quantity_v2_monthly_retarget.py',
                'data/current_quantity_v2_difference_plan.py',
                'data/current_research_intraday_execution.py')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from data.current_research_ohlc_panel import parse_provider_ohlc


def load_pinned(root, path, expected, pins):
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('SOURCE_OUTSIDE_ROOT')
    if resolved.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('SOURCE_TOO_LARGE')
    raw = resolved.read_bytes()
    actual = sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError('SOURCE_HASH_MISMATCH:' + str(path))
    pins[str(resolved.relative_to(root.resolve())).replace('\\', '/')] = actual
    return raw


def inspect(root, *, year, manifest_path, manifest_sha256,
            calendar_path, calendar_sha256, calendar_field='session_dates',
            observation_directory=None, as_of=None):
    root = Path(root).resolve()
    today = date.fromisoformat(as_of) if as_of else datetime.now(ZoneInfo('America/New_York')).date()
    if type(year) is not int or not 1900 <= year <= 2200:
        raise ValueError('INVALID_YEAR')
    pins = {}
    method_pins = {p: sha256((ROOT / p).read_bytes()).hexdigest() for p in METHOD_FILES}
    manifest = json.loads(load_pinned(root, manifest_path, manifest_sha256, pins))
    calendar = json.loads(load_pinned(root, calendar_path, calendar_sha256, pins))[calendar_field]
    if not calendar or calendar != sorted(set(calendar)):
        raise ValueError('ORDERED_CALENDAR_REQUIRED')
    for day in calendar:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError('INVALID_CALENDAR_DATE')
    # This is a supplied calendar inventory, not certification of an exchange year.
    sessions = [d for d in calendar if date.fromisoformat(d).year == year]
    training = manifest['training_dates']
    if len(training) != 253 or training != sorted(set(training)) or training[-1] != manifest['decision_date']:
        raise ValueError('EXACT_253_TRAINING_WINDOW_REQUIRED')
    for path, expected in manifest['source_hashes'].items():
        load_pinned(root, path, expected, pins)
    rows = []
    for candidate in manifest['candidates']:
        path = candidate['training_source']
        raw = load_pinned(root, path, manifest['source_hashes'][path], pins)
        parsed = parse_provider_ohlc(raw, candidate['ticker'])
        present = {d for d, values in zip(parsed['dates'], parsed['values']) if values[3] is not None}
        rows.append(dict(ticker=candidate['ticker'], security_id=candidate.get('security_id'),
                         declared_status=candidate['status'],
                         training_present=len(set(training) & present),
                         training_missing=sorted(set(training)-present),
                         supplied_year_sessions_present=len(set(sessions) & present),
                         supplied_year_sessions_missing=sorted(set(sessions)-present)))
    captures, failures, statuses = [], [], Counter()
    capture_days, methods = set(), Counter()
    if observation_directory is not None:
        folder = (root / observation_directory).resolve()
        if not folder.is_relative_to(root) or not folder.is_dir():
            raise ValueError('OBSERVATION_DIRECTORY_INVALID')
        events = sorted((folder / 'events').rglob('*.json'))
        if len(events) > 10000:
            raise ValueError('OBSERVATION_COUNT_LIMIT')
        for path in events:
            raw = path.read_bytes()
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError('EVENT_TOO_LARGE')
            pins[path.relative_to(root).as_posix()] = sha256(raw).hexdigest()
            event = json.loads(raw)
            statuses[event.get('response', {}).get('status', 'UNKNOWN')] += 1
            methods[event.get('research_binding', {}).get('method', 'UNKNOWN')] += 1
            for capture in event.get('captures', []):
                try:
                    at = datetime.fromisoformat(capture['captured_at'])
                    if at.utcoffset() is None:
                        raise ValueError('NAIVE_CAPTURE')
                    capture_days.add(at.astimezone(ZoneInfo('America/New_York')).date().isoformat())
                    body = load_pinned(root, (folder / capture['path']).relative_to(root), capture['sha256'], pins)
                    if body[:2] == b'\x1f\x8b':
                        with gzip.GzipFile(fileobj=io.BytesIO(body)) as source:
                            body = source.read(32*1024*1024+1)
                    if len(body)>32*1024*1024: raise ValueError('MINUTE_BODY_TOO_LARGE')
                    chart=json.loads(body)['chart']
                    if chart.get('error') is not None or len(chart.get('result') or [])!=1:
                        raise ValueError('MINUTE_RESULT_INVALID')
                    item=chart['result'][0]; meta=item['meta']
                    if meta.get('symbol')!=capture['ticker'] or meta.get('dataGranularity')!='1m' or meta.get('exchangeTimezoneName')!='America/New_York':
                        raise ValueError('MINUTE_METADATA_MISMATCH')
                    stamps=item['timestamp']
                    if not stamps or any(type(t)is not int or t<=0 for t in stamps) or stamps!=sorted(set(stamps)):
                        raise ValueError('MINUTE_TIMESTAMPS_INVALID')
                    days={datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat() for t in stamps}
                    for day in days:
                        if date.fromisoformat(day).year == year:
                            captures.append((day, capture['ticker']))
                except (ValueError, KeyError, OSError, TypeError, IndexError) as error:
                    failures.append(dict(event=path.relative_to(root).as_posix(), reason=str(error)))
    observed_days = sorted({d for d, _ in captures})
    return dict(schema='V2_ANNUAL_INPUT_PREFLIGHT_V1', status='INPUT_GAPS_NOT_ANNUAL_VALIDATION',
                year=year, as_of=today.isoformat(), year_completed=today > date(year, 12, 31),
                method='EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2',
                inspected_implementation_hashes=method_pins,
                request_policy='CURRENT_V2_MONTHLY_AND_FRESH_INTRADAY_LIMIT',
                sealed_daily_policy='SEALED_PREVIOUS_CLOSE_DAY_NOT_LIVE_MINUTE_RULE',
                training_definition='253 closes, 252 session intervals, twelve nonoverlapping 21-session gross scenarios',
                search_calls=0, book_calls=0, network_calls=0,
                supplied_calendar_sessions=sessions, calendar_full_year_verified=False,
                decision_dates_supplied=[manifest['decision_date']],
                monthly_decisions_complete=False, training_rows=rows,
                membership_observation_asof=manifest.get('membership_observation_asof'),
                membership_full_year_verified=False, full_pit_verified=False,
                minute_observation_days=observed_days,
                minute_observation_tickers=sorted({t for _, t in captures}),
                minute_capture_count=len(captures), observation_status_counts=dict(statuses),
                minute_capture_dates=sorted(capture_days), observation_method_counts=dict(methods),
                current_v2_usable_minute_coverage_verified=False,
                minute_capture_failures=failures,
                supplied_sessions_without_minute_observation=sorted(set(sessions)-set(observed_days)),
                minute_full_domain_or_session_coverage_verified=False,
                current_intraday_strategy_reproducible=False,
                missing_requirements=['Full-year dated membership/identity and per-decision training windows',
                    'Explicit complete exchange calendar including prior training year',
                    'Historical completed-minute and last-price observations at registered decision times',
                    'Registered intraday order timing, fills, partial fills, fees, actions and cash continuity'],
                limitations=['Daily OHLC permits only an explicitly separate daily execution assumption.',
                    'Observed captures may be old TOP1, unavailable, off-session or sparse; counts do not certify usable V2 evidence.',
                    'Current BUY uses floor-cent min(fresh last, completed minute low); current dollar allocation can change share quantity.',
                    'No historical annual profit, execution success, complete PIT or optimum is inferred.'],
                reviewed_source_hashes=pins)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest-path', 'manifest-sha256', 'calendar-path', 'calendar-sha256', 'output'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--root', default=str(ROOT))
    parser.add_argument('--calendar-field', default='session_dates')
    parser.add_argument('--observation-directory')
    args = vars(parser.parse_args())
    output = Path(args.pop('output'))
    result = inspect(**args)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
