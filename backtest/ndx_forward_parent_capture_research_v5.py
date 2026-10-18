"""Pure V3/V4/V5 capture planning from a normalized audited parent view. Caller supplies bytes, references and clock.

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
from backtest import ndx_prospective_history_parent_view_research_v5 as parent_view

SCHEMA = 'FORWARD_PARENT_CAPTURE_PLAN_V5'
SCOPED_PARSER_SHA256 = '9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee'
PARSER_DEPENDENCY_SHA256 = '30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'
PARENT_VIEW_SHA256 = '32bcabfbc08a63607b650141f7295fc1ed12a3fdeeb081527c8b32d8cc250373'
LEGACY_VIEW_SHA256 = '06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'
COMPACT_HELPER_SHA256 = '1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'
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


def plan_parent_capture(*, parent, source_bytes, source_references,
                            accounted_baseline_bytes, actual_baseline_bytes,
                            capture_started_at, capture_completed_at, tzif_bytes, tzif_reference):
    h = parent_view.inspect_parent_history_v5(parent)
    days = [row['session'] for row in h['known_typed_rows']]
    previous_suffix = h['pending_source_sessions'] + h['excluded_not_completed_source_sessions']
    previously_captured_days = days + [item['session'] for item in previous_suffix]
    sources = deepcopy(h['source_hashes'])
    for value in (source_bytes, source_references, accounted_baseline_bytes, actual_baseline_bytes,
                  h['accounted_baseline_references'], h['baseline_references']):
        require(type(value) is dict and set(value) == set(TICKERS), 'Exact source pair')
    started, completed = utc(capture_started_at), utc(capture_completed_at)
    require(started <= completed, 'Capture clock reversal')
    require(all(started >= utc(item['capture_completed_at_utc']) for item in previous_suffix),
            'Capture clock precedes previously recorded unconsumed sources')
    merge(sources, tzif_reference)
    exact(tzif_reference['sha256'], h['tzif_reference']['sha256'], 'Parent TZif hash binding')
    require(type(tzif_bytes) is bytes and sha256(tzif_bytes).hexdigest() == tzif_reference['sha256'], 'TZif bytes hash')
    zone = ZoneInfo.from_file(BytesIO(tzif_bytes), key='America/New_York')
    close = lambda session: datetime.combine(day(session), time(16), zone).astimezone(timezone.utc)
    require(started >= close(days[-1]), 'Capture precedes accounted close')
    diagnostics, evidence, new_dates = [], {}, {}
    for ticker in TICKERS:
        old, actual, current = accounted_baseline_bytes[ticker], actual_baseline_bytes[ticker], source_bytes[ticker]
        for raw, ref in ((old, h['accounted_baseline_references'][ticker]),
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
        if previous_suffix and current_days[:len(previously_captured_days)] != previously_captured_days:
            diagnostics.append(dict(reason='PREVIOUSLY_CAPTURED_SOURCE_SESSIONS_WITHDRAWN_OR_CHANGED', ticker=ticker))
        new_dates[ticker] = current_days[len(days):] if current_days[:len(days)] == days else []
        evidence[ticker] = dict(source_reference=deepcopy(source_references[ticker]),
            accounted_baseline_reference=deepcopy(h['accounted_baseline_references'][ticker]),
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
        actual_parent_schema=h['parent_schema'],
        parent_full_capture_source_references=deepcopy(h['full_capture_source_references']),
        parent_pending_source_sessions=deepcopy(h['pending_source_sessions']),
        parent_excluded_not_completed_source_sessions=deepcopy(h['excluded_not_completed_source_sessions']),
        known_typed_rows=deepcopy(h['known_typed_rows']), observations=deepcopy(h['observations']),
        parent_attempt_inventory=deepcopy(h['parent_attempt_inventory']),
        first_actual_observed_session_by_month=deepcopy(h['first_actual_observed_session_by_month']),
        baseline_references=deepcopy(h['baseline_references']), baseline_role=h['baseline_role'],
        accounted_baseline_references=deepcopy(h['accounted_baseline_references']),
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
        dependency_sha256=dict(scoped=SCOPED_PARSER_SHA256, base=PARSER_DEPENDENCY_SHA256,
            parent_view=PARENT_VIEW_SHA256, legacy_view=LEGACY_VIEW_SHA256,
            compact_helpers=COMPACT_HELPER_SHA256), **FLAGS)
