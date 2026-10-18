import copy
from datetime import date, timedelta
import json
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_observation_gap_frontier_20261002 as module


def fixture(root):
    parent = root / 'parent'; parent.mkdir()
    start = date(2026, 7, 1)
    days = [(start + timedelta(days=i)).isoformat() for i in range(86)
            if (start + timedelta(days=i)).weekday() < 5]
    days = days[:59] + ['2026-09-24']
    gaps = ['2026-09-25', '2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01']
    raw = {'parent_sessions': ('session_date\n' + ''.join(day + '\n' for day in days)).encode()}
    raw['QQQ'] = raw['SPY'] = ('Date,Close\n' + ''.join(day + ',100\n' for day in days + gaps)).encode()
    refs = {role: {'path': str(parent / 'parent_sessions.csv' if role == 'parent_sessions' else root / (role + '.csv')),
                   'sha256': module.sha(blob)} for role, blob in raw.items()}
    old_ref = {'path': str(root / 'old_sessions.csv'), 'sha256': refs['parent_sessions']['sha256']}
    flags = dict.fromkeys(module.PURE_FALSE, False)
    ledger = {'schema': 'OBSERVATION_GAP_EVIDENCE_LEDGER_V1',
        'parent_binding': {'event_count': 66, 'session_count': 60, 'last_session': '2026-09-24', 'session_projection_reference': old_ref},
        'old_last_observed_session_unchanged': '2026-09-24', 'missed_observation_count': 5,
        'batches': [{'classification_capture': {'captured_source_references': {ticker: refs[ticker] for ticker in ('QQQ', 'SPY')}}}],
        'events': [{'session': day, 'schema': 'MISSED_OBSERVATION_EVIDENCE_EVENT_V1', 'event_type': 'MISSED_OBSERVATION',
                    'event_sequence': 67 + index, 'event_sha256': str(index) * 64, **flags} for index, day in enumerate(gaps)],
        **dict.fromkeys(('observed_session_increment', 'fresh_session_increment', 'seal_increment', 'cohort_increment'), 0), **flags}
    raw['ledger'] = json.dumps(ledger).encode()
    refs['ledger'] = {'path': str(parent / 'ledger.json'), 'sha256': module.sha(raw['ledger'])}
    receipt = {'schema': 'OBSERVATION_GAP_LEDGER_PUBLICATION_V1', 'status': 'PUBLISHED_MISSED_OBSERVATION_EVIDENCE_ONLY',
        'artifacts': {'ledger': refs['ledger'], 'parent_sessions': refs['parent_sessions']},
        'input_references': {'parent_sessions': old_ref, **{ticker: refs[ticker] for ticker in ('QQQ', 'SPY')}}, **module.FLAGS}
    raw['publication'] = json.dumps(receipt).encode()
    refs['publication'] = {'path': str(parent / 'publication.json'), 'sha256': module.sha(raw['publication'])}
    raw['core'] = b'# synthetic source pin'
    refs['core'] = {'path': str(root / 'core.py'), 'sha256': module.sha(raw['core'])}
    for role, blob in raw.items(): Path(refs[role]['path']).write_bytes(blob)
    for name in module.PARENT_FILES:
        path = parent / name
        if not path.exists(): path.write_text('{}')
    return raw, refs


def pure():
    return runpy.run_path(str(module.ROOT / 'backtest/ndx_observation_gap_frontier_research.py'))['prepare_observation_frontier']


class Tests(unittest.TestCase):
    def setUp(self):
        # Each fixture models a fresh CLI; restore the discovery import state afterward.
        isolation = patch.dict(module.sys.modules)
        isolation.start()
        self.addCleanup(isolation.stop)
        module.sys.modules.pop('backtest.ndx_observation_gap_frontier_research', None)

    def test_full_common_prefix_and_source_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, refs = fixture(Path(directory))
            prepared = module.prepare(raw, refs)
            self.assertEqual(len(prepared['common_dates']), 65)
            changed = copy.deepcopy(raw)
            changed['SPY'] = raw['SPY'].replace(b'2026-07-02,100\n', b'')
            with self.assertRaises(ValueError): module.prepare(changed, refs)
            receipt = json.loads(raw['publication']); receipt['input_references']['QQQ'] = refs['SPY']
            with self.assertRaises(ValueError): module.prepare(dict(raw, publication=json.dumps(receipt).encode()), refs)

    def test_synthetic_pure_contract_not_eligibility(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, refs = fixture(Path(directory)); prepared = module.prepare(raw, refs)
            result = pure()(parent_session_dates=prepared['parent_dates'], gap_ledger=prepared['ledger'], common_source_session_dates=prepared['common_dates'])
            module.validate_result(result, prepared)
            for key, value in [('fresh_session_increment', False), ('future_timeliness_granted', True), ('last_observed_session', '2026-10-01')]:
                changed = copy.deepcopy(result); changed[key] = value
                with self.assertRaises(ValueError): module.validate_result(changed, prepared)

    def test_createonly_and_publication_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); raw, refs = fixture(root)
            callback = pure()
            loaded = SimpleNamespace(__file__=refs['core']['path'], prepare_observation_frontier=callback)
            original = module.write_new
            def write(path, value):
                digest = original(path, value)
                if path.name == 'publication.json': path.write_bytes(b'{}')
                return digest
            with patch.object(module, 'OUTPUT', root / 'out'), patch.object(module, 'PINS', {role: (ref['path'], ref['sha256']) for role, ref in refs.items()}), \
                    patch.object(module.importlib, 'import_module', return_value=loaded), patch.object(module, 'write_new', write):
                with self.assertRaisesRegex(ValueError, 'Final publication'): module.run()
                self.assertTrue((module.OUTPUT / 'failure.json').exists())
                with self.assertRaisesRegex(ValueError, 'no retry'): module.run()

    def test_pending_pin_does_not_read_parents(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(module, 'OUTPUT', Path(directory) / 'out'), \
                patch.object(module, 'PINS', {'core': ('missing.py', None)}), patch.object(module, 'prepare') as prepare:
            with self.assertRaisesRegex(ValueError, 'Pending'): module.run()
            prepare.assert_not_called()


if __name__ == '__main__': unittest.main()
