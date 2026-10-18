from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from scripts import ndx_dynamic_shadow_fresh_search_v3 as controller


class FreshSearchV3CompletionTests(unittest.TestCase):
    def result(self, reason, **overrides):
        return {
            "controller_stop_reason": reason,
            "final_role_seal_verified": False,
            "pending_shard_count": 3,
            "shard_timed_out": False,
            "seconds_to_role_seal_deadline": 500,
            "controller_status": "SHARD_TIMEOUT_INCOMPLETE_RESUMABLE",
            "planned_shard_count": 4,
            "verified_completed_shard_count": 1,
            "aggregation_allowed": False,
            **overrides,
        }

    def test_only_verified_final_can_exit_zero(self):
        result = self.result(
            "FINAL_ROLE_SEAL_VERIFIED", final_role_seal_verified=True,
            controller_status="FINAL_ROLE_SEAL_VERIFIED", pending_shard_count=0,
            verified_completed_shard_count=4, aggregation_allowed=True,
        )
        self.assertEqual(controller.classify_completion(result)["exit_code"], 0)
        result["pending_shard_count"] = 1
        with self.assertRaises(ValueError):
            controller.classify_completion(result)

    def test_timeout_retries_only_before_deadline(self):
        result = self.result("SHARD_TIMEOUT_PROCESS_TREE_TERMINATED", shard_timed_out=True)
        self.assertEqual(controller.classify_completion(result)["exit_code"], 75)
        for seconds in (0, -1):
            result["seconds_to_role_seal_deadline"] = seconds
            verdict = controller.classify_completion(result)
            self.assertEqual(verdict["exit_code"], 4)
            self.assertFalse(verdict["retryable"])
            self.assertFalse(verdict["backfill_allowed"])

    def test_incomplete_and_no_progress_never_report_success(self):
        for reason in (
            "NO_VERIFIED_PROGRESS_FAIL_CLOSED", "ITERATION_BOUND_REACHED_FAIL_CLOSED",
            "DEADLINE_BUDGET_DID_NOT_ADMIT_NEXT_SHARD",
            "NEXT_SHARD_NOT_ADMITTED_BEFORE_ROLE_SEAL_RESERVE",
        ):
            with self.subTest(reason=reason):
                verdict = controller.classify_completion(self.result(reason))
                self.assertNotEqual(verdict["exit_code"], 0)
                self.assertFalse(verdict["completed"])

    def test_unknown_or_inconsistent_result_is_rejected(self):
        for result in (
            self.result("UNKNOWN"),
            self.result("SHARD_TIMEOUT_PROCESS_TREE_TERMINATED"),
            self.result("SHARD_TIMEOUT_PROCESS_TREE_TERMINATED", shard_timed_out=True,
                        seconds_to_role_seal_deadline=float("nan")),
            self.result("FINAL_ROLE_SEAL_VERIFIED", final_role_seal_verified="true"),
        ):
            with self.subTest(result=result), self.assertRaises(ValueError):
                controller.classify_completion(result)

    def test_cli_propagates_resumable_timeout_exit_code(self):
        result = self.result("SHARD_TIMEOUT_PROCESS_TREE_TERMINATED", shard_timed_out=True)
        output = io.StringIO()
        with patch.object(controller, "execute_budgeted", return_value=result), contextlib.redirect_stdout(output):
            code = controller.main(["--execute", "--snapshot-manifest", "fixture.json"])
        self.assertEqual(code, 75)
        self.assertTrue(json.loads(output.getvalue())["v3_completion"]["retryable"])


if __name__ == "__main__":
    unittest.main()
