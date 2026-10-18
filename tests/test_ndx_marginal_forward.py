from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.ndx_marginal_forward import (
    NdxMarginalForwardError,
    append_cohort_index,
    build_cohort_curve_points,
    build_maturity_summary,
    evaluate_cohort,
    load_forward_spec,
    read_cohort_index,
)


ROOT = Path(__file__).resolve().parents[1]


class NdxMarginalForwardTests(unittest.TestCase):
    def test_spec_locks_stage1_and_stage2_stays_disabled(self):
        spec = load_forward_spec(ROOT / "config/ndx_marginal_forward_v1.yaml")
        self.assertEqual(spec["selection_contract"]["candidate_share_of_new_money"], [0.0, 0.05, 0.10, 0.15])
        self.assertEqual(spec["evaluation_contract"]["primary_horizon_trading_days"], 126)
        self.assertEqual(spec["evaluation_contract"]["contribution_start_offsets_months"], [0, 1, 2, 3, 4, 5])
        self.assertFalse(spec["stage_2_unlock"]["enabled"])

    def test_hash_chain_is_idempotent_and_rejects_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.jsonl"
            first = append_cohort_index(path, {"observation_date": "2026-07-13", "value": 1})
            repeated = append_cohort_index(path, {"observation_date": "2026-07-13", "value": 1})
            self.assertEqual(first, repeated)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)
            with self.assertRaises(NdxMarginalForwardError):
                append_cohort_index(path, {"observation_date": "2026-07-13", "value": 2})
            row = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(row["record_sha256"])
            self.assertEqual(read_cohort_index(path), [row])

    def test_maturity_evaluation_is_paired_with_same_incumbent_curve(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dates = pd.bdate_range("2026-07-13", periods=25)
            for ticker, growth in (("AAA", 1.24), ("BBB", 1.12)):
                close = pd.Series(range(25), dtype=float).map(lambda i: 100.0 * (1.0 + (growth - 1.0) * i / 24.0))
                pd.DataFrame({"Date": dates, "Open": [100.0] * 25, "Close": close}).to_csv(root / f"{ticker}.csv", index=False)
            incumbent_weights = json.dumps({"AAA": 1.0}, separators=(",", ":"))
            cohort = pd.DataFrame([
                {"observation_date": "2026-07-13", "action_id": "control_00pct", "ticker": "", "risk_chain": "", "target_candidate_share": 0.0, "cohort_fresh_oos_eligible": True, "execution_claim_allowed": False, "incumbent_weights_json": incumbent_weights},
                {"observation_date": "2026-07-13", "action_id": "BBB_10pct", "ticker": "BBB", "risk_chain": "test", "target_candidate_share": 0.10, "cohort_fresh_oos_eligible": True, "execution_claim_allowed": False, "incumbent_weights_json": incumbent_weights},
            ])
            target = pd.DataFrame(
                {"Close": pd.Series(range(25), index=dates, dtype=float).map(lambda i: 100.0 + i * 0.5)}
            )
            result = evaluate_cohort(
                cohort, price_cache_dir=root, horizons=[21, 63],
                transaction_cost_bps=10.0, target_nav=target,
            )
            mature = result.loc[result["horizon_trading_days"].eq(21)]
            self.assertTrue(mature["mature"].all())
            control = mature.loc[mature["action_id"].eq("control_00pct")].iloc[0]
            candidate = mature.loc[mature["action_id"].eq("BBB_10pct")].iloc[0]
            self.assertAlmostEqual(control["return_delta_vs_incumbent"], 0.0)
            self.assertLess(candidate["return_delta_vs_incumbent"], 0.0)
            self.assertEqual(candidate["entry_date"], "2026-07-13")
            self.assertTrue(candidate["target_mature"])
            self.assertIsNotNone(candidate["return_delta_vs_target"])
            interim = result.loc[
                result["action_id"].eq("BBB_10pct")
                & result["horizon_trading_days"].eq(63)
            ].iloc[0]
            self.assertEqual(interim["status"], "WAITING_FOR_MATURITY")
            self.assertIsNotNone(interim["interim_return_delta_vs_incumbent"])
            self.assertFalse(interim["interim_is_admission_evidence"])

            curves = build_cohort_curve_points(
                cohort,
                price_cache_dir=root,
                transaction_cost_bps=10.0,
                target_nav=target,
                primary_horizon=21,
            )
            self.assertEqual(len(curves), 50)
            self.assertEqual(set(curves["evidence_role"]), {
                "FORWARD_CURVE_MONITORING_ONLY_NOT_ADMISSION_EVIDENCE"
            })
            candidate_curve = curves.loc[curves["action_id"].eq("BBB_10pct")]
            self.assertEqual(candidate_curve["curve_session"].tolist(), list(range(1, 26)))
            self.assertTrue(candidate_curve["mature_primary"].all())
            self.assertTrue(candidate_curve["target_012922_nav"].notna().all())

    def test_distributions_are_withheld_before_twelve_fresh_primary_cohorts(self):
        evaluations = pd.DataFrame([
            {"observation_date": "2026-07-13", "action_id": "AAA_10pct", "horizon_trading_days": 126, "mature": True, "fresh_oos_eligible": True, "return_delta_vs_incumbent": 0.01, "dd_cost_vs_incumbent": 0.002}
        ])
        summary = build_maturity_summary(evaluations, primary_horizon=126, minimum_windows=12)
        self.assertEqual(summary.iloc[0]["admission_status"], "INSUFFICIENT_FRESH_PRIMARY_COHORTS")
        self.assertTrue(pd.isna(summary.iloc[0]["return_delta_p50"]))
        self.assertFalse(summary.iloc[0]["stage_2_unlocked"])

    def test_real_stage1_control_does_not_become_nan_ticker(self):
        from backtest.ndx_marginal_forward import build_cohort

        cohort, manifest = build_cohort(
            observation_date="2026-07-13",
            shortlist_path=ROOT / "data/cache/research/ndx_v11_current_competition_v1/risk_chain_shortlist.csv",
            actions_path=ROOT / "data/cache/research/ndx_marginal_stage1_v1/allocation_actions.csv",
            config_path=ROOT / "config/config.yaml",
            spec_path=ROOT / "config/ndx_marginal_forward_v1.yaml",
            imported_seed=True,
            registered_date="2026-07-16",
        )
        self.assertEqual(cohort.iloc[0]["ticker"], "")
        self.assertNotIn("nan", set(cohort["ticker"]))
        self.assertEqual(manifest["candidate_count"], 22)

    def test_shortlist_date_must_match_observation_date(self):
        from backtest.ndx_marginal_forward import build_cohort

        with self.assertRaises(NdxMarginalForwardError):
            build_cohort(
                observation_date="2026-07-16",
                shortlist_path=ROOT / "data/cache/research/ndx_v11_current_competition_v1/risk_chain_shortlist.csv",
                actions_path=ROOT / "data/cache/research/ndx_marginal_stage1_v1/allocation_actions.csv",
                config_path=ROOT / "config/config.yaml",
                spec_path=ROOT / "config/ndx_marginal_forward_v1.yaml",
                imported_seed=False,
                registered_date="2026-07-16",
            )


if __name__ == "__main__":
    unittest.main()
