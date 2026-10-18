"""Read-only sealed fixtures and adversarial identity boundaries."""
from copy import deepcopy
import unittest
import test_ndx_legacy_twelve_conditional_identity_20260923 as fixtures

m=fixtures.m


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.docs=fixtures.documents()

    def test_class_switch_cannot_collapse_cusip_or_certify_conversion(self):
        for attack in ('cusip','team_conversion','local_cover'):
            docs=deepcopy(self.docs)
            if attack=='cusip':next(r for r in docs['return_identity']['rows'] if r['ticker']=='GOOG')['cusip']='02079K305'
            else:
                row=next(r for r in docs['facts']['rows'] if r['ticker']=='TEAM')
                if attack=='team_conversion':row['old_issuer_or_class_conversion_verified']=True
                else:row['local_cover_context']['cusip_directly_verified_from_cover']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs)

    def test_row_permission_interval_and_price_denominator_rejected(self):
        for attack in ('row_pit','row_interval','old_enph','cells','clock'):
            docs=deepcopy(self.docs)
            if attack=='row_pit':docs['facts']['rows'][0]['point_in_time_verified']=True
            if attack=='row_interval':docs['facts']['rows'][0]['continuous_identity_interval']={'start':'2023-03-31','end':'2023-09-01'}
            if attack=='old_enph':docs['enph']['identity_projection']['enph_original_interval_certification_extended']=True
            if attack=='cells':docs['prices']['price_cell_count']=1498
            if attack=='clock':docs['lane']['decisions'][4]['execution_date']='2023-08-02'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs)

    def test_full_original_facts_and_causal_selected_risk_maps_retained(self):
        value=m.assemble(deepcopy(self.docs));by={r['ticker']:r for r in value['rows']}
        for ticker in m.NEW:
            original=next(r for r in self.docs['facts']['rows'] if r['ticker']==ticker)
            self.assertEqual(by[ticker]['evidence']['dated_evidence'],original)
        self.assertEqual(by['GOOG']['issuer_id'],by['GOOGL']['issuer_id'])
        self.assertNotEqual(by['GOOG']['security_id'],by['GOOGL']['security_id'])
        self.assertFalse(value['dated_fact_availability_backdated'])
        for choice in value['saved_lane_choices']:
            expected={sid:r['risk_chain'] for sid,r in choice['saved_candidate']['selected'].items()}
            self.assertEqual(value['selected_risk_chains_by_decision'][choice['decision_date']],expected)
        self.assertFalse(value['execution_risk_chain_union_verified'])


if __name__=='__main__':unittest.main()
