import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.strategy_halt_gap_diagnostic_v1 import HEADER, SOURCE_URL
from data.strategy_halt_observation_v1 import capture_halt_observation


class HaltObservationTests(unittest.TestCase):
    def capture(self, root, raw, url=SOURCE_URL):
        return capture_halt_observation(evidence_root=root,
            requests=[dict(ticker='MRNA', session='2026-10-22', missing_minutes=[])],
            fetch=lambda: dict(url=url, status=200, body=raw),
            clock=lambda: datetime(2026, 10, 22, 17, tzinfo=timezone.utc))

    def test_empty_valid_table_is_observation_not_permission(self):
        raw=('All times are Eastern Time<table><tr>'+''.join('<th>'+x+'</th>' for x in HEADER)+'</tr></table>').encode()
        with TemporaryDirectory() as root:
            result=self.capture(root,raw)
            directory=Path(result['evidence_directory'])
            self.assertEqual((directory/'source.raw').read_bytes(),raw)
            receipt=json.loads((directory/'receipt.json').read_text())
            self.assertEqual(receipt['status'],'OBSERVED_NOT_TRADE_AUTHORIZATION')
            self.assertFalse(result['observations'][0]['trade_eligibility_granted'])
            self.assertFalse(result['observations'][0]['all_gaps_explained'])

    def test_protection_html_preserved_with_failure_receipt(self):
        with TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                self.capture(root,b'<html>Service unavailable</html>')
            directory=next(Path(root).iterdir())
            self.assertEqual((directory/'source.raw').read_bytes(),b'<html>Service unavailable</html>')
            receipt=json.loads((directory/'receipt.json').read_text())
            self.assertEqual(receipt['status'],'FAILED')
            self.assertFalse((directory/'observations.json').exists())

    def test_redirect_not_admitted_or_saved_as_source(self):
        with TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,'HALT_SOURCE_BINDING'):
                self.capture(root,b'anything','https://example.com/login')
            receipt=next(Path(root).glob('*/receipt.json')).read_text()
            self.assertNotIn('example.com',receipt)

    def test_network_failure_has_receipt_without_replay(self):
        def fail(): raise TimeoutError('secret upstream string')
        with TemporaryDirectory() as root:
            with self.assertRaises(TimeoutError):
                capture_halt_observation(evidence_root=root,requests=[{}],fetch=fail)
            receipt=next(Path(root).glob('*/receipt.json')).read_text()
            self.assertIn('HALT_OBSERVATION_FAILED',receipt)
            self.assertNotIn('secret',receipt)
