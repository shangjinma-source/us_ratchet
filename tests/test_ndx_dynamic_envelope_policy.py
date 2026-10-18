"""Unit specifications for the new one-sided research hypothesis."""
import copy
import unittest

import pandas as pd

from backtest.ndx_dynamic_envelope_policy import evaluate_componentwise_envelope_candidates


def candidate(identifier="first", **changes):
    row = dict(source_batch="source", universe_track="strict_technology",
               selection_date="2024-05-01", decision_data_end="2024-04-30",
               portfolio_id=identifier, holding_count=4, weight_spec="equal_weight",
               tickers="AMAT;AVGO;CDNS;GOOG", weights="AMAT:.25;AVGO:.25;CDNS:.25;GOOG:.25",
               security_ids="security:a;security:b;security:c;security:d",
               issuer_ids="issuer:a;issuer:b;issuer:c;issuer:d", risk_chains="a;b;c;d",
               declared_constraints_passed=True, return_p50=.2, return_p10=.1,
               return_basis="NET_OF_MODELED_ENTRY_TURNOVER_COST",
               fit_strictly_before_evaluation=True, rolling_fit_window_count=3,
               last_fit_evaluation_boundary="2023-10-27<2023-10-30",
               max_drawdown_p50=.1, max_drawdown_p90=.15,
               return_p50_vs_012922=.02, return_p10_vs_012922=.01,
               max_drawdown_p50_vs_012922=-.01, max_drawdown_p90_vs_012922=-.02,
               paired_return_p50_vs_incumbent=.02, paired_return_p10_vs_incumbent=.01,
               paired_drawdown_cost_p50_vs_incumbent=-.02,
               paired_drawdown_cost_p90_vs_incumbent=-.01)
    row.update(changes)
    return row


def evaluate(*rows):
    return evaluate_componentwise_envelope_candidates(pd.DataFrame(rows))


class OneSidedEnvelopePolicyTests(unittest.TestCase):
    def test_dominance_does_not_penalize_large_outperformance(self):
        result = evaluate(candidate(return_p50_vs_012922=4., max_drawdown_p90_vs_012922=-.8))
        row = result["groups"][0]["candidates"][0]
        self.assertTrue(row["dual_benchmark_qualified"])
        self.assertEqual(sum(row["fund"]["deficits"].values()), 0.)
        self.assertFalse(result["existing_formal_gate_equivalent"])
        self.assertFalse(result["admission_allowed"])

    def test_one_failed_dimension_cannot_be_offset(self):
        row = evaluate(candidate(return_p50_vs_012922=100., return_p10_vs_012922=-.001))["groups"][0]["candidates"][0]
        self.assertFalse(row["fund"]["componentwise_noninferior"])
        self.assertEqual(row["fund"]["deficits"]["return_p10"], .001)
        self.assertFalse(row["dual_benchmark_qualified"])

    def test_exact_ties_are_noninferior_but_not_strict(self):
        row = candidate()
        for key in list(row):
            if "_vs_012922" in key or "_vs_incumbent" in key:
                row[key] = 0.
        diagnostic = evaluate(row)["groups"][0]["candidates"][0]
        self.assertTrue(diagnostic["fund"]["componentwise_noninferior"])
        self.assertFalse(diagnostic["fund"]["has_strict_improvement"])
        self.assertFalse(diagnostic["dual_benchmark_qualified"])

    def test_ineligible_preference_is_retained(self):
        group = evaluate(candidate(declared_constraints_passed=False))["groups"][0]
        self.assertEqual(len(group["candidates"]), 1)
        self.assertTrue(group["candidates"][0]["user_preference_reference"])
        self.assertFalse(group["candidates"][0]["dual_benchmark_qualified"])
        self.assertEqual(group["dual_benchmark_qualified_ids"], [])

    def test_deficit_pareto_keeps_tradeoffs_and_equal_vectors(self):
        group = evaluate(candidate("a", return_p50_vs_012922=-.1),
                         candidate("b", return_p10_vs_012922=-.1),
                         candidate("c", return_p50_vs_012922=-.2, return_p10_vs_012922=-.2),
                         candidate("d", return_p50_vs_012922=-.1))["groups"][0]
        self.assertEqual(group["deficit_pareto_ids"], ["a", "b", "d"])
        self.assertEqual(len(group["candidates"]), 4)

    def test_rows_are_order_independent_and_sources_separate(self):
        rows = [candidate("b"), candidate("a"), candidate("a", source_batch="other")]
        self.assertEqual(evaluate(*rows), evaluate(*reversed(rows)))
        self.assertEqual(len(evaluate(*rows)["groups"]), 2)

    def test_duplicate_candidate_and_inconsistent_cutoff_rejected(self):
        for rows in [(candidate(), candidate()),
                     (candidate(), candidate("two", decision_data_end="2024-04-29"))]:
            with self.assertRaises(ValueError):
                evaluate(*rows)

    def test_strict_dates_identity_and_finite_metrics(self):
        for changes in [dict(selection_date="2024-05-01T12:00:00"),
                        dict(decision_data_end="2024-05-01"),
                        dict(issuer_ids="issuer:a;issuer:a;issuer:c;issuer:d"),
                        dict(weights="AMAT:.3;AVGO:.25;CDNS:.25;GOOG:.25"),
                        dict(return_p50_vs_012922=float("nan")),
                        dict(paired_return_p10_vs_incumbent=True),
                        dict(holding_count=4.5)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                evaluate(candidate(**changes))

    def test_missing_paired_metrics_cannot_be_inferred(self):
        row = candidate()
        del row["paired_return_p50_vs_incumbent"]
        row["incumbent_return_p50"] = .1
        with self.assertRaises(ValueError):
            evaluate(row)

    def test_no_hard_cardinality_limit(self):
        count = 21
        tickers = [f"T{number}" for number in range(count)]
        row = candidate(holding_count=count, tickers=";".join(tickers),
                        weights=";".join(f"{ticker}:{1/count}" for ticker in tickers),
                        security_ids=";".join(f"security:{ticker}" for ticker in tickers),
                        issuer_ids=";".join(f"issuer:{ticker}" for ticker in tickers),
                        risk_chains=";".join(tickers))
        self.assertEqual(evaluate(row)["groups"][0]["candidates"][0]["holding_count"], 21)

    def test_input_is_not_mutated_and_future_extras_are_not_used(self):
        row = candidate(future_return=999.)
        frame = pd.DataFrame([row]); before = copy.deepcopy(frame)
        first = evaluate_componentwise_envelope_candidates(frame)
        pd.testing.assert_frame_equal(frame, before)
        frame["future_return"] = -999.
        self.assertEqual(first, evaluate_componentwise_envelope_candidates(frame))


if __name__ == "__main__":
    unittest.main()
