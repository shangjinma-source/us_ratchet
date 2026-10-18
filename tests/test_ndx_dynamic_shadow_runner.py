from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from backtest.ndx_dynamic_shadow_runner import (
    NdxDynamicShadowRunnerError,
    build_dynamic_shadow_readiness,
    build_monthly_decision_payloads,
    canonical_sha256,
    load_dynamic_shadow_runner_contract,
    simulate_fresh_lane_path,
    validate_dynamic_shadow_runner_contract,
    validate_monthly_session_timing,
    write_immutable_monthly_decisions,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "ndx_dynamic_shadow_runner_v1.yaml"
HASH = "a" * 64


def _sessions() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "session_date": "2026-10-01",
            "open_timestamp_utc": "2026-10-01T13:30:00Z",
            "close_timestamp_utc": "2026-10-01T20:00:00Z",
            "completed": True,
        },
        {
            "session_date": "2026-10-02",
            "open_timestamp_utc": "2026-10-02T13:30:00Z",
            "close_timestamp_utc": "2026-10-02T20:00:00Z",
            "completed": False,
        },
        {
            "session_date": "2026-10-05",
            "open_timestamp_utc": "2026-10-05T13:30:00Z",
            "close_timestamp_utc": "2026-10-05T20:00:00Z",
            "completed": False,
        },
    ])


def _candidates() -> pd.DataFrame:
    rows = []
    for track in ("strict_technology", "technology_plus_adjacent"):
        rows.extend([
            {
                "universe_track": track,
                "selection_date": "2026-10-02",
                "decision_data_end": "2026-10-01",
                "holding_count": 1,
                "portfolio_id": f"{track}-single",
                "weight_spec": "equal_weight",
                "tickers": "AAA",
                "weights": "AAA:1",
                "security_ids": "security:aaa",
                "issuer_ids": "issuer:aaa",
                "declared_constraints_passed": True,
                "return_p50": 0.3,
                "return_p10": 0.1,
                "max_drawdown_p50": 0.1,
                "max_drawdown_p90": 0.2,
                "target_012922_distance": 0.1,
            },
            {
                "universe_track": track,
                "selection_date": "2026-10-02",
                "decision_data_end": "2026-10-01",
                "holding_count": 4,
                "portfolio_id": f"{track}-preference",
                "weight_spec": "equal_weight",
                "tickers": "AMAT;AVGO;CDNS;GOOG",
                "weights": "AMAT:0.25;AVGO:0.25;CDNS:0.25;GOOG:0.25",
                "security_ids": "security:amat;security:avgo;security:cdns;security:goog",
                "issuer_ids": "issuer:amat;issuer:avgo;issuer:cdns;issuer:goog",
                "declared_constraints_passed": False,
                "return_p50": 0.2,
                "return_p10": 0.05,
                "max_drawdown_p50": 0.12,
                "max_drawdown_p90": 0.22,
                "target_012922_distance": 0.2,
            },
        ])
    return pd.DataFrame(rows)


class DynamicShadowRunnerTests(unittest.TestCase):
    def test_current_contract_is_complete_but_fail_closed(self):
        contract = load_dynamic_shadow_runner_contract(CONTRACT)
        self.assertFalse(contract["operation_gate"]["decision_registration_allowed"])
        self.assertEqual(
            contract["schedule_contract"]["execution_coordinate_rule"],
            "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION",
        )
        self.assertFalse(
            contract["schedule_contract"]["execution_date_known_at_selection_seal"]
        )
        self.assertEqual(
            contract["schedule_contract"]["missed_registration_window_action"],
            "NO_DECISION_NO_BACKFILL",
        )
        changed = copy.deepcopy(contract)
        changed["lane_contract"]["winner_take_all_ex_post_selection_allowed"] = True
        with self.assertRaisesRegex(NdxDynamicShadowRunnerError, "must be False"):
            validate_dynamic_shadow_runner_contract(changed)

    def test_current_readiness_verifies_calendar_but_keeps_other_gates_closed(self):
        healthy_calendar_fixture = {
            "verified": True,
            "error": None,
            "session_count": 1,
            "decision_eligible_session_count": 0,
        }
        with patch(
            "backtest.ndx_dynamic_shadow_runner."
            "verify_observed_session_calendar_manifest",
            return_value=healthy_calendar_fixture,
        ):
            result = build_dynamic_shadow_readiness(CONTRACT, as_of_date="2026-09-05")
        blockers = {item["blocker_id"] for item in result["blockers"]}
        self.assertEqual(result["schedule_status"], "NOT_DUE_BEFORE_REGISTERED_START")
        self.assertIn("POINT_IN_TIME_FUTURE_CANDIDATE_GENERATOR_UNREGISTERED", blockers)
        self.assertNotIn("VERIFIED_US_SESSION_CALENDAR_MANIFEST_MISSING_OR_INVALID", blockers)
        self.assertTrue(result["observed_session_calendar"]["verified"])
        self.assertNotIn("FROZEN_ORIGINAL_8_CONTROL_MISSING_OR_INVALID", blockers)
        self.assertTrue(result["original_8_control"]["verified"])
        self.assertFalse(
            result["original_8_control"]["broker_current_overlay_included"]
        )
        self.assertFalse(result["local_generator_audit"]["accepted_for_fresh_shadow"])
        self.assertFalse(result["historical_consumed_used"])
        self.assertFalse(result["promotion_allowed"])

    def test_runner_contract_rejects_noncanonical_observed_calendar(self):
        contract = load_dynamic_shadow_runner_contract(CONTRACT)
        changed = copy.deepcopy(contract)
        changed["required_runtime_inputs"]["us_session_calendar_manifest_path"] = "README.md"
        with self.assertRaisesRegex(NdxDynamicShadowRunnerError, "calendar path binding"):
            validate_dynamic_shadow_runner_contract(changed)

    def test_timing_rejects_backfill_same_close_and_late_registration(self):
        sessions = _sessions()
        with self.assertRaisesRegex(NdxDynamicShadowRunnerError, "backfill"):
            validate_monthly_session_timing(
                sessions, decision_date="2026-09-01", execution_date="2026-10-01",
                registration_timestamp_utc="2026-09-01T21:00:00Z",
            )
        with self.assertRaisesRegex(NdxDynamicShadowRunnerError, "first session after"):
            validate_monthly_session_timing(
                sessions, decision_date="2026-10-01", execution_date="2026-10-01",
                registration_timestamp_utc="2026-10-01T20:30:00Z",
            )
        with self.assertRaisesRegex(NdxDynamicShadowRunnerError, "before next-session open"):
            validate_monthly_session_timing(
                sessions, decision_date="2026-10-01", execution_date="2026-10-02",
                registration_timestamp_utc="2026-10-02T14:00:00Z",
            )

    def test_builds_complete_independent_lane_matrix_without_admission(self):
        payloads = build_monthly_decision_payloads(
            _candidates(), sessions=_sessions(), decision_date="2026-10-01",
            execution_date="2026-10-02",
            registration_timestamp_utc="2026-10-01T20:30:00Z",
            candidate_snapshot_sha256=HASH, calendar_manifest_sha256=HASH,
            generator_script_sha256=HASH, selector_registry_sha256=HASH,
            selector_policy_sha256=HASH,
        )
        self.assertEqual(len(payloads), 10)
        self.assertEqual(len({item["selector_id"] for item in payloads}), 10)
        self.assertTrue(all(item["independent_lane_only"] for item in payloads))
        self.assertTrue(all(not item["target_scalar_used_for_admission"] for item in payloads))
        self.assertTrue(all(not item["promotion_allowed"] for item in payloads))
        references = [item for item in payloads if item["policy_role"] == "USER_PREFERENCE"]
        self.assertEqual(len(references), 2)
        self.assertTrue(all(item["status"] == "SELECTED_REFERENCE_NOT_FIXED_ANSWER" for item in references))
        self.assertTrue(all(not item["selected_candidate"]["declared_constraints_passed"] for item in references))

    def test_immutable_decision_collision_is_rejected_before_overwrite(self):
        payloads = build_monthly_decision_payloads(
            _candidates(), sessions=_sessions(), decision_date="2026-10-01",
            execution_date="2026-10-02",
            registration_timestamp_utc="2026-10-01T20:30:00Z",
            candidate_snapshot_sha256=HASH, calendar_manifest_sha256=HASH,
            generator_script_sha256=HASH, selector_registry_sha256=HASH,
            selector_policy_sha256=HASH,
        )
        with TemporaryDirectory() as temporary:
            paths = write_immutable_monthly_decisions(temporary, payloads)
            original = paths[0].read_text(encoding="utf-8")
            changed = copy.deepcopy(payloads)
            changed[0]["status"] = "ALTERED_AFTER_THE_FACT"
            changed[0].pop("payload_sha256")
            changed[0]["payload_sha256"] = canonical_sha256(changed[0])
            with self.assertRaisesRegex(NdxDynamicShadowRunnerError, "collision"):
                write_immutable_monthly_decisions(temporary, changed)
            self.assertEqual(paths[0].read_text(encoding="utf-8"), original)

    def test_simulation_rejects_cross_lane_splicing_and_uses_open_close_contract(self):
        payloads = build_monthly_decision_payloads(
            _candidates(), sessions=_sessions(), decision_date="2026-10-01",
            execution_date="2026-10-02",
            registration_timestamp_utc="2026-10-01T20:30:00Z",
            candidate_snapshot_sha256=HASH, calendar_manifest_sha256=HASH,
            generator_script_sha256=HASH, selector_registry_sha256=HASH,
            selector_policy_sha256=HASH,
        )
        return_lane = [item for item in payloads if item["selector_id"] == "strict_technology__return__v1"]
        other_lane = next(item for item in payloads if item["selector_id"] == "technology_plus_adjacent__return__v1")
        with self.assertRaisesRegex(NdxDynamicShadowRunnerError, "splicing"):
            simulate_fresh_lane_path(
                [return_lane[0], other_lane], sessions=_sessions(),
                valuation_prices=pd.DataFrame(), execution_prices=pd.DataFrame(),
                valuation_end_date="2026-10-05",
            )
        valuation = pd.DataFrame(
            {"AAA": [110.0, 121.0]},
            index=pd.to_datetime(["2026-10-02", "2026-10-05"]),
        )
        execution = pd.DataFrame(
            {"AAA": [100.0, 120.0]},
            index=pd.to_datetime(["2026-10-02", "2026-10-05"]),
        )
        summary, _, trades, path = simulate_fresh_lane_path(
            return_lane, sessions=_sessions(), valuation_prices=valuation,
            execution_prices=execution, valuation_end_date="2026-10-05",
        )
        self.assertEqual(float(trades.iloc[0]["price_usd"]), 100.0)
        self.assertEqual(float(path.iloc[0]["holdings_value_usd"]), 27280.0)
        self.assertGreaterEqual(summary["minimum_cash_usd"], 100.0)
        self.assertEqual(summary["transaction_cost_bps"], 10.0)
        self.assertTrue(summary["fresh_oos"])
        self.assertFalse(summary["promotion_allowed"])

    def test_payload_hash_tampering_cannot_enter_path(self):
        payloads = build_monthly_decision_payloads(
            _candidates(), sessions=_sessions(), decision_date="2026-10-01",
            execution_date="2026-10-02",
            registration_timestamp_utc="2026-10-01T20:30:00Z",
            candidate_snapshot_sha256=HASH, calendar_manifest_sha256=HASH,
            generator_script_sha256=HASH, selector_registry_sha256=HASH,
            selector_policy_sha256=HASH,
        )
        lane = [copy.deepcopy(item) for item in payloads if item["selector_id"] == "strict_technology__return__v1"]
        lane[0]["selected_candidate"]["portfolio_id"] = "ex-post-winner"
        with self.assertRaisesRegex(NdxDynamicShadowRunnerError, "hash mismatch"):
            simulate_fresh_lane_path(
                lane, sessions=_sessions(), valuation_prices=pd.DataFrame(),
                execution_prices=pd.DataFrame(), valuation_end_date="2026-10-05",
            )

    def test_tampered_previous_lane_head_cannot_extend_chain(self):
        payloads = build_monthly_decision_payloads(
            _candidates(), sessions=_sessions(), decision_date="2026-10-01",
            execution_date="2026-10-02",
            registration_timestamp_utc="2026-10-01T20:30:00Z",
            candidate_snapshot_sha256=HASH, calendar_manifest_sha256=HASH,
            generator_script_sha256=HASH, selector_registry_sha256=HASH,
            selector_policy_sha256=HASH,
        )
        heads = {item["selector_id"]: copy.deepcopy(item) for item in payloads}
        heads["strict_technology__return__v1"]["selected_candidate"]["portfolio_id"] = "tampered"
        with self.assertRaisesRegex(NdxDynamicShadowRunnerError, "head hash mismatch"):
            build_monthly_decision_payloads(
                _candidates(), sessions=_sessions(), decision_date="2026-10-01",
                execution_date="2026-10-02",
                registration_timestamp_utc="2026-10-01T20:30:00Z",
                candidate_snapshot_sha256=HASH, calendar_manifest_sha256=HASH,
                generator_script_sha256=HASH, selector_registry_sha256=HASH,
                selector_policy_sha256=HASH, previous_lane_heads=heads,
            )


if __name__ == "__main__":
    unittest.main()
