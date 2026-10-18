"""Independent issuer endpoint crosscheck; not an exact security membership seed."""
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PEER = ROOT / 'data/cache/research/adobe_historical_peer_mirror_20260919_v1/issuer_table_facts.json'
PEER_SHA = '666c87f3b643076bdcb917de11dfa9f9d75ceabe3f5f05f3c354f623d615bbbf'
EVENTS = ROOT / 'data/cache/candidate_pools/ndx_history/exact_events'
MANIFEST_SHA = '57e3ff36401994b2d67dfae72a82aa6ca8a0ae4f90444190b793924cc931588d'
OUTPUT = ROOT / 'data/cache/research/adobe_event_endpoint_crosscheck_20260919_v1/report.json'
SOURCE = Path(__file__).resolve()
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def crosscheck(before, after, rows):
    """Compare ticker sets only, with no issuer/security/alias inference."""
    for endpoint in (before, after):
        if len(endpoint) != 100 or len(set(endpoint)) != 100:
            raise ValueError('Two complete distinct 100-company endpoints required')
    current = set(before)
    trace = []
    seen = set()
    selected = [r for r in rows if '2023-01-01' < r['effective_date'] < '2024-01-01']
    for day in sorted({r['effective_date'] for r in selected}):
        daily = [r for r in selected if r['effective_date'] == day]
        additions, removals = set(), set()
        for row in daily:
            key = (row['event_id'], row['action'], row['ticker'])
            if key in seen or row['event_status'] != 'effective':
                raise ValueError('Duplicate or ineffective event')
            seen.add(key)
            if row['action'] == 'weight_only':
                if row['ticker']:
                    raise ValueError('Weight-only event unexpectedly changes a ticker')
                continue
            if row['action'] not in ('add', 'remove') or not row['ticker']:
                raise ValueError('Explicit add/remove ticker required')
            target = additions if row['action'] == 'add' else removals
            if row['ticker'] in target:
                raise ValueError('Repeated same-day ticker action')
            target.add(row['ticker'])
        if additions & removals or not removals <= current or additions & current:
            raise ValueError('Events inconsistent with observed company endpoint')
        current = (current - removals) | additions
        trace.append(dict(effective_date=day, added=sorted(additions), removed=sorted(removals),
                          company_ticker_count=len(current)))
    return dict(observed_event_rows=len(selected), trace=trace,
                reconstructed_endpoint_tickers=sorted(current),
                absent_from_reconstruction=sorted(set(after)-current),
                extra_in_reconstruction=sorted(current-set(after)),
                endpoint_ticker_sets_equal=current == set(after),
                exact_security_membership_verified=False, event_coverage_complete=False,
                intermediate_membership_verified=False, historical_identity_verified=False,
                point_in_time_verified=False, promotion_allowed=False,
                endpoint_agreement_cannot_exclude_offsetting_omitted_events=True)


def build():
    sources = {str(SOURCE): LOADED}

    def read(path, expected):
        raw = path.read_bytes()
        if digest(raw) != expected:
            raise ValueError('Bound source bytes changed: ' + str(path))
        sources[str(path)] = expected
        return raw

    peers = json.loads(read(PEER, PEER_SHA))
    for path, expected in peers['source_hashes'].items():
        read(Path(path), expected)
    if [t['stated_as_of'] for t in peers['tables']] != ['2023-01-01', '2024-01-01']:
        raise ValueError('Exact two dated issuer tables required')
    manifest = json.loads(read(EVENTS/'manifest.json', MANIFEST_SHA))
    entry = manifest['files']['exact_events']
    rows = list(csv.DictReader(io.StringIO(read(EVENTS/entry['filename'], entry['sha256']).decode('utf-8-sig'))))
    if len(rows) != entry['rows'] or len(rows) != 129:
        raise ValueError('Full bound event denominator differs')
    read(EVENTS/entry['manifest_filename'], entry['manifest_sha256'])
    selected = [r for r in rows if '2023-01-01' < r['effective_date'] < '2024-01-01']
    event_ids = {r[k] for r in selected for k in ('event_id', 'action_source_event_id')}
    for event_id in sorted(event_ids):
        entry = manifest['raw_source_manifests'][event_id]
        path = EVENTS/entry['filename']
        read(path, entry['sha256'])
        read(Path(str(path)+'.manifest.json'), entry['manifest_sha256'])
    for row in selected:
        if sources[str(EVENTS/row['raw_path'])] != row['content_sha256']:
            raise ValueError('Event raw content association differs')
    report = crosscheck(*[[r['ticker'] for r in t['rows']] for t in peers['tables']], rows)
    report.update(schema='ADOBE_COMPANY_ENDPOINT_EVENT_CROSSCHECK_V1', source_hashes=sources,
                  inherited_event_flags_not_recertified=True,
                  issuer_table_mirror_not_index_provider_baseline=True)
    for path, expected in sources.items():
        if digest(Path(path).read_bytes()) != expected:
            raise ValueError('Source changed during readback')
    return report


if __name__ == '__main__':
    report = build()
    OUTPUT.parent.mkdir(exist_ok=False)
    with OUTPUT.open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    for path, expected in report['source_hashes'].items():
        if digest(Path(path).read_bytes()) != expected:
            raise ValueError('Source changed after publication; output not accepted')
    print(json.dumps(dict(path=str(OUTPUT), sha256=digest(OUTPUT.read_bytes()),
                          endpoint_equal=report['endpoint_ticker_sets_equal'])))
