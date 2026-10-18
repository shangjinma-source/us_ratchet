"""Independent source-bound readback; never executes the producer or new pure core."""
import argparse
from copy import deepcopy
from datetime import date, datetime, time, timezone
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
CAPTURE = ROOT / 'data/cache/research/forward_gap_parent_source_capture_20261009_v3'
OUTPUT = ROOT / 'data/cache/research/forward_gap_parent_capture_independent_readback_20261009_v3'
PRODUCER = ROOT / 'scripts/ndx_forward_gap_parent_source_capture_20261009_v3.py'
PURE = ROOT / 'backtest/ndx_forward_gap_parent_capture_research_v3.py'
PRODUCER_SHA = 'a52dcfe5d3daf7b0223e8f82c83b61ec3e840a9d5e5288e8b874df708e100486'
PURE_SHA = 'e179a621023a478ff0824d41243ceafaceb0aa2bc6b9a80998f7c03f0d5721f8'
CAPTURE_SHA = '26265fbb63dcbc04eb969c60e5dbb9704d893cb048e32e7a5df6cd11f0d3423d'
PUBLICATION_SHA = 'f2292529da898896a816cc0a919740623acf4d04e912a286e94be425dc7a6eeb'
CSV_READER = ROOT / 'scripts/ndx_variable_prefix_capture_independent_readback_20261003.py'
CSV_READER_SHA = 'aed7b71289fb30473cedefda00c6377c0700bea115e5d99328c1c20dd4572dbe'
PARENT_BOUND = {
    'reference': ('data/cache/research/prospective_gap_history_20261009_v3/history.json', '600d15deb7cdcbc74fb13337c279d31c910d9389088ebc8668ea650779fdfd8a'),
    'publication_reference': ('data/cache/research/prospective_gap_history_20261009_v3/publication.json', '3ff2cf28d954e64ed7a21af6d8b7ed5465c7cf2fe5c6fd7d057cd43e4cddfe10'),
    'readback_reference': ('data/cache/research/prospective_gap_history_independent_readback_20261009_v3/independent_readback.json', '86e867fa73f28b9a436472eb27848a159a75e5de4bcf97e7a4b69b6a1be98912'),
    'reader_reference': ('scripts/ndx_prospective_gap_history_independent_readback_20261009_v3.py', '2be765c5dafcb85366e4e84d3a8cbed2037a6924649695f3ab176764075791f8'),
}
DEPENDENCIES = {
    'base': ('backtest/ndx_forward_source_capture_research.py', '30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'),
    'scoped': ('backtest/ndx_forward_source_capture_scoped_research.py', '9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee'),
}
WRAPPER_FALSE = (
    'candidate_seal_allowed', 'clock_authenticity_verified', 'cohort_registration_allowed',
    'filesystem_attempt_inventory_authenticated', 'full_transitive_source_closure_reverified',
    'future_independent_oos', 'live_mutation_allowed', 'network_capture_performed',
    'observation_created', 'old_calendar_mutated', 'point_in_time_verified',
    'promotion_allowed', 'source_authenticity_verified')
PURE_FALSE = WRAPPER_FALSE + (
    'parent_history_authenticated_by_this_module', 'timeliness_verified',
    'production_generator_authorized', 'seal_event_created', 'partial_recovery_performed',
    'canonical_calendar_append_allowed', 'retrospective_backfill_allowed',
    'decision_eligible', 'exchange_holidays_and_early_closes_verified')
FALSE_FIELDS = PURE_FALSE + ('network_quote_refresh_performed',)
ROLES = ('reference', 'publication_reference', 'readback_reference', 'reader_reference')
TICKERS = ('QQQ', 'SPY')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def exact(left, right):
    require(encode(left) == encode(right), 'Independent exact value mismatch')


def decode(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate JSON key')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def reference(path, sha256):
    require(type(path) is str and path and path.strip() == path and '\x00' not in path, 'Reference path')
    require(type(sha256) is str and len(sha256) == 64 and
            all(c in '0123456789abcdef' for c in sha256), 'Pending immutable SHA')
    return dict(path=path, sha256=sha256)


def merge(sources, item):
    require(type(item) is dict and set(item) == {'path', 'sha256'}, 'Exact reference fields')
    reference(item['path'], item['sha256'])
    require(item['path'] not in sources or sources[item['path']] == item['sha256'], 'Conflicting source path')
    sources[item['path']] = item['sha256']


def declarations(value, sources):
    if type(value) is dict:
        if 'path' in value and 'sha256' in value:
            merge(sources, {key: value[key] for key in ('path', 'sha256')})
        for key, item in value.items():
            if key in ('source_hashes', 'source_reference_claims'):
                for path, sha256 in item.items():
                    merge(sources, reference(path, sha256))
            else:
                declarations(item, sources)
    elif type(value) is list:
        for item in value:
            declarations(item, sources)


def flags(value, fields):
    for key in fields:
        require(value.get(key) is False, 'Strict false authority ' + key)


def utc(value):
    require(type(value) is str, 'Explicit UTC string')
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0, 'Explicit UTC clock')
    return parsed.astimezone(timezone.utc)


def private_csv_reader(raw):
    require(digest(raw) == CSV_READER_SHA, 'Frozen CSV reader SHA')
    module = ModuleType('_independent_gap_capture_csv')
    module.__file__ = str(CSV_READER)
    exec(compile(raw.decode('utf-8-sig'), str(CSV_READER), 'exec'), module.__dict__)
    return module.csv_rows


def inspect_v3_parent(parent):
    require(set(parent) == set(ROLES) | {'document', 'publication', 'readback'}, 'Full V3 envelope')
    refs = {key: parent[key] for key in ROLES}
    sources = {}
    for item in refs.values():
        merge(sources, item)
    exact(parent['reader_reference']['sha256'], PARENT_BOUND['reader_reference'][1])
    d, p, a = (parent[key] for key in ('document', 'publication', 'readback'))
    exact(d['schema'], 'SOURCE_BOUND_PROSPECTIVE_GAP_HISTORY_V3')
    exact(p['schema'], 'PROSPECTIVE_GAP_HISTORY_PUBLICATION_V3')
    exact(p['status'], 'PUBLISHED_GAP_EXTENSION_PENDING_INDEPENDENT_READBACK')
    exact(a['schema'], 'PROSPECTIVE_GAP_HISTORY_INDEPENDENT_READBACK_V3')
    exact(a['status'], 'PURE_GAP_HISTORY_READBACK_PASS')
    for value in (d, p, a):
        flags(value, WRAPPER_FALSE); flags(value,set(PURE_FALSE).intersection(value)); declarations(value, sources)
    exact(p['history_reference'], refs['reference']); exact(a['history_reference'], refs['reference'])
    exact(a['publication_reference'], refs['publication_reference'])
    exact(a['reader_sha256'], refs['reader_reference']['sha256'])
    exact(d['input_references'], p['input_references']); exact(d['input_references'], a['input_references'])
    exact(d['source_hashes'], p['source_hashes'])
    require(a['entire_history_independently_reconstructed'] is True and a['publisher_called'] is False and
            a['new_pure_called'] is False and a['current_live_cache_read_or_reverified'] is False, 'V3 readback role')
    nested = {}; declarations(d, nested)
    for path, sha256 in nested.items():
        exact(d['source_hashes'].get(path), sha256)
    for item in (refs['reference'], refs['publication_reference'], refs['reader_reference'], a['producer_reference']):
        exact(a['source_hashes'].get(item['path']), item['sha256'])
    for path, sha256 in d['source_hashes'].items():
        exact(a['source_hashes'].get(path), sha256)
    h = d['history']; flags(h, PURE_FALSE)
    for key,role in [('parent_history_reference','reference'),('parent_publication_reference','publication_reference'),
                     ('parent_readback_reference','readback_reference')]: exact(h[key],d['input_references']['parent'][role])
    for key,role in [('capture_reference','reference'),('capture_publication_reference','publication_reference'),
                     ('capture_readback_reference','readback_reference')]: exact(h[key],d['input_references']['capture'][role])
    exact(h['schema'], 'PROSPECTIVE_GAP_EXTENSION_HISTORY_V3')
    exact(h['policy_id'], 'FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH')
    exact(h['baseline_role'], 'LAST_ACTUAL_OBSERVATION_BASELINE_NOT_LAST_ACCOUNTED')
    require(type(h['pending_source_sessions']) is list and not h['pending_source_sessions'] and
            type(h['excluded_not_completed_source_sessions']) is list and not h['excluded_not_completed_source_sessions'],
            'BASELINE_HAS_UNACCOUNTED_SUFFIX')
    exact(h['captured_sources_are_exact_accounted_prefix'], False)
    days, months, actual = [], {}, []
    for number, row in enumerate(h['known_typed_rows'], 1):
        exact(sorted(row), sorted(('sequence', 'session', 'kind', 'seal_status', 'evidence_reference')))
        require(type(row['sequence']) is int and row['sequence'] == number, 'Typed sequence')
        day = date.fromisoformat(row['session'])
        require(day.isoformat() == row['session'] and day.weekday() < 5, 'Canonical session')
        require(row['kind'] in ('SEALED_PARENT_OBSERVED_SESSION', 'PROSPECTIVE_OBSERVED_SESSION', 'MISSED_OBSERVATION'), 'Typed kind')
        require(type(row['evidence_reference'].get('json_pointer')) is str and row['evidence_reference']['json_pointer'].startswith('/'), 'Typed pointer')
        days.append(row['session'])
        if row['kind'] == 'MISSED_OBSERVATION': exact(row['seal_status'], 'NOT_ATTEMPTED')
        else: months.setdefault(row['session'][:7], row['session'])
        if row['kind'] == 'PROSPECTIVE_OBSERVED_SESSION': actual.append(row)
    exact(days, sorted(set(days))); require(bool(days), 'Nonempty history')
    exact(h['first_actual_observed_session_by_month'], months)
    exact(h['last_accounted_session'], days[-1])
    exact(h['last_observed_session'], next(row['session'] for row in reversed(h['known_typed_rows']) if row['kind'] != 'MISSED_OBSERVATION'))
    for key, expected in [('typed_row_count',len(days)),('observation_count',len(actual)),('new_observation_count',0),
                          ('parent_typed_row_count',len(h['known_typed_rows_preserved'])),
                          ('new_missed_observation_count',len(days)-len(h['known_typed_rows_preserved']))]:
        require(type(h[key]) is int and h[key] == expected, 'Exact history count')
    exact(h['known_typed_rows'][:h['parent_typed_row_count']], h['known_typed_rows_preserved'])
    added = h['known_typed_rows'][h['parent_typed_row_count']:]
    require(all(row['kind'] == 'MISSED_OBSERVATION' for row in added), 'Gap-only extension')
    exact([row['session'] for row in added], [value['session'] for value in h['gap_classifications']])
    require(len(h['observations']) == len(actual), 'Observation inventory')
    require(type(h['parent_attempt_inventory']) is list and len(h['parent_attempt_inventory']) == len(actual),'Exact attempt inventory')
    for row, observation in zip(actual, h['observations']):
        exact(observation['session'], row['session']); exact(observation['sequence'], row['sequence'])
        exact(row['evidence_reference'],dict(observation['payload_reference'],json_pointer='/observation_identity'))
        exact(observation['first_actual_observed_session_of_month'], months[row['session'][:7]])
        exact(observation['month_first_actual_observation'], months[row['session'][:7]] == row['session'])
        attempts=[attempt for attempt in h['parent_attempt_inventory'] if attempt.get('session')==row['session']]
        require(len(attempts)==1,'Unique resolved attempt')
        exact(attempts[0],dict(session=row['session'],observation_id=observation['observation_id'],
              status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',payload_reference=observation['payload_reference'],
              receipt_reference=observation['receipt_reference'],independent_readback_reference=observation['audit_reference']))
    exact(a['counts'], {key:h[key] for key in ('parent_typed_row_count','typed_row_count','observation_count',
          'new_observation_count','new_missed_observation_count','last_observed_session','last_accounted_session',
          'first_actual_observed_session_by_month')})
    return h, days, sources


def reconstruct_plan(*, parent, source_bytes, source_references, accounted_baseline_bytes,
                     actual_baseline_bytes, capture_started_at, capture_completed_at,
                     tzif_bytes, tzif_reference, csv_rows):
    h, days, sources = inspect_v3_parent(parent)
    for pair in (source_bytes, source_references, accounted_baseline_bytes, actual_baseline_bytes,
                 h['captured_source_references'], h['baseline_references']):
        require(type(pair) is dict and set(pair) == set(TICKERS), 'Exact source pair')
    begin, finish = utc(capture_started_at), utc(capture_completed_at)
    require(begin <= finish, 'Capture clock reversal')
    merge(sources, tzif_reference); exact(digest(tzif_bytes), tzif_reference['sha256'])
    exact(tzif_reference['sha256'],h['tzif_reference']['sha256'])
    zone = ZoneInfo.from_file(BytesIO(tzif_bytes), key='America/New_York')
    def close(session):
        return datetime.combine(date.fromisoformat(session), time(16), zone).astimezone(timezone.utc)
    require(begin >= close(days[-1]), 'Capture before last accounted close')
    diagnostics, evidence, new = [], {}, {}
    for ticker in TICKERS:
        baseline, actual, current = accounted_baseline_bytes[ticker], actual_baseline_bytes[ticker], source_bytes[ticker]
        for raw, ref in ((baseline,h['captured_source_references'][ticker]),
                         (actual,h['baseline_references'][ticker]),(current,source_references[ticker])):
            merge(sources, ref); exact(digest(raw), ref['sha256'])
        oldrows, _ = csv_rows(baseline, days[0]); actualrows, _ = csv_rows(actual, days[0]); rows, issues = csv_rows(current, days[0])
        scoped = lambda values:[row['Date'] for row in values if row['Date'] >= days[0]]
        require(scoped(oldrows) == days, 'BASELINE_HAS_UNACCOUNTED_SUFFIX')
        require(baseline.startswith(actual) and scoped(actualrows) == [value for value in days if value <= h['last_observed_session']], 'Complete actual baseline prefix')
        currentdays = scoped(rows)
        if not current.startswith(baseline) or currentdays[:len(days)] != days:
            diagnostics.append(dict(reason='ACCOUNTED_BASELINE_PREFIX_REVISED',ticker=ticker))
        new[ticker] = currentdays[len(days):] if currentdays[:len(days)] == days else []
        evidence[ticker] = dict(source_reference=deepcopy(source_references[ticker]),
            accounted_baseline_reference=deepcopy(h['captured_source_references'][ticker]),
            actual_baseline_reference=deepcopy(h['baseline_references'][ticker]), original_row_count=len(rows),
            source_session_dates=currentdays, new_session_dates=new[ticker],
            full_accounted_bytes_prefix_matches=current.startswith(baseline),
            included_original_row_indexes=[i for i,row in enumerate(rows) if row['Date'] >= days[0]],
            excluded_original_row_indexes=[i for i,row in enumerate(rows) if row['Date'] < days[0]],
            excluded_before_scope_ohlc_diagnostics=issues)
    if new['QQQ'] != new['SPY']: diagnostics.append(dict(reason='ASYMMETRIC_NEW_SESSION_DATES'))
    if any(len(values)>1 for values in new.values()): diagnostics.append(dict(reason='MULTIPLE_UNACCOUNTED_SESSIONS'))
    candidate = new['QQQ'][0] if not diagnostics and len(new['QQQ']) == 1 else None
    if candidate and begin < close(candidate):
        diagnostics.append(dict(reason='SOURCE_SESSION_NOT_COMPLETED_AT_CAPTURE_START')); candidate=None
    return dict(schema='FORWARD_GAP_PARENT_CAPTURE_PLAN_V3',
        status='BLOCKED_SOURCE_DIAGNOSTICS' if diagnostics else 'ONE_NEW_SESSION_CAPTURE_CANDIDATE' if candidate else 'NO_NEW_SESSION',
        diagnostics=diagnostics, candidate_session=candidate, policy_id=h['policy_id'],
        parent_references={key:deepcopy(parent[key]) for key in ROLES}, known_typed_rows=deepcopy(h['known_typed_rows']),
        observations=deepcopy(h['observations']), parent_attempt_inventory=deepcopy(h['parent_attempt_inventory']),
        first_actual_observed_session_by_month=deepcopy(h['first_actual_observed_session_by_month']),
        baseline_references=deepcopy(h['baseline_references']), baseline_role=h['baseline_role'],
        accounted_baseline_references=deepcopy(h['captured_source_references']),
        accounted_baseline_role='FULL_SAVED_CSV_SCOPE_EQUALS_ALL_KNOWN_TYPED_SESSIONS',
        last_accounted_session=h['last_accounted_session'],last_observed_session=h['last_observed_session'],
        source_evidence=evidence,source_reference_claims=sources,capture_started_at=begin.isoformat(),
        capture_completed_at=finish.isoformat(),tzif_reference=deepcopy(tzif_reference),
        candidate_conservative_close_utc=close(candidate).isoformat() if candidate else None,
        timing_semantics='CALLER_SUPPLIED_CLOCK_CONSERVATIVE_16_NY_CLOSE_NOT_AUTHENTICATED_EXCHANGE_CALENDAR',
        late_observation_classification_deferred_to_payload_core=True,
        authentication_role='STRUCTURAL_DECLARATIONS_AND_SUPPLIED_BYTES_ONLY_NO_IO_AUTHENTICATION',
        raw_source_bytes_embedded=False,dependency_sha256={key:value[1] for key,value in DEPENDENCIES.items()},
        **dict.fromkeys(PURE_FALSE,False))


def safe(path):
    path = Path(path)
    for item in (path,*path.parents):
        require(not item.is_symlink() and not getattr(item,'is_junction',lambda:False)(), 'Linked path forbidden')
    return path


def consume(item,sources):
    merge(sources,item); path=safe(item['path'])
    require(path.is_file() and path.stat().st_size <= 64*1024**2 and not (path.parent/'failure.json').exists(), 'Bounded immutable source')
    raw=path.read_bytes(); exact(digest(raw),item['sha256']); return raw


def namespace(path,names):
    items=list(safe(path).iterdir()); exact(sorted(item.name for item in items),sorted(names))
    require(all(safe(item).is_file() for item in items), 'Regular namespace')


def guard(sources):
    live={str((ROOT/'data/cache'/f'{ticker}.csv').resolve()) for ticker in TICKERS}
    for path,sha256 in sources.items():
        require(str(Path(path).resolve()) not in live, 'Mutable cache not permanent source')
        consume(reference(path,sha256),{})


def save(path,value):
    raw=encode(value)
    if path.name != 'failure.json':
        require(shutil.disk_usage(Path(OUTPUT.anchor)).free >= 5*1024**3 + len(raw), 'Resource stop before write')
    with safe(path).open('xb') as stream:
        require(stream.write(raw)==len(raw), 'Complete write'); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Durable saved bytes'); return reference(str(path),digest(raw))


def readback(*,execute=False):
    require(execute is True,'Explicit independent readback')
    # Every pending pin is validated before filesystem access or output creation.
    cr=reference(str(CAPTURE/'capture.json'),CAPTURE_SHA); pr=reference(str(CAPTURE/'publication.json'),PUBLICATION_SHA)
    producer_ref=reference(str(PRODUCER),PRODUCER_SHA); pure_ref=reference(str(PURE),PURE_SHA)
    parents={key:reference(str(ROOT/path),sha256) for key,(path,sha256) in PARENT_BOUND.items()}
    dependencies={key:reference(str(ROOT/path),sha256) for key,(path,sha256) in DEPENDENCIES.items()}
    require(not OUTPUT.exists(),'Create-only no retry')
    sources={str(SOURCE):LOADED_SHA}
    capture=decode(consume(cr,sources)); publication=decode(consume(pr,sources))
    parent=dict(parents)
    for role,key in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:
        parent[role]=decode(consume(parents[key],sources))
    consume(parents['reader_reference'],sources)
    h,_,_=inspect_v3_parent(parent)
    initial={}
    for item in (producer_ref,pure_ref,*dependencies.values(),*parents.values()): merge(initial,item)
    for obj in (parent['document'],parent['publication'],parent['readback']):
        for path,sha256 in obj['source_hashes'].items(): merge(initial,reference(path,sha256))
    for item in (*h['captured_source_references'].values(),*h['baseline_references'].values(),h['tzif_reference']): merge(initial,item)
    inputs=dict(dependencies,pure=pure_ref,tzif=h['tzif_reference'])
    exact(capture['schema'],'SOURCE_BOUND_FORWARD_GAP_PARENT_CAPTURE_V3')
    exact(publication['schema'],'FORWARD_GAP_PARENT_CAPTURE_PUBLICATION_V3')
    exact(publication['status'],'PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION');exact(publication['capture_reference'],cr)
    for obj in (capture,publication): flags(obj,FALSE_FIELDS)
    exact(capture['parent_references'],parents);exact(capture['input_references'],inputs)
    require(capture['clock_captured_by_runner'] is True and capture['external_clock_attestation_verified'] is False,'Clock recording not attestation')
    exact(capture['quote_source_type'],'EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH')
    exact(capture['current_cache_verification_scope'],'CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE')
    artifacts=capture['captured_artifacts'];exact(sorted(artifacts),['QQQ','SPY','tzif'])
    expected_sources=dict(initial)
    for key,item in artifacts.items():
        exact(item['path'],str(CAPTURE/('New_York.tzif' if key=='tzif' else key+'.csv')));merge(expected_sources,item)
    exact(capture['source_hashes'],expected_sources);exact(publication['source_hashes'],expected_sources)
    exact(sorted(capture['current_cache_references']),list(TICKERS))
    for ticker in TICKERS:
        exact(capture['current_cache_references'][ticker],reference(str(ROOT/'data/cache'/f'{ticker}.csv'),artifacts[ticker]['sha256']))
    for path,sha256 in expected_sources.items(): consume(reference(path,sha256),sources)
    actual={ticker:consume(h['baseline_references'][ticker],sources) for ticker in TICKERS}
    accounted={ticker:consume(h['captured_source_references'][ticker],sources) for ticker in TICKERS}
    snapshots={ticker:consume(artifacts[ticker],sources) for ticker in TICKERS}
    tz=consume(artifacts['tzif'],sources);exact(artifacts['tzif']['sha256'],h['tzif_reference']['sha256'])
    csv_ref=reference(str(CSV_READER),CSV_READER_SHA); csv_rows=private_csv_reader(consume(csv_ref,sources))
    expected=reconstruct_plan(parent=parent,source_bytes=snapshots,source_references={ticker:artifacts[ticker] for ticker in TICKERS},
        accounted_baseline_bytes=accounted,actual_baseline_bytes=actual,capture_started_at=capture['capture_started_at'],
        capture_completed_at=capture['capture_completed_at'],tzif_bytes=tz,tzif_reference=artifacts['tzif'],csv_rows=csv_rows)
    exact(capture['plan'],expected)
    started_path=safe(CAPTURE/'started.json')
    require(started_path.is_file() and started_path.stat().st_size <= 64*1024**2 and
            not (started_path.parent/'failure.json').exists(),'Bounded observed start source')
    raw=started_path.read_bytes();started_ref=reference(str(started_path),digest(raw));merge(sources,started_ref)
    exact(decode(raw),dict(schema='FORWARD_GAP_PARENT_CAPTURE_STARTED_V3',parent_references=parents,
         input_references=inputs,source_hashes=initial,retry_allowed=False,**dict.fromkeys(FALSE_FIELDS,False)))
    def final_guard():
        namespace(CAPTURE,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'))
        namespace(Path(parents['reference']['path']).parent,('started.json','history.json','publication.json'))
        namespace(Path(parents['readback_reference']['path']).parent,('started.json','independent_readback.json'))
        guard(sources)
    final_guard();require(shutil.disk_usage(Path(OUTPUT.anchor)).free >= 5*1024**3,'Resource stop before namespace')
    safe(OUTPUT).mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(schema='FORWARD_GAP_PARENT_CAPTURE_READBACK_STARTED_V3',capture_reference=cr,
             publication_reference=pr,reader_sha256=LOADED_SHA,**dict.fromkeys(FALSE_FIELDS,False)))
        report=save(OUTPUT/'independent_readback.json',dict(schema='FORWARD_GAP_PARENT_CAPTURE_INDEPENDENT_READBACK_V3',
            status='PURE_FORWARD_GAP_CAPTURE_READBACK_PASS',capture_reference=cr,publication_reference=pr,
            parent_references=parents,input_references=inputs,producer_reference=producer_ref,reader_sha256=LOADED_SHA,
            source_hashes=sources,counts=dict(status=expected['status'],parent_typed_row_count=len(expected['known_typed_rows']),
                parent_actual_observation_count=len(expected['observations']),
                parent_gap_count=sum(row['kind']=='MISSED_OBSERVATION' for row in expected['known_typed_rows']),candidate_session=expected['candidate_session'],
                diagnostic_count=len(expected['diagnostics']),snapshot_counts={ticker:expected['source_evidence'][ticker]['original_row_count'] for ticker in TICKERS}),
            entire_plan_independently_reconstructed=True,producer_called=False,new_pure_called=False,
            snapshot_bytes_verified=True,plan_gap_parent_capture_called=False,
            current_live_cache_read_or_reverified=False,external_clock_attestation_verified=False,
            started_reference_observed_not_external_anchor=started_ref,started_externally_authenticated=False,
            verification_scope='FIXED_PARENT_FOUR_ANCHORS_SAVED_BYTES_AND_INDEPENDENT_PLAN_FORMULA_NOT_SOURCE_OR_CLOCK_AUTHENTICATION',
            **dict.fromkeys(FALSE_FIELDS,False)))
        final_guard();consume(report,{});namespace(OUTPUT,('started.json','independent_readback.json'));return report
    except BaseException as error:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,retry_allowed=False,
             **dict.fromkeys(FALSE_FIELDS,False)));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    print(json.dumps(readback(execute=parser.parse_args().execute)))
