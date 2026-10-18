from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from data.cached_ohlc import read_cached_ohlc

ROWS = "Date,Open,High,Low,Close,Volume\n2026-09-28,10,13,9,12,100\n2026-09-30,12,15,11,14,200\n2026-10-02,14,16,13,15,300\n2026-10-05,15,17,14,16,400\n"


class CachedOhlcTests(unittest.TestCase):
    def test_actual_week_month_and_stale_no_writes(self):
        with TemporaryDirectory() as directory, patch('data.cached_ohlc.CACHE_DIRECTORY', Path(directory)):
            path = Path(directory) / 'AAA.csv'; path.write_text(ROWS)
            before = path.read_bytes()
            weekly = read_cached_ohlc('AAA', allowed_tickers={'AAA'}, interval='week', expected_session_date='2026-10-06')
            self.assertEqual([(b['open'],b['high'],b['low'],b['close'],b['volume']) for b in weekly['bars']], [(10,16,9,15,600),(15,17,14,16,400)])
            self.assertTrue(weekly['stale'])
            monthly = read_cached_ohlc('AAA', allowed_tickers={'AAA'}, interval='month', bars=1)
            self.assertEqual(monthly['bars'][0]['open'], 14)
            self.assertEqual(monthly['bars'][0]['close'], 16)
            limited = read_cached_ohlc('AAA', allowed_tickers={'AAA'}, expected_session_date='2026-09-30')
            self.assertEqual(limited['daily_as_of'], '2026-09-30')
            self.assertEqual(path.read_bytes(), before)

    def test_missing_invalid_dates_nan_and_structure(self):
        with TemporaryDirectory() as directory, patch('data.cached_ohlc.CACHE_DIRECTORY', Path(directory)):
            self.assertEqual(read_cached_ohlc('AAA', allowed_tickers={'AAA'})['status'], 'MISSING')
            for contents in (ROWS.replace('2026-09-30','2026-09-28'), ROWS.replace(',10,13,9,12,', ',nan,13,9,12,'), ROWS.replace(',10,13,9,12,', ',10,8,9,12,'), 'Date,Close\n2026-09-28,12\n'):
                (Path(directory)/'AAA.csv').write_text(contents)
                self.assertEqual(read_cached_ohlc('AAA', allowed_tickers={'AAA'})['status'], 'INVALID')

    def test_allowlist_path_and_range_pre_io(self):
        with patch('pathlib.Path.open', side_effect=AssertionError('unexpected IO')):
            for ticker, allowed, options in (('../AAA', {'../AAA'}, {}), ('AAA', {'BBB'}, {}), ('AAA', {'AAA'}, {'bars':True}), ('AAA', {'AAA'}, {'interval':'minute'})):
                with self.assertRaises(ValueError):
                    read_cached_ohlc(ticker, allowed_tickers=allowed, **options)

    def test_rejects_linked_cache_directory_without_opening(self):
        with TemporaryDirectory() as directory:
            actual = Path(directory) / 'actual'; actual.mkdir()
            linked = Path(directory) / 'linked'
            try:
                linked.symlink_to(actual, target_is_directory=True)
            except OSError as error:
                self.skipTest(f'local symlink unavailable: {error}')
            with patch('data.cached_ohlc.CACHE_DIRECTORY', linked), patch('pathlib.Path.open', side_effect=AssertionError('link IO')):
                self.assertEqual(read_cached_ohlc('AAA', allowed_tickers={'AAA'})['status'], 'INVALID')


if __name__ == '__main__': unittest.main()
