"""Read-only parent plus synthetic CPRT declaration; no published wiring."""
import unittest
import test_ndx_new_cutoff_identity_risk_wiring_v3_20260925 as owner
from scripts import ndx_new_cutoff_identity_risk_wiring_v3_20260925 as m


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):owner.Tests.setUpClass()

    def test_late_review_is_not_earlier_filing_availability(self):
        for key,value in [('saved_review_selection_postdates_window_start',False),('early_window_review_availability_verified',True)]:
            docs=owner.Tests().docs();docs['cprt_declaration'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.assemble(docs)
        docs=owner.Tests().docs();docs['cprt_declaration']['saved_review_decision']['selection_date']='2025-09-26'
        with self.assertRaises(ValueError):m.assemble(docs)

    def test_old_alternatives_and_full_non_cprt_rows_preserved(self):
        docs=owner.Tests().docs();result=m.assemble(docs)
        self.assertEqual(result['v3_extended_provenance'][0]['original_row'],next(r for r in docs['parent_wiring']['rows'] if r['ticker']=='CPRT'))
        for ticker in ('PCAR','CRWD','GOOG','GOOGL'):
            self.assertEqual(next(r for r in result['rows'] if r['ticker']==ticker),next(r for r in docs['parent_wiring']['rows'] if r['ticker']==ticker))
        old=result['v3_extended_provenance'][0]['complete_increment_evidence']['original_business_fact']
        self.assertIsNone(old['assigned_risk_chain']);self.assertEqual(len(old['candidate_risk_chains']),3)
        self.assertTrue(all(result[k] is False for k in m.FALSE))

    def test_prior_unresolved_alternative_cannot_be_erased(self):
        docs=owner.Tests().docs();docs['cprt_declaration']['original_business_fact']['candidate_risk_chains']=['automotive']
        with self.assertRaises(ValueError):m.assemble(docs)


if __name__=='__main__':unittest.main()
