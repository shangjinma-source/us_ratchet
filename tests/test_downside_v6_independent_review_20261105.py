import unittest
from copy import deepcopy
from scripts.research import review_downside_account_20261105_v6 as review

class V6Review(unittest.TestCase):
    def test_insm_empty_financial_events_and_scoped_proof(self):
        a=review.base.read(review.ROOT/review.INSM_PATH)
        d=review.base.read(review.ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json')
        self.assertEqual(review.validate_insm_absence(a,d['dividend_events'],d['provider_event_inventory']),[])
        bad=deepcopy(a);bad['dividend_events']=[]
        with self.assertRaisesRegex(ValueError,'NO_FINANCIAL_EVENTS'):review.validate_insm_absence(bad,[],d['provider_event_inventory'])
        bad=deepcopy(a);bad['review_rows'][0]['end_inclusive']='2027-01-01'
        with self.assertRaisesRegex(ValueError,'EXACT_SCOPE'):review.validate_insm_absence(bad,[],d['provider_event_inventory'])
        with self.assertRaisesRegex(ValueError,'KNOWN_PROVIDER_EVENT'):review.validate_insm_absence(a,[],d['provider_event_inventory']+[dict(ticker='INSM')])

if __name__=='__main__':unittest.main()
