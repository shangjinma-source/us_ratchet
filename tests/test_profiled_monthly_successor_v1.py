from pathlib import Path
from tempfile import TemporaryDirectory
import json
from hashlib import sha256
import unittest
from unittest.mock import patch
import test_update_profiled_monthly_release_v1 as updates
from test_materialize_real_monthly_successor import extended_fixture
from scripts.update_profiled_monthly_release_v1 import update
from scripts.materialize_profiled_monthly_successor_v1 import run
from core.strategy_account_ledger import canonical


class SuccessorTests(unittest.TestCase):
    def test_actual_adoption_handoff_rolling_materializes_and_waits_next_month(self):
        from scripts.run_rolling_profiled_monthly_update_v1 import run as rolling, SOURCES
        helper=updates.UpdateTests()
        with patch('test_build_real_monthly_release_entry.fixture',extended_fixture):helper.setUp()
        self.addCleanup(helper.doCleanups);root=helper.root
        result=update(**helper.args,execute=True)
        ready=json.loads((root/result['ready']['receipt_path']).read_bytes())
        pins={}
        for name in SOURCES:
            raw=(Path(__file__).resolve().parents[1]/name).read_bytes();p=root/name
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
        def ref(name,value):
            raw=canonical(value);(root/name).write_bytes(raw)
            return dict(path=name,sha256=sha256(raw).hexdigest())
        def existing(name):return dict(path=name,sha256=sha256((root/name).read_bytes()).hexdigest())
        initial=helper.activation.initial
        prep=ref('profile-preparation.json',dict(schema='PROFILED_SERVER_PREPARATION_V2',
            initial_snapshot=initial,legacy_anchor=helper.activation.legacy_anchor,source_pins=pins))
        upgrade=ref('upgrade.json',dict(schema='CONTINUOUS32_RESEARCH_UPGRADE_V1',
            purpose='EXPLICIT_SAME_MONTH_RESEARCH_VERSION_UPGRADE_NOT_MONTHLY_PUBLICATION',
            base_snapshot=dict(initial,revision=0),upgrade_archive=ready['archive'],upgraded_configuration=ready['runtime']))
        complete=json.loads((root/'real-market/complete.json').read_bytes())
        binding=complete['binding']
        source=dict(schema='SCHEDULED_REAL_MONTHLY_UPDATE_V1',root=str(root),
            coordinator_config='coordinator.json',coordinator_sha256=existing('coordinator.json')['sha256'],
            bootstrap_config='bootstrap.json',bootstrap_sha256=existing('bootstrap.json')['sha256'],
            policy_path='policy.json',policy_sha256=existing('policy.json')['sha256'],
            descriptor_path='approved-profile.json',descriptor_sha256=existing('approved-profile.json')['sha256'],
            market_output_directory='real-market',update_output_directory='unused-update',run_directory='source-runs',source_pins={})
        schedule=ref('profile-schedule.json',dict(schema='PROFILED_MONTHLY_SCHEDULE_V1',
            source_schedule=ref('source-schedule.json',source),preparation=prep,upgrade=upgrade,
            source_pins=pins,output_directory='profile-update'))
        configuration=ref('rolling.json',dict(schema='ROLLING_PROFILED_MONTHLY_UPDATE_V1',
            first_schedule=schedule,source_pins=pins,output_directory='chain'))
        args=dict(root=root,config_path=configuration['path'],config_sha256=configuration['sha256'],execute=True,clock=lambda:helper.f.now)
        before=helper.f.store.path.read_bytes()
        with patch('socket.socket',side_effect=AssertionError('NO_NETWORK')):
            outcome=rolling(**args)
            self.assertEqual(outcome['status'],'WAITING_SESSION_CLOSE')
            self.assertEqual(outcome['completed_months'],['2026-12'])
            self.assertEqual(rolling(**args),outcome)
        self.assertTrue((root/'chain/2026-12/profile-schedule.json').is_file())
        self.assertEqual(helper.f.store.path.read_bytes(),before)
        self.assertFalse(helper.activation.legacy.releases.path.exists())

    def test_real_profile_adoption_then_next_plan_no_new_target_or_capture(self):
        helper=updates.UpdateTests()
        with patch('test_build_real_monthly_release_entry.fixture',extended_fixture):helper.setUp()
        self.addCleanup(helper.doCleanups)
        adopted=update(**helper.args,execute=True)
        root=helper.root;source=helper.f.args
        args=dict(root=root,complete_path=source['complete_path'],complete_sha256=source['complete_sha256'],
            descriptor_path='approved-profile.json',descriptor_sha256=helper.f.save('approved-profile.json',
                json.loads((root/'approved-profile.json').read_bytes())),output_directory='next-profile-month',
            snapshot_provider=helper.activation.snapshot,validate_code=lambda:None,
            runtime_pins=helper.args['entry']['runtime_pins'],clock=lambda:helper.f.now)
        before=helper.f.store.path.read_bytes();count=len(helper.f.calls)
        with patch('socket.socket',side_effect=AssertionError('NO_NETWORK')):
            result=run(**args,execute=True)
            self.assertEqual(result['target_month'],'2027-01')
            self.assertEqual(run(**args,execute=True),result)
            self.assertEqual(helper.f.store.path.read_bytes(),before)
            self.assertFalse(helper.activation.targets.path.exists())
            self.assertFalse(helper.activation.legacy.releases.path.exists())
            self.assertEqual(len(helper.f.calls),count)
            (root/'next-profile-month/boundary.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'SUCCESSOR_OUTPUT_CHANGED'):run(**args,execute=True)
