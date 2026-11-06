"""Continuous QQQ account reference; reuse frozen payable-date evidence."""
import gzip
import hashlib
import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.research.qqq_paid_reinvestment_20261106 import run_book

ROOT = Path(__file__).resolve().parents[2]


def main():
    reference = ROOT / 'tmp/qqq_reinvest_20261106/report.json'
    report = json.loads(reference.read_bytes())
    pins = dict(report['source_hashes'])
    for name, digest in pins.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError('SOURCE_CHANGED:' + name)
    panel = {}
    for name in ('tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin',
                 'data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'):
        raw = (ROOT / name).read_bytes()
        source = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw,
                            parse_float=str)['chart']['result'][0]
        assert source['meta']['symbol'] == 'QQQ'
        assert not source.get('events', {}).get('splits')
        quotes = source['indicators']['quote'][0]
        for index, timestamp in enumerate(source['timestamp']):
            day = datetime.fromtimestamp(timestamp, ZoneInfo('America/New_York')).date().isoformat()
            if not '2020-12-31' <= day <= '2026-07-30':
                continue
            values = {key: str(Fraction(quotes[key][index])) for key in ('open', 'close')}
            assert all(Fraction(value) > 0 for value in values.values())
            assert day not in panel or panel[day] == values
            panel[day] = values
    days = sorted(panel)
    assert days[0] == '2020-12-31' and days[-1] == '2026-07-30'
    assert len(days) == 1400
    events = {}
    for event in report['event_matches']:
        if days[0] < event['ex_date'] <= days[-1]:
            row = {key: event[key] for key in ('ex_date', 'payment_date', 'amount', 'currency', 'type')}
            assert row['ex_date'] not in events or events[row['ex_date']] == row
            events[row['ex_date']] = row
    # Reject any omissions from the previously verified two-window event sets.
    raw_events = json.loads((ROOT / 'tmp/qqq_reinvest_20261106/nasdaq_dividends.json').read_bytes())
    expected = set()
    for row in raw_events['data']['dividends']['rows']:
        if row['exOrEffDate'] != 'N/A':
            day = datetime.strptime(row['exOrEffDate'], '%m/%d/%Y').date().isoformat()
            if days[0] < day <= days[-1]:
                expected.add(day)
    assert set(events) == expected, 'UNVERIFIED_DIVIDEND_GAP'
    book = run_book(days, panel, list(events.values()))
    equity = [20000.] + [float(Fraction(row['equity'])) for row in book['daily_ledger']]
    peak = equity[0]
    drawdown = 0.
    for value in equity:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    years = (datetime.fromisoformat(days[-1]) - datetime.fromisoformat(days[0])).days / 365.25
    for path in (reference, Path(__file__), ROOT / 'scripts/research/qqq_paid_reinvestment_20261106.py'):
        pins[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    output = dict(book=book, anchor=days[0], end=days[-1], sessions=len(days)-1,
                  metrics=dict(cagr_pct=100*((equity[-1]/20000.)**(1/years)-1),
                               drawdown_pct=100*drawdown, terminal=equity[-1]),
                  source_hashes=pins, limitations=report['rules'],
                  scope='CONTINUOUS_INTEGER_QQQ_GROSS_DIVIDENDS_NOT_HSBC_NET_TAX')
    target = ROOT / 'tmp/qqq_continuous_paid_reinvestment_20261106.json'
    target.write_text(json.dumps(output, indent=2), encoding='utf8')
    print(json.dumps(dict(path=str(target), metrics=output['metrics'], sessions=output['sessions'])))


if __name__ == '__main__':
    main()
