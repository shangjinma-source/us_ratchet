"""Read sealed observed and missed frontiers without granting timeliness."""
import argparse
import csv
from datetime import date
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/observation_gap_frontier_20261002_v1'
BASE = 'data/cache/research/observation_gap_ledger_20261002_v1/'
CAPTURE = 'data/cache/research/observation_gap_classification_20261002_v1/'
PINS = {
    'ledger': (BASE + 'ledger.json', '8c15643e8ccf0b4356f235b43bb29152d98be2c9e71c3f16310f6a1d7d12e67d'),
    'publication': (BASE + 'publication.json', '6d36f4e420dd4fe959c1d88cb3b68b133ccce57ed6ad316b9d99ba1b7e411d7d'),
    'parent_sessions': (BASE + 'parent_sessions.csv', 'f78183b85d8e83b5037d3c4b77b2a8662af451def7a0411bbc26f82e1081f2e2'),
    'QQQ': (CAPTURE + 'QQQ.csv', 'a05d32edf48d035631deffe86e4cb157ffd6918c285b23cdc5a02c3677756c88'),
    'SPY': (CAPTURE + 'SPY.csv', 'dcbae9b32cd04edb78b6b334f9c703a224d9b5ed00658c925a19f2e2e6e2c6cf'),
    'core': ('backtest/ndx_observation_gap_frontier_research.py', '6588c37907a281012c4573337a6ea1261db6ad869835758c4cd8347a9d33feaf'),
}
FLAGS = dict.fromkeys(('old_calendar_mutated', 'old_calendar_full_validation_reexecuted',
    'gap_ledger_validation_reexecuted', 'classifier_reexecuted', 'gap_append_called',
    'candidate_generator_called', 'timeliness_evaluated', 'canonical_calendar_append_allowed',
    'candidate_seal_allowed', 'cohort_registration_allowed', 'oos_recovery_completed',
    'source_price_rows_validated_for_execution', 'promotion_allowed', 'live_mutation_allowed',
    'point_in_time_verified', 'full_transitive_source_closure_reverified'), False)
PARENT_FILES = {'started.json', 'publication.json', 'ledger.json', 'extension_events.jsonl',
                'parent_manifest.json', 'parent_events.jsonl', 'parent_sessions.csv', 'parent_receipt.json'}
PURE_FALSE = ('observed_session_added', 'fresh_observation', 'decision_eligible',
    'candidate_seal_allowed', 'cohort_registration_allowed', 'first_observed_session_of_month',
    'historical_timeliness_verified', 'future_timeliness_granted', 'canonical_calendar_append_allowed',
    'point_in_time_verified', 'promotion_allowed', 'live_mutation_allowed', 'source_bytes_verified',
    'system_clock_verified', 'oos_recovery_completed', 'gap_hash_chain_reverified', 'parent_calendar_reverified')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def csv_dates(raw, field):
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    values = [row[field] for row in rows]
    require(values and all(date.fromisoformat(day).isoformat() == day for day in values), 'Canonical nonempty dates required')
    require(values == sorted(set(values)), 'Unique ascending dates required')
    return values


def prepare(raw, refs):
    ledger = json.loads(raw['ledger'])
    receipt = json.loads(raw['publication'])
    require(receipt['schema'] == 'OBSERVATION_GAP_LEDGER_PUBLICATION_V1'
            and receipt['status'] == 'PUBLISHED_MISSED_OBSERVATION_EVIDENCE_ONLY', 'Gap publication differs')
    require(receipt['artifacts']['ledger'] == refs['ledger']
            and receipt['artifacts']['parent_sessions'] == refs['parent_sessions'], 'Artifact binding differs')
    for flag in ('old_calendar_mutated', 'canonical_calendar_append_allowed', 'candidate_seal_allowed',
                 'cohort_registration_allowed', 'oos_recovery_completed', 'promotion_allowed', 'point_in_time_verified'):
        require(receipt[flag] is False, 'Parent authority differs')
    require(ledger['schema'] == 'OBSERVATION_GAP_EVIDENCE_LEDGER_V1', 'Gap ledger schema differs')
    binding = ledger['parent_binding']
    require(type(binding['event_count']) is int and binding['event_count'] == 66
            and type(binding['session_count']) is int and binding['session_count'] == 60
            and binding['last_session'] == '2026-09-24', 'Frozen parent boundary differs')
    require(binding['session_projection_reference'] == receipt['input_references']['parent_sessions']
            and binding['session_projection_reference']['sha256'] == refs['parent_sessions']['sha256'], 'Copied parent projection differs')
    parent_dates = csv_dates(raw['parent_sessions'], 'session_date')
    require(len(parent_dates) == 60 and parent_dates[0] == '2026-07-01'
            and parent_dates[-1] == binding['last_session'], 'Parent dates differ')
    source_dates = {}
    require(len(ledger['batches']) == 1, 'One sealed classification batch required')
    captured = ledger['batches'][0]['classification_capture']['captured_source_references']
    for ticker in ('QQQ', 'SPY'):
        require(receipt['input_references'][ticker] == refs[ticker] and captured[ticker] == refs[ticker], 'Captured source binding differs')
        source_dates[ticker] = csv_dates(raw[ticker], 'Date')
    common = sorted(set(source_dates['QQQ']) & set(source_dates['SPY']))
    common = [day for day in common if day >= parent_dates[0]]
    gap_dates = [event['session'] for event in ledger['events']]
    require(gap_dates == ['2026-09-25', '2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01'], 'Exact five gaps required')
    require(common[:65] == parent_dates + gap_dates, 'Full common source prefix differs')
    return {'ledger': ledger, 'parent_dates': parent_dates, 'common_dates': common,
            'source_dates_counts': {key: len(value) for key, value in source_dates.items()}}


def guard(sources):
    require(sources.get(str(SOURCE)) == LOADED_SHA, 'Loaded source binding differs')
    for path, digest in sources.items():
        require(sha(Path(path).read_bytes()) == digest, 'Source drift: ' + path)


def validate_result(result, prepared):
    require(result['schema'] == 'OBSERVATION_GAP_FRONTIER_RESEARCH_V1'
            and result['last_observed_session'] == '2026-09-24'
            and result['last_accounted_gap_session'] == result['last_accounted_session'] == '2026-10-01', 'Cursor result differs')
    require(type(result['parent_observed_session_count']) is int and result['parent_observed_session_count'] == 60
            and type(result['accounted_gap_count']) is int and result['accounted_gap_count'] == 5, 'Result counts differ')
    require(result['unaccounted_source_dates'] == prepared['common_dates'][65:] == []
            and result['excluded_source_dates_before_parent_start'] == [], 'Pinned capture frontier differs')
    require([row['session'] for row in result['known_accounted_rows']] == prepared['common_dates'], 'Accounted date projection differs')
    require(all(row['kind'] == 'SEALED_PARENT_OBSERVED_SESSION' and row['parent_session_index'] == index
                and row['eligibility_reverified'] is False for index, row in enumerate(result['known_accounted_rows'][:60])), 'Parent role differs')
    require(all(row['kind'] == 'MISSED_OBSERVATION' and row['gap_event_index'] == index
                and row['gap_event_sha256'] == prepared['ledger']['events'][index]['event_sha256']
                and row['counts_as_observed_session'] is False and row['decision_eligible'] is False
                for index, row in enumerate(result['known_accounted_rows'][60:])), 'Gap role differs')
    require(result['month_first_semantics'] == 'UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE', 'Month semantics changed')
    for key in PURE_FALSE:
        require(result[key] is False, 'Result authority differs: ' + key)
    for key in ('observed_session_increment', 'fresh_session_increment', 'seal_increment', 'cohort_increment'):
        require(type(result[key]) is int and result[key] == 0, 'Result increment differs')


def write_new(path, value):
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == data, 'Output differs')
    return sha(data)


def run():
    require(not OUTPUT.exists(), 'Fixed namespace exists; no retry')
    require(all(type(digest) is str and len(digest) == 64 for _, digest in PINS.values()), 'Pending source pins')
    sources = {str(SOURCE): LOADED_SHA}
    guard(sources)
    raw, refs = {}, {}
    for role, (relative, digest) in PINS.items():
        path = ROOT / relative
        data = path.read_bytes()
        require(sha(data) == digest, 'Source mismatch: ' + role)
        raw[role] = data
        refs[role] = {'path': str(path), 'sha256': digest}
        sources[str(path)] = digest
    require({path.name for path in Path(refs['ledger']['path']).parent.iterdir()} == PARENT_FILES, 'Parent namespace failed/incomplete')
    prepared = prepare(raw, refs)
    name = 'backtest.ndx_observation_gap_frontier_research'
    require(name not in sys.modules, 'Fresh CLI required')
    module = importlib.import_module(name)
    require(Path(module.__file__).resolve() == Path(refs['core']['path']).resolve(), 'Core path differs')
    guard(sources)
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        write_new(OUTPUT / 'started.json', {'source_hashes': sources, 'retry_allowed': False, **FLAGS})
        result = module.prepare_observation_frontier(parent_session_dates=prepared['parent_dates'],
            common_source_session_dates=prepared['common_dates'], gap_ledger=prepared['ledger'])
        validate_result(result, prepared)
        result.update(source_hashes=sources, input_references=refs,
                      raw_source_date_counts=prepared['source_dates_counts'], **FLAGS)
        guard(sources)
        digest = write_new(OUTPUT / 'frontier.json', result)
        guard(sources)
        pubsha = write_new(OUTPUT / 'publication.json', {'schema': 'OBSERVATION_GAP_FRONTIER_PUBLICATION_V1',
            'status': 'PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY',
            'frontier_reference': {'path': str(OUTPUT / 'frontier.json'), 'sha256': digest},
            'source_hashes': sources, **FLAGS})
        guard(sources)
        require(sha((OUTPUT / 'frontier.json').read_bytes()) == digest
                and sha((OUTPUT / 'publication.json').read_bytes()) == pubsha
                and {path.name for path in OUTPUT.iterdir()} == {'started.json', 'frontier.json', 'publication.json'}, 'Final publication differs')
        return {'path': str(OUTPUT / 'frontier.json'), 'sha256': digest, 'publication_sha256': pubsha}
    except Exception as error:
        write_new(OUTPUT / 'failure.json', {'status': 'FAILED_DO_NOT_CONSUME', 'error': str(error), 'retry_allowed': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    if not parser.parse_args().execute:
        parser.error('Explicit --execute required')
    print(json.dumps(run(), indent=2))
