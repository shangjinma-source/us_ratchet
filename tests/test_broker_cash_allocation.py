import copy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from core.broker_cash_allocation import BrokerCashAllocationStore
from core.broker_internal_transfers import create_transfers, apply_transfer_event
from core.strategy_account_ledger import create_account, apply_event


class BrokerCashAllocationTests(unittest.TestCase):
    now = datetime(2026, 11, 14, 4, tzinfo=timezone.utc)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'cash.sqlite3'
        self.store = BrokerCashAllocationStore(self.path)
        initial = create_account('isolated')
        self.account = apply_event(initial, dict(event_id='cash', kind='CASH_CONFIRM',
            amount='1000', cash_basis='AVAILABLE_AFTER_RESERVATIONS'),
            expected_revision=initial['revision'])[0]
        self.transfers = create_transfers('isolated')
        self.document = dict(account_id='isolated', account_revision=self.account['revision'],
            transfer_revision=self.transfers['revision'], balances={
                'HSBC': dict(available_cash='400', reserved_cash='0', observed_at=self.now.isoformat()),
                'USMART': dict(available_cash='600', reserved_cash='0', observed_at=self.now.isoformat())})

    def save(self, document=None):
        return self.store.save('split', document or self.document,
            account=self.account, transfers=self.transfers, now=self.now)

    def read(self):
        return self.store.read(account=self.account, transfers=self.transfers, now=self.now)

    def test_persisted_split_idempotent_no_account_mutation(self):
        before = copy.deepcopy(self.account)
        self.assertFalse(self.save()['already_recorded'])
        self.assertTrue(self.save()['already_recorded'])
        self.store = BrokerCashAllocationStore(self.path)
        self.assertEqual(self.read()['document'], self.document)
        self.assertEqual(self.account, before)

    def test_conflicting_retry_is_rejected(self):
        self.save()
        document = copy.deepcopy(self.document)
        document['balances']['HSBC']['available_cash'] = '401'
        with self.assertRaisesRegex(ValueError, 'EVENT_ID_CONFLICT'):
            self.save(document)

    def test_duplicate_capital_or_missing_broker_rejected(self):
        for modification in ('duplicate', 'missing'):
            document = copy.deepcopy(self.document)
            if modification == 'duplicate':
                document['balances']['USMART']['available_cash'] = '1000'
            else:
                del document['balances']['USMART']
            with self.assertRaises(ValueError):
                self.save(document)
        self.assertIsNone(self.read()['balances'])

    def test_account_change_invalidates_previous_split(self):
        self.save()
        self.account = apply_event(self.account, dict(event_id='new-cash', kind='CASH_CONFIRM',
            amount='900', cash_basis='AVAILABLE_AFTER_RESERVATIONS'),
            expected_revision=self.account['revision'])[0]
        self.assertIsNone(self.read()['balances'])

    def test_transfer_change_invalidates_previous_split(self):
        self.save()
        event = dict(event_id='sent', transfer_id='t', kind='SENT', source='HSBC',
            destination='USMART', principal='100', fee='0', occurred_at=self.now.isoformat())
        self.transfers = apply_transfer_event(self.transfers, event,
            expected_revision=self.transfers['revision'], now=self.now)
        self.assertIsNone(self.read()['balances'])

    def test_unconfirmed_aggregate_does_not_become_spendable(self):
        self.save()
        self.account['cash_confirmation_valid'] = False
        self.assertIsNone(self.read()['balances'])

    def test_reserved_money_is_not_spendable(self):
        self.account.update(available_cash='900', reserved_cash='100')
        document = copy.deepcopy(self.document)
        document['balances']['HSBC'].update(available_cash='300', reserved_cash='100')
        self.save(document)
        self.assertEqual(self.read()['document']['balances']['HSBC']['available_cash'], '300')

    def test_future_and_naive_observations_rejected(self):
        for value in ('2026-11-15T00:00:00+00:00', '2026-11-14T00:00:00'):
            document = copy.deepcopy(self.document)
            document['balances']['HSBC']['observed_at'] = value
            with self.assertRaisesRegex(ValueError, 'TIME_INVALID'):
                self.save(document)


if __name__ == '__main__':
    unittest.main()
