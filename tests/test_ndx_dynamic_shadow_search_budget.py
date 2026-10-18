from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backtest.ndx_dynamic_shadow_search_budget import (
    NdxDynamicShadowSearchBudgetError,
    build_deadline_budget_plan,
)
from scripts.ndx_dynamic_shadow_search_budget import build_readiness


def _jobs():
    return [
        {
            "checkpoint_key": "seal/track/holding_count_0001",
            "universe_track": "PIT_NDX_COMPLETE",
            "holding_count": 1,
            "job_search_class": "EXACT_ENUMERATION",
            "theoretical_issuer_combinations": 100,
        },
        {
            "checkpoint_key": "seal/track/holding_count_0002",
            "universe_track": "PIT_NDX_COMPLETE",
            "holding_count": 2,
            "job_search_class": "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND",
            "theoretical_issuer_combinations": 4950,
        },
    ]


class DynamicShadowSearchBudgetTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc)

    def test_large_exact_shard_is_refused_near_role_seal_deadline(self):
        job = _jobs()[0]
        job["theoretical_issuer_combinations"] = 500_000
        result = build_deadline_budget_plan(
            [job],
            verified_completed_checkpoint_keys=[],
            now_utc=self.now,
            role_seal_deadline_utc=self.now + timedelta(minutes=20),
            role_seal_reserve_seconds=900,
        )
        self.assertEqual(result["status"], "INCOMPLETE_DEADLINE_GUARD_NO_FALSE_COMPLETE")
        self.assertFalse(result["next_shard_admitted"])
        self.assertFalse(result["aggregation_allowed"])
        self.assertFalse(result["role_seal_allowed"])

    def test_resume_uses_only_missing_shard_and_all_verified_can_seal(self):
        first = _jobs()[0]["checkpoint_key"]
        partial = build_deadline_budget_plan(
            _jobs(),
            verified_completed_checkpoint_keys=[first],
            now_utc=self.now,
            role_seal_deadline_utc=self.now + timedelta(hours=2),
        )
        self.assertEqual(partial["pending_shard_count"], 1)
        self.assertEqual(partial["next_shard"]["holding_count"], 2)
        self.assertTrue(partial["next_shard_admitted"])
        self.assertFalse(partial["aggregation_allowed"])

        complete = build_deadline_budget_plan(
            _jobs(),
            verified_completed_checkpoint_keys=[job["checkpoint_key"] for job in _jobs()],
            now_utc=self.now,
            role_seal_deadline_utc=self.now + timedelta(minutes=5),
        )
        self.assertEqual(complete["status"], "ALL_SHARDS_VERIFIED_ROLE_SEAL_ALLOWED")
        self.assertTrue(complete["aggregation_allowed"])
        self.assertTrue(complete["role_seal_allowed"])

    def test_after_deadline_never_seals_even_when_complete(self):
        complete = build_deadline_budget_plan(
            _jobs(),
            verified_completed_checkpoint_keys=[job["checkpoint_key"] for job in _jobs()],
            now_utc=self.now,
            role_seal_deadline_utc=self.now - timedelta(seconds=1),
        )
        self.assertEqual(
            complete["status"], "ALL_SHARDS_VERIFIED_ROLE_SEAL_DEADLINE_MISSED"
        )
        self.assertTrue(complete["aggregation_allowed"])
        self.assertFalse(complete["role_seal_allowed"])

    def test_unexpected_duplicate_or_incomplete_identity_fails_closed(self):
        with self.assertRaises(NdxDynamicShadowSearchBudgetError):
            build_deadline_budget_plan(
                _jobs(),
                verified_completed_checkpoint_keys=["forged"],
                now_utc=self.now,
                role_seal_deadline_utc=self.now + timedelta(hours=1),
            )
        with self.assertRaises(NdxDynamicShadowSearchBudgetError):
            build_deadline_budget_plan(
                _jobs(),
                verified_completed_checkpoint_keys=[
                    _jobs()[0]["checkpoint_key"],
                    _jobs()[0]["checkpoint_key"],
                ],
                now_utc=self.now,
                role_seal_deadline_utc=self.now + timedelta(hours=1),
            )
        duplicate = _jobs()
        duplicate[1]["checkpoint_key"] = duplicate[0]["checkpoint_key"]
        with self.assertRaises(NdxDynamicShadowSearchBudgetError):
            build_deadline_budget_plan(
                duplicate,
                verified_completed_checkpoint_keys=[],
                now_utc=self.now,
                role_seal_deadline_utc=self.now + timedelta(hours=1),
            )

    def test_readiness_is_honestly_blocked_and_config_drift_fails(self):
        readiness = build_readiness()
        self.assertEqual(
            readiness["status"], "READY_FOR_VERSIONED_V2_ACTIVATION_MIGRATION_PLAN_ONLY"
        )
        self.assertTrue(readiness["active_executor_integration"])
        self.assertTrue(readiness["enforcement_claimed"])
        with patch(
            "scripts.ndx_dynamic_shadow_search_budget.yaml.safe_load",
            return_value={
                "status": "ACTIVE",
                "activation": {"active_executor_integration": True},
            },
        ):
            with self.assertRaises(ValueError):
                build_readiness()

    def test_nonfinite_rate_or_multiplier_fails_closed(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(NdxDynamicShadowSearchBudgetError):
                    build_deadline_budget_plan(
                        _jobs(), verified_completed_checkpoint_keys=[],
                        now_utc=self.now,
                        role_seal_deadline_utc=self.now + timedelta(hours=1),
                        exact_combinations_per_second_floor=value,
                    )


if __name__ == "__main__":
    unittest.main()
