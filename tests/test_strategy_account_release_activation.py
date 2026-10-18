from hashlib import sha256
from datetime import timedelta
import unittest

from data.strategy_account_release_activation import MonthlyReleaseActivation
from data.strategy_account_rolling_router import RollingMonthlyRuntimeRouter
from scripts.review_prepare_real_monthly_release import run
import test_review_prepare_real_monthly_release as fixtures


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ReviewPrepareTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        arguments = self.fixture.arguments
        self.initial = {key:arguments[key] for key in
                        ('registry_path','registry_sha256','archive_path','archive_sha256')}
        run(**arguments)
        self.receipt_path = 'reviewed-package/ready.json'
        self.receipt_hash = sha256((self.fixture.root/self.receipt_path).read_bytes()).hexdigest()
        self.service = MonthlyReleaseActivation(root=self.fixture.root, initial_snapshot=self.initial,
            validate_code=lambda:None, clock=lambda:self.fixture.now)

    def adopt(self):
        return self.service.adopt(receipt_path=self.receipt_path,
            receipt_sha256=self.receipt_hash, expected_release_revision=0)

    def test_real_pipeline_adopts_only_release_and_restarts(self):
        before = self.fixture.store.path.read_bytes()
        self.assertEqual(self.service.snapshot()['revision'], 0)
        result = self.adopt()
        self.assertEqual(result['revision'], 1)
        self.assertEqual(self.adopt(), result)
        restarted = MonthlyReleaseActivation(root=self.fixture.root, initial_snapshot=self.initial,
            validate_code=lambda:None, clock=lambda:self.fixture.now)
        self.assertEqual(restarted.snapshot()['registry_path'], 'reviewed-package/candidate/registry.json')
        self.assertEqual(self.fixture.store.path.read_bytes(), before)
        self.assertFalse((self.fixture.root/'data/strategy_account/monthly_targets.sqlite3').exists())
        router = RollingMonthlyRuntimeRouter(root=self.fixture.root,
            initial_snapshot=dict(self.initial, revision=0), snapshot_provider=restarted.snapshot,
            clock=lambda:self.fixture.now)
        selected = router._selection_configuration(self.fixture.store.read(), 'MONTHLY_SELECTION')
        self.assertEqual(selected['target_month'], '2026-12')
        self.assertEqual(self.fixture.store.path.read_bytes(), before)
        self.assertFalse(router.targets.path.exists())

    def test_account_changed_before_adoption_is_rejected(self):
        self.fixture.store.append(dict(event_id='later-cash',kind='CASH_CONFIRM',
            amount='100',cash_basis='TOTAL_UNINVESTED'),
            expected_revision=self.fixture.store.read()['revision'])
        with self.assertRaises(ValueError):
            self.adopt()
        self.assertIsNone(self.service.releases.current())

    def test_gate_failure_after_review_does_not_adopt(self):
        calls = []
        def gate():
            calls.append(1)
            if len(calls) == 2:
                raise ValueError('TEST_SOURCE_CHANGED')
        self.service.gate = gate
        with self.assertRaisesRegex(ValueError, 'TEST_SOURCE_CHANGED'):
            self.adopt()
        self.assertIsNone(self.service.releases.current())

    def test_intervening_account_change_caught_before_commit(self):
        calls = []
        def gate():
            calls.append(1)
            if len(calls) == 2:
                self.fixture.store.append(dict(event_id='during-cash',kind='CASH_CONFIRM',
                    amount='100',cash_basis='TOTAL_UNINVESTED'),
                    expected_revision=self.fixture.store.read()['revision'])
        self.service.gate = gate
        with self.assertRaisesRegex(ValueError, 'ACCOUNT_CHANGED_DURING_ACTIVATION'):
            self.adopt()
        self.assertIsNone(self.service.releases.current())

    def test_saved_pointer_replays_historical_account_after_later_cash_and_month(self):
        self.adopt()
        self.fixture.store.append(dict(event_id='later-cash',kind='CASH_CONFIRM',
            amount='100',cash_basis='TOTAL_UNINVESTED'),
            expected_revision=self.fixture.store.read()['revision'])
        later_fill = dict(self.fixture.store.read()['events'][0]['payload'], event_id='later-fill')
        self.fixture.store.append(later_fill, expected_revision=self.fixture.store.read()['revision'])
        self.assertFalse(self.fixture.store.read()['cash_confirmation_valid'])
        restarted = MonthlyReleaseActivation(root=self.fixture.root, initial_snapshot=self.initial,
            validate_code=lambda:None, clock=lambda:self.fixture.now+timedelta(days=40))
        before = self.fixture.store.path.read_bytes()
        self.assertEqual(restarted.snapshot()['revision'], 1)
        self.assertEqual(restarted.adopt(receipt_path=self.receipt_path,
            receipt_sha256=self.receipt_hash, expected_release_revision=0)['revision'], 1)
        self.assertEqual(self.fixture.store.path.read_bytes(), before)

    def test_forged_pointer_binding_fails_on_restart_and_idempotent_retry(self):
        payload = dict(self.initial, ready_path=self.receipt_path, ready_sha256=self.receipt_hash,
            target_month='2026-12', account_revision=self.fixture.store.read()['revision'],
            adopted_at=self.fixture.now.isoformat())
        self.service.releases.adopt(payload, expected_revision=0)
        with self.assertRaisesRegex(ValueError, 'ACTIVATION_SAVED_RECEIPT_BINDING_MISMATCH'):
            self.service.snapshot()
        with self.assertRaisesRegex(ValueError, 'ACTIVATION_SAVED_RECEIPT_BINDING_MISMATCH'):
            self.adopt()

    def test_missing_receipt_and_future_adoption_are_not_trusted(self):
        original = self.adopt()
        self.service.clock = lambda:self.fixture.now-timedelta(seconds=1)
        with self.assertRaisesRegex(ValueError, 'ACTIVATION_SAVED_CLOCK_INVALID'):
            self.service.snapshot()
        self.service.clock = lambda:self.fixture.now
        (self.fixture.root/self.receipt_path).unlink()
        with self.assertRaises(FileNotFoundError):
            self.service.snapshot()
        with self.assertRaises(FileNotFoundError):
            self.adopt()
        self.assertEqual(self.service.releases.current(), original)


if __name__ == '__main__':
    unittest.main()
