"""Fixed recent-window price mechanism study; current roster, NOT historical signals."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import statistics
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from scripts.research.roa_entry_timing_event_probe import analyze, money

DATES = ('2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06',
         '2026-11-09', '2026-11-10', '2026-11-11', '2026-11-12', '2026-11-13')


def summarize(rows):
    result = {'complete_security_days': len(rows),
              'close_below_open_count': sum(row['close'] < row['opening'] for row in rows),
              'discount_cross_count': sum(row['discount_cross'] for row in rows)}
    for arm in ('1030', '1200'):
        values = [100 * (row['opening'] - row[arm]) / row['opening'] for row in rows]
        result[arm] = {'mean_price_improvement_pct': statistics.mean(values) if values else None,
                       'median_price_improvement_pct': statistics.median(values) if values else None,
                       'cheaper_count': sum(value > 0 for value in values),
                       'more_expensive_count': sum(value < 0 for value in values)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    source = args.directory / 'report.json'
    original = json.loads(source.read_bytes())
    tickers = sorted({row['ticker'] for row in original['cases']})
    if len(tickers) != 10:
        raise ValueError('FIXED_ROSTER_REQUIRES_TEN')
    # Written before retrieval: no outcome-dependent date or ticker selection.
    contract = dict(dates=DATES, tickers=tickers, source_report_sha256=sha256(source.read_bytes()).hexdigest(),
                    selection='Current ROA roster applied to all fixed dates; not historical ROA selections.',
                    split='First five versus last five dates; all dates retrospective, not untouched holdout.',
                    timestamps='US Eastern 09:30,10:30,12:00 first-trade minute proxies; no guaranteed fill.',
                    max_requests=100, retries=0)
    contract_path = args.directory / 'fixed_window_contract.json'
    if contract_path.exists():
        if json.loads(contract_path.read_bytes()) != json.loads(json.dumps(contract)):
            raise ValueError('FIXED_CONTRACT_CHANGED')
    else:
        contract_path.write_text(json.dumps(contract, indent=2), encoding='utf-8')

    def probe(case):
        date, ticker = case
        path = args.directory / f'{ticker}_{date}.raw.json'
        result = {'session': date, 'ticker': ticker}
        try:
            if not path.exists():
                start = int(datetime.fromisoformat(date + 'T14:30:00+00:00').timestamp())
                url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + ticker + '?' + urlencode(
                    dict(interval='1m', period1=start, period2=start + 390 * 60,
                         includePrePost='false', events='div,splits'))
                with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=12) as response:
                    raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise ValueError('SOURCE_TOO_LARGE')
                path.write_bytes(raw)
            raw = path.read_bytes()
            bars, missing, symbol = analyze(raw, date)
            result.update(source_sha256=sha256(raw).hexdigest(), missing_minutes=len(missing))
            if symbol != ticker:
                raise ValueError('IDENTITY_MISMATCH')
            if missing:
                result['status'] = 'INCOMPLETE_EXCLUDED'
                return result
            limit = money(bars[0][0] * .99)
            result.update(status='COMPLETE_PRICE_PROXY', opening=bars[0][0], close=bars[389 * 60][3],
                          discount_cross=any(row[2] < limit and row[4] > 0
                                             for offset, row in bars.items() if 60 <= offset < 385 * 60))
            result['1030'] = bars[60 * 60][0]
            result['1200'] = bars[150 * 60][0]
        except Exception as error:
            result.update(status='UNAVAILABLE', error=f'{type(error).__name__}: {error}')
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(probe, [(date, ticker) for date in DATES for ticker in tickers]))
    complete = [row for row in rows if row['status'] == 'COMPLETE_PRICE_PROXY']
    summaries = {date: summarize([row for row in complete if row['session'] == date]) for date in DATES}
    result = dict(status='FIXED_WINDOW_PRICE_MECHANISM_NOT_STRATEGY_BACKTEST',
                  captured_at=datetime.now(timezone.utc).isoformat(), contract=contract, rows=rows,
                  overall=summarize(complete), per_day=summaries,
                  first_half=summarize([row for row in complete if row['session'] in DATES[:5]]),
                  second_half=summarize([row for row in complete if row['session'] in DATES[5:]]),
                  limitations=['Current roster selection bias; correlated stocks and dates are not independent trials.',
                    'Incomplete days excluded, potentially nonrandom missingness; not complete bull/bear coverage.',
                    'Only observed-price mechanism; no cash or fees in this window-level statistic.'])
    (args.directory / 'fixed_window_report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('overall', 'first_half', 'second_half', 'per_day')}))


if __name__ == '__main__':
    main()
