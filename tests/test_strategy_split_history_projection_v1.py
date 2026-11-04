from copy import deepcopy
import unittest
from core.monthly_peak_exit import advance_monthly_exit
from data.strategy_split_history_projection_v1 import project_history_units


class SplitHistoryTests(unittest.TestCase):
    def setUp(self):
        self.days = ['2026-11-02','2026-11-19','2026-11-20']
        self.action = dict(kind='SPLIT_CONFIRMED', security_id='S', ratio=8,
            effective_at='2026-11-20T14:30:00Z', old_unit_id='old', new_unit_id='new')
        self.rows = [dict(decision_date=self.days[0], session_date=day,
            closes={'S':price,'T':'50'}, unit_ids={'S':unit,'T':'t'}, evidence_sha256='a'*64)
            for day,price,unit in zip(self.days, ['1000','1100','137.5'], ['old','old','new'])]

    def test_raw_history_preserved_and_uniform_replay_has_no_false_exit(self):
        original = deepcopy(self.rows)
        output = project_history_units(observations=self.rows, action=self.action, expected_sessions=self.days)
        self.assertEqual(self.rows, original)
        self.assertEqual(output['payload']['original_observations'], original)
        state = None
        for row in output['payload']['normalized_observations']:
            arguments = {key:value for key,value in row.items() if key != 'evidence_sha256'}
            state = advance_monthly_exit(state=state, account_id='a', baseline_targets={'S':80,'T':1}, **arguments)['state']
        self.assertEqual(state['peaks'], {'S':'275/2','T':'50'})
        self.assertEqual(state['exited'], [])

    def test_pre_split_exit_survives_normalization(self):
        self.rows[1]['closes']['S'] = '700'
        output = project_history_units(observations=self.rows, action=self.action, expected_sessions=self.days)
        state = None
        for row in output['payload']['normalized_observations']:
            arguments = {key:value for key,value in row.items() if key != 'evidence_sha256'}
            state = advance_monthly_exit(state=state, account_id='a', baseline_targets={'S':80,'T':1}, **arguments)['state']
        self.assertEqual(state['exited'], ['S'])

    def test_missing_day_or_wrong_unit_rejected(self):
        with self.assertRaisesRegex(ValueError, 'FULL_HISTORY'):
            project_history_units(observations=self.rows[1:], action=self.action, expected_sessions=self.days)
        self.rows[-1]['unit_ids']['S'] = 'old'
        with self.assertRaisesRegex(ValueError, 'UNIT_MISMATCH'):
            project_history_units(observations=self.rows, action=self.action, expected_sessions=self.days)
