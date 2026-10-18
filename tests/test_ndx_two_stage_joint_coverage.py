import unittest
import pandas as pd

from backtest.ndx_two_stage_joint_coverage import select_joint_coverage_security_sets
from backtest.ndx_cardinality_discovery import select_multifrontier_security_sets


def rows():
    values = []
    for number in range(17):
        preference = number == 16
        values.append(dict(tickers="AMAT;AVGO;CDNS;GOOG" if preference else f"A{number:02};B{number:02};C{number:02};D{number:02}",
                           holding_count=4, weight_spec="equal_weight",
                           return_p50=-number / 100, return_p10=-number / 100 - .1,
                           max_drawdown_p90=.1 + number / 100, target_012922_distance=number / 100,
                           return_p50_vs_012922=-.1, return_p10_vs_012922=-.1,
                           max_drawdown_p50_vs_012922=.1, max_drawdown_p90_vs_012922=.1,
                           paired_return_p50_vs_incumbent=.1 if preference else -.1,
                           paired_return_p10_vs_incumbent=-.1,
                           paired_drawdown_cost_p50_vs_incumbent=.1,
                           paired_drawdown_cost_p90_vs_incumbent=.1))
    return pd.DataFrame(values)


def select(frame, **kwargs):
    return select_joint_coverage_security_sets(frame, selection_date="2024-05-01",
                                               decision_data_end="2024-04-30", **kwargs)


class JointCoverageTests(unittest.TestCase):
    def test_seventeenth_paired_winner_and_preference_not_lost(self):
        frame = rows(); old = select_multifrontier_security_sets(frame, per_frontier_limit=16)
        self.assertNotIn("AMAT;AVGO;CDNS;GOOG", old.tickers.tolist())
        result = select(frame)
        pd.testing.assert_frame_equal(old, result["legacy_control"])
        chosen = result["selected"].set_index("tickers").loc["AMAT;AVGO;CDNS;GOOG"]
        self.assertIn("PAIRED_INCUMBENT_RETURN_P50", chosen.second_stage_selection_tags)
        self.assertIn("USER_PREFERENCE", chosen.second_stage_selection_tags)
        self.assertEqual(result["audit"]["newly_added_count"], 1)
        self.assertFalse(result["audit"]["admission_allowed"])

    def test_all_equal_deficit_vectors_retained_without_pareto_truncation(self):
        frame = rows()
        frame["paired_return_p50_vs_incumbent"] = -.1
        result = select(frame, per_frontier_limit=1, pareto_block_size=1)
        self.assertEqual(result["audit"]["deficit_pareto_count"], 17)
        self.assertEqual(len(result["selected"]), 17)

    def test_block_size_and_row_order_do_not_change_output(self):
        frame = rows()
        first = select(frame, pareto_block_size=1)
        second = select(frame.iloc[::-1], pareto_block_size=7)
        pd.testing.assert_frame_equal(first["selected"], second["selected"])
        self.assertEqual(first["audit"], second["audit"])

    def test_invalid_inputs_fail_closed(self):
        for changes in [dict(weight_spec="constrained_fixed_shrinkage"),
                        dict(holding_count=5), dict(return_p50=float("nan")),
                        dict(tickers="A;A;C;D")]:
            frame = rows(); frame.loc[0, list(changes)] = list(changes.values())
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                select(frame)
        frame = rows(); frame.loc[1,"tickers"] = frame.loc[0,"tickers"]
        with self.assertRaises(ValueError): select(frame)

    def test_mixed_coordinate_or_bad_limit_rejected(self):
        frame = rows(); frame["selection_date"] = "2024-05-01"; frame.loc[0,"selection_date"] = "2024-06-03"
        with self.assertRaises(ValueError): select(frame)
        for limit in [0, True, 1.5]:
            with self.assertRaises(ValueError): select(rows(), per_frontier_limit=limit)

    def test_missing_preference_not_synthesized(self):
        result = select(rows().iloc[:-1])
        self.assertFalse(result["audit"]["user_preference_present"])
        self.assertEqual(result["audit"]["input_count"], 16)


if __name__ == "__main__":
    unittest.main()
