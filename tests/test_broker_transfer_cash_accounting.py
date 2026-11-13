"""Internal transfer scenarios against the existing aggregate account ledger."""
import unittest
from datetime import datetime, timezone
from core.strategy_account_ledger import create_account, apply_event
from data.roa_cash_flow.audit import audit_cash_changes
from data.roa_cash_flow.validation import validate_classification


def confirm(account, event_id, amount):
    return apply_event(account, dict(event_id=event_id, kind='CASH_CONFIRM',
        amount=amount, cash_basis='AVAILABLE_AFTER_RESERVATIONS'),
        expected_revision=account['revision'])[0]


class InternalTransferAccountingTests(unittest.TestCase):
    def setUp(self):
        self.baseline = confirm(create_account('test-only'), 'initial', '1000')

    def test_received_transfer_has_no_aggregate_cash_flow(self):
        # HSBC 1000 -> 400, uSMART 0 -> 600; both balances confirmed.
        current = confirm(self.baseline, 'received', str(400 + 600))
        result = audit_cash_changes(baseline=self.baseline, current=current)
        self.assertEqual(result['confirmations'][0]['unexplained_net_change'], '0')
        self.assertEqual(result['confirmations'][0]['status'], 'RECONCILED')
        self.assertFalse(result['returns_computed'])

    def test_in_transit_cash_is_not_automatically_a_withdrawal_or_loss(self):
        # Simulates entering only settled buying power while 600 is in transit.
        current = confirm(self.baseline, 'pending', '400')
        row = audit_cash_changes(baseline=self.baseline, current=current)['confirmations'][0]
        self.assertEqual(row['status'], 'UNEXPLAINED_CHANGE')
        self.assertEqual(row['unexplained_net_change'], '-600')
        self.assertIsNone(row['classification'])
        # Later receipt does not silently erase the earlier unresolved entry.
        received = confirm(current, 'received', '1000')
        rows = audit_cash_changes(baseline=self.baseline, current=received)['confirmations']
        self.assertEqual([r['unexplained_net_change'] for r in rows], ['-600', '600'])
        self.assertTrue(all(r['classification'] is None for r in rows))

    def test_confirmed_transfer_fee_is_not_external_capital(self):
        current = confirm(self.baseline, 'received-net-fee', '995')
        document = dict(schema='CASH_CHANGE_CLASSIFICATION_V1', account_id='test-only',
            cash_event_id='received-net-fee', before_revision=self.baseline['revision'],
            after_revision=current['revision'], net_change='-5', items=[
                dict(item_id='confirmed-fee', kind='FEE', amount='-5',
                     effective_at='2026-11-14T00:00:00+08:00')])
        result = validate_classification(baseline=self.baseline, current=current,
            document=document, now=datetime(2026,11,14,tzinfo=timezone.utc))
        self.assertEqual(result['net_external_flow'], '0')
        self.assertFalse(result['account_mutated'])
        self.assertFalse(result['persisted'])


if __name__ == '__main__':
    unittest.main()
