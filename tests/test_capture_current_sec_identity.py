import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from scripts.capture_current_sec_identity import subject_fields, check_subject, company_name, Capture


def raw(issuer='Example Inc', cusip='123456789'):
    values=[issuer,'(Name of Issuer)','Class A Common Stock','(Title of Class of Securities)',
            cusip,'(CUSIP Number)','06/30/2026','(Date of Event Which Requires Filing of this Statement)']
    return ''.join('<div>'+v+'</div>' for v in values).encode()


class SubjectIdentityTests(unittest.TestCase):
    def test_subject_not_reporter_and_exact_identifier(self):
        member=dict(ticker='EX',issuer_id='issuer:0000000001',security_id='security:0000000001:123456789')
        submissions=dict(cik='0000000001',tickers=['EX'],name='Example Incorporated')
        self.assertEqual(check_subject(member,submissions,subject_fields(raw()),'2026-08-01','2026-10-16'),
                         'MATCHED_EXACT_CURRENT_IDENTIFIER')
        self.assertEqual(check_subject(member,submissions,subject_fields(raw('Other Inc')),'2026-08-01','2026-10-16'),
                         'SUBJECT_NAME_MISMATCH_NOT_ACCEPTED')
        with self.assertRaisesRegex(ValueError,'CUSIP_CONFLICT'):
            check_subject(member,submissions,subject_fields(raw(cusip='987654321')),'2026-08-01','2026-10-16')
        with self.assertRaisesRegex(ValueError,'NOT_CURRENT_YEAR'):
            check_subject(member,submissions,subject_fields(raw()),'2026-11-01','2026-10-16')

    def test_ambiguous_cover_and_nonadjacent_fields_rejected(self):
        with self.assertRaisesRegex(ValueError,'NOT_UNIQUE'):
            subject_fields(raw()+b'<div>(Name of Issuer)</div>')
        body=raw().replace(b'<div>(CUSIP Number)</div>',b'<div>(CUSIP Number)</div>'+b'<div>unrelated</div>'*20)
        with self.assertRaisesRegex(ValueError,'ONE_COVER_SEGMENT'):
            subject_fields(body)

    def test_name_normalization_preserves_classes_and_jurisdiction(self):
        self.assertEqual(company_name('Example Holdings, Incorporated'),company_name('EXAMPLE HLDGS INC'))
        self.assertNotEqual(company_name('Example Class A Inc'),company_name('Example Class B Inc'))
        self.assertNotEqual(company_name('Example NV'),company_name('Example Inc'))

    def test_persisted_access_limit_blocks_restart_before_http(self):
        with TemporaryDirectory() as folder:
            path=Path(folder);(path/'denied.json').write_text(json.dumps({'status':429}))
            with patch('urllib.request.urlopen') as fetch:
                with self.assertRaisesRegex(ValueError,'ACCESS_LIMIT_STOP'):
                    Capture(path,'test')
                fetch.assert_not_called()

    def test_redirected_nonofficial_response_retained_but_rejected(self):
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,limit):return b'{}'
            def geturl(self):return 'https://not-sec.example/foreign'
        with TemporaryDirectory() as folder:
            path=Path(folder);capture=Capture(path,'test')
            with patch('urllib.request.urlopen',return_value=Response()) as fetch:
                with self.assertRaisesRegex(ValueError,'FINAL_OFFICIAL'):
                    capture.get('https://data.sec.gov/submissions/CIK0000000001.json')
                self.assertEqual(fetch.call_count,1)
            receipt=json.loads(next(path.glob('*.json')).read_bytes())
            self.assertEqual(receipt['final_url'],'https://not-sec.example/foreign')
            self.assertEqual(len(list(path.glob('*.bin'))),1)


if __name__=='__main__':unittest.main()
