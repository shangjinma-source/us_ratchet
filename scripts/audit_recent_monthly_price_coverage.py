"""Read saved price routes against all monthly members, without running strategy."""
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tmp/qqq_20201231_anchor_20261025'
ALIASES = {'FB': 'META', 'PCLN': 'BKNG', 'CTRP': 'TCOM', 'NLOK': 'GEN', 'WLTW': 'WTW'}


def valid_ohlc(row):
    try:
        o, h, l, c = [float(row[name]) for name in ('open', 'high', 'low', 'close')]
        return all(math.isfinite(v) and v > 0 for v in (o, h, l, c)) and l <= min(o, c) <= max(o, c) <= h
    except (ValueError, TypeError, KeyError):
        return False


def audit():
    hashes = {}
    def read(path):
        raw = path.read_bytes()
        hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(raw).hexdigest()
        return raw
    domain = json.loads(read(OUT / 'monthly_member_domain_v1.json'))
    routes = {}
    all_tickers = set().union(*(set(row['full_members']) for row in domain['decisions']))
    for ticker in sorted(all_tickers):
        symbol = ALIASES.get(ticker, ticker)
        route = {'query_symbol': symbol, 'rows': {}, 'source': None, 'unit_status': 'NO_PRICE_ROUTE'}
        if ticker == 'ATVI':
            path = ROOT / 'tmp/modern_archive_inventory_20261025/ATVI_price_candidate_2020_2023.csv'
            if path.exists():
                rows = list(csv.DictReader(read(path).decode().splitlines()))
                route.update(rows={row['date']:row for row in rows}, source=path.relative_to(ROOT).as_posix(),
                             unit_status='ATVI_SEC_ANCHORED_PRICE_CANDIDATE_ACTIONS_SEPARATE')
        else:
            for folder in ('free_history_alias_probe_20261025_v1', 'free_history_universe_probe_20261025_v1', 'free_history_price_probe_20261025_v1'):
                path = ROOT / f'tmp/{folder}/{symbol}.response'
                if not path.exists():
                    continue
                payload = json.loads(read(path))
                results = payload.get('chart', {}).get('result')
                if not results:
                    continue
                result = results[0]
                quotes = result['indicators']['quote'][0]
                rows = {}
                for index, stamp in enumerate(result['timestamp']):
                    day = datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
                    if day in rows:
                        raise ValueError('Duplicate quote day:' + ticker + day)
                    rows[day] = {key:quotes.get(key, [None] * len(result['timestamp']))[index] for key in ('open','high','low','close')}
                route.update(rows=rows, source=path.relative_to(ROOT).as_posix(), unit_status='YAHOO_PROVIDER_OHLC_NOMINAL_UNITS_NOT_ADMITTED')
                break
        if not route['source'] and ticker in ('EA', 'SGEN', 'SPLK', 'WBA'):
            path = ROOT / f'tmp/modern_archive_inventory_20261025/{ticker}.csv'
            if path.exists():
                rows = {}
                for row in csv.DictReader(read(path).decode('utf-8-sig').splitlines()):
                    day = datetime.strptime(row['Date'], '%d-%m-%Y').date().isoformat()
                    if day in rows:
                        raise ValueError('Duplicate archive date:' + ticker + day)
                    rows[day] = {key.lower():row[key] for key in ('Open','High','Low','Close')}
                route.update(rows=rows, source=path.relative_to(ROOT).as_posix(),
                             unit_status='ARCHIVE_PROVIDER_OHLC_UNITS_PENDING_PARTIAL_WINDOW',
                             suspect_dates=['2022-12-12'], suspect_reason='Archive terminal session may be intraday; retain but not count as complete daily bar.')
        route['valid_dates'] = {day for day, row in route['rows'].items() if valid_ohlc(row)}
        route['valid_dates'] -= set(route.get('suspect_dates', []))
        routes[ticker] = route
    sessions = sorted(routes['AAPL']['rows'])
    matrix, windows = [], []
    for decision in domain['decisions']:
        cutoff = decision['decision_cutoff']
        if cutoff >= '2023-12-01':
            continue
        year, month = int(cutoff[:4]), int(cutoff[5:7])
        execution_month = f'{year + (month == 12)}-{month % 12 + 1:02d}'
        execution_dates = [day for day in sessions if day.startswith(execution_month)]
        if not execution_dates:
            raise ValueError('Missing execution calendar:' + execution_month)
        training = decision['training_dates']
        records = []
        for ticker in decision['full_members']:
            route = routes[ticker]
            valid = route['valid_dates']
            first = min(valid) if valid else None
            missing_training = [day for day in training if day not in valid]
            missing_execution = [day for day in execution_dates if day not in valid]
            pre_first = [day for day in missing_training if first and day < first]
            internal = [day for day in missing_training if first and day >= first]
            status = ('NO_SAVED_PRICE_ROUTE' if not route['source'] else
                      'COMPLETE_PROVIDER_DATES_UNITS_PENDING' if not missing_training and not missing_execution else
                      'LEFT_EDGE_SHORT_HISTORY_IPO_NOT_YET_PROVEN' if pre_first and not internal and not missing_execution else
                      'MISSING_OR_INVALID_DATES')
            row = dict(decision_cutoff=cutoff, execution_month=execution_month, ticker=ticker,
                query_symbol=route['query_symbol'], source=route['source'], status=status, unit_status=route['unit_status'],
                first_valid_date=first, last_valid_date=max(valid) if valid else None,
                training_required=len(training), training_available=len(training)-len(missing_training),
                execution_required=len(execution_dates), execution_available=len(execution_dates)-len(missing_execution),
                missing_training_dates=missing_training, missing_execution_dates=missing_execution,
                suspect_source_dates=route.get('suspect_dates', []),
                before_first_quote_dates=pre_first, internal_or_trailing_training_missing=internal,
                insufficient_listing_history_proven=False, exclusion_authorized=False)
            records.append(row)
        matrix.extend(records)
        windows.append(dict(decision_cutoff=cutoff, execution_month=execution_month, members=len(records),
            complete_provider_date_members=[r['ticker'] for r in records if not r['missing_training_dates'] and not r['missing_execution_dates']],
            no_saved_route=[r['ticker'] for r in records if r['status']=='NO_SAVED_PRICE_ROUTE'],
            left_edge_history_to_verify=[r['ticker'] for r in records if r['status']=='LEFT_EDGE_SHORT_HISTORY_IPO_NOT_YET_PROVEN'],
            missing_or_invalid=[r['ticker'] for r in records if r['status']=='MISSING_OR_INVALID_DATES'],
            full_domain_dates_complete=all(not r['missing_training_dates'] and not r['missing_execution_dates'] for r in records),
            compiler_ready=False, compiler_blockers=['MEMBER_PRICE_GAPS_OR_UNPROVEN_LISTING_EXCLUSIONS','PRICE_UNIT_AND_IDENTITY_ADMISSION_PENDING']))
    return dict(status='ACTUAL_SAVED_PRICE_COVERAGE_NO_ECONOMIC_RUN', source_hashes=hashes, windows=windows, matrix=matrix,
        limitations=['Observed reference calendar, not official calendar certification.',
          'OHLC means saved provider fields, not certified as-traded nominal units.',
          'Each target member is checked over its full next-month execution window, even after index removal.',
          'Pre-first-quote gaps are not automatically IPO dates or permitted exclusions.',
          'Corporate-action conversions and previously carried holdings outside this monthly member domain require separate execution checks.'])


if __name__ == '__main__':
    result = audit()
    result['revision'] = 'V2_ADDS_FOUR_LOCAL_ARCHIVES_V1_RETAINED'
    (OUT / 'monthly_price_coverage_v2.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    with (OUT / 'monthly_price_coverage_summary_v2.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        fields = ['decision_cutoff','execution_month','members','complete_provider_date_members','no_saved_route','left_edge_history_to_verify','missing_or_invalid','full_domain_dates_complete','compiler_ready']
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in result['windows']:
            writer.writerow({key:(' '.join(value) if isinstance(value, list) else value) for key,value in row.items() if key in fields})
    print(json.dumps({'windows':len(result['windows']), 'security_windows':len(result['matrix']),
                      'date_complete_windows':[w['execution_month'] for w in result['windows'] if w['full_domain_dates_complete']],
                      'no_route':sorted(set().union(*(set(w['no_saved_route']) for w in result['windows'])))}))
