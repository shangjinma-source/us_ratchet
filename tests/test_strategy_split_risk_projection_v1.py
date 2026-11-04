from copy import deepcopy
import unittest

from core.monthly_peak_exit import advance_monthly_exit
from core.strategy_account_ledger import create_account
from core.strategy_account_split_v1 import apply_event
from core.strategy_split_risk_projection_v1 import project_split_risk


class SplitRiskProjectionTests(unittest.TestCase):
    def setUp(self):
        state = create_account('test')
        event = dict(event_id='split', kind='SPLIT_CONFIRMED', action_id='action', security_id='S', ratio=8,
            effective_at='2026-11-20T14:30:00Z', broker_confirmed_at='2026-11-20T14:31:00Z',
            old_unit_id='old', new_unit_id='new', evidence_sha256='a'*64)
        self.account, _ = apply_event(state, event, expected_revision=state['revision'])
        self.risk = advance_monthly_exit(state=None, account_id='test', decision_date='2026-11-02',
            session_date='2026-11-02', closes={'S':'1000','T':'100'}, unit_ids={'S':'old','T':'t'},
            baseline_targets={'S':10,'T':1})['state']

    def project(self, risk=None):
        return project_split_risk(account_after=self.account, action_id='action',
                                  risk_before=risk or self.risk, quantities_before={'S':10,'T':1})

    def advance(self, result, price):
        return advance_monthly_exit(state=result['risk_state'], account_id='test',
            decision_date='2026-11-02', session_date='2026-11-20',
            closes={'S':price,'T':'100'}, unit_ids={'S':'new','T':'t'},
            baseline_targets=result['target_quantities'])

    def test_split_does_not_trigger_exit_and_real_threshold_still_works(self):
        before = deepcopy(self.risk)
        projected = self.project()
        self.assertEqual(projected['target_quantities'], {'S':80,'T':1})
        self.assertEqual(projected['risk_state']['peaks'], {'S':'125','T':'100'})
        self.assertEqual(self.advance(projected, '125')['effective_target_quantities']['S'], 80)
        self.assertEqual(self.advance(projected, '100')['effective_target_quantities']['S'], 0)
        self.assertEqual(self.risk, before)

    def test_existing_exit_is_not_cleared(self):
        self.risk['exited'] = ['S']
        result = self.advance(self.project(), '150')
        self.assertEqual(result['effective_target_quantities']['S'], 0)
        self.assertEqual(result['state']['decision_date'], '2026-11-02')

    def test_duplicate_conversion_rejected(self):
        converted = self.project()['risk_state']
        with self.assertRaisesRegex(ValueError, 'OLD_UNIT_REQUIRED'): self.project(converted)

    def test_wrong_account_or_late_boundary_rejected(self):
        self.risk['account_id'] = 'different'
        with self.assertRaisesRegex(ValueError, 'ACCOUNT_MISMATCH'): self.project()
        self.risk['account_id'] = 'test'
        self.risk['session_date'] = '2026-11-20'
        with self.assertRaisesRegex(ValueError, 'PAST_BOUNDARY'): self.project()
