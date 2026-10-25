from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_verified_rss_capture_v1 import capture_session, attach_timing
import test_strategy_daily_session_capture as fixtures


class VerifiedCaptureTests(unittest.TestCase):
    def case(self, mode):
        fixture = fixtures.DailySessionCaptureTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        point = [datetime.fromisoformat('2026-10-20T11:59:59.513417+00:00')]
        channel = 'Tue, 20 Oct 2026 12:00:00 GMT'
        item = 'Tue, 20 Oct 2026 11:00:00 GMT'
        if mode == 'far': channel = 'Tue, 20 Oct 2026 12:00:02 GMT'
        if mode == 'naive': channel = 'Tue, 20 Oct 2026 12:00:00'
        if mode == 'future_item': item = 'Tue, 20 Oct 2026 12:00:00 GMT'
        raw = ('<rss><channel><pubDate>'+channel+'</pubDate><item><title>Unrelated</title><pubDate>'+
               item+'</pubDate></item></channel></rss>').encode()
        config = canonical(fixture.configuration)
        def sleep(seconds):
            if mode == 'frozen': return
            point[0] += timedelta(seconds=seconds)
        result = capture_session(root=fixture.root, configuration_bytes=config,
            configuration_sha256=sha256(config).hexdigest(),execute=True,
            fetch_daily=lambda *args: dict(status=200,body=fixture.daily),
            fetch_official=lambda: dict(status=200,body=raw),clock=lambda:point[0],sleep=sleep)
        return result, fixture, raw

    def test_actual_wait_preserves_network_time_and_closure(self):
        result, fixture, raw = self.case('ok')
        self.assertEqual(result['status'],'CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED',result)
        output = Path(result['output'])
        binding = json.loads((output/'official.timing.json').read_bytes())
        self.assertEqual(binding['transport']['transport_received_at'],'2026-10-20T11:59:59.513417+00:00')
        self.assertGreater(datetime.fromisoformat(binding['capture_received_at']),
                           datetime.fromisoformat(binding['transport']['transport_received_at']))
        self.assertEqual((output/'official.response.bin').read_bytes(),raw)
        files = {name:(output/name).read_bytes() for name in ('official.timing.json','official.receipt.json','official.response.bin')}
        reviewed = dict(files={},receipt=dict(source_sha256={}))
        admitted = attach_timing(reviewed=reviewed,capture_files=files)
        self.assertEqual(len(admitted['files']),1)
        files['official.response.bin'] = raw+b' '
        with self.assertRaises(ValueError): attach_timing(reviewed=reviewed,capture_files=files)

    def test_future_items_far_channel_naive_clock_and_wait_failure_reject(self):
        for mode in ('far','naive','future_item','frozen'):
            with self.subTest(mode=mode):
                result, fixture, raw = self.case(mode)
                self.assertNotEqual(result['status'],'CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED')
                self.assertFalse((Path(result['output'])/'official.timing.json').exists())
                self.assertEqual((Path(result['output'])/'official.transport.response.bin').read_bytes(),raw)
