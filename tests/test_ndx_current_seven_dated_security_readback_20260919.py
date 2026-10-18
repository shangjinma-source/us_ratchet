from copy import deepcopy
import unittest
from scripts import ndx_current_seven_dated_security_readback_20260919 as m

class Tests(unittest.TestCase):
    def test_real_dated_fact_and_explicit_remaining_gap(self):
        report=m.build();fact,=report['dated_facts']
        self.assertEqual(fact['cusip'],'55024U109');self.assertTrue(fact['cusip_checksum_valid'])
        self.assertEqual(fact['event_date'],'2024-12-31');self.assertEqual(len(report['unresolved']),6)
        self.assertTrue(all(n==0 for n in report['local_nport_exact_ticker_counts'].values()))
        self.assertFalse(fact['current_20260919_cusip_certified']);self.assertFalse(fact['provider_price_identity_bound'])
    def test_issuer_name_is_not_accession_binding(self):
        text='Lumentum Holdings Inc. (Name of Issuer) Common Stock (Title of Class of Securities) 55024U109 (CUSIP Number) 12/31/2024 (Date of Event Which Requires Filing of this Statement) Date: 02/12/2025'
        metadata={'/Title':'0001422849-25-000008','/Subject':'Form SC 13G filed on 2025-02-13'}
        sub=dict(cik=1633978,tickers=['LITE'],exchanges=['Nasdaq'],filings=dict(recent=dict(accessionNumber=['0001422849-25-000008'],form=['SCHEDULE 13G'],filingDate=['2025-02-13'],primaryDocument=['xslSCHEDULE_13G_X01/primary_doc.xml'])))
        m.extract(text,metadata,sub)
        for mode in ('accession','issuer','class','cusip','exchange'):
            bad=deepcopy(sub);words=text
            if mode=='accession':bad['filings']['recent']['accessionNumber']=['0000000000-25-000001']
            if mode=='issuer':bad['cik']=1422849
            if mode=='class':words=text.replace('Common Stock','Preferred Stock')
            if mode=='cusip':words=text.replace('55024U109','55024U108')
            if mode=='exchange':bad['exchanges']=['NYSE']
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.extract(words,metadata,bad)
if __name__=='__main__':unittest.main()
