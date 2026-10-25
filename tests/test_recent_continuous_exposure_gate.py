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

    def test_period_review_cannot_extend_to_a_different_month(self):
        self.prices['action_stream_missing']=['new']
        evidence=dict(rows=[dict(security_id='new',status='REVIEWED_NO_ACTION_FOR_PERIOD',
            start_exclusive='2021-01-29',end_inclusive='2021-02-26')])
        self.assertTrue(exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,evidence)['admitted'])
        self.assertFalse(exposed_action_blockers(self.arguments,self.selection,'2021-03-31',self.prices,evidence)['admitted'])

    def test_period_review_never_overrides_observed_action(self):
        self.prices['action_stream_missing']=['new']
        self.prices['provider_event_inventory']=[dict(security_id='new',date='2021-02-15',kind='dividends')]
        evidence=dict(rows=[dict(security_id='new',status='REVIEWED_NO_ACTION_FOR_PERIOD',
            start_exclusive='2021-01-29',end_inclusive='2021-02-26')])
        self.assertFalse(exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,evidence)['admitted'])

    def test_liquidated_old_holding_needs_review_through_next_open(self):
        self.prices['action_stream_missing']=['old']
        evidence=dict(rows=[dict(security_id='old',status='REVIEWED_NO_ACTION_FOR_PERIOD',
            start_exclusive='2021-01-29',end_inclusive='2021-02-01')])
        self.prices['provider_event_inventory']=[dict(security_id='old',date='2021-02-15',kind='dividends')]
        result=exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,evidence,'2021-02-01')
        self.assertTrue(result['admitted'])
        self.assertEqual(result['exposure_end_by_security']['old'],'2021-02-01')
        self.assertEqual(result['exposure_end_by_security']['new'],'2021-02-26')

    def test_liquidation_day_action_still_blocks(self):
        self.prices['provider_event_inventory']=[dict(security_id='old',date='2021-02-01',kind='splits')]
        self.assertFalse(exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,
            active_date='2021-02-01')['admitted'])


if __name__ == '__main__':
    unittest.main()
