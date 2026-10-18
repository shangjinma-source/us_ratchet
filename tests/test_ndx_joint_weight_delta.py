import unittest

import pandas as pd

from backtest.ndx_joint_weight_delta import build_joint_weight_delta_plan, SUPPORTED_WEIGHT_SPECS
from backtest.ndx_two_stage_joint_coverage import select_joint_coverage_security_sets


def fixture():
    rows = []
    for number in range(17):
        rows.append(dict(
            tickers="AMAT;AVGO;CDNS;GOOG" if number == 16 else f"A{number:02};B{number:02};C{number:02};D{number:02}",
            weight_spec="equal_weight", holding_count=4, return_p50=-number / 100,
            return_p10=-number / 100 - .1, max_drawdown_p90=.1 + number / 100,
            target_012922_distance=number / 100, return_p50_vs_012922=-.1,
            return_p10_vs_012922=-.1, max_drawdown_p50_vs_012922=.1,
            max_drawdown_p90_vs_012922=.1,
            paired_return_p50_vs_incumbent=.1 if number == 16 else -.1,
            paired_return_p10_vs_incumbent=-.1,
            paired_drawdown_cost_p50_vs_incumbent=.1,
            paired_drawdown_cost_p90_vs_incumbent=.1))
    return pd.DataFrame(rows)


def coordinate():
    return dict(source_batch="exact_v3", universe_track="strict", selection_date="2024-05-01",
                decision_data_end="2024-04-30", holding_count=4, child_manifest_sha256="a" * 64)


def plan(frame=None, scope=None, specs=SUPPORTED_WEIGHT_SPECS, **kwargs):
    return build_joint_weight_delta_plan(fixture() if frame is None else frame,
                                        coordinate=coordinate() if scope is None else scope,
                                        second_stage_weight_specs=specs, **kwargs)


class JointWeightDeltaTests(unittest.TestCase):
    def test_real_selector_delta_cartesian_product(self):
        frame = fixture()
        before = frame.copy(deep=True)
        result = plan(frame)
        selected = select_joint_coverage_security_sets(frame, selection_date="2024-05-01",
                                                       decision_data_end="2024-04-30")
        delta = set(selected["selected"].tickers) - set(selected["legacy_control"].tickers)
        self.assertEqual(delta, {"AMAT;AVGO;CDNS;GOOG"})
        self.assertEqual({(task["tickers"], task["weight_spec"]) for task in result["tasks"]},
                         {(ticker, spec) for ticker in delta for spec in SUPPORTED_WEIGHT_SPECS})
        self.assertEqual(len(result["tasks"]), 2)
        for task in result["tasks"]:
            self.assertIn("USER_PREFERENCE", task["second_stage_selection_tags"])
            for field, value in coordinate().items():
                self.assertEqual(task[field], value)
        self.assertFalse(result["audit"]["training_performed"])
        self.assertFalse(result["audit"]["promotion_allowed"])
        self.assertFalse(result["audit"]["source_authenticity_verified"])
        pd.testing.assert_frame_equal(before, frame)

    def test_stable_jobs_and_source_identity(self):
        first = plan()
        self.assertEqual(first, plan(fixture().iloc[::-1], specs=SUPPORTED_WEIGHT_SPECS[::-1]))
        for field, value in [("source_batch", "other"), ("universe_track", "adjacent"),
                             ("selection_date", "2024-05-02"),
                             ("decision_data_end", "2024-04-29"),
                             ("child_manifest_sha256", "b" * 64)]:
            changed = coordinate(); changed[field] = value
            self.assertTrue({job["job_id"] for job in first["tasks"]}.isdisjoint(
                job["job_id"] for job in plan(scope=changed)["tasks"]))

    def test_empty_delta_valid(self):
        result = plan(fixture().iloc[:16])
        self.assertEqual(result["tasks"], [])
        self.assertEqual(result["audit"]["planned_task_count"], 0)

    def test_invalid_specs_and_coordinates_rejected(self):
        for specs in [[], [SUPPORTED_WEIGHT_SPECS[0]] * 2, ["equal_weight"], "bad", [None]]:
            with self.subTest(specs=specs), self.assertRaises(ValueError):
                plan(specs=specs)
        for field, value in [("holding_count", 5), ("holding_count", True),
                             ("child_manifest_sha256", "A" * 64),
                             ("source_batch", " spaced "), ("decision_data_end", "2024-05-01")]:
            changed = coordinate(); changed[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                plan(scope=changed)
        changed = coordinate(); changed["unbound_field"] = "wrong"
        with self.assertRaises(ValueError):
            plan(scope=changed)

    def test_input_source_mismatch_rejected(self):
        for field in coordinate():
            if field == "holding_count":
                continue
            frame = fixture(); frame[field] = "different"
            with self.subTest(field=field), self.assertRaises(ValueError):
                plan(frame)
        frame = fixture()
        frame["child_manifest_sha256"] = pd.Series([pd.NA] * len(frame), dtype="string")
        with self.assertRaises(ValueError):
            plan(frame)

    def test_all_pareto_ties_and_dynamic_k_are_retained(self):
        frame = fixture(); frame["paired_return_p50_vs_incumbent"] = -.1
        frame["tickers"] = [f"T{number:02}" for number in range(len(frame))]
        frame["holding_count"] = 1
        changed = coordinate(); changed["holding_count"] = 1
        result = plan(frame, scope=changed, per_frontier_limit=1)
        self.assertEqual(result["audit"]["selected_count"], 17)
        self.assertEqual(len(result["tasks"]), 32)
        self.assertTrue(all(task["holding_count"] == 1 for task in result["tasks"]))


if __name__ == "__main__":
    unittest.main()
