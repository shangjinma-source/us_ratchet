import gzip
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_current92_sec_identity_readback_20260919 as module


class Tests(unittest.TestCase):
    def test_all_101_against_original_raw_rows_without_identity_parser(self):
        report = module.build()
        observed = {}
        for row in report['rows']:
            witness = row['matched_candidate']
            raw = Path(witness['raw_path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), witness['raw_sha256'])
            body = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
            position = row['reported_ticker_exchange_position']
            self.assertEqual(body['tickers'][position], row['ticker'])
            self.assertEqual(body['exchanges'][position], 'Nasdaq')
            self.assertEqual(body['cik'], row['current_reported_cik'])
            observed[row['ticker']] = body['cik']
        self.assertEqual(len(observed), 101)
        self.assertEqual(len(set(observed.values())), 100)
        self.assertEqual(observed['GOOG'], observed['GOOGL'])
        self.assertFalse(report['historical_cusip_verified'])
        self.assertFalse(report['provider_price_identity_bound'])
        self.assertFalse(report['point_in_time_verified'])

    def test_request_time_status_and_capture_denominator_tampering_rejected(self):
        original = module.nine.read
        for defect in ('request', 'utc', 'status', 'extra', 'missing'):
            def read(path, sha, sources):
                doc = original(path, sha, sources)
                if str(path) == str(module.MANIFEST):
                    item = doc['captures'][0]
                    if defect == 'request':
                        item['request_url'] = 'https://data.sec.gov/submissions/CIK0000000001.json'
                    elif defect == 'utc':
                        item['received_at_utc'] = '2026-09-19T00:00:00'
                    elif defect == 'status':
                        item['http_status'] = True
                    elif defect == 'extra':
                        doc['captures'].append(dict(item))
                    else:
                        doc['captures'].pop()
                return doc
            with self.subTest(defect=defect), patch.object(module.nine, 'read', side_effect=read):
                with self.assertRaises(ValueError):
                    module.build()


if __name__ == '__main__':
    unittest.main()
