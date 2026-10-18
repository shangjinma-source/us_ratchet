from copy import deepcopy
import unittest
from scripts import ndx_current_seven_figi_readback_20260919 as module


class Tests(unittest.TestCase):
    def fixture(self):
        request=module.json_source.loads((module.FOLDER/'batch_2.request.json').read_bytes())
        response=module.json_source.loads((module.FOLDER/'batch_2.response.bin').read_bytes())
        return request,response
    def test_real_all_candidates_and_spcx_non_etf_not_issuer_join(self):
        report=module.build();self.assertEqual(report['request_count'],7);self.assertEqual(report['response_candidate_count'],7)
        self.assertTrue(all(r['mapping_observation_status']=='SINGLE_COMMON_STOCK_CANDIDATE_OBSERVED' for r in report['rows']))
        spcx=report['rows'][-1];self.assertEqual(spcx['requested_ticker'],'SPCX')
        self.assertFalse(spcx['unique_security_identity_adjudicated']);self.assertFalse(report['name_join_used'])
        self.assertTrue(all(not c['cusip_returned'] for r in report['rows'] for c in r['candidates']))
    def test_swapped_jobs_wrong_market_missing_class_and_shape_reject(self):
        for defect in ('swap','market','exchange','class','request','count'):
            jobs,response=self.fixture()
            if defect=='swap':response[0],response[2]=response[2],response[0]
            elif defect=='market':response[2]['data'][0]['marketSector']='Fund'
            elif defect=='exchange':response[2]['data'][0]['exchCode']='LN'
            elif defect=='class':response[2]['data'][0].pop('shareClassFIGI')
            elif defect=='request':jobs[2]['idType']='ID_CUSIP'
            else:response.pop()
            with self.subTest(defect=defect),self.assertRaises(ValueError):module.parse_jobs(jobs,response)
    def test_etf_and_multiple_candidates_retained_unresolved_not_named_join(self):
        jobs,response=self.fixture();etf=deepcopy(response[2]['data'][0]);etf.update(securityType='ETP',securityType2='Mutual Fund',name='OLD SPCX ETF')
        response[2]['data'].append(etf);rows=module.parse_jobs(jobs,response)
        self.assertEqual(rows[2]['candidate_count'],2);self.assertEqual(rows[2]['mapping_observation_status'],'MULTIPLE_CANDIDATES_UNRESOLVED')
        self.assertFalse(rows[2]['candidates'][1]['common_stock_type_observed']);self.assertFalse(rows[2]['unique_security_identity_adjudicated'])
        response[2]['data']=[etf]
        self.assertEqual(module.parse_jobs(jobs,response)[2]['mapping_observation_status'],'SINGLE_NON_COMMON_STOCK_CANDIDATE_NOT_ADMITTED')


if __name__=='__main__':unittest.main()
