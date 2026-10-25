"""Offline historical input coverage diagnostic; never grants admission."""
import argparse
import hashlib
import json
from datetime import date
from fractions import Fraction
from pathlib import Path


def audit(manifest, root):
    """Schema: sessions, decisions, memberships, identities, prices, sources.

    Intervals use inclusive start/end and ticker; identities also security_id.
    prices maps SID to {basis, source, rows: {ISO date: OHLC}}.
    sources maps relative file paths to SHA256. Dates are explicit exchange sessions.
    Authenticity, corporate actions and interval completeness require separate review.
    """
    issues = []

    def issue(code, **context):
        issues.append(dict(code=code, **context))

    days = manifest['sessions']
    if not days or not manifest['decisions'] or not manifest['memberships']:
        issue('EMPTY_RESEARCH_SCOPE')
    try:
        valid = days == sorted(set(days)) and all(date.fromisoformat(d).isoformat() == d for d in days)
    except (ValueError, TypeError):
        valid = False
    if not valid:
        return dict(status='NOT_ADMITTED', issues=[dict(code='INVALID_CALENDAR')])
    pins = manifest['sources']
    for name, expected in pins.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()):
            issue('SOURCE_OUTSIDE_ROOT', source=name)
        elif not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            issue('SOURCE_MISSING_OR_CHANGED', source=name)
    decisions = manifest['decisions']
    if len(decisions) != len(set(decisions)) or decisions != sorted(decisions):
        issue('INVALID_DECISION_ORDER')
    for collection in ('memberships', 'identities'):
        for row in manifest[collection]:
            try:
                valid_interval = date.fromisoformat(row['start']) <= date.fromisoformat(row['end'])
            except ValueError:
                valid_interval = False
            if not valid_interval:
                issue('INVALID_INTERVAL', collection=collection, ticker=row['ticker'])
            if row.get('source') not in pins:
                issue('UNPINNED_INTERVAL', collection=collection, ticker=row['ticker'])
    counts = []
    for decision in decisions:
        if decision not in days or days.index(decision) < 252:
            issue('INSUFFICIENT_EXPLICIT_WARMUP', date=decision)
            continue
        training = days[days.index(decision)-252:days.index(decision)+1]
        members = [m for m in manifest['memberships'] if m['start'] <= decision <= m['end']]
        tickers = [m['ticker'] for m in members]
        counts.append(dict(date=decision, member_rows=len(members), distinct_tickers=len(set(tickers))))
        if not members:
            issue('EMPTY_MEMBER_DOMAIN', date=decision)
        if len(tickers) != len(set(tickers)):
            issue('OVERLAPPING_MEMBERSHIP', date=decision)
        seen = set()
        for ticker in sorted(set(tickers)):
            identities = [i for i in manifest['identities'] if i['ticker'] == ticker and i['start'] <= decision <= i['end']]
            if len(identities) != 1:
                issue('MISSING_OR_OVERLAPPING_IDENTITY', date=decision, ticker=ticker)
                continue
            sid = identities[0]['security_id']
            if sid in seen:
                issue('DUPLICATE_MEMBER_SECURITY', date=decision, security_id=sid)
            seen.add(sid)
            prices = manifest['prices'].get(sid)
            if prices is None:
                issue('MISSING_PRICE_SECURITY', date=decision, ticker=ticker, security_id=sid)
                continue
            if prices.get('source') not in pins:
                issue('UNPINNED_PRICE_SOURCE', security_id=sid)
            if prices.get('basis') != 'HISTORICAL_NOMINAL':
                issue('UNREVIEWED_PRICE_BASIS', security_id=sid)
            missing = []
            for day in training:
                row = prices['rows'].get(day, {})
                try:
                    values = [Fraction(str(row[k])) for k in ('open', 'high', 'low', 'close')]
                    opening, high, low, close = values
                    valid_bar = all(v > 0 for v in values) and low <= min(opening, close) <= max(opening, close) <= high
                except (ValueError, ZeroDivisionError, KeyError):
                    valid_bar = False
                if not valid_bar:
                    missing.append(day)
            if missing:
                issue('MISSING_OR_INVALID_TRAINING_BARS', date=decision, security_id=sid, dates=missing)
    return dict(status='NOT_ADMITTED', structural_coverage_pass=not issues,
                issues=issues, member_counts=counts, economic_searches=0,
                limitations=['Explicit calendar and membership completeness not authenticated',
                             'Source hashes do not authenticate derivation of parsed rows from those sources',
                             'No corporate action, execution holdings or dividend certification',
                             'No missing member is excluded; new-listing exceptions require separate evidence'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = audit(json.loads(args.manifest.read_bytes()), args.root)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
