"""Build exposure-scoped event candidates, never authorize economic execution."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'tmp/old_window_execution_prices_20261026/continuous_schema_precheck_v2.json'
EXPECTED = 'c1463e92169d9c32482fb86573cfe96f7d0f659405ff579a8038e56e45411f77'


def build_candidates(schema):
    metadata = schema['prepared_input_candidate']['metadata']
    groups = defaultdict(list)
    for observation in schema['provider_event_inventory']:
        groups[(observation['ticker'], observation['date'], observation['kind'])].append(observation)
    candidates = []
    for (ticker, day, kind), observations in sorted(groups.items()):
        identities = [sid for sid, meta in metadata.items()
                      if meta['ticker'] == ticker and day in schema['ohlc'].get(sid, {})]
        variants = {}
        for observation in observations:
            payload = observation['provider_payload']
            key = json.dumps(payload, sort_keys=True)
            variants.setdefault(key, []).append(observation['source'])
        candidates.append({
            'event_id': f'provider_candidate:{ticker}:{day}:{kind}',
            'ticker': ticker, 'date': day, 'kind': kind,
            'security_id': identities[0] if len(identities) == 1 else None,
            'identity_candidates': identities,
            'ex_date_candidate': day if kind == 'dividends' else None,
            'payment_date': None,
            'amount_per_share': None,
            'observations': observations,
            'distinct_payloads': [{'payload': json.loads(k), 'sources': sorted(set(v))}
                                  for k, v in sorted(variants.items())],
            'source_conflict': len(variants) > 1,
            'execution_authorized': False,
            'required_if_exposed': ['VERIFY_EVENT_SEMANTICS_AND_NOMINAL_SHARE_UNITS',
                                    'VERIFY_EX_DATE_AND_PAYMENT_DATE_SEPARATELY']
                                    if kind == 'dividends' else ['VERIFY_OFFICIAL_TERMS'],
        })
    return candidates


def main():
    raw = (ROOT / SOURCE).read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('FROZEN_SCHEMA_HASH_MISMATCH')
    schema = json.loads(raw)
    candidates = build_candidates(schema)
    missing_sources = {(row['ticker'], row['source']) for row in schema['action_stream_missing']}
    missing_segments = []
    prepared = schema['prepared_input_candidate']
    for sid, provenance in prepared['source_provenance'].items():
        ticker = prepared['metadata'][sid]['ticker']
        for segment in provenance['segments']:
            if (ticker, segment['source_path']) in missing_sources:
                missing_segments.append({'security_id': sid, 'ticker': ticker, **segment,
                                         'status': 'SELECTED_SOURCE_ACTION_STREAM_UNKNOWN'})
    result = {
        'status': 'EXPOSURE_INDEX_NOT_EXECUTION_INPUT',
        'source_hashes': {SOURCE: EXPECTED},
        'provider_candidates': candidates,
        'reviewed_facts': schema['reusable_reviewed_action_candidates'],
        'dated_identity_transitions': schema['dated_identity_transitions'],
        'missing_action_streams': schema['action_stream_missing'],
        'selected_missing_action_segments': missing_segments,
        'counts': {'raw_observations': len(schema['provider_event_inventory']),
                   'deduplicated_candidates': len(candidates),
                   'dividend_candidates': sum(c['kind'] == 'dividends' for c in candidates),
                   'conflicting_candidates': sum(c['source_conflict'] for c in candidates),
                   'unmapped_candidates': sum(c['security_id'] is None for c in candidates)},
        'limitations': ['Provider event date is not a payment date.',
                        'Provider split-adjusted dividend amounts require nominal-unit reconciliation.',
                        'Absent action stream is unknown, not certified no events.',
                        'Review only actual held or pending-order exposure; do not delete unselected evidence.',
                        'Reviewed facts and provider observations are separate views, not additive ledger events.'],
        'economic_runs': 0, 'execution_authorized': False,
    }
    output = ROOT / 'tmp/old_window_action_candidates_20261026_v1/candidates_v2.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps(result['counts']))


if __name__ == '__main__':
    main()
