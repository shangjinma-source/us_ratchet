"""Logical CSV records versus original byte offsets, pure adversarial tests."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_accounted_source_prefix_research_v1 as module
import test_ndx_accounted_source_prefix_research_v1 as author


class IndependentAccountedPrefixTests(unittest.TestCase):
    def test_utf8_quoted_records_bom_and_mixed_newline_byte_offsets(self):
        # Full-width digits are accepted numeric values but have multi-byte UTF8.
        header=b'\xef\xbb\xbf'+author.HEADER+b'\r\n\n'
        old=b'2026-10-02,10,9,11,10,100\r\n'
        first='2026-10-05,"１０",12,8,10,100\n'.encode('utf-8')
        second=b'2026-10-06,10,12,8,"10",100\r\n\r\n'
        prefix=header+old+first+second
        suffix=b'2026-10-07,"10",12,8,10,100'
        raw=prefix+suffix;a=author.arguments(raw);before=deepcopy(a)
        result,e=module.derive_accounted_prefix(**a)
        self.assertEqual(result,prefix);self.assertEqual(e['byte_stop'],len(prefix))
        self.assertEqual(e['prefix_sha256'],sha256(prefix).hexdigest());self.assertEqual(e['suffix_sessions'],['2026-10-07'])
        self.assertEqual(e['accounted_original_row_indexes'],[1,2]);self.assertEqual(e['suffix_original_row_indexes'],[3])
        self.assertEqual(e['excluded_before_scope_original_row_indexes'],[0]);self.assertTrue(e['excluded_before_scope_ohlc_diagnostics'])
        self.assertEqual(a,before)

    def test_quoted_fullprefix_original_bytes_and_no_final_newline(self):
        raw=b'\xef\xbb\xbf'+author.HEADER+b'\r2026-10-05,10,12,8,"10",100\n2026-10-06,"10",12,8,10,100'
        prefix,e=module.derive_accounted_prefix(**author.arguments(raw))
        self.assertEqual(prefix,raw);self.assertEqual(e['prefix_byte_count'],len(raw))
        self.assertEqual(e['full_source_byte_count'],len(raw));self.assertEqual(e['byte_start'],0)
        self.assertEqual(e['suffix_original_row_indexes'],[]);self.assertEqual(e['retained_original_row_count'],2)

    def test_multiline_record_spans_are_complete_but_business_parser_stays_failclosed(self):
        header=b'\xef\xbb\xbf'+author.HEADER+b'\r\n'
        first=b'2026-10-05,"10\r\n",12,8,10,100\n'
        blank=b'\r\n';second=b'2026-10-06,10,12,8,"10\n",100'
        rows=[dict(zip(module.scoped_parser.FIELDS,['2026-10-05','10\r\n','12','8','10','100'])),
              dict(zip(module.scoped_parser.FIELDS,['2026-10-06','10','12','8','10\n','100']))]
        metadata=dict(original_row_count=2,original_rows=[dict(raw_csv_row=r)for r in rows])
        spans=module._record_spans(header+first+blank+second,metadata)
        self.assertEqual(spans,[(len(header),len(header+first)),(len(header+first+blank),len(header+first+blank+second))])
        # Quoted multiline prices violate frozen scoped field whitespace grammar.
        # The public primitive must reject rather than silently cutting/reserializing.
        with self.assertRaises(ValueError):module.derive_accounted_prefix(**author.arguments(header+first+blank+second))

    def test_exact_physical_line_bound_even_blank_unretained_lines(self):
        records=author.HEADER+b'\n2026-10-05,10,12,8,10,100\n2026-10-06,10,12,8,10,100\n'
        raw=records+b'\n'*(module.MAX_PHYSICAL_LINES-3)
        prefix,_=module.derive_accounted_prefix(**author.arguments(raw));self.assertEqual(prefix,raw)
        with self.assertRaisesRegex(ValueError,'Physical CSV line bound'):module.derive_accounted_prefix(**author.arguments(raw+b'\n'))
        # Extra physical lines in a pending quoted record cannot evade the bound.
        raw=records+b'2026-10-07,"10'+b'\n'*module.MAX_PHYSICAL_LINES+b'",12,8,10,100\n'
        with self.assertRaises(ValueError):module.derive_accounted_prefix(**author.arguments(raw))

    def test_source_reference_whitespace_and_suffix_canonical_dates_reject(self):
        raw=author.HEADER+b'\n2026-10-05,10,12,8,10,100\n2026-10-06,10,12,8,10,100\n'
        a=author.arguments(raw);a['source_reference']['path']=' immutable/source.csv '
        with self.assertRaises(ValueError):module.derive_accounted_prefix(**a)
        for suffix in (b'2026-10-06,10,12,8,10,100\n',b'2026-10-04,10,12,8,10,100\n',
                       b'20261007,10,12,8,10,100\n',b'2026-10-07,NaN,12,8,10,100\n'):
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):module.derive_accounted_prefix(**author.arguments(raw+suffix))

    def test_deep_detachment_no_io_and_evidence_authority_boundary(self):
        raw=author.HEADER+b'\n2026-10-05,10,12,8,10,100\n2026-10-06,10,12,8,10,100\n2026-10-07,10,12,8,10,100\n'
        a=author.arguments(raw);before=deepcopy(a)
        with (patch.object(Path,'read_bytes',side_effect=AssertionError('Pure read')),
              patch.object(Path,'open',side_effect=AssertionError('Pure open')),
              patch.object(Path,'stat',side_effect=AssertionError('Pure stat'))):
            prefix,e=module.derive_accounted_prefix(**a)
        self.assertTrue(raw.startswith(prefix));self.assertFalse(e['csv_reserialized'])
        self.assertNotIn('prefix_reference',e);self.assertNotIn('prefix_path',e)
        self.assertTrue(all(e[k] is False for k in module.FLAGS))
        e['accounted_sessions'].clear();e['full_source_reference'].clear();self.assertEqual(a,before)


if __name__=='__main__':unittest.main()
