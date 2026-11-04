from copy import deepcopy
import unittest
from core.strategy_account_ledger import create_account
from core.strategy_account_split_v1 import apply_event, replay


class SplitLedgerTests(unittest.TestCase):
    def setUp(self):
        self.state = create_account('isolated')
        self.append(dict(event_id='buy', kind='DIRECT_FILL', security_id='S', side='BUY',
                         quantity=14, price='1000', fees='0', executed_at='2026-11-02T15:00:00Z'))
        self.append(dict(event_id='cash', kind='CASH_CONFIRM', amount='500', cash_basis='TOTAL_UNINVESTED'))
        self.split = dict(event_id='split', kind='SPLIT_CONFIRMED', action_id='issuer-action',
            security_id='S', ratio=8, effective_at='2026-11-20T14:30:00Z',
            broker_confirmed_at='2026-11-20T14:31:00Z', old_unit_id='old', new_unit_id='new', evidence_sha256='a'*64)

    def append(self, event):
        self.state, effect = apply_event(self.state, event, expected_revision=self.state['revision'])
        return effect

    def test_conversion_replay_and_duplicate(self):
        before = deepcopy(self.state)
        effect = self.append(self.split)
        self.assertEqual(self.state['shares']['S'], 112)
        self.assertEqual(self.state['cash'], '500')
        self.assertEqual(effect['cash_delta'], '0')
        self.assertFalse(self.state['execution_ready'])
        self.assertEqual(self.state['events'][:-1], before['events'])
        duplicate, _ = apply_event(self.state, self.split, expected_revision=before['revision'])
        self.assertEqual(duplicate, self.state)
        self.assertEqual(replay('isolated', [i['payload'] for i in self.state['events']]), self.state)
        with self.assertRaisesRegex(ValueError, 'ALREADY_APPLIED'):
            self.append(dict(self.split, event_id='different-request'))

    def test_pending_order_requires_broker_reconciliation(self):
        self.append(dict(event_id='order', kind='ORDER_OPEN', order_id='o', security_id='S',
                         side='SELL', quantity=2, limit_price='1000', fee_per_share='0'))
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, 'OPEN_ORDERS'):
            self.append(self.split)
        self.assertEqual(before, self.state)

    def test_later_split_uses_fresh_units_and_preserves_chain(self):
        self.append(self.split)
        next_split = dict(self.split, event_id='split-two', action_id='next-action', ratio=2,
            effective_at='2026-12-01T14:30:00Z', broker_confirmed_at='2026-12-01T14:31:00Z',
            old_unit_id='new', new_unit_id='old')
        with self.assertRaisesRegex(ValueError, 'UNIT_ID_REUSED'):
            self.append(next_split)
        self.append(dict(next_split, new_unit_id='new-two'))
        self.assertEqual(self.state['shares']['S'], 224)
        self.assertEqual(replay('isolated', [r['payload'] for r in self.state['events']]), self.state)

    def test_bad_ratio_time_and_revision_do_not_mutate(self):
        before = deepcopy(self.state)
        for ratio in (True, 0, 1, '8', '1/8'):
            with self.assertRaises(ValueError): self.append(dict(self.split, ratio=ratio))
        with self.assertRaisesRegex(ValueError, 'TOO_EARLY'):
            self.append(dict(self.split, broker_confirmed_at='2026-11-19T21:00:00Z'))
        with self.assertRaisesRegex(ValueError, 'STALE_REVISION'):
            apply_event(self.state, self.split, expected_revision='stale')
        self.assertEqual(self.state, before)

    def test_late_old_unit_fill_rejected_new_unit_fill_allowed(self):
        self.append(self.split)
        fill = dict(event_id='sale', kind='DIRECT_FILL', security_id='S', side='SELL',
                    quantity=8, price='125', fees='0', executed_at='2026-11-20T14:32:00Z')
        with self.assertRaisesRegex(ValueError, 'PRE_SPLIT_LATE_FILL'):
            self.append(dict(fill, executed_at='2026-11-19T20:00:00Z'))
        self.append(fill)
        self.assertEqual(self.state['shares']['S'], 104)

    def test_already_recorded_new_unit_fill_blocks_retroactive_split(self):
        self.append(dict(event_id='late-sale', kind='DIRECT_FILL', security_id='S', side='SELL',
                         quantity=1, price='125', fees='0', executed_at='2026-11-20T14:32:00Z'))
        with self.assertRaisesRegex(ValueError, 'POST_SPLIT_FILL'):
            self.append(self.split)
