from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

import pandas as pd

from backtest.ndx_pair_analysis import (
    select_pair_finalists,
    stage7_sensitivity_spec,
)


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / "data" / "cache" / "test_tmp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class NdxPairAnalysisTests(unittest.TestCase):
    def test_finalists_are_distinct_metric_roles(self):
        effects = pd.DataFrame([
            {
                "profile_id": "median",
                "omitted_ticker_1": "A",
                "omitted_ticker_2": "B",
                "omitted_tickers": "A;B",
                "concentration_guard_passed": True,
                "candidate_p50_return_delta_median": 0.05,
                "candidate_p10_return_delta_median": 0.02,
                "candidate_dd_p90_delta_median": -0.01,
            },
            {
                "profile_id": "tail",
                "omitted_ticker_1": "A",
                "omitted_ticker_2": "C",
                "omitted_tickers": "A;C",
                "concentration_guard_passed": True,
                "candidate_p50_return_delta_median": 0.04,
                "candidate_p10_return_delta_median": 0.04,
                "candidate_dd_p90_delta_median": -0.02,
            },
            {
                "profile_id": "drawdown",
                "omitted_ticker_1": "B",
                "omitted_ticker_2": "C",
                "omitted_tickers": "B;C",
                "concentration_guard_passed": True,
                "candidate_p50_return_delta_median": 0.03,
                "candidate_p10_return_delta_median": 0.01,
                "candidate_dd_p90_delta_median": 0.01,
            },
        ])

        selected = select_pair_finalists(effects)

        self.assertEqual(selected["profile_id"].tolist(), ["median", "tail", "drawdown"])
        self.assertEqual(
            selected["analysis_role"].tolist(),
            ["best_median_return", "best_tail_return", "best_drawdown_pressure"],
        )

    def test_stage7_has_baseline_single_and_three_pair_finalists(self):
        root = TEST_TMP_ROOT / f"pair_{uuid.uuid4().hex}"
        root.mkdir(parents=True)
        try:
            manifest = root / "manifest.json"
            shortlist = root / "shortlist.csv"
            manifest.write_text("{}\n", encoding="utf-8")
            shortlist.write_text("x\n", encoding="utf-8")
            pool24 = pd.DataFrame([
                {"rank": index + 1, "ticker": f"T{index:02d}"}
                for index in range(24)
            ])
            finalists = pd.DataFrame([
                {
                    "profile_id": f"pair_{index}",
                    "omitted_ticker_1": f"T{index:02d}",
                    "omitted_ticker_2": f"T{index + 3:02d}",
                    "analysis_role": f"role_{index}",
                }
                for index in range(3)
            ])

            spec = stage7_sensitivity_spec(
                source_manifest_path=manifest,
                shortlist_path=shortlist,
                pool24=pool24,
                contract={"incumbent_top1": 0.16, "incumbent_top3": 0.44},
                finalist_rows=finalists,
                best_single_ticker="T10",
            )

            profiles = spec["phases"][0]["construction_profiles"]
            self.assertEqual(len(profiles), 5)
            self.assertEqual(spec["phases"][0]["sweep"]["lookback_years"], [1, 2, 3])
            self.assertEqual(spec["phases"][0]["sweep"]["trade_cost_bps"], [5, 10, 25])
            self.assertFalse(spec["phases"][1]["enabled"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
