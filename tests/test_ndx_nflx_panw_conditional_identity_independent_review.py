import unittest
from scripts import ndx_nflx_panw_conditional_identity_20260919 as m
from test_ndx_nflx_panw_conditional_identity_20260919 import fixture


class IdentityReview(unittest.TestCase):
    def test_action_date_must_be_present_and_unchanged(self):
        for ticker,short,long in (('NFLX','11/17/2025','November 17, 2025'),('PANW','12/16/2024','December 16, 2024')):
            memo,cover=fixture(ticker)
            if 'Ex-Date:' not in memo:memo+=' Ex-Date: '+short
            if 'The Ex-distribution Date is' not in memo:memo+=' The Ex-distribution Date is '+long+'.'
            m.relation(ticker,memo,cover)
            for bad in (memo.replace(short,'01/01/2026'),memo.replace(long,'January 1, 2026')):
                with self.subTest(ticker=ticker),self.assertRaises(ValueError):m.relation(ticker,bad,cover)

    def test_cusip_ticker_class_and_duplicate_cover_cannot_cross_documents(self):
        for ticker in m.CASES:
            memo,cover=fixture(ticker)
            for bad_memo,bad_cover in ((memo.replace(m.CASES[ticker]['cusip'],'000000000'),cover),
                    (memo,cover.replace(ticker.encode(),b'OTHER')),
                    (memo,cover.replace(b'Common stock',b'Class B Common stock')),
                    (memo,cover+cover)):
                with self.subTest(ticker=ticker),self.assertRaises(ValueError):m.relation(ticker,bad_memo,bad_cover)

    def test_actual_panw_wrapper_is_one_pdf_only(self):
        raw=(m.BASE/m.CASES['PANW']['memo']).read_bytes()
        self.assertTrue(m.pdf_payload(raw,'PANW').startswith(b'%PDF'))
        for bad in (raw+raw,raw+b'EXTRA',raw.replace(b'PANW_Split_55607.pdf',b'OTHER.pdf')):
            with self.assertRaises(ValueError):m.pdf_payload(bad,'PANW')


if __name__=='__main__':unittest.main()
