import copy
import unittest
from datetime import datetime, timezone
from fractions import Fraction

from core.strategy_account_ledger import create_account, apply_event
from core.broker_internal_transfers import create_transfers, apply_transfer_event
from core.broker_transfer_cash_reconciliation import reconcile_transfer_cash


class TransferCashReconciliationTests(unittest.TestCase):
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    start = '2026-11-14T00:00:00+00:00'

    def setUp(self):
        self.initial = self.cash(create_account('test'), 'initial', '1000')
        self.transfers = create_transfers('test')
        self.add(dict(event_id='sent', transfer_id='t', kind='SENT',
            source='HSBC', destination='USMART', principal='600', fee='5',
            occurred_at='2026-11-14T01:00:00+00:00'))
        self.sent = self.cash(self.initial, 'cash-sent', '395')
        self.times = {'cash-sent': '2026-11-14T01:05:00+00:00'}
        self.links = {'cash-sent': ['sent']}

    def cash(self, state, event_id, amount):
        return apply_event(state, dict(event_id=event_id, kind='CASH_CONFIRM',
            amount=amount, cash_basis='AVAILABLE_AFTER_RESERVATIONS'),
            expected_revision=state['revision'])[0]

    def add(self, event):
        self.transfers = apply_transfer_event(self.transfers, event,
            expected_revision=self.transfers['revision'], now=self.now)

    def run_case(self, current=None, **changes):
        arguments = dict(transfer_state=self.transfers,
            expected_transfer_revision=self.transfers['revision'],
            baseline_account=self.initial, current_account=current or self.sent,
            baseline_at=self.start, valued_at='2026-11-14T04:00:00+00:00',
            now=self.now, links=self.links, confirmation_times=self.times)
        arguments.update(changes)
        return reconcile_transfer_cash(**arguments)

    def test_sent_principal_not_loss_fee_counted_once(self):
        before = copy.deepcopy((self.initial, self.sent, self.transfers))
        result = self.run_case()
        self.assertEqual(result['status'], 'TRANSFER_CASH_RECONCILED')
        self.assertEqual(result['current_in_transit'], '600')
        self.assertEqual(result['rows'][0]['residual_cash_change'], '0')
        self.assertEqual(Fraction('395') + Fraction(result['current_in_transit']) - 1000, -5)
        self.assertEqual(result['external_capital_flow'], '0')
        self.assertEqual(before, (self.initial, self.sent, self.transfers))

    def test_partial_and_full_arrival_move_assets_not_profit(self):
        current = self.sent
        for index, amount, balance, pending in [(2, '200', '595', '400'), (3, '400', '995', '0')]:
            key = f'received-{index}'
            self.add(dict(event_id=key, transfer_id='t', kind='RECEIVED', amount=amount,
                occurred_at=f'2026-11-14T0{index}:00:00+00:00'))
            current = self.cash(current, key, balance)
            self.links[key] = [key]
            self.times[key] = f'2026-11-14T0{index}:05:00+00:00'
            result = self.run_case(current)
            self.assertEqual(result['status'], 'TRANSFER_CASH_RECONCILED')
            self.assertEqual(result['current_in_transit'], pending)
            self.assertEqual(Fraction(balance) + Fraction(pending), 995)

    def test_equal_amount_is_not_automatic_evidence(self):
        result = self.run_case(links={})
        self.assertEqual(result['status'], 'TRANSFER_CASH_RECONCILIATION_REQUIRED')
        self.assertEqual(result['unlinked_transfer_events'], ['sent'])
        self.assertEqual(result['rows'][0]['residual_cash_change'], '-605')

    def test_unrelated_difference_stays_unresolved(self):
        different = self.cash(self.initial, 'cash-sent', '390')
        result = self.run_case(different)
        self.assertEqual(result['rows'][0]['residual_cash_change'], '-5')
        self.assertEqual(result['status'], 'TRANSFER_CASH_RECONCILIATION_REQUIRED')

    def test_duplicate_link_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ALREADY_LINKED'):
            self.run_case(links={'cash-sent': ['sent', 'sent']})

    def test_wrong_snapshot_or_missing_receipt_rejected(self):
        for changes, reason in [({'expected_transfer_revision': 'old'}, 'STALE_TRANSFER'),
                                ({'confirmation_times': {}}, 'TRUSTED_CONFIRMATION'),
                                ({'valued_at': '2026-11-16T00:00:00+00:00'}, 'TIME_INVALID')]:
            with self.assertRaisesRegex(ValueError, reason):
                self.run_case(**changes)

    def test_later_receipt_does_not_rewrite_earlier_in_transit(self):
        self.add(dict(event_id='later', transfer_id='t', kind='RECEIVED', amount='600',
            occurred_at='2026-11-14T05:00:00+00:00'))
        result = self.run_case()
        self.assertEqual(result['current_in_transit'], '600')
        self.assertEqual(result['unlinked_transfer_events'], [])

    def test_existing_in_transit_at_baseline_is_not_new_capital(self):
        self.add(dict(event_id='arrival', transfer_id='t', kind='RECEIVED', amount='600',
            occurred_at='2026-11-14T02:00:00+00:00'))
        current = self.cash(self.sent, 'arrival-cash', '995')
        result = self.run_case(current, baseline_account=self.sent,
            baseline_at='2026-11-14T01:10:00+00:00', links={'arrival-cash': ['arrival']},
            confirmation_times={'arrival-cash': '2026-11-14T02:05:00+00:00'})
        self.assertEqual(result['initial_in_transit'], '600')
        self.assertEqual(result['asset_adjustment_change'], '-600')
        self.assertEqual(result['status'], 'TRANSFER_CASH_RECONCILED')

    def test_link_must_precede_cash_confirmation(self):
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_CASH_CONFIRMATION_INTERVAL'):
            self.run_case(confirmation_times={'cash-sent': '2026-11-14T00:30:00+00:00'})


if __name__ == '__main__':
    unittest.main()
