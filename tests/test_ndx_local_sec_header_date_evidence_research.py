import unittest
from scripts import ndx_local_sec_header_date_evidence_research as evidence


class HeaderDatesTests(unittest.TestCase):
    def test_real_all83_and_preserve_unknown_timezone(self):
        report=evidence.build()
        self.assertEqual(report['document_count'],83)
        self.assertEqual(report['previously_missing_submission_documents_supplemented'],21)
        atvi=next(row for row in report['documents'] if row['tickers']=='ATVI')
        self.assertEqual(atvi['facts']['filing_date'],'2022-02-25')
        self.assertEqual(atvi['facts']['report_period_date'],'2021-12-31')
        self.assertEqual(atvi['facts']['acceptance_datetime_raw'],'20220225162105')
        self.assertIsNone(atvi['facts']['acceptance_instant_utc'])
        self.assertIsNone(atvi['exact_header_http_receipt_time'])
        self.assertFalse(report['new_filing_http_requests_performed'])

    def test_duplicate_acceptance_and_wrong_cik_rejected(self):
        raw=(evidence.BASE/'raw_headers/718877/0001628280-22-003992.header.txt').read_bytes()
        with self.assertRaises(ValueError):
            evidence.parse_header(raw+b'\n<ACCEPTANCE-DATETIME>20220225162105\n',
                accession='0001628280-22-003992',cik=718877,form='10-K')
        with self.assertRaises(ValueError):
            evidence.parse_header(raw,accession='0001628280-22-003992',cik=1,form='10-K')

    def test_joint_filer_is_explicit_not_single_issuer_claim(self):
        raw=(evidence.BASE/'raw_headers/4904/0000004904-22-000024.header.txt').read_bytes()
        result=evidence.parse_header(raw,accession='0000004904-22-000024',cik=4904,form='10-K')
        self.assertTrue(result['multiple_filer_header'])
        self.assertEqual(len(result['all_header_filer_ciks']),8)
        self.assertFalse(result['issuer_exclusive_filing_claim'])


if __name__=='__main__':unittest.main()
