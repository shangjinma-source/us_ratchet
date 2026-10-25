from copy import deepcopy
import unittest
from backtest.unexposed_post_close_event_review import review_unexposed_post_close


class PostCloseReviewTests(unittest.TestCase):
    def arguments(self):
        return dict(day='2026-01-02', state={'shares': {'A': 4, 'P': 0}, 'distribution_rights': []},
                    targets={'A': 4}, tracked_securities=['A'], events=[dict(
                        event_id='split-off', effective_date='2026-01-02', timing='AFTER_CLOSE',
                        parent_sid='P', post_parent_sid='P', child_sid='C', source_references=['fixture'])])

    def test_unheld_event_preserves_no_order_wait(self):
        arguments = self.arguments()
        before = deepcopy(arguments)
        result = review_unexposed_post_close(**arguments)
        self.assertEqual(result['status'], 'UNEXPOSED_RISK_DOMAIN_UNCHANGED')
        self.assertFalse(result['orders_permitted'])
        self.assertEqual(arguments, before)

    def test_any_exposure_or_missing_evidence_blocks(self):
        for mode in ('held', 'target', 'tracked', 'rights', 'source', 'date', 'duplicate'):
            with self.subTest(mode=mode):
                arguments = self.arguments()
                if mode == 'held': arguments['state']['shares']['P'] = 1
                if mode == 'target': arguments['targets']['C'] = 1
                if mode == 'tracked': arguments['tracked_securities'].append('P')
                if mode == 'rights': arguments['state']['distribution_rights'] = [{}]
                if mode == 'source': arguments['events'][0]['source_references'] = []
                if mode == 'date': arguments['events'][0]['effective_date'] = '2026-01-05'
                if mode == 'duplicate': arguments['events'].append(deepcopy(arguments['events'][0]))
                with self.assertRaises(ValueError): review_unexposed_post_close(**arguments)


if __name__ == '__main__': unittest.main()
