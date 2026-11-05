import unittest
from copy import deepcopy
from scripts.research import review_downside_account_20261105_v3 as review

class ChainReview(unittest.TestCase):
    def test_ceg_exact_not_provider_rounding(self):
        a=review.base.read(review.ROOT/review.CEG_PATH)
        d=review.base.read(review.ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json')
        self.assertEqual(len(review.validate_ceg_pairs(a,d['dividend_events'],d['provider_event_inventory'])),10)
        wrong=deepcopy(a)
        for section in ('review_rows','dividend_events','mapping'):wrong[section][0]['amount_per_share']='0.353'
        with self.assertRaisesRegex(ValueError,'EXACT_ISSUER_AMOUNT'):review.validate_ceg_pairs(wrong,[],d['provider_event_inventory'])
        wrong=deepcopy(a);wrong['dividend_events'].pop()
        with self.assertRaisesRegex(ValueError,'TEN_COMPLETE'):review.validate_ceg_pairs(wrong,[],d['provider_event_inventory'])
        with self.assertRaisesRegex(ValueError,'ALREADY_PRESENT'):review.validate_ceg_pairs(a,[a['dividend_events'][0]],d['provider_event_inventory'])

    def test_saved_two_generation_source_ownership(self):
        p=review.ancestor(review.ROOT/'tmp/downside_max10_20261105_late_v2')
        self.assertEqual(len(p['book']['daily_ledger']),83)
        self.assertEqual(len(p['records']),5)
        oldest=review.base.read(review.ROOT/'tmp/downside_max10_20261105_late_v1/contract.json',True)['source_hashes']
        self.assertEqual(p['records']['2023-12-29']['pins'],oldest)
        self.assertEqual(p['records']['2024-04-30']['pins'],p['contract']['source_hashes'])
        self.assertNotEqual(oldest,p['contract']['source_hashes'])

if __name__=='__main__':unittest.main()
