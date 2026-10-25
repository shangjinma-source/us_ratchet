import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import reconstruct_qqq_20231229_reference as subject


class DecemberReferenceTests(unittest.TestCase):
    def test_saved_reference_uses_contemporaneous_issuer_not_future_report(self):
        result = subject.reconstruct(Path(__file__).resolve().parents[1])
        self.assertEqual(len(result['resolved_tickers']), 101)
        self.assertEqual(result['security_count_including_unresolved'], 101)
        self.assertIn('ORLY', result['resolved_tickers'])
        self.assertEqual(result['later_report_comparison']['only_in_later_report'], [])
        orly = next(row for row in result['anchor']['rows'] if row.get('local_registry_ticker') == 'ORLY')
        self.assertEqual(orly['conservative_symbol_available_date'], '2023-11-09')
        self.assertNotIn('cusip', orly)
        self.assertFalse(result['later_report_comparison']['used_for_reconstruction'])
        self.assertFalse(result['eligible_for_strategy_backtest'])
        self.assertIn('TTWO', result['resolved_tickers'])
        self.assertNotIn('SGEN', result['resolved_tickers'])

    def test_unpublished_anchor_rejected(self):
        with patch.object(subject, 'match', return_value={'conservative_available_date': '2024-01-01'}):
            with self.assertRaisesRegex(ValueError, 'ANCHOR_NOT_YET_AVAILABLE'):
                subject.reconstruct(Path.cwd())

    def test_altered_issuer_symbol_rejected(self):
        original = Path.read_bytes

        def changed(path):
            raw = original(path)
            return raw.replace(b'ORLY', b'FAKE') if path.name == 'orly-20230930-10q.html' else raw

        with patch.object(Path, 'read_bytes', changed):
            with self.assertRaisesRegex(ValueError, 'ORLY_ISSUER_SOURCE_CHANGED'):
                subject.reconstruct(Path(__file__).resolve().parents[1])

    def test_tampered_original_release_rejected_even_if_update_valid(self):
        original = Path.read_bytes

        def changed(path):
            if path.name == 'ndx_annual_reconstitution_2023_initial.html':
                return b'altered initial release'
            return original(path)

        with patch.object(Path, 'read_bytes', changed):
            with self.assertRaisesRegex(ValueError, 'OFFICIAL_SOURCE_CHANGED'):
                subject.reconstruct(Path(__file__).resolve().parents[1])


if __name__ == '__main__':
    unittest.main()
