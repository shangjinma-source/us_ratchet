"""Root independent CSV review; supplied bytes only, no financial entry point."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_capture_source_csv_independent_reconstruction_research_v1 as module

HEADER = b'Date,Open,High,Low,Close,Volume\r\n'


class IndependentCaptureCsvReviewTests(unittest.TestCase):
    def test_preserves_raw_decimal_spellings_and_all_old_ohlc_violations(self):
        raw = HEADER + b'2026-10-02,10,9,11,10,0\r\n' + \
              '"2026-10-05","１_０","１２","٨","1e1","-0"'.encode() + b'\r\n'
        rows, issues = module.csv_rows(raw, '2026-10-05')
        self.assertEqual(rows[1], dict(Date='2026-10-05', Open='１_０', High='１２',
                                      Low='٨', Close='1e1', Volume='-0'))
        self.assertEqual(issues, [dict(original_data_row_index=0, session='2026-10-02',
            raw_csv_row=rows[0], violations=['LOW_EXCEEDS_OPEN', 'LOW_EXCEEDS_CLOSE',
                'HIGH_BELOW_OPEN', 'HIGH_BELOW_CLOSE', 'LOW_EXCEEDS_HIGH'],
            role='OUTSIDE_FRONTIER_SCOPE_DIAGNOSTIC_NOT_EXECUTION_PRICE')])

    def test_many_empty_records_are_allowed_but_nonempty_malformed_record_is_not(self):
        prefix = HEADER + b'\r\n' * 100005 + b'2026-10-05,10,12,8,10,100\r\n'
        self.assertEqual(len(module.csv_rows(prefix, '2026-10-05')[0]), 1)
        for suffix in (b'""\r\n', b' \r\n', b',,,,,\r\n',
                       b'2026-10-06,10,12,8,"1"0,100\r\n',
                       b'2026-10-06,10,12,8,NaN,100\r\n',
                       b'2026-10-04,10,12,8,10,100\r\n', b'\xff'):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                module.csv_rows(prefix + suffix, '2026-10-05')

    def test_rejects_nonbytes_ambiguous_headers_and_invalid_scope(self):
        raw = HEADER + b'2026-10-05,10,12,8,10,100'
        for value in (raw.decode(), bytearray(raw), memoryview(raw), b'', True, None):
            with self.subTest(value_type=type(value)), self.assertRaises(ValueError):
                module.csv_rows(value, '2026-10-05')
        for header in (b'Date,Open,High,Low,Close,Volume,extra\n',
                       b'Date,Open,High,Low,Close,Close\n',
                       b'Date,Open,High,Low,Close, Volume\n'):
            with self.subTest(header=header), self.assertRaises(ValueError):
                module.csv_rows(header + b'2026-10-05,10,12,8,10,100', '2026-10-05')
        for scope in ('20261005', '2026-10-05 ', None, 20261005):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                module.csv_rows(raw, scope)

    def test_no_producer_imports_or_execution_and_no_io(self):
        from backtest import ndx_forward_source_capture_scoped_research as producer
        from backtest import ndx_accounted_source_prefix_research_v1 as prefix
        tree = ast.parse(Path(module.__file__).read_bytes())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module)
        self.assertEqual(set(imports), {'csv', 'datetime', 'decimal', 'io'})
        raw = HEADER + b'2026-10-05,10,12,8,10,100'
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('IO')), \
                patch.object(producer, 'scoped_csv', side_effect=AssertionError('Producer')), \
                patch.object(prefix, 'derive_accounted_prefix', side_effect=AssertionError('Prefix producer')):
            self.assertEqual(module.csv_rows(raw, '2026-10-05')[0][0]['Close'], '10')


if __name__ == '__main__':
    unittest.main()
