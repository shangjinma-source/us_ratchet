from pathlib import Path
from hashlib import sha256
from datetime import datetime
import unittest
from unittest.mock import patch
import test_scheduled_real_monthly_update as old
from scripts import run_profiled_monthly_update_v1 as runner


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.f=old.PhaseTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        root=self.f.root;pins=dict(self.f.config['source_pins'])
        for name in runner.SOURCES:
            raw=(Path(__file__).resolve().parents[1]/name).read_bytes()
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
        def ref(name,obj):return dict(path=name,sha256=self.f.save(name,obj))
        config=dict(schema='PROFILED_MONTHLY_SCHEDULE_V1',source_schedule=ref('old-schedule.json',self.f.config),
            preparation=ref('prep.json',dict(schema='PROFILED_SERVER_PREPARATION_V2',source_pins={})),
            upgrade=ref('upgrade.json',{}),source_pins=pins,output_directory='new-profile-update')
        self.ref=ref('profile-schedule.json',config)
        self.producer=self.enterContext(patch.object(runner,'produce',return_value=dict(status='PREFLIGHT_ONLY')))
    def call(self,at):return runner.run(root=self.f.root,config_path=self.ref['path'],config_sha256=self.ref['sha256'],execute=True,clock=lambda:datetime.fromisoformat(at))
    def test_before_close_no_capture(self):
        self.assertEqual(self.call('2026-10-30T19:59:59+00:00')['status'],'WAITING_SESSION_CLOSE');self.producer.assert_not_called()
    def test_closed_window_only_prepares(self):
        self.assertEqual(self.call('2026-10-30T20:00:00+00:00')['status'],'MARKET_PREPARATION_PHASE')
        self.assertTrue(self.producer.call_args.kwargs['execute'])
        self.assertFalse((self.f.root/'new-profile-update').exists())
    def test_missed_source_window_never_catches_up(self):
        self.assertEqual(self.call('2026-11-02T15:00:00+00:00')['status'],'MISSED_PREPARATION_WINDOW');self.producer.assert_not_called()
    def test_nested_producer_failure_is_not_success(self):
        for status in ('BLOCKED', 'NEEDS_RECOVERY', 'WAITING_REVIEW', 'UNKNOWN'):
            self.producer.return_value = dict(status=status)
            value = self.call('2026-10-30T20:00:00+00:00')
            self.assertEqual(value['status'], 'BLOCKED')
            self.assertEqual(value['preparation']['status'], status)
