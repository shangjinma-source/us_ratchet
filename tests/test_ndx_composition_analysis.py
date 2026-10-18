from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

import pandas as pd

from backtest.ndx_composition_analysis import (
    ablation_effects,
    stage6_pair_search_spec,
)


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / "data" / "cache" / "test_tmp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


def _candidate(profile_id: str, p50: float, p10: float) -> dict:
    return {
        "profile_id": profile_id,
        "lookback_years": 3.0,
        "trade_cost_bps": 10.0,
        "concentration_guard_passed": True,
        "incumbent_win_rate": 0.3,
        "incumbent_xirr_p50_margin": p50,
        "incumbent_xirr_p10_margin": p10,
        "incumbent_dd_relief_p50": 0.02,
        "incumbent_dd_relief_p90": 0.01,
        "turnover_x_p50": 5.0,
    }


class NdxCompositionAnalysisTests(unittest.TestCase):
    def test_pair_seed_rule_requires_both_rollups_and_majority_windows(self):
        baseline_id = "baseline"
        candidates = pd.DataFrame([
            _candidate(baseline_id, -0.08, -0.13),
            _candidate("pool23__without_aaa", -0.05, -0.10),
            _candidate("pool23__without_bbb", -0.04, -0.14),
        ])
        windows = []
        for start_index in range(4):
            start = f"2022-0{start_index + 1}-01"
            for profile_id, margin in (
                (baseline_id, -0.08),
                ("pool23__without_aaa", -0.05 if start_index < 3 else -0.09),
                ("pool23__without_bbb", -0.04),
            ):
                windows.append({
                    "profile_id": profile_id,
                    "lookback_years": 3.0,
                    "trade_cost_bps": 10.0,
                    "start": start,
                    "incumbent_xirr_margin": margin,
                    "incumbent_dd_relief": 0.01,
                    "strategy_xirr": 0.3 + margin,
                    "strategy_maxdd": 0.2,
                    "turnover_x": 5.0,
                })
        shortlist = pd.DataFrame([
            {
                "ticker": ticker,
                "rank": index + 1,
                "sic2": index,
                "sic4": index * 100,
                "sic_description": ticker,
                "sic_division": "test",
                "evidence_score": 1.0 - index / 10,
                "current_strategy_member": False,
            }
            for index, ticker in enumerate(("AAA", "BBB"))
        ])

        effects = ablation_effects(
            candidates,
            pd.DataFrame(windows),
            baseline_profile_id=baseline_id,
            shortlist=shortlist,
        ).set_index("omitted_ticker")

        self.assertTrue(bool(effects.loc["AAA", "pair_search_eligible"]))
        self.assertFalse(bool(effects.loc["BBB", "pair_search_eligible"]))

    def test_stage6_contains_baseline_selected_singles_and_all_pairs(self):
        root = TEST_TMP_ROOT / f"composition_{uuid.uuid4().hex}"
        root.mkdir(parents=True)
        try:
            manifest = root / "manifest.json"
            shortlist_path = root / "shortlist.csv"
            manifest.write_text("{}\n", encoding="utf-8")
            shortlist_path.write_text("x\n", encoding="utf-8")
            pool24 = pd.DataFrame([
                {
                    "rank": index + 1,
                    "ticker": f"T{index:02d}",
                    "sic2": index // 2,
                }
                for index in range(24)
            ])
            selected = ["T00", "T02", "T04", "T06", "T08", "T10"]

            spec = stage6_pair_search_spec(
                source_manifest_path=manifest,
                shortlist_path=shortlist_path,
                pool24=pool24,
                contract={"incumbent_top1": 0.16, "incumbent_top3": 0.44},
                selected_tickers=selected,
            )

            profiles = spec["phases"][0]["construction_profiles"]
            self.assertEqual(len(profiles), 1 + 6 + 15)
            self.assertEqual(len(profiles[0]["candidate_tickers"]), 24)
            self.assertEqual(
                sum(len(profile["candidate_tickers"]) == 23 for profile in profiles),
                6,
            )
            self.assertEqual(
                sum(len(profile["candidate_tickers"]) == 22 for profile in profiles),
                15,
            )
            self.assertFalse(spec["phases"][1]["enabled"])
            self.assertFalse(spec["phases"][2]["enabled"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
