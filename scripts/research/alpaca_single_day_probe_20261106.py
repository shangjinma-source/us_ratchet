"""Bounded read-only historical bars probe. Default is offline dry-run."""
import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

URL = 'https://data.alpaca.markets/v2/stocks/bars'
PARAMS = dict(symbols='AAPL', timeframe='1Min', start='2022-01-03T14:30:00Z',
              end='2022-01-03T20:59:59Z', feed='sip', adjustment='raw',
              asof='2022-01-03', limit=1000, sort='asc')


def inspect(payload):
    errors = []
    if not isinstance(payload, dict) or not isinstance(payload.get('bars'), dict):
        return dict(accepted=False, full_regular_session=False, errors=['invalid_response_shape'])
    bars = payload.get('bars', {}).get('AAPL', [])
    if not isinstance(bars, list):
        return dict(accepted=False, full_regular_session=False, errors=['invalid_bars_shape'])
    times = []
    lower = datetime(2022, 1, 3, 14, 30, tzinfo=timezone.utc)
    upper = datetime(2022, 1, 3, 21, 0, tzinfo=timezone.utc)
    for index, bar in enumerate(bars):
        try:
            stamp = datetime.fromisoformat(bar['t'].replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                raise ValueError('timezone_required')
            if not lower <= stamp < upper:
                errors.append(f'time_out_of_bounds:{index}')
            if stamp.second or stamp.microsecond:
                errors.append(f'non_minute_timestamp:{index}')
            times.append(stamp)
            values = [bar[k] for k in ('o', 'h', 'l', 'c', 'v')]
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
                raise ValueError('nonfinite_or_non_numeric')
            opening, high, low, close, volume = values
            if not (0 < low <= min(opening, close) <= max(opening, close) <= high) or volume < 0 or int(volume) != volume:
                errors.append(f'invalid_ohlcv:{index}')
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            errors.append(f'invalid_bar:{index}')
    if len(times) != len(set(times)):
        errors.append('duplicate_timestamps')
    if any(a >= b for a, b in zip(times, times[1:])):
        errors.append('not_strictly_ordered')
    if payload.get('next_page_token'):
        errors.append('pagination_incomplete')
    if not bars:
        errors.append('empty_bars')
    expected = {int(lower.timestamp()) + 60 * n for n in range(390)}
    observed = {int(t.timestamp()) for t in times if t.tzinfo is not None}
    complete = not errors and expected == observed
    return dict(accepted=not errors, status='COMPLETE_SINGLE_SESSION' if complete else 'INCOMPLETE_OR_INVALID', errors=errors, rows=len(bars),
                missing_minutes=len(expected - observed),
                full_regular_session=complete,
                first=times[0].isoformat() if times else None,
                last=times[-1].isoformat() if times else None,
                scope='single AAPL session; no fill-forward; no strategy profitability claim')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', default='tmp/alpaca_single_day_probe_20261106')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(mode='dry_run', method='GET', url=URL, params=PARAMS,
                             network_requests=0, credentials_read=False), indent=2))
        return 0
    output = Path(args.output)
    if output.exists():
        print('Output already exists; no credentials read or request sent.')
        return 2
    key = os.environ.get('APCA_API_KEY_ID')
    secret = os.environ.get('APCA_API_SECRET_KEY')
    if not key or not secret:
        print('Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY; no request sent.')
        return 2
    import requests
    try:
        response = requests.get(URL, params=PARAMS, headers={
            'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret},
            timeout=30, allow_redirects=False)
    except requests.RequestException:
        print('Request failed; exception details and credentials suppressed.')
        return 2
    if response.status_code != 200:
        print(f'HTTP {response.status_code}; body suppressed; no retry or redirect.')
        return 2
    try:
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get('bars'), dict):
            raise ValueError('unexpected response')
        checks = inspect(payload)
    except (ValueError, TypeError):
        print('Invalid market-data response; body not saved.')
        return 2
    output.mkdir(parents=True, exist_ok=False)
    # Exclusive create prevents silently overwriting a prior observation.
    with (output / 'bars.raw.json').open('xb') as handle:
        handle.write(response.content)
    checks.update(sha256=hashlib.sha256(response.content).hexdigest(),
                  bytes=len(response.content), url=URL, params=PARAMS, http_status=200)
    (output / 'checks.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
    print(json.dumps(checks, indent=2))
    return 0 if checks['full_regular_session'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
