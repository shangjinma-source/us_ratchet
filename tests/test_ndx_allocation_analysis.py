import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.ndx_allocation_analysis import (
    _risk_derived_cap_grid,
    _stage3_spec,
    select_key_allocation_candidates,
)


def _candidate(
    profile_id: str,
    *,
    p50: float,
    p10: float,
    win_rate: float,
    dd50: float,
    dd90: float,
    effective_n: float,
    compliant: bool,
) -> dict:
    return {
        "profile_id": profile_id,
        "lookback_years": 3.0,
        "trade_cost_bps": 10.0,
        "concentration_guard_passed": compliant,
        "incumbent_win_rate": win_rate,
        "incumbent_xirr_p50_margin": p50,
        "incumbent_xirr_p10_margin": p10,
        "incumbent_dd_relief_p50": dd50,
        "incumbent_dd_relief_p90": dd90,
        "effective_n_p10": effective_n,
        "turnover_x_p50": 4.0,
    }


class NdxAllocationAnalysisTests(unittest.TestCase):
    def test_key_candidates_keep_unconstrained_and_compliant_tradeoffs_distinct(self):
        candidates = pd.DataFrame([
            _candidate(
                "return_unconstrained",
                p50=-0.02,
                p10=-0.06,
                win_rate=0.33,
                dd50=0.01,
                dd90=-0.01,
                effective_n=6.0,
                compliant=False,
            ),
            _candidate(
                "tail_unconstrained",
                p50=-0.04,
                p10=-0.04,
                win_rate=0.20,
                dd50=0.02,
                dd90=0.00,
                effective_n=7.0,
                compliant=False,
            ),
            _candidate(
                "return_compliant",
                p50=-0.10,
                p10=-0.15,
                win_rate=0.05,
                dd50=0.03,
                dd90=0.01,
                effective_n=8.0,
                compliant=True,
            ),
            _candidate(
                "drawdown_compliant",
                p50=-0.20,
                p10=-0.25,
                win_rate=0.00,
                dd50=0.05,
                dd90=0.04,
                effective_n=12.0,
                compliant=True,
            ),
        ])

        selected = select_key_allocation_candidates(candidates)

        self.assertEqual(selected.iloc[0]["profile_id"], "return_unconstrained")
        self.assertIn("return_compliant", set(selected["profile_id"]))
        self.assertIn("drawdown_compliant", set(selected["profile_id"]))
        self.assertEqual(
            len(selected[["profile_id", "lookback_years"]].drop_duplicates()),
            len(selected),
        )

    def test_stage3_spec_uses_only_declared_pools_and_risk_derived_cap_grid(self):
        rows = []
        for pool_id, size in (("pool24", 24), ("pool30", 30)):
            for rank in range(1, size + 1):
                rows.append({
                    "shortlist_id": pool_id,
                    "rank": rank,
                    "ticker": f"{pool_id.upper()}_{rank:02d}",
                })
        shortlists = pd.DataFrame(rows)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            shortlist_path = root / "shortlists.csv"
            manifest.write_text("{}", encoding="utf-8")
            shortlists.to_csv(shortlist_path, index=False)
            spec = _stage3_spec(
                manifest,
                shortlist_path,
                shortlists,
                {"top1": 0.16425, "top3": 0.44265, "effective_n": 7.7667},
                baseline_pool_id="pool24",
                baseline_top_n=12,
                baseline_cap=0.20,
            )

        profiles = spec["phases"][0]["construction_profiles"]
        self.assertEqual(len(profiles), 24)
        self.assertEqual(
            {profile["max_weight"] for profile in profiles},
            {0.125, 0.1363, 0.1475, 0.1643, 0.1821, 0.20},
        )
        self.assertEqual({profile["weight_mode"] for profile in profiles}, {"source_weight"})
        self.assertEqual({profile["top_n"] for profile in profiles}, {10, 12})
        self.assertEqual(
            spec["analysis_contract"]["cap_grid_policy"],
            "incumbent_envelope_interpolation_v1",
        )

    def test_cap_grid_is_derived_from_incumbent_envelope(self):
        caps = _risk_derived_cap_grid(
            {
                "top1": 0.16425389755011136,
                "top3": 0.44265033407572385,
                "effective_n": 7.766701539921048,
            },
            0.20,
        )

        self.assertEqual(caps, [0.125, 0.1363, 0.1476, 0.1643, 0.1821, 0.20])


if __name__ == "__main__":
    unittest.main()
