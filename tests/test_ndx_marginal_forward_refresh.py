from __future__ import annotations

import unittest
from pathlib import Path

from scripts.ndx_marginal_forward_refresh import cohort_price_tickers


ROOT = Path(__file__).resolve().parents[1]


class NdxMarginalForwardRefreshTests(unittest.TestCase):
    def test_refresh_scope_is_exactly_frozen_incumbents_and_champions(self):
        tickers = cohort_price_tickers(
            ROOT / "data/cache/research/ndx_marginal_forward_v1/cohort_index.jsonl"
        )
        self.assertEqual(len(tickers), 30)
        self.assertTrue({"NVDA", "TSM", "STX", "LRCX", "APP"}.issubset(tickers))
        self.assertNotIn("QQQ", tickers)


if __name__ == "__main__":
    unittest.main()
