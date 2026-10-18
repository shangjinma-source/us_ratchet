from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_ndx_dynamic_shadow_daily_task.ps1"


@unittest.skipUnless(os.name == "nt", "Windows Scheduled Task installer is Windows-only")
class NdxDynamicShadowTaskInstallerTests(unittest.TestCase):
    def _run_plan(
        self,
        project_root: Path,
        readiness: Path,
        *,
        environment: dict[str, str] | None = None,
        daily_time: str = "11:20",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-ProjectRoot",
                str(project_root),
                "-TaskName",
                "us_ratchet_dynamic_shadow_test_plan_only",
                "-ReadinessManifest",
                str(readiness),
                "-DailyTime",
                daily_time,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )

    @staticmethod
    def _plan_payload(completed: subprocess.CompletedProcess[str]) -> dict:
        return json.loads(completed.stdout.split("\nRESULT=", maxsplit=1)[0])

    def test_default_is_readiness_only_plan_without_registration(self) -> None:
        missing = ROOT / "data" / "cache" / "research" / "missing_dynamic_shadow_readiness.json"
        completed = self._run_plan(ROOT, missing)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"mode":  "PLAN_ONLY"', completed.stdout)
        self.assertIn('"action_mode":  "READINESS_ONLY_NO_DECISION_GENERATION"', completed.stdout)
        self.assertIn('"api_service_dependency":  false', completed.stdout)
        self.assertIn('"system_timezone_id":  "China Standard Time"', completed.stdout)
        self.assertIn('"beijing_timezone":  true', completed.stdout)
        self.assertIn('"canonical_paths_selected":  false', completed.stdout)
        self.assertIn('"retrospective_backfill_allowed":  false', completed.stdout)
        self.assertIn('"start_when_available":  true', completed.stdout)
        self.assertIn('"activation_ready_required":  false', completed.stdout)
        self.assertIn('"action_is_readiness_only":  true', completed.stdout)
        self.assertIn('"selection_seal_phase_enabled_in_this_task":  false', completed.stdout)
        self.assertIn('"execution_date_known_at_selection_seal":  false', completed.stdout)
        self.assertIn('"late_or_missed_selection_seal_action":  "NO_DECISION_NO_BACKFILL"', completed.stdout)
        self.assertIn('"registration_allowed_by_this_installer":  false', completed.stdout)
        self.assertIn('"planned_task_name":  "us_ratchet_ndx_dynamic_shadow_selection_daily"', completed.stdout)
        self.assertIn('"selection_wrapper_present":  true', completed.stdout)
        self.assertIn('"selection_contract_present":  true', completed.stdout)
        self.assertIn('"registration_allowed_by_this_installer":  false', completed.stdout)
        self.assertIn('"planned_execution_time_limit_mode":  "WINDOW_COVERING_11_HOURS_WRAPPER_SELF_LIMITS"', completed.stdout)
        self.assertIn('"planned_execution_time_limit_minutes":  660', completed.stdout)
        self.assertIn('"task_scheduler_start_when_available_is_sufficient_for_selection_seal":  false', completed.stdout)
        self.assertIn('"conservative_window_start":  "06:00"', completed.stdout)
        self.assertIn('"conservative_window_end_exclusive":  "21:30"', completed.stdout)
        self.assertIn('"scheduled_time_inside_conservative_window":  true', completed.stdout)
        self.assertIn('"restart_count":  3', completed.stdout)
        self.assertIn('"multiple_instances":  "IGNORE_NEW"', completed.stdout)
        self.assertIn('"passed":  false', completed.stdout)
        self.assertIn("RESULT=plan_only", completed.stdout)
        self.assertNotIn("RESULT=registered", completed.stdout)

    def test_ready_label_without_hash_locked_inputs_does_not_open_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            readiness = Path(directory) / "readiness.json"
            readiness.write_text(
                json.dumps(
                    {
                        "manifest_type": "ndx_dynamic_shadow_activation_readiness",
                        "status": "READY_FOR_AUTOMATION_REGISTRATION",
                        "automation_registration_allowed": True,
                        "caller_supplied_booleans_can_activate": False,
                        "historical_candidate_replay_allowed": False,
                        "retrospective_backfill_allowed": False,
                        "frozen_forward_candidates_allowed_as_dynamic_source": False,
                        "guards": {
                            "runner_registered": True,
                            "selector_registry_active": True,
                            "decision_generation_allowed": True,
                            "no_backfill_verified": True,
                            "next_session_execution_verified": True,
                            "append_only_verified": True,
                            "live_isolation_verified": True,
                            "immutable_artifact_evidence_verified": True,
                        },
                        "inputs": {},
                    }
                ),
                encoding="utf-8",
            )
            completed = self._run_plan(ROOT, readiness)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"status":  "READY_FOR_AUTOMATION_REGISTRATION"', completed.stdout)
        self.assertIn('"checked":  0', completed.stdout)
        self.assertIn('"passed":  false', completed.stdout)
        self.assertIn("RESULT=plan_only", completed.stdout)

    def test_apply_guards_precede_registration_and_no_replace_path_exists(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")

        register_index = source.index("Register-ScheduledTask")
        for guard in (
            "if (-not $AcknowledgeReadinessOnlyNoDecisionGeneration)",
            "if (-not $AcknowledgeExternalSchedulerDisabled)",
            "if (-not $readinessMonitorGatePassed)",
            "if ($activeWindowsDuplicates.Count -gt 0 -or $activeOpenClawDuplicates.Count -gt 0)",
            "if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)",
        ):
            self.assertIn(guard, source)
            self.assertLess(source.index(guard), register_index)
        self.assertIn("--readiness", source)
        self.assertIn("activation_verifier_hash_bound", source)
        self.assertIn("$actionArguments = '-B \"{0}\" --readiness'", source)
        self.assertIn("planned_arguments = ('-B \"{0}\" --execute'", source)
        self.assertIn("ndx_dynamic_shadow_daily.py", source)
        self.assertNotIn("Unregister-ScheduledTask", source)
        self.assertNotIn("/api/", source)

    def test_canonical_readiness_monitor_gate_tracks_manifest_hash_currency(self) -> None:
        readiness = (
            ROOT
            / "data/cache/research/ndx_dynamic_shadow_activation_readiness_v1/manifest.json"
        )
        completed = self._run_plan(ROOT, readiness)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = self._plan_payload(completed)
        gate = payload["readiness_monitor_registration_gate"]
        self.assertFalse(gate["activation_ready_required"])
        self.assertTrue(gate["action_is_readiness_only"])
        self.assertTrue(gate["canonical_paths_selected"])
        self.assertEqual(
            gate["passed"],
            gate["all_manifest_input_hashes_current"]
            and gate["canonical_runner_hash_bound"]
            and gate["canonical_activation_verifier_hash_bound"],
        )
        self.assertFalse(payload["readiness_gate"]["passed"])
        self.assertFalse(
            payload["prospective_selection_scheduler_contract"]
            ["registration_allowed_by_this_installer"]
        )

    def test_plan_marks_late_start_when_available_as_no_decision_no_backfill(self) -> None:
        completed = self._run_plan(
            ROOT,
            ROOT / "data" / "cache" / "research" / "missing.json",
            daily_time="22:00",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = self._plan_payload(completed)
        prospective = payload["prospective_selection_scheduler_contract"]
        self.assertFalse(prospective["scheduled_time_inside_conservative_window"])
        self.assertEqual(prospective["planned_execution_time_limit_minutes"], 660)
        self.assertEqual(prospective["wake_after_window_action"], "NO_DECISION_NO_BACKFILL")
        self.assertFalse(payload["readiness_gate"]["passed"])

    def test_enabled_openclaw_definition_closes_duplicate_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            cron = profile / ".openclaw" / "cron"
            cron.mkdir(parents=True)
            (cron / "jobs.json").write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "id": "duplicate",
                                "name": "ndx-dynamic-shadow",
                                "enabled": True,
                                "payload": {
                                    "message": "python scripts/ndx_dynamic_shadow_runner.py --readiness"
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["USERPROFILE"] = str(profile)
            completed = self._run_plan(
                ROOT,
                ROOT / "data" / "cache" / "research" / "missing.json",
                environment=environment,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        duplicate = self._plan_payload(completed)["duplicate_scheduler_gate"]
        self.assertFalse(duplicate["passed"])
        self.assertEqual(duplicate["active_openclaw_count"], 1)

    def test_disabled_openclaw_definition_does_not_count_as_active_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            cron = profile / ".openclaw" / "cron"
            cron.mkdir(parents=True)
            (cron / "jobs.json").write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "id": "disabled-definition",
                                "name": "ndx-dynamic-shadow",
                                "enabled": False,
                                "payload": {
                                    "message": "python scripts/ndx_dynamic_shadow_runner.py --readiness"
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["USERPROFILE"] = str(profile)
            completed = self._run_plan(
                ROOT,
                ROOT / "data" / "cache" / "research" / "missing.json",
                environment=environment,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        duplicate = self._plan_payload(completed)["duplicate_scheduler_gate"]
        self.assertTrue(duplicate["passed"])
        self.assertEqual(duplicate["active_openclaw_count"], 0)
        self.assertEqual(len(duplicate["openclaw_definitions"]), 1)


if __name__ == "__main__":
    unittest.main()
