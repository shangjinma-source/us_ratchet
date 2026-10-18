import unittest
from copy import deepcopy
from datetime import date, timedelta
from backtest.return_priority_monthly_training_inputs import compile_monthly_training_window


class MonthlyTrainingTests(unittest.TestCase):
    def fixture(self):
        days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(253)]
        row = dict(ticker='A', security_id='SID:A', issuer_id='ISSUER:A', status='READY_CONDITIONAL',
                   blockers=[], training_source='prices', training_close=[str(100+i) for i in range(253)], decision_cost='352')
        return dict(window=dict(decision_cutoff=days[-1], training_dates=days, candidates=[row]),
                    source_hashes={'prices': 'a'*64, 'review': 'b'*64},
                    admission=dict(decision_date=days[-1], status='REVIEWED_CONDITIONAL', members=['A'], source_references=['review']))

    def test_exact_mature_scenarios(self):
        args = self.fixture()
        result = compile_monthly_training_window(**args)
        self.assertEqual(result['training_scenarios'][0], {'SID:A': '121/100'})
        self.assertEqual(result['training_scenarios'][-1], {'SID:A': '352/331'})
        self.assertEqual(result['scenario_dates'][-1], result['decision_date'])
        self.assertEqual(result['prices'], {'SID:A': '352'})

    def test_missing_member_or_price_never_silently_excluded(self):
        args = self.fixture(); args['admission']['members'].append('B')
        with self.assertRaisesRegex(ValueError, 'MEMBER_DOMAIN_MISMATCH'):
            compile_monthly_training_window(**args)
        args = self.fixture(); args['window']['candidates'][0]['training_close'][20] = None
        with self.assertRaises(ValueError):
            compile_monthly_training_window(**args)

    def test_exclusion_needs_review_and_past_evidence(self):
        args = self.fixture()
        other = deepcopy(args['window']['candidates'][0]); other.update(ticker='B', status='EXCLUDED_TRAINING_RULE')
        args['window']['candidates'].append(other); args['admission']['members'].append('B')
        with self.assertRaisesRegex(ValueError, 'EXCLUSION_NOT_ADMITTED'):
            compile_monthly_training_window(**args)
        args['admission']['training_exclusions'] = {'B': dict(reason='INSUFFICIENT_253_SESSION_PREDECISION_HISTORY', source_references=['review'], known_asof='2026-01-01')}
        with self.assertRaisesRegex(ValueError, 'FUTURE_EXCLUSION'):
            compile_monthly_training_window(**args)
        args['admission']['training_exclusions']['B']['known_asof'] = '2025-01-01'
        self.assertEqual(set(compile_monthly_training_window(**args)['prices']), {'SID:A'})

    def test_unreviewed_window_and_future_calendar_rejected(self):
        args = self.fixture(); args['admission']['status'] = 'PENDING'
        with self.assertRaisesRegex(ValueError, 'WINDOW_NOT_ADMITTED'):
            compile_monthly_training_window(**args)
        args = self.fixture(); args['window']['training_dates'][-1] = '2026-01-01'
        with self.assertRaisesRegex(ValueError, 'INVALID_MATURE_TRAINING_CALENDAR'):
            compile_monthly_training_window(**args)


if __name__ == '__main__':
    unittest.main()
