"""Read-only source integration and small synthetic sizing checks; no selector."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import unittest
from unittest.mock import patch

from data.current_top1_portfolio_research import (
    CurrentTop1PortfolioResearch, project_top1, RESULT,
    PreviewSourceError, ResearchExpiredError,
)


class Top1ProjectionTests(unittest.TestCase):
    def test_exact_floor_and_no_runner_up(self):
        args = dict(decision_date='2026-10-13', prices={'A': '30', 'B': '1'},
                    metadata={'A': {'ticker': 'AAA', 'issuer_id': 'IA'}, 'B': {'ticker': 'BBB', 'issuer_id': 'IB'}},
                    fee_bps='0', minimum_cash_buffer='0')
        small = project_top1(args, 'A', '29.99')
        self.assertEqual((small['status'], small['stocks'], small['cash']), ('ALL_CASH', [], 29.99))
        large = project_top1(args, 'A', '100.01')
        self.assertEqual(large['stocks'][0]['units'], 3)
        accounting = large['budget_identity_exact']
        self.assertEqual(Fraction(accounting['stock_notional']) + Fraction(accounting['residual_cash']), Fraction('100.01'))
        self.assertEqual(args['prices'], {'A': '30', 'B': '1'})

    def test_real_seed_snapshot_and_selected_only_bars(self):
        service = CurrentTop1PortfolioResearch()
        result = service.calculate('20000')
        self.assertEqual([(r['ticker'], r['units']) for r in result['stocks']], [('SNDK', 13)])
        self.assertEqual(result['generator_calls_this_request'], 0)
        self.assertEqual(result['selector_calls_this_request'], 0)
        self.assertEqual(Fraction(result['budget_identity_exact']['residual_cash']), Fraction(5977789, 8192))
        copy = service.snapshot(result['research_id'])
        copy['stocks'].clear()
        self.assertEqual(len(service.snapshot(result['research_id'])['stocks']), 1)
        for interval in ('day', 'week', 'month'):
            chart = service.bars(result['research_id'], 'SNDK', interval)
            self.assertEqual(chart['bars'][-1]['close'], result['stocks'][0]['close'])
            self.assertEqual(chart['daily_as_of'], '2026-10-13')
        with self.assertRaises(PreviewSourceError):
            service.bars(result['research_id'], 'MRNA')

    def test_cash_identity_cache_and_lru(self):
        service = CurrentTop1PortfolioResearch()
        first = service.calculate('50')
        self.assertEqual(first['status'], 'ALL_CASH')
        self.assertTrue(service.calculate('50.00')['cache_hit'])
        for amount in range(100, 109):
            service.calculate(str(amount))
        with self.assertRaises(ResearchExpiredError):
            service.snapshot(first['research_id'])
        with self.assertRaises(ValueError):
            service.calculate(True)
        with self.assertRaises(ValueError):
            service.calculate('0')

    def test_source_drift_fails_closed_even_cached(self):
        service = CurrentTop1PortfolioResearch()
        result = service.calculate('20000')
        original = Path.read_bytes
        def changed(path):
            value = original(path)
            return value + b' ' if path.as_posix().endswith(RESULT) else value
        with patch.object(Path, 'read_bytes', changed):
            with self.assertRaises(PreviewSourceError):
                service.snapshot(result['research_id'])
        self.assertFalse(service.results)

    def test_source_path_escape_rejected(self):
        service = CurrentTop1PortfolioResearch()
        with self.assertRaises(PreviewSourceError):
            service._path('../outside.json')
        with self.assertRaises(PreviewSourceError):
            service._path('C:/outside.json')


if __name__ == '__main__':
    unittest.main()
