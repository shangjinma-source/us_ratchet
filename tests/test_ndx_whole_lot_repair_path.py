import math
import unittest

import pandas as pd

from backtest.ndx_whole_lot_rebalance import simulate_continuous_whole_lot_rebalance
from backtest.ndx_whole_lot_repair_path import (
    simulate_conditional_whole_lot_repair_path,
)


class NdxWholeLotRepairPathTests(unittest.TestCase):
    def _contract(self, tickers, *, same_chain=False):
        return {
            "risk_chain_by_ticker": {
                ticker: "same" if same_chain else f"chain_{ticker}"
                for ticker in tickers
            },
            "portfolio_cash_usd": 1_000.0,
            "minimum_cash_buffer_usd": 100.0,
            "transaction_cost_bps": 10.0,
            "max_single_weight": 0.45,
            "min_single_weight": 0.05,
            "top_weight_cap": 0.80,
            "minimum_effective_n_ratio": 0.70,
            "risk_chain_top1_cap": 0.55,
        }

    def _schedule(self, tickers, dates):
        return [
            (pd.Timestamp(date), {ticker: 1 / len(tickers) for ticker in tickers})
            for date in dates
        ]

    def test_no_repair_trigger_reuses_exact_legacy_summary_and_ledger(self):
        tickers = list("ABCD")
        index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
        prices = pd.DataFrame(
            [[100.0] * 4, [101.0, 99.0, 102.0, 98.0], [100.0] * 4],
            index=index,
            columns=tickers,
        )
        schedule = self._schedule(tickers, ["2024-01-02", "2024-01-04"])
        contract = self._contract(tickers)
        legacy_summary, legacy_ledger = simulate_continuous_whole_lot_rebalance(
            prices, schedule, **contract
        )
        result, ledger = simulate_conditional_whole_lot_repair_path(
            prices, schedule, **contract
        )
        self.assertTrue(result["legacy_no_trigger_path_reused_exactly"])
        self.assertEqual(result["repair_invocation_count"], 0)
        self.assertEqual(result["summary"], legacy_summary)
        self.assertEqual(ledger.to_dict("records"), legacy_ledger.to_dict("records"))
        self.assertEqual(
            result["summary"]["whole_lot_rebalance_trace_sha256"],
            legacy_summary["whole_lot_rebalance_trace_sha256"],
        )

    def test_conditional_repair_is_self_financing_across_periods(self):
        tickers = list("ABCD")
        index = pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        )
        prices = pd.DataFrame(
            [
                [100.0, 100.0, 100.0, 100.0],
                [110.0, 100.0, 100.0, 100.0],
                [140.0, 100.0, 100.0, 100.0],
                [130.0, 110.0, 110.0, 110.0],
            ],
            index=index,
            columns=tickers,
        )
        schedule = self._schedule(
            tickers, ["2024-01-02", "2024-01-04", "2024-01-05"]
        )
        contract = self._contract(tickers)
        legacy_summary, legacy_ledger = simulate_continuous_whole_lot_rebalance(
            prices, schedule, **contract
        )
        self.assertFalse(bool(legacy_ledger.iloc[1]["constraints_passed"]))
        result, ledger = simulate_conditional_whole_lot_repair_path(
            prices, schedule, max_repair_evaluations=16, **contract
        )
        self.assertTrue(result["search_complete"])
        self.assertGreaterEqual(result["successful_repair_count"], 1)
        self.assertEqual(result["unresolved_rebalance_count"], 0)
        self.assertTrue(result["execution_eligible"])
        for date, record in zip(pd.to_datetime(ledger["rebalance_date"]), ledger.to_dict("records")):
            marks = prices.loc[date]
            holdings = sum(
                int(part.split(":")[1]) * float(marks[part.split(":")[0]])
                for part in record["shares"].split(";")
            )
            self.assertAlmostEqual(
                record["posttrade_cash_usd"] + holdings,
                record["pretrade_equity_usd"] - record["transaction_cost_usd"],
                places=8,
            )
            self.assertAlmostEqual(
                record["transaction_cost_usd"],
                record["traded_notional_usd"] * 10.0 / 10_000.0,
                places=10,
            )
        self.assertEqual(result["daily_risk_audit"]["failure_session_count"], 0)
        self.assertFalse(result["admission_claimed"])
        self.assertFalse(result["order_creation_allowed"])

    def test_budget_exhaustion_marks_entire_path_incomplete_without_fallback(self):
        tickers = list("ABCD")
        prices = pd.DataFrame(
            [[140.0, 100.0, 100.0, 100.0]],
            index=pd.to_datetime(["2024-01-02"]),
            columns=tickers,
        )
        result, ledger = simulate_conditional_whole_lot_repair_path(
            prices,
            self._schedule(tickers, ["2024-01-02"]),
            max_repair_evaluations=1,
            **self._contract(tickers, same_chain=True),
        )
        self.assertEqual(result["status"], "INCOMPLETE_REPAIR_SEARCH_BUDGET_EXHAUSTED")
        self.assertFalse(result["search_complete"])
        self.assertIsNone(result["summary"])
        self.assertIsNone(result["daily_risk_audit"])
        self.assertFalse(result["execution_eligible"])
        self.assertTrue(ledger.empty)

    def test_complete_local_no_solution_is_explicitly_unresolved(self):
        tickers = ["A"]
        prices = pd.DataFrame(
            [[100.0], [105.0]],
            index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
            columns=tickers,
        )
        result, ledger = simulate_conditional_whole_lot_repair_path(
            prices,
            self._schedule(tickers, ["2024-01-02"]),
            max_repair_evaluations=2,
            **self._contract(tickers),
        )
        self.assertEqual(
            result["status"], "COMPLETE_WITH_UNRESOLVED_REBALANCE_FAILURES"
        )
        self.assertEqual(result["unresolved_rebalance_count"], 1)
        self.assertFalse(result["execution_eligible"])
        self.assertFalse(result["full_integer_space_infeasibility_claimed"])
        self.assertFalse(ledger.iloc[0]["constraints_passed"])

    def test_nonfinite_contract_fails_closed(self):
        tickers = list("ABCD")
        prices = pd.DataFrame(
            [[100.0] * 4],
            index=pd.to_datetime(["2024-01-02"]),
            columns=tickers,
        )
        contract = self._contract(tickers)
        contract["transaction_cost_bps"] = math.nan
        with self.assertRaisesRegex(ValueError, "finite numeric"):
            simulate_conditional_whole_lot_repair_path(
                prices, self._schedule(tickers, ["2024-01-02"]), **contract
            )

    def test_noncanonical_dates_duplicate_columns_and_weight_scale_fail_closed(self):
        tickers = list("ABCD")
        contract = self._contract(tickers)
        prices = pd.DataFrame(
            [[100.0] * 4],
            index=pd.to_datetime(["2024-01-02"]),
            columns=tickers,
        )
        for bad_date in (
            "2024-01-02T12:00:00",
            pd.Timestamp("2024-01-02", tz="UTC"),
            pd.NaT,
        ):
            with self.subTest(bad_date=str(bad_date)), self.assertRaises(ValueError):
                simulate_conditional_whole_lot_repair_path(
                    prices,
                    [(bad_date, {ticker: 0.25 for ticker in tickers})],
                    **contract,
                )
        duplicate_columns = prices.copy()
        duplicate_columns.columns = ["A", "A", "C", "D"]
        with self.assertRaisesRegex(ValueError, "price coordinates"):
            simulate_conditional_whole_lot_repair_path(
                duplicate_columns,
                self._schedule(tickers, ["2024-01-02"]),
                **contract,
            )
        with self.assertRaisesRegex(ValueError, "sum to one"):
            simulate_conditional_whole_lot_repair_path(
                prices,
                [(pd.Timestamp("2024-01-02"), {ticker: 2.0 for ticker in tickers})],
                **contract,
            )


if __name__ == "__main__":
    unittest.main()
