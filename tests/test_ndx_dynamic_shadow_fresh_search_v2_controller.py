from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd

import scripts.ndx_dynamic_shadow_daily_v2 as daily_v2
import scripts.ndx_dynamic_shadow_fresh_search_v2 as controller
from backtest.ndx_dynamic_shadow_fresh_search import coordinate_hash, write_completed_shard
from data.versioning import file_sha256


def _step(before, after, *, final=False, timed_out=False, invoked=True, admitted=True):
    return {
        "final_role_seal_verified": final,
        "shard_timed_out": timed_out,
        "v1_engine_invoked": invoked,
        "verified_before_shard_count": before,
        "verified_completed_shard_count": after,
        "pending_shard_count": 0 if final else 1,
        "next_shard_admitted": admitted,
    }


class FreshSearchV2ControllerTest(unittest.TestCase):
    def _run(self, steps):
        jobs = pd.DataFrame([{"checkpoint_key": "a"}, {"checkpoint_key": "b"}])
        with (
            patch.object(controller, "verify_snapshot_bundle", return_value={}),
            patch.object(controller.v1, "_artifact", return_value=jobs),
            patch.object(controller, "execute_one", side_effect=steps) as execute_one,
        ):
            return controller.execute(controller.Path("snapshot.json")), execute_one.call_count

    def test_two_shards_continue_in_same_invocation_until_final(self):
        result, calls = self._run([_step(0, 1), _step(1, 2, final=True)])
        self.assertEqual(calls, 2)
        self.assertEqual(result["controller_stop_reason"], "FINAL_ROLE_SEAL_VERIFIED")

    def test_two_real_verified_checkpoints_reach_final_in_one_controller_invocation(self):
        decision = "2026-10-01"
        fingerprint = "1" * 64

        def job(track):
            return {
                "snapshot_fingerprint": fingerprint, "universe_track": track,
                "decision_date": decision,
                "execution_coordinate_rule": "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION",
                "decision_data_end": decision, "holding_count": 1,
                "eligible_security_count": 1, "eligible_issuer_count": 1,
                "one_security_per_issuer_required": True,
                "theoretical_issuer_combinations": 1,
                "job_search_class": "EXACT_ENUMERATION",
                "search_completion_status": "PLANNED_NOT_EXECUTED",
                "global_optimality_claimed": False,
                "bounded_search_disclosure": "EXHAUSTIVE_ENUMERATION_REQUIRED_NOT_YET_EXECUTED",
                "checkpoint_key": f"{fingerprint}/{track}/{decision}/holding_count_0001",
                "historical_candidate_replay_allowed": False, "promotion_allowed": False,
            }

        jobs = pd.DataFrame([job("strict_technology"), job("technology_plus_adjacent")])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot_path = root / decision / "manifest.json"
            snapshot_path.parent.mkdir(parents=True)
            snapshot_path.write_text("{}\n", encoding="utf-8")
            output = root / "output"
            snapshot = {
                "decision_date": decision, "snapshot_fingerprint": fingerprint,
                "conservative_seal_deadline_utc": (
                    datetime.now(timezone.utc) + timedelta(hours=2)
                ).isoformat(),
            }
            original_hash, executor_hash = "4" * 64, "3" * 64
            calls = []

            def run_one(command, *, timeout_seconds):
                index = len(calls)
                current = jobs.iloc[index].to_dict()
                identity = coordinate_hash(
                    current, snapshot_manifest_sha256=file_sha256(snapshot_path),
                    executor_sha256=executor_hash, original_8_sha256=original_hash,
                )
                shard = controller.v1._shard_dir(output, current)
                write_completed_shard(
                    shard,
                    pd.DataFrame([{"coordinate_hash": identity, "portfolio_id": f"p{index}"}]),
                    {"search_audit": {
                        "snapshot_fingerprint": fingerprint,
                        "checkpoint_key": current["checkpoint_key"],
                        "job_search_class": current["job_search_class"],
                        "historical_candidate_replay_used": False, "promotion_allowed": False,
                    }},
                    coordinate_hash=identity,
                )
                calls.append(timeout_seconds)
                if len(calls) == 2:
                    final = output / "final" / decision / "manifest.json"
                    final.parent.mkdir(parents=True)
                    final.write_text("{}\n", encoding="utf-8")
                return 0

            with (
                patch.object(controller, "OUTPUT_ROOT", output),
                patch.object(controller, "CONTROL_ROOT", root / "controller"),
                patch.object(controller.v1, "CANONICAL_SNAPSHOT_ROOT", root),
                patch.object(controller, "verify_snapshot_bundle", return_value=snapshot),
                patch.object(controller.v1, "_artifact", return_value=jobs),
                patch("scripts.ndx_dynamic_shadow_candidate_generator._verify_manifest_seal_record"),
                patch.object(controller, "load_frozen_original_8_definition", return_value=([], {}, original_hash)),
                patch.object(controller, "_executor_hash", return_value=executor_hash),
                patch.object(controller, "run_process_tree", side_effect=run_one),
                patch.object(controller, "verify_final_candidate_snapshot", return_value={}),
                patch.object(controller, "verify_final_role_seal_record"),
                patch.object(controller, "write_controller_run", side_effect=lambda path, payload, **kwargs: payload),
            ):
                result = controller.execute(snapshot_path)
            self.assertEqual(len(calls), 2)
            self.assertEqual(result["verified_completed_shard_count"], 2)
            self.assertTrue(result["final_role_seal_verified"])

    def test_timeout_no_progress_and_deadline_each_stop_without_loop(self):
        cases = (
            (_step(0, 0, timed_out=True), "SHARD_TIMEOUT_PROCESS_TREE_TERMINATED"),
            (_step(0, 0), "NO_VERIFIED_PROGRESS_FAIL_CLOSED"),
            (_step(0, 0, invoked=False, admitted=False), "DEADLINE_BUDGET_DID_NOT_ADMIT_NEXT_SHARD"),
        )
        for step, reason in cases:
            with self.subTest(reason=reason):
                result, calls = self._run([step])
                self.assertEqual(calls, 1)
                self.assertEqual(result["controller_stop_reason"], reason)

    def test_timeout_kills_exact_windows_process_tree_and_waits(self):
        process = Mock()
        process.pid = 4321
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("x", 1), None]
        with (
            patch.object(controller.os, "name", "nt"),
            patch.object(controller.subprocess, "Popen", return_value=process),
            patch.object(controller.subprocess, "run") as taskkill,
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                controller.run_process_tree(["python", "job.py"], timeout_seconds=1)
        self.assertEqual(taskkill.call_args.args[0], ["taskkill", "/PID", "4321", "/T", "/F"])
        self.assertGreaterEqual(process.wait.call_count, 2)

    def test_daily_v2_manual_execute_holds_v1_single_instance_lock(self):
        events = []

        @contextmanager
        def lock():
            events.append("lock")
            yield

        with (
            patch(
                "backtest.ndx_dynamic_shadow_activation_v3.verify_activation_v3_static_sources",
                side_effect=lambda *args, **kwargs: events.append("static"),
            ),
            patch(
                "backtest.ndx_dynamic_shadow_activation_v3.verify_activation_v3_manifest",
                side_effect=lambda *args, **kwargs: events.append("full"),
            ),
            patch.object(daily_v2.v1, "single_instance_lock", side_effect=lock),
            patch.object(daily_v2.v1, "_refresh_calendar", side_effect=lambda: events.append("refresh")),
            patch.object(daily_v2.v1, "_protected_hashes", return_value={"safe": "same"}),
            patch.object(daily_v2.json, "loads", return_value={"status": "CURRENT_OBSERVED_SESSION_CALENDAR"}),
            patch.object(
                daily_v2.v1, "execute",
                side_effect=lambda **kwargs: (events.append("execute") or {"status": "ok"}),
            ) as execute,
        ):
            result = daily_v2.execute()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(events, ["lock", "static", "refresh", "full", "execute"])
        execute.assert_called_once_with(max_search_jobs=1)

    def test_appended_calendar_manifest_is_normalized_once_before_full_verify(self):
        events = []

        @contextmanager
        def lock():
            yield

        with (
            patch("backtest.ndx_dynamic_shadow_activation_v3.verify_activation_v3_static_sources"),
            patch(
                "backtest.ndx_dynamic_shadow_activation_v3.verify_activation_v3_manifest",
                side_effect=lambda *args, **kwargs: events.append("full"),
            ),
            patch.object(daily_v2.v1, "single_instance_lock", side_effect=lock),
            patch.object(daily_v2.v1, "_refresh_calendar"),
            patch.object(daily_v2.v1, "_protected_hashes", return_value={}),
            patch.object(daily_v2.json, "loads", return_value={"status": "PROSPECTIVE_OBSERVED_SESSION_APPENDED"}),
            patch.object(daily_v2.v1, "_run_checked", side_effect=lambda *args, **kwargs: events.append("normalize")),
            patch.object(daily_v2.v1, "execute", return_value={"status": "ok"}),
        ):
            daily_v2.execute()
        self.assertEqual(events, ["normalize", "full"])


if __name__ == "__main__":
    unittest.main()
