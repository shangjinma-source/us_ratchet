from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_store import StrategyAccountStore
from data.strategy_daily_preview_service import StrategyDailyPreviewService


class TargetStore:
    def __init__(self):
        self.target = dict(target_id='monthly-target', payload=dict(
            account_id='a', target_month='2026-10', target_quantities={'S': 21}))

    def current(self):
        return deepcopy(self.target)


class DailyPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = datetime(2026, 10, 20, 14, tzinfo=timezone.utc)
        self.account = StrategyAccountStore(Path(self.temp.name) / 'account.sqlite3',
                                           clock=lambda: self.now)
        self.account.initialize('a', operation_id='init')
        self.sequence = 0
        self.event('CASH_CONFIRM', amount='2000', cash_basis='TOTAL_UNINVESTED')
        self.event('DIRECT_FILL', security_id='S', side='BUY', quantity=14,
                   price='100', fees='0', executed_at=self.now.isoformat())
        self.event('CASH_CONFIRM', amount='600', cash_basis='TOTAL_UNINVESTED')
        self.targets = TargetStore()
        self.quantity = 7
        self.signal_mode = 'valid'
        self.calls = 0
        self.provider_quantity = None
        self.mutation = None
        self.service = StrategyDailyPreviewService(
            account_store=self.account, target_store=self.targets,
            signal_verifier=self.signal, execution_provider=self.evidence,
            policy_id='test-only', clock=lambda: self.now,
            fee_bps='0', maximum_mark_age_seconds=120)

    def event(self, kind, **fields):
        self.sequence += 1
        return self.account.append(dict(event_id=str(self.sequence), kind=kind, **fields),
                                   expected_revision=self.account.read()['revision'])

    def signal(self, state, target, now):
        if self.signal_mode == 'missing':
            return None
        return dict(account_id=state['account_id'], account_revision=state['revision'],
                    target_id=target['target_id'], policy_id='test-only', evidence_id='fixture',
                    observed_at=(now-timedelta(days=1)).isoformat(),
                    available_at=(now-timedelta(hours=1)).isoformat(),
                    valid_from=(now-timedelta(minutes=30)).isoformat(),
                    valid_until=(now+timedelta(minutes=-1 if self.signal_mode == 'expired' else 30)).isoformat(),
                    effective_target_quantities={'S': self.quantity})

    def evidence(self, state, effective, now):
        self.calls += 1
        self.provider_quantity = deepcopy(effective)
        if self.mutation == 'target':
            effective['S'] = 21
        if self.mutation == 'account':
            self.event('CASH_CONFIRM', amount='500', cash_basis='TOTAL_UNINVESTED')
        if self.mutation == 'monthly':
            self.targets.target['target_id'] = 'other'
        if self.mutation == 'expiry':
            self.now += timedelta(hours=1)
        if self.mutation == 'clock_backwards':
            self.now -= timedelta(seconds=1)
        return dict(marks={'S': dict(security_id='S', currency='USD', price_basis='TEST',
                                    observed_at=now.isoformat(), price='100')},
                    limits={'S': dict(security_id='S', price_basis='TEST', buy='99', sell='101',
                                      observed_at=now.isoformat(),
                                      reference_valid_until=(now+timedelta(seconds=90)).isoformat())})

    def test_missing_expired_hold_and_month_roll_never_request_limits(self):
        for mode in ('missing', 'expired'):
            self.signal_mode = mode
            result = self.service.preview()
            self.assertEqual(result['new_orders'], [])
            self.assertIsNone(result['effective_target_quantities'])
        self.signal_mode = 'valid'
        self.quantity = 14
        self.assertEqual(self.service.preview()['status'], 'HOLD')
        self.targets.target['payload']['target_month'] = '2026-09'
        self.assertEqual(self.service.preview()['status'], 'WAIT_MONTHLY_TARGET')
        self.assertEqual(self.calls, 0)

    def test_reduce_uses_effective_not_monthly_and_does_not_mutate_sqlite(self):
        before = self.account.path.read_bytes()
        result = self.service.preview()
        self.assertEqual(self.provider_quantity, {'S': 7})
        self.assertEqual(result['effective_target_quantities'], {'S': 7})
        order = result['new_orders'][0]
        self.assertEqual((order['side'], order['quantity']), ('SELL', 7))
        self.assertEqual(self.account.path.read_bytes(), before)

    def test_user_monthly_13_held_14_daily_risk_target_6(self):
        # Monthly allocation alone requires one share sold. A separately
        # verified daily reduction to six requires eight, never thirteen/eight
        # added together. Previewing repeatedly must not record either sale.
        self.targets.target['payload']['target_quantities'] = {'S': 13}
        before = self.account.path.read_bytes()
        for effective, expected in ((13, 1), (6, 8)):
            with self.subTest(effective_target=effective):
                self.quantity = effective
                for _ in range(2):
                    result = self.service.preview()
                    self.assertEqual(result['effective_target_quantities'], {'S': effective})
                    self.assertEqual([(o['side'], o['quantity']) for o in result['new_orders']],
                                     [('SELL', expected)])
                    self.assertEqual(self.account.path.read_bytes(), before)
                    self.assertEqual(self.targets.target['payload']['target_quantities'], {'S': 13})
        self.quantity = 14
        result = self.service.preview()
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['new_orders'], [])
        self.assertEqual(self.account.path.read_bytes(), before)

    def test_zero_cash_buy_waits_sell_still_previews(self):
        self.event('CASH_CONFIRM', amount='0', cash_basis='TOTAL_UNINVESTED')
        self.quantity = 21
        self.assertEqual(self.service.preview()['new_orders'], [])
        self.assertEqual(self.calls, 0)
        self.quantity = 7
        self.assertEqual(self.service.preview()['new_orders'][0]['side'], 'SELL')

    def test_opposite_pending_is_not_cancelled_and_no_limits_requested(self):
        self.event('ORDER_OPEN', order_id='open', security_id='S', side='BUY',
                   quantity=1, limit_price='99', fee_per_share='0')
        before = self.account.read()
        self.assertEqual(self.service.preview()['status'], 'WAIT_PENDING_RECONCILIATION')
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.account.read(), before)

    def test_provider_mutation_account_race_target_race_and_expiry_rejected(self):
        for mutation in ('target', 'account', 'monthly', 'expiry', 'clock_backwards'):
            with self.subTest(mutation=mutation):
                self.mutation = mutation
                with self.assertRaises(ValueError):
                    self.service.preview()
                self.targets.target['target_id'] = 'monthly-target'
                self.now = datetime(2026, 10, 20, 14, tzinfo=timezone.utc)


if __name__ == '__main__':
    unittest.main()
