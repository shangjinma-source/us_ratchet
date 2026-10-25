from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from data.strategy_halt_market_capture_v1 import HaltMarketCaptureV1
from data.strategy_halt_gap_diagnostic_v1 import SOURCE_URL


class HaltMarketCaptureTests(unittest.TestCase):
    def test_source_capture_precedes_marks_and_closes_hash_domain(self):
        calls=[]
        class Market:
            def capture(self,**kwargs):
                calls.append('marks')
                return dict(files={},source_hashes={},marks={})
        def fetch():
            calls.append('halts')
            return dict(url=SOURCE_URL,status=200,body=b'<html>raw</html>')
        with TemporaryDirectory() as root:
            wrapper=HaltMarketCaptureV1(Market(),fetch=fetch,
                clock=lambda:datetime(2026,10,22,17,tzinfo=timezone.utc))
            result=wrapper.capture(output_directory=Path(root)/'market')
            self.assertEqual(calls,['halts','marks'])
            self.assertEqual(set(result['files']),set(result['source_hashes']))
            for key,value in result['files'].items():
                self.assertEqual(sha256(value).hexdigest(),result['source_hashes'][key])
            self.assertTrue((Path(root)/'market-halts'/'receipt.json').exists())

    def test_halt_failure_preserves_marks_but_no_buy_evidence(self):
        class Market:
            def capture(self,**kwargs): return dict(files={},source_hashes={},marks={'held':'unchanged'})
        def fetch(): raise TimeoutError('not persisted')
        with TemporaryDirectory() as root:
            result=HaltMarketCaptureV1(Market(),fetch=fetch).capture(output_directory=Path(root)/'market')
            self.assertEqual(result['marks'],{'held':'unchanged'})
            self.assertNotIn('halt_evidence',result)
            self.assertEqual(result['halt_capture_failure'],'HALT_CAPTURE_UNAVAILABLE')
            self.assertNotIn('not persisted',(Path(root)/'market-halts'/'receipt.json').read_text())
