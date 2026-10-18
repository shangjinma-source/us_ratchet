import copy
import unittest

import numpy as np
import pandas as pd

from backtest.ndx_cardinality_discovery import evaluate_synthetic_portfolio, synthetic_fixture, search_synthetic_cardinality
from backtest.ndx_joint_weight_delta import build_joint_weight_delta_plan, SUPPORTED_WEIGHT_SPECS
from backtest.ndx_joint_weight_evaluation import evaluate_joint_weight_task


def fixture():
    universe, returns, target, incumbent = synthetic_fixture(seed=18, business_days=180)
    task = dict(tickers="ALFA;BETA;DELT;EPSI;GAMM", holding_count=5,
                decision_data_end="2020-09-09", selection_date="2020-09-10",
                weight_spec="constrained_fixed_shrinkage")
    nominal = (1 + returns).cumprod() * universe.set_index("ticker").synthetic_price
    contract = dict(window_days=42, step_days=21, transaction_cost_bps=10., fit_days=63,
                    shrinkage_intensity=.35, max_single_weight=.45, min_single_weight=.05,
                    top_weight_cap=.80, minimum_effective_n_ratio=.70, risk_chain_top1_cap=.55,
                    turnover_anchor_strength=.25, portfolio_cash_usd=5000.,
                    minimum_cash_buffer_usd=100., minimum_median_dollar_volume_usd=50_000_000.)
    inputs = dict(universe=universe, returns=returns, target_returns=target,
                  nominal_prices=nominal, incumbent_weights={x: 1 / len(incumbent) for x in incumbent},
                  contract=contract)
    return task, inputs


class JointWeightEvaluationTests(unittest.TestCase):
    def test_real_equal_stage_to_delta_plan_to_both_weight_evaluations(self):
        task, inputs = fixture()
        first_stage, _ = search_synthetic_cardinality(
            inputs["universe"], inputs["returns"], inputs["target_returns"],
            sorted(inputs["incumbent_weights"]), holding_count=2, exact_limit=100,
            beam_width=8, weight_specs=("equal_weight",),
            execution_prices=inputs["nominal_prices"],
            incumbent_weights=inputs["incumbent_weights"], **inputs["contract"])
        coordinate = dict(source_batch="SYNTHETIC_INTEGRATION", universe_track="strict_technology",
                          selection_date=task["selection_date"], holding_count=2,
                          decision_data_end=task["decision_data_end"], child_manifest_sha256="a" * 64)
        plan = build_joint_weight_delta_plan(first_stage, coordinate=coordinate,
                                            second_stage_weight_specs=SUPPORTED_WEIGHT_SPECS,
                                            per_frontier_limit=1)
        self.assertGreater(len(plan["tasks"]), 0)
        self.assertEqual(len(plan["tasks"]), plan["audit"]["newly_added_count"] * 2)
        for planned_task in plan["tasks"]:
            result = evaluate_joint_weight_task(planned_task, **inputs)
            self.assertEqual(result["tickers"], planned_task["tickers"])
            self.assertEqual(result["weight_spec"], planned_task["weight_spec"])
            self.assertEqual(result["holding_count"], 2)
            self.assertIn("paired_return_p10_vs_incumbent", result)
            self.assertIn("declared_constraints_passed", result)
            self.assertIn("whole_lot_path_return_net", result)
            self.assertFalse(result["promotion_allowed"])

    def test_two_actual_weight_models_match_direct_evaluator_without_input_mutation(self):
        for spec in ("constrained_fixed_shrinkage", "constrained_fixed_shrinkage_turnover_anchor"):
            task, inputs = fixture()
            task["weight_spec"] = spec
            before = copy.deepcopy(inputs)
            actual = evaluate_joint_weight_task(task, **inputs)
            expected = evaluate_synthetic_portfolio(
                tuple(task["tickers"].split(";")), inputs["universe"], inputs["returns"],
                inputs["target_returns"], sorted(inputs["incumbent_weights"]),
                weight_spec=spec, incumbent_weights=inputs["incumbent_weights"],
                execution_prices=inputs["nominal_prices"], **inputs["contract"])
            self.assertEqual(actual, expected)
            for key in ("universe", "returns", "nominal_prices"):
                pd.testing.assert_frame_equal(inputs[key], before[key], check_exact=True)
            pd.testing.assert_series_equal(inputs["target_returns"], before["target_returns"])
            self.assertEqual(inputs["contract"], before["contract"])

    def test_rejects_future_or_stale_input_calendar(self):
        for key, value in (("decision_data_end", "2020-09-08"),
                           ("decision_data_end", "2020-09-10"),
                           ("selection_date", "2020-09-09")):
            task, inputs = fixture()
            task[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                evaluate_joint_weight_task(task, **inputs)

    def test_requires_explicit_incumbent_cash_and_nominal_prices(self):
        for mutation in (lambda i: i.update(incumbent_weights=None),
                         lambda i: i["contract"].pop("portfolio_cash_usd"),
                         lambda i: i.update(nominal_prices=i["nominal_prices"].iloc[1:]),
                         lambda i: i.update(incumbent_weights={"ALFA": .5})):
            task, inputs = fixture()
            mutation(inputs)
            with self.assertRaises(ValueError):
                evaluate_joint_weight_task(task, **inputs)

    def test_rejects_nonfinite_panels_ambiguous_identity_and_negative_cost(self):
        mutations = (lambda i: i["returns"].iloc.__setitem__((0, 0), np.nan),
                     lambda i: i["universe"].loc.__setitem__((1, "security_id"), "s1"),
                     lambda i: i["contract"].update(transaction_cost_bps=-1.),
                     lambda i: i["contract"].update(step_days=True))
        for mutation in mutations:
            task, inputs = fixture()
            mutation(inputs)
            with self.assertRaises(ValueError):
                evaluate_joint_weight_task(task, **inputs)

    def test_rejects_boolean_and_string_numeric_cells(self):
        for field in ("returns", "target_returns", "nominal_prices", "universe"):
            for value in (True, "0.01"):
                task, inputs = fixture()
                if field == "universe":
                    inputs[field]["median_dollar_volume_usd"] = inputs[field]["median_dollar_volume_usd"].astype(object)
                    inputs[field].loc[0, "median_dollar_volume_usd"] = value
                else:
                    inputs[field] = inputs[field].astype(object)
                    if field == "target_returns":
                        inputs[field].iloc[0] = value
                    else:
                        inputs[field].iloc[0, 0] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    evaluate_joint_weight_task(task, **inputs)


if __name__ == "__main__":
    unittest.main()
