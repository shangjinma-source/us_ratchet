"""Research-only holdings reference plus verified, known Nasdaq changes.

This cannot certify complete index membership. Later fund reports are never
inputs to the reconstructed reference, only a separately labelled comparison.
"""
import csv
import json
from hashlib import sha256
from pathlib import Path

from bs4 import BeautifulSoup
from scripts.match_qqq_20230930_security_titles import match


SOURCES = {
    'initial': 'd4298ab86ce6323a19b2c69a07e6d0945ee4e2296697172d6c37d95c2bc55e21',
    'update': '544f16aa57f0cb786fc8a631b88904a595e232cd1cecfb84bcb43f29eb6df0fd',
}
ADDED = {'CDW', 'CCEP', 'DASH', 'MDB', 'ROP', 'SPLK', 'TTWO'}
REMOVED = {'ALGN', 'EBAY', 'ENPH', 'JD', 'LCID', 'ZM', 'SGEN'}


def reconstruct(root):
    root = Path(root)
    anchor = match(root)
    asof = '2023-12-29'
    if anchor['conservative_available_date'] > asof:
        raise ValueError('ANCHOR_NOT_YET_AVAILABLE')
    base = root / 'data/cache/candidate_pools/ndx_history/exact_events'
    raw = (base / 'exact_events.csv').read_bytes()
    manifest = json.loads((base / 'exact_events.csv.manifest.json').read_bytes())
    if sha256(raw).hexdigest() != manifest['content_sha256']:
        raise ValueError('EVENT_REGISTRY_CHANGED')
    registry = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    if len(registry) != manifest['row_count']:
        raise ValueError('EVENT_ROW_COUNT_CHANGED')
    events = [row for row in registry if row['event_status'] == 'effective'
              and anchor['report_date'] < row['effective_date'] <= asof]
    if len(events) != 14 or {row['event_id'] for row in events} != {
            'ndx_annual_reconstitution_2023_update'}:
        raise ValueError('UNREVIEWED_INTERVAL_EVENTS')
    evidence = []
    texts = {}
    for kind, expected in SOURCES.items():
        path = base / f'raw_nasdaq/ndx_annual_reconstitution_2023_{kind}.html'
        source = path.read_bytes()
        if sha256(source).hexdigest() != expected:
            raise ValueError('OFFICIAL_SOURCE_CHANGED')
        text = BeautifulSoup(source, 'html.parser').get_text(' ', strip=True)
        if 'December 18, 2023' not in text:
            raise ValueError('EFFECTIVE_DATE_MISSING')
        texts[kind] = text
        evidence.append(dict(path=path.relative_to(root).as_posix(), sha256=expected))
    if 'will remain the same' not in texts['update']:
        raise ValueError('INITIAL_ACTION_INHERITANCE_UNCONFIRMED')
    actions = {action: {row['ticker'] for row in events if row['action'] == action}
               for action in ('add', 'remove')}
    if actions != {'add': ADDED, 'remove': REMOVED}:
        raise ValueError('UNREVIEWED_ACTIONS')
    for event in events:
        expected_source = ('update' if event['ticker'] in {'TTWO', 'SGEN'} else 'initial')
        if f"Nasdaq: {event['ticker']}" not in texts[expected_source]:
            raise ValueError('TICKER_ABSENT_FROM_ORIGINAL_ANNOUNCEMENT')
        if not (event['announcement_date'] <= event['source_available_date']
                <= event['effective_date'] <= asof):
            raise ValueError('EVENT_NOT_AVAILABLE')
        if event['content_sha256'] != SOURCES['update']:
            raise ValueError('EVENT_SOURCE_BINDING_CHANGED')
    current = {row['local_registry_ticker'] for row in anchor['rows']
               if 'local_registry_ticker' in row}
    if not REMOVED <= current or ADDED & current:
        raise ValueError('EVENT_INCONSISTENT_WITH_ANCHOR')
    current = (current - REMOVED) | ADDED
    unresolved = [row for row in anchor['rows'] if 'local_registry_ticker' not in row]
    # Do not use the later report to fill the unresolved identity or membership.
    nport_path = root / 'data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv'
    nport_raw = nport_path.read_bytes()
    if sha256(nport_raw).hexdigest() != anchor['registry_sha256']:
        raise ValueError('NPORT_REGISTRY_CHANGED')
    later = [row for row in csv.DictReader(nport_raw.decode('utf-8-sig').splitlines())
             if row['report_date'] == '2023-12-31']
    later_tickers = {row['ticker'] for row in later}
    return dict(schema='QQQ_HOLDINGS_EVENT_REFERENCE_V1', asof=asof,
                anchor=anchor, event_registry_sha256=sha256(raw).hexdigest(),
                official_sources=evidence, applied_events=events,
                resolved_tickers=sorted(current), unresolved_securities=unresolved,
                security_count_including_unresolved=len(current)+len(unresolved),
                later_report_comparison=dict(report_date='2023-12-31',
                    available_dates=sorted({row['available_date'] for row in later}),
                    count=len(later), only_in_reference=sorted(current-later_tickers),
                    only_in_later_report=sorted(later_tickers-current),
                    used_for_reconstruction=False),
                index_membership_certified=False, interval_event_coverage_certified=False,
                production_pool_changed=False, eligible_for_strategy_backtest=False)


if __name__ == '__main__':
    print(json.dumps(reconstruct(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))
