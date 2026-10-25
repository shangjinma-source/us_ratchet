"""Runner orchestration only; source and market review have separate tests."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.strategy_daily_advice_journal_v1 import encoded
from data.strategy_followup_queue_v1 import IDENTITY_FIELDS, store_plans
from scripts import run_current_daily_followups_v2 as runner


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'data/strategy_advice_followup'
        close = datetime.now(timezone.utc) - timedelta(days=1)
        self.row = {key: 'test' for key in IDENTITY_FIELDS}
        self.row.update(side='BUY', order_index=0, horizon_sessions=1,
            ticker='SNDK', reference_limit='100', reference_quantity=1,
            reference_session=(close.date()-timedelta(days=1)).isoformat(),
            observation_session=close.date().isoformat(), observation_close=close.isoformat(),
            final_return_sha256='f'*64, capture_admitted=False,
            actual_fill_inferred=False, performance_computed=False)
        self.row['observation_id'] = sha256(encoded({key:self.row[key] for key in IDENTITY_FIELDS})).hexdigest()
        self.queue = self.patch('queue_run', side_effect=self.plan)
        self.audit = self.patch('audit', return_value={'rows':[{
            'event_id':'test', 'status':'ARCHIVE_INTEGRITY_AND_TARGET_RECOMPUTED'}]})
        self.capture = self.patch('capture', return_value={'network_calls':2})
        self.archive = self.patch('archive', side_effect=self.publish)
        self.read = self.patch('read_observation', return_value={'verified':True})

    def patch(self, name, **kwargs):
        manager = patch.object(runner, name, **kwargs)
        result = manager.start()
        self.addCleanup(manager.stop)
        return result

    def plan(self, root, *, execute, include_plans):
        self.assertTrue(include_plans)
        if execute:store_plans(self.base/'queue', [self.row])
        return {'plans':[dict(self.row)], 'observations':1}

    def publish(self, root, *, capture_path):
        folder = self.base/'results/index'
        folder.mkdir(parents=True, exist_ok=True)
        (folder/(self.row['observation_id']+'.json')).write_text('{}')
        return {'observations':1, 'readback_verified':True}

    def test_publish_once_then_verify_without_capture(self):
        first = runner.run(root=self.root, execute=True)
        self.assertEqual(first['status'], 'PUBLISHED')
        second = runner.run(root=self.root, execute=True)
        self.assertEqual(second['completed_verified'], 1)
        self.assertEqual(second['network_calls'], 0)
        self.capture.assert_called_once()
        self.archive.assert_called_once()
        self.assertFalse((self.base/'runner_v1/active.json').exists())
        self.assertEqual(len(list((self.base/'runner_v1/runs').glob('*/complete.json'))), 2)

    def test_failure_preserves_evidence_and_blocks_retry(self):
        self.capture.side_effect = RuntimeError('source unavailable')
        with self.assertRaisesRegex(RuntimeError, 'source unavailable'):
            runner.run(root=self.root, execute=True)
        self.assertTrue((self.base/'runner_v1/active.json').exists())
        failures = list((self.base/'runner_v1/runs').glob('*/failed.json'))
        self.assertEqual(len(failures), 1)
        self.assertFalse(json.loads(failures[0].read_text())['automatic_retry'])
        self.assertEqual(runner.run(root=self.root, execute=True)['status'], 'NEEDS_RECOVERY')
        self.capture.assert_called_once()
        self.archive.assert_not_called()

    def test_future_plans_read_only_and_execute_do_not_capture(self):
        self.row['observation_close'] = (datetime.now(timezone.utc)+timedelta(days=5)).isoformat()
        for execute in (False, True):
            result = runner.run(root=self.root, execute=execute)
            self.assertEqual(result['waiting'], 1)
            self.assertEqual(result['status'], 'WAIT_OBSERVATION_CLOSE')
        self.capture.assert_not_called()
        self.audit.assert_not_called()

    def test_changed_queue_date_rejected_before_capture(self):
        store_plans(self.base/'queue', [self.row])
        path = self.base/'queue'/(self.row['observation_id']+'.json')
        row = json.loads(path.read_text())
        row['observation_close'] = '2000-01-01T00:00:00+00:00'
        path.write_bytes(encoded(row))
        with self.assertRaisesRegex(Exception, 'QUEUE_PLAN_CONFLICT'):
            runner.run(root=self.root)
        self.capture.assert_not_called()

    def test_corrupt_existing_result_does_not_recapture(self):
        self.publish(self.root, capture_path=None)
        self.read.side_effect = ValueError('broken result')
        with self.assertRaisesRegex(ValueError, 'broken result'):
            runner.run(root=self.root, execute=True)
        self.capture.assert_not_called()
        self.assertTrue((self.base/'runner_v1/active.json').exists())

    def test_unapproved_source_not_dispatched(self):
        self.audit.return_value = {'rows':[]}
        result = runner.run(root=self.root, execute=True)
        self.assertEqual(result['status'], 'SOURCE_REVIEW_BLOCKED')
        self.assertEqual(result['blocked'], [self.row['observation_id']])
        self.capture.assert_not_called()


if __name__ == '__main__':unittest.main()
