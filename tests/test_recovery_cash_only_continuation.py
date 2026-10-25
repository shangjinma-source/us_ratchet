# All cash fixtures are synthetic; no broker balance or transfer amount is used.
from copy import deepcopy
import unittest
from core.strategy_account_ledger import create_account, apply_event
from scripts.prepare_continuous32_recovery_v5 import validate_cash_only_continuation


class CashContinuationTests(unittest.TestCase):
    def event(self, state, **value):
        return apply_event(state, value, expected_revision=state['revision'])[0]

    def test_cash_confirm_suffix_and_same_state(self):
        old = create_account('fixture')
        old = self.event(old, kind='CASH_CONFIRM', event_id='cash1',
                         amount='10234.56', cash_basis='TOTAL_UNINVESTED')
        new = self.event(old, kind='CASH_CONFIRM', event_id='cash2',
                         amount='10234.56', cash_basis='TOTAL_UNINVESTED')
        self.assertEqual(validate_cash_only_continuation(old, new)['cash_confirmation_count'], 1)
        self.assertEqual(validate_cash_only_continuation(old, old)['cash_confirmation_count'], 0)
        for field in ('shares', 'orders'):
            changed = deepcopy(new)
            changed[field] = {'injected': 1}
            with self.assertRaises(ValueError):
                validate_cash_only_continuation(old, changed)
        changed = deepcopy(new)
        changed['events'][0]['payload']['amount'] = '999'
        with self.assertRaisesRegex(ValueError, 'PREFIX_CHANGED'):
            validate_cash_only_continuation(old, changed)
        changed = deepcopy(new)
        changed['events'][-1]['payload']['kind'] = 'FILL'
        with self.assertRaisesRegex(ValueError, 'NON_CASH_CHANGE'):
            validate_cash_only_continuation(old, changed)
