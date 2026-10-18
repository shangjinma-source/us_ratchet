from copy import deepcopy
import json
import unittest
from scripts import ndx_current_nine_identity_readback_20260919 as module


class Tests(unittest.TestCase):
    def test_real_eleven_candidates_nine_current_matches(self):
        report=module.build();rows={r['ticker']:r for r in report['rows']}
        self.assertEqual(report['matched_count'],9)
        self.assertEqual(rows['SNDK']['current_reported_cik'],'0002023554')
        self.assertEqual(rows['SNDK']['excluded_candidates'][0]['cik'],'0001000180')
        self.assertEqual(rows['RKLB']['current_reported_cik'],'0001819994')
        self.assertEqual(rows['RKLB']['excluded_candidates'][0]['cik'],'0001849874')
        self.assertFalse(report['provider_price_identity_bound']);self.assertFalse(report['point_in_time_verified'])

    def test_cik_type_duplicate_ticker_array_length_and_duplicate_json_reject(self):
        body=dict(cik='0002023554',name='Issuer',tickers=['SNDK'],exchanges=['Nasdaq'])
        for field,value in [('cik',2023554),('cik','0001000180'),('tickers',['SNDK','SNDK']),('exchanges',[])]:
            bad=dict(body);bad[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):module.parse_identity(json.dumps(bad),'0002023554')
        with self.assertRaises(ValueError):module.parse_identity('{"cik":"0002023554","cik":"0001000180"}','0002023554')

    def test_name_not_binding_exchange_position_and_ambiguity(self):
        report=module.build();plan=module.loads((module.FOLDER/'plan.json').read_bytes())
        for defect in ('no_ticker','wrong_exchange','two_matches'):
            facts=deepcopy(report['candidate_facts'])
            if defect=='no_ticker':facts['0002023554']['reported_tickers']=['OTHER']
            elif defect=='wrong_exchange':facts['0002023554']['reported_exchanges']=['NYSE']
            else:facts['0001000180'].update(reported_tickers=['SNDK'],reported_exchanges=['Nasdaq'])
            with self.subTest(defect=defect),self.assertRaises(ValueError):module.match_candidates(plan['rows'],facts)


if __name__=='__main__':unittest.main()
