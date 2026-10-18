from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_ndx_dynamic_shadow_selection_task.ps1"


@unittest.skipUnless(os.name == "nt", "Windows Scheduled Task installer is Windows-only")
class NdxDynamicShadowSelectionTaskInstallerTests(unittest.TestCase):
    def _run_plan(
        self,
        manifest: Path,
        *,
        daily_time: str = "11:20",
        environment: dict[str, str] | None = None,
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
                str(ROOT),
                "-TaskName",
                "us_ratchet_ndx_dynamic_shadow_selection_daily",
                "-ActivationManifest",
                str(manifest),
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
    def _payload(completed: subprocess.CompletedProcess[str]) -> dict:
        return json.loads(completed.stdout.split("\nRESULT=", maxsplit=1)[0])

    def test_default_is_plan_only_with_exact_research_schedule(self) -> None:
        manifest = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/manifest.json"
        completed = self._run_plan(manifest)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = self._payload(completed)
        self.assertEqual(payload["mode"], "PLAN_ONLY")
        self.assertEqual(payload["action_mode"], "RESEARCH_SELECTION_AND_PATH_ONLY")
        self.assertEqual(
            payload["arguments"],
            f'-B "{ROOT / "scripts/ndx_dynamic_shadow_daily.py"}" --execute',
        )
        self.assertEqual(
            payload["trigger"]["days"],
            ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        )
        self.assertEqual(payload["trigger"]["time"], "11:20")
        self.assertTrue(payload["start_when_available"])
        self.assertEqual(payload["multiple_instances"], "IGNORE_NEW")
        self.assertEqual(payload["restart_count"], 3)
        self.assertEqual(payload["execution_time_limit_minutes"], 660)
        self.assertTrue(payload["wrapper_self_limits_to_remaining_pre_open_window"])
        self.assertEqual(
            payload["conservative_window"]["missed_or_late_action"],
            "NO_DECISION_NO_BACKFILL",
        )
        self.assertFalse(payload["conservative_window"]["retrospective_backfill_allowed"])
        self.assertTrue(payload["readiness_monitor_is_separate_task"])
        self.assertEqual(payload["readiness_monitor_execution_limit_minutes"], 20)
        self.assertFalse(payload["api_service_dependency"])
        self.assertFalse(payload["live_state_or_order_write"])
        self.assertIn("RESULT=plan_only", completed.stdout)
        self.assertNotIn("RESULT=registered", completed.stdout)

    def test_missing_or_self_reported_manifest_cannot_open_gate(self) -> None:
        missing = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/missing.json"
        completed = self._run_plan(missing)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(self._payload(completed)["activation_v2_gate"]["passed"])

        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "manifest.json"
            fake.write_text(
                json.dumps(
                    {
                        "manifest_type": "ndx_dynamic_shadow_activation_v2",
                        "status": "READY_FOR_RESEARCH_AUTOMATION_REGISTRATION",
                        "research_automation_registration_allowed": True,
                        "decision_and_path_generation_research_only": True,
                        "promotion_allowed": False,
                        "live_mutation_allowed": False,
                        "task_registration_performed": False,
                        "manifest_sha256": "0" * 64,
                        "canonical_source_bindings": {},
                    }
                ),
                encoding="utf-8",
            )
            completed = self._run_plan(fake)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        gate = self._payload(completed)["activation_v2_gate"]
        self.assertFalse(gate["canonical_paths_selected"])
        self.assertFalse(gate["canonical_artifact_hashes"]["passed"])
        self.assertFalse(gate["passed"])

    def test_canonical_v2_activation_is_superseded_by_current_v3_scheduler(self) -> None:
        manifest = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/manifest.json"
        completed = self._run_plan(manifest)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = self._payload(completed)
        self.assertTrue(payload["activation_v2_gate"]["passed"])
        self.assertTrue(
            payload["activation_v2_gate"]["calendar_append_only_extension_contract"]
        )
        duplicate = payload["duplicate_scheduler_gate"]
        self.assertFalse(duplicate["passed"])
        self.assertEqual(duplicate["active_windows_count"], 1)
        self.assertEqual(duplicate["active_openclaw_count"], 0)
        self.assertEqual(
            [
                row["task_name"]
                for row in duplicate["windows_definitions"]
                if row["enabled"]
            ],
            ["us_ratchet_ndx_dynamic_shadow_selection_daily_v3_reviewed_calendar"],
        )
        self.assertEqual(
            payload["registration_gate"]["passed"],
            not payload["registration_gate"]["target_task_already_exists"],
        )
        self.assertEqual(payload["mode"], "PLAN_ONLY")
        self.assertIn("RESULT=plan_only", completed.stdout)
        self.assertNotIn("RESULT=registered", completed.stdout)

    def test_time_outside_seal_window_is_fail_closed(self) -> None:
        manifest = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/missing.json"
        completed = self._run_plan(manifest, daily_time="22:00")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = self._payload(completed)
        self.assertFalse(payload["conservative_window"]["scheduled_time_inside"])
        self.assertEqual(
            payload["conservative_window"]["missed_or_late_action"],
            "NO_DECISION_NO_BACKFILL",
        )
        self.assertFalse(payload["registration_gate"]["passed"])

    def test_enabled_openclaw_execute_is_a_duplicate_but_readiness_is_not(self) -> None:
        manifest = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/missing.json"
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            cron = profile / ".openclaw" / "cron"
            cron.mkdir(parents=True)
            (cron / "jobs.json").write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "id": "monitor",
                                "name": "dynamic readiness",
                                "enabled": True,
                                "payload": {
                                    "message": "python scripts/ndx_dynamic_shadow_runner.py --readiness"
                                },
                            },
                            {
                                "id": "selection",
                                "name": "dynamic shadow selection",
                                "enabled": True,
                                "payload": {
                                    "message": "python scripts/ndx_dynamic_shadow_daily.py --execute"
                                },
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["USERPROFILE"] = str(profile)
            completed = self._run_plan(manifest, environment=environment)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        duplicate = self._payload(completed)["duplicate_scheduler_gate"]
        self.assertFalse(duplicate["passed"])
        self.assertEqual(duplicate["active_openclaw_count"], 1)
        self.assertEqual(duplicate["openclaw_definitions"][0]["id"], "selection")

    def test_apply_path_is_explicit_non_replacing_and_independently_verifies(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        register_index = source.index("Register-ScheduledTask")
        for guard in (
            "if (-not $AcknowledgeResearchOnlyNoLiveMutation)",
            "if (-not $AcknowledgeExternalSchedulerDisabled)",
            "if (-not $activationGatePassed)",
            "if (-not $duplicateGatePassed)",
            "if ($targetTaskExists)",
            "--verify-activation-manifest",
            "if ($LASTEXITCODE -ne 0)",
            "$postVerificationManifestSha256 -ne $activationManifestSha256",
            "-not $postVerificationArtifactChecks.passed",
        ):
            self.assertIn(guard, source)
            self.assertLess(source.index(guard), register_index)
        self.assertIn("-ExecutionTimeLimit (New-TimeSpan -Minutes $executionLimitMinutes)", source)
        self.assertIn("-StartWhenAvailable", source)
        self.assertIn("-AllowStartIfOnBatteries", source)
        self.assertIn("-DontStopIfGoingOnBatteries", source)
        self.assertIn("-MultipleInstances IgnoreNew", source)
        self.assertIn("selection_task_registration.json", source)
        self.assertIn("registration_record_sha256", source)
        self.assertIn("Current selection task differs from immutable registration evidence", source)
        self.assertIn("[System.IO.File]::Move($temporary, $Path)", source)
        self.assertIn("refusing to overwrite immutable evidence", source)
        self.assertNotIn("Unregister-ScheduledTask", source)
        self.assertNotIn("/api/", source)

    def test_plan_reports_battery_only_migration_without_changing_task(self) -> None:
        command = (
            "$t=Get-ScheduledTask -TaskName "
            "us_ratchet_ndx_dynamic_shadow_selection_daily -ErrorAction Stop; "
            "[pscustomobject]@{Disallow=[bool]$t.Settings.DisallowStartIfOnBatteries;"
            "Stop=[bool]$t.Settings.StopIfGoingOnBatteries;"
            "Action=[string]$t.Actions[0].Arguments;"
            "Start=[string]$t.Triggers[0].StartBoundary} | ConvertTo-Json -Compress"
        )
        before = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        completed = self._run_plan(
            ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v2/manifest.json"
        )
        after = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(before, after)
        migration = self._payload(completed)["battery_reliability"]
        self.assertTrue(migration["migration_required"])
        self.assertEqual(migration["proposed_cmdlet"], "Set-ScheduledTask")
        self.assertFalse(migration["migration_performed_by_this_plan"])

    def test_canonical_registration_evidence_is_hash_bound_and_immutable(self) -> None:
        evidence_path = (
            ROOT
            / "data/cache/research/ndx_dynamic_shadow_activation_v2"
            / "selection_task_registration.json"
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence_file_sha256_before = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        self.assertEqual(
            evidence["manifest_type"],
            "ndx_dynamic_shadow_selection_task_registration",
        )
        self.assertEqual(
            evidence["task_name"],
            "us_ratchet_ndx_dynamic_shadow_selection_daily",
        )
        self.assertTrue(evidence["immutable"])
        self.assertFalse(evidence["overwrite_allowed"])
        self.assertRegex(evidence["registration_record_sha256"], r"^[0-9a-f]{64}$")
        snapshot = evidence["task_snapshot"]
        self.assertEqual(
            hashlib.sha256(snapshot["task_xml"].encode("utf-8")).hexdigest(),
            snapshot["task_xml_sha256"],
        )
        activation_path = Path(evidence["activation_manifest"]["path"])
        self.assertEqual(
            hashlib.sha256(activation_path.read_bytes()).hexdigest(),
            evidence["activation_manifest"]["file_sha256"],
        )
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-ProjectRoot",
                str(ROOT),
                "-CaptureExistingRegistrationEvidence",
                "-AcknowledgeResearchOnlyNoLiveMutation",
                "-AcknowledgeExternalSchedulerDisabled",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("enabled duplicate Windows/OpenClaw selection scheduler", completed.stderr)
        self.assertEqual(
            hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            evidence_file_sha256_before,
        )

        # Current runtime health is intentionally not a unit-test invariant:
        # the immutable v1 registration can remain intact while its mutable
        # vendor inputs are no longer reproducible.  The versioned read-only
        # legacy health CLI probes that external state without granting task
        # authority; this test keeps proving only immutability/hash binding.

    def test_registration_verifier_rejects_record_and_resigned_task_tampering(self) -> None:
        source_evidence = (
            ROOT
            / "data/cache/research/ndx_dynamic_shadow_activation_v2"
            / "selection_task_registration.json"
        )
        resign = r'''
$path = $env:TEST_EVIDENCE_PATH
$mode = $env:TEST_TAMPER_MODE
$e = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
if ($mode -eq "action") {
    $e.task_snapshot.action.arguments = "-B malicious.py --execute"
} elseif ($mode -eq "xml") {
    $e.task_snapshot.task_xml = [string]$e.task_snapshot.task_xml + " "
    $a = [Security.Cryptography.SHA256]::Create()
    try { $e.task_snapshot.task_xml_sha256 = [BitConverter]::ToString($a.ComputeHash([Text.UTF8Encoding]::new($false).GetBytes([string]$e.task_snapshot.task_xml))).Replace("-", "").ToLowerInvariant() } finally { $a.Dispose() }
}
$a = [Security.Cryptography.SHA256]::Create()
try { $e.task_snapshot_sha256 = [BitConverter]::ToString($a.ComputeHash([Text.UTF8Encoding]::new($false).GetBytes(($e.task_snapshot | ConvertTo-Json -Depth 14 -Compress)))).Replace("-", "").ToLowerInvariant() } finally { $a.Dispose() }
$e.PSObject.Properties.Remove("registration_record_sha256")
$a = [Security.Cryptography.SHA256]::Create()
try { $recordHash = [BitConverter]::ToString($a.ComputeHash([Text.UTF8Encoding]::new($false).GetBytes(($e | ConvertTo-Json -Depth 16 -Compress)))).Replace("-", "").ToLowerInvariant() } finally { $a.Dispose() }
$e | Add-Member -NotePropertyName registration_record_sha256 -NotePropertyValue $recordHash
[IO.File]::WriteAllText($path, (($e | ConvertTo-Json -Depth 16) + "`n"), [Text.UTF8Encoding]::new($false))
'''

        def verify_tampered(project_root: Path) -> subprocess.CompletedProcess[str]:
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
                    "-VerifyRegistrationEvidence",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            target = project / "data/cache/research/ndx_dynamic_shadow_activation_v2"
            target.mkdir(parents=True)
            evidence = target / "selection_task_registration.json"
            value = json.loads(source_evidence.read_text(encoding="utf-8"))
            value["registration_record_sha256"] = "0" * 64
            evidence.write_text(json.dumps(value), encoding="utf-8")
            failed = verify_tampered(project)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("record hash mismatch", failed.stderr)

        for mode in ("action", "xml"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                target = project / "data/cache/research/ndx_dynamic_shadow_activation_v2"
                target.mkdir(parents=True)
                evidence = target / "selection_task_registration.json"
                evidence.write_bytes(source_evidence.read_bytes())
                environment = os.environ.copy()
                environment["TEST_EVIDENCE_PATH"] = str(evidence)
                environment["TEST_TAMPER_MODE"] = mode
                resigned = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", resign],
                    cwd=ROOT,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                self.assertEqual(resigned.returncode, 0, resigned.stderr)
                failed = verify_tampered(project)
                self.assertNotEqual(failed.returncode, 0)
                self.assertIn(
                    "Current selection task differs from immutable registration evidence",
                    failed.stderr,
                )


if __name__ == "__main__":
    unittest.main()
