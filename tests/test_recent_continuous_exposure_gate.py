"""Protect causal book admission against omitted exposed corporate actions."""
import unittest
from scripts.run_recent_continuous_probe import exposed_action_blockers


class ExposureGateTests(unittest.TestCase):
    def setUp(self):
        self.arguments = dict(decision_date='2021-01-29', account_state=dict(shares={'old':2,'zero':0}))
        self.selection = dict(target_quantities={'new':3,'unused':0})
        self.prices = dict(action_stream_missing=[],provider_event_inventory=[])

    def check(self):
        return exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices)

    def test_new_target_action_on_last_day_blocks(self):
        self.prices['provider_event_inventory'] = [dict(security_id='new',date='2021-02-26',kind='splits')]
        self.assertFalse(self.check()['admitted'])

    def test_existing_holdings_require_action_stream_even_if_not_targeted(self):
        self.prices['action_stream_missing'] = ['old']
        self.assertEqual(self.check()['missing_action_streams'],['old'])

    def test_unheld_actions_and_past_events_do_not_block(self):
        self.prices['action_stream_missing'] = ['unused']
        self.prices['provider_event_inventory'] = [dict(security_id='unused',date='2021-02-01'),
                                                  dict(security_id='old',date='2021-01-29')]
        self.assertTrue(self.check()['admitted'])


if __name__ == '__main__':
    unittest.main()
