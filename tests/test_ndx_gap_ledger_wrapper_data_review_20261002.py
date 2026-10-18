import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_observation_gap_ledger_20261002 as module


def fixture(root):
    raw = {}
    raw['parent_events'] = b''.join(json.dumps({'event_sha256': 'a' * 64}).encode() + b'\n' for _ in range(66))
    raw['parent_sessions'] = ('session_date\n' + '2026-09-24\n' * 60).encode()
    raw['QQQ'] = raw['SPY'] = ('Date,Close\n' + ''.join(day + ',100\n' for day in module.DATES)).encode()
    refs = {role: {'path': str(root / (role + '.data')), 'sha256': module.sha(value)} for role, value in raw.items()}
    manifest = {'manifest_type': 'ndx_observed_us_session_calendar_v2', 'event_count': 66, 'session_count': 60,
        'decision_eligible_session_count': 0, 'latest_session_date': '2026-09-24', 'latest_event_sha256': 'a' * 64,
        'commit_transaction_id': 'b' * 64, 'artifacts': {'event_ledger': {'sha256': refs['parent_events']['sha256']},
            'session_projection': {'sha256': refs['parent_sessions']['sha256']}}}
    raw['parent_manifest'] = json.dumps(manifest).encode()
    raw['parent_receipt'] = json.dumps({'planned_manifest': manifest, 'transaction_id': 'b' * 64}).encode()
    for role in ('parent_manifest', 'parent_receipt'):
        refs[role] = {'path': str(root / (role + '.json')), 'sha256': module.sha(raw[role])}
    capture = {'schema': 'CURRENT_SOURCE_GAP_CLASSIFICATION_CAPTURE_V1', 'captured_using_system_clock': True,
        'captured_at_utc': '2026-10-02T14:26:14+00:00',
        'parent_references': {'calendar_manifest': refs['parent_manifest'], 'calendar_events': refs['parent_events']},
        'classification': {'pending_classifications': [{'session': day} for day in module.DATES],
            'timeliness_candidate': None, 'missed_or_ineligible_row_count': 5},
        'captured_source_references': {ticker: refs[ticker] for ticker in ('QQQ', 'SPY')},
        'pending_source_rows': {ticker: {day: {'Date': day, 'Close': '100'} for day in module.DATES} for ticker in ('QQQ', 'SPY')},
        **dict.fromkeys(('calendar_append_allowed', 'candidate_seal_allowed', 'cohort_registration_allowed',
            'old_calendar_mutated', 'source_price_rows_validated_for_execution', 'promotion_allowed', 'live_mutation_allowed'), False)}
    raw['classification'] = json.dumps(capture).encode()
    raw['core'] = b'# synthetic core'
    for role in ('classification', 'core'):
        refs[role] = {'path': str(root / (role + '.data')), 'sha256': module.sha(raw[role])}
    for role, value in raw.items(): Path(refs[role]['path']).write_bytes(value)
    return raw, refs


def output_fixture(**kwargs):
    flags = dict.fromkeys(module.LEDGER_FALSE, False)
    return {'schema': 'OBSERVATION_GAP_EVIDENCE_LEDGER_V1',
        'parent_binding': copy.deepcopy(kwargs['parent_binding']),
        'old_last_observed_session_unchanged': '2026-09-24', 'missed_observation_count': 5,
        **dict.fromkeys(('observed_session_increment', 'fresh_session_increment', 'seal_increment', 'cohort_increment'), 0),
        'events': [{'session': day, 'event_recorded_at_utc': kwargs['recorded_at_utc'],
            'classification_captured_at_utc': kwargs['classification_capture']['captured_at_utc'],
            'historical_source_first_observed_at_utc': None, **flags} for day in module.DATES],
        'batches': [{key: copy.deepcopy(kwargs[key]) for key in ('classification_capture', 'classification_reference', 'recorded_at_utc')}],
        **flags}


class Tests(unittest.TestCase):
    def setUp(self):
        # Each fixture models a fresh CLI; restore the discovery import state afterward.
        isolation = patch.dict(module.sys.modules)
        isolation.start()
        self.addCleanup(isolation.stop)
        module.sys.modules.pop('backtest.ndx_observation_gap_ledger_research', None)

    def test_receipt_tail_and_source_row_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, refs = fixture(Path(directory))
            module.prepare(raw, refs)
            for role, mutate in (
                ('parent_receipt', lambda doc: doc.update(transaction_id='c' * 64)),
                ('classification', lambda doc: doc['pending_source_rows']['QQQ'][module.DATES[0]].update(Close='999')),
                ('classification', lambda doc: doc.update(candidate_seal_allowed=True)),
            ):
                changed = copy.deepcopy(raw)
                doc = json.loads(changed[role]); mutate(doc); changed[role] = json.dumps(doc).encode()
                with self.assertRaises(ValueError): module.prepare(changed, refs)
            with self.assertRaises(ValueError): module.prepare(dict(raw, parent_events=raw['parent_events'].split(b'\n', 1)[1]), refs)

    def test_copies_and_new_record_clock_separate_from_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); raw, refs = fixture(root); observed = []
            def append(**kwargs):
                observed.append(kwargs)
                return output_fixture(**kwargs)
            core = SimpleNamespace(__file__=refs['core']['path'], append_missed_observations=append)
            with patch.object(module, 'OUTPUT', root / 'out'), \
                    patch.object(module, 'PINS', {role: (ref['path'], ref['sha256']) for role, ref in refs.items()}), \
                    patch.object(module.importlib, 'import_module', return_value=core):
                module.run()
                self.assertEqual(len(observed), 1)
                self.assertNotEqual(observed[0]['recorded_at_utc'], observed[0]['classification_capture']['captured_at_utc'])
                for role, name in [('parent_manifest', 'parent_manifest.json'), ('parent_events', 'parent_events.jsonl'),
                                   ('parent_sessions', 'parent_sessions.csv'), ('parent_receipt', 'parent_receipt.json')]:
                    self.assertEqual((module.OUTPUT / name).read_bytes(), raw[role])
                    self.assertEqual(Path(refs[role]['path']).read_bytes(), raw[role])
                with self.assertRaisesRegex(ValueError, 'no retry'): module.run()
                self.assertEqual(len(observed), 1)

    def test_publication_tampering_leaves_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); raw, refs = fixture(root)
            core = SimpleNamespace(__file__=refs['core']['path'], append_missed_observations=output_fixture)
            original = module.write_json
            def write(path, value):
                digest = original(path, value)
                if path.name == 'publication.json': path.write_bytes(b'{}')
                return digest
            with patch.object(module, 'OUTPUT', root / 'out'), \
                    patch.object(module, 'PINS', {role: (ref['path'], ref['sha256']) for role, ref in refs.items()}), \
                    patch.object(module.importlib, 'import_module', return_value=core), patch.object(module, 'write_json', write):
                with self.assertRaises(ValueError): module.run()
                self.assertTrue((module.OUTPUT / 'failure.json').exists())

    def test_output_zero_boolean_authority_and_record_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, refs = fixture(Path(directory))
            prepared = module.prepare(raw, refs)
            recorded = '2026-10-02T15:00:00+00:00'
            ledger = output_fixture(**prepared, recorded_at_utc=recorded)
            module.validate_result(ledger, prepared, recorded)
            for key in ('observed_session_increment', 'fresh_session_increment', 'seal_increment', 'cohort_increment'):
                changed = copy.deepcopy(ledger); changed[key] = False
                with self.assertRaises(ValueError): module.validate_result(changed, prepared, recorded)
            changed = copy.deepcopy(ledger); changed['events'][0]['fresh_observation'] = True
            with self.assertRaises(ValueError): module.validate_result(changed, prepared, recorded)
            changed = copy.deepcopy(ledger); changed['events'][0]['event_recorded_at_utc'] = prepared['classification_capture']['captured_at_utc']
            with self.assertRaises(ValueError): module.validate_result(changed, prepared, recorded)


if __name__ == '__main__': unittest.main()
