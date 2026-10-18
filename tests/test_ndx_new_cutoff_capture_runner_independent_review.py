"""No HTTP: independently attack durable capture/resume invariants."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from scripts import ndx_new_cutoff_capture_runner_20260923 as module


class Response:
    status = 200
    headers = {}
    def __init__(self, url): self.url = url
    def __enter__(self): return self
    def __exit__(self, *arguments): pass
    def read(self): return b'{"chart":{"result":[],"error":null}}'


class IndependentCaptureReview(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.old = 'https://query1.finance.yahoo.com/v8/finance/chart/AMAT?period1=1640995200&period2=1&interval=1d&events=div,splits'
        self.row = dict(ticker='AMAT', prior_receipt={'request_url': self.old},
                        request_url_template=self.old.replace('period2=1&', 'period2={actual_request_start_utc_epoch}&'))
        self.plan = dict(output_directory=str(self.output), queue=[self.row])
        self.now = datetime(2026, 9, 23, 4, tzinfo=timezone.utc)
        self.calls = 0

    def opener(self, request, **kwargs):
        self.calls += 1
        return Response(request.full_url)

    def capture(self):
        return module.capture_one(self.row, self.output, 'plan', module.LOADED_SHA, {self.old},
                                  self.opener, lambda: self.now)

    def rewrite(self, path, value):
        raw = json.dumps(value, sort_keys=True).encode()
        Path(path).write_bytes(raw)
        return module.digest(raw)

    def alter_receipt(self, entry, key, value):
        receipt = json.loads(Path(entry['receipt_path']).read_bytes())
        receipt[key] = value
        entry['receipt_sha256'] = self.rewrite(entry['receipt_path'], receipt)
        decoded = json.loads(Path(entry['decoded_path']).read_bytes())
        decoded['receipt_sha256'] = entry['receipt_sha256']
        entry['decoded_sha256'] = self.rewrite(entry['decoded_path'], decoded)

    def test_resigned_false_new_york_cutoff_rejected(self):
        entry = self.capture()
        self.alter_receipt(entry, 'completed_training_excludes_dates_on_or_after', '2026-09-24')
        with self.assertRaises(ValueError):
            module.check_entries([entry], self.plan, 'plan', module.LOADED_SHA)

    def test_resigned_naive_receipt_time_rejected(self):
        entry = self.capture()
        self.alter_receipt(entry, 'received_at_utc', '2026-09-23T04:00:00')
        with self.assertRaises(ValueError):
            module.check_entries([entry], self.plan, 'plan', module.LOADED_SHA)

    def test_decoded_cannot_upgrade_promotion_or_price_reconstruction(self):
        entry = self.capture()
        decoded = json.loads(Path(entry['decoded_path']).read_bytes())
        decoded.update(promotion_allowed=True, prices_reconstructed=True)
        entry['decoded_sha256'] = self.rewrite(entry['decoded_path'], decoded)
        with self.assertRaises(ValueError):
            module.check_entries([entry], self.plan, 'plan', module.LOADED_SHA)

    def test_raw_orphan_prevents_first_network_attempt(self):
        (self.output / 'AMAT.response.bin').write_bytes(b'orphan')
        with self.assertRaises(FileExistsError):
            self.capture()
        self.assertEqual(self.calls, 0)

    def test_second_call_does_not_retry(self):
        self.capture()
        with self.assertRaises(FileExistsError):
            self.capture()
        self.assertEqual(self.calls, 1)

    def test_external_current_sha_cannot_override_loaded_sha(self):
        with patch.object(module.preparation, 'sha', return_value='changed'):
            with self.assertRaises(ValueError):
                module.verify_runner('changed')

    def test_orphan_raw_for_completed_failed_attempt_rejected(self):
        def failed(*arguments, **keywords):
            raise URLError('fixture')
        entry = module.capture_one(self.row, self.output, 'plan', module.LOADED_SHA,
                                   {self.old}, failed, lambda: self.now)
        (self.output / 'AMAT.response.bin').write_bytes(b'unreferenced orphan')
        with self.assertRaises(ValueError):
            module.check_entries([entry], self.plan, 'plan', module.LOADED_SHA)


if __name__ == '__main__':
    unittest.main()
