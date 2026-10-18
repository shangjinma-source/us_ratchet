import copy
import math
import unittest

from backtest.ndx_whole_lot_repair_diagnostic import (
    NdxWholeLotRepairDiagnosticError,
    project_whole_lot_rebalance,
)


class NdxWholeLotRepairDiagnosticTests(unittest.TestCase):
    def _contract(self):
        return {
            "minimum_cash_buffer_usd": 100.0,
            "transaction_cost_bps": 10.0,
            "max_single_weight": 0.45,
            "min_single_weight": 0.05,
            "top_weight_cap": 0.80,
            "minimum_effective_n_ratio": 0.70,
            "risk_chain_top1_cap": 0.55,
        }

    def test_locked_k14_floor_failure_has_fee_aware_feasible_projection(self):
        tickers = [
            "ADBE", "ADI", "AMZN", "AVGO", "BKR", "CDNS", "CSGP",
            "FTNT", "GOOGL", "PDD", "QCOM", "SNPS", "TEAM", "TXN",
        ]
        current_shares = {
            "ADBE": 4, "ADI": 13, "AMZN": 16, "AVGO": 2, "BKR": 92,
            "CDNS": 9, "CSGP": 31, "FTNT": 39, "GOOGL": 18, "PDD": 20,
            "QCOM": 18, "SNPS": 4, "TEAM": 10, "TXN": 16,
        }
        prices = {
            "ADBE": 567.94, "ADI": 194.66, "AMZN": 177.58,
            "AVGO": 1402.26, "BKR": 29.43, "CDNS": 317.31,
            "CSGP": 88.59, "FTNT": 71.39, "GOOGL": 133.35,
            "PDD": 122.12, "QCOM": 166.56, "SNPS": 594.32,
            "TEAM": 207.60, "TXN": 172.44,
        }
        risk_chains = {
            "ADBE": "cloud_application_software", "ADI": "analog_power",
            "AMZN": "internet_ecommerce", "AVGO": "diversified_technology",
            "BKR": "energy_technology", "CDNS": "eda_ip",
            "CSGP": "internet_ecommerce", "FTNT": "cybersecurity",
            "GOOGL": "platform_advertising", "PDD": "internet_ecommerce",
            "QCOM": "wireless_semiconductor", "SNPS": "eda_ip",
            "TEAM": "cloud_application_software", "TXN": "analog_power",
        }
        before = copy.deepcopy(current_shares)
        result = project_whole_lot_rebalance(
            current_shares=current_shares,
            current_cash_usd=1684.5235499999978,
            prices=prices,
            target_weights={ticker: 1.0 / len(tickers) for ticker in tickers},
            risk_chain_by_ticker=risk_chains,
            max_evaluations=1 << len(tickers),
            **self._contract(),
        )
        self.assertEqual(current_shares, before)
        self.assertEqual(result["status"], "FEASIBLE_RESEARCH_PROJECTION_FOUND")
        self.assertTrue(result["search_complete"])
        self.assertTrue(result["feasible_projection_found"])
        self.assertEqual(result["evaluations_completed"], 1 << 14)
        self.assertEqual(result["floor_shares"]["AVGO"], 1)
        self.assertEqual(result["projected_shares"]["AVGO"], 2)
        self.assertGreaterEqual(result["posttrade_cash_usd"], 100.0)
        self.assertGreaterEqual(result["minimum_single_weight"], 0.05)
        self.assertLessEqual(result["maximum_single_weight"], 0.45)
        self.assertLessEqual(result["top3_weight"], 0.80)
        self.assertGreaterEqual(result["effective_n"], 0.70 * 14)
        self.assertLessEqual(result["risk_chain_top1_weight"], 0.55)
        self.assertAlmostEqual(result["accounting_conservation_error_usd"], 0.0, places=8)
        self.assertAlmostEqual(
            result["transaction_cost_usd"],
            result["traded_notional_usd"] * 10.0 / 10_000.0,
            places=10,
        )
        self.assertFalse(result["portfolio_optimality_claimed"])
        self.assertFalse(result["admission_claimed"])
        self.assertFalse(result["order_creation_allowed"])

    def test_dynamic_k_four_uses_complete_deterministic_neighborhood(self):
        result = project_whole_lot_rebalance(
            current_shares={ticker: 0 for ticker in "ABCD"},
            current_cash_usd=10_001.0,
            prices={"A": 101.0, "B": 103.0, "C": 107.0, "D": 109.0},
            target_weights={ticker: 0.25 for ticker in "ABCD"},
            risk_chain_by_ticker={ticker: ticker for ticker in "ABCD"},
            max_evaluations=16,
            **self._contract(),
        )
        self.assertEqual(result["search_space_size"], 16)
        self.assertEqual(result["evaluations_completed"], 16)
        self.assertTrue(result["feasible_projection_found"])
        self.assertTrue(all(isinstance(value, int) for value in result["projected_shares"].values()))

    def test_search_budget_exhaustion_returns_no_partial_allocation(self):
        tickers = list("ABCDEFGHI")
        result = project_whole_lot_rebalance(
            current_shares={ticker: 1 for ticker in tickers},
            current_cash_usd=10_001.0,
            prices={ticker: 100.0 for ticker in tickers},
            target_weights={ticker: 1 / len(tickers) for ticker in tickers},
            risk_chain_by_ticker={ticker: ticker for ticker in tickers},
            max_evaluations=128,
            **self._contract(),
        )
        self.assertEqual(result["status"], "RESEARCH_SEARCH_BUDGET_EXHAUSTED")
        self.assertFalse(result["search_complete"])
        self.assertFalse(result["feasible_projection_found"])
        self.assertEqual(result["projected_shares"], {})
        self.assertFalse(result["full_integer_space_infeasibility_claimed"])

    def test_exact_integer_target_has_one_option_not_floor_plus_one(self):
        result = project_whole_lot_rebalance(
            current_shares={"A": 26, "B": 26, "C": 26, "D": 26},
            current_cash_usd=100.0,
            prices={ticker: 100.0 for ticker in "ABCD"},
            target_weights={ticker: 0.25 for ticker in "ABCD"},
            risk_chain_by_ticker={ticker: ticker for ticker in "ABCD"},
            max_evaluations=1,
            **self._contract(),
        )
        # Pre-trade equity is 10,500 and investable equity is exactly 10,400,
        # so each target coordinate is exactly 26 shares.
        self.assertEqual(result["search_space_size"], 1)
        self.assertEqual(result["evaluations_completed"], 1)
        self.assertEqual(result["projected_shares"], {ticker: 26 for ticker in "ABCD"})

    def test_complete_neighborhood_failure_does_not_claim_full_integer_infeasibility(self):
        result = project_whole_lot_rebalance(
            current_shares={"A": 0},
            current_cash_usd=1_000.0,
            prices={"A": 100.0},
            target_weights={"A": 1.0},
            risk_chain_by_ticker={"A": "chain_a"},
            max_evaluations=2,
            **self._contract(),
        )
        self.assertEqual(
            result["status"],
            "NO_FEASIBLE_PROJECTION_IN_COMPLETE_FLOOR_CEIL_NEIGHBORHOOD",
        )
        self.assertTrue(result["search_complete"])
        self.assertFalse(result["full_integer_space_infeasibility_claimed"])

    def test_nonfinite_and_fractional_inputs_fail_closed(self):
        base = dict(
            current_shares={"A": 1, "B": 1, "C": 1, "D": 1},
            current_cash_usd=1_000.0,
            prices={ticker: 100.0 for ticker in "ABCD"},
            target_weights={ticker: 0.25 for ticker in "ABCD"},
            risk_chain_by_ticker={ticker: ticker for ticker in "ABCD"},
            **self._contract(),
        )
        bad_price = copy.deepcopy(base)
        bad_price["prices"]["A"] = math.nan
        with self.assertRaises(NdxWholeLotRepairDiagnosticError):
            project_whole_lot_rebalance(**bad_price)
        bad_shares = copy.deepcopy(base)
        bad_shares["current_shares"]["A"] = 1.5
        with self.assertRaises(NdxWholeLotRepairDiagnosticError):
            project_whole_lot_rebalance(**bad_shares)

        bad_ticker = copy.deepcopy(base)
        bad_ticker["current_shares"] = {" A": 1, "B": 1, "C": 1, "D": 1}
        with self.assertRaises(NdxWholeLotRepairDiagnosticError):
            project_whole_lot_rebalance(**bad_ticker)

        bad_chain = copy.deepcopy(base)
        bad_chain["risk_chain_by_ticker"]["A"] = None
        with self.assertRaises(NdxWholeLotRepairDiagnosticError):
            project_whole_lot_rebalance(**bad_chain)

        overflow = copy.deepcopy(base)
        overflow["current_cash_usd"] = 1e308
        overflow["prices"]["A"] = 5e-324
        with self.assertRaises(NdxWholeLotRepairDiagnosticError):
            project_whole_lot_rebalance(**overflow)


if __name__ == "__main__":
    unittest.main()
