from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

import pandas as pd

from backtest.ndx_cap_frontier_analysis import (
    CONCENTRATION_KEYS,
    adjacent_cap_pairs,
    attach_cost_invariant_concentration,
    stage4_envelope_spec,
)


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / "data" / "cache" / "test_tmp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class NdxCapFrontierAnalysisTests(unittest.TestCase):
    def test_cost_invariant_concentration_is_merged_without_row_loss(self):
        candidates = pd.DataFrame([
            {"profile_id": "pool24__cap-a", "lookback_years": 1.0, "trade_cost_bps": 5.0},
            {"profile_id": "pool24__cap-a", "lookback_years": 1.0, "trade_cost_bps": 25.0},
        ])
        concentration_row = {
            "profile_id": "pool24__cap-a",
            "lookback_years": 1.0,
            **{key: 1.0 for key in CONCENTRATION_KEYS},
        }
        concentration_row["concentration_guard_passed"] = True

        merged = attach_cost_invariant_concentration(
            candidates, pd.DataFrame([concentration_row])
        )

        self.assertEqual(len(merged), 2)
        self.assertEqual(set(merged["profile_pool"]), {"pool24"})
        self.assertTrue(merged["concentration_guard_passed"].all())

    def test_every_adjacent_cap_can_show_the_same_return_risk_tradeoff(self):
        rows = []
        for pool in ("pool24", "pool30"):
            for cap, p50, p10, dd50, dd90 in (
                (0.12, -0.10, -0.15, 0.030, 0.020),
                (0.15, -0.07, -0.12, 0.025, 0.010),
                (0.20, -0.02, -0.06, 0.015, -0.005),
            ):
                rows.append({
                    "profile_pool": pool,
                    "top_n": 12,
                    "lookback_years": 3.0,
                    "trade_cost_bps": 10.0,
                    "max_weight": cap,
                    "incumbent_xirr_p50_margin": p50,
                    "incumbent_xirr_p10_margin": p10,
                    "incumbent_dd_relief_p50": dd50,
                    "incumbent_dd_relief_p90": dd90,
                })

        pairs, summary = adjacent_cap_pairs(pd.DataFrame(rows))

        self.assertEqual(summary["family_paths"], 2)
        self.assertEqual(summary["adjacent_comparisons"], 4)
        self.assertEqual(summary["return_p50_improved"], 4)
        self.assertEqual(summary["return_p10_improved"], 4)
        self.assertEqual(summary["drawdown_p50_worsened"], 4)
        self.assertEqual(summary["drawdown_p90_worsened"], 4)
        self.assertEqual(summary["higher_cap_dominates"], 0)
        self.assertTrue((pairs["upper_cap"] > pairs["lower_cap"]).all())

    def test_stage4_has_two_paired_baselines_and_two_exact_envelopes(self):
        root = TEST_TMP_ROOT / f"cap_{uuid.uuid4().hex}"
        root.mkdir(parents=True)
        try:
            manifest = root / "manifest.json"
            shortlists = root / "shortlists.csv"
            manifest.write_text("{}\n", encoding="utf-8")
            shortlists.write_text("shortlist_id,rank,ticker\n", encoding="utf-8")
            contract = {
                "incumbent_top1": 0.16425389755011136,
                "incumbent_top3": 0.44265033407572385,
                "incumbent_effective_n": 7.766701539921048,
            }
            evidence = {
                "adjacent_comparisons": 180,
                "return_p50_improved": 180,
                "drawdown_p90_worsened": 180,
            }

            spec = stage4_envelope_spec(
                source_manifest_path=manifest,
                shortlist_path=shortlists,
                pool24_tickers=[f"T{index:02d}" for index in range(24)],
                contract=contract,
                evidence_summary=evidence,
            )

            profiles = spec["phases"][0]["construction_profiles"]
            self.assertEqual(len(profiles), 4)
            self.assertEqual(
                spec["analysis_contract"]["baseline_profile_id"],
                profiles[0]["id"],
            )
            self.assertNotIn("top_weight_cap", profiles[0])
            self.assertNotIn("top_weight_cap", profiles[1])
            self.assertEqual(profiles[2]["top_weight_count"], 3)
            self.assertEqual(profiles[2]["top_weight_cap"], contract["incumbent_top3"])
            self.assertNotIn("min_effective_n", profiles[2])
            self.assertEqual(
                profiles[3]["min_effective_n"], contract["incumbent_effective_n"]
            )
            self.assertFalse(spec["phases"][1]["enabled"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
