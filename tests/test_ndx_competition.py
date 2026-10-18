import numpy as np
import pandas as pd
import unittest
from unittest.mock import patch

import backtest.ndx_competition as ndx


def _snapshot_and_series(*, stale_count: int = 1):
    tickers = ["GOOG", "GOOGL"] + [f"T{i:03d}" for i in range(98)]
    snapshot = pd.DataFrame({
        "ticker": tickers,
        "weight": np.repeat(1.0 / len(tickers), len(tickers)),
    })
    fresh_dates = pd.bdate_range("2023-01-02", "2024-01-09")
    stale_dates = pd.bdate_range("2023-01-02", "2023-12-15")
    series = {}
    stale = set(tickers[-stale_count:]) if stale_count else set()
    for ticker in tickers:
        dates = stale_dates if ticker in stale else fresh_dates
        series[ticker] = pd.DataFrame(
            {"Close": np.linspace(100.0, 120.0, len(dates))},
            index=dates,
        )
    series["QQQ"] = pd.DataFrame(
        {"Close": np.linspace(100.0, 130.0, len(fresh_dates))},
        index=fresh_dates,
    )
    return snapshot, series


def _fake_metrics(series, asof, *, lookback_days, min_history_days):
    ordered = ["GOOG", "GOOGL", "T000", "T001", "T002"]
    scores = {ticker: 100.0 - rank for rank, ticker in enumerate(ordered)}
    rows = []
    for ticker in series:
        score = scores.get(ticker, 1.0)
        rows.append({
            "ticker": ticker,
            "ret_1y": score / 100.0,
            "ret_3y": score / 100.0,
            "vol_3y": 0.25,
            "dd_3y": 0.20,
            "attack_score": score,
        })
    return pd.DataFrame(rows).set_index("ticker", drop=False)


def _correlation_snapshot_and_series(*, identical: bool = False):
    tickers = ["A", "B", "C", "D", "E", "F"]
    snapshot = pd.DataFrame({
        "ticker": tickers,
        "weight": [0.42, 0.28, 0.16, 0.08, 0.04, 0.02],
    })
    dates = pd.bdate_range("2022-10-03", periods=330)
    rng = np.random.default_rng(20260712)
    base = rng.normal(0.0005, 0.012, len(dates))
    returns = {
        "A": base,
        "B": base if identical else base + rng.normal(0.0, 0.0002, len(dates)),
        "C": base if identical else rng.normal(0.0004, 0.014, len(dates)),
        "D": base if identical else rng.normal(0.0003, 0.011, len(dates)),
        "E": base if identical else rng.normal(0.0002, 0.016, len(dates)),
        "F": base if identical else rng.normal(0.0001, 0.010, len(dates)),
    }
    series = {
        ticker: pd.DataFrame(
            {"Close": 100.0 * np.cumprod(1.0 + values)},
            index=dates,
        )
        for ticker, values in returns.items()
    }
    return snapshot, series, dates[-1] + pd.Timedelta(days=1)


def _correlation_metrics(series, asof, *, lookback_days, min_history_days):
    rows = []
    for rank, ticker in enumerate(["A", "B", "C", "D", "E", "F"]):
        rows.append({
            "ticker": ticker,
            "ret_1y": 1.0 - rank / 10.0,
            "ret_3y": 1.0 - rank / 10.0,
            "vol_3y": 0.20,
            "dd_3y": 0.20,
            "attack_score": 1.0 - rank / 10.0,
        })
    return pd.DataFrame(rows).set_index("ticker", drop=False)


def _quality_scores(
    asof: pd.Timestamp,
    *,
    scores: dict[str, float] | None = None,
    sic4: dict[str, int] | None = None,
    sic2: dict[str, str] | None = None,
) -> pd.DataFrame:
    tickers = ["A", "B", "C", "D", "E", "F"]
    score_map = scores or {
        ticker: float((index + 1) * 10) for index, ticker in enumerate(tickers)
    }
    sic4_map = sic4 or {
        "A": 7372,
        "B": 7372,
        "C": 7370,
        "D": 3674,
        "E": 2834,
        "F": 2086,
    }
    sic2_map = sic2 or {
        "A": "73",
        "B": "73",
        "C": "73",
        "D": "36",
        "E": "28",
        "F": "20",
    }
    date_label = pd.Timestamp(asof).strftime("%Y-%m-%d")
    return pd.DataFrame([
        {
            "selection_date": date_label,
            "ticker": ticker,
            "cik": 1000 + index,
            "quality_score": score_map[ticker],
            "quality_eligible": True,
            "quality_policy_id": ndx.QUALITY_POLICY_ID,
            "sic": sic4_map[ticker],
            "sic_group_2d": sic2_map[ticker],
        }
        for index, ticker in enumerate(tickers)
    ])


def _valuation_scores(asof: pd.Timestamp) -> pd.DataFrame:
    tickers = ["A", "B", "C", "D", "E", "F"]
    date_label = pd.Timestamp(asof).strftime("%Y-%m-%d")
    return pd.DataFrame([
        {
            "selection_date": date_label,
            "ticker": ticker,
            "cik": 1000 + index,
            "valuation_score": 50.0 if ticker == "C" else float((index + 1) * 10),
            "valuation_factor_active": True,
            "valuation_factor_coverage": 5 / 6,
            "valuation_missing_neutral_applied": ticker == "C",
            "valuation_missing_neutral_score": 50.0,
            "valuation_policy_id": ndx.VALUATION_SCORE_POLICY_ID,
        }
        for index, ticker in enumerate(tickers)
    ])


class NdxCompetitionTests(unittest.TestCase):
    def test_frozen_candidate_pool_is_intersected_after_full_universe_audit(self):
        snapshot, series = _snapshot_and_series(stale_count=1)
        with patch.object(ndx, "_metrics_asof", side_effect=_fake_metrics):
            choice = ndx._choose_from_snapshot(
                snapshot,
                {"available_date": "2024-01-01"},
                asof=pd.Timestamp("2024-01-10"),
                series=series,
                top_n=3,
                weight_mode="equal",
                lookback_days=252,
                min_history_days=126,
                candidate_tickers=["T001", "T002", "T003", "T004"],
            )

        self.assertEqual(choice.expected_count, 100)
        self.assertEqual(choice.price_count, 99)
        self.assertEqual(choice.candidate_member_count, 4)
        self.assertEqual(choice.candidate_tickers, ("T001", "T002", "T003", "T004"))
        self.assertEqual(choice.tickers, ("T001", "T002", "T003"))

    def test_frozen_candidate_pool_fails_closed_when_date_has_too_few_members(self):
        snapshot, series = _snapshot_and_series(stale_count=1)
        with patch.object(ndx, "_metrics_asof", side_effect=_fake_metrics):
            with self.assertRaisesRegex(
                ndx.NdxCompetitionError,
                "after frozen candidate-pool intersection",
            ):
                ndx._choose_from_snapshot(
                    snapshot,
                    {},
                    asof=pd.Timestamp("2024-01-10"),
                    series=series,
                    top_n=3,
                    weight_mode="equal",
                    lookback_days=252,
                    min_history_days=126,
                    candidate_tickers=["T001", "NOT_A_MEMBER", "ALSO_MISSING"],
                )

    def test_snapshot_choice_is_tradeable_distinct_issuer_and_excludes_qqq(self):
        snapshot, series = _snapshot_and_series(stale_count=1)
        with patch.object(ndx, "_metrics_asof", side_effect=_fake_metrics):
            choice = ndx._choose_from_snapshot(
                snapshot,
                {"available_date": "2024-01-01"},
                asof=pd.Timestamp("2024-01-10"),
                series=series,
                top_n=4,
                weight_mode="equal",
                lookback_days=252,
                min_history_days=126,
                max_weight=0.35,
            )

        self.assertEqual(choice.expected_count, 100)
        self.assertEqual(choice.expected_issuer_count, 99)
        self.assertEqual(choice.price_count, 99)
        self.assertEqual(choice.stale_price_tickers, ("T097",))
        self.assertEqual(choice.tickers, ("GOOG", "T000", "T001", "T002"))
        self.assertEqual(choice.duplicate_issuer_tickers, ("GOOGL",))
        self.assertNotIn("QQQ", choice.tickers)
        self.assertAlmostEqual(sum(choice.weights.values()), 1.0)

    def test_snapshot_choice_fails_closed_when_price_coverage_is_low(self):
        snapshot, series = _snapshot_and_series(stale_count=3)
        with patch.object(ndx, "_metrics_asof", side_effect=_fake_metrics):
            with self.assertRaisesRegex(ndx.NdxCompetitionError, "price coverage 97.0%"):
                ndx._choose_from_snapshot(
                    snapshot,
                    {},
                    asof=pd.Timestamp("2024-01-10"),
                    series=series,
                    top_n=4,
                    weight_mode="equal",
                    lookback_days=252,
                    min_history_days=126,
                )

    def test_risk_parity_weights_respect_bounds_and_sum(self):
        rng = np.random.default_rng(20260710)
        returns = pd.DataFrame(
            rng.normal(0.0005, [0.010, 0.015, 0.020, 0.025], size=(400, 4)),
            columns=["A", "B", "C", "D"],
        )

        weights = ndx._risk_parity_weights(
            returns,
            max_weight=0.35,
            min_weight=0.02,
        )

        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertGreaterEqual(min(weights.values()), 0.02 - 1e-8)
        self.assertLessEqual(max(weights.values()), 0.35 + 1e-8)

    def test_current_source_weight_is_unavailable_instead_of_guessed(self):
        result = ndx._current_choice(
            pd.DataFrame({"ticker": ["AAPL"]}),
            {},
            row={"weight_mode": "source_weight"},
            asof=pd.Timestamp("2026-07-10"),
        )

        self.assertFalse(result["available"])
        self.assertIn("not guessed", result["reason"])

    def test_incumbent_anchor_blends_subaccounts_with_exact_cash_flows(self):
        challenger_equity = np.asarray([100.0, 120.0, 132.0])
        incumbent_equity = np.asarray([100.0, 105.0, 110.0])
        flows = [(0, 100.0)]

        nav, equity, observed_flows = ndx._blend_incumbent_anchor(
            challenger_equity / 100.0,
            challenger_equity,
            flows,
            incumbent_equity / 100.0,
            incumbent_equity,
            [(0, 40.0), (0, 60.0)],
            challenger_weight=0.20,
        )

        np.testing.assert_allclose(equity, [100.0, 108.0, 114.4])
        np.testing.assert_allclose(nav, [1.0, 1.08, 1.144])
        self.assertEqual(observed_flows, flows)

    def test_subaccount_unitization_removes_monthly_flow_from_return(self):
        nav = ndx._unitized_nav_from_equity(
            np.asarray([100.0, 120.0, 132.0]),
            [(0, 100.0), (1, 10.0)],
        )

        np.testing.assert_allclose(nav, [1.0, 1.1, 1.21])

    def test_correlation_replacement_uses_only_prior_prices_and_replaces_peer(self):
        snapshot, series, asof = _correlation_snapshot_and_series()
        with patch.object(ndx, "_metrics_asof", side_effect=_correlation_metrics):
            choice = ndx._choose_from_snapshot(
                snapshot,
                {"available_date": "2023-12-01"},
                asof=asof,
                series=series,
                top_n=3,
                weight_mode="equal",
                lookback_days=252,
                min_history_days=126,
                selection_mode="correlation_replacement",
                correlation_lookback_days=252,
                correlation_threshold=0.75,
            )

        self.assertEqual(choice.tickers, ("A", "C", "D"))
        self.assertIn("B", choice.rejected_correlated_tickers)
        self.assertLess(choice.max_pair_correlation, 0.75)
        self.assertTrue(choice.correlation_strict_asof_passed)
        self.assertLess(pd.Timestamp(choice.correlation_price_end), asof)

    def test_correlation_replacement_fails_closed_instead_of_relaxing_threshold(self):
        snapshot, series, asof = _correlation_snapshot_and_series(identical=True)
        with patch.object(ndx, "_metrics_asof", side_effect=_correlation_metrics):
            with self.assertRaisesRegex(ndx.NdxCompetitionError, "filled only 1 of top3"):
                ndx._choose_from_snapshot(
                    snapshot,
                    {},
                    asof=asof,
                    series=series,
                    top_n=3,
                    weight_mode="equal",
                    lookback_days=252,
                    min_history_days=126,
                    selection_mode="correlation_replacement",
                    correlation_lookback_days=252,
                    correlation_threshold=0.75,
                )

    def test_cluster_weight_budget_preserves_sum_and_caps_correlated_names(self):
        snapshot, series, asof = _correlation_snapshot_and_series()
        with patch.object(ndx, "_metrics_asof", side_effect=_correlation_metrics):
            choice = ndx._choose_from_snapshot(
                snapshot,
                {},
                asof=asof,
                series=series,
                top_n=4,
                weight_mode="source_weight",
                lookback_days=252,
                min_history_days=126,
                max_weight=0.50,
                selection_mode="rank",
                correlation_lookback_days=252,
                correlation_threshold=0.75,
                cluster_max_weight=0.40,
            )

        self.assertAlmostEqual(sum(choice.weights.values()), 1.0)
        self.assertLessEqual(max(choice.cluster_weights.values()), 0.40 + 1e-10)
        self.assertEqual(choice.cluster_labels["A"], choice.cluster_labels["B"])

    def test_source_weight_envelope_is_applied_and_exposed(self):
        snapshot, series, asof = _correlation_snapshot_and_series()
        with patch.object(ndx, "_metrics_asof", side_effect=_correlation_metrics):
            choice = ndx._choose_from_snapshot(
                snapshot,
                {},
                asof=asof,
                series=series,
                top_n=6,
                weight_mode="source_weight",
                lookback_days=252,
                min_history_days=126,
                max_weight=0.25,
                min_weight=0.02,
                top_weight_count=3,
                top_weight_cap=0.55,
                min_effective_n=5.0,
            )

        weights = np.asarray(list(choice.weights.values()), dtype=float)
        self.assertAlmostEqual(float(weights.sum()), 1.0, places=9)
        self.assertLessEqual(float(weights.max()), 0.25 + 1e-9)
        self.assertLessEqual(float(np.sort(weights)[-3:].sum()), 0.55 + 1e-9)
        self.assertGreaterEqual(1.0 / float(np.square(weights).sum()), 5.0 - 1e-8)
        self.assertEqual(choice.top_weight_count, 3)
        self.assertEqual(choice.top_weight_cap, 0.55)
        self.assertEqual(choice.min_effective_n, 5.0)

    def test_profile_normalization_rejects_partial_or_non_source_envelope(self):
        base = {
            "id": "envelope",
            "top_n": 8,
            "weight_mode": "source_weight",
            "rebalance_months": 6,
            "safe_weight": 0.26,
            "max_weight": 0.20,
            "top_weight_count": 3,
            "top_weight_cap": 0.45,
        }
        kwargs = {
            "lookback_years": 1.0,
            "top_values": [8],
            "mode_values": ["source_weight"],
            "safe_values": [0.26],
            "rebalance_values": [6],
            "max_weight_values": [0.20],
        }

        normalized = ndx._normalize_construction_profiles([base], **kwargs)[0]
        self.assertEqual(normalized["top_weight_count"], 3)
        self.assertEqual(normalized["top_weight_cap"], 0.45)

        partial = dict(base)
        partial.pop("top_weight_cap")
        with self.assertRaisesRegex(ndx.NdxCompetitionError, "declared together"):
            ndx._normalize_construction_profiles([partial], **kwargs)

        unsupported = dict(base, weight_mode="equal")
        with self.assertRaisesRegex(ndx.NdxCompetitionError, "source_weight"):
            ndx._normalize_construction_profiles([unsupported], **kwargs)

    def test_quality_blend_reorders_price_rank_with_exact_point_in_time_scores(self):
        snapshot, series, asof = _correlation_snapshot_and_series()
        quality = _quality_scores(asof)
        with patch.object(ndx, "_metrics_asof", side_effect=_correlation_metrics):
            choice = ndx._choose_from_snapshot(
                snapshot,
                {"available_date": "2023-12-01"},
                asof=asof,
                series=series,
                top_n=3,
                weight_mode="equal",
                lookback_days=252,
                min_history_days=126,
                quality_scores=quality,
                fundamental_score_weight=1.0,
                quality_policy_id=ndx.QUALITY_POLICY_ID,
            )

        self.assertEqual(choice.tickers, ("F", "E", "D"))
        self.assertEqual(choice.quality_score_date, asof.strftime("%Y-%m-%d"))
        self.assertTrue(choice.quality_future_data_guard_passed)
        self.assertAlmostEqual(choice.quality_score_coverage, 1.0)

    def test_valuation_blend_reorders_price_rank_and_keeps_missing_neutral(self):
        snapshot, series, asof = _correlation_snapshot_and_series()
        valuation = _valuation_scores(asof)
        with patch.object(ndx, "_metrics_asof", side_effect=_correlation_metrics):
            choice = ndx._choose_from_snapshot(
                snapshot,
                {"available_date": "2023-12-01"},
                asof=asof,
                series=series,
                top_n=3,
                weight_mode="equal",
                lookback_days=252,
                min_history_days=126,
                valuation_scores=valuation,
                valuation_score_weight=1.0,
                valuation_policy_id=ndx.VALUATION_SCORE_POLICY_ID,
            )

        self.assertEqual(choice.tickers, ("F", "C", "E"))
        self.assertEqual(choice.valuation_score_date, asof.strftime("%Y-%m-%d"))
        self.assertTrue(choice.valuation_future_data_guard_passed)
        self.assertAlmostEqual(choice.valuation_score_coverage, 1.0)
        self.assertAlmostEqual(choice.valuation_observed_coverage, 5 / 6)
        self.assertEqual(choice.valuation_missing_neutral_count, 1)

    def test_bounded_quality_challenge_limits_price_rank_replacements(self):
        snapshot, series, asof = _correlation_snapshot_and_series()
        quality = _quality_scores(asof)
        with patch.object(ndx, "_metrics_asof", side_effect=_correlation_metrics):
            choice = ndx._choose_from_snapshot(
                snapshot,
                {"available_date": "2023-12-01"},
                asof=asof,
                series=series,
                top_n=3,
                weight_mode="equal",
                lookback_days=252,
                min_history_days=126,
                quality_scores=quality,
                quality_policy_id=ndx.QUALITY_POLICY_ID,
                quality_selection_mode="bounded_challenge",
                quality_challenge_pool_size=6,
                max_quality_replacements=1,
            )

        self.assertEqual(choice.tickers, ("B", "C", "F"))
        self.assertEqual(
            choice.quality_challenge_pool_tickers,
            ("A", "B", "C", "D", "E", "F"),
        )
        self.assertEqual(len(choice.quality_replacement_pairs), 1)
        pair = choice.quality_replacement_pairs[0]
        self.assertEqual(pair["outgoing_ticker"], "A")
        self.assertEqual(pair["incoming_ticker"], "F")
        self.assertGreater(pair["quality_score_delta"], 0.0)
        self.assertAlmostEqual(choice.quality_score_coverage, 1.0)

    def test_bounded_quality_challenge_does_not_treat_missing_score_as_bad(self):
        quality = _quality_scores(pd.Timestamp("2024-01-02"))
        quality.loc[quality["ticker"].eq("A"), "quality_eligible"] = False

        picked, _, replacements = ndx._select_bounded_quality_challengers(
            ["A", "B", "C", "D", "E", "F"],
            quality.set_index("ticker", drop=False),
            top_n=3,
            pool_size=6,
            max_replacements=1,
        )

        self.assertEqual(picked, ["A", "C", "F"])
        self.assertEqual(replacements[0]["outgoing_ticker"], "B")

    def test_quality_profile_fails_closed_without_exact_selection_date(self):
        snapshot, series, asof = _correlation_snapshot_and_series()
        quality = _quality_scores(asof - pd.Timedelta(days=1))
        with patch.object(ndx, "_metrics_asof", side_effect=_correlation_metrics):
            with self.assertRaisesRegex(
                ndx.NdxCompetitionError, "snapshot is unavailable"
            ):
                ndx._choose_from_snapshot(
                    snapshot,
                    {},
                    asof=asof,
                    series=series,
                    top_n=3,
                    weight_mode="equal",
                    lookback_days=252,
                    min_history_days=126,
                    quality_scores=quality,
                    fundamental_score_weight=0.25,
                    quality_policy_id=ndx.QUALITY_POLICY_ID,
                )

    def test_sic_name_caps_replace_lower_ranked_industry_duplicates(self):
        snapshot, series, asof = _correlation_snapshot_and_series()
        quality = _quality_scores(
            asof,
            sic4={
                "A": 7372,
                "B": 7372,
                "C": 7372,
                "D": 7372,
                "E": 3674,
                "F": 2834,
            },
            sic2={
                "A": "73",
                "B": "73",
                "C": "73",
                "D": "73",
                "E": "36",
                "F": "28",
            },
        )
        with patch.object(ndx, "_metrics_asof", side_effect=_correlation_metrics):
            choice = ndx._choose_from_snapshot(
                snapshot,
                {},
                asof=asof,
                series=series,
                top_n=4,
                weight_mode="equal",
                lookback_days=252,
                min_history_days=126,
                quality_scores=quality,
                quality_policy_id=ndx.QUALITY_POLICY_ID,
                max_names_per_sic4=2,
                max_names_per_sic2=2,
            )

        self.assertEqual(choice.tickers, ("A", "B", "E", "F"))
        self.assertEqual(choice.rejected_sic_reasons["C"], "sic4_name_cap")
        self.assertEqual(choice.rejected_sic_reasons["D"], "sic4_name_cap")

    def test_sic_weight_caps_bound_nested_groups_after_source_weighting(self):
        snapshot, series, asof = _correlation_snapshot_and_series()
        quality = _quality_scores(asof)
        with patch.object(ndx, "_metrics_asof", side_effect=_correlation_metrics):
            choice = ndx._choose_from_snapshot(
                snapshot,
                {},
                asof=asof,
                series=series,
                top_n=4,
                weight_mode="source_weight",
                lookback_days=252,
                min_history_days=126,
                max_weight=0.50,
                quality_scores=quality,
                quality_policy_id=ndx.QUALITY_POLICY_ID,
                sic4_max_weight=0.50,
                sic2_max_weight=0.60,
            )

        self.assertAlmostEqual(sum(choice.weights.values()), 1.0)
        self.assertLessEqual(max(choice.sic4_weights.values()), 0.50 + 1e-8)
        self.assertLessEqual(max(choice.sic2_weights.values()), 0.60 + 1e-8)

    def test_vol_target_signal_has_a_one_day_information_lag(self):
        signal = np.cumprod(np.r_[1.0, np.repeat(1.002, 79)])
        shocked = signal.copy()
        shocked[50:] *= 0.70

        base_weights = ndx._vol_target_weight_series(signal, 0.25, 0.10, 0.15, 20)
        shocked_weights = ndx._vol_target_weight_series(shocked, 0.25, 0.10, 0.15, 20)

        np.testing.assert_allclose(base_weights[:51], shocked_weights[:51])

    def test_ex_ante_basket_volatility_seeds_from_strict_prior_history(self):
        _, series, _ = _correlation_snapshot_and_series()
        grid = series["A"].index[-20:]
        selection = [{
            "date": grid[0].strftime("%Y-%m-%d"),
            "weights": {"A": 0.50, "C": 0.50},
        }]
        baseline, meta = ndx._selected_basket_realized_vol_series(
            grid,
            selection,
            series,
            vol_window=20,
        )
        shocked = {ticker: frame.copy() for ticker, frame in series.items()}
        shocked["A"].loc[grid[0], "Close"] *= 2.0
        changed, _ = ndx._selected_basket_realized_vol_series(
            grid,
            selection,
            shocked,
            vol_window=20,
        )

        self.assertTrue(meta["prehistory_seeded"])
        self.assertTrue(meta["strict_asof_passed"])
        self.assertLess(pd.Timestamp(meta["first_signal_date"]), grid[0])
        self.assertAlmostEqual(baseline[0], changed[0])
        self.assertNotAlmostEqual(baseline[1], changed[1])

    def test_ex_ante_drawdown_guard_uses_prior_history_and_bounded_ramp(self):
        _, series, _ = _correlation_snapshot_and_series()
        grid = series["A"].index[-20:]
        selection = [{
            "date": grid[0].strftime("%Y-%m-%d"),
            "weights": {"A": 0.50, "C": 0.50},
        }]
        baseline, meta = ndx._selected_basket_current_drawdown_series(
            grid,
            selection,
            series,
            lookback_days=126,
        )
        shocked = {ticker: frame.copy() for ticker, frame in series.items()}
        shocked["A"].loc[grid[0], "Close"] *= 0.5
        changed, _ = ndx._selected_basket_current_drawdown_series(
            grid,
            selection,
            shocked,
            lookback_days=126,
        )
        weights = ndx._safe_weights_from_drawdown(
            np.asarray([0.00, 0.05, 0.10, 0.20]),
            base_weight=0.0,
            max_safe_weight=0.30,
            trigger=0.05,
            full=0.15,
        )

        self.assertTrue(meta["prehistory_seeded"])
        self.assertLess(pd.Timestamp(meta["first_signal_date"]), grid[0])
        self.assertAlmostEqual(baseline[0], changed[0])
        self.assertNotAlmostEqual(baseline[1], changed[1])
        np.testing.assert_allclose(weights, [0.0, 0.0, 0.15, 0.30])
        np.testing.assert_allclose(
            ndx._slow_release_safe_weights(
                np.asarray([0.0, 0.30, 0.0, 0.0, 0.10, 0.0]),
                0.10,
            ),
            [0.0, 0.30, 0.20, 0.10, 0.10, 0.0],
        )

    def test_defensive_overlay_trade_cost_is_deducted_from_equity(self):
        grid = pd.bdate_range("2024-01-02", periods=30)
        risky_nav = np.cumprod(np.r_[1.0, np.repeat(1.01, len(grid) - 1)])
        flows = [(0, 1000.0)]
        no_cost = ndx._run_defensive_fund(
            grid, risky_nav, flows, 0.0, 0.50, 1, 0.0
        )
        execution = {}
        with_cost = ndx._run_defensive_fund(
            grid,
            risky_nav,
            flows,
            0.0,
            0.50,
            1,
            0.0,
            trade_cost_bps=100.0,
            execution_stats=execution,
        )

        self.assertGreater(execution["cost_paid"], 0.0)
        self.assertLess(with_cost[1][-1], no_cost[1][-1])


if __name__ == "__main__":
    unittest.main()
