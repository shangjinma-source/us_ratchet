from copy import deepcopy
import unittest
from backtest import ndx_gap_monthly_observation_policy_research as m
from test_ndx_gap_monthly_observation_policy_research import fixture,row

class MonthlyIndependentReview(unittest.TestCase):
    def test_gap_does_not_consume_failed_observation_does(self):
        a=fixture();a['known_rows'][0]['seal_status']='UNKNOWN'
        a['new_prospective_observations']=[row(4,'2026-10-02','PROSPECTIVE_OBSERVED_SESSION','FAILED'),row(5,'2026-10-05','PROSPECTIVE_OBSERVED_SESSION','SEALED'),row(6,'2026-11-02','PROSPECTIVE_OBSERVED_SESSION','NOT_ATTEMPTED')]
        old=deepcopy(a);r=m.monthly_observation_coordinates(**a)
        self.assertEqual(a,old);self.assertEqual([x['monthly_coordinate_eligible'] for x in r['rows']],[True,False,False,True,False,True])
        for status in ('UNKNOWN','NOT_ATTEMPTED','SEALED'):
            a['new_prospective_observations'][0]['seal_status']=status
            changed=m.monthly_observation_coordinates(**a)
            self.assertEqual([x['monthly_coordinate_eligible'] for x in changed['rows']],[True,False,False,True,False,True])
        for key in ('candidate_seal_allowed','cohort_registration_allowed','input_timeliness_verified','complete_sequence_independently_verified','point_in_time_verified','user_choice_authenticity_verified'):self.assertIs(r[key],False)

    def test_no_seal_outcome_filter_or_relabelled_new_gap(self):
        for kind in ('skipsequence','gapnew','duplicate_ref','bad_escape','boolseq','weekend'):
            a=fixture();a['new_prospective_observations']=[row(4,'2026-10-02','PROSPECTIVE_OBSERVED_SESSION')]
            r=a['new_prospective_observations'][0]
            if kind=='skipsequence':r['sequence']=5
            elif kind=='gapnew':r['kind']='MISSED_OBSERVATION'
            elif kind=='duplicate_ref':r['evidence_reference']=deepcopy(a['known_rows'][0]['evidence_reference'])
            elif kind=='bad_escape':r['evidence_reference']['json_pointer']='/events/~2'
            elif kind=='boolseq':a['known_rows'][0]['sequence']=True
            else:r['session']='2026-10-03'
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.monthly_observation_coordinates(**a)

if __name__=='__main__':unittest.main()
