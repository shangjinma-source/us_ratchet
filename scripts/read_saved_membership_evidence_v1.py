"""Bind the existing fixed-pool limitation report to saved official raw evidence.

This is an evidence readback, not membership reconstruction or a new backtest.
"""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def run():
    base = ROOT / 'data/cache/candidate_pools/ndx_history/exact_events'
    registry_path = base / 'exact_events.csv'
    registry_raw = registry_path.read_bytes()
    manifest = json.loads((base / 'exact_events.csv.manifest.json').read_text(encoding='utf-8'))
    if digest(registry_raw) != manifest['content_sha256']:
        raise ValueError('Saved event registry hash mismatch')
    rows = list(csv.DictReader(registry_raw.decode('utf-8-sig').splitlines()))
    if len(rows) != manifest['row_count']:
        raise ValueError('Saved event registry count mismatch')
    prior_path = ROOT / 'tmp/historical_membership_limitations_20261024.json'
    prior_raw = prior_path.read_bytes()
    prior = json.loads(prior_raw)
    metrics_path = ROOT / prior['artifact']
    if digest(metrics_path.read_bytes()) != prior['artifact_sha256']:
        raise ValueError('Backtest metric artifact changed')
    sources = []
    for item in prior['sources']:
        matches = [row for row in rows if row['ticker'] == item['ticker']
                   and row['action'] == 'add' and row['effective_date'] == item['effective_date']
                   and row['announcement_date'] == item['announcement_date']]
        if len(matches) != 1:
            raise ValueError('Ambiguous saved addition event')
        event = matches[0]
        path = (base / event['raw_path']).resolve()
        if not path.is_relative_to(base.resolve()):
            raise ValueError('Raw evidence outside registry directory')
        raw = path.read_bytes()
        if digest(raw) != event['content_sha256']:
            raise ValueError('Raw official source hash mismatch')
        sources.append(dict(ticker=item['ticker'], event_id=event['event_id'],
                            announcement_date=event['announcement_date'],
                            effective_date=event['effective_date'],
                            source_url=event['source_locator'], raw_path=str(path.relative_to(ROOT)),
                            raw_sha256=digest(raw), byte_count=len(raw)))
    return dict(schema='SAVED_MEMBERSHIP_EVIDENCE_READBACK_V1',
                registry_sha256=digest(registry_raw), registry_rows=len(rows),
                previous_report_sha256=digest(prior_raw), sources=sources,
                affected_target_rows=len(prior['selected_before_known_addition']),
                affected_decision_months=len({row['decision_date'] for row in prior['selected_before_known_addition']}),
                raw_archive_verified=True, historical_complete_pool_verified=False,
                current_membership_verified=False, backtest_recomputed=False,
                production_pool_changed=False,
                limitation='Official event evidence exists; full initial membership and complete event coverage remain unproven. Historical fixed98 results retain their conditional scope.')


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2))
