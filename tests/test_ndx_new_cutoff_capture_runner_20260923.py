from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from scripts import ndx_new_cutoff_capture_runner_20260923 as m


class Response:
    status = 200
    headers = {}
    def __init__(self, url, body=b'{"chart":{"error":null,"result":[]}}'):
        self.url, self.body = url, body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return self.body


class CaptureRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.old = 'https://query1.finance.yahoo.com/v8/finance/chart/AMAT?period1=1640995200&period2=1&interval=1d&events=div,splits'
        self.row = dict(ticker='AMAT', request_url_template=self.old.replace('period2=1&', 'period2={actual_request_start_utc_epoch}&'))
        self.now = datetime(2026, 9, 23, 4, tzinfo=timezone.utc)

    def capture(self, opener, clock=None):
        return m.capture_one(self.row, self.output, 'plan', m.LOADED_SHA, {self.old}, opener, clock or (lambda: self.now))

    def test_raw_first_started_before_network_and_readback(self):
        def opener(request, **kwargs):
            self.assertTrue((self.output/'AMAT.started.json').exists())
            self.assertFalse((self.output/'AMAT.receipt.json').exists())
            return Response(request.full_url)
        entry = self.capture(opener)
        plan = dict(output_directory=str(self.output), queue=[self.row])
        m.check_entries([entry], plan, 'plan', m.LOADED_SHA)
        self.assertEqual(json.loads((self.output/'AMAT.decoded.json').read_text())['parse_status'], 'JSON_CHANNEL_OBSERVATION_NOT_IDENTITY')
        with self.assertRaises(FileExistsError): self.capture(opener)
        (self.output/'AMAT.response.bin').write_bytes(b'tampered')
        with self.assertRaises(ValueError): m.check_entries([entry], plan, 'plan', m.LOADED_SHA)

    def test_pre_midnight_blocks_without_attempt(self):
        with self.assertRaises(ValueError):
            self.capture(lambda *a, **k: self.fail('network'), lambda: datetime(2026,9,23,3,59,59,tzinfo=timezone.utc))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_failed_request_is_durable_and_never_retried(self):
        def opener(*args, **kwargs): raise URLError('offline fixture')
        entry = self.capture(opener)
        receipt = m.bound_json(entry['receipt_path'], entry['receipt_sha256'])
        self.assertEqual(receipt['error_type'], 'URLError')
        self.assertNotIn('raw_path', receipt)
        with self.assertRaises(FileExistsError): self.capture(opener)

    def test_redirect_body_preserved_but_not_decoded_as_accepted(self):
        entry = self.capture(lambda *a, **k: Response('https://example.invalid/'))
        decoded = m.bound_json(entry['decoded_path'], entry['decoded_sha256'])
        self.assertEqual(decoded['parse_status'], 'BLOCKED_RECEIPT_OR_DECODE')
        self.assertTrue((self.output/'AMAT.response.bin').exists())
        self.assertIsNone(m.NoRedirect().redirect_request(None,None,302,'',{},'https://example.invalid'))

    def test_receipt_day_crossing_remains_raw_evidence_only(self):
        times = iter([self.now, datetime(2026,9,24,4,tzinfo=timezone.utc)])
        entry = self.capture(lambda request, **k: Response(request.full_url), lambda: next(times))
        receipt = m.bound_json(entry['receipt_path'], entry['receipt_sha256'])
        self.assertEqual(receipt['completed_training_excludes_dates_on_or_after'], '2026-09-24')
        self.assertEqual(m.bound_json(entry['decoded_path'], entry['decoded_sha256'])['parse_status'], 'BLOCKED_RECEIPT_OR_DECODE')

    def test_url_inventory_and_orphans_fail_closed(self):
        url = self.old.replace('period2=1&', 'period2=2&')
        self.assertEqual(m.validate_request(url, 'AMAT', {self.old}), 2)
        for bad, old in [(url, set()), (self.old, {self.old}), (url+'#fragment', {self.old})]:
            with self.assertRaises(ValueError): m.validate_request(bad,'AMAT',old)
        (self.output/'AMAT.started.json').write_text('{}')
        with self.assertRaises(ValueError):
            m.check_entries([], dict(output_directory=str(self.output),queue=[self.row]),'plan',m.LOADED_SHA)

    def test_batch_resume_external_index_and_source_change_after_http(self):
        rows = [dict(self.row, prior_url_inventory_complete=True, prior_receipt={'request_url':self.old})]
        second_old = self.old.replace('AMAT', 'ADI')
        rows.append(dict(rows[0], ticker='ADI', request_url_template=rows[0]['request_url_template'].replace('AMAT','ADI'),
                         prior_receipt={'request_url':second_old}))
        plan = dict(output_directory=str(self.output), queue=rows, maximum_requests_per_batch=1, source_hashes={})
        path = self.output/'plan.json'
        plan_sha = m.save(path, plan)
        capture = m.capture_one
        calls = []
        def wrapped(row, output, plan_sha, runner_sha, prior_urls):
            calls.append(row['ticker'])
            return capture(row, output, plan_sha, runner_sha, prior_urls,
                           lambda request, **kwargs: Response(request.full_url), lambda: self.now)
        with patch.object(m.preparation,'build',return_value=plan), patch.object(m,'utc_now',return_value=self.now), patch.object(m,'capture_one',side_effect=wrapped):
            first = m.run(path, plan_sha, m.LOADED_SHA, execute=True)
            second = m.run(path, plan_sha, m.LOADED_SHA, execute=True,
                           index_path=first['last_index']['path'], index_sha=first['last_index']['sha256'])
            self.assertEqual(calls,['AMAT','ADI'])
            self.assertEqual(second['completed_attempts'],2)
            self.assertTrue((self.output/'completion_index_001.json').exists())
            self.assertTrue((self.output/'completion_index_002.json').exists())

    def test_source_change_during_http_keeps_evidence_without_index(self):
        source = self.output/'source.txt'
        source.write_text('before')
        row = dict(self.row, prior_url_inventory_complete=True, prior_receipt={'request_url':self.old})
        plan = dict(output_directory=str(self.output),queue=[row],maximum_requests_per_batch=1,
                    source_hashes={str(source):m.digest(source.read_bytes())})
        path = self.output/'plan.json'
        plan_sha = m.save(path,plan)
        capture = m.capture_one
        def opener(request, **kwargs):
            source.write_text('after')
            return Response(request.full_url)
        def wrapped(row, output, plan_sha, runner_sha, prior_urls):
            return capture(row, output, plan_sha, runner_sha, prior_urls,opener,lambda:self.now)
        with patch.object(m.preparation,'build',return_value=plan),patch.object(m,'utc_now',return_value=self.now),patch.object(m,'capture_one',side_effect=wrapped):
            with self.assertRaises(ValueError): m.run(path,plan_sha,m.LOADED_SHA,execute=True)
        self.assertTrue((self.output/'AMAT.response.bin').exists())
        self.assertTrue((self.output/'AMAT.receipt.json').exists())
        self.assertFalse(list(self.output.glob('completion_index*')))


if __name__ == '__main__': unittest.main()
