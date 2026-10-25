from pathlib import Path
from hashlib import sha256
import unittest
from unittest.mock import patch
from data.strategy_profiled_server_preparation import SOURCES
from data.strategy_profiled_release_activation import ProfiledMonthlyReleaseActivation
from scripts.build_real_monthly_release_entry import build
from scripts.update_profiled_monthly_release_v1 import update
import test_run_real_monthly_release_update as fixtures


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.UpdateTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root
        import json
        descriptor=json.loads((self.root/'approved.json').read_bytes())
        for name in SOURCES:
            raw=(Path(__file__).resolve().parents[1]/name).read_bytes()
            target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            descriptor['source_pins'][name]=sha256(raw).hexdigest()
        digest=self.f.save('approved-profile.json',descriptor)
        args=self.f.args
        entry=build(root=self.root,complete_path=args['complete_path'],complete_sha256=args['complete_sha256'],
            descriptor_path='approved-profile.json',descriptor_sha256=digest)
        from data.strategy_continuous32_runtime import RUNTIME_PATHS
        from data.strategy_profiled_ready_release import PROFILE_ADMISSION_SOURCES
        entry['runtime_pins'].update({p:descriptor['source_pins'][p] for p in RUNTIME_PATHS | PROFILE_ADMISSION_SOURCES})
        initial={k:descriptor[k] for k in ('registry_path','registry_sha256','archive_path','archive_sha256')}
        self.activation=ProfiledMonthlyReleaseActivation(root=self.root,initial_snapshot=initial,
            legacy_anchor=dict(revision=0,record_sha256=None,snapshot=dict(initial,revision=0)),
            validate_code=lambda:None,clock=lambda:self.f.now)
        self.args=dict(root=self.root,entry=entry,output_directory='profile-update',activation=self.activation,
            snapshot_provider=self.activation.snapshot,validate_code=lambda:None,clock=lambda:self.f.now,
            market_capture=args['market_capture'],action_capture=args['action_capture'])

    def test_actual_saved_market_entry_review_adopt_restart(self):
        before=self.f.store.path.read_bytes()
        self.assertEqual(update(**self.args)['status'],'PROFILED_UPDATE_PREFLIGHT')
        result=update(**self.args,execute=True)
        with patch('scripts.update_profiled_monthly_release_v1.prepare',side_effect=AssertionError('NO_RECAPTURE')):
            self.assertEqual(update(**self.args,execute=True),result)
        self.assertEqual(result['release_revision'],1)
        self.assertEqual(self.f.store.path.read_bytes(),before)
        self.assertFalse(self.activation.legacy.releases.path.exists())
        self.assertFalse(self.activation.targets.path.exists())

    def test_failed_capture_never_blindly_retried(self):
        with patch.object(self.args['market_capture'],'capture',side_effect=ValueError('INJECTED_CAPTURE')) as capture:
            with self.assertRaisesRegex(ValueError,'INJECTED_CAPTURE'):update(**self.args,execute=True)
            with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED'):update(**self.args,execute=True)
            self.assertEqual(capture.call_count,1)

    def test_prepared_unadopted_cannot_resume_in_later_month(self):
        from datetime import datetime
        with patch.object(self.activation,'adopt',side_effect=ValueError('SIMULATED_PRE_ADOPTION_INTERRUPTION')):
            with self.assertRaisesRegex(ValueError,'SIMULATED_PRE_ADOPTION_INTERRUPTION'):
                update(**self.args,execute=True)
        self.f.now=datetime.fromisoformat('2027-01-04T15:00:00+00:00')
        with patch('scripts.update_profiled_monthly_release_v1.prepare',side_effect=AssertionError('NO_RECAPTURE')):
            with self.assertRaisesRegex(ValueError,'READY_CURRENT_MONTH_REQUIRED'):
                update(**self.args,execute=True)
        self.assertFalse(self.activation.releases.path.exists())


if __name__=='__main__':unittest.main()
