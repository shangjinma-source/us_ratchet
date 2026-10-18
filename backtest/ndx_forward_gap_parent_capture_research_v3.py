"""Pure structural V3 capture planning. Caller supplies bytes, references and clock.

No filesystem, network, actual observation, authentication or seal operation.
The later IO adapter must bind this source and privately load its parser closure.
"""
from copy import deepcopy
from datetime import date, datetime, time, timezone
from hashlib import sha256
from io import BytesIO
import json
import re
from zoneinfo import ZoneInfo

from backtest.ndx_forward_source_capture_scoped_research import scoped_csv

SCHEMA = 'FORWARD_GAP_PARENT_CAPTURE_PLAN_V3'
SCOPED_PARSER_SHA256 = '9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee'
PARSER_DEPENDENCY_SHA256 = '30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'
PARENT_READER_SHA256 = '2be765c5dafcb85366e4e84d3a8cbed2037a6924649695f3ab176764075791f8'
ROLES = ('reference', 'publication_reference', 'readback_reference', 'reader_reference')
TICKERS = ('QQQ', 'SPY')
WRAPPER_FALSE = (
    'candidate_seal_allowed', 'clock_authenticity_verified', 'cohort_registration_allowed',
    'filesystem_attempt_inventory_authenticated', 'full_transitive_source_closure_reverified',
    'future_independent_oos', 'live_mutation_allowed', 'network_capture_performed',
    'observation_created', 'old_calendar_mutated', 'point_in_time_verified',
    'promotion_allowed', 'source_authenticity_verified')
FLAGS = dict.fromkeys(WRAPPER_FALSE + (
    'parent_history_authenticated_by_this_module', 'timeliness_verified',
    'production_generator_authorized', 'seal_event_created', 'partial_recovery_performed',
    'canonical_calendar_append_allowed', 'retrospective_backfill_allowed',
    'decision_eligible', 'exchange_holidays_and_early_closes_verified'), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact(left, right, message='Exact structural value required'):
    require(json.dumps(left, sort_keys=True, allow_nan=False) ==
            json.dumps(right, sort_keys=True, allow_nan=False), message)


def reference(value):
    require(type(value) is dict and set(value) == {'path', 'sha256'}, 'Exact reference')
    require(type(value['path']) is str and value['path'] and '\x00' not in value['path'], 'Reference path')
    require(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'Reference SHA256')
    return value


def merge(sources, value):
    reference(value)
    require(value['path'] not in sources or sources[value['path']] == value['sha256'], 'Conflicting source path')
    sources[value['path']] = value['sha256']


def claims(sources, mapping):
    require(type(mapping) is dict, 'Source claim map')
    for path, digest in mapping.items():
        merge(sources, dict(path=path, sha256=digest))


def inventory_references(value, sources):
    """Collect all nested reference declarations without treating them as IO proof."""
    if type(value) is dict:
        if 'path' in value and 'sha256' in value:
            merge(sources, {key: value[key] for key in ('path', 'sha256')})
        for key, item in value.items():
            if key in ('source_hashes', 'source_reference_claims'):
                claims(sources, item)
            else:
                inventory_references(item, sources)
    elif type(value) is list:
        for item in value:
            inventory_references(item, sources)


def false_flags(value, fields):
    for key in fields:
        require(value.get(key) is False, 'Authority flag changed: ' + key)


def day(value):
    require(type(value) is str, 'Session string')
    parsed = date.fromisoformat(value)
    require(parsed.isoformat() == value and parsed.weekday() < 5, 'Canonical weekday session')
    return parsed


def utc(value):
    require(type(value) is str, 'Explicit UTC capture string')
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0, 'Explicit UTC capture timestamp')
    return parsed.astimezone(timezone.utc)


def inspect_parent(parent):
    require(type(parent) is dict and set(parent) == set(ROLES) | {'document', 'publication', 'readback'}, 'Complete V3 envelope')
    sources = {}
    for role in ROLES:
        merge(sources, parent[role])
    exact(parent['reader_reference']['sha256'], PARENT_READER_SHA256)
    wrapper, publication, audit = (parent[key] for key in ('document', 'publication', 'readback'))
    exact(wrapper['schema'], 'SOURCE_BOUND_PROSPECTIVE_GAP_HISTORY_V3')
    exact(publication['schema'], 'PROSPECTIVE_GAP_HISTORY_PUBLICATION_V3')
    exact(publication['status'], 'PUBLISHED_GAP_EXTENSION_PENDING_INDEPENDENT_READBACK')
    exact(audit['schema'], 'PROSPECTIVE_GAP_HISTORY_INDEPENDENT_READBACK_V3')
    exact(audit['status'], 'PURE_GAP_HISTORY_READBACK_PASS')
    for item in (wrapper, publication, audit):
        false_flags(item, WRAPPER_FALSE)
        false_flags(item, set(FLAGS).intersection(item))
        inventory_references(item, sources)
    exact(publication['history_reference'], parent['reference'])
    exact(audit['history_reference'], parent['reference'])
    exact(audit['publication_reference'], parent['publication_reference'])
    exact(audit['reader_sha256'], parent['reader_reference']['sha256'])
    exact(wrapper['input_references'], publication['input_references'])
    exact(wrapper['input_references'], audit['input_references'])
    exact(wrapper['source_hashes'], publication['source_hashes'])
    declared = {}
    inventory_references(wrapper, declared)
    for path, digest in declared.items():
        require(wrapper['source_hashes'].get(path) == digest, 'Wrapper omitted nested source reference')
    producer = reference(audit['producer_reference'])
    require(audit['source_hashes'].get(producer['path']) == producer['sha256'], 'Readback producer association')
    require(audit['entire_history_independently_reconstructed'] is True and
            audit['publisher_called'] is False and audit['new_pure_called'] is False and
            audit['current_live_cache_read_or_reverified'] is False, 'Independent V3 reader roles')
    for role in ('reference', 'publication_reference', 'reader_reference'):
        item = parent[role]
        require(audit['source_hashes'].get(item['path']) == item['sha256'], 'Readback source association')
    for path, digest in wrapper['source_hashes'].items():
        require(audit['source_hashes'].get(path) == digest, 'Readback omitted wrapper source')
    h = wrapper['history']
    for prefix, role in (('parent_history','reference'), ('parent_publication','publication_reference'),
                         ('parent_readback','readback_reference')):
        exact(h[prefix + '_reference'], wrapper['input_references']['parent'][role])
    for prefix, role in (('capture','reference'), ('capture_publication','publication_reference'),
                         ('capture_readback','readback_reference')):
        exact(h[prefix + '_reference'], wrapper['input_references']['capture'][role])
    exact(h['schema'], 'PROSPECTIVE_GAP_EXTENSION_HISTORY_V3')
    false_flags(h, FLAGS)
    exact(h['policy_id'], 'FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH')
    exact(h['baseline_role'], 'LAST_ACTUAL_OBSERVATION_BASELINE_NOT_LAST_ACCOUNTED')
    require(type(h['pending_source_sessions']) is list and
            type(h['excluded_not_completed_source_sessions']) is list and
            not h['pending_source_sessions'] and not h['excluded_not_completed_source_sessions'],
            'BASELINE_HAS_UNACCOUNTED_SUFFIX')
    exact(h['captured_sources_are_exact_accounted_prefix'], False)
    rows = h['known_typed_rows']
    require(type(rows) is list and rows, 'Complete typed rows')
    days, months, actual = [], {}, []
    for index, row in enumerate(rows):
        exact(sorted(row), sorted(('sequence', 'session', 'kind', 'evidence_reference', 'seal_status')))
        require(type(row['sequence']) is int and row['sequence'] == index + 1, 'Typed sequence')
        day(row['session']); days.append(row['session'])
        require(row['kind'] in ('SEALED_PARENT_OBSERVED_SESSION', 'PROSPECTIVE_OBSERVED_SESSION', 'MISSED_OBSERVATION'), 'Typed kind')
        pointer = row['evidence_reference']
        require(type(pointer.get('json_pointer')) is str and pointer['json_pointer'].startswith('/'), 'Typed evidence pointer')
        if row['kind'] != 'MISSED_OBSERVATION':
            months.setdefault(row['session'][:7], row['session'])
        else:
            exact(row['seal_status'], 'NOT_ATTEMPTED')
        if row['kind'] == 'PROSPECTIVE_OBSERVED_SESSION':
            actual.append(row)
    exact(days, sorted(set(days)))
    for key, expected in [('typed_row_count', len(rows)), ('observation_count', len(actual)),
                          ('new_observation_count', 0)]:
        require(type(h[key]) is int and h[key] == expected, 'Exact history count: ' + key)
    original = h['known_typed_rows_preserved']
    require(type(h['parent_typed_row_count']) is int and h['parent_typed_row_count'] == len(original), 'Parent count')
    exact(rows[:len(original)], original)
    added = rows[len(original):]
    require(all(row['kind'] == 'MISSED_OBSERVATION' for row in added), 'Only gap extension')
    require(type(h['new_missed_observation_count']) is int and h['new_missed_observation_count'] == len(added), 'New gap count')
    exact([item['session'] for item in h['gap_classifications']], [row['session'] for row in added])
    exact(h['first_actual_observed_session_by_month'], months)
    exact(h['last_accounted_session'], days[-1])
    exact(h['last_observed_session'], next(row['session'] for row in reversed(rows) if row['kind'] != 'MISSED_OBSERVATION'))
    entries = h['observations']
    require(type(entries) is list and len(entries) == len(actual), 'Actual observation inventory')
    require(type(h['parent_attempt_inventory']) is list and len(h['parent_attempt_inventory']) == len(actual), 'Exact resolved attempt inventory')
    for row, entry in zip(actual, entries):
        exact(entry['session'], row['session']); exact(entry['sequence'], row['sequence'])
        exact(row['evidence_reference'], dict(entry['payload_reference'], json_pointer='/observation_identity'))
        exact(entry['first_actual_observed_session_of_month'], months[row['session'][:7]])
        exact(entry['month_first_actual_observation'], months[row['session'][:7]] == row['session'])
        matching = [attempt for attempt in h['parent_attempt_inventory'] if attempt.get('session') == row['session']]
        require(len(matching) == 1, 'Unique resolved actual attempt')
        exact(matching[0], dict(session=row['session'], observation_id=entry['observation_id'],
              status='PERSISTED_AND_INDEPENDENTLY_READ_BACK', payload_reference=entry['payload_reference'],
              receipt_reference=entry['receipt_reference'], independent_readback_reference=entry['audit_reference']))
    exact(audit['counts'], {key: h[key] for key in ('parent_typed_row_count', 'typed_row_count',
          'observation_count', 'new_observation_count', 'new_missed_observation_count',
          'last_observed_session', 'last_accounted_session', 'first_actual_observed_session_by_month')})
    return h, days, sources


def plan_gap_parent_capture(*, parent, source_bytes, source_references,
                            accounted_baseline_bytes, actual_baseline_bytes,
                            capture_started_at, capture_completed_at, tzif_bytes, tzif_reference):
    h, days, sources = inspect_parent(parent)
    for value in (source_bytes, source_references, accounted_baseline_bytes, actual_baseline_bytes,
                  h['captured_source_references'], h['baseline_references']):
        require(type(value) is dict and set(value) == set(TICKERS), 'Exact source pair')
    started, completed = utc(capture_started_at), utc(capture_completed_at)
    require(started <= completed, 'Capture clock reversal')
    merge(sources, tzif_reference)
    exact(tzif_reference['sha256'], h['tzif_reference']['sha256'], 'Parent TZif hash binding')
    require(type(tzif_bytes) is bytes and sha256(tzif_bytes).hexdigest() == tzif_reference['sha256'], 'TZif bytes hash')
    zone = ZoneInfo.from_file(BytesIO(tzif_bytes), key='America/New_York')
    close = lambda session: datetime.combine(day(session), time(16), zone).astimezone(timezone.utc)
    require(started >= close(days[-1]), 'Capture precedes accounted close')
    diagnostics, evidence, new_dates = [], {}, {}
    for ticker in TICKERS:
        old, actual, current = accounted_baseline_bytes[ticker], actual_baseline_bytes[ticker], source_bytes[ticker]
        for raw, ref in ((old, h['captured_source_references'][ticker]),
                         (actual, h['baseline_references'][ticker]), (current, source_references[ticker])):
            merge(sources, ref)
            require(type(raw) is bytes and sha256(raw).hexdigest() == ref['sha256'], 'CSV bytes hash')
        _, old_meta = scoped_csv(old, days[0]); _, actual_meta = scoped_csv(actual, days[0])
        _, current_meta = scoped_csv(current, days[0])
        scoped_days = lambda meta: [meta['original_rows'][i]['session'] for i in meta['included_original_row_indexes']]
        require(scoped_days(old_meta) == days, 'BASELINE_HAS_UNACCOUNTED_SUFFIX')
        require(old.startswith(actual) and scoped_days(actual_meta) ==
                [value for value in days if value <= h['last_observed_session']], 'Last actual complete baseline prefix')
        current_days = scoped_days(current_meta)
        if not current.startswith(old) or current_days[:len(days)] != days:
            diagnostics.append(dict(reason='ACCOUNTED_BASELINE_PREFIX_REVISED', ticker=ticker))
        new_dates[ticker] = current_days[len(days):] if current_days[:len(days)] == days else []
        evidence[ticker] = dict(source_reference=deepcopy(source_references[ticker]),
            accounted_baseline_reference=deepcopy(h['captured_source_references'][ticker]),
            actual_baseline_reference=deepcopy(h['baseline_references'][ticker]),
            original_row_count=current_meta['original_row_count'], source_session_dates=current_days,
            new_session_dates=new_dates[ticker], full_accounted_bytes_prefix_matches=current.startswith(old),
            included_original_row_indexes=current_meta['included_original_row_indexes'],
            excluded_original_row_indexes=current_meta['excluded_original_row_indexes'],
            excluded_before_scope_ohlc_diagnostics=current_meta['excluded_before_scope_ohlc_diagnostics'])
    if new_dates['QQQ'] != new_dates['SPY']:
        diagnostics.append(dict(reason='ASYMMETRIC_NEW_SESSION_DATES'))
    if any(len(value) > 1 for value in new_dates.values()):
        diagnostics.append(dict(reason='MULTIPLE_UNACCOUNTED_SESSIONS'))
    candidate = new_dates['QQQ'][0] if not diagnostics and len(new_dates['QQQ']) == 1 else None
    if candidate and started < close(candidate):
        diagnostics.append(dict(reason='SOURCE_SESSION_NOT_COMPLETED_AT_CAPTURE_START'))
        candidate = None
    status = ('BLOCKED_SOURCE_DIAGNOSTICS' if diagnostics else
              'ONE_NEW_SESSION_CAPTURE_CANDIDATE' if candidate else 'NO_NEW_SESSION')
    return dict(schema=SCHEMA, status=status, diagnostics=diagnostics, candidate_session=candidate,
        policy_id=h['policy_id'], parent_references={key: deepcopy(parent[key]) for key in ROLES},
        known_typed_rows=deepcopy(h['known_typed_rows']), observations=deepcopy(h['observations']),
        parent_attempt_inventory=deepcopy(h['parent_attempt_inventory']),
        first_actual_observed_session_by_month=deepcopy(h['first_actual_observed_session_by_month']),
        baseline_references=deepcopy(h['baseline_references']), baseline_role=h['baseline_role'],
        accounted_baseline_references=deepcopy(h['captured_source_references']),
        accounted_baseline_role='FULL_SAVED_CSV_SCOPE_EQUALS_ALL_KNOWN_TYPED_SESSIONS',
        last_accounted_session=h['last_accounted_session'], last_observed_session=h['last_observed_session'],
        source_evidence=evidence, source_reference_claims=sources,
        capture_started_at=started.isoformat(), capture_completed_at=completed.isoformat(),
        tzif_reference=deepcopy(tzif_reference),
        candidate_conservative_close_utc=close(candidate).isoformat() if candidate else None,
        timing_semantics='CALLER_SUPPLIED_CLOCK_CONSERVATIVE_16_NY_CLOSE_NOT_AUTHENTICATED_EXCHANGE_CALENDAR',
        late_observation_classification_deferred_to_payload_core=True,
        authentication_role='STRUCTURAL_DECLARATIONS_AND_SUPPLIED_BYTES_ONLY_NO_IO_AUTHENTICATION',
        raw_source_bytes_embedded=False,
        dependency_sha256=dict(scoped=SCOPED_PARSER_SHA256, base=PARSER_DEPENDENCY_SHA256), **FLAGS)
