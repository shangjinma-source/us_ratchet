from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_local_real_monthly_update as launcher


class LauncherTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        def save(name, value):
            path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(value).encode(); path.write_bytes(raw)
            return sha256(raw).hexdigest()
        self.save = save
        pins = {}
        for name in launcher.REQUIRED_SOURCE_PATHS:
            raw = (Path(launcher.__file__).resolve().parents[1]/name).read_bytes()
            target = self.root/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        rolling_hash = save('rolling.json', dict(schema='ROLLING_REAL_MONTHLY_UPDATE_V1', root=str(self.root),
            scheduled_config='first.json', scheduled_sha256='0'*64, output_directory='chain', source_pins=pins))
        descriptor = dict(schema='LOCAL_REAL_MONTHLY_LAUNCHER_V1', root=str(self.root), python_path=sys.executable,
            rolling_config='rolling.json', rolling_sha256=rolling_hash, log_directory='logs', source_pins=pins)
        self.digest = save('launcher.json', descriptor)

    def run_launcher(self, execute=False):
        return launcher.run(config_path=self.root/'launcher.json', config_sha256=self.digest, execute=execute)

    def child(self, status, code=0):
        def invoke(command, **kwargs):
            self.assertEqual(kwargs['cwd'], self.root)
            self.assertEqual(kwargs['timeout'], 7200)
            self.assertIn('creationflags', kwargs)
            self.assertEqual(command[-1], '--execute')
            kwargs['stdout'].write(json.dumps(dict(status=status)).encode())
            return SimpleNamespace(returncode=code)
        return invoke

    def test_preview_no_launch_or_logs(self):
        with patch.object(subprocess, 'run', side_effect=AssertionError('NO_CHILD')):
            result = self.run_launcher()
        self.assertEqual(result['status'], 'VALIDATED_PREVIEW')
        self.assertFalse((self.root/'logs').exists())

    def test_waiting_failure_success_are_distinct_and_logged(self):
        for status, code, expected in [('WAITING_SESSION_CLOSE',0,'WAITING'),
                ('MARKET_PREPARATION_PHASE',0,'SUCCESS'),('MISSED_PREPARATION_WINDOW',1,'FAILED'),
                ('WAITING_REVIEW',0,'FAILED'),('WAITING_SESSION_CLOSE',9,'FAILED')]:
            with self.subTest(status=status, code=code), patch.object(subprocess,'run',side_effect=self.child(status,code)):
                self.assertEqual(self.run_launcher(True)['status'], expected)
        self.assertEqual(len(list((self.root/'logs').glob('*/finished.json'))), 5)
        self.assertEqual(len(list((self.root/'logs').glob('*/stdout.txt'))), 5)
        self.assertFalse((self.root/'logs/running.lock').exists())

    def test_stale_lock_preserved_and_no_child(self):
        self.save('logs/running.lock', {'pid':123})
        with patch.object(subprocess,'run',side_effect=AssertionError('NO_CHILD')):
            self.assertEqual(self.run_launcher(True)['status'], 'SKIPPED')
        self.assertTrue((self.root/'logs/running.lock').exists())

    def test_timeout_preserves_logs_and_reports_reconcile(self):
        with patch.object(subprocess,'run',side_effect=subprocess.TimeoutExpired('child',7200)):
            result = self.run_launcher(True)
        self.assertEqual(result['reason'], 'CHILD_TIMEOUT_RECONCILE_BEFORE_RETRY')
        self.assertFalse(result['automatic_retry'])
        self.assertTrue(list((self.root/'logs').glob('*/stderr.txt')))

    def test_unapproved_source_rejected_and_post_drift_is_failed(self):
        def drift(command, **kwargs):
            (self.root/'scripts/run_rolling_real_monthly_update.py').write_text('changed')
            return self.child('WAITING_SESSION_CLOSE')(command, **kwargs)
        with patch.object(subprocess,'run',side_effect=drift):
            self.assertEqual(self.run_launcher(True)['status'], 'FAILED')
        with patch.object(subprocess,'run',side_effect=AssertionError('NO_CHILD')):
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'): self.run_launcher(True)

    def test_malformed_output_is_not_success(self):
        def invalid(command, **kwargs):
            kwargs['stdout'].write(b'not json')
            return SimpleNamespace(returncode=0)
        with patch.object(subprocess,'run',side_effect=invalid):
            self.assertEqual(self.run_launcher(True)['reason'], 'LAUNCHER_CHILD_JSON_INVALID')

    def test_cli_failed_exit_code(self):
        with patch.object(launcher,'run',return_value={'status':'FAILED'}):
            self.assertEqual(launcher.main(['--config-path','unused','--config-sha256','unused']),2)


if __name__ == '__main__':
    unittest.main()
