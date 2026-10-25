"""Prefix views must not hide post-valuation changes or missing sessions."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from scripts.review_recent_continuous_probe import review_executed_prefix


class PrefixReviewTests(unittest.TestCase):
    def setUp(self):
        self.assembled=dict(session_dates=['2021-01-29','2021-02-01','2021-02-02'],
            monthly_inputs=[dict(decision_date='2021-01-29'),dict(decision_date='2021-02-01')],
            actions=[],provider_actions=[],distribution_events=[],cash_stock_merger_events=[])
        state=dict(cash='20000',shares={},receivable='0',distribution_rights=[],merger_entitlements=[])
        self.book=dict(status='BLOCKED',reason='ORDER_PROVIDER_NOT_READY',**state,
            state_date='2021-02-02',last_valued_date='2021-02-01',
            daily_ledger=[dict(date='2021-02-01',equity='20000',**state)],
            provider_audit=[dict(status='READY',orders=[]),dict(status='BLOCKED',orders=[])],
            selection_account_states=[dict(decision_date='2021-01-29'),dict(decision_date='2021-02-01')],order_log=[])

    def test_preserves_executed_final_day_and_original_status(self):
        original=deepcopy(self.book)
        with patch('scripts.review_recent_continuous_probe.review',return_value={'verified':True}) as core:
            result=review_executed_prefix(self.book,self.assembled,{})
        self.assertEqual(result['end'],'2021-02-01')
        self.assertEqual(result['unexecuted_selection_dates'],['2021-02-01'])
        self.assertEqual(self.book,original)
        self.assertEqual(len(core.call_args.args[0]['daily_ledger']),1)
        self.assertTrue(core.call_args.kwargs['verify_risk_provider'])

    def test_unvalued_cash_change_is_rejected(self):
        self.book['cash']='19000'
        with self.assertRaisesRegex(ValueError,'UNVALUED_TERMINAL_MUTATION'):
            review_executed_prefix(self.book,self.assembled,{})

    def test_no_post_prefix_execution_can_be_dropped(self):
        self.book['order_log']=[dict(date='2021-02-02',event='ASSUMED_NEXT_OPEN_FILLED')]
        with self.assertRaisesRegex(ValueError,'POST_PREFIX_ORDER_LOG'):
            review_executed_prefix(self.book,self.assembled,{})

    def test_missing_middle_session_cannot_be_relabelled_prefix(self):
        self.book['daily_ledger'][0]['date']='2021-02-02'
        with self.assertRaisesRegex(ValueError,'NONCONTIGUOUS_EXECUTED_PREFIX'):
            review_executed_prefix(self.book,self.assembled,{})


if __name__=='__main__':unittest.main()
