import unittest
from copy import deepcopy
from scripts.research import review_downside_account_20261105_v4 as review

class V4Review(unittest.TestCase):
    def test_ctsh_complete_dates_amount_and_duplicates(self):
        a=review.base.read(review.ROOT/review.CTSH_PATH)
        d=review.base.read(review.ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json')
        self.assertEqual(len(review.validate_ctsh_pairs(a,d['dividend_events'],d['provider_event_inventory'])),10)
        wrong=deepcopy(a);wrong['dividend_events'][0]['amount_per_share']='1'
        with self.assertRaisesRegex(ValueError,'AMOUNT'):review.validate_ctsh_pairs(wrong,[],d['provider_event_inventory'])
        wrong=deepcopy(a);wrong['dividend_events'].pop()
        with self.assertRaisesRegex(ValueError,'TEN_COMPLETE'):review.validate_ctsh_pairs(wrong,[],d['provider_event_inventory'])
        wrong=deepcopy(a);wrong['dividend_events'][0]['payment_date']='2024-02-29'
        with self.assertRaisesRegex(ValueError,'DATES_SID'):review.validate_ctsh_pairs(wrong,[],d['provider_event_inventory'])
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):review.validate_ctsh_pairs(a,[a['dividend_events'][0]],d['provider_event_inventory'])

    def test_azn_ads_unit_and_conversion_rejected(self):
        a=review.base.read(review.ROOT/review.AZN_PATH)
        d=review.base.read(review.ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json')
        self.assertEqual(len(review.validate_azn_pairs(a,d['dividend_events'],d['provider_event_inventory'])),3)
        wrong=deepcopy(a)
        for section in ('review_rows','dividend_events'):wrong[section][0]['amount_per_share']='1'
        with self.assertRaisesRegex(ValueError,'HALF_UNIT'):review.validate_azn_pairs(wrong,[],d['provider_event_inventory'])
        wrong=deepcopy(a);wrong['dividend_events'][0]['ex_date']='2026-02-19'
        with self.assertRaisesRegex(ValueError,'DATE_DOMAIN'):review.validate_azn_pairs(wrong,[],d['provider_event_inventory'])
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):review.validate_azn_pairs(a,[a['dividend_events'][0]],d['provider_event_inventory'])

if __name__=='__main__':unittest.main()
