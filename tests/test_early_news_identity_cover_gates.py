from copy import deepcopy
import unittest
from bs4 import BeautifulSoup
from scripts.verify_early_news_identity_covers_v1 import source_guard, context_identifier


class CoverGateTests(unittest.TestCase):
    def test_source_identity_url_and_exposure_are_bound(self):
        source=dict(cik=123,filings=dict(recent=dict(accessionNumber=['0000000123-21-000001'],
            primaryDocument=['report.htm'],acceptanceDateTime=['2021-11-01T10:00:00Z'])))
        receipt=dict(cik=123,accession='0000000123-21-000001',acceptance='2021-11-01T10:00:00Z',
            first_exposure='2022-01-03',url='https://www.sec.gov/Archives/edgar/data/123/000000012321000001/report.htm')
        source_guard(receipt,source,'2022-01-03')
        for key,value in [('cik',456),('url',receipt['url'].replace('/123/','/456/')),
                          ('url',receipt['url'].replace('report.htm','another.htm')),
                          ('first_exposure','2023-01-03')]:
            altered=deepcopy(receipt);altered[key]=value
            with self.assertRaises(ValueError):source_guard(altered,source,'2022-01-03')

    def test_duplicate_context_and_non_sec_scheme_rejected(self):
        raw='<xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000123</xbrli:identifier></xbrli:entity></xbrli:context>'
        self.assertEqual(context_identifier(BeautifulSoup(raw,'html.parser'),'c','0000000123').text,'0000000123')
        for altered in [raw+raw,raw.replace('http://www.sec.gov/CIK','https://evil.example/CIK')]:
            with self.assertRaises(ValueError):context_identifier(BeautifulSoup(altered,'html.parser'),'c','0000000123')


if __name__=='__main__':unittest.main()
