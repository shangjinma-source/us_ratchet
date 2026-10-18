from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_forward_source_capture_20261002 as module


def fixture(root):
    parent = root / 'parent'; parent.mkdir()
    cache = root / 'data/cache'; cache.mkdir(parents=True)
    raw = {'baseline_QQQ': b'Date,Close\n2026-10-01,100\n', 'baseline_SPY': b'Date,Close\n2026-10-01,101\n',
           'tzif': b'synthetic tzif - never parsed', 'core': b'# synthetic core - never executed'}
    refs = {role: {'path': str(root / (role + '.bin')), 'sha256': module.sha(value)} for role, value in raw.items()}
    frontier = {'schema': 'OBSERVATION_GAP_FRONTIER_RESEARCH_V1', 'source_hashes': {'sealed': 'a' * 64},
        'last_observed_session': '2026-09-24', 'last_accounted_gap_session': '2026-10-01',
        'last_accounted_session': '2026-10-01', 'known_accounted_rows': [{} for _ in range(65)],
        'unaccounted_source_dates': [], 'input_references': {ticker: refs['baseline_' + ticker] for ticker in ('QQQ', 'SPY')},
        **module.FLAGS}
    raw['frontier'] = json.dumps(frontier).encode()
    refs['frontier'] = {'path': str(parent / 'frontier.json'), 'sha256': module.sha(raw['frontier'])}
    receipt = {'schema': 'OBSERVATION_GAP_FRONTIER_PUBLICATION_V1', 'status': 'PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY',
        'frontier_reference': refs['frontier'], 'source_hashes': frontier['source_hashes'], **module.FLAGS}
    raw['frontier_publication'] = json.dumps(receipt).encode()
    refs['frontier_publication'] = {'path': str(parent / 'publication.json'), 'sha256': module.sha(raw['frontier_publication'])}
    for role, value in raw.items(): Path(refs[role]['path']).write_bytes(value)
    (parent / 'started.json').write_text('{}')
    for ticker in ('QQQ', 'SPY'): (cache / (ticker + '.csv')).write_bytes(raw['baseline_' + ticker])
    return raw, refs, frontier, receipt


class Tests(unittest.TestCase):
    def setUp(self):
        # Each fixture models a fresh CLI; restore the discovery import state afterward.
        isolation = patch.dict(module.sys.modules)
        isolation.start()
        self.addCleanup(isolation.stop)
        module.sys.modules.pop('backtest.ndx_forward_source_capture_research', None)

    def test_result_guard_rejects_hash_clock_and_nested_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, refs, frontier, receipt = fixture(Path(directory))
            frontier['known_accounted_rows'] = [{'session': '2026-10-01'}]
            current = {ticker: raw['baseline_' + ticker] for ticker in ('QQQ', 'SPY')}
            result = {'schema': 'FORWARD_SOURCE_CAPTURE_PLANNING_V1',
                'capture_started_at_utc': 'start', 'observed_at_utc': 'end',
                'source_sha256': {ticker: module.sha(value) for ticker, value in current.items()},
                'baseline_sha256': {ticker: module.sha(value) for ticker, value in current.items()},
                'tzif_sha256': module.sha(raw['tzif']), 'accounted_prefix_dates': ['2026-10-01'],
                'last_observed_session_unchanged': '2026-09-24', 'last_accounted_session_unchanged': '2026-10-01',
                'month_first_semantics': 'UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE',
                'classifications': [], 'timeliness_candidate': dict.fromkeys(module.PLAN_FALSE, False),
                **dict.fromkeys(module.PLAN_FALSE, False)}
            module.validate_result(result, frontier, current, raw, 'start', 'end')
            result['timeliness_candidate']['candidate_seal_allowed'] = True
            with self.assertRaises(ValueError): module.validate_result(result, frontier, current, raw, 'start', 'end')
            result['timeliness_candidate']['candidate_seal_allowed'] = False
            with self.assertRaises(ValueError): module.validate_result(result, frontier, current, raw, 'other', 'end')
            result['source_sha256']['QQQ'] = '0' * 64
            with self.assertRaises(ValueError): module.validate_result(result, frontier, current, raw, 'start', 'end')

    def test_frontier_receipt_baseline_and_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, refs, frontier, receipt = fixture(Path(directory))
            module.validate_parent(frontier, receipt, refs)
            frontier['input_references']['QQQ'] = refs['baseline_SPY']
            with self.assertRaises(ValueError): module.validate_parent(frontier, receipt, refs)
            frontier['input_references']['QQQ'] = refs['baseline_QQQ']
            receipt['cohort_registration_allowed'] = True
            with self.assertRaises(ValueError): module.validate_parent(frontier, receipt, refs)

    def test_raw_preserved_on_classifier_failure_clock_and_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); raw, refs, _, _ = fixture(root); calls = []; trace = []
            instants = [datetime(2026, 10, 2, 15, 0, 0, tzinfo=timezone.utc), datetime(2026, 10, 2, 15, 0, 1, tzinfo=timezone.utc)]
            def now(zone):
                trace.append('clock'); return instants[len([x for x in trace if x == 'clock']) - 1]
            original_read = Path.read_bytes
            def read(path):
                if path.parent == root / 'data/cache': trace.append(path.name)
                return original_read(path)
            def classify(**kwargs):
                calls.append(kwargs)
                raise ValueError('synthetic classification failure')
            core = SimpleNamespace(__file__=refs['core']['path'], plan_forward_source_capture=classify)
            with patch.object(module, 'ROOT', root), patch.object(module, 'OUTPUT', root / 'output'), \
                    patch.object(module, 'PINS', {role: (ref['path'], ref['sha256']) for role, ref in refs.items()}), \
                    patch.object(module.importlib, 'import_module', return_value=core), \
                    patch.object(module, 'datetime', SimpleNamespace(now=now)), patch.object(Path, 'read_bytes', read):
                with self.assertRaisesRegex(ValueError, 'synthetic classification'): module.run()
                self.assertEqual(trace[:4], ['clock', 'QQQ.csv', 'SPY.csv', 'clock'])
                self.assertEqual(calls[0]['capture_started_at_utc'], instants[0].isoformat())
                self.assertEqual(calls[0]['observed_at_utc'], instants[1].isoformat())
                for ticker in ('QQQ', 'SPY'):
                    self.assertEqual((module.OUTPUT / (ticker + '.csv')).read_bytes(), raw['baseline_' + ticker])
                    self.assertEqual(calls[0]['source_csv_bytes'][ticker], raw['baseline_' + ticker])
                self.assertEqual((module.OUTPUT / 'New_York.tzif').read_bytes(), raw['tzif'])
                self.assertEqual(calls[0]['tzif_bytes'], raw['tzif'])
                self.assertTrue((module.OUTPUT / 'failure.json').exists())
                with self.assertRaisesRegex(ValueError, 'no retry'): module.run()
                self.assertEqual(len(calls), 1)

    def test_current_cache_drift_rejected_before_classification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); raw, refs, _, _ = fixture(root); original = Path.read_bytes; changed = []
            def read(path):
                value = original(path)
                if path == root / 'data/cache/QQQ.csv' and not changed:
                    changed.append(True); path.write_bytes(value + b'2026-10-02,102\n')
                return value
            core = SimpleNamespace(__file__=refs['core']['path'], plan_forward_source_capture=lambda **kwargs: self.fail('Must not classify drifting source'))
            with patch.object(module, 'ROOT', root), patch.object(module, 'OUTPUT', root / 'output'), \
                    patch.object(module, 'PINS', {role: (ref['path'], ref['sha256']) for role, ref in refs.items()}), \
                    patch.object(module.importlib, 'import_module', return_value=core), patch.object(Path, 'read_bytes', read):
                with self.assertRaisesRegex(ValueError, 'Source drift'): module.run()
                self.assertFalse(module.OUTPUT.exists())


if __name__ == '__main__': unittest.main()
