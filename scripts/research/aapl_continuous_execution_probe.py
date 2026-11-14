"""Frozen historical AAPL targets with continuous cash and holdings; not full strategy."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from scripts.research.probe_aapl_historical_execution_events import inspect


def replay(events, buy_rule, initial_cash=10000, fee=18):
    cash, held, target = initial_cash, 0, 0
    records = []
    for original, raw in events:
        quantity = int(original['quantity'])
        target += quantity if original['side'] == 'BUY' else -quantity
        if target < 0:
            raise ValueError('NEGATIVE_FROZEN_TARGET')
        change = target - held
        record = dict(date=original['date'], target=target, before=held, action='NO_CHANGE')
        if change:
            side = 'BUY' if change > 0 else 'SELL'
            checked = inspect(raw, dict(original, side=side))
            rule = buy_rule if side == 'BUY' else 'OPEN_REFERENCE'
            arm = next(arm for arm in checked['arms'] if arm['name'] == rule)
            fill = arm['fill']
            record.update(action=side, requested=abs(change), rule=rule, filled=0)
            if fill:
                amount = abs(change) * fill['price']
                if side == 'SELL' or amount + fee <= cash:
                    cash += amount - fee if side == 'SELL' else -amount - fee
                    held += change
                    record.update(filled=abs(change), price=fill['price'])
                else:
                    record['reason'] = 'INSUFFICIENT_CASH_WHOLE_ORDER'
            else:
                record['reason'] = 'LIMIT_NOT_CROSSED'
        if held < 0 or cash < -1e-8:
            raise ValueError('ACCOUNT_INVARIANT_FAILED')
        close = json.loads(raw)['c'][-1]
        record.update(cash=cash, held=held, marked_equity=cash+held*close)
        records.append(record)
    return dict(buy_rule=buy_rule, fee=fee, initial_cash=initial_cash, ending_cash=cash,
                ending_shares=held, terminal_equity=records[-1]['marked_equity'],
                pnl=records[-1]['marked_equity']-initial_cash, records=records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    source = json.loads((args.directory/'event_results.json').read_text(encoding='utf-8'))
    events = []
    for result in sorted(source, key=lambda row: row['event']['date']):
        raw = (args.directory/(result['event']['date']+'.json')).read_bytes()
        if sha256(raw).hexdigest() != result['sha256']:
            raise ValueError('SOURCE_HASH_CHANGED')
        inspect(raw, result['event'])
        events.append((result['event'], raw))
    runs = [replay(events, rule, fee=fee) for fee in (0,18)
            for rule in ('OPEN_REFERENCE','1030','1200','OPEN_MINUS_1PCT')]
    output = dict(scope='Frozen AAPL target slice, 2021-01-04 through 2023-12-01.',
        limitations=['Not portfolio replay; no other securities or capital competition.',
                     'Targets frozen from original account; not recalculated from new equity.',
                     'No intervening-day valuation: no annual return or drawdown claim.',
                     'No retries between original event dates; no queue/partial fills model.'], runs=runs)
    (args.directory/'continuous_execution.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps([{k:v for k,v in run.items() if k!='records'} for run in runs],indent=2))


if __name__ == '__main__':
    main()
