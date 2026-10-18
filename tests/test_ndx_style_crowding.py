from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from backtest.ndx_style_crowding import (
    build_risk_chain_exposure,
    marginal_risk_contributions,
    parse_weight_map,
    read_verified_style_crowding_bundle,
    resolve_risk_chain,
    style_metrics_before,
    write_style_crowding_bundle,
)


class NdxStyleCrowdingTests(unittest.TestCase):
    def test_weight_parser_rejects_benchmark_and_requires_stock_sleeve_sum(self) -> None:
        self.assertEqual(parse_weight_map("AAA:0.4;BBB:0.6"), {"AAA": 0.4, "BBB": 0.6})
        with self.assertRaises(ValueError):
            parse_weight_map("QQQ:1.0")
        with self.assertRaises(ValueError):
            parse_weight_map("AAA:0.4;BBB:0.4")

    def test_incumbent_overlay_is_not_backfilled_into_historical_candidates(self) -> None:
        taxonomy = pd.DataFrame([
            {
                "ticker": "AAA", "issuer_id": "issuer:aaa", "security_id": "security:aaa",
                "risk_chain": "consumer", "risk_chain_label": "消费",
                "selection_date_start": "2020-01-01", "selection_date_end": "2025-01-01",
                "evidence_available_date": "2020-01-01", "confidence": "high",
                "status": "accepted", "evidence_source": "SEC",
            }
        ])
        overlay = pd.DataFrame([
            {
                "ticker": "BBB", "issuer_id": "issuer:bbb", "security_id": "security:bbb",
                "risk_chain": "ai_accelerator", "evidence_available_date": "2019-01-01",
                "effective_from": "2019-01-01", "effective_to": "",
                "confidence": "high", "status": "accepted", "evidence_source": "SEC",
            }
        ])
        historical = resolve_risk_chain(
            "BBB", "2022-01-01", source_scope="historical_taxonomy",
            taxonomy=taxonomy, overlay=overlay,
        )
        incumbent = resolve_risk_chain(
            "BBB", "2022-01-01", source_scope="incumbent_overlay",
            taxonomy=taxonomy, overlay=overlay,
        )
        self.assertEqual(historical["risk_chain"], "unclassified")
        self.assertEqual(incumbent["risk_chain"], "ai_accelerator")

    def test_risk_chain_exposure_keeps_unclassified_as_conservative_bucket(self) -> None:
        portfolio = {
            "portfolio_id": "test", "family": "test", "profile_id": "test", "role": "test",
            "selection_date": "2024-01-01", "equity_weight": 0.75,
            "weights": {"AAA": 0.5, "BBB": 0.5},
        }
        rows = pd.DataFrame([
            {
                "portfolio_id": "test", "family": "test", "profile_id": "test", "role": "test",
                "selection_date": "2024-01-01", "ticker": "AAA", "issuer_id": "issuer:aaa",
                "security_id": "security:aaa", "risk_chain": "consumer", "risk_chain_label": "消费",
                "confidence": "high", "classification_status": "accepted", "classification_reason": "",
                "evidence_source": "SEC", "evidence_available_date": "2020-01-01",
                "source_scope": "historical_taxonomy", "equity_sleeve_weight": 0.5,
                "portfolio_weight": 0.375, "classification_available_by_selection": True,
                "marginal_risk_pct": np.nan,
            },
            {
                "portfolio_id": "test", "family": "test", "profile_id": "test", "role": "test",
                "selection_date": "2024-01-01", "ticker": "BBB", "issuer_id": "",
                "security_id": "", "risk_chain": "unclassified", "risk_chain_label": "未分类",
                "confidence": "", "classification_status": "unclassified", "classification_reason": "",
                "evidence_source": "", "evidence_available_date": "",
                "source_scope": "historical_taxonomy", "equity_sleeve_weight": 0.5,
                "portfolio_weight": 0.375, "classification_available_by_selection": False,
                "marginal_risk_pct": np.nan,
            },
        ])
        summary, exposure = build_risk_chain_exposure(portfolio, rows)
        self.assertAlmostEqual(summary["unclassified_weight"], 0.375)
        self.assertEqual(summary["unclassified_ticker_count"], 1)
        self.assertIn("unclassified", set(exposure["risk_chain"]))

    def test_price_diagnostics_are_strictly_before_selection_date(self) -> None:
        dates = pd.date_range("2023-01-01", periods=120, freq="B")
        base = np.arange(120, dtype=float) + 100.0
        close = pd.DataFrame({
            "AAA": base,
            "BBB": base * 1.01,
            "QQQ": base * 1.02,
            "SPY": base * 0.99,
            "SMH": base * 1.03,
        }, index=dates)
        portfolio = {
            "portfolio_id": "test", "family": "test", "profile_id": "test", "role": "test",
            "selection_date": dates[100].strftime("%Y-%m-%d"),
            "equity_weight": 0.75, "weights": {"AAA": 0.5, "BBB": 0.5},
        }
        style = style_metrics_before(close, portfolio, lookback_days=[60], min_observations=20)
        self.assertEqual(style.iloc[0]["status"], "ok")
        self.assertTrue(bool(style.iloc[0]["strict_asof_passed"]))
        self.assertLess(style.iloc[0]["price_end"], portfolio["selection_date"])
        risk = marginal_risk_contributions(close, portfolio, lookback_days=60, min_observations=20)
        self.assertTrue((risk["status"] == "ok").all())
        self.assertAlmostEqual(float(risk["marginal_risk_pct"].sum()), 1.0, places=6)

    def test_static_bundle_reader_verifies_sidecar_hashes(self) -> None:
        frames = {
            "portfolio_summary": pd.DataFrame([{"portfolio_id": "test"}]),
            "risk_chain_exposure": pd.DataFrame([{"risk_chain": "unclassified"}]),
            "ticker_exposure": pd.DataFrame([{"ticker": "AAA"}]),
            "style_metrics": pd.DataFrame([{"lookback_days": 252}]),
            "risk_contributions": pd.DataFrame([{"ticker": "AAA"}]),
            "coverage": pd.DataFrame([{"metric": "portfolio_count", "value": 1}]),
            "unresolved": pd.DataFrame([{"issue_type": "test"}]),
        }
        summary = {
            "dataset_type": "ndx_style_crowding_diagnostic",
            "dataset_key": "test_style_crowding",
            "research_only": True,
            "historical_diagnostic_only": True,
            "fresh_oos": False,
            "promotion_allowed": False,
            "qqq_is_candidate": False,
            "return_data_read": True,
            "price_data_used": True,
        }
        with TemporaryDirectory() as directory:
            write_style_crowding_bundle(frames, summary, directory, write_xlsx=False)
            loaded = read_verified_style_crowding_bundle(directory)
            self.assertTrue(loaded["available"])
            self.assertEqual(loaded["portfolio_summary"][0]["portfolio_id"], "test")

            with open(f"{directory}/coverage.csv", "ab") as handle:
                handle.write(b"tampered\n")
            with self.assertRaises(ValueError):
                read_verified_style_crowding_bundle(directory)


if __name__ == "__main__":
    unittest.main()
