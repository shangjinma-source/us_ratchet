import copy
import gzip
import json
import unittest
from unittest.mock import patch
from scripts import ndx_legacy_five_dated_facts_20260923 as subject


class FiveDatedFactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blobs = {}
        for key, (path, digest) in subject.BOUND.items():
            raw = (subject.ROOT / path).read_bytes()
            if subject.sha(raw) != digest:
                raise AssertionError(key + ' source mismatch')
            cls.blobs[key] = raw

    def test_five_dated_facts_without_identity_upgrade(self):
        value = subject.assemble(self.blobs)
        self.assertEqual({r['ticker'] for r in value['rows']}, {'ADI','QCOM','TXN','DDOG','TEAM'})
        self.assertEqual(len(value['rows']), 5)
        for row in value['rows']:
            self.assertLess(row['filing_date'], '2023-03-31')
            for flag in subject.FLAGS:
                self.assertIs(row[flag], False)
                self.assertIs(value[flag], False)
            self.assertIsNone(row['continuous_identity_interval'])

    def test_13f_subject_reporter_and_period_not_event(self):
        rows = {r['ticker']:r for r in subject.assemble(self.blobs)['rows']}
        for ticker in ('DDOG','TEAM'):
            row = rows[ticker]
            self.assertEqual(row['reporter_cik'], '0001357550')
            self.assertNotEqual(row['subject_cik'], row['reporter_cik'])
            self.assertIsNone(row['event_date'])
            self.assertFalse(row['subject_cik_directly_in_cusip_document'])
            self.assertFalse(row['old_issuer_or_class_conversion_verified'])
            self.assertEqual(row['tool_call_started_utc'], 'unknown')
            self.assertEqual(row['accepted_timezone'], 'unknown')
        self.assertEqual(rows['TEAM']['cusip'],'049468101')

    def test_same_accession_submissions_date_document_subject(self):
        raw = self.blobs['QCOM_submissions']
        original = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
        accession = '0001104659-23-016796'
        for mutation in ('cik','filingDate','primaryDocument','form','duplicate'):
            value = copy.deepcopy(original)
            index = value['filings']['recent']['accessionNumber'].index(accession)
            if mutation == 'cik':
                value['cik'] = 1357550
            elif mutation == 'duplicate':
                value['filings']['recent']['accessionNumber'].append(accession)
            else:
                value['filings']['recent'][mutation][index] = 'INVALID'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                subject.submission_link(value,'QCOM',accession,'2023-02-09','tv01740-qualcomminc.htm')

    def test_adi_reuses_saved_observation_time_txn_stays_2022(self):
        rows = {r['ticker']:r for r in subject.assemble(self.blobs)['rows']}
        self.assertEqual(rows['ADI']['tool_call_started_utc'],'2026-09-19 12:50:10 UTC')
        self.assertEqual(rows['TXN']['filing_date'],'2022-02-10')
        self.assertEqual(rows['TXN']['event_date'],'2021-12-31')
        self.assertEqual(rows['TXN']['tool_call_completed_utc'],'unknown')

    def test_wrong_adi_cusip_rejected(self):
        blobs = dict(self.blobs)
        value = json.loads(blobs['adi_readback'])
        next(r for r in value['rows'] if r['ticker']=='ADI')['cusip'] = '049468101'
        blobs['adi_readback'] = json.dumps(value).encode()
        with self.assertRaises(ValueError):
            subject.assemble(blobs)

    def test_source_drift_prevents_publication(self):
        with patch.object(subject, 'LOADED_SHA', '0'*64), patch.object(subject.Path,'mkdir') as mkdir:
            with self.assertRaisesRegex(ValueError, 'Loaded source drift'):
                subject.publish({'source_hashes':{}})
            mkdir.assert_not_called()


if __name__ == '__main__':
    unittest.main()
