from copy import deepcopy
import unittest
from backtest import ndx_post_action_interval_research as core
from scripts import ndx_post_action_interval_plan_20260919 as plan


class Tests(unittest.TestCase):
    def arguments(self):
        return dict(ticker='HON', calendar=['2026-06-29','2026-06-30'],
            returned_events=[dict(session='2025-10-30',provider_fields={'splitRatio':'1061:1000'}),
                dict(session='2026-06-29',provider_fields={'splitRatio':'1907:2000'})],
            official_boundary=dict(ticker='HON',first_post_action_session='2026-06-29',post_action_cusip='438516205',role='POST_REVERSE_SPLIT_NEW_CUSIP'),
            completed_before='2026-09-18')

    def test_preserves_complex_events_without_share_multiplier(self):
        args=self.arguments();before=deepcopy(args); result=core.propose_interval(**args)
        self.assertEqual(args,before)
        self.assertEqual(result['returned_events'],args['returned_events'])
        for flag in ('simple_split_whole_channel_admitted','first_requested_session_return_allowed','input_artifact_binding_verified',
                     'no_returned_later_event_proves_complete_actions','quote_reconstruction_performed','provider_price_identity_bound'):
            self.assertFalse(result[flag])

    def test_cross_floor_later_action_identity_splice_or_partial_day_rejected(self):
        for mode in ('floor','later','identity','incomplete','missing','duplicate','unknown'):
            args=self.arguments()
            if mode=='floor':args['calendar'].insert(0,'2026-06-26')
            if mode=='later':args['returned_events'].append(dict(session='2026-08-01'))
            if mode=='identity':args['official_boundary']['post_action_cusip']='OLD'
            if mode=='incomplete':args['calendar'].append('2026-09-18')
            if mode=='missing':args['returned_events'].pop()
            if mode=='duplicate':args['returned_events'].append(deepcopy(args['returned_events'][0]))
            if mode=='unknown':args['ticker']='CMCSA'
            with self.subTest(mode=mode),self.assertRaises(ValueError):core.propose_interval(**args)

    def test_actual_existing_bytes_four_proposals_two_blocked(self):
        result=plan.build();rows={r['ticker']:r for r in result['rows']}
        self.assertEqual((result['conditional_interval_proposals'],result['still_blocked_count']),(4,2))
        self.assertEqual({t:len(rows[t]['proposed_interval']['calendar']) for t in core.SUPPORTED},
            {'EXC':1160,'HON':57,'LRCX':490,'WDC':394})
        self.assertIsNone(rows['CMCSA']['proposed_interval']);self.assertIsNone(rows['TRI']['proposed_interval'])
        self.assertEqual(rows['WDC']['proposed_interval']['post_action_cusip'],'958102105')
        self.assertNotEqual(rows['WDC']['proposed_interval']['post_action_cusip'],'958102121')
        self.assertFalse(result['quote_reconstruction_performed'])


if __name__=='__main__':unittest.main()
