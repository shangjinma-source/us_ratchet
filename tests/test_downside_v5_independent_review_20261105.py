import unittest
from copy import deepcopy
from scripts.research import review_downside_account_20261105_v5 as review

class V5Review(unittest.TestCase):
    def test_lrcx_post_split_pair_and_existing_duplicates(self):
        a=review.base.read(review.ROOT/review.LRCX_PATH)
        d=review.base.read(review.ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json')
        old=review.base.read(review.ROOT/'tmp/downside_max10_20261105_late_v4/bounded_execution_evidence.json',True)['events']
        self.assertEqual(len(review.validate_lrcx_pairs(a,old,d['provider_event_inventory'])),2)
        wrong=deepcopy(a);wrong['dividend_events'][0]['security_id']='security:0000707549:512807108'
        with self.assertRaisesRegex(ValueError,'DATES_SID'):review.validate_lrcx_pairs(wrong,old,d['provider_event_inventory'])
        wrong=deepcopy(a);wrong['dividend_events'][0]['amount_per_share']='2.6'
        with self.assertRaisesRegex(ValueError,'AMOUNT'):review.validate_lrcx_pairs(wrong,old,d['provider_event_inventory'])
        with self.assertRaisesRegex(ValueError,'EXISTING_BOUND_PAIR'):review.validate_lrcx_pairs(a,[],d['provider_event_inventory'])
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):review.validate_lrcx_pairs(a,old+[a['dividend_events'][0]],d['provider_event_inventory'])

    def test_four_generation_parent(self):
        p=review.chain.ancestor(review.ROOT/'tmp/downside_max10_20261105_late_v4')
        self.assertEqual(len(p['book']['daily_ledger']),417)
        self.assertEqual(len(p['records']),21)
        self.assertEqual(p['summary']['searches'],dict(new=21,reused=0,replayed=8))

if __name__=='__main__':unittest.main()
