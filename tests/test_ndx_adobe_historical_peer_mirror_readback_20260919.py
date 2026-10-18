import unittest
from bs4 import BeautifulSoup
from scripts import ndx_adobe_historical_peer_mirror_readback_20260919 as module


class Tests(unittest.TestCase):
    def test_bound_both_years_and_security_scope(self):
        report=module.build()
        self.assertEqual([x['issuer_row_count'] for x in report['tables']],[100,100])
        self.assertFalse(report['index_provider_membership_baseline_verified'])
        self.assertFalse(report['point_in_time_verified'])
        for table in report['tables']:
            self.assertEqual([r['ordinal'] for r in table['rows']],list(range(1,101)))
            self.assertNotIn('GOOG',[r['ticker'] for r in table['rows']])

    def test_missing_duplicate_bad_header_wrong_date_reject(self):
        for defect in ('missing','duplicate','header','date'):
            raw=(module.FOLDER/'2023.response.bin').read_bytes()
            soup=BeautifulSoup(raw,'html.parser');tables=soup.find_all('table')
            if defect=='missing':tables[3].find_all('tr')[2].decompose()
            elif defect=='duplicate':tables[3].find_all('tr')[3].find_all('td')[0].string='1'
            elif defect=='header':tables[3].find_all('tr')[1].find_all('td')[1].string='ChangedTicker'
            else:
                raw=raw.replace(b'January 1, 2023',b'January 1, 2025')
            with self.subTest(defect=defect),self.assertRaises(ValueError):
                module.extract(raw if defect=='date' else str(soup).encode(),2023)


if __name__=='__main__':unittest.main()
