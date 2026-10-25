import unittest
from datetime import datetime, timezone
from hashlib import sha256
from data.strategy_halt_gap_diagnostic_v1 import diagnose_halt_gaps, SOURCE_URL


class HaltGapTests(unittest.TestCase):
    def run_case(self, minutes, ticker='MRNA', resume='12:39:54'):
        raw=('<html>All times are Eastern Time<table><tr>'
             '<th>Symbol</th><th>Company</th><th>Market</th><th>Halt</th><th>Reason</th>'
             '<th>Resume Date</th><th>Quote Time</th><th>Resume Time</th></tr>'
             '<tr><td>MRNA</td><td>MODERNA INC COM</td><td>NASDAQ</td>'
             '<td>10/22/2026 12:34:54</td><td>Volatility Pause</td>'
             '<td>10/22/2026</td><td></td><td>'+resume+'</td></tr></table></html>').encode()
        receipt=dict(url=SOURCE_URL,http_status=200,raw_sha256=sha256(raw).hexdigest(),bytes=len(raw),
                     started_at='2026-10-22T17:00:00Z',received_at='2026-10-22T17:00:01Z')
        return diagnose_halt_gaps(raw=raw,receipt=receipt,ticker=ticker,session='2026-10-22',
            missing_minutes=['2026-10-22T12:'+m+':00-04:00' for m in minutes],
            now=datetime(2026,10,22,17,0,2,tzinfo=timezone.utc))

    def test_exact_complete_halt_minutes_only(self):
        result=self.run_case(['35','36','37','38'])
        self.assertTrue(result['all_gaps_explained'])
        self.assertFalse(result['trade_eligibility_granted'])
        self.assertFalse(result['synthetic_bars_created'])

    def test_boundary_partial_minutes_are_not_invented(self):
        result=self.run_case(['34','35','39'])
        self.assertEqual(len(result['halt_explained_minutes']),1)
        self.assertEqual(len(result['unexplained_minutes']),2)

    def test_other_ticker_is_not_covered(self):
        self.assertFalse(self.run_case(['35'],'SNDK')['all_gaps_explained'])

    def test_future_resumption_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'HALT_RESUME_FUTURE'):
            self.run_case(['35'],resume='15:00:00')

    def test_active_halt_is_not_resumed_or_tradable(self):
        result=self.run_case(['35'],resume='')
        self.assertIsNone(result['events'][0]['resumed_at'])
        self.assertFalse(result['trade_eligibility_granted'])
