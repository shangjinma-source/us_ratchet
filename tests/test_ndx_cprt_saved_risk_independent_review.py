"""Synthetic source parsing and scope checks; no declaration publication."""
from copy import deepcopy
import unittest
import test_ndx_cprt_saved_risk_adjudication_20260925 as f
from scripts import ndx_cprt_saved_risk_adjudication_20260925 as m


class IndependentReview(unittest.TestCase):
    def test_late_review_and_prior_facts_are_not_upgraded(self):
        docs,raw=f.fixture();original=deepcopy(docs)
        result=f.run(docs,raw)
        self.assertEqual(docs,original)
        self.assertEqual(result['original_identity_fact'],original['identity']['rows'][0])
        self.assertEqual(result['original_business_fact'],original['business']['rows'][0])
        self.assertTrue(result['saved_review_selection_postdates_window_start'])
        self.assertFalse(result['early_window_review_availability_verified'])
        self.assertFalse(result['classification_uniquely_proven'])

    def test_current_ticker_review_not_dated_cusip_evidence(self):
        docs,raw=f.fixture();docs['snapshot']['decisions'][0]['security_ids']=['security:0000900075:217204106']
        with self.assertRaises(ValueError):f.run(docs,raw)

    def test_duplicate_decision_and_false_direct_identity_proof_rejected(self):
        for attack in ('duplicate','direct'):
            docs,raw=f.fixture()
            if attack=='duplicate':docs['snapshot']['decisions'].append(deepcopy(docs['snapshot']['decisions'][0]))
            else:docs['identity']['rows'][0]['direct_single_document_cusip_cik_proof']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):f.run(docs,raw)

    def test_evidence_date_cannot_replace_review_selection_date(self):
        docs,raw=f.fixture();docs['snapshot']['decisions'][0]['selection_date']='2025-09-26'
        with self.assertRaises(ValueError):f.run(docs,raw)


if __name__=='__main__':unittest.main()
