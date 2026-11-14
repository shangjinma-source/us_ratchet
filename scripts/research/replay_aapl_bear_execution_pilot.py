"""AAPL-only historical execution pilot; not a full holding-period account backtest."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from scripts.research.roa_entry_timing_account_probe import ARMS, simulate


def load_day(path, date):
    raw = path.read_bytes()
    data = json.loads(raw)
    start = int(datetime.fromisoformat(date + 'T14:30:00+00:00').timestamp())
    expected = list(range(start, start + 390 * 60, 60))
    if data.get('s') != 'ok' or data['t'] != expected:
        raise ValueError('INCOMPLETE_OR_WRONG_SESSION')
    if any(len(data[k]) != 390 for k in ('o', 'h', 'l', 'c', 'v')):
        raise ValueError('COLUMN_LENGTH_MISMATCH')
    bars = {}
    for index in range(390):
        values = [data[k][index] for k in ('o', 'h', 'l', 'c', 'v')]
        o, high, low, close, volume = values
        if not all(math.isfinite(x) for x in values) or not 0 < low <= min(o, close) <= max(o, close) <= high or volume < 0:
            raise ValueError('INVALID_BAR')
        bars[index * 60] = values
    return {'AAPL': bars}, sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    loaded = [load_day(args.directory / (date + '.json'), date)
              for date in ('2022-01-03', '2022-01-24')]
    results = []
    for arm in ARMS:
        for sell_start in (1, 60, 150):
            result = simulate([x[0] for x in loaded], {'AAPL': 16}, 4000, arm, 18, sell_start=sell_start)
            # The intervening holding days are absent: never publish the helper's drawdown/return as a full path.
            results.append(dict(arm=arm, sell_start=sell_start,
                modeled_profit=result['net_profit'], fills=result['fills'],
                unbought=result['unbought'], remaining_holdings=result['remaining_holdings']))
    output = dict(status='SINGLE_SECURITY_EXECUTION_PILOT', source_hashes=[x[1] for x in loaded],
        fixed_shares=16, hypothetical_available_cash=4000, fee_per_fill=18,
        dates=['2022-01-03', '2022-01-24'], results=results,
        limitations=['Not a portfolio result; no intervening daily path, dividends or stop simulation.',
            'Fixed shares from historical event; 4000 cash is an isolated sufficient budget, not real account cash.',
            'Strict crossing is hypothetical; quote queues, partial fills and spread are not reproduced.',
            'Unfilled orders expire; no replacement on missing intervening sessions.'])
    (args.directory / 'execution_pilot.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
