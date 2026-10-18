import copy
import unittest
from backtest import ndx_gap_monthly_observation_policy_research as module


def row(sequence, session, kind='MISSED_OBSERVATION', seal='NOT_ATTEMPTED'):
    return {'sequence':sequence,'session':session,'kind':kind,'seal_status':seal,
            'evidence_reference':{'path':'ledger.json','sha256':'a'*64,'json_pointer':'/events/'+str(sequence-1)}}


def fixture():
    return dict(policy_id=module.POLICY_ID,known_rows=[row(1,'2026-09-24','SEALED_PARENT_OBSERVED_SESSION'),
        row(2,'2026-09-25'),row(3,'2026-10-01')],new_prospective_observations=[])


class MonthlyTests(unittest.TestCase):
    def test_gap_only_october_has_no_observed_coordinate(self):
        args=fixture(); original=copy.deepcopy(args)
        result=module.monthly_observation_coordinates(**args)
        self.assertEqual(args,original)
        self.assertEqual(result['months'][1],{'month':'2026-10','first_observed_session':None,'observed_count':0,'missed_count':1})
        self.assertFalse(result['rows'][2]['monthly_coordinate_eligible'])

    def test_failed_first_observation_still_consumes_coordinate(self):
        args=fixture(); args['new_prospective_observations']=[row(4,'2026-10-02','PROSPECTIVE_OBSERVED_SESSION','FAILED'),
            row(5,'2026-10-05','PROSPECTIVE_OBSERVED_SESSION','SEALED')]
        result=module.monthly_observation_coordinates(**args)
        self.assertEqual([r['monthly_coordinate_eligible'] for r in result['rows']],[True,False,False,True,False])
        self.assertFalse(result['candidate_seal_allowed'])
        args['new_prospective_observations'].pop(0)
        with self.assertRaises(ValueError): module.monthly_observation_coordinates(**args)

    def test_schema_type_pointer_order_attacks(self):
        for mutation in (
            lambda a:a.update(policy_id='FIRST_MARKET_DATE'),
            lambda a:a['known_rows'][0].update(sequence=True),
            lambda a:a['known_rows'][1].update(session='2026-09-24'),
            lambda a:a['known_rows'][1].update(kind='TIMELY_LATEST_ROW_REQUIRES_NEW_LINEAGE_REVIEW'),
            lambda a:a['known_rows'][1]['evidence_reference'].pop('json_pointer'),
            lambda a:a['known_rows'][1]['evidence_reference'].update(json_pointer='/events/0'),
            lambda a:a['known_rows'].reverse(),
            lambda a:a['known_rows'][1].update(seal_status='FAILED'),
        ):
            args=fixture(); mutation(args)
            with self.assertRaises(ValueError): module.monthly_observation_coordinates(**args)

    def test_late_row_cannot_be_new_observed(self):
        args=fixture(); args['new_prospective_observations']=[row(4,'2026-10-02')]
        with self.assertRaises(ValueError): module.monthly_observation_coordinates(**args)

    def test_unknown_parent_seal_still_observed_not_invented(self):
        args=fixture(); args['known_rows'][0]['seal_status']='UNKNOWN'
        result=module.monthly_observation_coordinates(**args)
        self.assertTrue(result['rows'][0]['monthly_coordinate_eligible'])
        self.assertEqual(result['rows'][0]['input_row']['seal_status'],'UNKNOWN')
        args['known_rows'][1]['seal_status']='UNKNOWN'
        with self.assertRaises(ValueError): module.monthly_observation_coordinates(**args)


if __name__=='__main__': unittest.main()
