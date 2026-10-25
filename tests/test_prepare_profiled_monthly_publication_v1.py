from pathlib import Path
from hashlib import sha256
import json
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_profiled_server_preparation import SOURCES
from data.strategy_profiled_release_activation import ProfiledMonthlyReleaseActivation
from data.strategy_account_release_activation import MonthlyReleaseActivation
from scripts.prepare_profiled_monthly_publication_v1 import prepare
import test_review_prepare_real_monthly_release as fixtures


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ReviewPrepareTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        for name in SOURCES:
            raw = (Path(__file__).resolve().parents[1]/name).read_bytes()
            dest = self.root/name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
            self.f.f.entry['runtime_pins'][name] = sha256(raw).hexdigest()
        self.snapshot = {k:self.f.arguments[k] for k in ('registry_path','registry_sha256','archive_path','archive_sha256')}
        self.snapshot['revision'] = 0
        self.args = dict(root=self.root, snapshot=self.snapshot, new_entry=self.f.f.entry,
            output_directory='profile-publication', clock=lambda:self.f.now, validate_code=lambda:None,
            market_capture=self.f.arguments['market_capture'], action_capture=self.f.arguments['action_capture'])

    def test_real_review_profile_adoption_repeat_without_legacy_or_account_write(self):
        before = self.f.store.path.read_bytes()
        result = prepare(**self.args)
        initial = {k:v for k,v in self.snapshot.items() if k != 'revision'}
        old = MonthlyReleaseActivation(root=self.root, initial_snapshot=initial, validate_code=lambda:None, clock=lambda:self.f.now)
        anchor = dict(revision=0, record_sha256=None, snapshot=old.snapshot())
        activation = ProfiledMonthlyReleaseActivation(root=self.root, initial_snapshot=initial,
            validate_code=lambda:None, legacy_anchor=anchor, clock=lambda:self.f.now)
        ref = result['ready']; args = dict(receipt_path=ref['path'], receipt_sha256=ref['sha256'], expected_release_revision=0)
        adopted = activation.adopt(**args)
        self.assertEqual(activation.adopt(**args), adopted)
        self.assertEqual(activation.snapshot()['revision'], 1)
        self.assertFalse(old.releases.path.exists())
        self.assertEqual(self.f.store.path.read_bytes(), before)
        self.assertFalse(activation.targets.path.exists())

    def test_capture_failure_retained_without_ready_or_retry(self):
        def fail(**kwargs): raise ValueError('TEST_CAPTURE_FAILED')
        self.args['market_capture'].capture = fail
        with self.assertRaisesRegex(ValueError, 'TEST_CAPTURE_FAILED'): prepare(**self.args)
        self.assertTrue((self.root/'profile-publication/failed.json').exists())
        self.assertFalse((self.root/'profile-publication/ready.json').exists())
        with self.assertRaisesRegex(ValueError,'OUTPUT_CONFLICT'): prepare(**self.args)

    def existing_target_case(self, first_adoption=False):
        from copy import deepcopy
        from data.strategy_continuous32_target_decision import PROFILE_ID
        from data.strategy_profiled_runtime_archive import configuration_for_target
        from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
        def put(name,value):
            raw=canonical(value);(self.root/name).write_bytes(raw)
            return dict(path=name,sha256=sha256(raw).hexdigest())
        # Synthetic prior published configuration: distinct training document,
        # exact original bytes; this test asserts archival identity, not selection.
        original=self.f.f.resolve()
        old=deepcopy(original)
        (self.root/'prior-training.json').write_bytes((self.root/old['training_manifest']).read_bytes())
        old.update(schema='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1',selector_profile=PROFILE_ID,
                   target_month='2026-11',training_manifest='prior-training.json')
        oldref=put('prior-runtime.json',old)
        oldrow=dict(configuration_path=oldref['path'],configuration_sha256=oldref['sha256'])
        archive=put('prior-archive.json',dict(schema='PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1',entries=[oldrow]))
        assignment=dict(target_month='2026-11',selector_profile=PROFILE_ID)
        registry=put('prior-registry.json',dict(schema='PROFILED_MONTHLY_RELEASES_V1',
            original_registry=dict(path=self.snapshot['registry_path'],sha256=self.snapshot['registry_sha256']),profiles=[assignment]))
        self.args['snapshot']=dict(self.snapshot,registry_path=registry['path'],registry_sha256=registry['sha256'],
            archive_path=archive['path'],archive_sha256=archive['sha256'])
        binding=dict(account_id=self.f.store.read()['account_id'],selector_profile=PROFILE_ID,
            documents=dict(training_manifest=old['training_manifest']),
            source_hashes={old['training_manifest']:old['training_sha256'],old['identity_manifest']:old['identity_sha256']})
        decision_payload=dict(input_binding=binding,input_id=sha256(canonical(binding)).hexdigest(),target_quantities={})
        decision=dict(payload=decision_payload,decision_id=sha256(canonical(decision_payload)).hexdigest())
        targets=StrategyMonthlyTargetStore(self.root/'data/strategy_account/monthly_targets.sqlite3')
        target=targets.append(dict(schema='REAL_STRATEGY_MONTHLY_TARGET_V1',account_id=binding['account_id'],
            target_month='2026-11',created_at=self.f.now.isoformat(),request=dict(event_id='prior-profile-fixture'),
            previous_target_id=None,decision=decision,target_quantities={},runtime_pins=old['runtime_pins']))
        before=targets.path.read_bytes()
        if first_adoption:
            # Actual deployment shape: no profiled release row yet, legacy stays
            # revision zero, but current target already uses upgrade archive.
            from data.strategy_continuous32_upgrade_handoff import upgrade_handoff_snapshot_provider
            from scripts.update_profiled_monthly_release_v1 import update
            initial={k:v for k,v in self.snapshot.items() if k!='revision'}
            activation=ProfiledMonthlyReleaseActivation(root=self.root,initial_snapshot=initial,
                legacy_anchor=dict(revision=0,record_sha256=None,snapshot=self.snapshot),
                validate_code=lambda:None,clock=lambda:self.f.now)
            package=put('first-upgrade-handoff.json',dict(schema='CONTINUOUS32_RESEARCH_UPGRADE_V1',
                purpose='EXPLICIT_SAME_MONTH_RESEARCH_VERSION_UPGRADE_NOT_MONTHLY_PUBLICATION',
                base_snapshot=self.snapshot,upgrade_archive=archive,upgraded_configuration=oldref))
            handoff=upgrade_handoff_snapshot_provider(root=self.root,package_path=package['path'],
                package_sha256=package['sha256'],base_provider=activation.snapshot,
                target_provider=targets.current,validate_code=lambda:None)
            self.assertEqual(handoff()['revision'],0)
            self.assertEqual(handoff()['archive_sha256'],archive['sha256'])
            self.assertFalse(activation.releases.path.exists())
            result=update(root=self.root,entry=self.f.f.entry,output_directory='first-profile-update',
                activation=activation,snapshot_provider=handoff,validate_code=lambda:None,
                clock=lambda:self.f.now,execute=True,market_capture=self.args['market_capture'],
                action_capture=self.args['action_capture'])
            self.assertEqual(result['release_revision'],1)
            after=handoff()
            self.assertEqual(configuration_for_target(root=self.root,archive_path=after['archive_path'],
                archive_sha256=after['archive_sha256'],target=target),old)
            self.assertEqual(targets.path.read_bytes(),before)
            self.assertFalse(activation.legacy.releases.path.exists())
            if hasattr(self, 'after_adoption'):
                self.after_adoption(activation, handoff, targets, old)
            return
        result=prepare(**self.args)
        ready=json.loads((self.root/result['ready']['path']).read_bytes())
        current_archive=json.loads((self.root/ready['archive']['path']).read_bytes())
        current_registry=json.loads((self.root/ready['registry']['path']).read_bytes())
        self.assertIn(oldrow,current_archive['entries']);self.assertIn(assignment,current_registry['profiles'])
        self.assertEqual(configuration_for_target(root=self.root,archive_path=ready['archive']['path'],
            archive_sha256=ready['archive']['sha256'],target=target),old)
        initial={k:v for k,v in self.snapshot.items() if k!='revision'}
        activation=ProfiledMonthlyReleaseActivation(root=self.root,initial_snapshot=initial,
            legacy_anchor=dict(revision=0,record_sha256=None,snapshot=self.snapshot),
            validate_code=lambda:None,clock=lambda:self.f.now)
        activation.adopt(receipt_path=result['ready']['path'],receipt_sha256=result['ready']['sha256'],expected_release_revision=0)
        from data.strategy_continuous32_upgrade_handoff import upgrade_handoff_snapshot_provider
        package=put('upgrade-handoff.json',dict(schema='CONTINUOUS32_RESEARCH_UPGRADE_V1',
            purpose='EXPLICIT_SAME_MONTH_RESEARCH_VERSION_UPGRADE_NOT_MONTHLY_PUBLICATION',
            base_snapshot=self.snapshot,upgrade_archive=archive,upgraded_configuration=oldref))
        handoff=upgrade_handoff_snapshot_provider(root=self.root,package_path=package['path'],
            package_sha256=package['sha256'],base_provider=activation.snapshot,
            target_provider=targets.current,validate_code=lambda:None)
        self.assertEqual(handoff(),activation.snapshot())
        self.assertEqual(targets.path.read_bytes(),before)
        self.assertFalse(activation.legacy.releases.path.exists())

    def test_existing_profile_archive_and_target_survive_successor(self):
        self.existing_target_case()

    def test_first_adoption_from_revision_zero_upgrade_with_existing_target(self):
        self.existing_target_case(first_adoption=True)


if __name__ == '__main__': unittest.main()
