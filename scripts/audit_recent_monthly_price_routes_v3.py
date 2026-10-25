"""Inventory every saved route independently; date unions never authorize splicing."""
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
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
    eligibility = json.loads(raw(OUT / 'regular_way_eligibility_v1.json'))
    for evidence_path in ('tmp/andrewmvd_inventory_20261025/stocks_download_manifest.json',
                          'tmp/andrewmvd_inventory_20261025/stocks_extraction_audit.json',
                          'tmp/modern_archive_inventory_20261025/ATVI_price_candidate_audit.json',
                          'tmp/candlestick_gap_probe_20261025/ALXN_price_candidate_audit.json'):
        raw(ROOT / evidence_path)
    exclusions = {(r['ticker'],r['decision_cutoff']):r for r in eligibility['records'] if r['status']=='EXCLUDED_TRAINING_RULE'}
    for evidence_path in (
        'tmp/chartexchange_gap_20261025/MXIM_audit.json',
        'tmp/chartexchange_gap_20261025/XLNX_audit.json',
        'tmp/xlnx_cern_gap_20261025/manifest.json',
        'tmp/splk_sgen_bridge_20261025/overlap_audit.json',
        'tmp/zenodo_wba_20261026/independent_wba_price_review.json',
    ):
        path = ROOT / evidence_path
        if path.exists():
            raw(path)
    domain_by_day = {row['decision_cutoff']:row for row in domain['decisions']}
    # Reuse the same saved reference calendar as V2, without loading extra sources.
    reference = json.loads(raw(ROOT / 'tmp/free_history_price_probe_20261025_v1/AAPL.response'))
    sessions = [datetime.fromtimestamp(stamp, timezone.utc).date().isoformat() for stamp in reference['chart']['result'][0]['timestamp']]
    selected = {row['ticker']:row['source'] for row in previous['matrix']}
    candidates, empty_routes = {}, {}
    for ticker, selected_path in selected.items():
        paths = {ROOT / selected_path} if selected_path else set()
        paths.update(path for path in (ROOT / f'tmp/modern_missing_probe_20261025/{ticker}_quiver.csv',
                    ROOT / f'tmp/modern_archive_inventory_20261025/{ticker}.csv',
                    ROOT / f'tmp/andrewmvd_inventory_20261025/{ticker}_stocks.csv',
                    ROOT / f'tmp/candlestick_gap_probe_20261025/{ticker}_price_candidate_2020_2021.csv') if path.exists())
        paths.update(path for path in (
            ROOT / f'tmp/chartexchange_gap_20261025/{ticker}_price_candidate.csv',
            ROOT / f'tmp/xlnx_cern_gap_20261025/{ticker}_archive.csv',
            ROOT / f'tmp/xlnx_cern_gap_20261025/{ticker}_chart.csv',
            ROOT / f'tmp/splk_sgen_bridge_20261025/{ticker}.csv',
            ROOT / f'tmp/zenodo_wba_20261026/{ticker}_stock_data.csv',
        ) if path.exists())
        # Explicit candidates retain fixed source priority; date coverage alone is not admission.
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
                        day = datetime.strptime(row['Date'], '%Y-%m-%d' if row['Date'][4:5]=='-' else '%d-%m-%Y').date().isoformat()
                        quote = {key.lower():row[key] for key in ('Open','High','Low','Close')}
                    else:
                        day, quote = row['date'], row
                    if day in rows:
                        raise ValueError('Duplicate source date:' + str(path) + day)
                    rows[day] = quote
                if path.parent.name == 'modern_archive_inventory_20261025' and not path.name.startswith('ATVI_price_candidate'):
                    suspect = ['2022-12-12']
            valid = {day:quote for day,quote in rows.items() if valid_ohlc(quote) and day not in suspect}
            def positive_fields(quote, fields):
                try:
                    return all(not isinstance(quote.get(key),bool) and math.isfinite(float(quote[key])) and float(quote[key])>0 for key in fields)
                except (ValueError, TypeError, KeyError):
                    return False
            close_dates = {day for day,quote in rows.items() if day not in suspect and positive_fields(quote,('close',))}
            open_close_dates = {day for day,quote in rows.items() if day not in suspect and positive_fields(quote,('open','close'))}
            if not valid and not close_dates:
                empty_routes.setdefault(ticker, []).append(dict(path=path.relative_to(ROOT).as_posix(),
                    reason='NO_FINITE_VALID_OHLC_NOT_A_SUCCESSFUL_PRICE_ROUTE'))
                continue
            routes[path.relative_to(ROOT).as_posix()] = dict(rows=valid, suspect_dates=suspect,
                close_dates=close_dates, open_close_dates=open_close_dates,
                first=min(valid) if valid else None, last=max(valid) if valid else None,
                explicit_priority_reviewed=path.name in ('ATVI_price_candidate_2020_2023.csv','ALXN_price_candidate_2020_2021.csv','MXIM_price_candidate.csv','XLNX_price_candidate.csv'))
        candidates[ticker] = routes
    matrix = []
    for old in previous['matrix']:
        cutoff, ticker = old['decision_cutoff'], old['ticker']
        train = domain_by_day[cutoff]['training_dates']
        execution = [day for day in sessions if day.startswith(old['execution_month'])]
        # These boundaries are action obligations, never fictitious old-stock bars.
        last_trade = {'ALXN':'2021-07-20','MXIM':'2021-08-25','XLNX':'2022-02-11','SGEN':'2023-12-13'}.get(ticker)
        action_dates = [day for day in execution if last_trade and day > last_trade]
        old_security_execution = [day for day in execution if day not in action_dates]
        required = sorted(set(train + execution))
        routes = candidates[ticker]
        route_dates = {name:list(route['rows']) for name,route in routes.items()}
        training_coverage = classify_route_dates(train, route_dates)
        execution_coverage = classify_route_dates(old_security_execution, route_dates)
        qualification = exclusions.get((ticker,cutoff))
        close_coverage = classify_route_dates(train, {name:route['close_dates'] for name,route in routes.items()})
        open_close_coverage = classify_route_dates(old_security_execution, {name:route['open_close_dates'] for name,route in routes.items()})
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
            rejected_empty_sources=empty_routes.get(ticker, []),
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
        matrix[-1].update(training_coverage=training_coverage,
            training_close_coverage=close_coverage,
            training_close_missing=[] if qualification else close_coverage['missing_union_dates'],
            execution_open_close_coverage=open_close_coverage,
            execution_open_close_missing=open_close_coverage['missing_union_dates'],
            execution_full_ohlc_schema_still_required=True,
            training_ready_at_date_level=bool(close_coverage['single_source_complete']) or qualification is not None,
            training_rule_exclusion=qualification,
            execution_old_security_coverage=execution_coverage,
            execution_requires_action=bool(action_dates), action_required_dates=action_dates,
            last_trade_boundary=last_trade,
            action_boundary_evidence=('docs/candlestick_modern_gap_probe_20261025.md + parent supplied ALXN last-trade boundary; conversion terms still require admission' if ticker=='ALXN' else
                'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2021-172' if ticker=='MXIM' else
                'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-23' if ticker=='XLNX' else
                'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2023-721' if ticker=='SGEN' else None),
            real_training_quote_gaps=[] if qualification else training_coverage['missing_union_dates'],
            real_execution_quote_gaps=execution_coverage['missing_union_dates'])
    windows = []
    for cutoff in domain_by_day:
        group = [row for row in matrix if row['decision_cutoff']==cutoff]
        if not group:
            continue
        windows.append(dict(decision_cutoff=cutoff, execution_month=group[0]['execution_month'],
             by_status={status:[row['ticker'] for row in group if row['status']==status] for status in sorted({row['status'] for row in group})},
             source_overlap_disagreements=[row['ticker'] for row in group if row['overlapping_price_disagreement_dates']],
             training_ready_at_date_level=all(row['training_ready_at_date_level'] for row in group),
             training_missing=[row['ticker'] for row in group if not row['training_ready_at_date_level']],
             lawful_short_history_exclusions=[row['ticker'] for row in group if row['training_rule_exclusion']],
             execution_requires_action=[row['ticker'] for row in group if row['execution_requires_action']],
             all_members_single_source_dates_complete=all(row['single_source_complete'] for row in group), compiler_ready=False))
    gap_segments = []
    positions = {day:i for i,day in enumerate(sessions)}
    for ticker in sorted(candidates):
        for kind in ('training','execution'):
            days = sorted({day for row in matrix if row['ticker']==ticker for day in row['real_'+kind+'_quote_gaps']})
            segments = []
            for day in days:
                if not segments or positions[day] != positions[segments[-1][-1]]+1:
                    segments.append([day])
                else:
                    segments[-1].append(day)
            gap_segments.extend(dict(ticker=ticker,kind=kind,start=part[0],end=part[-1],sessions=len(part)) for part in segments)
    field_gap_segments = []
    for ticker in sorted(candidates):
        train_missing = {day for row in matrix if row['ticker']==ticker for day in row['training_close_missing']}
        execution_missing = {day for row in matrix if row['ticker']==ticker for day in row['execution_open_close_missing']}
        for kind, missing_days in [('TRAINING_ONLY_CLOSE_SUFFICIENT',train_missing-execution_missing),('EXECUTION_OPEN_CLOSE_AND_CURRENT_OHLC_SCHEMA_REQUIRED',execution_missing)]:
            parts = []
            for day in sorted(missing_days):
                if not parts or positions[day] != positions[parts[-1][-1]]+1:
                    parts.append([day])
                else:
                    parts[-1].append(day)
            field_gap_segments.extend(dict(ticker=ticker, requirement=kind,start=part[0],end=part[-1],sessions=len(part)) for part in parts)
    return dict(revision='V5_FIELD_REQUIREMENTS_DIAGNOSTIC_NO_SCHEMA_RELAXATION', source_hashes=hashes, windows=windows, matrix=matrix,
                field_gap_segments=field_gap_segments,
                remaining_quote_gap_segments=gap_segments,
                limitations=['Date unions are diagnostics only, never admitted training/execution quotes.',
                             'Price disagreements can be rounding, units or real source errors; no source is selected by performance.',
                             'ATVI, ALXN, MXIM and partial XLNX candidates have explicit priority reviews; other route splicing needs review.',
                             'Training ready here is date-level only, not identity/unit/action admission.',
                             'Known post-last-trade dates require conversion/receivable handling, never manufactured old-stock quotes.'])


if __name__ == '__main__':
    result = audit()
    (OUT / 'monthly_price_routes_v5_fields.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'windows':len(result['windows']), 'security_windows':len(result['matrix']),
                      'training_date_ready':[w['execution_month'] for w in result['windows'] if w['training_ready_at_date_level']],
                      'field_gap_segments':result['field_gap_segments']}))
