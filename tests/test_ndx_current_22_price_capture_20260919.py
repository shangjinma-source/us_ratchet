import gzip
import json
from pathlib import Path
import tempfile
import unittest
from scripts import ndx_current_22_price_capture_20260919 as module


class Response:
    status = 200
    url = 'https://query1.finance.yahoo.com/mock'
    headers = {'Content-Encoding': 'gzip'}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return gzip.compress(b'{"chart":{"result":[],"error":null}}')


class CaptureTests(unittest.TestCase):
    def test_real_hard_difference_without_network(self):
        plan = module.build_plan()
        self.assertEqual(len(plan['tickers']), 22)
        self.assertEqual(plan['tickers'][:8], ['ALAB', 'ALNY', 'APP', 'ARM', 'AXON', 'CRWV', 'FER', 'HONA'])
        self.assertNotIn('KHC', plan['tickers'])
        self.assertEqual(plan['period1_utc_epoch'], 1640995200)

    def test_batches_resume_unique_requests_and_raw_bindings(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            plan = dict(tickers=['T'+str(i) for i in range(10)], output_directory=str(output))
            seen = []
            def opener(request, **kwargs):
                seen.append(request.full_url)
                return Response()
            first = module.run_batch(plan, 'p', output, opener=opener)
            self.assertEqual(len(seen), 8)
            second = module.run_batch(plan, 'p', output, first['path'], first['sha256'], opener)
            self.assertEqual(len(seen), 10)
            self.assertEqual(len(set(seen)), 10)
            with self.assertRaisesRegex(ValueError, 'complete'):
                module.run_batch(plan, 'p', output, second['path'], second['sha256'], opener)
            (output/'T0.response.bin').write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'Raw changed'):
                module.run_batch(plan, 'p', output, second['path'], second['sha256'], opener)

    def test_unindexed_attempt_cannot_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            module.save(output/'A.started.json', {'attempt': 1})
            with self.assertRaisesRegex(ValueError, 'Unindexed'):
                module.run_batch(dict(tickers=['A'], output_directory=str(output)), 'p', output,
                                 opener=lambda *a, **k: self.fail('HTTP must not run'))

    def test_network_failure_receipt_is_durable_and_counts_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            def fail(*args, **kwargs):
                raise TimeoutError()
            result = module.run_batch(dict(tickers=['A'], output_directory=str(output)), 'p', output, opener=fail)
            receipt = json.loads((output/'A.receipt.json').read_bytes())
            self.assertEqual(receipt['error_type'], 'TimeoutError')
            self.assertIn('received_at_utc', receipt)
            self.assertFalse(receipt['historical_identity_verified'])
            self.assertEqual(result['attempted_count'], 1)

    def test_parse_failure_does_not_lose_body_or_receipt(self):
        class Bad(Response):
            def read(self):
                return b'\x1f\x8bbroken'
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            entry = module.capture_one('A', output, 'p', lambda *a, **k: Bad())
            parsed = json.loads(Path(entry['decoded_path']).read_bytes())
            self.assertEqual(parsed['parse_status'], 'DECODE_OR_PARSE_FAILED')
            self.assertTrue((output/'A.receipt.json').is_file())
            self.assertEqual((output/'A.response.bin').read_bytes(), b'\x1f\x8bbroken')


if __name__ == '__main__':
    unittest.main()
