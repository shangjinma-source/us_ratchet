from __future__ import annotations

import unittest

import pandas as pd

from backtest.ndx_dynamic_candidate_policy import (
    NdxDynamicCandidatePolicyError,
    build_dynamic_policy_schedule,
    select_dynamic_candidate_policy,
    select_user_preference_reference_policy,
)


def _row(date: str, identity: str, tickers: str, metrics: tuple[float, float, float, float, float]) -> dict:
    names = tickers.split(";")
    security_ids = ";".join(f"security:{ticker.lower()}" for ticker in names)
    issuer_ids = ";".join(f"issuer:{ticker.lower()}" for ticker in names)
    weights = ";".join(f"{ticker}:{1 / len(names):.10f}" for ticker in names)
    return {
        "selection_date": date,
        "decision_data_end": (pd.Timestamp(date) - pd.offsets.BDay(1)).date().isoformat(),
        "holding_count": len(names),
        "portfolio_id": identity,
        "weight_spec": "equal_weight",
        "tickers": tickers,
        "weights": weights,
        "security_ids": security_ids,
        "issuer_ids": issuer_ids,
        "declared_constraints_passed": True,
        "return_p50": metrics[0],
        "return_p10": metrics[1],
        "max_drawdown_p50": metrics[2],
        "max_drawdown_p90": metrics[3],
        "target_012922_distance": metrics[4],
    }


class DynamicCandidatePolicyTests(unittest.TestCase):
    def setUp(self):
        rows = []
        for date in ("2024-01-02", "2024-02-01"):
            rows.extend([
                _row(date, date + "-return", "A;B", (0.30, 0.05, 0.20, 0.30, 0.40)),
                _row(date, date + "-tail", "A;B;C", (0.20, 0.10, 0.18, 0.25, 0.30)),
                _row(date, date + "-risk", "A;B;C;D", (0.10, 0.02, 0.10, 0.12, 0.20)),
                _row(date, date + "-pref", "AMAT;AVGO;CDNS;GOOG", (0.15, 0.03, 0.15, 0.18, 0.25)),
            ])
        self.frame = pd.DataFrame(rows)

    def test_each_role_selects_across_dynamic_k(self):
        expected = {"RETURN": 2, "BAD_TAIL": 3, "DRAWDOWN": 4, "TARGET_ENVELOPE": 4}
        for role, holding_count in expected.items():
            with self.subTest(role=role):
                selected = select_dynamic_candidate_policy(self.frame, policy_role=role)
                self.assertEqual(selected["holding_count"].astype(int).tolist(), [holding_count, holding_count])
                self.assertTrue(selected["training_selection_only"].all())
                self.assertFalse(selected["scalar_target_distance_used_for_admission"].any())

    def test_user_preference_is_reference_lane_not_global_answer(self):
        selected = select_dynamic_candidate_policy(self.frame, policy_role="USER_PREFERENCE")
        self.assertTrue(selected["tickers"].eq("AMAT;AVGO;CDNS;GOOG").all())
        self.assertTrue(selected["policy_role"].eq("USER_PREFERENCE").all())

    def test_user_preference_reference_retains_failed_dates_without_admission(self):
        changed = self.frame.loc[
            self.frame["portfolio_id"].str.endswith("-pref")
        ].copy()
        changed["constraint_failure_reasons"] = ""
        changed.loc[changed.index[0], "declared_constraints_passed"] = False
        changed.loc[
            changed.index[0], "constraint_failure_reasons"
        ] = "WHOLE_LOT_EXECUTABILITY_FAILED"
        selected = select_user_preference_reference_policy(changed)
        self.assertEqual(len(selected), 2)
        self.assertFalse(bool(selected.iloc[0]["reference_declared_constraints_passed"]))
        self.assertEqual(
            selected.iloc[0]["constraint_failure_reasons"],
            "WHOLE_LOT_EXECUTABILITY_FAILED",
        )
        self.assertTrue(
            selected["reference_role"].eq("REFERENCE_NOT_FIXED_ANSWER").all()
        )
        self.assertFalse(selected["admission_allowed"].astype(bool).any())
        self.assertFalse(selected["promotion_allowed"].astype(bool).any())

    def test_schedule_uses_security_ids_and_pre_execution_data_cutoff(self):
        selected = select_dynamic_candidate_policy(self.frame, policy_role="BAD_TAIL")
        schedule = build_dynamic_policy_schedule(selected)
        self.assertEqual(len(schedule), 2)
        self.assertLess(schedule[0]["decision_date"], schedule[0]["execution_date"])
        self.assertEqual(set(schedule[0]["targets"]), {"security:a", "security:b", "security:c"})
        self.assertEqual(schedule[0]["targets"]["security:a"]["issuer_id"], "issuer:a")

    def test_future_schedule_executes_only_on_next_session(self):
        selected = select_dynamic_candidate_policy(self.frame, policy_role="BAD_TAIL")
        mapping = {
            pd.Timestamp("2024-01-02"): pd.Timestamp("2024-01-03"),
            pd.Timestamp("2024-02-01"): pd.Timestamp("2024-02-02"),
        }
        schedule = build_dynamic_policy_schedule(selected, execution_dates=mapping)
        self.assertEqual(schedule[0]["decision_date"], pd.Timestamp("2024-01-02"))
        self.assertEqual(schedule[0]["execution_date"], pd.Timestamp("2024-01-03"))

    def test_missing_preference_fails_closed(self):
        without_preference = self.frame.loc[~self.frame["portfolio_id"].str.endswith("-pref")]
        with self.assertRaisesRegex(NdxDynamicCandidatePolicyError, "absent"):
            select_dynamic_candidate_policy(without_preference, policy_role="USER_PREFERENCE")

    def test_future_contaminated_decision_date_fails_closed(self):
        changed = self.frame.copy()
        changed.loc[0, "decision_data_end"] = changed.loc[0, "selection_date"]
        with self.assertRaisesRegex(NdxDynamicCandidatePolicyError, "must end before"):
            select_dynamic_candidate_policy(changed, policy_role="RETURN")


if __name__ == "__main__":
    unittest.main()
