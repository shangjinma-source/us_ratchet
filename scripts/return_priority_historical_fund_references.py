"""Independent next-open fund references from saved quote channels; no search."""
import argparse
from datetime import datetime
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo


def prepare(root, inputs_path):
    sources = {}
    def read(path):
        raw = path.read_bytes()
        sources[str(path)] = hashlib.sha256(raw).hexdigest()
        return raw
    windows = json.loads(read(inputs_path))['windows']
    series = {}
    for ticker in ('QQQ', 'SPY'):
        base = root / 'data/cache/research/current_raw_capture_20261013_v1'
        receipt = json.loads(read(base / (ticker + '.receipt.json')))
        raw = read(base / (ticker + '.response.bin'))
        if hashlib.sha256(raw).hexdigest() != receipt['raw_sha256']:
            raise ValueError('Receipt/raw mismatch')
        decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
        data = json.loads(decoded)['chart']['result'][0]
        if data['meta']['symbol'] != ticker or data.get('events', {}).get('splits'):
            raise ValueError('Unexpected symbol or split; explicit treatment required')
        dates = [datetime.fromtimestamp(value, ZoneInfo(data['meta']['exchangeTimezoneName'])).date().isoformat()
                 for value in data['timestamp']]
        if len(set(dates)) != len(dates):
            raise ValueError('Duplicate session')
        quote = data['indicators']['quote'][0]
        series[ticker] = {day: {'open': quote['open'][i], 'close': quote['close'][i]}
                          for i, day in enumerate(dates)}
    result = []
    for window in windows:
        args = window['outcome_arguments']
        budget = Fraction(args['entered_cash'])
        days = args['session_dates'][1:]
        if Fraction(args['fee_bps']) or len(days) != 21:
            raise ValueError('Zero fee / 21-session comparison required')
        refs = {}
        for ticker, rows in series.items():
            opening = Fraction(str(rows[days[0]]['open']))
            if opening <= 0:
                raise ValueError('Nonpositive entry price')
            quantity = int(budget // opening)
            cash = budget - quantity * opening
            peak, drawdown, ledger = budget, Fraction(0), []
            for day in days:
                close = Fraction(str(rows[day]['close']))
                if close <= 0:
                    raise ValueError('Nonpositive mark')
                equity = cash + quantity * close
                peak = max(peak, equity)
                drawdown = max(drawdown, 1 - equity / peak)
                ledger.append(dict(date=day, close=str(close), equity=str(equity)))
            refs[ticker] = dict(shares=quantity, entry_open=str(opening), cash=str(cash),
                               return_fraction=str(equity / budget - 1), maximum_drawdown=str(drawdown),
                               daily_ledger=ledger)
        result.append(dict(decision_cutoff=args['decision_date'], references=refs))
    return dict(windows=result, source_hashes=sources, search_calls=0,
                conditional_provider_quote_units=True, independent_fresh_cash_windows=True,
                dividends_included=False, taxes_and_other_fees_included=False,
                quote_basis_independently_authenticated=False, cagr=None,
                comparison_scope='Same next-open entry, 21-session exit marks, integer shares and zero commission; price return only.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(Path(__file__).resolve().parents[1], args.inputs.resolve())
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
