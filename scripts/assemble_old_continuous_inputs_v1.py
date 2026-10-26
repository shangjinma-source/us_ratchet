"""Preserve the entire reviewed interval for selection and exposure-gated execution.

This envelope deliberately is NOT the v4 execution assembler output. Unknown
action families remain null. A runner must save its selection and call the gate
before admitting any interval to an execution adapter.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SHA256 = 'c1463e92169d9c32482fb86573cfe96f7d0f659405ff579a8038e56e45411f77'
KNOWN_BARRIERS = (
    ('SPLK', '2024-03-18', 'CASH_MERGER'),
    ('ILMN', '2024-06-24', 'GRAL_DISTRIBUTION'),
    ('WDC', '2025-02-24', 'SNDK_DISTRIBUTION'),
    ('ANSS', '2025-07-17', 'CASH_STOCK_MERGER'),
    ('WBA', '2025-08-28', 'CASH_AND_UNVALUED_DAP'),
)
MERGER_REFERENCES = {
    'SPLK': 'tmp/ea_splk_lifecycle_20261026/review.json',
    'ANSS': 'tmp/anss_terminal_bridge_20261026/review.json',
    'WBA': 'tmp/wba_terminal_official_20261026/review.json',
}


def assemble(schema_path):
    raw = Path(schema_path).read_bytes()
    if sha256(raw).hexdigest() != SCHEMA_SHA256:
        raise ValueError('FROZEN_SCHEMA_CHANGED')
    schema = json.loads(raw)
    pins = dict(schema['source_hashes'])
    for name, expected in pins.items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError('SOURCE_CHANGED:' + name)
    monthly = deepcopy(schema['monthly_input_candidates'])
    prepared = deepcopy(schema['prepared_input_candidate'])
    sessions = prepared['session_dates']
    if len(monthly) != 31 or sessions[0] != '2023-12-29' or sessions[-1] != '2026-07-30':
        raise ValueError('FULL_31_MONTH_SCOPE_REQUIRED')
    pins[Path(schema_path).resolve().relative_to(ROOT).as_posix()] = SCHEMA_SHA256
    pins[Path(__file__).resolve().relative_to(ROOT).as_posix()] = sha256(Path(__file__).read_bytes()).hexdigest()
    for plan in monthly:
        plan['source_hashes'] = deepcopy(pins)
    prepared['source_hashes'] = deepcopy(pins)
    distributions = deepcopy(schema['reusable_reviewed_action_candidates']['prior_distribution_events'])
    for reference in MERGER_REFERENCES.values():
        raw_review = (ROOT / reference).read_bytes()
        pins[reference] = sha256(raw_review).hexdigest()
        review = json.loads(raw_review)
        for source, expected in review.get('source_hashes', {}).items():
            if sha256((ROOT / source).read_bytes()).hexdigest() != expected:
                raise ValueError('MERGER_SOURCE_CHANGED:' + source)
            if source in pins and pins[source] != expected:
                raise ValueError('MERGER_SOURCE_PIN_CONFLICT:' + source)
            pins[source] = expected
    for event in distributions:
        if event['effective_date'] != event['date'] or event['timing'] not in ('BEFORE_OPEN', 'AFTER_CLOSE'):
            raise ValueError('DISTRIBUTION_EFFECTIVE_CLOCK_INVALID')
        for reference in event['source_references']:
            content = (ROOT / reference).read_bytes()
            expected = sha256(content).hexdigest()
            if reference in pins and pins[reference] != expected:
                raise ValueError('DISTRIBUTION_SOURCE_CHANGED:' + reference)
            pins[reference] = expected
    for plan in monthly:
        plan['source_hashes'] = deepcopy(pins)
    prepared['source_hashes'] = deepcopy(pins)
    return dict(status='FULL_INTERVAL_SELECTION_ENVELOPE_EXECUTION_REQUIRES_EXPOSURE_GATE',
                monthly_inputs=monthly, session_dates=sessions, source_hashes=pins,
                prepared_input_candidate=prepared, ohlc=schema['ohlc'],
                provider_event_inventory=schema['provider_event_inventory'],
                action_stream_missing=schema['action_stream_missing'],
                dated_identity_transitions=schema['dated_identity_transitions'],
                prior_distribution_events=distributions,
                runner_execution_authorized=False, economic_run_completed=False,
                unknown_action_families_preserved=True)


def exposure_gate(envelope, arguments, selected, end_date, active_date):
    """Conservative first gate. Reviewed mappings require a later explicit adapter.

    Do not accept caller-supplied booleans as event execution authorization.
    All dated provider observations stay visible, including alternate sources.
    """
    start = arguments['decision_date']
    holdings = arguments['account_state']['shares']
    targets = selected['target_quantities']
    exposed = {sid for sid, quantity in holdings.items() if quantity}
    exposed.update(sid for sid, quantity in targets.items() if quantity)
    ends = {sid: end_date if targets.get(sid, 0) else active_date for sid in exposed}
    metadata = envelope['prepared_input_candidate']['metadata']
    events, missing = [], []
    for sid in sorted(exposed):
        if sid not in metadata:
            raise ValueError('UNKNOWN_EXPOSED_SECURITY:' + sid)
        ticker = metadata[sid]['ticker']
        for row in envelope['provider_event_inventory']:
            if row['ticker'] == ticker and start < row['date'] <= ends[sid]:
                events.append(dict(security_id=sid, **row))
        for row in envelope['action_stream_missing']:
            if row['ticker'] == ticker:
                segments = envelope['prepared_input_candidate']['source_provenance'][sid]['segments']
                covered = [segment for segment in segments
                           if segment['source_path'] == row['source']
                           and segment['end'] > start and segment['start'] <= ends[sid]]
                if covered:
                    missing.append(dict(security_id=sid, selected_source_segments=covered, **row))
        for transition in envelope['dated_identity_transitions']:
            if sid in (transition['old_sid'], transition['new_sid']) and start < transition['date'] <= ends[sid]:
                events.append(dict(security_id=sid, kind='IDENTITY_CONVERSION', **transition))
        for event in envelope.get('prior_distribution_events', []):
            day = event['effective_date']
            # Decision snapshots precede after-close distributions. Such rights
            # must be recognized before computing that day's recommendation.
            after_close_at_start = day == start and event['timing'] == 'AFTER_CLOSE' and holdings.get(sid, 0)
            if sid == event['parent_sid'] and (start < day <= ends[sid] or after_close_at_start):
                events.append(dict(security_id=sid, kind='DISTRIBUTION', **event))
        for event_ticker, day, kind in KNOWN_BARRIERS:
            if ticker == event_ticker and start < day <= ends[sid]:
                events.append(dict(security_id=sid, date=day, kind=kind, origin='REVIEW_BARRIER_NOT_EXECUTION',
                                   source_references=[MERGER_REFERENCES[ticker]] if ticker in MERGER_REFERENCES else []))
    return dict(admitted=not events and not missing, decision_date=start, through=end_date,
                exposed=sorted(exposed), exposure_end_by_security=ends,
                unmapped_events=events, missing_action_streams=missing,
                evidence_scope='CONDITIONAL_PROVIDER_ABSENCE_NOT_EXHAUSTIVE_OFFICIAL_PROOF')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--schema', type=Path, default=ROOT / 'tmp/old_window_execution_prices_20261026/continuous_schema_precheck_v2.json')
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    result = assemble(options.schema)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    with options.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(dict(status=result['status'], months=len(result['monthly_inputs']), search_calls=0)))


if __name__ == '__main__':
    main()
