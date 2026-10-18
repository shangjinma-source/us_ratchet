"""Independent V5 gap arithmetic from supplied evidence, without producer calls.

The IO reader supplies privately verified upstream parent, CSV and independent
prefix checkers. This function neither reads files nor authenticates receipts.
"""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import json
from zoneinfo import ZoneInfo

DEPENDENCY_SHA256 = dict(
    parent_view='32bcabfbc08a63607b650141f7295fc1ed12a3fdeeb081527c8b32d8cc250373',
    csv_reader='c9dbb1c15c12d84910842874d1800d09c73d90893b91d54865826bf240ef9787',
    independent_prefix='b66bf0824971a94d0ba4f7f65ae91b7f6ed898c1977503fcdd15bf1fe38473b5')
TICKERS = ('QQQ', 'SPY')
ROLES = ('reference', 'publication_reference', 'readback_reference', 'reader_reference')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def merge(sources, reference):
    require(type(reference) is dict and set(reference) == {'path', 'sha256'}, 'Exact immutable reference')
    path, digest = reference['path'], reference['sha256']
    require(type(path) is str and path and path == path.strip(), 'Explicit reference path')
    require(type(digest) is str and len(digest) == 64 and
            all(char in '0123456789abcdef' for char in digest), 'Nonpending canonical SHA')
    require(path not in sources or sources[path] == digest, 'Source reference conflict')
    sources[path] = digest


def utc(value):
    require(type(value) is str, 'UTC timestamp string')
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), 'Explicit zero-offset UTC')
    return parsed.astimezone(timezone.utc)


def session_timing(session, zone):
    day = date.fromisoformat(session)
    following = day + timedelta(days=1)
    while following.weekday() > 4:
        following += timedelta(days=1)
    return (datetime.combine(day, time(16), zone).astimezone(timezone.utc),
            datetime.combine(following, time(9, 30), zone).astimezone(timezone.utc))


def summary(evidence):
    result = deepcopy(evidence)
    for key in ('excluded_before_scope_rows', 'excluded_before_scope_ohlc_diagnostics'):
        values = result.pop(key)
        result[key + '_count'] = len(values)
        result[key + '_sha256'] = sha256(encode(values)).hexdigest()
    return result


def validate_typed_rows(rows, sources):
    require(type(rows) is list and 0 < len(rows) < 20000, 'Complete typed history bound')
    previous, pointers, months = '', set(), {}
    for index, row in enumerate(rows):
        require(type(row) is dict and set(row) == {'sequence', 'session', 'kind', 'evidence_reference', 'seal_status'}, 'Exact typed row')
        session = row['session']
        require(type(session) is str, 'Typed session string')
        day = date.fromisoformat(session)
        require(day.isoformat() == session and day.weekday() < 5 and session > previous, 'Typed chronological weekdays')
        require(type(row['sequence']) is int and row['sequence'] == index + 1, 'Typed exact sequence')
        require(row['kind'] in ('SEALED_PARENT_OBSERVED_SESSION', 'PROSPECTIVE_OBSERVED_SESSION', 'MISSED_OBSERVATION'), 'Typed kind')
        require(row['seal_status'] in ('NOT_ATTEMPTED', 'UNKNOWN', 'FAILED', 'SEALED') and
                (row['kind'] != 'MISSED_OBSERVATION' or row['seal_status'] == 'NOT_ATTEMPTED'), 'Typed seal state')
        reference = row['evidence_reference']
        require(type(reference) is dict and set(reference) == {'path', 'sha256', 'json_pointer'}, 'Typed evidence pointer')
        merge(sources, {key: reference[key] for key in ('path', 'sha256')})
        pointer = reference['json_pointer']
        require(type(pointer) is str and pointer.startswith('/') and len(pointer) > 1, 'Exact evidence pointer')
        identity = (reference['path'], reference['sha256'], pointer)
        require(identity not in pointers, 'Duplicate historical evidence pointer')
        pointers.add(identity)
        if row['kind'] != 'MISSED_OBSERVATION':
            months.setdefault(session[:7], session)
        previous = session
    return months


def reconstruct_gap_history(*, parent, capture_references, source_bytes, source_references,
        accounted_baseline_bytes, actual_baseline_bytes, prefix_references, prefix_evidence_references,
        capture_started_at, capture_completed_at, tzif_bytes, tzif_reference,
        parent_checker, csv_rows, prefix_checker):
    """Return the complete expected V5 history; verify supplied hashes, not IO."""
    view = parent_checker.inspect_parent_history_v5(parent)
    sources = deepcopy(view['source_hashes'])
    require(type(capture_references) is dict and set(capture_references) == set(ROLES), 'Four capture anchors')
    for reference in capture_references.values():
        merge(sources, reference)
    for values in (source_bytes, source_references, accounted_baseline_bytes, actual_baseline_bytes,
                   prefix_references, prefix_evidence_references):
        require(type(values) is dict and set(values) == set(TICKERS), 'Complete source pair')
    begin, end = utc(capture_started_at), utc(capture_completed_at)
    require(begin <= end, 'Nonreversed capture interval')
    tail = view['pending_source_sessions'] + view['excluded_not_completed_source_sessions']
    require(all(begin >= utc(item['capture_completed_at_utc']) for item in tail), 'Previously captured tail clock cannot regress')
    merge(sources, tzif_reference)
    require(tzif_reference['sha256'] == view['tzif_reference']['sha256'] and
            type(tzif_bytes) is bytes and 0 < len(tzif_bytes) <= 100000 and
            sha256(tzif_bytes).hexdigest() == tzif_reference['sha256'], 'Original bound TZif bytes')
    zone = ZoneInfo.from_file(BytesIO(tzif_bytes), key='America/New_York')
    known = deepcopy(view['known_typed_rows'])
    days = [row['session'] for row in known]
    require(begin >= session_timing(days[-1], zone)[0], 'Capture before accounted close')
    prior_dates = days + [item['session'] for item in tail]
    source_evidence, new_dates = {}, {}
    for ticker in TICKERS:
        current, old, actual = source_bytes[ticker], accounted_baseline_bytes[ticker], actual_baseline_bytes[ticker]
        for raw, reference in ((current, source_references[ticker]),
                (old, view['accounted_baseline_references'][ticker]), (actual, view['baseline_references'][ticker])):
            merge(sources, reference)
            require(type(raw) is bytes and sha256(raw).hexdigest() == reference['sha256'], 'Complete supplied CSV SHA')
        current_rows, issues = csv_rows(current, days[0])
        old_rows, _ = csv_rows(old, days[0])
        actual_rows, _ = csv_rows(actual, days[0])
        scoped_dates = lambda rows: [row['Date'] for row in rows if row['Date'] >= days[0]]
        current_dates = scoped_dates(current_rows)
        require(scoped_dates(old_rows) == days, 'Prior accounted dates exact')
        require(scoped_dates(actual_rows) == [day for day in days if day <= view['last_observed_session']] and
                old.startswith(actual), 'Last actual bytes and dates preserved')
        require(current.startswith(old) and current_dates[:len(days)] == days, 'Complete prior raw byte prefix preserved')
        require(current_dates[:len(prior_dates)] == prior_dates, 'Previously captured dates cannot be withdrawn')
        new_dates[ticker] = current_dates[len(days):]
        source_evidence[ticker] = dict(source_reference=deepcopy(source_references[ticker]),
            accounted_baseline_reference=deepcopy(view['accounted_baseline_references'][ticker]),
            actual_baseline_reference=deepcopy(view['baseline_references'][ticker]), original_row_count=len(current_rows),
            source_session_dates=current_dates, new_session_dates=new_dates[ticker], full_accounted_bytes_prefix_matches=True,
            included_original_row_indexes=[i for i, row in enumerate(current_rows) if row['Date'] >= days[0]],
            excluded_original_row_indexes=[i for i, row in enumerate(current_rows) if row['Date'] < days[0]],
            excluded_before_scope_ohlc_diagnostics=issues)
    require(new_dates['QQQ'] == new_dates['SPY'], 'Symmetric unconsumed dates')
    classes = [[], [], []]
    for index, session in enumerate(new_dates['QQQ']):
        close, deadline = session_timing(session, zone)
        group = 2 if begin < close else 0 if begin >= deadline and end >= deadline else 1
        classes[group].append(dict(session=session, conservative_close_utc=close.isoformat(),
            conservative_next_weekday_open_utc=deadline.isoformat(), capture_started_at_utc=begin.isoformat(),
            capture_completed_at_utc=end.isoformat(), source_session_pointer_by_ticker={ticker:
                '/plan/source_evidence/' + ticker + '/new_session_dates/' + str(index) for ticker in TICKERS},
            counts_as_observed_session=False, consumes_month_first_opportunity=False, decision_eligible=False,
            classification=('MISSED_CONSERVATIVE_NEXT_OPEN_DEADLINE',
                'DEADLINE_NOT_PASSED_FOR_ENTIRE_CAPTURE_INTERVAL', 'SOURCE_ROW_NOT_COMPLETED_AT_CAPTURE_START')[group]))
    gaps, pending, unfinished = classes
    require([item['session'] for group in classes for item in group] == new_dates['QQQ'] and len(pending) <= 1,
            'Expired prefix followed by pending and unfinished suffix')
    for index, item in enumerate(gaps):
        known.append(dict(sequence=len(known) + 1, session=item['session'], kind='MISSED_OBSERVATION',
            seal_status='NOT_ATTEMPTED', evidence_reference=dict(capture_references['reference'],
            json_pointer='/plan/source_evidence/QQQ/new_session_dates/' + str(index))))
    require(encode(validate_typed_rows(known, sources)) == encode(view['first_actual_observed_session_by_month']), 'Actual month coordinates preserved')
    accounted = [row['session'] for row in known]
    prefix_evidence = {}
    for ticker in TICKERS:
        prefix, evidence = prefix_checker.reconstruct_accounted_prefix(source_bytes=source_bytes[ticker],
            source_reference=source_references[ticker], accounted_sessions=accounted, scope_start=days[0])
        merge(sources, prefix_references[ticker]); merge(sources, prefix_evidence_references[ticker])
        require(prefix_references[ticker]['sha256'] == sha256(prefix).hexdigest() and
                prefix.startswith(accounted_baseline_bytes[ticker]), 'Saved prefix SHA and prior full bytes')
        require(prefix_evidence_references[ticker]['sha256'] == sha256(encode(evidence) + b'\n').hexdigest(), 'Full evidence artifact SHA')
        prefix_evidence[ticker] = summary(evidence)
    flags = dict.fromkeys(set(parent_checker.legacy.WRAPPER_FALSE) | set(parent_checker.legacy.compact.FLAGS), False)
    return dict(schema='PROSPECTIVE_GAP_EXTENSION_HISTORY_V5', status='GAP_EXTENSION_RESEARCH_ONLY' if gaps else 'NO_EXPIRED_SESSION_TO_APPEND',
        policy_id=view['policy_id'], parent_references=deepcopy(view['parent_references']), capture_references=deepcopy(capture_references),
        parent_state_reference=deepcopy(parent['reference']), prior_state_preserved=parent_checker.parent_state_for_gap(view),
        known_typed_rows=known, known_typed_rows_preserved=deepcopy(view['known_typed_rows']), observations=deepcopy(view['observations']),
        parent_attempt_inventory=deepcopy(view['parent_attempt_inventory']), first_actual_observed_session_by_month=deepcopy(view['first_actual_observed_session_by_month']),
        genesis_preserved=deepcopy(view['genesis_preserved']), baseline_references=deepcopy(view['baseline_references']), baseline_role=view['baseline_role'],
        full_capture_source_references=deepcopy(source_references), full_capture_source_role=parent_checker.FULL_CAPTURE_ROLE,
        accounted_prefix_references=deepcopy(prefix_references), accounted_prefix_evidence=prefix_evidence,
        accounted_prefix_evidence_references=deepcopy(prefix_evidence_references), accounted_prefix_role=parent_checker.ACCOUNTED_PREFIX_ROLE,
        source_evidence=source_evidence, gap_classifications=gaps, pending_source_sessions=pending, excluded_not_completed_source_sessions=unfinished,
        last_observed_session=view['last_observed_session'], last_accounted_session=known[-1]['session'], typed_row_count=len(known),
        parent_typed_row_count=view['typed_row_count'], parent_actual_observation_count=view['observation_count'], observation_count=view['observation_count'],
        gap_count=view['gap_count'] + len(gaps), new_observation_count=0, new_missed_observation_count=len(gaps),
        capture_started_at=begin.isoformat(), capture_completed_at=end.isoformat(), tzif_reference=deepcopy(tzif_reference),
        source_hashes=deepcopy(sources), source_reference_claims=deepcopy(sources), raw_source_bytes_embedded=False, **flags)
