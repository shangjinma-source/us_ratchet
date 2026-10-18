"""Independent CSV prefix/evidence reconstruction, with no producer imports or IO.

The caller must obtain accounted dates from separately verified history and
timing. This checker preserves all original bytes and grants no authenticity.
"""
from copy import deepcopy
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re

FIELDS = ('Date', 'Open', 'High', 'Low', 'Close', 'Volume')
MAX_BYTES = 8_000_000
MAX_PHYSICAL_LINES = 100000
MAX_DATA_ROWS = 20000
FLAGS = dict.fromkeys((
    'source_authenticity_verified', 'clock_authenticity_verified',
    'point_in_time_verified', 'observation_created', 'decision_eligible',
    'candidate_seal_allowed', 'cohort_registration_allowed',
    'future_independent_oos', 'promotion_allowed', 'live_mutation_allowed',
    'filesystem_attempt_inventory_authenticated', 'network_capture_performed',
    'timeliness_verified', 'exchange_calendar_verified',
), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def reconstruct_accounted_prefix(*, source_bytes, source_reference, accounted_sessions, scope_start):
    """Derive original prefix and complete V1 evidence independently of producer."""
    require(type(source_bytes) is bytes and 0 < len(source_bytes) <= MAX_BYTES,
            'Bounded original CSV bytes')
    require(type(source_reference) is dict and set(source_reference) == {'path', 'sha256'},
            'Exact full source reference')
    path, claimed = source_reference['path'], source_reference['sha256']
    require(type(path) is str and path and path.strip() == path and '\x00' not in path,
            'Explicit full source path')
    require(type(claimed) is str and re.fullmatch('[0-9a-f]{64}', claimed) is not None and
            sha256(source_bytes).hexdigest() == claimed, 'Full original source SHA')
    require(type(accounted_sessions) is list and accounted_sessions, 'Nonempty accounted dates')
    previous = ''
    for session in accounted_sessions:
        require(type(session) is str, 'Accounted date string')
        day = date.fromisoformat(session)
        require(day.isoformat() == session and day.weekday() < 5 and session > previous,
                'Canonical unique ordered accounted weekdays')
        previous = session
    require(scope_start == accounted_sessions[0], 'Scope from first accounted date')

    # Feed raw physical lines to the CSV parser while tracking the exact byte
    # cursor. Unlike a decoded/re-serialized CSV, this retains CR, BOM and blanks.
    cursor = 0
    line_count = 0

    def physical_lines():
        nonlocal cursor, line_count
        while cursor < len(source_bytes):
            require(line_count < MAX_PHYSICAL_LINES, 'Physical CSV line bound exceeded')
            start = cursor
            while cursor < len(source_bytes) and source_bytes[cursor] not in (10, 13):
                cursor += 1
            if cursor < len(source_bytes):
                first = source_bytes[cursor]
                cursor += 1
                if first == 13 and cursor < len(source_bytes) and source_bytes[cursor] == 10:
                    cursor += 1
            line_count += 1
            yield source_bytes[start:cursor].decode('utf-8-sig' if line_count == 1 else 'utf-8')

    reader = csv.reader(physical_lines(), strict=True)
    records, excluded, included, diagnostics = [], [], [], []
    previous = ''
    suffix_start = None
    retained_count = None
    try:
        require(next(reader) == list(FIELDS), 'Exact complete CSV header')
        while True:
            record_start = cursor
            try:
                cells = next(reader)
            except StopIteration:
                break
            if not cells:
                continue
            require(len(records) < MAX_DATA_ROWS and len(cells) == len(FIELDS) and
                    all(type(cell) is str and cell and cell.strip() == cell for cell in cells),
                    'Bounded complete canonical CSV record')
            session = cells[0]
            day = date.fromisoformat(session)
            require(day.isoformat() == session and day.weekday() < 5 and session > previous,
                    'Original unique ordered weekday dates')
            previous = session
            values = {}
            for field, text in zip(FIELDS[1:], cells[1:]):
                require(len(text) <= 100, 'Numeric text bound')
                value = Decimal(text)
                require(value.is_finite() and len(value.as_tuple().digits) <= 50 and
                        -50 <= value.as_tuple().exponent <= 50 and
                        (value >= 0 if field == 'Volume' else value > 0), 'Bounded positive OHLCV')
                values[field] = value
            violations = [name for left, right, name in (
                ('Low', 'Open', 'LOW_EXCEEDS_OPEN'),
                ('Low', 'Close', 'LOW_EXCEEDS_CLOSE'),
                ('Open', 'High', 'HIGH_BELOW_OPEN'),
                ('Close', 'High', 'HIGH_BELOW_CLOSE'),
                ('Low', 'High', 'LOW_EXCEEDS_HIGH'),
            ) if values[left] > values[right]]
            in_scope = session >= scope_start
            require(not in_scope or not violations, 'Required-scope OHLC bounds')
            index = len(records)
            row = dict(zip(FIELDS, cells))
            records.append(dict(original_data_row_index=index, session=session,
                                raw_csv_row=row, included_in_scoped_csv=in_scope))
            (included if in_scope else excluded).append(index)
            if violations:
                diagnostics.append(dict(original_data_row_index=index, session=session,
                    raw_csv_row=deepcopy(row), violations=violations,
                    role='OUTSIDE_FRONTIER_SCOPE_DIAGNOSTIC_NOT_EXECUTION_PRICE'))
            if in_scope:
                scope_index = len(included) - 1
                if scope_index < len(accounted_sessions):
                    require(session == accounted_sessions[scope_index], 'Complete accounted scope without holes')
                elif suffix_start is None:
                    suffix_start, retained_count = record_start, index
    except (csv.Error, StopIteration, InvalidOperation, UnicodeError) as error:
        raise ValueError('Invalid original complete CSV') from error
    require(len(included) >= len(accounted_sessions), 'Complete accounted dates present')
    stop = len(source_bytes) if suffix_start is None else suffix_start
    retained_count = len(records) if retained_count is None else retained_count
    prefix = source_bytes[:stop]
    evidence = dict(
        schema='ACCOUNTED_SOURCE_BYTE_PREFIX_EVIDENCE_V1',
        full_source_reference=deepcopy(source_reference), full_source_byte_count=len(source_bytes),
        prefix_sha256=sha256(prefix).hexdigest(), prefix_byte_count=len(prefix),
        byte_start=0, byte_stop=stop, scope_start=scope_start,
        accounted_sessions=deepcopy(accounted_sessions),
        suffix_sessions=[records[index]['session'] for index in included[len(accounted_sessions):]],
        original_row_count=len(records), retained_original_row_count=retained_count,
        accounted_original_row_indexes=included[:len(accounted_sessions)],
        suffix_original_row_indexes=included[len(accounted_sessions):],
        excluded_before_scope_original_row_indexes=excluded,
        excluded_before_scope_rows=[deepcopy(records[index]) for index in excluded],
        excluded_before_scope_ohlc_diagnostics=diagnostics,
        prefix_selection='COMPLETE_ACCOUNTED_SESSION_PREFIX_NOT_PRICE_OR_TIMELINESS_SELECTED',
        byte_span_semantics='ZERO_BASED_START_INCLUSIVE_STOP_EXCLUSIVE_ORIGINAL_BYTES',
        prefix_is_original_initial_byte_range=True, csv_reserialized=False,
        full_source_bytes_embedded=False, prefix_bytes_embedded=False,
        dependency_sha256=dict(
            scoped='9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee',
            base='30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'),
        authentication_role='SUPPLIED_BYTES_DERIVATION_NOT_EXTERNAL_SOURCE_OR_CLOCK_AUTHENTICATION',
        **FLAGS)
    return prefix, evidence


def verify_accounted_prefix(*, prefix_bytes, evidence, **arguments):
    """Check all prefix bytes and evidence fields; returns no authority flags."""
    expected_prefix, expected_evidence = reconstruct_accounted_prefix(**arguments)
    require(type(prefix_bytes) is bytes and prefix_bytes == expected_prefix,
            'Exact original prefix byte range')
    require(encode(evidence) == encode(expected_evidence), 'Complete independently reconstructed prefix evidence')
    return dict(schema='INDEPENDENT_ACCOUNTED_SOURCE_PREFIX_CHECK_V1',
                prefix_byte_count=len(expected_prefix), original_row_count=expected_evidence['original_row_count'],
                producer_prefix_core_called=False, producer_scoped_parser_called=False,
                source_bytes_verified_against_supplied_sha=True, **FLAGS)
