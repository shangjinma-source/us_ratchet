from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data.ndx_security_identity import (
    NdxSecurityIdentityError,
    apply_security_lifecycle,
    load_security_lifecycle,
)


class NdxSecurityIdentityTests(unittest.TestCase):
    def test_repository_lifecycle_resolves_symbol_change_by_effective_date(self):
        lifecycle = load_security_lifecycle("config/ndx_security_lifecycle.yaml")
        plan = pd.DataFrame([
            {"selection_date": "2022-06-08", "ticker": "META", "cik": 1326801},
            {"selection_date": "2022-06-09", "ticker": "META", "cik": 1326801},
            {"selection_date": "2023-06-07", "ticker": "FISV", "cik": 798354},
            {"selection_date": "2023-06-08", "ticker": "AAPL", "cik": 320193},
        ])
        result = apply_security_lifecycle(plan, lifecycle).set_index("ticker")
        meta = apply_security_lifecycle(plan.iloc[:2], lifecycle)
        self.assertEqual(list(meta["price_ticker"]), ["FB", "META"])
        self.assertEqual(result.loc["FISV", "price_ticker"], "FI")
        self.assertEqual(result.loc["AAPL", "price_ticker"], "AAPL")
        self.assertTrue(bool(result.loc["FISV", "ticker_alias_applied"]))
        self.assertEqual(
            result.loc["FISV", "ticker_lifecycle_rule_id"],
            "fiserv_fisv_to_fi_2023",
        )

    def test_lifecycle_rejects_gap_between_intervals(self):
        yaml_text = """
schema_version: 1
mapping_id: invalid_gap
rules:
  - rule_id: test
    cik: '0000000001'
    cusip: '123456789'
    issuer_name: Test
    recognized_tickers: [OLD, NEW]
    intervals:
      - {effective_from: null, effective_to: 2024-01-01, price_ticker: OLD}
      - {effective_from: 2024-01-03, effective_to: null, price_ticker: NEW}
    evidence:
      - {effective_date: 2024-01-03, url: 'https://example.com/evidence'}
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lifecycle.yaml"
            path.write_text(yaml_text, encoding="utf-8")
            with self.assertRaisesRegex(NdxSecurityIdentityError, "gap or overlap"):
                load_security_lifecycle(path)

    def test_lifecycle_rejects_unrecognized_plan_ticker(self):
        lifecycle = load_security_lifecycle("config/ndx_security_lifecycle.yaml")
        plan = pd.DataFrame([
            {"selection_date": "2022-06-09", "ticker": "WRONG", "cik": 1326801}
        ])
        with self.assertRaisesRegex(NdxSecurityIdentityError, "not recognized"):
            apply_security_lifecycle(plan, lifecycle)


if __name__ == "__main__":
    unittest.main()
