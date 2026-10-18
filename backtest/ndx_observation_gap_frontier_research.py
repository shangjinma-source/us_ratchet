"""Structural cursor planning from sealed evidence, never observation recovery.

The caller authenticates source bytes. No old calendar verifier, gap append,
ledger validator, clock classifier, seal, or generator is invoked here.
"""
from datetime import date

SCHEMA = 'OBSERVATION_GAP_FRONTIER_RESEARCH_V1'
LEDGER_SCHEMA = 'OBSERVATION_GAP_EVIDENCE_LEDGER_V1'
MAX_DATES = 10000
FALSE_FIELDS = (
    'observed_session_added', 'fresh_observation', 'decision_eligible',
    'candidate_seal_allowed', 'cohort_registration_allowed',
    'first_observed_session_of_month', 'historical_timeliness_verified',
    'future_timeliness_granted', 'canonical_calendar_append_allowed',
    'point_in_time_verified', 'promotion_allowed', 'live_mutation_allowed',
    'source_bytes_verified', 'system_clock_verified', 'oos_recovery_completed')
INCREMENTS = ('observed_session_increment', 'fresh_session_increment',
              'seal_increment', 'cohort_increment')


def require(value, message):
    if not value:
        raise ValueError(message)


def dates(values, label, *, nonempty=True):
    require(type(values) is list and len(values) <= MAX_DATES and
            (bool(values) or not nonempty), label+' bounded date list required')
    for value in values:
        require(type(value) is str, label+' canonical date required')
        parsed = date.fromisoformat(value)
        require(parsed.isoformat() == value and parsed.weekday() < 5, label+' canonical weekday required')
    require(values == sorted(set(values)), label+' unique ascending dates required')


def false_fields(value):
    require(type(value) is dict, 'Evidence mapping required')
    for key in FALSE_FIELDS:
        require(value.get(key) is False, 'Evidence permission changed: '+key)


def prepare_observation_frontier(*, parent_session_dates, gap_ledger,
                                 common_source_session_dates):
    """Plan a full-date cursor; newly encountered dates have no eligibility.

    Parent dates retain only their supplied observed-calendar role. Neither
    historical parent eligibility nor gap hash integrity is re-certified.
    """
    dates(parent_session_dates, 'Parent')
    dates(common_source_session_dates, 'Source')
    false_fields(gap_ledger)
    require(gap_ledger.get('schema') == LEDGER_SCHEMA, 'Gap ledger schema')
    for key in INCREMENTS:
        require(type(gap_ledger.get(key)) is int and gap_ledger[key] == 0, 'Gap increment must be integer zero')
    binding = gap_ledger['parent_binding']
    require(type(binding) is dict and type(binding.get('session_count')) is int and
            binding['session_count'] == len(parent_session_dates), 'Parent session count mismatch')
    require(type(binding.get('event_count')) is int and binding['event_count'] >= len(parent_session_dates), 'Parent event count')
    require(binding.get('last_session') == parent_session_dates[-1] and
            gap_ledger.get('old_last_observed_session_unchanged') == parent_session_dates[-1], 'Parent last session mismatch')
    events = gap_ledger.get('events')
    require(type(events) is list and len(events) <= MAX_DATES, 'Gap events list')
    require(type(gap_ledger.get('missed_observation_count')) is int and
            gap_ledger['missed_observation_count'] == len(events), 'Gap event count mismatch')
    gap_dates = []
    for index, event in enumerate(events):
        false_fields(event)
        require(event.get('schema') == 'MISSED_OBSERVATION_EVIDENCE_EVENT_V1' and
                event.get('event_type') == 'MISSED_OBSERVATION', 'Not missed-observation evidence')
        require(type(event.get('event_sequence')) is int and
                event['event_sequence'] == binding['event_count']+index+1, 'Gap sequence mismatch')
        gap_dates.append(event['session'])
    dates(gap_dates, 'Gap', nonempty=False)
    require(not gap_dates or gap_dates[0] > parent_session_dates[-1], 'Gap overlaps parent')
    covered = parent_session_dates + gap_dates
    source = [value for value in common_source_session_dates if value >= parent_session_dates[0]]
    require(source[:len(covered)] == covered, 'Source must preserve complete parent-plus-gap prefix')
    rows = [{'session': value, 'kind': 'SEALED_PARENT_OBSERVED_SESSION',
             'parent_session_index': index, 'eligibility_reverified': False}
            for index, value in enumerate(parent_session_dates)]
    rows += [{'session': event['session'], 'kind': 'MISSED_OBSERVATION',
              'gap_event_index': index, 'gap_event_sha256': event['event_sha256'],
              'counts_as_observed_session': False, 'decision_eligible': False}
             for index, event in enumerate(events)]
    return {'schema': SCHEMA, 'last_observed_session': parent_session_dates[-1],
        'last_accounted_gap_session': gap_dates[-1] if gap_dates else None,
        'last_accounted_session': covered[-1], 'known_accounted_rows': rows,
        'parent_observed_session_count': len(parent_session_dates),
        'accounted_gap_count': len(gap_dates),
        'unaccounted_source_dates': source[len(covered):],
        'excluded_source_dates_before_parent_start': [value for value in common_source_session_dates if value < parent_session_dates[0]],
        'month_first_semantics': 'UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE',
        'unaccounted_dates_require_clock_price_and_revision_review': True,
        'gap_hash_chain_reverified': False, 'parent_calendar_reverified': False,
        'scope': 'CURSOR_PLANNING_ONLY_NOT_OOS_RECOVERY',
        **{key: 0 for key in INCREMENTS}, **{key: False for key in FALSE_FIELDS}}
