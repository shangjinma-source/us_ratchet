import unittest
from datetime import datetime, timezone
import json
import tempfile
from pathlib import Path

import pandas as pd

from backtest.ndx_challenger_forward_cohort import (
    NdxChallengerForwardCohortError,
    build_cohort_snapshot,
    expected_monthly_observation,
    next_fresh_monthly_observation,
    observation_liquidity,
    validate_observation,
)
from data.versioning import file_sha256
from scripts.ndx_challenger_forward_cohort import (
    _missing_observation_close_tickers,
    registration_date_for,
    validate_existing_cohort_manifest,
)


def _spec():
    return {
        "schema_version": 1, "status": "PRE_REGISTERED_FORWARD_ONLY_NOT_ADMISSION",
        "registration_date": "2026-07-20", "safe_leg_included": False,
        "external_index_included": False, "personal_off_strategy_positions_included": False,
        "candidate_contract": {
            "active_execution_status": "WHOLE_LOT_REPLAY_COMPLIANT",
            "frozen_entries": [{"candidate_id": "one", "selection_role": "RETURN", "rationale": "test_return"}],
            "failed_controls_preserved": True, "source_roles_are_independent": True,
            "composite_score_used": False, "target_weights_frozen_at_registration": True,
            "historical_whole_lot_shares_are_audit_only": True,
            "future_whole_lot_shares_must_be_resized_from_cohort_cash_and_prior_close": True,
        },
        "forward_contract": {
            "cohort_frequency": "monthly_first_completed_us_trading_session",
            "first_fresh_observation_on_or_after": "2026-07-20",
            "observation_price": "completed_session_close",
            "entry": "first_common_session_open_strictly_after_observation_date",
            "standardized_execution_cash_usd": 5000, "minimum_cash_buffer_usd": 100,
            "primary_horizon_trading_days": 126, "minimum_fresh_mature_cohorts": 12,
            "minimum_distinct_regimes": 2, "selection_date_or_later_data_for_registration_allowed": False,
            "liquidity_lookback_trading_days": 126, "minimum_liquidity_observations": 60,
            "minimum_median_dollar_volume_usd": 50_000_000.0,
        },
        "promotion_contract": {
            "fresh_oos_required": True, "incumbent_p50_p10_and_drawdown_p50_p90_required": True,
            "target_012922_envelope_required": True, "execution_cost_liquidity_and_risk_chain_required": True,
            "today_diff_and_rollback_required": True, "user_confirmation_required": True,
            "promotion_allowed_at_registration": False, "live_mutation_allowed": False,
            "policy_gate": {
                "paired_return_p50_minimum": 0.0, "paired_return_p10_minimum": 0.0,
                "paired_drawdown_cost_p50_maximum": 0.0, "paired_drawdown_cost_p90_maximum": 0.0,
                "target_012922_distance_not_worse_than_original_8": True,
                "require_continuous_and_execution_tracks": True,
                "require_at_least_one_strict_incumbent_improvement": True,
            },
        },
    }


class NdxChallengerForwardCohortTests(unittest.TestCase):
    def test_liquidity_gate_uses_only_observation_date_and_earlier_rows(self):
        dates = pd.date_range("2026-01-01", periods=70, freq="B")
        frame = pd.DataFrame({"Close": 100.0, "Volume": 1_000_000.0}, index=dates)
        frame.loc[dates[-1], "Volume"] = 1.0
        detail = observation_liquidity(
            frame, dates[-2].strftime("%Y-%m-%d"), lookback=126, minimum_observations=60,
        )
        self.assertEqual(detail["liquidity_observations"], 69)
        self.assertEqual(detail["median_dollar_volume_usd"], 100_000_000.0)

    def test_readiness_coverage_requires_every_frozen_ticker_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "A.csv").write_text("Date,Close\n2026-07-20,10\n", encoding="utf-8")
            (root / "B.csv").write_text("Date,Close\n2026-07-17,20\n", encoding="utf-8")
            self.assertEqual(
                _missing_observation_close_tickers(root, ["A", "B", "C"], "2026-07-20"),
                ["B", "C"],
            )

    def test_fresh_registration_date_cannot_be_backdated(self):
        now = datetime(2026, 7, 21, 0, 30, tzinfo=timezone.utc)
        self.assertEqual(
            registration_date_for(imported_seed=False, override=None, now=now),
            "2026-07-20",
        )
        with self.assertRaises(NdxChallengerForwardCohortError):
            registration_date_for(imported_seed=False, override="2026-07-19", now=now)
        self.assertEqual(
            registration_date_for(imported_seed=True, override="2026-07-19", now=now),
            "2026-07-19",
        )

    def test_existing_cohort_manifest_cannot_flip_seed_to_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cohort = root / "cohort.csv"
            positions = root / "positions.csv"
            spec = root / "spec.yaml"
            registry = root / "registry.json"
            cohort.write_text("x\n1\n", encoding="utf-8")
            positions.write_text("x\n1\n", encoding="utf-8")
            spec.write_text("schema_version: 1\n", encoding="utf-8")
            registry.write_text(json.dumps({"ok": True}), encoding="utf-8")
            observation = {
                "observation_date": "2026-07-20", "registered_date": "2026-07-21",
                "cohort_origin": "imported_seed", "fresh_oos_eligible": False,
            }
            manifest = {
                "manifest_type": "ndx_challenger_forward_cohort", **observation,
                "inputs": {
                    "spec": {"path": spec.as_posix(), "sha256": file_sha256(spec)},
                    "registry_manifest": {"path": registry.as_posix(), "sha256": file_sha256(registry)},
                    "registry_content_sha256": "locked",
                },
                "artifacts": {
                    "cohort_candidates": {"path": cohort.as_posix(), "rows": 1, "sha256": file_sha256(cohort)},
                    "cohort_positions": {"path": positions.as_posix(), "rows": 1, "sha256": file_sha256(positions)},
                },
            }
            validate_existing_cohort_manifest(
                manifest, observation=observation, cohort_path=cohort, positions_path=positions,
                cohort_rows=1, position_rows=1, spec_path=spec, registry_path=registry,
                registry_content_sha256="locked",
            )
            manifest["fresh_oos_eligible"] = True
            with self.assertRaises(NdxChallengerForwardCohortError):
                validate_existing_cohort_manifest(
                    manifest, observation=observation, cohort_path=cohort, positions_path=positions,
                    cohort_rows=1, position_rows=1, spec_path=spec, registry_path=registry,
                    registry_content_sha256="locked",
                )

    def test_monthly_anchor_and_fresh_date_gate(self):
        sessions = pd.DatetimeIndex(["2026-07-17", "2026-07-20", "2026-07-21", "2026-08-03"])
        self.assertEqual(expected_monthly_observation(sessions, "2026-07-20"), "2026-07-20")
        result = validate_observation(
            "2026-07-20", "2026-07-20", sessions,
            first_not_before="2026-07-20",
        )
        self.assertTrue(result["fresh_oos_eligible"])
        with self.assertRaises(NdxChallengerForwardCohortError):
            validate_observation("2026-07-21", "2026-07-21", sessions, first_not_before="2026-07-20")
        with self.assertRaises(NdxChallengerForwardCohortError):
            validate_observation("2026-08-03", "2026-07-20", sessions, first_not_before="2026-07-20")

    def test_expired_month_is_skipped_without_fresh_backfill(self):
        sessions = pd.DatetimeIndex([
            "2026-07-20", "2026-07-21", "2026-08-03", "2026-08-04", "2026-09-01",
        ])
        expected, skipped = next_fresh_monthly_observation(
            sessions, "2026-07-20", "2026-08-03",
        )
        self.assertEqual(expected, "2026-08-03")
        self.assertEqual(skipped, ["2026-07-20"])
        result = validate_observation(
            "2026-08-03", "2026-08-03", sessions,
            first_not_before="2026-07-20",
        )
        self.assertTrue(result["fresh_oos_eligible"])
        with self.assertRaises(NdxChallengerForwardCohortError):
            validate_observation(
                "2026-07-20", "2026-08-03", sessions,
                first_not_before="2026-07-20",
            )

    def test_past_date_is_seed_only(self):
        sessions = pd.DatetimeIndex(["2026-07-20"])
        with self.assertRaises(NdxChallengerForwardCohortError):
            validate_observation("2026-07-20", "2026-07-21", sessions, first_not_before="2026-07-20")
        result = validate_observation(
            "2026-07-20", "2026-07-21", sessions,
            first_not_before="2026-07-20", imported_seed=True,
        )
        self.assertFalse(result["fresh_oos_eligible"])

    def test_snapshot_resizes_and_does_not_reuse_historical_shares(self):
        tickers = ["A", "B", "C", "D"]
        active = pd.DataFrame([{
            "registry_entry_id": "FWD_ONE", "candidate_id": "one", "selection_role": "RETURN",
            "action_scope": "VARIABLE_CARDINALITY", "research_track": "portfolio_optimization",
            "holding_count_interpretation": "dynamic_k_portfolio_structure",
            "candidate_tickers": "A;B;C;D", "selection_rationale": "test_dynamic_k_return",
            "frozen_target_weights": "A:0.25;B:0.25;C:0.25;D:0.25",
            "historical_execution_audit_shares": "A:999;B:999;C:999;D:999",
        }])
        risk_map = pd.DataFrame([
            {"registry_entry_id": "FWD_ONE", "ticker": ticker, "risk_chain": f"chain_{ticker}"}
            for ticker in tickers
        ])
        baseline = pd.DataFrame([{
            "ticker": ticker, "frozen_weight": 0.25,
            "issuer_id": f"issuer_{ticker}", "risk_chain": f"chain_{ticker}",
        } for ticker in tickers])
        cohort, positions = build_cohort_snapshot(
            active, risk_map, baseline, {ticker: 100.0 for ticker in tickers},
            {ticker: 100_000_000.0 for ticker in tickers}, _spec(),
            {"observation_date": "2026-07-20", "registered_date": "2026-07-20", "cohort_origin": "same_day_registration", "fresh_oos_eligible": True},
        )
        self.assertEqual(len(cohort), 2)
        self.assertTrue(cohort["future_entry_price_read"].eq(False).all())
        challenger = cohort.loc[cohort["track_role"].eq("CHALLENGER")].iloc[0]
        self.assertEqual(challenger["research_track"], "portfolio_optimization")
        self.assertEqual(challenger["holding_count_interpretation"], "dynamic_k_portfolio_structure")
        self.assertEqual(int(challenger["holding_count"]), 4)
        self.assertTrue(positions.loc[positions["track_role"].eq("CHALLENGER"), "research_track"].eq("portfolio_optimization").all())
        self.assertTrue(positions["historical_audit_shares_reused"].eq(False).all())
        self.assertTrue((positions["cohort_whole_lot_shares"] < 999).all())
        self.assertFalse(cohort["promotion_allowed"].any())

    def test_track_identity_mismatch_fails_closed(self):
        active = pd.DataFrame([{
            "registry_entry_id": "FWD_ONE", "candidate_id": "one", "selection_role": "RETURN",
            "action_scope": "VARIABLE_CARDINALITY", "research_track": "migration_control",
            "holding_count_interpretation": "frozen_incumbent_migration_action_not_target_cardinality",
            "candidate_tickers": "A", "selection_rationale": "invalid",
            "frozen_target_weights": "A:1.0",
        }])
        risk_map = pd.DataFrame([{"registry_entry_id": "FWD_ONE", "ticker": "A", "risk_chain": "chain_A"}])
        baseline = pd.DataFrame([{"ticker": "A", "frozen_weight": 1.0, "issuer_id": "issuer_A", "risk_chain": "chain_A"}])
        with self.assertRaisesRegex(NdxChallengerForwardCohortError, "track identity mismatch"):
            build_cohort_snapshot(
                active, risk_map, baseline, {"A": 10.0}, {"A": 100_000_000.0}, _spec(),
                {"observation_date": "2026-07-20", "registered_date": "2026-07-20", "cohort_origin": "fresh", "fresh_oos_eligible": True},
            )

    def test_snapshot_liquidity_failure_is_not_execution_compliant(self):
        tickers = ["A", "B", "C", "D"]
        active = pd.DataFrame([{
            "registry_entry_id": "FWD_ONE", "candidate_id": "one", "selection_role": "RETURN",
            "action_scope": "VARIABLE_CARDINALITY", "research_track": "portfolio_optimization",
            "holding_count_interpretation": "dynamic_k_portfolio_structure",
            "candidate_tickers": ";".join(tickers), "selection_rationale": "test_dynamic_k_return",
            "frozen_target_weights": ";".join(f"{ticker}:0.25" for ticker in tickers),
        }])
        risk_map = pd.DataFrame([
            {"registry_entry_id": "FWD_ONE", "ticker": ticker, "risk_chain": f"chain_{ticker}"}
            for ticker in tickers
        ])
        baseline = pd.DataFrame([{
            "ticker": ticker, "frozen_weight": 0.25,
            "issuer_id": f"issuer_{ticker}", "risk_chain": f"chain_{ticker}",
        } for ticker in tickers])
        liquidity = {ticker: 100_000_000.0 for ticker in tickers}
        liquidity["D"] = 49_999_999.0
        cohort, _ = build_cohort_snapshot(
            active, risk_map, baseline, {ticker: 100.0 for ticker in tickers}, liquidity, _spec(),
            {"observation_date": "2026-07-20", "registered_date": "2026-07-20", "cohort_origin": "fresh", "fresh_oos_eligible": True},
        )
        challenger = cohort.loc[cohort["track_role"].eq("CHALLENGER")].iloc[0]
        self.assertEqual(challenger["execution_track_status"], "COHORT_WHOLE_LOT_NONCOMPLIANT")
        self.assertIn("median_dollar_volume", challenger["execution_constraint_failures"])


if __name__ == "__main__":
    unittest.main()
