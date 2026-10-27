import importlib.util
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'data'


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


groups = load('candidate_groups', 'news_evidence_groups.py')
with patch.dict(sys.modules, {'data.news_evidence_groups': groups}):
    history = load('candidate_history', 'news_observation_history.py')


def event(body='first', stamp='2026-10-27T01:00:00+00:00'):
    return dict(url='https://example.com/release', source_text=body,
                collected_at=stamp, source='Issuer', account_balance=12345)


class ObservationHistoryTests(unittest.TestCase):
    def test_missing_get_never_creates_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'absent'
            self.assertEqual(history.read_history(target)['status'], 'NO_RECORDED_HISTORY')
            self.assertFalse(target.exists())

    def test_atomic_retry_preserves_versions_time_and_public_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            row = event()
            row.update(published_at='2026-01-01T00:00:00+00:00',
                       uncertainty=['Only a truncated excerpt'], summary='AI text')
            history.append_observations(directory, [row, event('second')])
            history.append_observations(directory, [row, event('second')])
            result = history.read_history(directory)
            self.assertEqual(len(result['batches']), 1)
            self.assertEqual(len(result['evidence']['observations']), 2)
            self.assertEqual(result['evidence']['observations'][0]['collected_at'], row['collected_at'])
            self.assertNotIn('account_balance', result['evidence']['observations'][0])
            self.assertNotIn('summary', result['evidence']['observations'][0])
            self.assertEqual(result['evidence']['observations'][0]['published_at'], row['published_at'])
            self.assertEqual(result['evidence']['observations'][0]['source_uncertainty'], row['uncertainty'])
            self.assertIn('recorded_at', result['batches'][0])
            self.assertTrue(result['evidence']['same_url_groups'][0]['has_observed_text_variants'])

    def test_invalid_batch_does_not_partially_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            history.append_observations(directory, [event()])
            with self.assertRaises(ValueError):
                history.append_observations(directory, [event('new'), event(stamp='bad')])
            self.assertEqual(len(history.read_history(directory)['batches']), 1)

    def test_bounded_read_does_not_prune_and_get_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            for index in range(3):
                history.append_observations(directory, [event(str(index))])
            path = Path(directory) / history.DATABASE
            original = path.read_bytes()
            self.assertTrue(history.read_history(directory, batch_limit=1)['truncated'])
            self.assertTrue(history.read_history(directory, event_limit=1)['truncated'])
            self.assertEqual(len(history.read_history(directory)['batches']), 3)
            self.assertEqual(path.read_bytes(), original)

    def test_corruption_is_not_empty_success(self):
        with tempfile.TemporaryDirectory() as directory:
            history.append_observations(directory, [event()])
            with closing(sqlite3.connect(Path(directory) / history.DATABASE)) as connection, connection:
                connection.execute("UPDATE batches SET payload='[]'")
            with self.assertRaisesRegex(ValueError, 'INTEGRITY'):
                history.read_history(directory)

    def test_limits_and_naive_time_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                history.append_observations(directory, [event()] * 251)
            with self.assertRaises(ValueError):
                history.append_observations(directory, [event(stamp='2026-10-27')])
            with self.assertRaises(ValueError):
                history.read_history(directory, batch_limit=33)


if __name__ == '__main__':
    unittest.main()
