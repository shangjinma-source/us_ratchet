"""Independent capture CSV resource/grammar tests, no actual capture."""
import ast
from datetime import date,timedelta
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_capture_source_csv_independent_reconstruction_research_v1 as module
from backtest import ndx_forward_source_capture_scoped_research as producer

HEADER=b'Date,Open,High,Low,Close,Volume'
SCOPE='2026-10-05'


class IndependentCaptureCSVTests(unittest.TestCase):
    def test_format_matrix_full_rows_and_diagnostics_match_scoped_contract(self):
        for ending in (b'\r',b'\n',b'\r\n'):
            for bom in (b'',b'\xef\xbb\xbf'):
                for quote in (False,True):
                    for blanks in (0,2):
                        lines=[HEADER]
                        for line in ('2026-10-02,10,9,11,10,100','2026-10-05,10,12,8,10,100','2026-10-06,10,12,8,10,100'):
                            if quote:line=','.join('"'+cell+'"'for cell in line.split(','))
                            lines.append(line.encode())
                        raw=bom+(ending*(blanks+1)).join(lines)+ending*blanks
                        _,metadata=producer.scoped_csv(raw,SCOPE)
                        self.assertEqual(module.csv_rows(raw,SCOPE),([row['raw_csv_row']for row in metadata['original_rows']],metadata['excluded_before_scope_ohlc_diagnostics']))

    def test_blank_records_do_not_consume_data_rows_or_add_physical_cap(self):
        for count in (21000,100005):
            raw=HEADER+b'\n'+b'\n'*count+b'2026-10-05,10,12,8,10,100\n'
            rows,issues=module.csv_rows(raw,SCOPE);self.assertEqual(len(rows),1);self.assertEqual(issues,[])
            self.assertEqual(rows[0]['Date'],SCOPE)
            self.assertEqual(producer.scoped_csv(raw,SCOPE)[1]['original_row_count'],1)

    def test_exact_data_and_byte_bounds(self):
        dates=[];day=date(1900,1,1)
        while len(dates)<20001:
            if day.weekday()<5:dates.append(day.isoformat())
            day+=timedelta(days=1)
        raw=HEADER+b'\n'+b''.join((day+',10,12,8,10,100\n').encode()for day in dates[:20000])
        self.assertEqual(len(module.csv_rows(raw,dates[0])[0]),20000)
        with self.assertRaises(ValueError):module.csv_rows(raw+(dates[-1]+',10,12,8,10,100\n').encode(),dates[0])
        with self.assertRaises(ValueError):module.csv_rows(b'\n'*8000001,SCOPE)

    def test_whole_suffix_corruption_and_invalid_numeric_dates_reject(self):
        base=HEADER+b'\n2026-10-05,10,12,8,10,100\n'
        for suffix in (b'2026-10-06,10,9,11,10,100\n',b'2026-10-06,"10\n",12,8,10,100\n',
                b'2026-10-05,10,12,8,10,100\n',b'2026-10-10,10,12,8,10,100\n',b'2026-10-06,NaN,12,8,10,100\n',
                b'2026-10-06,10,12,8,10,100,extra\n',b'2026-10-06,10,12,8,10,\xff\n'):
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):module.csv_rows(base+suffix,SCOPE)

    def test_independence_no_project_imports_or_filesystem_calls(self):
        tree=ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
        imports=[node.module or ''for node in ast.walk(tree)if isinstance(node,ast.ImportFrom)]
        self.assertFalse(any(name.startswith(('scripts','backtest'))for name in imports))
        raw=HEADER+b'\n2026-10-05,10,12,8,10,100'
        with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(producer,'scoped_csv',side_effect=AssertionError('Producer executed')):
            self.assertEqual(len(module.csv_rows(raw,SCOPE)[0]),1)


if __name__=='__main__':unittest.main()
