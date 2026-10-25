from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_local_paper_monthly_update as launcher


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
        settings_hash = save('settings.json', dict(capture_index_path='capture/index.json',
            preparation_output='prepared', publish_output='published'))
        coordinator_hash = save('coordinator.json', dict(settings_path='settings.json', settings_sha256=settings_hash, stage_directory='stages'))
        bootstrap_hash = save('bootstrap.json', dict(database_path='simulation.sqlite3', audit_directory='audit'))
        policy_hash = save('policy.json', {})
        rolling_hash = save('rolling.json', dict(schema='ROLLING_MONTHLY_SIMULATION_V1', root=str(self.root),
            first_coordinator=dict(path='coordinator.json',sha256=coordinator_hash),
            bootstrap=dict(path='bootstrap.json',sha256=bootstrap_hash),policy=dict(path='policy.json',sha256=policy_hash),
            rolling_output_directory='chain', first_evidence_directory='evidence'))
        descriptor = dict(schema='LOCAL_PAPER_MONTHLY_LAUNCHER_V1', root=str(self.root), python_path=sys.executable,
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
            child = dict(status=status)
            if status == 'MONTHLY_COMPLETE_NEXT_PLAN_READY':
                child.update(result=dict(status='MONTHLY_RUNTIME_PUBLISHED'), successor=dict(status='SUCCESSOR_COORDINATOR_MATERIALIZED'))
            kwargs['stdout'].write(json.dumps(child).encode())
            return SimpleNamespace(returncode=code)
        return invoke

    def test_preview_no_launch_or_logs(self):
        with patch.object(subprocess, 'run', side_effect=AssertionError('NO_CHILD')):
            result = self.run_launcher()
        self.assertEqual(result['status'], 'VALIDATED_PREVIEW')
        self.assertFalse((self.root/'logs').exists())

    def test_waiting_failure_success_are_distinct_and_logged(self):
        for status, code, expected in [('WAITING_SESSION_CLOSE',0,'WAITING'),
                ('MONTHLY_COMPLETE_NEXT_PLAN_READY',0,'SUCCESS'),('RECOVERY_REQUIRED',0,'NEEDS_RECOVERY'),
                ('WAITING_REVIEW',0,'NEEDS_REVIEW'),('WAITING_SESSION_CLOSE',9,'FAILED'),
                ('WAITING_ACCOUNT',0,'NEEDS_INITIALIZATION')]:
            with self.subTest(status=status, code=code), patch.object(subprocess,'run',side_effect=self.child(status,code)):
                self.assertEqual(self.run_launcher(True)['status'], expected)
        self.assertEqual(len(list((self.root/'logs').glob('*/finished.json'))), 6)
        self.assertEqual(len(list((self.root/'logs').glob('*/stdout.txt'))), 6)
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
            (self.root/'scripts/run_rolling_monthly_simulation.py').write_text('changed')
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
        for status in ('FAILED', 'NEEDS_INITIALIZATION', 'NEEDS_RECOVERY', 'NEEDS_REVIEW'):
            with patch.object(launcher,'run',return_value={'status':status}):
                self.assertEqual(launcher.main(['--config-path','unused','--config-sha256','unused']),2)

    def test_reselection_and_false_success_require_review(self):
        result = launcher.classify(dict(status='BLOCKED', reason='RESELECT_REQUIRED'),0)
        self.assertEqual(result['status'], 'NEEDS_REVIEW')
        self.assertIn('no historical backfill', result['explanation'])
        with self.assertRaisesRegex(ValueError, 'SUCCESS_EVIDENCE_MISSING'):
            launcher.classify(dict(status='MONTHLY_COMPLETE_NEXT_PLAN_READY'),0)
        with self.assertRaisesRegex(ValueError, 'STATUS_UNKNOWN'):
            launcher.classify(dict(status='unknown'),0)

    def test_log_directory_cannot_touch_existing_paper_capture(self):
        descriptor = json.loads((self.root/'launcher.json').read_bytes())
        descriptor['log_directory'] = 'capture/logs'
        self.digest = self.save('launcher.json', descriptor)
        with self.assertRaisesRegex(ValueError, 'LOG_OVERLAP'):
            self.run_launcher(True)
        self.assertFalse((self.root/'capture').exists())


if __name__ == '__main__':
    unittest.main()
