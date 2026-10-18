"""Independent create-only V3 gap readback; never calls the publisher or new pure."""
import argparse
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
from types import ModuleType
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/prospective_gap_history_independent_readback_20261009_v3'
HISTORY = ROOT / 'data/cache/research/prospective_gap_history_20261009_v3'
PRODUCER = ROOT / 'scripts/ndx_prospective_gap_history_20261009_v3.py'
PRODUCER_SHA = 'a926d01a84284ea18a193d04f3f10522b64ef048179fab8929f93948826fe3a3'
HISTORY_SHA = '600d15deb7cdcbc74fb13337c279d31c910d9389088ebc8668ea650779fdfd8a'
PUBLICATION_SHA = '3ff2cf28d954e64ed7a21af6d8b7ed5465c7cf2fe5c6fd7d057cd43e4cddfe10'
PURE = ROOT / 'backtest/ndx_prospective_gap_history_research_v3.py'
PURE_SHA = '12690e619763ff32ff601d0d0f4071f41d7ecf5e921d19601c58ab5802ed5c63'
CAPTURE_READER = ROOT / 'scripts/ndx_variable_prefix_capture_independent_readback_20261003.py'
CAPTURE_READER_SHA = 'aed7b71289fb30473cedefda00c6377c0700bea115e5d99328c1c20dd4572dbe'
POLICY = 'FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
DEPENDENCIES = {
    'core': ('backtest/ndx_variable_prefix_capture_research.py', '9c76324fcbc8e5d57a1ef25566a59110acff32a58506c6d5b6947996e6c26039'),
    'scoped': ('backtest/ndx_forward_source_capture_scoped_research.py', '9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee'),
    'base': ('backtest/ndx_forward_source_capture_research.py', '30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'),
}
PARENT_BOUND = {
    'reference': ('data/cache/research/prospective_observation_parent_history_20261003_v1/history.json', 'bd0eb3bb1ed5a4103af964e4c2016caf8e5abf45caf799ffbf786642bc7a4a33'),
    'publication_reference': ('data/cache/research/prospective_observation_parent_history_20261003_v1/publication.json', '648f6937e7ff876a824bab96a654461b411dccd6b4c7a6a19217d0bdd09fbcf6'),
    'readback_reference': ('data/cache/research/prospective_observation_parent_history_independent_readback_20261003_v1/independent_readback.json', 'c6f9a113b1b5f00128befa74a415e6604012d47ac17eb7db2048dafa8a31a86a'),
    'reader_reference': ('scripts/ndx_prospective_observation_parent_history_independent_readback_20261003.py', '876094538679db3216f69cf3035101baf91498d5296512cbef4b2911486d7aef'),
}
CAPTURE_BOUND = {
    'reference': ('data/cache/research/variable_prefix_source_capture_20261003_v1/capture.json', '435c1129792aaec3a52c7d156a39f34cf594838e1d406a833ddd55dc86ae878e'),
    'publication_reference': ('data/cache/research/variable_prefix_source_capture_20261003_v1/publication.json', '16bd9eaf7da6e36eaa1b2d927e0749ea77c5f5885b5eddd28daa069f4171cadf'),
    'readback_reference': ('data/cache/research/variable_prefix_capture_independent_readback_20261003_v1/independent_readback.json', '20dbef63741bb9e75372fbec435ddaa6883f2ee54241d6d79536073526715e1d'),
    'reader_reference': ('scripts/ndx_variable_prefix_capture_independent_readback_20261003.py', CAPTURE_READER_SHA),
}
FALSE_FIELDS = (
    'source_authenticity_verified', 'parent_history_authenticated_by_this_module',
    'clock_authenticity_verified', 'timeliness_verified',
    'filesystem_attempt_inventory_authenticated', 'observation_created',
    'candidate_seal_allowed', 'cohort_registration_allowed', 'point_in_time_verified',
    'promotion_allowed', 'live_mutation_allowed', 'future_independent_oos',
    'production_generator_authorized', 'seal_event_created', 'partial_recovery_performed',
    'old_calendar_mutated', 'canonical_calendar_append_allowed', 'retrospective_backfill_allowed',
    'decision_eligible', 'exchange_holidays_and_early_closes_verified',
    'network_capture_performed', 'full_transitive_source_closure_reverified',
)
WRAPPER_FALSE = (
    'observation_created', 'candidate_seal_allowed', 'cohort_registration_allowed',
    'point_in_time_verified', 'promotion_allowed', 'future_independent_oos',
    'live_mutation_allowed', 'old_calendar_mutated', 'network_capture_performed',
    'source_authenticity_verified', 'clock_authenticity_verified',
    'filesystem_attempt_inventory_authenticated', 'full_transitive_source_closure_reverified',
)
PARENT_DOCUMENT_FALSE = (
    'source_authenticity_verified', 'filesystem_attempt_inventory_authenticated',
    'clock_authenticity_verified', 'candidate_seal_allowed', 'cohort_registration_allowed',
    'point_in_time_verified', 'promotion_allowed', 'live_mutation_allowed',
    'future_independent_oos', 'production_generator_authorized', 'seal_event_created',
    'partial_recovery_performed', 'old_calendar_mutated',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(left, right):
    require(encode(left) == encode(right), 'Independent exact value/type mismatch')


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON ' + value)))


def reference(path, sha256):
    require(type(path) is str and path and path.strip() == path, 'Exact reference path')
    require(type(sha256) is str and len(sha256) == 64 and
            all(char in '0123456789abcdef' for char in sha256), 'Pending immutable SHA')
    return {'path': path, 'sha256': sha256}


def merge(sources, item):
    require(type(item) is dict and set(item) == {'path', 'sha256'}, 'Exact reference fields')
    reference(item['path'], item['sha256'])
    require(item['path'] not in sources or sources[item['path']] == item['sha256'], 'Source conflict')
    sources[item['path']] = item['sha256']


def claims(sources, value):
    require(type(value) is dict, 'Source claim map')
    for path, sha256 in value.items():
        merge(sources, reference(path, sha256))


def flags(value, fields):
    for field in fields:
        require(value.get(field) is False, 'Strict false field: ' + field)


def utc(value):
    require(type(value) is str, 'UTC string')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), 'Explicit UTC timestamp')
    return parsed


def timing(session, zone):
    day = date.fromisoformat(session)
    require(day.isoformat() == session and day.weekday() < 5, 'Canonical weekday')
    close = datetime.combine(day, time(16), zone).astimezone(timezone.utc)
    following = day + timedelta(days=1)
    while following.weekday() >= 5:
        following += timedelta(days=1)
    return close, datetime.combine(following, time(9, 30), zone).astimezone(timezone.utc)


def reconstruct_history(*, parent, capture, source_bytes, baseline_bytes, tzif_bytes, checker):
    """Independent formula replay; checker is privately loaded fixed old readback code."""
    flags(parent['document'], PARENT_DOCUMENT_FALSE)
    days, months, sources = checker.inspect_parent(parent)
    original = parent['document']['known_typed_rows']
    parent_flags = set(FALSE_FIELDS) | set(checker.PURE_FALSE)
    for role in ('document', 'publication', 'readback'):
        flags(parent[role], parent_flags.intersection(parent[role]))
    pointers = set()
    for row in original:
        exact(sorted(row), sorted(('sequence', 'session', 'kind', 'seal_status', 'evidence_reference')))
        evidence = row['evidence_reference']
        exact(sorted(evidence), ['json_pointer', 'path', 'sha256'])
        pointer = evidence['json_pointer']
        require(type(pointer) is str and pointer.startswith('/') and len(pointer) > 1, 'Row pointer')
        key = (evidence['path'], evidence['sha256'], pointer)
        require(key not in pointers, 'Duplicate row pointer')
        pointers.add(key)
        merge(sources, {key: evidence[key] for key in ('path', 'sha256')})
    for role in ('reference', 'publication_reference', 'readback_reference', 'reader_reference'):
        merge(sources, capture[role])
    document, publication, audit = (capture[key] for key in ('document', 'publication', 'readback'))
    exact(document['schema'], 'SOURCE_BOUND_VARIABLE_PREFIX_CAPTURE_V1')
    exact(publication['schema'], 'VARIABLE_PREFIX_CAPTURE_PUBLICATION_V1')
    exact(publication['status'], 'PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION')
    exact(audit['schema'], 'VARIABLE_PREFIX_CAPTURE_INDEPENDENT_READBACK_V1')
    exact(audit['status'], 'PASS')
    for item in (publication, audit):
        exact(item['capture_reference'], capture['reference'])
    exact(audit['publication_reference'], capture['publication_reference'])
    exact(audit['reader_sha256'], capture['reader_reference']['sha256'])
    parent_refs = {key: parent[key] for key in PARENT_BOUND}
    exact(document['parent_references'], parent_refs)
    exact(audit['parent_references'], parent_refs)
    for item in (document, publication, audit):
        flags(item, checker.PURE_FALSE)
        claims(sources, item['source_hashes'])
    exact(document['source_hashes'], publication['source_hashes'])
    for path, sha256 in document['source_hashes'].items():
        exact(audit['source_hashes'][path], sha256)
    for role in ('reference', 'publication_reference', 'reader_reference'):
        item = capture[role]
        exact(audit['source_hashes'][item['path']], item['sha256'])
    require(document['clock_captured_by_runner'] is True and
            document['external_clock_attestation_verified'] is False and
            audit['external_clock_attestation_verified'] is False, 'Clock recording is not attestation')
    require(audit['producer_called'] is False and audit['plan_history_capture_called'] is False and
            audit['snapshot_bytes_verified'] is True, 'Independent old readback role')
    inputs, artifacts = document['input_references'], document['captured_artifacts']
    exact(sorted(inputs), ['base', 'core', 'scoped', 'tzif'])
    exact(sorted(artifacts), ['QQQ', 'SPY', 'tzif'])
    for key, (_, sha256) in DEPENDENCIES.items():
        exact(inputs[key]['sha256'], sha256)
    exact(inputs['tzif']['sha256'], artifacts['tzif']['sha256'])
    for item in (*inputs.values(), *artifacts.values(), *parent_refs.values()):
        exact(document['source_hashes'][item['path']], item['sha256'])
        merge(sources, item)
    plan = document['plan']
    counts = checker.inspect_plan(plan=plan, parent=parent, source_bytes=source_bytes,
        source_references={ticker: artifacts[ticker] for ticker in ('QQQ', 'SPY')},
        baseline_bytes=baseline_bytes, tzif_bytes=tzif_bytes, tzif_reference=artifacts['tzif'],
        start=document['capture_started_at'], end=document['capture_completed_at'])
    exact(audit['counts'], counts)
    claims(sources, plan['source_reference_claims'])
    require(plan['diagnostics'] in ([], [{'reason': 'MULTIPLE_UNACCOUNTED_SESSIONS'}]),
            'Source diagnostics block extension')
    dates = plan['source_evidence']['QQQ']['new_session_dates']
    exact(dates, plan['source_evidence']['SPY']['new_session_dates'])
    started, completed = utc(document['capture_started_at']), utc(document['capture_completed_at'])
    require(started <= completed, 'Clock reversal')
    zone = ZoneInfo.from_file(BytesIO(tzif_bytes), key='America/New_York')
    require(started >= timing(days[-1], zone)[0], 'Clock precedes parent close')
    missed, pending, unfinished = [], [], []
    for index, session in enumerate(dates):
        close, deadline = timing(session, zone)
        item = dict(session=session, conservative_close_utc=close.isoformat(),
            conservative_next_weekday_open_utc=deadline.isoformat(),
            capture_started_at_utc=started.isoformat(), capture_completed_at_utc=completed.isoformat(),
            source_session_pointer_by_ticker={ticker: '/plan/source_evidence/' + ticker +
                '/new_session_dates/' + str(index) for ticker in ('QQQ', 'SPY')},
            counts_as_observed_session=False, consumes_month_first_opportunity=False,
            decision_eligible=False)
        if close > started:
            item['classification'] = 'SOURCE_ROW_NOT_COMPLETED_AT_CAPTURE_START'
            unfinished.append(item)
        elif deadline <= min(started, completed):
            item['classification'] = 'MISSED_CONSERVATIVE_NEXT_OPEN_DEADLINE'
            missed.append(item)
        else:
            item['classification'] = 'DEADLINE_NOT_PASSED_FOR_ENTIRE_CAPTURE_INTERVAL'
            pending.append(item)
    require(len(pending) <= 1 and (not pending or pending[0]['session'] == dates[-1]), 'Latest pending only')
    rows = deepcopy(original)
    for item in missed:
        rows.append(dict(sequence=len(rows)+1, session=item['session'], kind='MISSED_OBSERVATION',
            seal_status='NOT_ATTEMPTED', evidence_reference=dict(capture['reference'],
                json_pointer='/plan/source_evidence/QQQ/new_session_dates/' + str(dates.index(item['session'])))))
    exact([row['session'] for row in rows], sorted(set(row['session'] for row in rows)))
    return dict(
        schema='PROSPECTIVE_GAP_EXTENSION_HISTORY_V3', policy_id=POLICY,
        status='GAP_EXTENSION_RESEARCH_ONLY' if missed else 'NO_EXPIRED_SESSION_TO_APPEND',
        supported_parent_schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2',
        old_v2_capture_writer_reader_compatible=False, future_actual_observation_requires_new_v3_consumers=True,
        parent_history_reference=deepcopy(parent['reference']),
        parent_publication_reference=deepcopy(parent['publication_reference']),
        parent_readback_reference=deepcopy(parent['readback_reference']),
        capture_reference=deepcopy(capture['reference']),
        capture_publication_reference=deepcopy(capture['publication_reference']),
        capture_readback_reference=deepcopy(capture['readback_reference']),
        genesis_preserved=deepcopy(parent['document']['genesis_preserved']),
        known_typed_rows=rows, known_typed_rows_preserved=deepcopy(original),
        observations=deepcopy(parent['document']['observations']),
        parent_attempt_inventory=deepcopy(parent['document']['parent_attempt_inventory']),
        baseline_references=deepcopy(parent['document']['baseline_references']),
        baseline_role='LAST_ACTUAL_OBSERVATION_BASELINE_NOT_LAST_ACCOUNTED',
        captured_source_references={ticker: deepcopy(artifacts[ticker]) for ticker in ('QQQ', 'SPY')},
        captured_source_role='FULL_CAPTURE_MAY_INCLUDE_PENDING_NOT_EXACT_ACCOUNTED_BASELINE',
        captured_sources_are_exact_accounted_prefix=False,
        first_actual_observed_session_by_month=deepcopy(months),
        last_observed_session=next(row['session'] for row in reversed(original) if row['kind'] != 'MISSED_OBSERVATION'),
        last_accounted_session=rows[-1]['session'], observation_count=parent['document']['observation_count'],
        new_observation_count=0, parent_typed_row_count=len(original), typed_row_count=len(rows),
        new_missed_observation_count=len(missed), gap_classifications=missed,
        pending_source_sessions=pending, excluded_not_completed_source_sessions=unfinished,
        capture_started_at=plan['capture_started_at'], capture_completed_at=plan['capture_completed_at'],
        tzif_reference=deepcopy(artifacts['tzif']),
        timing_semantics='CALLER_BOUND_TZIF_REGULAR_CLOSE_AND_NEXT_WEEKDAY_OPEN_NOT_EXCHANGE_CALENDAR',
        source_hashes=deepcopy(sources), source_reference_claims=deepcopy(sources),
        dependency_sha256={key: value[1] for key, value in DEPENDENCIES.items()},
        authentication_role='STRUCTURAL_REPLAY_ONLY_EXTERNALLY_BOUND_EVIDENCE_NOT_IO_AUTHENTICATION',
        raw_source_bytes_embedded=False, **dict.fromkeys(FALSE_FIELDS, False))


def safe(path):
    path = Path(path)
    for ancestor in (path, *path.parents):
        require(not ancestor.is_symlink() and not getattr(ancestor, 'is_junction', lambda: False)(),
                'Linked source/output forbidden')
    return path


def consume(item, sources):
    merge(sources, item)
    path = safe(item['path'])
    require(path.is_file() and path.stat().st_size <= 64*1024**2, 'Bounded regular source')
    require(not (path.parent/'failure.json').exists(), 'Failed source namespace')
    raw = path.read_bytes()
    exact(digest(raw), item['sha256'])
    return raw


def configured(bound):
    return {key: reference(str(ROOT/path), sha256) for key, (path, sha256) in bound.items()}


def load_envelope(refs, sources):
    result = dict(refs)
    for role, key in (('document', 'reference'), ('publication', 'publication_reference'),
                      ('readback', 'readback_reference')):
        result[role] = decode(consume(refs[key], sources))
        claims(sources, result[role]['source_hashes'])
    consume(refs['reader_reference'], sources)
    return result


def namespace(path, names):
    items = list(safe(path).iterdir())
    exact(sorted(item.name for item in items), sorted(names))
    require(all(safe(item).is_file() for item in items), 'Exact regular namespace')


def guard(sources):
    mutable = {(ROOT/'data/cache'/f'{ticker}.csv').resolve() for ticker in ('QQQ', 'SPY')}
    for path, sha256 in sources.items():
        require(Path(path).resolve() not in mutable, 'Mutable cache cannot enter source closure')
        consume(reference(path, sha256), {})
    exact(digest(SOURCE.read_bytes()), LOADED_SHA)


def private_checker(raw):
    exact(digest(raw), CAPTURE_READER_SHA)
    module = ModuleType('_fixed_independent_capture_reader_for_gap_v3')
    module.__file__ = str(CAPTURE_READER)
    exec(compile(raw, str(CAPTURE_READER), 'exec'), module.__dict__)
    exact(module.LOADED, CAPTURE_READER_SHA)
    return module


def save(path, value):
    raw = encode(value)
    if path.name != 'failure.json':
        require(shutil.disk_usage(Path(OUTPUT.anchor)).free >= 5*1024**3 + len(raw), 'Resource stop')
    with safe(path).open('xb') as stream:
        require(stream.write(raw) == len(raw), 'Complete report write')
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'Exact durable saved bytes')
    return reference(str(path), digest(raw))


def readback(*, execute=False):
    require(execute is True, 'Explicit independent readback')
    # Resolve every pending external anchor before any source IO or directory creation.
    history_ref = reference(str(HISTORY/'history.json'), HISTORY_SHA)
    publication_ref = reference(str(HISTORY/'publication.json'), PUBLICATION_SHA)
    producer_ref = reference(str(PRODUCER), PRODUCER_SHA)
    pure_ref = reference(str(PURE), PURE_SHA)
    parent_refs, capture_refs = configured(PARENT_BOUND), configured(CAPTURE_BOUND)
    require(not OUTPUT.exists(), 'Create-only no retry')
    sources = {str(SOURCE): LOADED_SHA}
    document = decode(consume(history_ref, sources))
    publication = decode(consume(publication_ref, sources))
    producer_sources = {str(PRODUCER): PRODUCER_SHA, str(PURE): PURE_SHA}
    consume(producer_ref, sources)
    consume(pure_ref, sources)  # Bytes only: never import, compile or call the new pure.
    parent = load_envelope(parent_refs, sources)
    capture = load_envelope(capture_refs, sources)
    for refs, envelope in ((parent_refs, parent), (capture_refs, capture)):
        for item in refs.values():
            merge(producer_sources, item)
        for key in ('document', 'publication', 'readback'):
            claims(producer_sources, envelope[key]['source_hashes'])
    for path, sha256 in DEPENDENCIES.values():
        item = reference(str(ROOT/path), sha256)
        consume(item, sources)
        merge(producer_sources, item)
    artifacts = capture['document']['captured_artifacts']
    snapshots = {ticker: consume(artifacts[ticker], sources) for ticker in ('QQQ', 'SPY')}
    baselines = {ticker: consume(parent['document']['baseline_references'][ticker], sources)
                 for ticker in ('QQQ', 'SPY')}
    tzif = consume(artifacts['tzif'], sources)
    checker = private_checker(consume(reference(str(CAPTURE_READER), CAPTURE_READER_SHA), sources))
    expected = reconstruct_history(parent=parent, capture=capture, source_bytes=snapshots,
        baseline_bytes=baselines, tzif_bytes=tzif, checker=checker)
    input_refs = dict(parent=parent_refs, capture=capture_refs, pure=pure_ref)
    for item in (document, publication):
        flags(item, WRAPPER_FALSE)
        exact(item['input_references'], input_refs)
        exact(item['source_hashes'], producer_sources)
        claims(sources, item['source_hashes'])
    exact(document['schema'], 'SOURCE_BOUND_PROSPECTIVE_GAP_HISTORY_V3')
    exact(document['history'], expected)
    exact(publication['schema'], 'PROSPECTIVE_GAP_HISTORY_PUBLICATION_V3')
    exact(publication['status'], 'PUBLISHED_GAP_EXTENSION_PENDING_INDEPENDENT_READBACK')
    exact(publication['history_reference'], history_ref)
    started_ref = publication['started_reference']
    exact(started_ref['path'], str(HISTORY/'started.json'))
    started = decode(consume(started_ref, sources))
    exact(started, dict(schema='PROSPECTIVE_GAP_HISTORY_STARTED_V3',
        input_references=input_refs, source_hashes=producer_sources, **dict.fromkeys(WRAPPER_FALSE, False)))
    def final_guard():
        namespace(HISTORY, ('started.json', 'history.json', 'publication.json'))
        namespace(Path(parent_refs['reference']['path']).parent, ('started.json', 'history.json', 'publication.json'))
        namespace(Path(parent_refs['readback_reference']['path']).parent, ('started.json', 'independent_readback.json'))
        namespace(Path(capture_refs['reference']['path']).parent,
                  ('started.json', 'QQQ.csv', 'SPY.csv', 'New_York.tzif', 'capture.json', 'publication.json'))
        namespace(Path(capture_refs['readback_reference']['path']).parent, ('started.json', 'independent_readback.json'))
        guard(sources)
    final_guard()
    require(shutil.disk_usage(Path(OUTPUT.anchor)).free >= 5*1024**3, 'Resource stop before namespace')
    safe(OUTPUT).mkdir(parents=True, exist_ok=False)
    try:
        save(OUTPUT/'started.json', dict(schema='PROSPECTIVE_GAP_HISTORY_READBACK_STARTED_V3',
            history_reference=history_ref, publication_reference=publication_ref,
            reader_sha256=LOADED_SHA, **dict.fromkeys(WRAPPER_FALSE, False)))
        report = save(OUTPUT/'independent_readback.json', dict(
            schema='PROSPECTIVE_GAP_HISTORY_INDEPENDENT_READBACK_V3', status='PURE_GAP_HISTORY_READBACK_PASS',
            history_reference=history_ref, publication_reference=publication_ref,
            input_references=input_refs, producer_reference=producer_ref, reader_sha256=LOADED_SHA,
            source_hashes=sources, counts={key: expected[key] for key in
                ('parent_typed_row_count', 'typed_row_count', 'observation_count',
                 'new_observation_count', 'new_missed_observation_count', 'last_observed_session',
                 'last_accounted_session', 'first_actual_observed_session_by_month')},
            entire_history_independently_reconstructed=True, publisher_called=False,
            new_pure_called=False, current_live_cache_read_or_reverified=False,
            verified_scope='EXACT_SAVED_BYTES_AND_STRUCTURAL_FORMULA_REPLAY_NOT_SOURCE_OR_CLOCK_AUTHENTICATION',
            **dict.fromkeys(WRAPPER_FALSE, False)))
        final_guard()
        consume(report, {})
        namespace(OUTPUT, ('started.json', 'independent_readback.json'))
        return report
    except BaseException as error:
        save(OUTPUT/'failure.json', dict(status='FAILED_DO_NOT_CONSUME',
            error_type=type(error).__name__, retry_allowed=False, **dict.fromkeys(WRAPPER_FALSE, False)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    print(json.dumps(readback(execute=parser.parse_args().execute)))
