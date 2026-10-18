import unittest
from backtest.annual_coordinate_coverage import audit_coordinate_coverage


class CoordinateCoverageTests(unittest.TestCase):
    def test_missing_whole_session_and_blocked_domain_retained(self):
        rows = [dict(current_security_id='A', ticker='A', status='CONDITIONAL',
                     nominal_ohlc={'2024-01-02': {'ohlc':dict(open='1', high='1', low='1', close='1')}}),
                dict(current_security_id='B', ticker='B', status='BLOCKED', nominal_ohlc=None)]
        result = audit_coordinate_coverage(rows=rows, calendars=[dict(
            year=2024, sessions=['2024-01-02', '2024-01-03'])])
        self.assertEqual(result['domain_count'], 2)
        self.assertEqual(result['years'][0]['securities'][0]['missing_sessions'], ['2024-01-03'])
        self.assertEqual(result['years'][0]['securities'][1]['status'], 'COORDINATES_BLOCKED')
        self.assertFalse(result['domain_filtered'])

    def test_calendar_and_identity_mismatch_rejected(self):
        row = dict(current_security_id='A', ticker='A', status='BLOCKED', nominal_ohlc=None)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_TICKER'):
            audit_coordinate_coverage(rows=[row,row], calendars=[])
        with self.assertRaisesRegex(ValueError, 'YEAR_MISMATCH'):
            audit_coordinate_coverage(rows=[row], calendars=[dict(year=2024,sessions=['2025-01-02'])])

    def test_unresolved_identities_remain_separate_unadmitted_rows(self):
        rows = [dict(current_security_id=None,ticker=t,status='CONDITIONAL',nominal_ohlc={})
                for t in ['X','Y']]
        result = audit_coordinate_coverage(rows=rows,calendars=[dict(year=2024,sessions=['2024-01-02'])])
        self.assertEqual(result['domain_count'],2)
        self.assertEqual([r['status'] for r in result['years'][0]['securities']],
                         ['IDENTITY_UNRESOLVED','IDENTITY_UNRESOLVED'])

    def test_present_but_missing_or_invalid_ohlc_is_not_covered(self):
        for value in (None, {}, {'ohlc':dict(open='1',high='1',low='2',close='1')},
                      {'ohlc':dict(open=True,high='1',low='1',close='1')}):
            row = dict(current_security_id='A',ticker='A',status='CONDITIONAL',
                       nominal_ohlc={'2024-01-02':value})
            result = audit_coordinate_coverage(rows=[row], calendars=[dict(year=2024,sessions=['2024-01-02'])])
            security = result['years'][0]['securities'][0]
            self.assertEqual(security['status'],'MISSING_SESSIONS')
            self.assertEqual(security['invalid_present_sessions'],['2024-01-02'])


if __name__ == '__main__':
    unittest.main()
