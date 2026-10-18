import unittest

import numpy as np
import pandas as pd

from backtest.ndx_dynamic_whole_lot_path import (
    NdxDynamicWholeLotPathError,
    simulate_dynamic_security_id_fractional_path,
    simulate_dynamic_security_id_whole_lot_path,
)


def _target(ticker, weight):
    return {"ticker": ticker, "target_weight": weight}


class NdxDynamicWholeLotPathTests(unittest.TestCase):
    def test_separate_open_execution_and_close_valuation_channels(self):
        dates = pd.date_range("2024-01-02", periods=2, freq="B")
        closes = pd.DataFrame({"A": [100.0, 101.0]}, index=dates)
        opens = pd.DataFrame({"A": [50.0, 51.0]}, index=dates)
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": dates[0],
            "targets": {
                "security:a": {
                    "ticker": "A", "issuer_id": "issuer:a", "target_weight": 1.0,
                }
            },
        }]
        summary, rebalances, _, path = simulate_dynamic_security_id_whole_lot_path(
            closes,
            schedule,
            execution_prices=opens,
            require_separate_execution_prices=True,
            require_next_session_execution=True,
            require_issuer_trace=True,
            initial_cash_usd=1000.0,
            minimum_cash_buffer_usd=100.0,
            valuation_end_date=dates[-1],
        )
        self.assertTrue(summary["separate_execution_price_channel"])
        self.assertEqual(rebalances.iloc[0]["holdings"], '{"security:a":{"issuer_id":"issuer:a","shares":17,"ticker":"A"}}')
        self.assertGreater(path.iloc[0]["total_value_usd"], 1800.0)

    def test_future_shadow_guards_fail_closed_when_optional_channels_are_omitted(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame({"A": [100.0, 101.0, 102.0]}, index=dates)
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": dates[0],
            "targets": {"security:a": _target("A", 1.0)},
        }]
        with self.assertRaisesRegex(NdxDynamicWholeLotPathError, "separate execution"):
            simulate_dynamic_security_id_whole_lot_path(
                prices,
                schedule,
                require_separate_execution_prices=True,
                require_issuer_trace=True,
                initial_cash_usd=1000.0,
                minimum_cash_buffer_usd=100.0,
                valuation_end_date=dates[-1],
            )

    def test_security_id_cannot_change_issuer_across_periods(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame({"A": [100.0, 101.0, 102.0]}, index=dates)
        schedule = [
            {
                "decision_date": "2024-01-01", "execution_date": dates[0],
                "targets": {"security:a": {"ticker": "A", "issuer_id": "issuer:one", "target_weight": 1.0}},
            },
            {
                "decision_date": dates[0], "execution_date": dates[1],
                "targets": {"security:a": {"ticker": "A", "issuer_id": "issuer:two", "target_weight": 1.0}},
            },
        ]
        with self.assertRaisesRegex(NdxDynamicWholeLotPathError, "changed issuer_id"):
            simulate_dynamic_security_id_whole_lot_path(
                prices,
                schedule,
                initial_cash_usd=1000.0,
                minimum_cash_buffer_usd=100.0,
                valuation_end_date=dates[-1],
            )

    def test_first_session_execution_guard_rejects_skipped_session(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame({"A": [100.0, 101.0, 102.0]}, index=dates)
        schedule = [{
            "decision_date": dates[0],
            "execution_date": dates[2],
            "targets": {"security:a": {"ticker": "A", "issuer_id": "issuer:a", "target_weight": 1.0}},
        }]
        with self.assertRaisesRegex(NdxDynamicWholeLotPathError, "not the first session"):
            simulate_dynamic_security_id_whole_lot_path(
                prices,
                schedule,
                execution_prices=prices,
                require_separate_execution_prices=True,
                require_next_session_execution=True,
                require_issuer_trace=True,
                initial_cash_usd=1000.0,
                minimum_cash_buffer_usd=100.0,
                valuation_end_date=dates[-1],
            )

    def test_complete_issuer_trace_is_recorded_and_duplicate_issuer_rejected(self):
        date = pd.Timestamp("2024-01-02")
        prices = pd.DataFrame({"A": [100.0], "A2": [100.0]}, index=[date])
        traced = [{
            "decision_date": "2024-01-01",
            "execution_date": date,
            "targets": {
                "security:a": {"ticker": "A", "issuer_id": "issuer:a", "target_weight": 1.0}
            },
        }]
        summary, _, _, _ = simulate_dynamic_security_id_whole_lot_path(
            prices,
            traced,
            initial_cash_usd=1000.0,
            minimum_cash_buffer_usd=100.0,
            valuation_end_date=date,
        )
        self.assertTrue(summary["issuer_identity_trace_available"])

        duplicated = [{
            "decision_date": "2024-01-01",
            "execution_date": date,
            "targets": {
                "security:a": {"ticker": "A", "issuer_id": "issuer:a", "target_weight": 0.5},
                "security:a2": {"ticker": "A2", "issuer_id": "issuer:a", "target_weight": 0.5},
            },
        }]
        with self.assertRaisesRegex(NdxDynamicWholeLotPathError, "appears more than once"):
            simulate_dynamic_security_id_whole_lot_path(
                prices,
                duplicated,
                initial_cash_usd=1000.0,
                minimum_cash_buffer_usd=100.0,
                valuation_end_date=date,
            )

    def test_fractional_companion_preserves_buffer_and_dynamic_identity(self):
        dates = pd.date_range("2024-01-02", periods=4, freq="B")
        prices = pd.DataFrame(
            {"A": [100.0, 101.0, 102.0, 103.0], "B": [50.0, 51.0, 52.0, 53.0]},
            index=dates,
        )
        schedule = [
            {
                "decision_date": "2024-01-01",
                "execution_date": dates[0],
                "targets": {"security:a": _target("A", 1.0)},
            },
            {
                "decision_date": dates[1],
                "execution_date": dates[2],
                "targets": {
                    "security:a": _target("A", 0.4),
                    "security:b": _target("B", 0.6),
                },
            },
        ]
        summary, rebalances, trades, path = simulate_dynamic_security_id_fractional_path(
            prices,
            schedule,
            initial_cash_usd=1000.0,
            minimum_cash_buffer_usd=100.0,
            transaction_cost_bps=10.0,
            valuation_end_date=dates[-1],
        )
        self.assertEqual(summary["k_path"], [1, 2])
        self.assertTrue(summary["cash_buffer_preserved"])
        self.assertFalse(summary["issuer_identity_trace_available"])
        self.assertTrue(summary["cash_conservation_passed"])
        self.assertTrue(summary["accounting_invariant_passed"])
        self.assertAlmostEqual(rebalances.iloc[-1]["cash_after_usd"], 100.0, places=8)
        self.assertTrue((trades.loc[trades["event_type"].eq("ECONOMIC_TRADE"), "shares_after"] % 1 != 0).any())
        self.assertEqual(path.iloc[-1]["holding_count"], 2)

    def test_fractional_rename_is_zero_fee_identity_event(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame(
            {"OLD": [100.0, float("nan"), float("nan")], "NEW": [float("nan"), 100.0, 101.0]},
            index=dates,
        )
        schedule = [
            {"decision_date": "2024-01-01", "execution_date": dates[0], "targets": {"security:a": _target("OLD", 1.0)}},
            {"decision_date": dates[0], "execution_date": dates[1], "targets": {"security:a": _target("NEW", 1.0)}},
        ]
        _, _, trades, _ = simulate_dynamic_security_id_fractional_path(
            prices,
            schedule,
            initial_cash_usd=1000.0,
            minimum_cash_buffer_usd=100.0,
            valuation_end_date=dates[-1],
        )
        rename = trades.loc[
            trades["rebalance_sequence"].eq(2) & trades["event_type"].eq("RENAME_NO_TRADE")
        ].iloc[0]
        self.assertEqual(rename["transaction_cost_usd"], 0.0)

    def test_variable_k_composition_weights_and_two_sided_costs_are_continuous(self):
        dates = pd.date_range("2024-01-02", periods=5, freq="B")
        prices = pd.DataFrame(
            {ticker: [100.0] * len(dates) for ticker in ["A", "B", "C", "D"]},
            index=dates,
        )
        schedule = [
            {
                "decision_date": "2024-01-01",
                "execution_date": dates[0],
                "targets": {
                    "security:a": _target("A", 0.5),
                    "security:b": _target("B", 0.5),
                },
            },
            {
                "decision_date": dates[1],
                "execution_date": dates[2],
                "targets": {
                    "security:b": _target("B", 0.5),
                    "security:c": _target("C", 0.25),
                    "security:d": _target("D", 0.25),
                },
            },
        ]

        summary, rebalances, trades, path = simulate_dynamic_security_id_whole_lot_path(
            prices,
            schedule,
            initial_cash_usd=1000.0,
            minimum_cash_buffer_usd=100.0,
            transaction_cost_bps=10.0,
            valuation_end_date=dates[-1],
        )

        self.assertEqual(summary["portfolio_track"], "portfolio_optimization")
        self.assertFalse(summary["migration_control_assumption_used"])
        self.assertEqual(summary["k_path"], [2, 3])
        self.assertEqual(rebalances["posttrade_k"].tolist(), [2, 3])
        self.assertEqual(rebalances.iloc[1]["added_security_ids"], '["security:c","security:d"]')
        self.assertEqual(rebalances.iloc[1]["removed_security_ids"], '["security:a"]')
        self.assertAlmostEqual(rebalances.iloc[0]["cash_after_usd"], 199.2)
        self.assertAlmostEqual(rebalances.iloc[1]["cash_before_usd"], 199.2)
        self.assertAlmostEqual(rebalances.iloc[1]["cash_after_usd"], 198.4)
        second = trades[
            (trades["rebalance_sequence"] == 2)
            & (trades["event_type"] == "ECONOMIC_TRADE")
        ].set_index("security_id")
        self.assertEqual(second.at["security:a", "action"], "SELL")
        self.assertAlmostEqual(second.at["security:a", "transaction_cost_usd"], 0.4)
        self.assertAlmostEqual(second.at["security:c", "transaction_cost_usd"], 0.2)
        self.assertAlmostEqual(second.at["security:d", "transaction_cost_usd"], 0.2)
        self.assertAlmostEqual(summary["total_transaction_cost_usd"], 1.6)
        self.assertEqual(path["holding_count"].tolist(), [2, 2, 3, 3, 3])
        self.assertTrue(summary["cash_conservation_passed"])
        self.assertTrue(summary["accounting_invariant_passed"])
        self.assertTrue(summary["whole_share_invariant_passed"])
        self.assertTrue(summary["cash_buffer_preserved"])
        self.assertAlmostEqual(summary["path_max_drawdown"], 0.0016)
        self.assertEqual(summary["path_trading_session_count"], 5)

    def test_ticker_rename_carries_security_id_shares_without_trade_or_fee(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame(
            {
                "OLD": [100.0, np.nan, np.nan],
                "NEW": [np.nan, 100.0, 101.0],
            },
            index=dates,
        )
        schedule = [
            {
                "decision_date": "2024-01-01",
                "execution_date": dates[0],
                "targets": {"security:same": _target("OLD", 1.0)},
            },
            {
                "decision_date": dates[0],
                "execution_date": dates[1],
                "targets": {"security:same": _target("NEW", 1.0)},
            },
        ]

        summary, rebalances, trades, path = simulate_dynamic_security_id_whole_lot_path(
            prices,
            schedule,
            initial_cash_usd=1000.0,
            minimum_cash_buffer_usd=100.0,
            valuation_end_date=dates[-1],
        )

        second = trades[trades["rebalance_sequence"] == 2]
        self.assertEqual(second["event_type"].tolist(), ["RENAME_NO_TRADE"])
        self.assertEqual(second["share_delta"].tolist(), [0])
        self.assertEqual(second["notional_usd"].tolist(), [0.0])
        self.assertEqual(second["transaction_cost_usd"].tolist(), [0.0])
        self.assertAlmostEqual(rebalances.iloc[1]["transaction_cost_usd"], 0.0)
        self.assertAlmostEqual(summary["total_transaction_cost_usd"], 0.8)
        self.assertIn(
            '"security:same":{"issuer_id":"","shares":8,"ticker":"NEW"}',
            path.iloc[-1]["holdings"],
        )

    def test_rename_with_weight_change_has_separate_economic_share_trades(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame(
            {ticker: [100.0] * len(dates) for ticker in ["OLD", "NEW", "B"]},
            index=dates,
        )
        schedule = [
            {
                "decision_date": "2024-01-01",
                "execution_date": dates[0],
                "targets": {
                    "security:a": _target("OLD", 0.5),
                    "security:b": _target("B", 0.5),
                },
            },
            {
                "decision_date": dates[0],
                "execution_date": dates[1],
                "targets": {
                    "security:a": _target("NEW", 0.75),
                    "security:b": _target("B", 0.25),
                },
            },
        ]

        _, rebalances, trades, _ = simulate_dynamic_security_id_whole_lot_path(
            prices,
            schedule,
            initial_cash_usd=1000.0,
            minimum_cash_buffer_usd=100.0,
            valuation_end_date=dates[-1],
        )

        second = trades[trades["rebalance_sequence"] == 2]
        rename = second[second["event_type"] == "RENAME_NO_TRADE"].iloc[0]
        self.assertEqual(rename["security_id"], "security:a")
        self.assertEqual(rename["transaction_cost_usd"], 0.0)
        economic = second[second["event_type"] == "ECONOMIC_TRADE"].set_index("security_id")
        self.assertEqual(economic.at["security:a", "share_delta"], 2)
        self.assertEqual(economic.at["security:b", "share_delta"], -2)
        self.assertAlmostEqual(rebalances.iloc[1]["transaction_cost_usd"], 0.4)

    def test_same_ticker_but_new_security_id_is_a_two_sided_replacement(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame({"A": [100.0, 100.0, 100.0]}, index=dates)
        schedule = [
            {
                "decision_date": "2024-01-01",
                "execution_date": dates[0],
                "targets": {"security:old-member": _target("A", 1.0)},
            },
            {
                "decision_date": dates[0],
                "execution_date": dates[1],
                "targets": {"security:new-member": _target("A", 1.0)},
            },
        ]

        _, rebalances, trades, _ = simulate_dynamic_security_id_whole_lot_path(
            prices,
            schedule,
            initial_cash_usd=1000.0,
            minimum_cash_buffer_usd=100.0,
            transaction_cost_bps=10.0,
            valuation_end_date=dates[-1],
        )

        second = trades[
            (trades["rebalance_sequence"] == 2)
            & (trades["event_type"] == "ECONOMIC_TRADE")
        ].set_index("security_id")
        self.assertEqual(second.at["security:old-member", "action"], "SELL")
        self.assertEqual(second.at["security:new-member", "action"], "BUY")
        self.assertAlmostEqual(second.at["security:old-member", "transaction_cost_usd"], 0.8)
        self.assertAlmostEqual(second.at["security:new-member", "transaction_cost_usd"], 0.8)
        self.assertAlmostEqual(rebalances.iloc[1]["transaction_cost_usd"], 1.6)

    def test_missing_added_security_execution_price_fails_closed(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame({"A": [100, 100, 100], "B": [100, np.nan, 100]}, index=dates)
        schedule = [
            {
                "decision_date": "2024-01-01",
                "execution_date": dates[0],
                "targets": {"security:a": _target("A", 1.0)},
            },
            {
                "decision_date": dates[0],
                "execution_date": dates[1],
                "targets": {"security:b": _target("B", 1.0)},
            },
        ]
        with self.assertRaisesRegex(NdxDynamicWholeLotPathError, "required price"):
            simulate_dynamic_security_id_whole_lot_path(
                prices,
                schedule,
                initial_cash_usd=1000,
                minimum_cash_buffer_usd=100,
                valuation_end_date=dates[-1],
            )

    def test_missing_active_daily_price_fails_closed(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame({"A": [100.0, np.nan, 102.0]}, index=dates)
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": dates[0],
            "targets": {"security:a": _target("A", 1.0)},
        }]
        with self.assertRaisesRegex(NdxDynamicWholeLotPathError, "required price"):
            simulate_dynamic_security_id_whole_lot_path(
                prices,
                schedule,
                initial_cash_usd=1000,
                minimum_cash_buffer_usd=100,
                valuation_end_date=dates[-1],
            )

    def test_removed_security_requires_an_exit_price(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame({"A": [100, np.nan, np.nan], "B": [100, 100, 100]}, index=dates)
        schedule = [
            {
                "decision_date": "2024-01-01",
                "execution_date": dates[0],
                "targets": {"security:a": _target("A", 1.0)},
            },
            {
                "decision_date": dates[0],
                "execution_date": dates[1],
                "targets": {"security:b": _target("B", 1.0)},
            },
        ]
        with self.assertRaisesRegex(NdxDynamicWholeLotPathError, "required price"):
            simulate_dynamic_security_id_whole_lot_path(
                prices,
                schedule,
                initial_cash_usd=1000,
                minimum_cash_buffer_usd=100,
                valuation_end_date=dates[-1],
            )

    def test_decision_must_strictly_precede_execution(self):
        date = pd.Timestamp("2024-01-02")
        prices = pd.DataFrame({"A": [100]}, index=[date])
        schedule = [{
            "decision_date": date,
            "execution_date": date,
            "targets": {"security:a": _target("A", 1.0)},
        }]
        with self.assertRaisesRegex(NdxDynamicWholeLotPathError, "must precede"):
            simulate_dynamic_security_id_whole_lot_path(
                prices,
                schedule,
                initial_cash_usd=1000,
                minimum_cash_buffer_usd=100,
                valuation_end_date=date,
            )

    def test_execution_dates_must_be_sorted_and_unique(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame({"A": [100, 100, 100]}, index=dates)
        base = {"targets": {"security:a": _target("A", 1.0)}}
        unsorted = [
            {**base, "decision_date": dates[0], "execution_date": dates[2]},
            {**base, "decision_date": "2024-01-01", "execution_date": dates[1]},
        ]
        duplicate = [
            {**base, "decision_date": "2024-01-01", "execution_date": dates[1]},
            {**base, "decision_date": dates[0], "execution_date": dates[1]},
        ]
        for schedule, message in [(unsorted, "sorted"), (duplicate, "unique")]:
            with self.subTest(message=message):
                with self.assertRaisesRegex(NdxDynamicWholeLotPathError, message):
                    simulate_dynamic_security_id_whole_lot_path(
                        prices,
                        schedule,
                        initial_cash_usd=1000,
                        minimum_cash_buffer_usd=100,
                        valuation_end_date=dates[-1],
                    )

    def test_one_ticker_cannot_represent_two_security_ids_at_same_event(self):
        date = pd.Timestamp("2024-01-02")
        prices = pd.DataFrame({"A": [100]}, index=[date])
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": date,
            "targets": {
                "security:a": _target("A", 0.5),
                "security:b": _target("A", 0.5),
            },
        }]
        with self.assertRaisesRegex(NdxDynamicWholeLotPathError, "multiple security_ids"):
            simulate_dynamic_security_id_whole_lot_path(
                prices,
                schedule,
                initial_cash_usd=1000,
                minimum_cash_buffer_usd=100,
                valuation_end_date=date,
            )

    def test_explicit_cutoff_makes_post_cutoff_prices_irrelevant(self):
        dates = pd.date_range("2024-01-02", periods=5, freq="B")
        first_prices = pd.DataFrame({"A": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=dates)
        second_prices = first_prices.copy()
        second_prices.loc[dates[3]:, "A"] = [999_999.0, np.nan]
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": dates[0],
            "targets": {"security:a": _target("A", 1.0)},
        }]

        first = simulate_dynamic_security_id_whole_lot_path(
            first_prices,
            schedule,
            initial_cash_usd=1000,
            minimum_cash_buffer_usd=100,
            valuation_end_date=dates[2],
        )
        second = simulate_dynamic_security_id_whole_lot_path(
            second_prices,
            schedule,
            initial_cash_usd=1000,
            minimum_cash_buffer_usd=100,
            valuation_end_date=dates[2],
        )

        self.assertEqual(first[0], second[0])
        for first_frame, second_frame in zip(first[1:], second[1:]):
            pd.testing.assert_frame_equal(first_frame, second_frame)
        self.assertEqual(first[0]["maximum_price_date_used"], dates[2].date().isoformat())

    def test_end_date_cannot_precede_last_execution(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        prices = pd.DataFrame({"A": [100, 100, 100]}, index=dates)
        schedule = [
            {
                "decision_date": "2024-01-01",
                "execution_date": dates[0],
                "targets": {"security:a": _target("A", 1.0)},
            },
            {
                "decision_date": dates[0],
                "execution_date": dates[2],
                "targets": {"security:a": _target("A", 1.0)},
            },
        ]
        with self.assertRaisesRegex(NdxDynamicWholeLotPathError, "final execution"):
            simulate_dynamic_security_id_whole_lot_path(
                prices,
                schedule,
                initial_cash_usd=1000,
                minimum_cash_buffer_usd=100,
                valuation_end_date=dates[1],
            )

    def test_cost_buffer_failure_never_drops_target_below_one_share(self):
        date = pd.Timestamp("2024-01-02")
        prices = pd.DataFrame({"A": [50.0], "B": [50.0]}, index=[date])
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": date,
            "targets": {
                "security:a": _target("A", 0.5),
                "security:b": _target("B", 0.5),
            },
        }]
        with self.assertRaisesRegex(NdxDynamicWholeLotPathError, "positive lots cannot be preserved"):
            simulate_dynamic_security_id_whole_lot_path(
                prices,
                schedule,
                initial_cash_usd=200,
                minimum_cash_buffer_usd=100,
                transaction_cost_bps=10,
                valuation_end_date=date,
            )


if __name__ == "__main__":
    unittest.main()
