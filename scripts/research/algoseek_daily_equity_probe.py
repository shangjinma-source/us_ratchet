"""Daily marks for the frozen-target price-only replay; not total-return validation."""
import argparse
import csv
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    source = args.directory / 'continuous_portfolio_price_only.json'
    raw = source.read_bytes()
    replay = json.loads(raw)
    runs = replay['runs']
    start, end = runs[0]['records'][0]['date'], runs[0]['records'][-1]['date']
    symbols = sorted({symbol for run in runs for record in run['records'] for symbol, quantity in record['holdings'].items() if quantity})
    cache_path = args.directory / 'daily_close_cache.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    with zipfile.ZipFile(args.directory / 'full_archive.zip') as archive:
        names = sorted(name for name in archive.namelist() if name.startswith('2021/') and name.endswith('.zip'))
        days = []
        for name in names:
            date = Path(name).stem
            day = date[:4] + '-' + date[4:6] + '-' + date[6:8]
            if not start <= day <= end:
                continue
            days.append(day)
            if day in cache:
                continue
            marks = {}
            with zipfile.ZipFile(io.BytesIO(archive.read(name))) as session:
                for symbol in symbols:
                    matches = [item for item in session.namelist() if item.endswith('/' + symbol + '.csv')]
                    if len(matches) != 1:
                        raise ValueError('MISSING_SYMBOL:' + day + ':' + symbol)
                    csv_raw = session.read(matches[0])
                    # Nasdaq 2021 calendar: Thanksgiving Friday closed at 13:00 ET.
                    closing_minute = '12:59' if day == '2021-11-26' else '15:59'
                    rows = [row for row in csv.DictReader(io.StringIO(csv_raw.decode())) if row['TimeBarStart'] == closing_minute]
                    if len(rows) != 1 or rows[0]['Date'] != date or rows[0]['Ticker'] != symbol:
                        raise ValueError('INVALID_FINAL_BAR:' + day + ':' + symbol)
                    price = float(rows[0]['LastTradePrice'])
                    if not math.isfinite(price) or price <= 0:
                        raise ValueError('INVALID_CLOSE')
                    marks[symbol] = dict(price=price, csv_sha256=sha256(csv_raw).hexdigest())
            cache[day] = marks
            cache_path.write_text(json.dumps(cache), encoding='utf-8')
            if len(days) % 20 == 0:
                print('daily sessions', len(days), day, flush=True)
    results = []
    for run in runs:
        events = {record['date']: record for record in run['records']}
        cash, holdings, peak, maximum_drawdown = 20000.0, {}, 20000.0, 0.0
        ledger = []
        for day in days:
            if day == '2021-07-20':
                holdings['NVDA'] = holdings.get('NVDA', 0) * 4
            if day in events:
                cash, holdings = events[day]['cash'], dict(events[day]['holdings'])
            equity = cash + sum(quantity * cache[day][symbol]['price'] for symbol, quantity in holdings.items() if quantity)
            if day in events and abs(equity - events[day]['equity']) > 1e-6:
                raise ValueError('EVENT_EQUITY_MISMATCH')
            peak = max(peak, equity)
            drawdown = equity / peak - 1
            maximum_drawdown = min(maximum_drawdown, drawdown)
            ledger.append(dict(date=day, equity=equity, drawdown_pct=drawdown * 100))
        results.append(dict(buy_rule=run['buy_rule'], sell_rule=run['sell_rule'], fee=run['fee'],
                            price_only_return_pct=run['price_only_return_pct'],
                            observed_daily_maximum_drawdown_pct=maximum_drawdown * 100, ledger=ledger))
    output = dict(scope=replay['scope'], sessions=len(days), input_sha256=sha256(raw).hexdigest(),
                  limitations=[item for item in replay['limitations'] if not item.startswith('No intervening-day valuation:')] + ['Daily marks are final-minute trades, not official close auctions.',
                      'Archive session coverage not yet cross-checked with exchange calendar; drawdown is observed-session only.'], runs=results)
    (args.directory / 'daily_equity_price_only.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps([{key: value for key, value in run.items() if key != 'ledger'} for run in results], indent=2))


if __name__ == '__main__':
    main()
