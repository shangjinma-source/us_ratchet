import unittest

import numpy as np
import pandas as pd

from backtest.ndx_staged_search import _balanced_shortlists, _stage2_profiles


class NdxStagedSearchTests(unittest.TestCase):
    def _ranking(self, count: int = 30) -> pd.DataFrame:
        rows = []
        for index in range(count):
            rows.append({
                "rank": index + 1,
                "ticker": f"T{index:02d}",
                "issuer_key": f"I{index:02d}",
                "sic2": f"{index // 2:02d}",
                "sic_description": f"sector {index // 2}",
                "membership_date_coverage": 1.0,
                "selected_rule_family_count": 5,
                "selected_lookback_count": 3,
                "forward_observations": 20,
                "forward_horizon_count": 2,
                "evidence_score": 1.0 - index / 100.0,
            })
        return pd.DataFrame(rows)

    def test_balanced_shortlists_obey_sector_and_point_in_time_coverage(self):
        ranking = self._ranking()
        universes = {
            "2022-01-11": set(ranking["ticker"]),
            "2023-01-11": set(ranking["ticker"]),
        }
        contract = {
            "shortlist_min_membership_date_rate": 0.50,
            "shortlist_min_rule_families": 2,
            "shortlist_min_lookbacks": 2,
        }

        pools, summary = _balanced_shortlists(
            ranking,
            universes,
            contract,
            sizes=(18, 24),
            max_per_sic2=2,
            required_top_n=12,
        )

        self.assertEqual(set(summary["shortlist_size"]), {18, 24})
        self.assertTrue(
            (pools.groupby(["shortlist_id", "sic2"]).size() <= 2).all()
        )
        self.assertTrue((summary["minimum_point_in_time_members"] >= 12).all())

    def test_stage2_profiles_freeze_pool_and_only_vary_declared_dimensions(self):
        pool = self._ranking(18).assign(
            shortlist_id="pool18",
            shortlist_size=18,
            shortlist_max_per_sic2=2,
        )

        profiles = _stage2_profiles(pool)

        self.assertEqual(len(profiles), 80)
        self.assertEqual(len({profile["id"] for profile in profiles}), 80)
        expected = pool.sort_values("rank")["ticker"].tolist()
        self.assertTrue(all(profile["candidate_tickers"] == expected for profile in profiles))
        self.assertEqual({profile["safe_weight"] for profile in profiles}, {0.26})
        self.assertEqual({profile["rebalance_months"] for profile in profiles}, {6})
        self.assertEqual({profile["top_n"] for profile in profiles}, {6, 8, 10, 12})


if __name__ == "__main__":
    unittest.main()
