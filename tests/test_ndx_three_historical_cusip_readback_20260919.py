import unittest
from scripts import ndx_three_historical_cusip_readback_20260919 as m

class Tests(unittest.TestCase):
    def test_contiguous_cover_not_reporting_fund_identity(self):
        selection=dict(ticker='BKR',cik='0001701605',form='SC 13G',primary_document='bound.txt',filing_date='2023-02-03',accession='bound')
        raw=b'bound.txt SCHEDULE 13G BAKER HUGHES CO --- (Name of Issuer) Class A Common Stock --- (Title of Class of Securities) 05722G100 --- (CUSIP Number) December 31, 2022 Check the appropriate box BlackRock Inc'
        self.assertEqual(m.parse_primary(raw,'BKR',selection)['cusip'],'05722G100')
        for old,new in ((b'05722G100',b'05722G109'),(b'Class A',b'Class B'),(b'December 31, 2022',b'December 31, 2023'),(b'bound.txt',b'other.txt')):
            with self.subTest(old=old),self.assertRaises(ValueError):m.parse_primary(raw.replace(old,new),'BKR',selection)
        with self.assertRaises(ValueError):m.parse_primary(raw,'BKR',dict(selection,cik='0001364742'))

    def test_actual_10k_covers_do_not_claim_sidecar_cusip(self):
        for ticker,fact in m.FACTS.items():
            raw=(m.SECROOT/fact['file']).read_bytes()
            self.assertEqual(m.hashlib.sha256(raw).hexdigest(),fact['sha'])
            self.assertFalse(m.parse_cover(raw,ticker)['cusip_present_in_filing_text'])
            self.assertTrue(m.checksum(fact['cusip']))

if __name__=='__main__':unittest.main()
