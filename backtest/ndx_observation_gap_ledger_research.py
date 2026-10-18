"""Separate missed-observation evidence chain; never a calendar-v2 extension.

References and timestamps are caller-supplied. A source-bound caller must check
their bytes and clock. This module grants no timely-observation permissions.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json

SCHEMA = 'OBSERVATION_GAP_EVIDENCE_LEDGER_V1'
MAX_EVENTS = 1024
FALSE = {key: False for key in (
    'observed_session_added', 'fresh_observation', 'decision_eligible',
    'candidate_seal_allowed', 'cohort_registration_allowed',
    'first_observed_session_of_month', 'historical_timeliness_verified',
    'future_timeliness_granted', 'canonical_calendar_append_allowed',
    'point_in_time_verified', 'promotion_allowed', 'live_mutation_allowed',
    'source_bytes_verified', 'system_clock_verified', 'oos_recovery_completed')}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()


def reference(value):
    require(type(value) is dict and set(value) == {'path', 'sha256'}, 'Reference schema')
    require(type(value['path']) is str and bool(value['path'].strip()), 'Reference path')
    sha(value['sha256'])


def sha(value):
    require(type(value) is str and len(value) == 64 and
            all(c in '0123456789abcdef' for c in value), 'SHA256 required')


def day(value):
    require(type(value) is str and date.fromisoformat(value).isoformat() == value, 'Canonical session')
    require(date.fromisoformat(value).weekday() < 5, 'Weekday session required')
    return value


def clock(value):
    require(type(value) is str, 'Explicit UTC timestamp')
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), 'UTC required')
    return parsed


def parent(value):
    require(type(value) is dict and set(value) == {'manifest_reference',
        'event_prefix_reference', 'session_projection_reference', 'event_count',
        'session_count', 'last_session', 'event_tail_sha256'}, 'Parent binding schema')
    for key in ('manifest_reference', 'event_prefix_reference', 'session_projection_reference'):
        reference(value[key])
    require(type(value['event_count']) is int and type(value['session_count']) is int
            and value['event_count'] >= value['session_count'] > 0, 'Parent counts')
    day(value['last_session']); sha(value['event_tail_sha256'])


def _build(binding, batches):
    parent(binding)
    require(type(batches) is list and 0 < len(batches) <= MAX_EVENTS, 'Bounded nonempty batches')
    events = []; previous = binding['event_tail_sha256']; latest = binding['last_session']
    last_recorded = None; last_captured = None; receipts = {}; capture_hashes = set()
    for batch in batches:
        require(type(batch) is dict and set(batch) == {'classification_capture',
            'classification_reference', 'recorded_at_utc'}, 'Batch schema')
        reference(batch['classification_reference'])
        capture = batch['classification_capture']; recorded = clock(batch['recorded_at_utc'])
        require(type(capture) is dict and capture.get('schema') == 'CURRENT_SOURCE_GAP_CLASSIFICATION_CAPTURE_V1', 'Capture schema')
        captured = clock(capture['captured_at_utc'])
        require(last_captured is None or captured >= last_captured, 'Capture timestamp moved backwards')
        last_captured = captured
        require(recorded >= captured and (last_recorded is None or recorded >= last_recorded), 'Record precedes capture or prior record')
        last_recorded = recorded
        cref = batch['classification_reference']['sha256']
        require(cref not in capture_hashes, 'Duplicate classification reference')
        capture_hashes.add(cref)
        for key in ('old_calendar_mutated', 'calendar_append_allowed', 'candidate_seal_allowed',
                    'cohort_registration_allowed', 'promotion_allowed', 'live_mutation_allowed'):
            require(capture.get(key) is False, 'Capture permission changed: '+key)
        require(capture['parent_references']['calendar_manifest'] == binding['manifest_reference'] and
                capture['parent_references']['calendar_events'] == binding['event_prefix_reference'], 'Old prefix drift')
        refs = capture['captured_source_references']
        require(type(refs) is dict and set(refs) == {'QQQ', 'SPY'}, 'Two saved raw references required')
        for ref in refs.values():
            reference(ref)
            identity = (ref['path'], ref['sha256'])
            require(identity not in receipts or receipts[identity] == capture['captured_at_utc'], 'Raw receipt timestamp contradiction')
            receipts[identity] = capture['captured_at_utc']
        classified = capture['classification']
        require(classified['schema'] == 'OBSERVATION_GAP_RECOVERY_CLASSIFICATION_V1' and
                classified['last_sealed_session'] == binding['last_session'] and
                classified['observed_at_utc'] == capture['captured_at_utc'] and
                classified['timeliness_candidate'] is None, 'Classification boundary changed')
        rows = classified['pending_classifications']
        require(type(rows) is list and rows and type(classified['missed_or_ineligible_row_count']) is int
                and classified['missed_or_ineligible_row_count'] == len(rows), 'Missed count')
        for key in ('canonical_calendar_append_allowed', 'candidate_seal_allowed', 'cohort_registration_allowed',
                    'retrospective_backfill_allowed', 'point_in_time_verified', 'promotion_allowed'):
            require(classified.get(key) is False, 'Classification permission changed')
        for index, row in enumerate(rows):
            session = day(row['session'])
            require(session > latest, 'Unique ascending missed sessions required')
            latest = session
            require(row['classification'] in {'EARLIER_PENDING_ROW_NOT_TIMELY_EVIDENCE',
                'LATEST_ROW_SEAL_DEADLINE_MISSED', 'BEFORE_PROSPECTIVE_START'}, 'Timely row cannot enter missed ledger')
            require(row['recorded_at_utc'] == capture['captured_at_utc'] and
                    row['decision_eligible'] is False and row['first_observed_at_historical_close_claimed'] is False,
                    'Historical observation falsely claimed')
            require(clock(row['conservative_close_utc']) < clock(row['conservative_seal_deadline_utc']) <= captured,
                    'This ledger accepts only already-late completed observations')
            source_rows = {ticker: capture['pending_source_rows'][ticker][session] for ticker in refs}
            require(all(source_row['Date'] == session for source_row in source_rows.values()), 'Source row date mismatch')
            event = {'schema': 'MISSED_OBSERVATION_EVIDENCE_EVENT_V1',
                'event_sequence': binding['event_count']+len(events)+1,
                'event_type': 'MISSED_OBSERVATION', 'session': session,
                'event_recorded_at_utc': batch['recorded_at_utc'],
                'classification_captured_at_utc': capture['captured_at_utc'],
                'historical_source_first_observed_at_utc': None,
                'classification_reference': deepcopy(batch['classification_reference']),
                'classification_json_pointer': '/classification/pending_classifications/'+str(index),
                'classification_row': deepcopy(row), 'source_references': deepcopy(refs),
                'saved_source_rows': deepcopy(source_rows), 'previous_event_sha256': previous, **FALSE}
            event['event_sha256'] = digest(event)
            previous = event['event_sha256']; events.append(event)
            require(len(events) <= MAX_EVENTS, 'Engineering event bound exceeded')
    result = {'schema': SCHEMA, 'parent_binding': deepcopy(binding), 'batches': deepcopy(batches),
        'events': events, 'missed_observation_count': len(events),
        'terminal_event_sha256': previous, 'observed_session_increment': 0,
        'fresh_session_increment': 0, 'seal_increment': 0, 'cohort_increment': 0,
        'old_last_observed_session_unchanged': binding['last_session'],
        'scope': 'SEPARATE_MISSED_EVIDENCE_CHAIN_NOT_CALENDAR_V2_OR_CANDIDATE_ADAPTER', **FALSE}
    result['ledger_sha256'] = digest(result)
    return result


def validate_gap_ledger(*, ledger, parent_binding):
    """Rebuild every hash and permission; caller still authenticates file refs."""
    require(type(ledger) is dict and ledger.get('parent_binding') == parent_binding, 'Parent binding drift')
    expected = _build(parent_binding, ledger['batches'])
    unsigned = dict(ledger)
    saved_digest = unsigned.pop('ledger_sha256', None)
    require(digest(unsigned) == saved_digest, 'Ledger digest changed')
    require(canonical(ledger) == canonical(expected), 'Ledger content or hash chain changed')
    return True


def append_missed_observations(*, parent_binding, classification_capture,
        classification_reference, recorded_at_utc, existing_ledger=None):
    """Append a whole sealed late batch. Existing evidence cannot be revised."""
    batches = []
    if existing_ledger is not None:
        validate_gap_ledger(ledger=existing_ledger, parent_binding=parent_binding)
        batches = deepcopy(existing_ledger['batches'])
    batches.append({'classification_capture': deepcopy(classification_capture),
        'classification_reference': deepcopy(classification_reference), 'recorded_at_utc': recorded_at_utc})
    result = _build(parent_binding, batches)
    if existing_ledger is not None:
        require(result['events'][:len(existing_ledger['events'])] == existing_ledger['events'], 'Append rewrote prefix')
    return result
