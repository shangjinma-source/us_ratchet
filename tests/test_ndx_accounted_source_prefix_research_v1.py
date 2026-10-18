"""Exact raw prefix boundaries; these tests do not create observations."""
from copy import deepcopy
from hashlib import sha256
import unittest

from backtest import ndx_accounted_source_prefix_research_v1 as module


HEADER = b'Date,Open,High,Low,Close,Volume'
DAYS = ['2026-10-05', '2026-10-06', '2026-10-07']


def arguments(raw, days=None):
    return dict(source_bytes=raw,
                source_reference=dict(path='immutable/source.csv', sha256=sha256(raw).hexdigest()),
                accounted_sessions=list(days if days is not None else DAYS[:2]),
                scope_start=DAYS[0])


class AccountedSourceBytePrefixTests(unittest.TestCase):
    def test_mixed_pending_suffix_retains_exact_bom_crlf_quotes_and_blank_lines(self):
        prefix = b'\xef\xbb\xbf' + HEADER + b'\r\n' + b'"2026-10-05",10,12,8,10,100\r\n\r\n2026-10-06,10,12,8,10,100\r\n\r\n'
        raw = prefix + b'2026-10-07,10,12,8,10,100\r\n'
        args = arguments(raw); before = deepcopy(args)
        derived, evidence = module.derive_accounted_prefix(**args)
        self.assertEqual(derived, prefix); self.assertEqual(args, before)
        self.assertEqual(evidence['byte_stop'], len(prefix))
        self.assertEqual(evidence['accounted_sessions'], DAYS[:2])
        self.assertEqual(evidence['suffix_sessions'], DAYS[2:])
        self.assertEqual(evidence['suffix_original_row_indexes'], [2])
        self.assertTrue(all(evidence[key] is False for key in module.FLAGS))
        self.assertFalse(evidence['csv_reserialized'])
        evidence['full_source_reference']['path'] = 'mutated'
        self.assertEqual(args, before)

    def test_full_prefix_is_original_bytes_with_trailing_blanks_and_no_final_newline(self):
        for ending in (b'', b'\n\n', b'\r\n\r\n'):
            raw = HEADER + b'\n2026-10-05,10,12,8,10,100\n2026-10-06,10,12,8,10,100' + ending
            with self.subTest(ending=ending):
                prefix, evidence = module.derive_accounted_prefix(**arguments(raw))
                self.assertEqual(prefix, raw)
                self.assertEqual(evidence['byte_stop'], len(raw))
                self.assertEqual(evidence['suffix_sessions'], [])

    def test_cr_only_and_mixed_newlines_are_preserved(self):
        prefix = HEADER + b'\r2026-10-05,10,12,8,10,100\r\n2026-10-06,10,12,8,10,100\n'
        raw = prefix + b'2026-10-07,10,12,8,10,100'
        derived, evidence = module.derive_accounted_prefix(**arguments(raw))
        self.assertEqual(derived, prefix)
        self.assertEqual(evidence['prefix_sha256'], sha256(prefix).hexdigest())

    def test_pre_scope_bad_ohlc_is_retained_as_diagnostic_not_repaired(self):
        old = b'2026-10-02,10,9,11,10,100\n'
        prefix = HEADER + b'\n' + old + b'2026-10-05,10,12,8,10,100\n2026-10-06,10,12,8,10,100\n'
        derived, evidence = module.derive_accounted_prefix(**arguments(prefix + b'2026-10-07,10,12,8,10,100\n'))
        self.assertEqual(derived, prefix)
        self.assertEqual(evidence['excluded_before_scope_original_row_indexes'], [0])
        self.assertEqual(evidence['excluded_before_scope_rows'][0]['raw_csv_row']['High'], '9')
        self.assertTrue(evidence['excluded_before_scope_ohlc_diagnostics'])

    def test_holes_reordering_duplicates_scope_and_hash_mismatch_reject(self):
        raw = HEADER + b'\n' + b''.join((day + ',10,12,8,10,100\n').encode() for day in DAYS)
        cases = []
        for days in ([], [DAYS[0], DAYS[2]], [DAYS[1], DAYS[0]], [DAYS[0], DAYS[0]]):
            cases.append(arguments(raw, days))
        changed = arguments(raw); changed['scope_start'] = '2026-10-02'; cases.append(changed)
        changed = arguments(raw); changed['source_reference']['sha256'] = '0' * 64; cases.append(changed)
        changed = arguments(raw); changed['source_reference']['extra'] = True; cases.append(changed)
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                module.derive_accounted_prefix(**args)

    def test_in_scope_corruption_in_unretained_suffix_is_not_hidden(self):
        prefix = HEADER + b'\n2026-10-05,10,12,8,10,100\n2026-10-06,10,12,8,10,100\n'
        for suffix in (b'2026-10-07,10,9,11,10,100\n', b'"2026-10-07,10,12,8,10,100\n'):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                module.derive_accounted_prefix(**arguments(prefix + suffix))


if __name__ == '__main__':
    unittest.main()
