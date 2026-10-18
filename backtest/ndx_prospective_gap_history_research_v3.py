"""Pure V2-to-V3 missed-session extension; no IO, clock authentication or observation."""
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

from backtest import ndx_variable_prefix_capture_research as capture_core

SCHEMA = 'PROSPECTIVE_GAP_EXTENSION_HISTORY_V3'
POLICY = capture_core.POLICY
DEPENDENCY_SHA256 = {
    'core': '9c76324fcbc8e5d57a1ef25566a59110acff32a58506c6d5b6947996e6c26039',
    'scoped': capture_core.SCOPED_PARSER_SHA256,
    'base': capture_core.PARSER_DEPENDENCY_SHA256,
}
FLAGS = dict.fromkeys((
    'source_authenticity_verified', 'parent_history_authenticated_by_this_module',
    'clock_authenticity_verified', 'timeliness_verified',
    'filesystem_attempt_inventory_authenticated', 'observation_created',
    'candidate_seal_allowed', 'cohort_registration_allowed', 'point_in_time_verified',
    'promotion_allowed', 'live_mutation_allowed', 'future_independent_oos',
    'production_generator_authorized', 'seal_event_created', 'partial_recovery_performed',
    'old_calendar_mutated', 'canonical_calendar_append_allowed',
    'retrospective_backfill_allowed', 'decision_eligible',
    'exchange_holidays_and_early_closes_verified',
    'network_capture_performed', 'full_transitive_source_closure_reverified',
), False)
PARENT_AUTHORITY_FLAGS = (
    'source_authenticity_verified', 'filesystem_attempt_inventory_authenticated',
    'clock_authenticity_verified', 'candidate_seal_allowed', 'cohort_registration_allowed',
    'point_in_time_verified', 'promotion_allowed', 'live_mutation_allowed',
    'future_independent_oos', 'production_generator_authorized', 'seal_event_created',
    'partial_recovery_performed', 'old_calendar_mutated',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact(left, right):
    capture_core.exact(left, right)


def merge_claims(sources, claims):
    require(type(claims) is dict, 'Exact source claim map required')
    for path, digest in claims.items():
        capture_core.merge(sources, {'path': path, 'sha256': digest})


def no_authority(document, fields):
    for field in fields:
        require(document.get(field) is False, 'Authority flag changed: ' + field)


def inspect_capture(envelope, parent, sources):
    """Validate supplied evidence associations; never authenticate filesystem bytes."""
    for role in ('reference', 'publication_reference', 'readback_reference', 'reader_reference'):
        capture_core.merge(sources, envelope[role])
    document, publication, audit = (envelope[key] for key in ('document', 'publication', 'readback'))
    exact(document['schema'], 'SOURCE_BOUND_VARIABLE_PREFIX_CAPTURE_V1')
    exact(publication['schema'], 'VARIABLE_PREFIX_CAPTURE_PUBLICATION_V1')
    exact(publication['status'], 'PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION')
    exact(audit['schema'], 'VARIABLE_PREFIX_CAPTURE_INDEPENDENT_READBACK_V1')
    exact(audit['status'], 'PASS')
    for item in (publication, audit):
        exact(item['capture_reference'], envelope['reference'])
    exact(audit['publication_reference'], envelope['publication_reference'])
    exact(audit['reader_sha256'], envelope['reader_reference']['sha256'])
    parent_references = {role: parent[role] for role in
                         ('reference', 'publication_reference', 'readback_reference', 'reader_reference')}
    exact(document['parent_references'], parent_references)
    exact(audit['parent_references'], parent_references)
    for item in (document, publication, audit):
        no_authority(item, capture_core.FLAGS)
        merge_claims(sources, item['source_hashes'])
    exact(document['source_hashes'], publication['source_hashes'])
    for path, digest in document['source_hashes'].items():
        require(audit['source_hashes'].get(path) == digest, 'Capture audit omitted source')
    for role in ('reference', 'publication_reference', 'reader_reference'):
        reference = envelope[role]
        require(audit['source_hashes'].get(reference['path']) == reference['sha256'],
                'Capture audit reference association')
    require(document['clock_captured_by_runner'] is True,
            'Runner clock recording required, not external authentication')
    require(document['external_clock_attestation_verified'] is False and
            audit['external_clock_attestation_verified'] is False, 'No external clock inference')
    require(audit['producer_called'] is False and audit['plan_history_capture_called'] is False and
            audit['snapshot_bytes_verified'] is True, 'Independent capture reader role')
    inputs = document['input_references']
    require(type(inputs) is dict and set(inputs) == {'core', 'scoped', 'base', 'tzif'},
            'Exact capture dependency roles')
    for role, digest in DEPENDENCY_SHA256.items():
        capture_core.merge(sources, inputs[role])
        exact(inputs[role]['sha256'], digest)
    artifacts = document['captured_artifacts']
    require(type(artifacts) is dict and set(artifacts) == {'QQQ', 'SPY', 'tzif'},
            'Exact captured artifacts')
    for reference in (*inputs.values(), *artifacts.values(), *parent_references.values()):
        capture_core.ref(reference)
        require(document['source_hashes'].get(reference['path']) == reference['sha256'],
                'Capture source reference association')
        capture_core.merge(sources, reference)
    exact(artifacts['tzif']['sha256'], inputs['tzif']['sha256'])
    return document, audit


def conservative_timing(session, zone):
    day = datetime.fromisoformat(session).date()
    close = datetime.combine(day, time(16), zone).astimezone(timezone.utc)
    following = day + timedelta(days=1)
    while following.weekday() >= 5:
        following += timedelta(days=1)
    deadline = datetime.combine(following, time(9, 30), zone).astimezone(timezone.utc)
    return close, deadline


def extend_gap_history(*, parent, capture, source_bytes, baseline_bytes, tzif_bytes):
    """Consume an externally read-back V2 parent and capture; append missed rows only.

    Only V2 parents are supported. V3 is deliberately incompatible with the old
    variable-prefix observer. A future V3 source capture/writer/reader is required
    before new actual observations can consume this result. All bytes and anchors
    are caller supplied; the IO adapter must authenticate them independently.
    New dates are derived exclusively by replaying the pinned upstream capture
    plan against complete QQQ/SPY source and original baseline bytes.
    """
    history, days, months, sources = capture_core.inspect_parent(parent)
    no_authority(history, PARENT_AUTHORITY_FLAGS)
    # Publication/readback schemas carry different optional authority fields.
    # Their mandatory four are checked upstream; any additional known field
    # present must also remain strictly false, never contradictory to history.
    authority_fields = set(PARENT_AUTHORITY_FLAGS) | set(FLAGS) | set(capture_core.FLAGS)
    for role in ('publication', 'readback'):
        no_authority(parent[role], authority_fields.intersection(parent[role]))
    # Tighten typed row shape and preserve every historical evidence pointer.
    pointers = set()
    for row in history['known_typed_rows']:
        require(type(row) is dict and set(row) ==
                {'sequence', 'session', 'kind', 'evidence_reference', 'seal_status'}, 'Exact typed row')
        evidence = row['evidence_reference']
        require(type(evidence) is dict and set(evidence) == {'path', 'sha256', 'json_pointer'},
                'Exact historical pointer')
        capture_core.merge(sources, {key: evidence[key] for key in ('path', 'sha256')})
        pointer = evidence['json_pointer']
        require(type(pointer) is str and pointer.startswith('/') and len(pointer) > 1,
                'Historical JSON pointer')
        identity = (evidence['path'], evidence['sha256'], pointer)
        require(identity not in pointers, 'Duplicate historical pointer')
        pointers.add(identity)
    document, audit = inspect_capture(capture, parent, sources)
    artifacts = document['captured_artifacts']
    plan = capture_core.plan_history_capture(
        parent=parent, source_bytes=source_bytes,
        source_references={ticker: artifacts[ticker] for ticker in ('QQQ', 'SPY')},
        baseline_bytes=baseline_bytes, capture_started_at=document['capture_started_at'],
        capture_completed_at=document['capture_completed_at'], tzif_bytes=tzif_bytes,
        tzif_reference=artifacts['tzif'])
    exact(document['plan'], plan)
    merge_claims(sources, plan['source_reference_claims'])
    require(plan['diagnostics'] in ([], [{'reason': 'MULTIPLE_UNACCOUNTED_SESSIONS'}]),
            'Source revisions, missing prefix or asymmetric dates block gap extension')
    dates = plan['source_evidence']['QQQ']['new_session_dates']
    exact(dates, plan['source_evidence']['SPY']['new_session_dates'])
    expected_counts = {
        'status': plan['status'], 'parent_typed_row_count': len(days),
        'parent_observed_count': sum(row['kind'] != 'MISSED_OBSERVATION'
                                     for row in history['known_typed_rows']),
        'parent_gap_count': sum(row['kind'] == 'MISSED_OBSERVATION'
                                for row in history['known_typed_rows']),
        'candidate_session': plan['candidate_session'], 'diagnostic_count': len(plan['diagnostics']),
        'snapshot_counts': {ticker: plan['source_evidence'][ticker]['original_row_count']
                            for ticker in ('QQQ', 'SPY')},
    }
    exact(audit['counts'], expected_counts)
    started = capture_core.utc(plan['capture_started_at'])
    completed = capture_core.utc(plan['capture_completed_at'])
    zone = ZoneInfo.from_file(BytesIO(tzif_bytes), key='America/New_York')
    require(started >= conservative_timing(days[-1], zone)[0], 'Clock precedes parent close')
    gaps, pending, unfinished = [], [], []
    for index, session in enumerate(dates):
        close, deadline = conservative_timing(session, zone)
        item = {
            'session': session, 'conservative_close_utc': close.isoformat(),
            'conservative_next_weekday_open_utc': deadline.isoformat(),
            'capture_started_at_utc': started.isoformat(),
            'capture_completed_at_utc': completed.isoformat(),
            'source_session_pointer_by_ticker': {
                ticker: '/plan/source_evidence/' + ticker + '/new_session_dates/' + str(index)
                for ticker in ('QQQ', 'SPY')},
            'counts_as_observed_session': False, 'consumes_month_first_opportunity': False,
            'decision_eligible': False,
        }
        if started < close:
            item['classification'] = 'SOURCE_ROW_NOT_COMPLETED_AT_CAPTURE_START'
            unfinished.append(item)
        elif started >= deadline and completed >= deadline:
            item['classification'] = 'MISSED_CONSERVATIVE_NEXT_OPEN_DEADLINE'
            gaps.append(item)
        else:
            item['classification'] = 'DEADLINE_NOT_PASSED_FOR_ENTIRE_CAPTURE_INTERVAL'
            pending.append(item)
    require(len(pending) <= 1 and (not pending or pending[0]['session'] == dates[-1]),
            'Only latest source session may remain completed and pending')
    original = deepcopy(history['known_typed_rows'])
    rows = deepcopy(original)
    for item in gaps:
        index = dates.index(item['session'])
        rows.append({
            'sequence': len(rows) + 1, 'session': item['session'],
            'kind': 'MISSED_OBSERVATION', 'seal_status': 'NOT_ATTEMPTED',
            'evidence_reference': dict(capture['reference'],
                json_pointer='/plan/source_evidence/QQQ/new_session_dates/' + str(index)),
        })
    require([row['session'] for row in rows] == sorted(set(row['session'] for row in rows)),
            'Gap rows cannot rewrite or duplicate historical dates')
    last_observed = next(row['session'] for row in reversed(original)
                         if row['kind'] != 'MISSED_OBSERVATION')
    return {
        'schema': SCHEMA, 'policy_id': POLICY,
        'status': 'GAP_EXTENSION_RESEARCH_ONLY' if gaps else 'NO_EXPIRED_SESSION_TO_APPEND',
        'supported_parent_schema': 'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2',
        'old_v2_capture_writer_reader_compatible': False,
        'future_actual_observation_requires_new_v3_consumers': True,
        'parent_history_reference': deepcopy(parent['reference']),
        'parent_publication_reference': deepcopy(parent['publication_reference']),
        'parent_readback_reference': deepcopy(parent['readback_reference']),
        'capture_reference': deepcopy(capture['reference']),
        'capture_publication_reference': deepcopy(capture['publication_reference']),
        'capture_readback_reference': deepcopy(capture['readback_reference']),
        'genesis_preserved': deepcopy(history['genesis_preserved']),
        'known_typed_rows': rows, 'known_typed_rows_preserved': original,
        'observations': deepcopy(history['observations']),
        'parent_attempt_inventory': deepcopy(history['parent_attempt_inventory']),
        'baseline_references': deepcopy(history['baseline_references']),
        'baseline_role': 'LAST_ACTUAL_OBSERVATION_BASELINE_NOT_LAST_ACCOUNTED',
        'captured_source_references': {ticker: deepcopy(artifacts[ticker]) for ticker in ('QQQ', 'SPY')},
        'captured_source_role': 'FULL_CAPTURE_MAY_INCLUDE_PENDING_NOT_EXACT_ACCOUNTED_BASELINE',
        'captured_sources_are_exact_accounted_prefix': False,
        'first_actual_observed_session_by_month': deepcopy(months),
        'last_observed_session': last_observed, 'last_accounted_session': rows[-1]['session'],
        'observation_count': history['observation_count'], 'new_observation_count': 0,
        'parent_typed_row_count': len(original), 'typed_row_count': len(rows),
        'new_missed_observation_count': len(gaps), 'gap_classifications': gaps,
        'pending_source_sessions': pending, 'excluded_not_completed_source_sessions': unfinished,
        'capture_started_at': plan['capture_started_at'], 'capture_completed_at': plan['capture_completed_at'],
        'tzif_reference': deepcopy(artifacts['tzif']),
        'timing_semantics': 'CALLER_BOUND_TZIF_REGULAR_CLOSE_AND_NEXT_WEEKDAY_OPEN_NOT_EXCHANGE_CALENDAR',
        'source_hashes': deepcopy(sources), 'source_reference_claims': deepcopy(sources),
        'dependency_sha256': deepcopy(DEPENDENCY_SHA256),
        'authentication_role': 'STRUCTURAL_REPLAY_ONLY_EXTERNALLY_BOUND_EVIDENCE_NOT_IO_AUTHENTICATION',
        'raw_source_bytes_embedded': False, **FLAGS,
    }
