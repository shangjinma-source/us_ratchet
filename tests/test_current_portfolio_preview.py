"""Focused source/cache/OHLC checks; synthetic files only, no provider or account."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.current_portfolio_preview import CurrentPortfolioPreview, PreviewSourceError, RESULT, PANEL, QUOTES


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        tickers = ['S' + str(number) for number in range(6)]
        positions = [dict(ticker=ticker, security_id=ticker, issuer_id=ticker, indicative_units=1,
                          saved_close=12, target_weight='1/6', stock_internal_weight='1/6') for ticker in tickers]
        result = dict(status='SELECTED_CURRENT_INDICATIVE_RESEARCH_CANDIDATE',
                      current_adoption_allowed=False, orders_created=False, saved_observation_date='2026-02-02',
                      fresh_cash_pool='1000', selected_positions=positions,
                      selected_candidate=dict(indicative_residual_cash='927.928', indicative_buy_fee='0.072',
                                              indicative_total_cost='72.072', method_rule_id='synthetic'))
        panel = dict(calendar=['2026-01-29', '2026-01-30', '2026-02-02'], price_basis='SYNTHETIC',
                     stocks=[dict(ticker=ticker, values=[[9, 11, 8, 10, 100], [10, 13, 9, 11, 200], [11, 14, 10, 12, 300]]) for ticker in tickers])
        quotes = dict(rows=[dict(ticker=ticker, display_price='15', reference_snapshot_date='2026-02-02',
                                reference_snapshot_close=12, weight_recalculation_allowed=False,
                                execution_authorized=False, display_market_date='2026-02-03', source='synthetic') for ticker in tickers])
        self.pins = {}
        for relative, value in ((RESULT, result), (PANEL, panel), (QUOTES, quotes)):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(value).encode()
            path.write_bytes(raw)
            self.pins[relative] = hashlib.sha256(raw).hexdigest()
        self.preview = CurrentPortfolioPreview(self.root, self.pins)

    def test_budget_quotes_and_exact_ohlc_aggregation(self):
        result = self.preview.preview()
        self.assertAlmostEqual(result['invested'] + result['fees'] + result['cash'], result['budget'])
        self.assertEqual(result['stocks'][0]['close'], 12)
        self.assertEqual(result['stocks'][0]['latest_reference_quote'], 15)
        self.assertEqual(result['stocks'][0]['notional'], 12)
        for interval in ('week', 'month'):
            bars = self.preview.bars('S0', interval)['bars']
            self.assertEqual(len(bars), 2)
            self.assertEqual((bars[0]['open'], bars[0]['high'], bars[0]['low'], bars[0]['close'], bars[0]['volume']),
                             (9, 13, 8, 11, 300))
        self.assertEqual(len(self.preview.bars('S0', 'day', 1)['bars']), 1)

    def test_cache_does_not_reread_and_responses_are_isolated(self):
        original = self.preview.preview()
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('unchanged cache reread')):
            original['stocks'][0]['close'] = 999
            self.assertEqual(self.preview.preview()['stocks'][0]['close'], 12)
            self.assertEqual(len(self.preview.bars('S0')['bars']), 3)

    def test_changed_source_does_not_serve_old_cache(self):
        self.preview.preview()
        path = self.root / PANEL
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaises(PreviewSourceError):
            self.preview.preview()
        self.assertIsNone(self.preview.payload)

    def test_allowlist_and_bounds(self):
        for arguments in [('SPY', 'day', 90), ('S0', 'year', 90), ('S0', 'day', 261), ('S0', 'day', True)]:
            with self.assertRaises(ValueError):
                self.preview.bars(*arguments)

    def test_actual_ohlc_invalid_not_replaced_with_close(self):
        panel_path = self.root / PANEL
        value = json.loads(panel_path.read_bytes())
        value['stocks'][0]['values'][0][1] = 5
        raw = json.dumps(value).encode()
        panel_path.write_bytes(raw)
        self.pins[PANEL] = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(PreviewSourceError):
            CurrentPortfolioPreview(self.root, self.pins).preview()


if __name__ == '__main__':
    unittest.main()
