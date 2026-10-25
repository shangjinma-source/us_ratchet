"""Restore frozen research OHLC coordinates; never authorize economic execution."""
import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'
OUTPUT = ROOT / 'tmp/recent_execution_prices_20261026'
START, END = '2020-12-31', '2023-12-29'
FIELDS = ('open', 'high', 'low', 'close')


def coordinate_factor(calibration, events, day):
    factor = Fraction(calibration['factor'])
    for event in events:
        if event.get('apply_nominal_scale') is False:
            continue
        event_day, ratio = event['date'], Fraction(event['factor'])
        if ratio <= 0:
            raise ValueError('NONPOSITIVE_COORDINATE_FACTOR')
        if day < event_day <= calibration['date']:
            factor *= ratio
        elif calibration['date'] < event_day <= day:
            factor /= ratio
    return factor


def prepare(input_path=INPUT):
    snapshots = {}

    def read(path, expected=None):
        path = path.resolve()
        if path not in snapshots:
            raw = path.read_bytes()
            snapshots[path] = (raw, hashlib.sha256(raw).hexdigest())
        raw, digest = snapshots[path]
        if expected is not None and digest != expected:
            raise ValueError('BOUND_SOURCE_CHANGED:' + str(path))
        return raw

    training = json.loads(read(input_path))
    read(Path(__file__))
    # Verify all evidence bound by the producer, not just current price files.
    for relative, digest in training['source_hashes'].items():
        read(ROOT / relative, digest)
    reference_path = ROOT / 'tmp/free_history_price_probe_20261025_v1/AAPL.response'
    reference = json.loads(read(reference_path))['chart']['result'][0]
    sessions = sorted({datetime.fromtimestamp(t, timezone.utc).date().isoformat()
                       for t in reference['timestamp']
                       if START <= datetime.fromtimestamp(t, timezone.utc).date().isoformat() <= END})
    expected_dates = set(sessions)
    prices, reviews, inventory, anomalies, missing_streams = {}, [], [], [], []
    identities = {}
    for fixed in training['fixed_sources']:
        ticker, source, sid = fixed['ticker'], fixed['source'], fixed['security_id']
        raw = read(ROOT / source, fixed['sha256'])
        rows, events = [], None
        if source.endswith(('.response', '.response.bin')):
            result = json.loads(raw)['chart']['result'][0]
            quote = result['indicators']['quote'][0]
            events = result.get('events', {})
            for index, stamp in enumerate(result['timestamp']):
                day = datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
                if START <= day <= END:
                    rows.append((day, {key: quote[key][index] for key in FIELDS}))
        else:
            for original in csv.DictReader(raw.decode('utf-8-sig').splitlines()):
                row = {key.lower(): value for key, value in original.items()}
                day = row['date']
                if day[4:5] != '-':
                    day = datetime.strptime(day, '%d-%m-%Y').date().isoformat()
                if START <= day <= END:
                    rows.append((day, {key: row.get(key) for key in FIELDS}))
        calibration = fixed.get('calibration')
        restored, seen = {}, set()
        for day, values in rows:
            if day in seen:
                raise ValueError('DUPLICATE_SOURCE_DATE:' + ticker + ':' + day)
            seen.add(day)
            if calibration is None:
                continue
            try:
                factor = coordinate_factor(calibration, fixed['provider_coordinate_events'], day)
                bar = {key: Fraction(str(value)) * factor for key, value in values.items()}
                if min(bar.values()) <= 0 or not bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high']:
                    raise ValueError('OHLC_ORDER_OR_NONPOSITIVE')
            except (ValueError, ZeroDivisionError) as error:
                anomalies.append(dict(ticker=ticker, date=day, kind='INVALID_RAW_OR_RESTORED_BAR', detail=str(error)))
                continue
            restored[day] = {key: str(value) for key, value in bar.items()}
        prices[ticker] = restored
        identities.setdefault(sid, []).append(ticker)
        missing = sorted(expected_dates - set(restored))
        observed = sorted(seen)
        reviews.append(dict(ticker=ticker, security_id=sid, source=source, sha256=fixed['sha256'],
            calibration=calibration, provider_coordinate_events=fixed['provider_coordinate_events'],
            actual_source_first=observed[0] if observed else None, actual_source_last=observed[-1] if observed else None,
            restored_rows=len(restored), missing_dates=missing,
            dates_before_source=[d for d in missing if observed and d < observed[0]],
            dates_after_source=[d for d in missing if observed and d > observed[-1]],
            unexpected_dates=sorted(set(restored) - expected_dates),
            missing_reason='SOURCE_COVERAGE_ONLY_IPO_DELISTING_NOT_INFERRED',
            provider_action_stream_available=events is not None))
        if calibration is None:
            appearances = [candidate for window in training['windows']
                           for candidate in window['window']['candidates']
                           if candidate['ticker'] == ticker]
            all_excluded = bool(appearances) and all(candidate['status'] == 'EXCLUDED_TRAINING_RULE'
                                                      for candidate in appearances)
            anomalies.append(dict(ticker=ticker, kind='CALIBRATION_MISSING',
                all_member_appearances_legally_excluded=all_excluded,
                blocks_ready_training=not all_excluded, future_exposure_requires_nominal_mark=True))
        if events is None:
            missing_streams.append(ticker)
        else:
            for kind, records in events.items():
                for event in records.values():
                    day = datetime.fromtimestamp(event['date'], timezone.utc).date().isoformat()
                    inventory.append(dict(ticker=ticker, security_id=sid, date=day, kind=kind,
                        within_execution_range=START <= day <= END, provider_event=event,
                        source=source, source_sha256=fixed['sha256'], economic_action_admitted=False))
    checks = []
    for window in training['windows']:
        for candidate in window['window']['candidates']:
            if candidate['status'] != 'READY_CONDITIONAL':
                continue
            day, ticker = window['decision_cutoff'], candidate['ticker']
            bar = prices[ticker].get(day)
            matches = bar is not None and Fraction(bar['close']) == Fraction(candidate['decision_cost'])
            checks.append(dict(ticker=ticker, decision_date=day, exact_match=matches))
            if not matches:
                anomalies.append(dict(ticker=ticker, date=day, kind='READY_DECISION_COST_MISMATCH'))
    # No concurrent rewrite may silently create a mixture of evidence versions.
    for path, (_, digest) in snapshots.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('INPUT_CHANGED_DURING_PREPARATION:' + str(path))
    collisions = {sid: tickers for sid, tickers in identities.items() if len(tickers) > 1}
    ohlc = {sid: prices[tickers[0]] for sid, tickers in identities.items() if len(tickers) == 1}
    return dict(status='PRICE_COORDINATES_PREPARED_ECONOMIC_EXECUTION_NOT_AUTHORIZED',
        start=START, end=END, session_dates=sessions, ohlc=ohlc, ohlc_by_ticker=prices,
        security_identity_collisions=collisions, source_reviews=reviews, anomalies=anomalies,
        ready_decision_checks=checks, provider_event_inventory=inventory,
        action_stream_missing=sorted({fixed['security_id'] for fixed in training['fixed_sources']
                                      if fixed['ticker'] in missing_streams}),
        action_stream_missing_by_ticker=missing_streams,
        provider_coordinate_events_are_not_share_actions=True,
        source_hashes={path.relative_to(ROOT).as_posix(): digest for path, (_, digest) in snapshots.items()},
        training_snapshot_sha256=snapshots[input_path.resolve()][1],
        member_windows=[dict(decision_cutoff=w['decision_cutoff'],members=w['admission']['members'],
                             status=w['status']) for w in training['windows']],
        runner_execution_authorized=False, search_calls=0, economic_run_completed=False,
        limitations=['Reference calendar is saved AAPL timestamps, not an independent exchange calendar.',
                    'Missing bars retained as explicit gaps; no forward fill, interpolation or member removal.',
                    'Price-coordinate events must not become holdings actions; dividends remain unmapped.',
                    'Ticker views retained separately; identity collisions require explicit alias resolution.'])


if __name__ == '__main__':
    result = prepare()
    OUTPUT.mkdir(exist_ok=True)
    target = OUTPUT / 'execution_prices_v1.json'
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result, indent=2), encoding='utf-8')
    temporary.replace(target)
    print(json.dumps(dict(securities=len(result['source_reviews']), sessions=len(result['session_dates']),
        decision_checks=len(result['ready_decision_checks']), anomalies=len(result['anomalies']),
        collisions=result['security_identity_collisions'], training_sha=result['training_snapshot_sha256'])))
