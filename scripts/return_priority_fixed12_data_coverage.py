"""Saved-source membership overlay and whole-source numeric coverage only."""
import argparse
import csv
import hashlib
import io
import json
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    pins = {}

    def read(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('Source changed: ' + str(path))
        pins[str(path)] = digest
        return raw

    def csv_source(path):
        manifest = json.loads(read(str(path) + '.manifest.json'))
        records = list(csv.DictReader(io.StringIO(read(path, manifest['content_sha256']).decode('utf-8-sig'))))
        if len(records) != manifest['row_count']:
            raise ValueError('Source row count differs')
        return records

    base = ROOT / 'data/cache/candidate_pools/ndx_history'
    history = csv_source(base / 'qqq_nport_constituents.csv')
    events = csv_source(base / 'exact_events/exact_events.csv')
    gaps = csv_source(base / 'exact_events/unresolved_gaps.csv')
    if len({(r['event_id'], r['action'], r['ticker']) for r in events}) != len(events):
        raise ValueError('Duplicate official action')
    if any(r['event_status'] != 'effective' for r in events):
        raise ValueError('Unresolved event status')
    panel_path = 'tmp/current_ohlc_actual_projection_20261013_v1/panel.json'
    panel = json.loads(read(panel_path, '92361a7321765594a5544ab3cb9128410c8296799d99b3d23090e24a37df9822'))
    calendar = panel['calendar']
    channels = {r['ticker']: dict(zip(calendar, r['values'])) for r in panel['stocks']}
    archive_path = 'data/cache/research/root_price_byte_archive_20260919_v1/archive_manifest.json'
    archive = json.loads(read(archive_path))
    archive_index = {Path(r['archived_path']).name.split('.')[0]: r for r in archive['rows']}
    cached = {}

    def price_sources(ticker):
        if ticker in cached:
            return cached[ticker]
        sources = []
        if ticker in channels:
            sources.append(dict(path=panel_path, basis='CONDITIONAL_PROVIDER_QUOTE_NOT_AUTHENTICATED',
                                rows=channels[ticker]))
        raw_path = ROOT / 'data/cache/candidate_pools/ndx_fundamentals/price_basis_v1/raw' / (ticker + '.csv')
        if raw_path.exists():
            records = csv_source(raw_path)
            sources.append(dict(path=str(raw_path), basis='SINA_DECLARED_NOMINAL_VALUATION_ONLY',
                rows={r['Date']: [r[k] for k in ('Open', 'High', 'Low', 'Close')] for r in records}))
        if ticker in archive_index:
            declaration = archive_index[ticker]
            records = list(csv.DictReader(io.StringIO(read(declaration['archived_path'], declaration['archived_sha256']).decode('utf-8-sig'))))
            if len({r['Date'] for r in records}) != len(records):
                raise ValueError('Duplicate archived date')
            sources.append(dict(path=declaration['archived_path'], basis='ARCHIVED_PRICE_UNIT_UNAUTHENTICATED',
                archival_role=declaration['archival_role'],
                rows={r['Date']: [r[k] for k in ('Open', 'High', 'Low', 'Close')] for r in records}))
        cached[ticker] = sources
        return sources

    def missing(source, days, ohlc):
        result = []
        for day in days:
            try:
                row = source['rows'][day]
                values = [Fraction(str(row[i])) for i in (range(4) if ohlc else [3])]
                good = all(v > 0 for v in values)
                if ohlc:
                    op, hi, lo, cl = values
                    good = good and lo <= min(op, cl) <= max(op, cl) <= hi
            except (KeyError, IndexError, ValueError, TypeError, ZeroDivisionError):
                good = False
            if not good:
                result.append(day)
        return result

    cutoffs = [max(d for d in calendar if d.startswith(month)) for month in
               [f'2024-{m:02d}' for m in range(7, 13)] + [f'2025-{m:02d}' for m in range(1, 7)]]
    output = []
    for cutoff in cutoffs:
        available = max(r['available_date'] for r in history if r['available_date'] <= cutoff)
        latest_snapshot = [r for r in history if r['available_date'] == available]
        # Anchor to the already reconciled101-member report, retaining later
        # NPORT holdings as independent discrepancies (e.g. distributed GRAL).
        snapshot = [r for r in history if r['report_date'] == '2024-03-31']
        if len(snapshot) != 101 or any(r['available_date'] > cutoff for r in snapshot):
            raise ValueError('Reviewed public baseline unavailable')
        report = snapshot[0]['report_date']
        members = {r['ticker']: dict(baseline=r) for r in snapshot}
        actions = sorted([r for r in events if report < r['effective_date'] <= cutoff
            and r['announcement_date'] <= cutoff and r['source_available_date'] <= cutoff
            and r['action'] in ('add', 'remove')],
            key=lambda r: (r['effective_date'], r['event_id'], r['action'], r['ticker']))
        for action in actions:
            if not all(action[k] == 'True' for k in ('source_verified', 'source_manifest_verified', 'future_data_guard')):
                raise ValueError('Official action evidence unresolved')
            read(base / 'exact_events' / action['raw_path'], action['content_sha256'])
            ticker = action['ticker']
            if action['action'] == 'add':
                if ticker in members:
                    raise ValueError('Duplicate addition: ' + ticker)
                members[ticker] = dict(official_addition=action)
            else:
                if ticker not in members:
                    raise ValueError('Missing removal: ' + ticker)
                del members[ticker]
        index = calendar.index(cutoff)
        training, future = calendar[index-252:index+1], calendar[index+1:index+22]
        assert len(training) == 253 and len(future) == 21
        rows = []
        for ticker, evidence in sorted(members.items()):
            choices = []
            for source in price_sources(ticker):
                choices.append(dict(**{k:v for k,v in source.items() if k != 'rows'},
                    missing_training_close=missing(source, training, False),
                    missing_outcome_ohlc=missing(source, future, True)))
            rows.append(dict(ticker=ticker, membership_evidence=evidence, source_candidates=choices,
                training_numeric_available=any(not c['missing_training_close'] for c in choices),
                outcome_numeric_available=any(not c['missing_outcome_ohlc'] for c in choices),
                one_source_both_available=any(not c['missing_training_close'] and not c['missing_outcome_ohlc'] for c in choices)))
        fresh_members = {r['ticker'] for r in latest_snapshot}
        fresh_report = latest_snapshot[0]['report_date']
        for action in actions:
            if action['effective_date'] > fresh_report:
                if action['action'] == 'add':
                    fresh_members.add(action['ticker'])
                else:
                    fresh_members.discard(action['ticker'])
        uncertain = []
        for ticker in sorted(fresh_members-set(members)):
            choices = [dict(**{k:v for k,v in source.items() if k != 'rows'},
                missing_training_close=missing(source, training, False),
                missing_outcome_ohlc=missing(source, future, True)) for source in price_sources(ticker)]
            uncertain.append(dict(ticker=ticker, membership_status='NPORT_EXTRA_INDEX_MEMBERSHIP_UNRESOLVED_NOT_DROPPED',
                                  source_candidates=choices))
        output.append(dict(decision_cutoff=cutoff, proxy_report=report, proxy_available=snapshot[0]['available_date'],
            membership_mode='FIXED_RECONCILED_MARCH2024_BASELINE_PLUS_SAVED_OFFICIAL_EVENTS_CONDITIONAL',
            latest_public_report=fresh_report, latest_public_available=available,
            latest_public_overlay_count=len(fresh_members),
            latest_public_overlay_extra=sorted(fresh_members-set(members)),
            latest_public_overlay_missing=sorted(set(members)-fresh_members),
            unresolved_additional_candidates=uncertain,
            member_denominator=len(members), members=sorted(members), applied_actions=actions,
            training_dates=training, outcome_dates=future, candidates=rows,
            missing_training=[r['ticker'] for r in rows if not r['training_numeric_available']],
            missing_outcome=[r['ticker'] for r in rows if not r['outcome_numeric_available']],
            no_single_source_both=[r['ticker'] for r in rows if not r['one_source_both_available']]))
    read(Path(__file__))
    return dict(status='PREPARED_OFFICIAL_EVENT_OVERLAY_AND_NUMERIC_COVERAGE_ONLY', windows=output,
        source_hashes=pins, saved_registry_gaps=gaps, exact_registry_completeness_certified=False,
        point_in_time_identity_certified=False, prices_spliced=False, members_dropped_for_price_gaps=False,
        adjusted_training_returns_generated=False, strategy_calls=0, network_calls=0,
        next_step='Review each complete whole-source candidate for units/identity/events before preparing fixed quantity-vs-top1-vsQQQ inputs; missing future prices never select the member universe.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Create-only output exists')
    result = prepare()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps([dict(cutoff=w['decision_cutoff'], missing_training=w['missing_training'],
                          missing_outcome=w['missing_outcome']) for w in result['windows']]))
