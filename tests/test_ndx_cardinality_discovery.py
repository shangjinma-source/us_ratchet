import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from backtest.ndx_cardinality_discovery import (
    NdxCardinalityDiscoveryError,
    _bounded_issuer_unique_beam_combos,
    _window_metrics,
    build_point_in_time_taxonomy_panel,
    build_training_job_plan,
    constrained_fixed_shrinkage_weights,
    evaluate_synthetic_portfolio,
    load_discovery_spec,
    monthly_selection_dates,
    pareto_mask,
    point_in_time_cardinality_readiness,
    point_in_time_track_memberships,
    read_synthetic_checkpoint,
    search_two_stage_cardinality,
    search_synthetic_cardinality,
    select_multifrontier_security_sets,
    synthetic_fixture,
    synthetic_run_fingerprint,
    validate_checkpoint_coordinate,
    validate_discovery_spec,
    write_synthetic_checkpoint,
)
from data.versioning import file_sha256
from scripts.ndx_cardinality_discovery import build_synthetic_smoke


ROOT = Path(__file__).resolve().parents[1]


class NdxCardinalityDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_discovery_spec(ROOT / "config" / "ndx_cardinality_discovery_v1.yaml")

    def test_spec_forbids_backfill_and_promotion(self):
        self.assertTrue(validate_discovery_spec(self.spec)["passed"])
        self.assertFalse(self.spec["point_in_time_contract"]["current_taxonomy_backfill_allowed"])
        self.assertFalse(self.spec["promotion_allowed"])

    def test_backfill_enabled_is_rejected(self):
        changed = copy.deepcopy(self.spec)
        changed["point_in_time_contract"]["current_taxonomy_backfill_allowed"] = True
        with self.assertRaises(NdxCardinalityDiscoveryError):
            validate_discovery_spec(changed)

    def test_monthly_calendar_uses_first_observed_trading_day(self):
        dates = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-02-02"])
        result = monthly_selection_dates(dates, "2026-01-01", "2026-02-28")
        self.assertEqual([item.date().isoformat() for item in result], ["2026-01-02", "2026-02-02"])

    def test_evidence_date_controls_each_cardinality_window(self):
        universe = pd.DataFrame([
            {"ticker": "A", "security_id": "s1", "issuer_id": "i1", "evidence_available_date": "2026-01-01", "strict_technology_eligible": True},
            {"ticker": "B", "security_id": "s2", "issuer_id": "i2", "evidence_available_date": "2026-02-01", "strict_technology_eligible": True},
        ])
        calendar = pd.date_range("2026-01-01", periods=80, freq="B")
        selections = [pd.Timestamp("2026-01-02"), pd.Timestamp("2026-02-02")]
        windows, coverage = point_in_time_cardinality_readiness(
            universe, selections, calendar, track="strict_technology",
            horizon_days=5, minimum_windows=1,
        )
        self.assertEqual(windows["available_issuer_count"].tolist(), [1, 2])
        by_k = coverage.set_index("holding_count")
        self.assertEqual(by_k.loc[1, "mature_window_count"], 2)
        self.assertEqual(by_k.loc[2, "mature_window_count"], 1)
        self.assertTrue(bool(by_k.loc[2, "training_evaluation_ready"]))

    def test_event_gap_scope_is_attributed_and_excluded_per_selection_window(self):
        universe = pd.DataFrame([
            {"ticker": "A", "security_id": "s1", "issuer_id": "i1", "evidence_available_date": "2026-01-01", "strict_technology_eligible": True},
            {"ticker": "B", "security_id": "s2", "issuer_id": "i2", "evidence_available_date": "2026-01-01", "strict_technology_eligible": True},
        ])
        gaps = pd.DataFrame([{
            "case_id": "gap_february", "ticker": "B",
            "blocked_selection_start": "2026-02-01", "blocked_selection_end": "2026-02-28",
            "status": "locked_blocker", "promotion_allowed": False, "evidence_match": True,
        }])
        calendar = pd.date_range("2026-01-01", periods=80, freq="B")
        selections = [pd.Timestamp("2026-01-02"), pd.Timestamp("2026-02-02")]
        windows, coverage = point_in_time_cardinality_readiness(
            universe, selections, calendar, track="strict_technology",
            horizon_days=5, minimum_windows=2, event_gap_scope=gaps,
        )
        february = windows.set_index("selection_date").loc["2026-02-02"]
        self.assertTrue(bool(february["event_gap_blocked"]))
        self.assertEqual(february["event_gap_case_ids"], "gap_february")
        self.assertFalse(bool(february["membership_window_eligible"]))
        by_k = coverage.set_index("holding_count")
        self.assertEqual(by_k.loc[2, "raw_mature_window_count_before_event_gap_exclusion"], 2)
        self.assertEqual(by_k.loc[2, "event_gap_blocked_mature_window_count"], 1)
        self.assertEqual(by_k.loc[2, "mature_window_count"], 1)
        self.assertFalse(bool(by_k.loc[2, "training_evaluation_ready"]))

    def test_taxonomy_panel_uses_latest_global_membership_snapshot(self):
        records = pd.DataFrame([
            {
                "ticker": "A", "security_id": "s1", "issuer_id": "i1",
                "selection_dates": "2026-01-31", "risk_chain": "eda_ip",
                "evidence_available_date": "2026-01-01", "status": "accepted",
            },
            {
                "ticker": "B", "security_id": "s2", "issuer_id": "i2",
                "selection_dates": "2026-02-28", "risk_chain": "consumer",
                "evidence_available_date": "", "status": "unclassified",
            },
        ])
        plan = {
            "universe_tracks": {
                "strict_technology": {"accepted_risk_chains": ["eda_ip"]},
                "technology_plus_adjacent": {
                    "inherits": "strict_technology", "additional_risk_chains": ["automotive"],
                },
            }
        }
        panel = build_point_in_time_taxonomy_panel(records, plan)
        calendar = pd.date_range("2026-02-01", periods=60, freq="B")
        windows, _ = point_in_time_cardinality_readiness(
            panel, [pd.Timestamp("2026-02-02"), pd.Timestamp("2026-03-02")], calendar,
            track="strict_technology", horizon_days=5, minimum_windows=1,
        )
        self.assertEqual(windows["available_issuer_count"].tolist(), [1, 0])
        self.assertEqual(
            windows["membership_snapshot_date"].tolist(), ["2026-01-31", "2026-02-28"]
        )

    def test_taxonomy_panel_rejects_duplicate_security_snapshot(self):
        records = pd.DataFrame([
            {
                "ticker": ticker, "security_id": "s1", "issuer_id": "i1",
                "selection_dates": "2026-01-31", "risk_chain": "eda_ip",
                "evidence_available_date": "2026-01-01", "status": "accepted",
            }
            for ticker in ("A", "A2")
        ])
        plan = {
            "universe_tracks": {
                "strict_technology": {"accepted_risk_chains": ["eda_ip"]},
                "technology_plus_adjacent": {
                    "inherits": "strict_technology", "additional_risk_chains": [],
                },
            }
        }
        with self.assertRaises(NdxCardinalityDiscoveryError):
            build_point_in_time_taxonomy_panel(records, plan)

    def test_price_ticker_lifecycle_is_resolved_on_selection_date(self):
        panel = pd.DataFrame([{
            "ticker": "META", "taxonomy_ticker_aliases": "FB;META",
            "security_id": "s1", "issuer_id": "i1", "cik": "1326801",
            "cusip": "30303M102", "membership_snapshot_date": "2022-02-26",
            "risk_chain": "platform_advertising", "evidence_available_date": "2022-02-04",
            "strict_technology_eligible": True,
        }])
        lifecycle = {
            "schema_version": 1,
            "rules": [{
                "rule_id": "meta_fb_to_meta_2022", "cik": "0001326801",
                "cusip": "30303M102", "recognized_tickers": ["FB", "META"],
                "intervals": [
                    {"effective_to": "2022-06-08", "price_ticker": "FB"},
                    {"effective_from": "2022-06-09", "price_ticker": "META"},
                ],
            }],
        }
        result = point_in_time_track_memberships(
            panel, [pd.Timestamp("2022-03-01"), pd.Timestamp("2022-07-01")],
            track="strict_technology", ticker_lifecycle=lifecycle,
        )
        self.assertEqual(result["ticker"].tolist(), ["FB", "META"])
        self.assertTrue(result["price_ticker_resolution"].eq("reviewed_ticker_lifecycle").all())

    def test_training_job_plan_only_uses_ready_mature_coordinates(self):
        memberships = pd.DataFrame([
            {
                "universe_track": "strict_technology", "selection_date": "2026-01-02",
                "ticker": ticker, "security_id": security, "issuer_id": issuer,
                "risk_chain": "eda_ip", "membership_window_eligible": True,
            }
            for ticker, security, issuer in (("A", "s1", "i1"), ("B", "s2", "i2"))
        ])
        windows = pd.DataFrame([{
            "universe_track": "strict_technology", "selection_date": "2026-01-02",
            "membership_window_eligible": True,
        }])
        coverage = pd.DataFrame([
            {"universe_track": "strict_technology", "holding_count": 1, "training_evaluation_ready": True},
            {"universe_track": "strict_technology", "holding_count": 2, "training_evaluation_ready": True},
            {"universe_track": "strict_technology", "holding_count": 3, "training_evaluation_ready": False},
        ])
        jobs = build_training_job_plan(memberships, windows, coverage, exact_limit=1)
        self.assertEqual(jobs["holding_count"].tolist(), [1, 2])
        self.assertEqual(
            jobs["planned_search_method"].tolist(),
            ["MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND", "EXACT_ENUMERATION"],
        )
        self.assertTrue(jobs["execution_status"].str.startswith("DRY_RUN_BLOCKED").all())

    def test_exact_search_covers_all_issuer_unique_portfolios(self):
        universe, returns, target, incumbent = synthetic_fixture(seed=7, business_days=180)
        frame, audit = search_synthetic_cardinality(
            universe, returns, target, incumbent, holding_count=2,
            exact_limit=100, beam_width=4, window_days=42, step_days=21,
            transaction_cost_bps=10,
        )
        issuer = universe.set_index("ticker")["issuer_id"].to_dict()
        self.assertTrue(audit["search_exhaustive"])
        self.assertEqual(audit["fully_evaluated_portfolios"], 14)
        self.assertEqual(audit["unevaluated_feasible_portfolios"], 0)
        for tickers in frame["tickers"]:
            names = tickers.split(";")
            self.assertEqual(len({issuer[name] for name in names}), len(names))

    def test_bounded_search_reports_unsearched_space_without_optimal_claim(self):
        universe, returns, target, incumbent = synthetic_fixture(seed=7, business_days=180)
        frame, audit = search_synthetic_cardinality(
            universe, returns, target, incumbent, holding_count=2,
            exact_limit=10, beam_width=4, window_days=42, step_days=21,
            transaction_cost_bps=10,
        )
        self.assertFalse(audit["search_exhaustive"])
        self.assertFalse(audit["optimality_claim_allowed"])
        self.assertEqual(
            audit["search_mode"], "MULTIOBJECTIVE_DETERMINISTIC_BEAM_APPROXIMATION"
        )
        self.assertEqual(
            audit["bounded_prefix_objectives"],
            ["RETURN", "BAD_TAIL", "DRAWDOWN", "012922_DISTANCE"],
        )
        self.assertFalse(audit["mathematical_bound_certificate_available"])
        self.assertGreater(audit["unevaluated_feasible_portfolios"], 0)
        self.assertEqual(audit["result_label"], "SYNTHETIC_CURRENT_SEARCHED_FRONTIER")
        self.assertTrue(frame["frontier_tags"].str.contains("PARETO").any())

    def test_bounded_beam_keeps_only_prefixes_that_can_reach_target_k(self):
        tickers = list("ABCDEF")
        universe = pd.DataFrame({
            "ticker": tickers,
            "issuer_id": [f"issuer-{ticker}" for ticker in tickers],
        })
        # Later alphabetic names deliberately have better partial scores.  A
        # width-one beam without completion pruning selects F at depth one and
        # becomes empty before reaching k=5.
        returns = pd.DataFrame({
            ticker: [float(index)] * 10 for index, ticker in enumerate(tickers)
        })
        combos, _, _ = _bounded_issuer_unique_beam_combos(
            universe, returns, holding_count=5, beam_width=1, fit_days=5,
        )
        self.assertEqual(len(combos), 1)
        self.assertEqual(len(combos[0]), 5)
        self.assertEqual(len(set(combos[0])), 5)

    def test_two_stage_search_reports_unsearched_weight_space(self):
        universe, returns, target, incumbent = synthetic_fixture(seed=18, business_days=180)
        frame, shortlist, audit = search_two_stage_cardinality(
            universe, returns, target, incumbent, holding_count=2,
            exact_limit=100, beam_width=8, window_days=42, step_days=21,
            transaction_cost_bps=10, second_stage_per_frontier=1,
            second_stage_weight_specs=("constrained_fixed_shrinkage",), fit_days=63,
        )
        self.assertEqual(audit["first_stage_security_sets"], 14)
        self.assertGreater(len(shortlist), 0)
        self.assertLess(len(shortlist), audit["first_stage_security_sets"])
        self.assertEqual(
            audit["weight_space_unevaluated_security_sets"],
            audit["first_stage_security_sets"] - len(shortlist),
        )
        self.assertFalse(audit["optimality_claim_allowed"])
        self.assertEqual(audit["second_stage_failed_evaluations"], 0)
        self.assertIn("second_stage_failure_count", shortlist.columns)
        self.assertEqual(len(frame), 14 + len(shortlist))
        self.assertTrue(frame["second_stage_selection_tags"].ne("").any())

    def test_multifrontier_shortlist_is_deterministic(self):
        frame = pd.DataFrame([
            {"tickers": "A;B", "weight_spec": "equal_weight", "return_p50": 3, "return_p10": 0, "max_drawdown_p90": 3, "target_012922_distance": 3},
            {"tickers": "A;C", "weight_spec": "equal_weight", "return_p50": 2, "return_p10": 3, "max_drawdown_p90": 2, "target_012922_distance": 2},
            {"tickers": "B;C", "weight_spec": "equal_weight", "return_p50": 1, "return_p10": 1, "max_drawdown_p90": 1, "target_012922_distance": 1},
        ])
        first = select_multifrontier_security_sets(frame, per_frontier_limit=1)
        second = select_multifrontier_security_sets(frame.sample(frac=1, random_state=7), per_frontier_limit=1)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(set(first["tickers"]), {"A;B", "A;C", "B;C"})

    def test_liquidity_pruning_is_separate_from_issuer_theoretical_space(self):
        universe, returns, target, incumbent = synthetic_fixture(seed=8, business_days=180)
        universe.loc[universe["ticker"].eq("EPSI"), "median_dollar_volume_usd"] = 1.0
        frame, audit = search_synthetic_cardinality(
            universe, returns, target, incumbent, holding_count=1,
            exact_limit=100, beam_width=4, window_days=42, step_days=21,
            transaction_cost_bps=10, minimum_median_dollar_volume_usd=50_000_000.0,
        )
        self.assertEqual(audit["theoretical_feasible_portfolios"], 6)
        self.assertEqual(audit["liquidity_feasible_portfolios"], 5)
        self.assertEqual(audit["liquidity_pruned_portfolios"], 1)
        self.assertFalse(frame["tickers"].eq("EPSI").any())

    def test_pareto_mask_rejects_a_dominated_row(self):
        frame = pd.DataFrame([
            {"return_p50": 2, "return_p10": 2, "max_drawdown_p50": 1, "max_drawdown_p90": 1, "target_012922_distance": 1, "turnover": 1},
            {"return_p50": 1, "return_p10": 1, "max_drawdown_p50": 2, "max_drawdown_p90": 2, "target_012922_distance": 2, "turnover": 2},
        ])
        self.assertEqual(pareto_mask(frame).tolist(), [True, False])

    def test_drawdown_includes_first_day_loss_from_initial_nav(self):
        _, drawdowns = _window_metrics(pd.Series([-0.10, 0.0, 0.0]), 3, 1)
        self.assertAlmostEqual(drawdowns[0], 0.10)

    def test_modeled_entry_cost_reduces_frontier_return(self):
        universe, returns, target, incumbent = synthetic_fixture(seed=9, business_days=180)
        no_cost = evaluate_synthetic_portfolio(
            ("ALFA", "GAMM"), universe, returns, target, incumbent,
            window_days=42, step_days=21, transaction_cost_bps=0,
        )
        with_cost = evaluate_synthetic_portfolio(
            ("ALFA", "GAMM"), universe, returns, target, incumbent,
            window_days=42, step_days=21, transaction_cost_bps=1000,
        )
        self.assertLess(with_cost["return_p50"], no_cost["return_p50"])
        self.assertEqual(with_cost["return_basis"], "NET_OF_MODELED_ENTRY_TURNOVER_COST")
        self.assertGreater(with_cost["initial_turnover"], 0)
        self.assertGreater(with_cost["initial_transaction_cost"], 0)

    def test_fixed_shrinkage_weights_are_constrained_and_future_blind(self):
        _, returns, _, _ = synthetic_fixture(seed=11, business_days=220)
        combo = ("ALFA", "BETA", "GAMM", "EPSI")
        history = returns.iloc[:126].copy()
        first = constrained_fixed_shrinkage_weights(
            history, combo, shrinkage_intensity=0.35,
            max_single_weight=0.45, min_single_weight=0.05,
            top_weight_cap=0.80, minimum_effective_n_ratio=0.70,
        )
        mutated = returns.copy()
        mutated.iloc[126:, :] = mutated.iloc[126:, :] * -50.0
        second = constrained_fixed_shrinkage_weights(
            mutated.iloc[:126], combo, shrinkage_intensity=0.35,
            max_single_weight=0.45, min_single_weight=0.05,
            top_weight_cap=0.80, minimum_effective_n_ratio=0.70,
        )
        pd.testing.assert_series_equal(first, second)
        self.assertAlmostEqual(float(first.sum()), 1.0)
        self.assertLessEqual(float(first.max()), 0.45 + 1e-9)
        self.assertGreaterEqual(1.0 / float((first ** 2).sum()), 2.8 - 1e-9)

    def test_shrinkage_projection_uses_an_independent_risk_chain_cap(self):
        universe, returns, _, _ = synthetic_fixture(seed=12, business_days=220)
        chains = universe.set_index("ticker")["risk_chain"].to_dict()
        combo = ("ALFA", "BETA", "GAMM", "EPSI")
        weights = constrained_fixed_shrinkage_weights(
            returns.iloc[:126], combo, shrinkage_intensity=0.35,
            max_single_weight=0.45, min_single_weight=0.05,
            top_weight_cap=0.80, minimum_effective_n_ratio=0.70,
            risk_chain_by_ticker=chains, risk_chain_top1_cap=0.55,
        )
        self.assertLessEqual(float(weights[["ALFA", "BETA"]].sum()), 0.55 + 1e-9)
        self.assertFalse(bool(weights.attrs["risk_chain_projection_relaxed"]))

    def test_infeasible_risk_chain_cap_is_relaxed_but_not_hidden(self):
        universe, returns, _, _ = synthetic_fixture(seed=12, business_days=220)
        chains = universe.set_index("ticker")["risk_chain"].to_dict()
        weights = constrained_fixed_shrinkage_weights(
            returns.iloc[:126], ("ALFA", "BETA"), shrinkage_intensity=0.35,
            max_single_weight=0.60, min_single_weight=0.05,
            top_weight_cap=0.80, minimum_effective_n_ratio=0.70,
            risk_chain_by_ticker=chains, risk_chain_top1_cap=0.55,
        )
        self.assertAlmostEqual(float(weights.sum()), 1.0)
        self.assertTrue(bool(weights.attrs["risk_chain_projection_relaxed"]))

    def test_small_k_shrinkage_uses_structurally_feasible_projection_cap(self):
        universe, returns, _, _ = synthetic_fixture(seed=12, business_days=220)
        chains = universe.set_index("ticker")["risk_chain"].to_dict()
        weights = constrained_fixed_shrinkage_weights(
            returns.iloc[:126], ("ALFA", "GAMM"), shrinkage_intensity=0.35,
            max_single_weight=0.45, min_single_weight=0.05,
            top_weight_cap=0.80, minimum_effective_n_ratio=0.70,
            risk_chain_by_ticker=chains, risk_chain_top1_cap=0.55,
        )
        self.assertAlmostEqual(float(weights.sum()), 1.0)
        self.assertLessEqual(float(weights.max()), 0.50 + 1e-9)

    def test_turnover_anchor_reduces_rolling_rebalance_turnover(self):
        universe, returns, target, incumbent = synthetic_fixture(seed=14, business_days=260)
        plain = evaluate_synthetic_portfolio(
            ("ALFA", "BETA", "GAMM", "EPSI"), universe, returns, target, incumbent,
            window_days=42, step_days=21, transaction_cost_bps=10,
            weight_spec="constrained_fixed_shrinkage", fit_days=126,
        )
        anchored = evaluate_synthetic_portfolio(
            ("ALFA", "BETA", "GAMM", "EPSI"), universe, returns, target, incumbent,
            window_days=42, step_days=21, transaction_cost_bps=10,
            weight_spec="constrained_fixed_shrinkage_turnover_anchor", fit_days=126,
            turnover_anchor_strength=0.25,
        )
        self.assertLessEqual(anchored["turnover"], plain["turnover"] + 1e-12)
        self.assertEqual(anchored["turnover_regularization"], "L2_PREVIOUS_WEIGHT_ANCHOR")

    def test_whole_lot_failure_is_reported_without_fractional_share_assumption(self):
        universe, returns, target, incumbent = synthetic_fixture(seed=16, business_days=220)
        universe.loc[universe["ticker"].eq("BETA"), "synthetic_price"] = 10_000.0
        result = evaluate_synthetic_portfolio(
            ("BETA", "GAMM"), universe, returns, target, incumbent,
            window_days=42, step_days=21, transaction_cost_bps=10,
            portfolio_cash_usd=5000.0, minimum_cash_buffer_usd=100.0,
        )
        self.assertFalse(result["whole_lot_executable_all_windows"])
        self.assertEqual(result["whole_lot_min_shares"], 0)
        self.assertIn("WHOLE_LOT_EXECUTABILITY_FAILED", result["constraint_failure_reasons"])

    def test_small_cardinalities_report_declared_constraint_failures(self):
        universe, returns, target, incumbent = synthetic_fixture(seed=13, business_days=220)
        one = evaluate_synthetic_portfolio(
            ("ALFA",), universe, returns, target, incumbent,
            window_days=42, step_days=21, transaction_cost_bps=10,
        )
        two = evaluate_synthetic_portfolio(
            ("ALFA", "GAMM"), universe, returns, target, incumbent,
            window_days=42, step_days=21, transaction_cost_bps=10,
        )
        self.assertEqual(one["weight_top1_p50"], 1.0)
        self.assertFalse(one["declared_max_single_passed"])
        self.assertFalse(one["declared_security_top3_weight_passed"])
        self.assertAlmostEqual(two["weight_top1_p50"], 0.5)
        self.assertAlmostEqual(two["effective_n_p50"], 2.0)
        self.assertFalse(two["declared_max_single_passed"])
        self.assertFalse(two["declared_security_top3_weight_passed"])

    def test_security_top3_constraint_is_not_conflated_with_risk_chain_diagnostic(self):
        universe, returns, target, incumbent = synthetic_fixture(seed=15, business_days=220)
        result = evaluate_synthetic_portfolio(
            ("ALFA", "BETA", "GAMM", "EPSI"), universe, returns, target, incumbent,
            window_days=42, step_days=21, transaction_cost_bps=10,
        )
        self.assertAlmostEqual(result["weight_top3_max"], 0.75)
        self.assertTrue(result["declared_security_top3_weight_passed"])
        self.assertEqual(result["risk_chain_top3"], 1.0)

    def test_beam_selection_does_not_read_after_fit_cutoff(self):
        universe, returns, target, incumbent = synthetic_fixture(seed=17, business_days=220)
        first, _ = search_synthetic_cardinality(
            universe, returns, target, incumbent, holding_count=3,
            exact_limit=1, beam_width=3, window_days=42, step_days=21,
            transaction_cost_bps=10, fit_days=63,
        )
        changed = returns.copy()
        changed.iloc[63:, :] = (changed.iloc[63:, :] * -5.0).clip(lower=-0.50, upper=0.50)
        changed_target = changed[["ALFA", "GAMM", "EPSI"]].mul([0.35, 0.40, 0.25]).sum(axis=1)
        second, _ = search_synthetic_cardinality(
            universe, changed, changed_target, incumbent, holding_count=3,
            exact_limit=1, beam_width=3, window_days=42, step_days=21,
            transaction_cost_bps=10, fit_days=63,
        )
        self.assertEqual(set(first["tickers"]), set(second["tickers"]))

    def test_checkpoint_fails_closed_on_damage_or_fingerprint_change(self):
        fingerprint = synthetic_run_fingerprint("spec", self.spec["synthetic_smoke_contract"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            payload = {
                "schema_version": 1,
                "status": "SYNTHETIC_ENGINE_VALIDATION_ONLY",
                "run_fingerprint": fingerprint,
            }
            write_synthetic_checkpoint(path, payload)
            self.assertEqual(read_synthetic_checkpoint(path, fingerprint)["run_fingerprint"], fingerprint)
            with self.assertRaises(NdxCardinalityDiscoveryError):
                read_synthetic_checkpoint(path, "changed")
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(NdxCardinalityDiscoveryError):
                read_synthetic_checkpoint(path, fingerprint)

    def test_checkpoint_coordinate_rejects_unsafe_path_components(self):
        with self.assertRaises(NdxCardinalityDiscoveryError):
            validate_checkpoint_coordinate({
                "universe_track": "../strict", "selection_date": "2026-01-02",
                "holding_count": 2, "shard_id": "0000",
            })

    def test_resume_matches_clean_synthetic_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            common = {
                "spec": str(ROOT / "config/ndx_cardinality_discovery_v1.yaml"),
                "config": str(ROOT / "config/config.yaml"),
                "state": str(ROOT / "data/state.json"),
            }
            partial_args = SimpleNamespace(
                **common, smoke_output_dir=str(root / "resumed"),
                resume=False, max_cardinalities=2,
            )
            partial = build_synthetic_smoke(partial_args)
            self.assertFalse(partial["all_cardinalities_complete"])
            self.assertEqual(partial["checkpoint_layout"], "IMMUTABLE_CARDINALITY_SHARDS")
            self.assertEqual(partial["checkpoint_shard_count"], 2)
            coordinate = partial["artifacts"]["checkpoint_shards"][0]["checkpoint_coordinate"]
            self.assertEqual(coordinate["universe_track"], "synthetic_fixture")
            self.assertEqual(coordinate["selection_date"], "SYNTHETIC_ALL_WINDOWS")
            resumed_args = SimpleNamespace(
                **common, smoke_output_dir=str(root / "resumed"),
                resume=True, max_cardinalities=0,
            )
            resumed = build_synthetic_smoke(resumed_args)
            self.assertTrue(resumed["all_cardinalities_complete"])
            clean_args = SimpleNamespace(
                **common, smoke_output_dir=str(root / "clean"),
                resume=False, max_cardinalities=0,
            )
            clean = build_synthetic_smoke(clean_args)
            self.assertEqual(
                file_sha256(Path(resumed["artifacts"]["candidates"]["path"])),
                file_sha256(Path(clean["artifacts"]["candidates"]["path"])),
            )
            self.assertEqual(resumed["checkpoint_shard_count"], 5)

    def test_resume_fails_closed_when_a_cardinality_shard_is_damaged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            common = {
                "spec": str(ROOT / "config" / "ndx_cardinality_discovery_v1.yaml"),
                "config": str(ROOT / "config" / "config.yaml"),
                "state": str(ROOT / "data/state.json"),
                "smoke_output_dir": str(root / "damaged"),
            }
            partial = build_synthetic_smoke(SimpleNamespace(
                **common, resume=False, max_cardinalities=1,
            ))
            shard_path = Path(partial["artifacts"]["checkpoint_shards"][0]["path"])
            shard_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(NdxCardinalityDiscoveryError):
                build_synthetic_smoke(SimpleNamespace(
                    **common, resume=True, max_cardinalities=0,
                ))


if __name__ == "__main__":
    unittest.main()
