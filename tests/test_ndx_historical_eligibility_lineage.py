from copy import deepcopy
import unittest
from backtest.ndx_historical_eligibility_lineage import _verify_rows, _csv, verify_historical_eligibility


class HistoricalLineageTests(unittest.TestCase):
    def fixture(self):
        common=dict(security_id='s',issuer_id='i',ticker='A',risk_chain='chain',status='accepted',
            effective_from='2023-01-01',effective_to='2023-11-29',evidence_available_date='2023-01-01',
            selection_date_start='2023-01-01',selection_date_end='2023-11-29',
            selection_dates='2023-01-01;2023-11-29',observations_count='2',
            evidence_source_type='sec',evidence_ids='e',evidence_locator='https://example.com/e')
        eligible=dict(common,selection_date='2024-02-01',universe_track='strict_technology',
            membership_snapshot_date='2023-11-29',taxonomy_ticker_aliases='A',strict_technology_eligible='True',
            membership_window_eligible='True',event_gap_blocked='False')
        evidence=dict(common,evidence_id='e',validation_status='valid',scope='issuer',effective_to='')
        return dict(selection_date='2024-02-01',securities={'s':{'ticker':'A','issuer_id':'i'}},
            universe_track='strict_technology',eligible=[eligible],records=[dict(common)],evidence=[evidence])

    def test_linked_artifact_still_unknown_current_scope(self):
        result=_verify_rows(**self.fixture())[0]
        self.assertTrue(result['historical_artifact_verified'])
        self.assertEqual(result['current_technology_qualification'],'UNKNOWN')

    def test_missing_not_a_negative_technology_classification(self):
        args=self.fixture(); args['eligible']=[]
        result=_verify_rows(**args)[0]
        self.assertFalse(result['historical_artifact_verified'])
        self.assertEqual(result['current_technology_qualification'],'UNKNOWN')

    def test_future_expired_identity_and_duplicate_fail_closed(self):
        for table,field,value in [('evidence','evidence_available_date','2024-02-02'),
                ('evidence','effective_to','2024-01-01'),('eligible','issuer_id','wrong')]:
            args=self.fixture();args[table][0][field]=value
            with self.assertRaises(ValueError):_verify_rows(**args)
        args=self.fixture();args['evidence'].append(deepcopy(args['evidence'][0]))
        with self.assertRaises(ValueError):_verify_rows(**args)

    def test_csv_duplicate_and_ragged_rejected(self):
        for raw in (b'a,a\n1,2\n',b'a,b\n1\n'):
            with self.assertRaises(ValueError):_csv(raw)

    def test_same_issuer_multiple_security_universe_allowed(self):
        args=self.fixture();args['securities']['s2']={'ticker':'B','issuer_id':'i'}
        for table in ('eligible','records','evidence'):
            item=deepcopy(args[table][0]);item.update(security_id='s2',ticker='B')
            if table=='eligible':item['taxonomy_ticker_aliases']='B'
            args[table].append(item)
        self.assertEqual(len(_verify_rows(**args)),2)

    def test_real_enph_observation_end_not_evidence_expiry(self):
        result=verify_historical_eligibility(selection_date='2024-02-01',universe_track='strict_technology',
            securities={'security:0001463101:29355A107':{'ticker':'ENPH','issuer_id':'issuer:0001463101'}})
        self.assertTrue(result['securities'][0]['historical_artifact_verified'])
        self.assertEqual(result['securities'][0]['evidence'][0]['effective_to'],'')

    def test_membership_not_in_record_observations_rejected(self):
        args=self.fixture();args['eligible'][0]['membership_snapshot_date']='2023-11-28'
        with self.assertRaises(ValueError):_verify_rows(**args)


if __name__=='__main__':unittest.main()
