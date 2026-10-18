"""Pure gap extension preserving full capture, pending tail and byte prefixes.

All references, bytes and timestamps are supplied declarations. A later IO
publisher and independent reader must bind the actual parent/capture receipts,
freeze this dependency closure and independently verify every saved byte.
This module does not execute capture, write files or create observations.
"""
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from zoneinfo import ZoneInfo

from backtest import ndx_accounted_source_prefix_research_v1 as prefix_core
from backtest import ndx_forward_source_capture_scoped_research as scoped_parser
from backtest import ndx_prospective_history_parent_view_research_v5 as parent_view
from backtest import ndx_prospective_observation_parent_history_research as compact


TICKERS = ('QQQ', 'SPY')
ROLES = ('reference', 'publication_reference', 'readback_reference', 'reader_reference')
FLAGS = dict.fromkeys((*parent_view.legacy.WRAPPER_FALSE, *compact.FLAGS), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def utc(value):
    require(type(value) is str, 'Explicit UTC timestamp')
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0),
            'Explicit zero-offset UTC timestamp')
    return parsed.astimezone(timezone.utc)


def conservative_timing(session, zone):
    day = datetime.fromisoformat(session).date()
    close = datetime.combine(day, time(16), zone).astimezone(timezone.utc)
    following = day + timedelta(days=1)
    while following.weekday() >= 5:
        following += timedelta(days=1)
    deadline = datetime.combine(following, time(9, 30), zone).astimezone(timezone.utc)
    return close, deadline


def scope_dates(raw, scope_start):
    _, metadata = scoped_parser.scoped_csv(raw, scope_start)
    dates = [metadata['original_rows'][index]['session']
             for index in metadata['included_original_row_indexes']]
    return dates, metadata


def prefix_evidence_bytes(evidence):
    """Canonical bytes for the separately saved complete derivation evidence."""
    return compact.encoded(evidence) + b'\n'


def prefix_evidence_summary(evidence):
    """Keep dates/indexes and digest large row lists, which remain in the artifact."""
    result = deepcopy(evidence)
    for key in ('excluded_before_scope_rows', 'excluded_before_scope_ohlc_diagnostics'):
        values = result.pop(key)
        result[key + '_count'] = len(values)
        result[key + '_sha256'] = sha256(compact.encoded(values)).hexdigest()
    return result


def extend_gap_history(*, parent, capture_references, source_bytes, source_references,
                       accounted_baseline_bytes, actual_baseline_bytes,
                       prefix_references, prefix_evidence_references,
                       capture_started_at, capture_completed_at,
                       tzif_bytes, tzif_reference):
    """Append only expired source dates; retain unconsumed dates and full bytes.

    capture_references must come from a genuinely independently read-back
    capture. This pure function checks their shape, not the external receipt;
    the IO adapter must reconstruct that capture and bind its source/time/parent
    associations before consuming this result. Prefix references are caller
    supplied saved-artifact declarations checked against deterministic bytes.
    """
    view = parent_view.inspect_parent_history_v5(parent)
    known = deepcopy(view['known_typed_rows'])
    days = [row['session'] for row in known]
    prior_captured_days = days + [item['session'] for item in
        view['pending_source_sessions'] + view['excluded_not_completed_source_sessions']]
    sources = deepcopy(view['source_hashes'])
    require(type(capture_references) is dict and set(capture_references) == set(ROLES),
            'Four genuine capture reference roles')
    for reference in capture_references.values():
        compact.ref(reference, sources)
    for mapping in (source_bytes, source_references, accounted_baseline_bytes,
                    actual_baseline_bytes, prefix_references, prefix_evidence_references):
        require(type(mapping) is dict and set(mapping) == set(TICKERS), 'Exact source pair')
    started, completed = utc(capture_started_at), utc(capture_completed_at)
    require(started <= completed, 'Nonreversed capture interval')
    previous_suffix = view['pending_source_sessions'] + view['excluded_not_completed_source_sessions']
    require(all(started >= utc(item['capture_completed_at_utc']) for item in previous_suffix),
            'New capture clock cannot precede previously captured unconsumed sessions')
    compact.ref(tzif_reference, sources)
    require(tzif_reference['sha256'] == view['tzif_reference']['sha256'], 'Parent TZif binding')
    require(type(tzif_bytes) is bytes and 0 < len(tzif_bytes) <= 100000 and
            sha256(tzif_bytes).hexdigest() == tzif_reference['sha256'], 'Bounded exact TZif bytes')
    zone = ZoneInfo.from_file(BytesIO(tzif_bytes), key='America/New_York')
    require(started >= conservative_timing(days[-1], zone)[0], 'Capture precedes accounted close')
    source_evidence, new_dates = {}, {}
    for ticker in TICKERS:
        current, old, actual = (mapping[ticker] for mapping in
                                (source_bytes, accounted_baseline_bytes, actual_baseline_bytes))
        for raw, reference in ((current, source_references[ticker]),
                               (old, view['accounted_baseline_references'][ticker]),
                               (actual, view['baseline_references'][ticker])):
            compact.ref(reference, sources)
            require(type(raw) is bytes and sha256(raw).hexdigest() == reference['sha256'],
                    'Complete CSV bytes hash')
        old_dates, _ = scope_dates(old, days[0])
        actual_dates, _ = scope_dates(actual, days[0])
        current_dates, metadata = scope_dates(current, days[0])
        require(old_dates == days, 'Prior accounted baseline exact complete scope')
        require(actual_dates == [day for day in days if day <= view['last_observed_session']] and
                old.startswith(actual), 'Last actual full-byte baseline preserved')
        require(current.startswith(old) and current_dates[:len(days)] == days,
                'Full accounted raw prefix must not be revised or omitted')
        require(current_dates[:len(prior_captured_days)] == prior_captured_days,
                'Previously captured pending or unfinished session dates cannot disappear or change')
        new_dates[ticker] = current_dates[len(days):]
        source_evidence[ticker] = dict(
            source_reference=deepcopy(source_references[ticker]),
            accounted_baseline_reference=deepcopy(view['accounted_baseline_references'][ticker]),
            actual_baseline_reference=deepcopy(view['baseline_references'][ticker]),
            original_row_count=metadata['original_row_count'], source_session_dates=current_dates,
            new_session_dates=new_dates[ticker], full_accounted_bytes_prefix_matches=True,
            included_original_row_indexes=metadata['included_original_row_indexes'],
            excluded_original_row_indexes=metadata['excluded_original_row_indexes'],
            excluded_before_scope_ohlc_diagnostics=metadata['excluded_before_scope_ohlc_diagnostics'])
    require(new_dates['QQQ'] == new_dates['SPY'], 'Symmetric complete new session dates')
    gaps, pending, unfinished = [], [], []
    for index, session in enumerate(new_dates['QQQ']):
        close, deadline = conservative_timing(session, zone)
        item = dict(
            session=session, conservative_close_utc=close.isoformat(),
            conservative_next_weekday_open_utc=deadline.isoformat(),
            capture_started_at_utc=started.isoformat(), capture_completed_at_utc=completed.isoformat(),
            source_session_pointer_by_ticker={ticker: '/plan/source_evidence/' + ticker +
                '/new_session_dates/' + str(index) for ticker in TICKERS},
            counts_as_observed_session=False, consumes_month_first_opportunity=False,
            decision_eligible=False)
        if started < close:
            item['classification'] = 'SOURCE_ROW_NOT_COMPLETED_AT_CAPTURE_START'
            unfinished.append(item)
        elif started >= deadline and completed >= deadline:
            item['classification'] = 'MISSED_CONSERVATIVE_NEXT_OPEN_DEADLINE'
            gaps.append(item)
        else:
            item['classification'] = 'DEADLINE_NOT_PASSED_FOR_ENTIRE_CAPTURE_INTERVAL'
            pending.append(item)
    require([item['session'] for item in gaps + pending + unfinished] == new_dates['QQQ'],
            'Expired gap prefix followed only by complete pending/unfinished suffix')
    require(len(pending) <= 1, 'At most one completed pending session')
    for index, item in enumerate(gaps):
        known.append(dict(sequence=len(known) + 1, session=item['session'], kind='MISSED_OBSERVATION',
                          seal_status='NOT_ATTEMPTED', evidence_reference=dict(
                              capture_references['reference'],
                              json_pointer='/plan/source_evidence/QQQ/new_session_dates/' + str(index))))
    compact.exact(compact.rows_check(known, sources), view['first_actual_observed_session_by_month'],
                  'Gap extension cannot change first actual month opportunity')
    accounted_sessions = [row['session'] for row in known]
    prefix_evidence = {}
    for ticker in TICKERS:
        prefix, evidence = prefix_core.derive_accounted_prefix(
            source_bytes=source_bytes[ticker], source_reference=source_references[ticker],
            accounted_sessions=accounted_sessions, scope_start=days[0])
        compact.ref(prefix_references[ticker], sources)
        require(prefix_references[ticker]['sha256'] == evidence['prefix_sha256'] and
                prefix.startswith(accounted_baseline_bytes[ticker]), 'Saved prefix SHA and full prior bytes')
        compact.ref(prefix_evidence_references[ticker], sources)
        require(prefix_evidence_references[ticker]['sha256'] == sha256(prefix_evidence_bytes(evidence)).hexdigest(),
                'Complete separately saved prefix evidence SHA')
        prefix_evidence[ticker] = prefix_evidence_summary(evidence)
    return dict(
        schema=parent_view.GAP_SCHEMA,
        status='GAP_EXTENSION_RESEARCH_ONLY' if gaps else 'NO_EXPIRED_SESSION_TO_APPEND',
        policy_id=view['policy_id'],
        parent_references=deepcopy(view['parent_references']),
        capture_references=deepcopy(capture_references), parent_state_reference=deepcopy(parent['reference']),
        prior_state_preserved=parent_view.parent_state_for_gap(view),
        known_typed_rows=known, known_typed_rows_preserved=deepcopy(view['known_typed_rows']),
        observations=deepcopy(view['observations']),
        parent_attempt_inventory=deepcopy(view['parent_attempt_inventory']),
        first_actual_observed_session_by_month=deepcopy(view['first_actual_observed_session_by_month']),
        genesis_preserved=deepcopy(view['genesis_preserved']),
        baseline_references=deepcopy(view['baseline_references']), baseline_role=view['baseline_role'],
        full_capture_source_references=deepcopy(source_references),
        full_capture_source_role=parent_view.FULL_CAPTURE_ROLE,
        accounted_prefix_references=deepcopy(prefix_references), accounted_prefix_evidence=prefix_evidence,
        accounted_prefix_evidence_references=deepcopy(prefix_evidence_references),
        accounted_prefix_role=parent_view.ACCOUNTED_PREFIX_ROLE,
        source_evidence=source_evidence, gap_classifications=gaps, pending_source_sessions=pending,
        excluded_not_completed_source_sessions=unfinished,
        last_observed_session=view['last_observed_session'], last_accounted_session=known[-1]['session'],
        typed_row_count=len(known), parent_typed_row_count=view['typed_row_count'],
        parent_actual_observation_count=view['observation_count'], observation_count=view['observation_count'],
        gap_count=view['gap_count'] + len(gaps), new_observation_count=0,
        new_missed_observation_count=len(gaps), capture_started_at=started.isoformat(),
        capture_completed_at=completed.isoformat(), tzif_reference=deepcopy(tzif_reference),
        source_hashes=deepcopy(sources), source_reference_claims=deepcopy(sources),
        raw_source_bytes_embedded=False, **FLAGS)
