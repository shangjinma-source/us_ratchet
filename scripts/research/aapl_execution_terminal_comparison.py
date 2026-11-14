"""Compare all fixed events at session close, including unfilled orders."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from scripts.research.probe_aapl_historical_execution_events import inspect


def terminal_value(side, quantity, close, fill, fee):
    if fill is None:
        return 0.0 if side == 'BUY' else quantity * close
    return quantity * (close - fill['price']) - fee if side == 'BUY' else quantity * fill['price'] - fee


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    results = json.loads((args.directory / 'event_results.json').read_text(encoding='utf-8'))
    rows = []
    for result in results:
        event = result['event']
        raw = (args.directory / (event['date'] + '.json')).read_bytes()
        if sha256(raw).hexdigest() != result['sha256']:
            raise ValueError('SOURCE_HASH_CHANGED')
        checked = inspect(raw, event)
        close = json.loads(raw)['c'][-1]
        quantity = float(event['quantity'])
        for fee in (0, 18):
            baseline = terminal_value(event['side'], quantity, close, checked['arms'][0]['fill'], fee)
            for arm in checked['arms']:
                value = terminal_value(event['side'], quantity, close, arm['fill'], fee)
                rows.append(dict(date=event['date'], side=event['side'], rule=arm['name'], fee=fee,
                                 filled=arm['fill'] is not None, advantage_usd=value-baseline,
                                 advantage_bps=(value-baseline)/(quantity*checked['reference'])*10000))
    summary = []
    for side in ('BUY', 'SELL'):
        for rule in sorted({row['rule'] for row in rows if row['side'] == side}):
            subset = [row for row in rows if row['side'] == side and row['rule'] == rule and row['fee'] == 18]
            summary.append(dict(side=side, rule=rule, events=len(subset), fills=sum(row['filled'] for row in subset),
                                mean_advantage_bps=sum(row['advantage_bps'] for row in subset)/len(subset),
                                better=sum(row['advantage_usd'] > .000001 for row in subset),
                                worse=sum(row['advantage_usd'] < -.000001 for row in subset)))
    output = dict(scope='Independent orders marked at same session close; not portfolio return or drawdown.',
                  benchmark='Same strict-cross OPEN_REFERENCE limit model, including its non-fills.',
                  limitations='No cross-session carry, reinvestment, queue, partial fills or cash competition.',
                  rows=rows, summary=summary)
    (args.directory / 'terminal_comparison.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
