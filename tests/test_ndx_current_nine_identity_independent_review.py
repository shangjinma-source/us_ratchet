from copy import deepcopy
import hashlib,json
import unittest
from scripts import ndx_current_nine_identity_readback_20260919 as module


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=module.build()
        cls.plan=module.loads((module.FOLDER/'plan.json').read_bytes())

    def test_full_sealed_report_and_source_denominators_exact(self):
        path=module.FOLDER/'current_identity_facts.json';raw=path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'33eb7055e9072431def42f0a9fa88a0f03c245efd8664844c620955ca576fa32')
        self.assertEqual(json.loads(raw),self.report)
        self.assertEqual(len(self.report['candidate_facts']),11)
        self.assertEqual(len({r['ticker'] for r in self.report['rows']}),9)
        for row in self.report['rows']:
            candidate=row['matched_candidate'];position=row['reported_ticker_exchange_position']
            self.assertEqual(candidate['reported_cik'],row['current_reported_cik'])
            self.assertEqual(candidate['reported_tickers'][position],row['ticker'])
            self.assertEqual(candidate['reported_exchanges'][position],'Nasdaq')
            for key in ('historical_cusip_verified','provider_price_identity_bound','historical_alias_join_allowed','point_in_time_verified'):
                self.assertIs(row[key],False)

    def test_ticker_and_exchange_cannot_match_different_positions(self):
        facts=deepcopy(self.report['candidate_facts'])
        facts['0002023554'].update(reported_tickers=['SNDK','OTHER'],reported_exchanges=['NYSE','Nasdaq'])
        with self.assertRaisesRegex(ValueError,'Exactly one'):
            module.match_candidates(self.plan['rows'],facts)

    def test_former_name_and_old_cik_cannot_supply_current_ticker(self):
        facts=deepcopy(self.report['candidate_facts'])
        facts['0002023554'].update(reported_tickers=[],reported_exchanges=[],reported_name='SNDK',former_names_diagnostic_only=[{'name':'SNDK','from':'1900-01-01','to':'2099-01-01'}])
        with self.assertRaisesRegex(ValueError,'Exactly one'):
            module.match_candidates(self.plan['rows'],facts)
        body={'cik':'0001000180','name':'Sandisk','tickers':['SNDK'],'exchanges':['Nasdaq']}
        with self.assertRaisesRegex(ValueError,'exact request'):
            module.parse_identity(json.dumps(body),'0002023554')

    def test_nonfinite_and_nonstring_coordinates_rejected(self):
        for body in ('{"cik":"0002023554","name":"Issuer","tickers":[true],"exchanges":["Nasdaq"]}',
                     '{"cik":"0002023554","name":"Issuer","tickers":["SNDK"],"exchanges":["Nasdaq"],"extra":NaN}'):
            with self.assertRaises(ValueError):module.parse_identity(body,'0002023554')


if __name__=='__main__':unittest.main()
