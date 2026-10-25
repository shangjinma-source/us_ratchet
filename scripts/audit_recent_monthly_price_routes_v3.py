"""Inventory every saved route independently; date unions never authorize splicing."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_recent_monthly_price_coverage import valid_ohlc

OUT = ROOT / 'tmp/qqq_20201231_anchor_20261025'


def classify_route_dates(required, routes):
    """Pure date coverage, intentionally separate from price admission."""
    required = set(required)
    complete = [name for name, dates in routes.items() if required <= set(dates)]
    union = set().union(*(set(dates) for dates in routes.values())) if routes else set()
    if complete:
        status = 'SINGLE_SOURCE_DATES_COMPLETE'
    elif required <= union:
        status = 'UNION_COMPLETE_REQUIRES_EXPLICIT_STITCH_REVIEW'
    elif not required & union:
        status = 'NO_DATES_IN_REQUESTED_WINDOW'
    else:
        status = 'PARTIAL_SOURCES_WITH_REMAINING_GAPS'
    return dict(status=status, single_source_complete=complete,
                union_available=len(required & union), missing_union_dates=sorted(required-union),
                union_admitted=False, implicit_splicing_permitted=False)


def audit():
    hashes = {}
    def raw(path):
        value = path.read_bytes()
        hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(value).hexdigest()
        return value
    previous = json.loads(raw(OUT / 'monthly_price_coverage_v2.json'))
    domain = json.loads(raw(OUT / 'monthly_member_domain_v1.json'))
    domain_by_day = {row['decision_cutoff']:row for row in domain['decisions']}
    # Reuse the same saved reference calendar as V2, without loading extra sources.
    reference = json.loads(raw(ROOT / 'tmp/free_history_price_probe_20261025_v1/AAPL.response'))
    sessions = [datetime.fromtimestamp(stamp, timezone.utc).date().isoformat() for stamp in reference['chart']['result'][0]['timestamp']]
    selected = {row['ticker']:row['source'] for row in previous['matrix']}
    candidates = {}
    for ticker, selected_path in selected.items():
        paths = {ROOT / selected_path} if selected_path else set()
        paths.update(path for path in (ROOT / f'tmp/modern_missing_probe_20261025/{ticker}_quiver.csv',
                    ROOT / f'tmp/modern_archive_inventory_20261025/{ticker}.csv') if path.exists())
        # ATVI has the only previously reviewed explicit multi-source priority.
        routes = {}
        for path in sorted(paths):
            content = raw(path)
            suspect = []
            if path.suffix == '.response':
                result = json.loads(content)['chart']['result'][0]
                quote = result['indicators']['quote'][0]
                rows = {datetime.fromtimestamp(stamp, timezone.utc).date().isoformat():
                        {key:quote[key][i] for key in ('open','high','low','close')}
                        for i,stamp in enumerate(result['timestamp'])}
            else:
                rows = {}
                for row in csv.DictReader(content.decode('utf-8-sig').splitlines()):
                    if 'Date' in row:
                        day = datetime.strptime(row['Date'], '%d-%m-%Y').date().isoformat()
                        quote = {key.lower():row[key] for key in ('Open','High','Low','Close')}
                    else:
                        day, quote = row['date'], row
                    if day in rows:
                        raise ValueError('Duplicate source date:' + str(path) + day)
                    rows[day] = quote
                if path.parent.name == 'modern_archive_inventory_20261025' and not path.name.startswith('ATVI_price_candidate'):
                    suspect = ['2022-12-12']
            valid = {day:quote for day,quote in rows.items() if valid_ohlc(quote) and day not in suspect}
            routes[path.relative_to(ROOT).as_posix()] = dict(rows=valid, suspect_dates=suspect,
                first=min(valid) if valid else None, last=max(valid) if valid else None,
                explicit_priority_reviewed=path.name=='ATVI_price_candidate_2020_2023.csv')
        candidates[ticker] = routes
    matrix = []
    for old in previous['matrix']:
        cutoff, ticker = old['decision_cutoff'], old['ticker']
        train = domain_by_day[cutoff]['training_dates']
        execution = [day for day in sessions if day.startswith(old['execution_month'])]
        required = sorted(set(train + execution))
        routes = candidates[ticker]
        coverage = classify_route_dates(required, {name:list(route['rows']) for name,route in routes.items()})
        union = set().union(*(set(route['rows']) for route in routes.values())) if routes else set()
        earliest = min(union) if union else None
        left = [day for day in coverage['missing_union_dates'] if earliest and day < earliest]
        if routes and union & set(required) and left == coverage['missing_union_dates'] and left:
            coverage['status'] = 'LEFT_EDGE_HISTORY_QUALIFICATION_UNPROVEN'
        conflicts = []
        for day in required:
            quotes = [route['rows'][day] for route in routes.values() if day in route['rows']]
            if len(quotes)>1 and any(abs(float(q[key])-float(quotes[0][key])) > max(0.0001, abs(float(quotes[0][key]))*0.000001)
                                    for q in quotes[1:] for key in ('open','high','low','close')):
                conflicts.append(day)
        matrix.append(dict(decision_cutoff=cutoff, execution_month=old['execution_month'], ticker=ticker,
            **coverage, source_count=len(routes), no_saved_source=not routes,
            sources=[dict(path=name, first=route['first'], last=route['last'],
                      outside_requested_period=not bool(set(route['rows']) & set(required)),
                      training_available=sum(day in route['rows'] for day in train),
                      execution_available=sum(day in route['rows'] for day in execution),
                      suspect_dates=route['suspect_dates'], explicit_priority_reviewed=route['explicit_priority_reviewed'])
                     for name,route in routes.items()],
            missing_training_union=[day for day in train if day not in union],
            missing_execution_union=[day for day in execution if day not in union],
            overlapping_price_disagreement_dates=conflicts, qualification_exclusion_authorized=False,
            units_identity_actions_admitted=False))
    windows = []
    for cutoff in domain_by_day:
        group = [row for row in matrix if row['decision_cutoff']==cutoff]
        if not group:
            continue
        windows.append(dict(decision_cutoff=cutoff, execution_month=group[0]['execution_month'],
             by_status={status:[row['ticker'] for row in group if row['status']==status] for status in sorted({row['status'] for row in group})},
             source_overlap_disagreements=[row['ticker'] for row in group if row['overlapping_price_disagreement_dates']],
             all_members_single_source_dates_complete=all(row['single_source_complete'] for row in group), compiler_ready=False))
    return dict(revision='V3_ALL_SAVED_ROUTES_NO_IMPLICIT_SPLICE', source_hashes=hashes, windows=windows, matrix=matrix,
                limitations=['Date unions are diagnostics only, never admitted training/execution quotes.',
                             'Price disagreements can be rounding, units or real source errors; no source is selected by performance.',
                             'Only ATVI price candidate has an existing explicit priority review; other route splicing needs review.'])


if __name__ == '__main__':
    result = audit()
    (OUT / 'monthly_price_routes_v3.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'windows':len(result['windows']), 'security_windows':len(result['matrix']),
                      'truly_no_saved_source':sorted({row['ticker'] for row in result['matrix'] if row['no_saved_source']})}))
