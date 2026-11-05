import unittest
from copy import deepcopy
from scripts.research import review_downside_account_20261105_v6 as review

class V6Review(unittest.TestCase):
    def test_actual_v9_normalized_absence_and_reject_scope_drift(self):
        artifact=review.base.read(review.ROOT/review.INSM_PATH)
        old=review.base.read(review.ROOT/'tmp/downside_max10_20261105_late_v5/2025-12-31.exposure.json',True)
        new=review.base.read(review.ROOT/'tmp/downside_max10_20261105_late_v9/2025-12-31.exposure.json',True)
        missing=old['missing_action_streams'][0]
        review.check_insm_applied(new,missing,artifact)
        for field,value in [('security_id','other'),('end_inclusive','2027-01-01'),('selected_price_sources',['wrong']),('legacy_request_check',{})]:
            bad=deepcopy(new)
            row=next(e['review'] for e in bad['accepted_period_reviews'] if e['missing_stream']['security_id']==missing['security_id'])
            row[field]=value
            with self.assertRaisesRegex(ValueError,'SCOPED_REVIEW_APPLIED'):review.check_insm_applied(bad,missing,artifact)
        bad=deepcopy(new)
        entry=next(e for e in bad['accepted_period_reviews'] if e['missing_stream']['security_id']==missing['security_id'])
        entry['missing_stream']['selected_source_segments'][0]['end']='2027-01-01'
        with self.assertRaisesRegex(ValueError,'SCOPED_REVIEW_APPLIED'):review.check_insm_applied(bad,missing,artifact)

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
