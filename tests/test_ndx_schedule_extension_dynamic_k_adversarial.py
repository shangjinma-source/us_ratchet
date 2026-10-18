from __future__ import annotations

import math
import unittest

import pandas as pd

from backtest import ndx_equal_weight_schedule_extension_runner as runner
from backtest.ndx_whole_lot_rebalance import (
    simulate_continuous_whole_lot_rebalance,
)


def _case(k: int):
    tickers = [f"T{index:02d}" for index in range(k)]
    dates = pd.bdate_range("2024-01-02", periods=70)
    prices = pd.DataFrame(
        {
            ticker: [100.0 + day * (index + 1) * 0.02 for day in range(70)]
            for index, ticker in enumerate(tickers)
        },
        index=dates,
    )
    weights = {ticker: 1.0 / k for ticker in tickers}
    schedule = [
        (dates[0], weights.copy()),
        (dates[21], weights.copy()),
    ]
    contract = {
        "risk_chain_by_ticker": {
            ticker: f"CHAIN_{index:02d}" for index, ticker in enumerate(tickers)
        },
        "portfolio_cash_usd": 25_000.0,
        "minimum_cash_buffer_usd": 100.0,
        "transaction_cost_bps": 10.0,
        **runner.LOCKED_RISK_THRESHOLDS,
    }
    original_summary, _ = simulate_continuous_whole_lot_rebalance(
        prices, schedule, **contract
    )
    expected = {
        field: original_summary[field] for field in runner.ORIGINAL_SUMMARY_FIELDS
    }
    candidate = {
        "candidate_key": f"{k:024x}",
        "candidate_identity_sha256": f"{k:064x}",
        "source_batch": runner.SOURCE_BATCH,
        "job_search_class": runner.JOB_SEARCH_CLASS,
        "evaluation_semantics_sha256": runner.EVALUATOR_SHA256,
        "universe_track": "strict_technology",
        "selection_date": runner.SELECTION_DATE,
        "portfolio_id": f"synthetic-dynamic-k{k}",
        "holding_count": k,
        "tickers": tickers,
        "weights": weights,
        "security_ids": [f"SECURITY_{index:02d}" for index in range(k)],
        "issuer_ids": [f"ISSUER_{index:02d}" for index in range(k)],
        "risk_chains": [f"CHAIN_{index:02d}" for index in range(k)],
        "source_failure_class": "SOURCE_REPORTED_ELIGIBLE",
        "source_failure_reasons": [],
        "expected_original_summary": expected,
    }
    return prices, schedule, contract, candidate


def _parse_shares(value: str) -> dict[str, int]:
    return {
        ticker: int(quantity)
        for ticker, quantity in (item.split(":", 1) for item in value.split(";"))
    }


def _assert_ledger_accounting(
    case: unittest.TestCase,
    prices: pd.DataFrame,
    schedule,
    contract,
) -> None:
    summary, ledger = simulate_continuous_whole_lot_rebalance(
        prices, schedule, **contract
    )
    tickers = list(prices.columns)
    previous_shares = {ticker: 0 for ticker in tickers}
    previous_cash = float(contract["portfolio_cash_usd"])
    total_notional = 0.0
    total_fees = 0.0
    for row in ledger.to_dict("records"):
        day = pd.Timestamp(row["rebalance_date"])
        marks = {ticker: float(prices.loc[day, ticker]) for ticker in tickers}
        shares = _parse_shares(row["shares"])
        buy = sum(
            max(0, shares[ticker] - previous_shares[ticker]) * marks[ticker]
            for ticker in tickers
        )
        sell = sum(
            max(0, previous_shares[ticker] - shares[ticker]) * marks[ticker]
            for ticker in tickers
        )
        traded = buy + sell
        fees = traded * float(contract["transaction_cost_bps"]) / 10_000.0
        expected_pretrade = previous_cash + sum(
            previous_shares[ticker] * marks[ticker] for ticker in tickers
        )
        expected_cash = previous_cash + sell - buy - fees
        case.assertTrue(math.isclose(row["pretrade_equity_usd"], expected_pretrade))
        case.assertTrue(math.isclose(row["traded_notional_usd"], traded))
        case.assertTrue(math.isclose(row["transaction_cost_usd"], fees))
        case.assertTrue(math.isclose(row["posttrade_cash_usd"], expected_cash))
        case.assertGreaterEqual(row["posttrade_cash_usd"], 100.0 - 1e-9)
        total_notional += traded
        total_fees += fees
        previous_shares = shares
        previous_cash = expected_cash
    case.assertTrue(
        math.isclose(summary["whole_lot_total_trade_notional_usd"], total_notional)
    )
    case.assertTrue(
        math.isclose(summary["whole_lot_total_transaction_cost_usd"], total_fees)
    )


class NdxScheduleExtensionDynamicKAdversarialTests(unittest.TestCase):
    def test_dynamic_k_paths_preserve_whole_lot_accounting_and_cadence(self) -> None:
        for k in (1, 7, 12):
            with self.subTest(k=k):
                prices, schedule, contract, candidate = _case(k)
                result = runner.diagnose_locked_equal_weight_candidate(
                    prices,
                    schedule,
                    candidate=candidate,
                    execution_contract=contract,
                )
                original = result["original_schedule_b"]
                continued = result["continued_schedule_a"]
                self.assertEqual(result["holding_count"], k)
                self.assertEqual(len(result["tickers"]), k)
                self.assertEqual(
                    original["summary"],
                    {
                        **candidate["expected_original_summary"],
                        "whole_lot_execution_mode": (
                            "CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_REAL_CLOSES"
                        ),
                    },
                )
                self.assertEqual(
                    continued["added_rebalance_dates"],
                    [
                        prices.index[42].date().isoformat(),
                        prices.index[63].date().isoformat(),
                    ],
                )
                for path in (original, continued):
                    summary = path["summary"]
                    audit = path["daily_risk_audit"]
                    self.assertEqual(
                        summary["whole_lot_terminal_value_usd"],
                        audit["terminal_value_usd"],
                    )
                    self.assertEqual(
                        summary["whole_lot_path_max_drawdown"],
                        audit["legacy_drawdown_without_initial_capital_peak"],
                    )
                    self.assertGreaterEqual(
                        audit["corrected_drawdown_with_initial_capital_peak"], 0.0
                    )
                extended = runner.extend_equal_weight_schedule_to_path_end(
                    prices, schedule, tickers=list(prices.columns)
                )
                _assert_ledger_accounting(self, prices, schedule, contract)
                _assert_ledger_accounting(self, prices, extended, contract)


if __name__ == "__main__":
    unittest.main()
