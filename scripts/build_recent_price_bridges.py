"""Build fixed-source research prices, preserving discrepancies and provenance.

This does not certify corporate actions, identity, or strategy performance.
"""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_recent_monthly_price_coverage import valid_ohlc

OUTPUT = ROOT / 'tmp/recent_price_bridges_20261026'
FIELDS = ('open', 'high', 'low', 'close')


def read_prices(path):
    result = {}
    for original in csv.DictReader(path.read_text(encoding='utf-8-sig').splitlines()):
        row = {key.lower(): value for key, value in original.items()}
        day = row['date']
        if day[4:5] != '-':
            day = datetime.strptime(day, '%d-%m-%Y').date().isoformat()
        # The frozen study starts with 2020 prewarm. Older unused bars do not
        # enter either the candidate or its overlap validation.
        if day < '2020-01-02':
            continue
        if day in result:
            raise ValueError(f'Duplicate date: {path} {day}')
        quote = {field: float(row[field]) for field in FIELDS}
        if not valid_ohlc(quote):
            raise ValueError(f'Invalid OHLC: {path} {day}')
        result[day] = quote
    return result


def build():
    OUTPUT.mkdir(exist_ok=True)
    reference_path = ROOT / 'tmp/free_history_price_probe_20261025_v1/AAPL.response'
    stamps = json.loads(reference_path.read_bytes())['chart']['result'][0]['timestamp']
    calendar = {datetime.fromtimestamp(stamp, timezone.utc).date().isoformat() for stamp in stamps}
    summaries = []
    for ticker, end in [('SGEN', '2023-12-13'), ('SPLK', '2023-12-29'),
                        ('CERN', '2022-06-07'), ('XLNX', '2022-02-11')]:
        paths = [ROOT / f'tmp/modern_archive_inventory_20261025/{ticker}.csv',
                 ROOT / f'tmp/splk_sgen_bridge_20261025/{ticker}.csv',
                 ROOT / f'tmp/modern_missing_probe_20261025/{ticker}_quiver.csv']
        if ticker == 'CERN':
            paths[:2] = [ROOT / 'tmp/abr_gap_probe_20261026/Stock_prediction_approach_modified_CERN.csv',
                         ROOT / 'tmp/abr_gap_probe_20261026/CERN_chart.csv']
        elif ticker == 'XLNX':
            paths[:2] = [ROOT / 'tmp/xlnx_tsaustin_20261026/XLNX.csv',
                         ROOT / 'tmp/chartexchange_gap_20261025/XLNX_chart.csv']
        sources = [read_prices(path) for path in paths]
        # Whole visible windows determine priority before observing returns.
        cutovers = [min(sources[1]), min(sources[2])]
        if not cutovers[0] < cutovers[1]:
            raise ValueError('Unexpected source chronology')
        selected = {}
        for index, source in enumerate(sources):
            lower = '2020-01-02' if index == 0 else cutovers[index - 1]
            upper = cutovers[index] if index < 2 else '9999'
            for day, quote in source.items():
                if lower <= day < upper and '2020-01-02' <= day <= end:
                    selected[day] = dict(date=day, **quote,
                                        source=paths[index].relative_to(ROOT).as_posix())
        expected = {day for day in calendar if '2020-01-02' <= day <= end}
        if expected != set(selected):
            raise ValueError(f'{ticker} calendar mismatch: missing={sorted(expected-set(selected))}, extra={sorted(set(selected)-expected)}')
        if selected.get('2022-12-12', {}).get('source') == paths[0].relative_to(ROOT).as_posix():
            raise ValueError('Suspect archive final bar selected')
        disagreements = []
        for first, second in [(0, 1), (1, 2)]:
            shared = sorted(set(sources[first]) & set(sources[second]))
            differences = [dict(date=day, field=field, left=sources[first][day][field],
                                right=sources[second][day][field])
                           for day in shared for field in FIELDS
                           if abs(sources[first][day][field]-sources[second][day][field]) > 0.011]
            disagreements.append(dict(left=str(paths[first].relative_to(ROOT)),
                                      right=str(paths[second].relative_to(ROOT)),
                                      overlap_sessions=len(shared), differences=differences))
        target = OUTPUT / f'{ticker}_price_candidate.csv'
        with target.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=['date', *FIELDS, 'source'])
            writer.writeheader()
            writer.writerows(selected[day] for day in sorted(selected))
        audit = dict(ticker=ticker, rows=len(selected), first=min(selected), last=max(selected),
                     source_priority='Quiver entire visible window; ChartExchange before Quiver; archive before ChartExchange',
                     cutovers=cutovers, overlaps=disagreements,
                     reference_calendar='Saved AAPL response, not independent exchange calendar',
                     missing_dates=[], extra_dates=[], full_strategy_admission=False,
                     source_hashes={path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                    for path in [*paths, reference_path, target]})
        (OUTPUT / f'{ticker}_audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
        summaries.append({key: audit[key] for key in ('ticker', 'rows', 'first', 'last', 'cutovers')})
    print(json.dumps(summaries))


if __name__ == '__main__':
    build()
