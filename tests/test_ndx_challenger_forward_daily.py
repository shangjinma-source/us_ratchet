from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.ndx_challenger_forward_daily import is_safe_post_close_window, run_daily


class NdxChallengerForwardDailyTests(unittest.TestCase):
    def test_post_close_window_is_dst_aware(self):
        self.assertTrue(is_safe_post_close_window(datetime(2026, 7, 21, 0, 0, tzinfo=timezone.utc)))
        self.assertFalse(is_safe_post_close_window(datetime(2026, 7, 20, 20, 0, tzinfo=timezone.utc)))

    def test_waiting_readiness_does_not_register(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            calls = []

            def runner(command, timeout):
                calls.append(command)
                if "ndx_challenger_forward_cohort.py" in command[2] and "plan" in command:
                    (output / "readiness.json").write_text(json.dumps({
                        "status": "WAITING_FOR_COMPLETED_MONTHLY_COHORT_SESSION",
                        "next_expected_observation_if_already_cached": None,
                    }), encoding="utf-8")
                return {"command": command, "returncode": 0, "stdout": "ok", "stderr": ""}

            payload, code = run_daily(output=output, runner=runner)
            self.assertEqual(code, 0)
            self.assertEqual(len(calls), 4)
            self.assertIn("ndx_challenger_forward_evaluate.py", calls[-2][2])
            self.assertIn("portfolio_pullback_pooled_reserve_audit.py", calls[-1][2])
            self.assertTrue(payload["pullback_pooled_reserve_shadow_performed"])
            self.assertFalse(payload["cohort_registration_performed"])

    def test_ready_readiness_registers_exact_same_market_date(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            calls = []

            def runner(command, timeout):
                calls.append(command)
                if "ndx_challenger_forward_cohort.py" in command[2] and "plan" in command:
                    (output / "readiness.json").write_text(json.dumps({
                        "status": "READY_FOR_SAME_DAY_POST_CLOSE_REGISTRATION",
                        "next_expected_observation_if_already_cached": "2026-07-20",
                    }), encoding="utf-8")
                return {"command": command, "returncode": 0, "stdout": "ok", "stderr": ""}

            payload, code = run_daily(output=output, runner=runner)
            self.assertEqual(code, 0)
            self.assertEqual(len(calls), 5)
            observation_index = calls[2].index("--observation-date")
            self.assertEqual(calls[2][observation_index:observation_index + 2], ["--observation-date", "2026-07-20"])
            self.assertNotIn("--registered-date", calls[2])
            self.assertIn("ndx_challenger_forward_evaluate.py", calls[3][2])
            self.assertIn("portfolio_pullback_pooled_reserve_audit.py", calls[4][2])
            self.assertTrue(payload["cohort_registration_performed"])
            self.assertFalse(payload["promotion_allowed"])

    def test_incomplete_same_day_close_coverage_requests_scheduler_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            calls = []

            def runner(command, timeout):
                calls.append(command)
                if "ndx_challenger_forward_cohort.py" in command[2] and "plan" in command:
                    (output / "readiness.json").write_text(json.dumps({
                        "status": "WAITING_FOR_COMPLETE_OBSERVATION_CLOSE_COVERAGE",
                        "next_expected_observation_if_already_cached": "2026-07-20",
                        "missing_observation_close_tickers": ["QCOM"],
                    }), encoding="utf-8")
                return {"command": command, "returncode": 0, "stdout": "ok", "stderr": ""}

            payload, code = run_daily(output=output, runner=runner)
            self.assertEqual(code, 3)
            self.assertFalse(payload["ok"])
            self.assertTrue(payload["retry_needed"])
            self.assertEqual(payload["missing_observation_close_tickers"], ["QCOM"])
            self.assertFalse(payload["cohort_registration_performed"])
            self.assertEqual(len(calls), 4)
            self.assertIn("ndx_challenger_forward_evaluate.py", calls[-2][2])
            self.assertIn("portfolio_pullback_pooled_reserve_audit.py", calls[-1][2])

    def test_custom_forward_paths_are_propagated_to_all_versioned_children(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            calls = []

            def runner(command, timeout):
                calls.append(command)
                if "ndx_challenger_forward_cohort.py" in command[2] and "plan" in command:
                    (output / "readiness.json").write_text(json.dumps({
                        "status": "WAITING_FOR_COMPLETED_MONTHLY_COHORT_SESSION",
                        "next_expected_observation_if_already_cached": None,
                    }), encoding="utf-8")
                return {"command": command, "returncode": 0, "stdout": "ok", "stderr": ""}

            payload, code = run_daily(
                output=output, spec="config/v4.yaml", registry_manifest="registry/v4.json",
                price_cache_dir="prices", target_nav="fund.csv", runner=runner,
            )
            self.assertEqual(code, 0)
            for command in calls[:3]:
                if "portfolio_pullback_pooled_reserve_audit.py" in command[2]:
                    continue
                self.assertIn("registry/v4.json", command)
            self.assertIn("config/v4.yaml", calls[1])
            self.assertIn("config/v4.yaml", calls[2])
            self.assertEqual(payload["forward_spec"], "config/v4.yaml")


if __name__ == "__main__":
    unittest.main()
