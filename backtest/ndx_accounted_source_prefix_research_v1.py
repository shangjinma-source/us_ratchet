"""Derive an exact initial byte range of a supplied CSV; no IO or observation.

The caller chooses dates from independently checked history and timing evidence.
This module checks that those dates form the complete in-scope initial range.
It neither chooses expired sessions nor authenticates the supplied source.
"""
from copy import deepcopy
import csv
from datetime import date
from hashlib import sha256
import io
import re

from backtest import ndx_forward_source_capture_scoped_research as scoped_parser

SCHEMA = 'ACCOUNTED_SOURCE_BYTE_PREFIX_EVIDENCE_V1'
SCOPED_PARSER_SHA256 = '9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee'
BASE_PARSER_SHA256 = '30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'
MAX_PHYSICAL_LINES = 100000
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


def _record_spans(raw, metadata):
    """Map logical CSV records to original byte ranges, preserving all newlines."""
    ends = []
    for match in re.finditer(rb'\r\n|\r|\n', raw):
        require(len(ends) < MAX_PHYSICAL_LINES, 'Physical CSV line bound exceeded')
        ends.append(match.end())
    if not ends or ends[-1] != len(raw):
        require(len(ends) < MAX_PHYSICAL_LINES, 'Physical CSV line bound exceeded')
        ends.append(len(raw))
    reader = csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
    try:
        require(next(reader) == list(scoped_parser.FIELDS), 'Exact original CSV header')
        previous_line_count = reader.line_num
        spans = []
        for values in reader:
            start = ends[previous_line_count - 1] if previous_line_count else 0
            stop = ends[reader.line_num - 1]
            previous_line_count = reader.line_num
            if not values:
                continue
            index = len(spans)
            require(index < len(metadata['original_rows']), 'CSV parser row disagreement')
            original = metadata['original_rows'][index]['raw_csv_row']
            require(values == [original[field] for field in scoped_parser.FIELDS],
                    'CSV parser record disagreement')
            spans.append((start, stop))
    except (csv.Error, StopIteration) as error:
        raise ValueError('Invalid complete CSV record') from error
    require(len(spans) == metadata['original_row_count'], 'Complete CSV record mapping')
    return spans


def derive_accounted_prefix(*, source_bytes, source_reference, accounted_sessions, scope_start):
    """Return (original-prefix bytes, provenance declarations), without writing.

    References to the saved prefix are added by a later create-only IO adapter.
    Prefix SHA and size can therefore be derived before any artifact is named.
    """
    require(type(source_reference) is dict and set(source_reference) == {'path', 'sha256'},
            'Exact full source reference')
    require(type(source_reference['path']) is str and source_reference['path'] and
            source_reference['path'].strip() == source_reference['path'] and
            '\x00' not in source_reference['path'], 'Full source path')
    require(type(source_reference['sha256']) is str and
            re.fullmatch('[0-9a-f]{64}', source_reference['sha256']), 'Canonical full source SHA')
    require(type(source_bytes) is bytes and 0 < len(source_bytes) <= scoped_parser.MAX_BYTES,
            'Bounded full source bytes')
    require(sha256(source_bytes).hexdigest() == source_reference['sha256'], 'Full source bytes SHA')
    require(type(accounted_sessions) is list and accounted_sessions, 'Nonempty accounted sessions')
    previous = ''
    for session in accounted_sessions:
        require(type(session) is str, 'Accounted session string')
        parsed = date.fromisoformat(session)
        require(parsed.isoformat() == session and parsed.weekday() < 5 and session > previous,
                'Canonical strictly ordered accounted weekday sessions')
        previous = session
    require(scope_start == accounted_sessions[0], 'Scope comes from first accounted session')
    _, metadata = scoped_parser.scoped_csv(source_bytes, scope_start)
    included = metadata['included_original_row_indexes']
    source_sessions = [metadata['original_rows'][index]['session'] for index in included]
    require(source_sessions[:len(accounted_sessions)] == accounted_sessions,
            'Accounted sessions must be complete initial source scope without holes')
    spans = _record_spans(source_bytes, metadata)
    suffix_indexes = included[len(accounted_sessions):]
    # Include pre-scope records and all intervening blank lines verbatim. When
    # there is no suffix, retain every byte, including trailing blank lines.
    stop = spans[suffix_indexes[0]][0] if suffix_indexes else len(source_bytes)
    prefix = source_bytes[:stop]
    _, prefix_metadata = scoped_parser.scoped_csv(prefix, scope_start)
    prefix_dates = [prefix_metadata['original_rows'][index]['session']
                    for index in prefix_metadata['included_original_row_indexes']]
    require(prefix_dates == accounted_sessions, 'Derived prefix exact accounted scope')
    require(prefix_metadata['original_rows'] ==
            metadata['original_rows'][:prefix_metadata['original_row_count']],
            'Derived prefix preserves original records')
    excluded = metadata['excluded_original_row_indexes']
    evidence = dict(
        schema=SCHEMA, full_source_reference=deepcopy(source_reference),
        full_source_byte_count=len(source_bytes), prefix_sha256=sha256(prefix).hexdigest(),
        prefix_byte_count=len(prefix), byte_start=0, byte_stop=stop,
        scope_start=scope_start, accounted_sessions=deepcopy(accounted_sessions),
        suffix_sessions=source_sessions[len(accounted_sessions):],
        original_row_count=metadata['original_row_count'],
        retained_original_row_count=prefix_metadata['original_row_count'],
        accounted_original_row_indexes=included[:len(accounted_sessions)],
        suffix_original_row_indexes=suffix_indexes,
        excluded_before_scope_original_row_indexes=excluded,
        excluded_before_scope_rows=[deepcopy(metadata['original_rows'][index]) for index in excluded],
        excluded_before_scope_ohlc_diagnostics=deepcopy(metadata['excluded_before_scope_ohlc_diagnostics']),
        prefix_selection='COMPLETE_ACCOUNTED_SESSION_PREFIX_NOT_PRICE_OR_TIMELINESS_SELECTED',
        byte_span_semantics='ZERO_BASED_START_INCLUSIVE_STOP_EXCLUSIVE_ORIGINAL_BYTES',
        prefix_is_original_initial_byte_range=True, csv_reserialized=False,
        full_source_bytes_embedded=False, prefix_bytes_embedded=False,
        dependency_sha256=dict(scoped=SCOPED_PARSER_SHA256, base=BASE_PARSER_SHA256),
        authentication_role='SUPPLIED_BYTES_DERIVATION_NOT_EXTERNAL_SOURCE_OR_CLOCK_AUTHENTICATION',
        **FLAGS,
    )
    return prefix, evidence
