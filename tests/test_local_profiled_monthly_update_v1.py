"""Launcher boundary tests; child market/release behavior is tested separately."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import run_local_profiled_monthly_update_v1 as launcher


class LauncherTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        pins = {}
        for name in launcher.SOURCES:
            raw = (Path(launcher.__file__).resolve().parents[1] / name).read_bytes()
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        schedule = self.save('rolling.json', dict(
            schema='ROLLING_PROFILED_MONTHLY_UPDATE_V1',
            output_directory='chain', source_pins=pins))
        self.digest = self.save('launcher.json', dict(
            schema='LOCAL_PROFILED_MONTHLY_LAUNCHER_V1',
            schedule=dict(path='rolling.json', sha256=schedule),
            log_directory='logs', source_pins=pins))

    def save(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(value).encode()
        path.write_bytes(raw)
        return sha256(raw).hexdigest()

    def run_launcher(self, execute=False):
        return launcher.run(root=self.root, config_path='launcher.json',
                            config_sha256=self.digest, execute=execute)

    def test_preview_does_not_execute_child_or_create_logs(self):
        with patch.object(launcher, 'scheduled_run', return_value={
                'status': 'WAITING_SESSION_CLOSE'}) as child:
            self.assertEqual(self.run_launcher()['status'], 'WAITING_SESSION_CLOSE')
        self.assertNotIn('execute', child.call_args.kwargs)
        self.assertFalse((self.root / 'logs').exists())

    def test_existing_lock_is_preserved_without_running_child(self):
        self.save('logs/running.lock', {'pid': 123, 'reason': 'preserved'})
        before = (self.root / 'logs/running.lock').read_bytes()
        with patch.object(launcher, 'scheduled_run', side_effect=AssertionError('NO_RUN')):
            result = self.run_launcher(True)
        self.assertEqual(result['status'], 'NEEDS_RECOVERY')
        self.assertFalse(result['automatic_retry'])
        self.assertEqual((self.root / 'logs/running.lock').read_bytes(), before)
        self.assertEqual(list((self.root / 'logs').glob('*/started.json')), [])

    def test_failure_is_logged_and_owned_lock_released(self):
        with patch.object(launcher, 'scheduled_run', side_effect=ValueError('SOURCE_FAILED')):
            result = self.run_launcher(True)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['reason'], 'SOURCE_FAILED')
        self.assertFalse(result['automatic_retry'])
        receipts = list((self.root / 'logs').glob('*/finished.json'))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(json.loads(receipts[0].read_bytes())['result'], result)
        self.assertFalse((self.root / 'logs/running.lock').exists())
        self.assertFalse((self.root / 'data/strategy_account').exists())

    def test_post_execution_source_drift_blocks_success(self):
        def drift(**kwargs):
            self.assertTrue(kwargs['execute'])
            (self.root / 'scripts/run_rolling_profiled_monthly_update_v1.py').write_text('changed')
            return dict(status='WAITING_SESSION_CLOSE')
        with patch.object(launcher, 'scheduled_run', side_effect=drift):
            result = self.run_launcher(True)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('SOURCE', result['reason'])
        with patch.object(launcher, 'scheduled_run', side_effect=AssertionError('NO_RUN')):
            with self.assertRaises(ValueError):
                self.run_launcher(True)


if __name__ == '__main__':
    unittest.main()
