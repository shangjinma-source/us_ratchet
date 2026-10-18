from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from backtest.ndx_correlation_clusters import (
    NdxCorrelationClusterError,
    build_selection_plan,
    complete_linkage_clusters,
    correlation_matrix_before,
    scenario_cluster_metrics,
)


def _selection_row(cost: float, *, weights: str | None = None) -> dict:
    return {
        "experiment_id": "test",
        "phase_id": "training",
        "lookback_years": 2.0,
        "top_n": 4,
        "weight_mode": "equal",
        "rebalance_months": 6,
        "safe_weight": 0.0,
        "max_weight": 0.25,
        "trade_cost_bps": cost,
        "window_start": "2022-01-11",
        "selection_date": "2022-01-11",
        "trigger": "scheduled",
        "report_date": "2021-09-30",
        "available_date": "2021-11-30",
        "accession_number": "report-a",
        "tickers": "A;B;C;D",
        "weights": weights or "A:0.25;B:0.25;C:0.25;D:0.25",
    }


class NdxCorrelationClusterTests(unittest.TestCase):
    def test_selection_plan_reuses_identical_choices_across_costs(self):
        selections = pd.DataFrame([
            _selection_row(5.0),
            _selection_row(10.0),
            _selection_row(25.0),
        ])

        plan = build_selection_plan(selections, canonical_cost_bps=10.0)

        self.assertTrue(plan["audit"]["cost_invariance_passed"])
        self.assertEqual(plan["audit"]["unique_shape_events"], 1)
        self.assertEqual(plan["audit"]["unique_date_ticker_universes"], 1)
        self.assertEqual(plan["audit"]["unique_weight_scenarios"], 1)

    def test_selection_plan_rejects_weight_changes_across_costs(self):
        selections = pd.DataFrame([
            _selection_row(5.0),
            _selection_row(10.0, weights="A:0.4;B:0.3;C:0.2;D:0.1"),
        ])

        with self.assertRaisesRegex(NdxCorrelationClusterError, "vary across"):
            build_selection_plan(selections, canonical_cost_bps=10.0)

    def test_correlation_uses_only_prices_strictly_before_selection(self):
        dates = pd.bdate_range("2020-01-01", periods=100)
        returns = np.asarray([0.001 + 0.0005 * np.sin(index) for index in range(100)])
        a = 100.0 * np.cumprod(1.0 + returns)
        b = a.copy()
        b[80:] = b[79] * np.cumprod(1.0 - returns[80:])
        c = 100.0 * np.cumprod(1.0 + np.roll(returns, 7))
        close = pd.DataFrame({"A": a, "B": b, "C": c}, index=dates)

        corr, meta = correlation_matrix_before(
            close,
            ["A", "B", "C"],
            dates[80],
            lookback_days=60,
            min_observations=20,
        )

        self.assertTrue(meta["strict_asof_passed"])
        self.assertLess(pd.Timestamp(meta["price_end"]), dates[80])
        self.assertAlmostEqual(corr.loc["A", "B"], 1.0)

    def test_complete_linkage_and_weighted_cluster_metrics_are_auditable(self):
        names = ["A", "B", "C", "D"]
        corr = pd.DataFrame(
            [
                [1.0, 0.90, 0.20, 0.10],
                [0.90, 1.0, 0.15, 0.05],
                [0.20, 0.15, 1.0, 0.80],
                [0.10, 0.05, 0.80, 1.0],
            ],
            index=names,
            columns=names,
        )
        labels = complete_linkage_clusters(corr, 0.75)
        scenario = {
            "scenario_id": "scenario:test",
            "universe_id": "universe:test",
            "selection_date": "2022-01-11",
            "tickers": "A;B;C;D",
            "weights": "A:0.4;B:0.3;C:0.2;D:0.1",
        }
        meta = {
            "requested_lookback_days": 252,
            "observations": 252,
            "coverage": 1.0,
            "price_start": "2021-01-11",
            "price_end": "2022-01-10",
            "strict_asof_passed": True,
        }

        result = scenario_cluster_metrics(scenario, corr, meta, 0.75, labels)

        self.assertEqual(labels["A"], labels["B"])
        self.assertEqual(labels["C"], labels["D"])
        self.assertNotEqual(labels["A"], labels["C"])
        self.assertEqual(result["cluster_count"], 2)
        self.assertAlmostEqual(result["max_cluster_weight"], 0.7)
        self.assertAlmostEqual(result["largest_cluster_top2_weight"], 0.7)
        self.assertAlmostEqual(result["effective_cluster_count"], 1.0 / 0.58)
        self.assertEqual(result["high_corr_pair_count"], 2)
        self.assertEqual(result["largest_cluster_tickers"], "A;B")


if __name__ == "__main__":
    unittest.main()
