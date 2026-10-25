from hashlib import sha256
import unittest
from data.strategy_execution_halt_evidence_v1 import verified_halt_intervals
from data.strategy_halt_gap_diagnostic_v1 import HEADER, SOURCE_URL


def header(): return '<tr>'+''.join('<th>'+x+'</th>' for x in HEADER)+'</tr>'


def row(resume='12:39:54', date='10/22/2026'):
    return '<tr>'+''.join('<td>'+x+'</td>' for x in [
        'MRNA','MODERNA','NASDAQ','10/22/2026 12:34:54','Volatility Pause',date,'',resume])+'</tr>'


def check(body, **changes):
    raw=('All times are Eastern Time<h3>Non-Cboe Listed Halts</h3>'+body).encode()
    receipt=dict(url=SOURCE_URL,http_status=200,raw_sha256=sha256(raw).hexdigest(),bytes=len(raw),
                 started_at='2026-10-22T17:00:00Z',received_at='2026-10-22T17:00:01Z')
    args=dict(raw=raw,receipt=receipt,security_id='MRNA-ID',ticker='MRNA',session='2026-10-22',
        session_open='2026-10-22T09:30:00-04:00',session_close='2026-10-22T16:00:00-04:00',now='2026-10-22T17:00:02Z')
    args.update(changes)
    return verified_halt_intervals(**args)


class ExecutionHaltEvidenceTests(unittest.TestCase):
    def test_exact_table_returns_bound_interval(self):
        result=check('<table>'+header()+row()+'</table>')
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['security_id'],'MRNA-ID')
        self.assertEqual(result[0]['resumed_at'],'2026-10-22T12:39:54-04:00')

    def test_other_table_row_cannot_authorize_gap(self):
        self.assertEqual(check('<table>'+header()+'</table><table>'+row()+'</table>'),[])

    def test_duplicate_and_active_halts_rejected(self):
        for records in (row()+row(),row(''),row()+row('')):
            with self.assertRaises(ValueError):check('<table>'+header()+records+'</table>')

    def test_cross_session_or_future_resumption_rejected(self):
        for records in (row(date='10/23/2026'),row('15:00:00')):
            with self.assertRaisesRegex(ValueError,'HALT_RESUME_DOMAIN'):
                check('<table>'+header()+records+'</table>')

    def test_ambiguous_or_unclosed_table_rejected(self):
        for body in ('<table>'+header()+'</table><table>'+header()+row()+'</table>',
                     '<table>'+header()+row()):
            with self.assertRaises(ValueError):check(body)

    def test_stale_evidence_cannot_reauthorize(self):
        with self.assertRaisesRegex(ValueError,'HALT_SOURCE_CLOCK_OR_STALE'):
            check('<table>'+header()+row()+'</table>',now='2026-10-22T17:06:00Z')

    def test_changed_raw_rejected(self):
        with self.assertRaisesRegex(ValueError,'HALT_SOURCE_BINDING'):
            check('<table>'+header()+row()+'</table>',raw=b'different')
