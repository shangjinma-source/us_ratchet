"""Bounded execution-price study of saved ROA events; never writes an account.

Minute-open observations are price proxies, NOT guaranteed limit-order fills.
No account CAGR/drawdown is inferred from this short event sample.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from hashlib import sha256
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def money(value):
    return float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def analyze(raw, session):
    chart = json.loads(raw)['chart']
    if chart.get('error') or len(chart.get('result') or []) != 1:
        raise ValueError('SOURCE_UNAVAILABLE')
    result = chart['result'][0]
    opening = int(datetime.fromisoformat(session + 'T14:30:00+00:00').timestamp())
    # All frozen events are in November 2026, after the DST change.
    quotes = result['indicators']['quote'][0]
    bars = {}
    stamps = result.get('timestamp', [])
    if len(stamps) != len(set(stamps)) or stamps != sorted(stamps):
        raise ValueError('UNORDERED_OR_DUPLICATE_TIMESTAMPS')
    for index, stamp in enumerate(stamps):
        if not opening <= stamp < opening + 390 * 60:
            continue
        row = [quotes[key][index] for key in ('open', 'high', 'low', 'close', 'volume')]
        if any(value is None for value in row):
            continue
        o, h, low, close, volume = row
        if (not all(math.isfinite(value) for value in row)
                or not 0 < low <= min(o, close) <= max(o, close) <= h or volume < 0):
            raise ValueError('INVALID_OHLCV')
        bars[stamp - opening] = row
    missing = sorted(set(range(0, 390 * 60, 60)) - set(bars))
    meta = result['meta']
    if meta.get('dataGranularity') != '1m' or meta.get('currency') != 'USD':
        raise ValueError('SOURCE_UNIT_MISMATCH')
    if any(result.get('events', {}).values()):
        raise ValueError('CORPORATE_ACTION_REVIEW_REQUIRED')
    return bars, missing, meta.get('symbol')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    lifecycle_path = args.root / 'data/strategy_account/roa_20261106/lifecycle.json'
    lifecycle_bytes = lifecycle_path.read_bytes()
    life = json.loads(lifecycle_bytes)['state']
    with urlopen('http://127.0.0.1:8010/api/strategy-roa/snapshot', timeout=15) as response:
        account_view = json.load(response)
    identities = {row['security_id']: row['ticker'] for row in account_view['rows']}
    events = [event for event in life['events'] if event.get('materialized_revision')
              and event['session'] in ('2026-11-06', '2026-11-09', '2026-11-13')]
    cases = [(event, sid, ticker) for event in events for sid, ticker in identities.items()]

    def probe(case):
        event, sid, ticker = case
        session = event['session']
        path = args.output / f'{ticker}_{session}.raw.json'
        record = {'ticker': ticker, 'session': session, 'side': 'BUY' if event['risk_on'] else 'SELL',
                  'quantity': (event.get('targets') or {}).get(sid, 0)}
        try:
            if not path.exists():
                start = int(datetime.fromisoformat(session + 'T14:30:00+00:00').timestamp())
                url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + ticker + '?' + urlencode(
                    dict(interval='1m', period1=start, period2=start + 390 * 60,
                         includePrePost='false', events='div,splits'))
                with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=12) as response:
                    raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise ValueError('SOURCE_TOO_LARGE')
                path.write_bytes(raw)
            raw = path.read_bytes()
            bars, missing, symbol = analyze(raw, session)
            if symbol != ticker:
                raise ValueError('SOURCE_SYMBOL_MISMATCH')
            record.update(source_sha256=sha256(raw).hexdigest(), missing_minutes=len(missing))
            if missing:
                record['status'] = 'INCOMPLETE_SESSION_EXCLUDED'
                return record
            opening = bars[0][0]
            record.update(status='OBSERVED_PRICE_PROXY', opening=opening,
                          at_1030=bars[60 * 60][0], at_1200=bars[150 * 60][0], close=bars[389 * 60][3],
                          close_below_open=bars[389 * 60][3] < opening)
            saved_open = (event.get('opening_prices') or {}).get(sid)
            if saved_open:
                record['saved_open'] = float(Fraction(saved_open))
                record['saved_open_difference_pct'] = 100 * (opening / float(Fraction(saved_open)) - 1)
            limit = money(opening * .99)
            # Start at 09:31: the opening observation cannot authorize a pre-open order.
            eligible = [(offset, row) for offset, row in sorted(bars.items()) if 60 <= offset < 385 * 60]
            strict = next(((offset, min(row[0], limit)) for offset, row in eligible
                           if row[0] < limit or row[2] < limit), None)
            touch = next(((offset, min(row[0], limit)) for offset, row in eligible if row[2] <= limit), None)
            record.update(discount_limit=limit, strict_cross_proxy=strict, touch_proxy=touch)
            for arm in ('at_1030', 'at_1200'):
                record[arm + '_buy_improvement_pct'] = 100 * (opening - record[arm]) / opening
        except Exception as error:
            record.update(status='UNAVAILABLE', error=f'{type(error).__name__}: {error}')
        return record

    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(probe, cases))
    summaries = []
    for session in ('2026-11-06', '2026-11-13'):
        rows = [row for row in records if row['session'] == session and row['status'] == 'OBSERVED_PRICE_PROXY']
        total = sum(row['quantity'] * row['opening'] for row in rows)
        summary = dict(session=session, complete_symbols=len(rows), expected_symbols=10,
                       close_below_open=sum(row['close_below_open'] for row in rows))
        if total:
            for arm in ('at_1030', 'at_1200'):
                summary[arm + '_weighted_buy_improvement_pct'] = 100 * sum(
                    row['quantity'] * (row['opening'] - row[arm]) for row in rows) / total
                summary[arm + '_cheaper_symbols'] = sum(row[arm] < row['opening'] for row in rows)
            summary['discount_strict_cross_symbols'] = sum(row['strict_cross_proxy'] is not None for row in rows)
            summary['discount_touch_symbols'] = sum(row['touch_proxy'] is not None for row in rows)
            summary['saved_open_discrepancies_over_005pct'] = sum(
                abs(row.get('saved_open_difference_pct', 0)) > .05 for row in rows)
        summaries.append(summary)
    report = dict(status='EVENT_PRICE_STUDY_NOT_ACCOUNT_BACKTEST',
                  captured_at=datetime.now(timezone.utc).isoformat(),
                  lifecycle_sha256=sha256(lifecycle_bytes).hexdigest(),
                  cases=records, buy_summaries=summaries,
                  limitations=['Only two actual ROA buy events; no bull/bear coverage or annualization.',
                    'Minute first-bar open can differ from saved production opening reference; retain both and review discrepancies.',
                    'Minute opens and strict crossings are hypothetical execution proxies, not confirmed fills.',
                    'No bid/ask, queue, latency, independent corporate-action certification or cash replay yet.',
                    'Saved target shares remain fixed. Fees, idle cash and missed-trade opportunity cost not yet simulated.',
                    'Sell event observations are controls; sell timing is unchanged in the proposed comparison.'])
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'buy_summaries': summaries,
                      'unavailable': sum(row['status'] != 'OBSERVED_PRICE_PROXY' for row in records)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
