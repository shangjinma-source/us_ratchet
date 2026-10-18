import hashlib
import unittest
from unittest.mock import Mock
import pandas as pd
from backtest.ndx_dynamic_nav_research_v2 import load_nav_v2


class CanonicalNavTests(unittest.TestCase):
    def test_intraday_and_timezone_calendar_rejected(self):
        for calendar in (pd.to_datetime(['2023-01-01 10:00', '2023-01-01 11:00']),
                         pd.date_range('2023-01-01', periods=2, tz='UTC')):
            with self.subTest(calendar=calendar), self.assertRaisesRegex(ValueError, 'midnight'):
                load_nav_v2(csv_path=None, manifest_path=None, expected_csv_sha256='',
                            expected_manifest_sha256='', calendar=calendar)

    def test_duplicate_header_rejected(self):
        raw = b'Date,Close,Close\n2023-01-01,1,2\n'
        with self.assertRaisesRegex(ValueError, 'Unique'):
            load_nav_v2(csv_path=Mock(read_bytes=lambda: raw), manifest_path=None,
                        expected_csv_sha256=hashlib.sha256(raw).hexdigest(),
                        expected_manifest_sha256='', calendar=pd.date_range('2023-01-01', periods=2))


if __name__ == '__main__':
    unittest.main()
