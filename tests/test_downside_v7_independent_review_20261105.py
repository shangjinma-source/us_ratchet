import unittest
from copy import deepcopy
from scripts.research import review_downside_account_20261105_v7 as review

class V7Review(unittest.TestCase):
    def test_class_c_amount_dates_and_duplicate(self):
        a=review.base.read(review.ROOT/review.ARTIFACT)
        d=review.base.read(review.ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json')
        self.assertEqual(len(review.validate_pairs(a,d['dividend_events'],d['provider_event_inventory'])),4)
        for field,value,reason in [('nominal_unit','GOOGL_CLASS_A','CLASS_C'),('amount_per_share','0.21','NOMINAL_AMOUNT'),('payment_date','2026-06-16','SID_DATES')]:
            bad=deepcopy(a);bad['review_rows'][1][field]=value
            with self.assertRaisesRegex(ValueError,reason):review.validate_pairs(bad,[],d['provider_event_inventory'])
        bad=deepcopy(a);bad['dividend_events'].pop()
        with self.assertRaisesRegex(ValueError,'FOUR_COMPLETE'):review.validate_pairs(bad,[],d['provider_event_inventory'])
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):review.validate_pairs(a,[a['dividend_events'][0]],d['provider_event_inventory'])

    def test_six_generation_parent(self):
        p=review.previous.chain.ancestor(review.ROOT/'tmp/downside_max10_20261105_late_v6')
        self.assertEqual(len(p['book']['daily_ledger']),541)
        self.assertEqual(len(p['records']),27)
        self.assertIn('tmp/downside_max10_20261105_late_v5/contract.json',p['hashes'])

if __name__=='__main__':unittest.main()
