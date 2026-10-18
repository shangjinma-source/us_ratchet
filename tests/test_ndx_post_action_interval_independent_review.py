import unittest
from backtest import ndx_post_action_interval_research as core
from scripts import ndx_post_action_interval_plan_20260919 as recipe


class IndependentReview(unittest.TestCase):
    def test_later_event_cannot_hide_outside_requested_short_calendar(self):
        floor,cusip,role=core.SUPPORTED['WDC']
        with self.assertRaisesRegex(ValueError,'Later returned action'):
            core.propose_interval(ticker='WDC',calendar=[floor],returned_events=[{'session':floor},{'session':'2026-01-02'}],official_boundary=dict(ticker='WDC',first_post_action_session=floor,post_action_cusip=cusip,role=role),completed_before='2026-09-18')

    def test_real_source_closure_and_interval_partition_denominators(self):
        value=recipe.build();recipe.verify(value['source_hashes'])
        for row in value['rows']:
            proposal=row['proposed_interval']
            if proposal is None:
                self.assertIn(row['ticker'],('TRI','CMCSA'));continue
            self.assertEqual(len(proposal['calendar'])+len(row['excluded_pre_boundary_provider_dates'])+len(row['receipt_or_later_dates_excluded']),row['full_provider_row_count'])
            self.assertEqual(proposal['returned_events'],row['all_returned_events'])
            self.assertFalse(proposal['first_requested_session_return_allowed'])
            self.assertFalse(proposal['provider_price_identity_bound'])
            self.assertTrue(proposal['excluded_pre_boundary_history_still_blocked'])


if __name__=='__main__':unittest.main()
