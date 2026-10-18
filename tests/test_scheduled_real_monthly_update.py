from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import run_scheduled_real_monthly_update as runner


class PhaseTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        def save(name, value):
            path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value), encoding='utf-8')
            return sha256(path.read_bytes()).hexdigest()
        self.save = save
        pins = {}
        source = Path(runner.__file__).resolve().parents[1]
        for name in runner.REQUIRED_SOURCE_PATHS:
            raw = (source/name).read_bytes(); path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        boundary = save('boundary.json', dict(decision_close_at='2026-10-30T20:00:00+00:00',active_open_at='2026-11-02T14:30:00+00:00'))
        schedule = save('schedule.json', dict(sessions=[dict(open_at='2026-11-02T14:30:00+00:00',close_at='2026-11-02T21:00:00+00:00')]))
        settings = save('settings.json', dict(calendar_path='boundary.json',schedule_path='schedule.json',
            fixed_source_hashes={'boundary.json':boundary,'schedule.json':schedule},
            preparation_output='prepared',publish_output='published',capture_index_path='capture/index.json'))
        coordinator = save('coordinator.json',dict(root=str(self.root),settings_path='settings.json',settings_sha256=settings,stage_directory='stage'))
        self.config = dict(schema='SCHEDULED_REAL_MONTHLY_UPDATE_V1',root=str(self.root),
            coordinator_config='coordinator.json',coordinator_sha256=coordinator,
            bootstrap_config='bootstrap.json',bootstrap_sha256=save('bootstrap.json',{}),
            policy_path='policy.json',policy_sha256=save('policy.json',{}),
            descriptor_path='descriptor.json',descriptor_sha256=save('descriptor.json',{}),
            market_output_directory='market',update_output_directory='update',run_directory='runs',source_pins=pins)
        self.now = datetime.fromisoformat('2026-10-29T20:00:00+00:00')
        self.producer = self.enterContext(patch.object(runner,'produce',return_value={'status':'PREFLIGHT_ONLY'}))
        self.updater = self.enterContext(patch.object(runner,'update',return_value={'status':'MONTHLY_DATA_RELEASE_ADOPTED'}))

    def run_phase(self, execute=False):
        digest = self.save('config.json',self.config)
        return runner.run(config_path=self.root/'config.json',config_sha256=digest,execute=execute,clock=lambda:self.now)

    def test_preflight_and_before_close_no_network_no_directory(self):
        self.assertEqual(self.run_phase()['status'],'WAITING_SESSION_CLOSE')
        self.assertFalse((self.root/'runs').exists())
        self.run_phase(True)
        self.assertNotIn('execute',self.producer.call_args.kwargs)
        self.updater.assert_not_called()

    def test_preparation_only_between_boundaries(self):
        self.now = datetime.fromisoformat('2026-10-31T01:00:00+00:00')
        self.run_phase(True)
        self.assertTrue(self.producer.call_args.kwargs['execute'])
        self.updater.assert_not_called()

    def test_late_missing_package_never_catches_up(self):
        self.now = datetime.fromisoformat('2026-11-02T15:00:00+00:00')
        self.assertEqual(self.run_phase(True)['status'],'MISSED_PREPARATION_WINDOW')
        self.producer.assert_not_called(); self.updater.assert_not_called()

    def test_fresh_review_only_regular_session(self):
        self.save('market/complete.json',{})
        for value in ('2026-11-02T14:45:00+00:00','2026-11-02T21:00:00+00:00','2026-11-03T15:00:00+00:00'):
            self.now = datetime.fromisoformat(value)
            self.assertEqual(self.run_phase(True)['status'],'WAITING_REGULAR_REVIEW_WINDOW')
        self.updater.assert_not_called()
        self.now = datetime.fromisoformat('2026-11-02T15:00:00+00:00')
        self.run_phase(True); self.assertTrue(self.updater.call_args.kwargs['execute'])
        self.assertNotIn('execute',self.producer.call_args.kwargs)

    def test_fresh_review_clock_cannot_cross_close(self):
        self.save('market/complete.json',{})
        self.now = datetime.fromisoformat('2026-11-02T20:59:00+00:00')
        def cross_close(**kwargs):
            self.now = datetime.fromisoformat('2026-11-02T21:00:00+00:00')
            kwargs['clock']()
        self.updater.side_effect=cross_close
        with self.assertRaisesRegex(ValueError,'REGULAR_REVIEW_WINDOW_ELAPSED'):
            self.run_phase(True)

    def test_overlapping_output_rejected(self):
        self.config['run_directory']='market/logs'
        with self.assertRaisesRegex(ValueError,'OUTPUT_DIRECTORIES_OVERLAP'):
            self.run_phase(True)
        self.producer.assert_not_called()

    def test_review_source_drift_before_activation_clock_rejected(self):
        self.save('market/complete.json',{})
        self.now = datetime.fromisoformat('2026-11-02T15:00:00+00:00')
        def drift(**kwargs):
            (self.root/'scripts/run_real_monthly_release_update.py').write_text('changed')
            kwargs['clock']()
        self.updater.side_effect=drift
        with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'): self.run_phase(True)

    def test_waiting_review_package_not_passed_to_update(self):
        self.save('market/complete.json',{})
        self.now = datetime.fromisoformat('2026-11-02T15:00:00+00:00')
        self.producer.return_value={'status':'WAITING_REVIEW'}
        self.assertEqual(self.run_phase(True)['status'],'WAITING_REVIEW')
        self.updater.assert_not_called()

    def test_absolute_late_path_rejected_before_production(self):
        self.config['descriptor_path']=str(self.root/'descriptor.json')
        with self.assertRaisesRegex(ValueError,'SCHEDULED_RELATIVE_PATH_REQUIRED'): self.run_phase(True)
        self.producer.assert_not_called()

    def test_cli_failures_are_nonzero(self):
        with patch.object(runner, 'run', return_value={'status':'MISSED_PREPARATION_WINDOW'}):
            self.assertEqual(runner.main(['--config-path','unused','--config-sha256','unused']),1)
        with patch.object(runner, 'run', side_effect=ValueError('SOURCE_CHANGED')):
            self.assertEqual(runner.main(['--config-path','unused','--config-sha256','unused']),1)

    def test_saved_review_reconciles_outside_session(self):
        self.save('market/complete.json',{}); self.save('update/review/ready.json',{})
        self.now = datetime.fromisoformat('2026-11-02T22:00:00+00:00')
        self.run_phase(True); self.updater.assert_called_once()

    def test_lock_and_source_drift_fail_before_dispatch(self):
        self.save('runs/running.lock',{})
        with self.assertRaises(FileExistsError): self.run_phase(True)
        self.producer.assert_not_called()
        (self.root/'runs/running.lock').unlink()
        (self.root/'scripts/run_real_monthly_release_update.py').write_text('changed')
        with self.assertRaises(ValueError): self.run_phase(True)
        self.producer.assert_not_called()

    def test_post_source_drift_is_recorded_and_not_success(self):
        def drift(**kwargs):
            (self.root/'scripts/run_real_monthly_release_update.py').write_text('changed')
            return {'status':'PREFLIGHT_ONLY'}
        self.producer.side_effect=drift
        with self.assertRaises(ValueError): self.run_phase(True)
        self.assertEqual(len(list((self.root/'runs').glob('*/failed.json'))),1)
        self.assertFalse(list((self.root/'runs').glob('*/complete.json')))


if __name__ == '__main__': unittest.main()
