"""Compare limit references at identical submission times, never hindsight lows."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from scripts.research.probe_aapl_historical_execution_events import inspect
from scripts.research.roa_entry_timing_event_probe import money
from scripts.research.aapl_execution_terminal_comparison import terminal_value


def simulate(data, side, start, reference):
    if start not in (60, 150) or reference not in ('OPEN', 'LATEST_COMPLETED'):
        raise ValueError('UNSUPPORTED_FIXED_COMPARISON')
    value = data['o'][0] if reference == 'OPEN' else data['c'][start - 1]
    if value is None:
        raise ValueError('REFERENCE_UNAVAILABLE')
    limit = money(value)
    fill = None
    for minute in range(start, 385):
        if not data['v'][minute]:
            continue
        crossed = data['l'][minute] < limit if side == 'BUY' else data['h'][minute] > limit
        if crossed:
            price = min(data['o'][minute], limit) if side == 'BUY' else max(data['o'][minute], limit)
            fill = dict(price=price, minute=minute)
            break
    return dict(reference=reference, limit=limit, fill=fill)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    validation = json.loads((args.directory / 'event_validation.json').read_text())
    rows, hashes = [], {}
    for result in validation['results']:
        if not result['status'].startswith('VALID'):
            raise ValueError('INCOMPLETE_EVENT_SET')
        event = result['event']
        filename = event['date'].replace('-', '') + '_' + result['symbol'] + '.json'
        raw = (args.directory / 'normalized' / filename).read_bytes()
        hashes[filename] = sha256(raw).hexdigest()
        inspect(raw, event, allow_no_trade=True)
        data = json.loads(raw)
        for start in (60, 150):
            opening = simulate(data, event['side'], start, 'OPEN')
            current = simulate(data, event['side'], start, 'LATEST_COMPLETED')
            quantity = float(event['quantity'])
            for fee in (0, 18):
                difference = terminal_value(event['side'], quantity, data['c'][-1], current['fill'], fee) - terminal_value(event['side'], quantity, data['c'][-1], opening['fill'], fee)
                rows.append(dict(date=event['date'], symbol=result['symbol'], side=event['side'], start=start,
                    fee=fee, opening=opening, current=current, advantage_bps=difference/(quantity*data['o'][0])*10000))
    summary = []
    for start in (60, 150):
        for side in ('BUY', 'SELL'):
            subset = [row for row in rows if row['start']==start and row['side']==side and row['fee']==18]
            summary.append(dict(start=start, side=side, events=len(subset),
                open_fills=sum(row['opening']['fill'] is not None for row in subset),
                current_fills=sum(row['current']['fill'] is not None for row in subset),
                mean_current_advantage_bps=sum(row['advantage_bps'] for row in subset)/len(subset),
                better=sum(row['advantage_bps']>1e-6 for row in subset), worse=sum(row['advantage_bps']< -1e-6 for row in subset)))
            favorable = [row for row in subset if (row['current']['limit'] < row['opening']['limit'] if side == 'BUY' else row['current']['limit'] > row['opening']['limit'])]
            summary[-1]['current_reference_more_favorable'] = dict(events=len(favorable),
                mean_advantage_bps=sum(row['advantage_bps'] for row in favorable)/len(favorable) if favorable else None,
                better=sum(row['advantage_bps']>1e-6 for row in favorable), worse=sum(row['advantage_bps']< -1e-6 for row in favorable))
    output = dict(scope='Same submission time, quantity, expiry and fee; only limit reference changes.',
        limitations=['Independent events, no portfolio return or cash reservation claim.',
                     'Latest completed minute close proxies refresh quote; no historical bid/ask execution certification.',
                     'Strict crossing with price improvement, no queue or partial fill model.',
                     'Open means first-minute first trade, not official auction price.',
                     'Unfilled buys keep cash, unfilled sells keep stock; marked at same-day close.'],
        source_hashes=hashes, rows=rows, summary=summary)
    (args.directory / 'limit_reference_comparison.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
