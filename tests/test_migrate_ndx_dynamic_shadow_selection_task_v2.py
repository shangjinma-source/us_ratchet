from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/migrate_ndx_dynamic_shadow_selection_task_v2.ps1"


class AtomicV2TaskMigrationScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_default_mode_is_plan_only_and_does_not_mutate(self):
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(SCRIPT), "-ProjectRoot", str(ROOT)],
            cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        plan = json.loads(completed.stdout)
        self.assertEqual(plan["mode"], "PLAN_ONLY")
        self.assertFalse(plan["mutation_performed"])
        self.assertFalse(plan["protected_live_mutation_allowed"])

    def test_new_task_is_registered_disabled_before_old_is_disabled(self):
        create_disabled = self.source.index('$enabled.InnerText = "false"')
        register = self.source.index("Register-ScheduledTask -TaskName $newTaskName")
        disable_old = self.source.index("Disable-ScheduledTask -TaskName $oldTaskName")
        enable_new = self.source.index("Enable-ScheduledTask -TaskName $newTaskName | Out-Null")
        self.assertLess(create_disabled, register)
        self.assertLess(register, disable_old)
        self.assertLess(disable_old, enable_new)

    def test_battery_settings_are_false_and_old_contract_is_preserved(self):
        self.assertIn('@("DisallowStartIfOnBatteries", "StopIfGoingOnBatteries")', self.source)
        self.assertIn('$node.InnerText = "false"', self.source)
        for field in (
            "start_boundary", "days_of_week_bitmask", "weeks_interval", "principal.user_id",
            "multiple_instances", "restart_count", "restart_interval", "execution_time_limit",
        ):
            self.assertIn(field, self.source)

    def test_failure_rolls_back_without_deleting_tasks(self):
        self.assertIn("Disable-ScheduledTask -TaskName $newTaskName", self.source)
        self.assertIn("Enable-ScheduledTask -TaskName $oldTaskName", self.source)
        self.assertNotIn("Unregister-ScheduledTask", self.source)
        self.assertNotIn("Stop-Process", self.source)
        self.assertIn("NEW_DISABLED_OLD_ENABLED_NO_TASK_DELETION", self.source)

    def test_empty_process_inventory_is_always_counted_as_an_array(self):
        self.assertGreaterEqual(self.source.count("@(Get-OldExecutorProcesses).Count"), 3)
        self.assertNotIn("(Get-OldExecutorProcesses).Count", self.source.replace("@(Get-OldExecutorProcesses).Count", ""))

    def test_protected_files_and_immutable_evidence_are_explicit(self):
        for relative in ("config\\config.yaml", "data\\state.json", "data\\broker_positions.json"):
            self.assertIn(relative, self.source)
        self.assertIn("Write-ImmutableRecord", self.source)
        self.assertIn("USER_EXPLICITLY_APPROVED_ATOMIC_V2_BUDGETED_MIGRATION_AND_BATTERY_OPERATION", self.source)
        self.assertIn("-VerifyPostEvidence", self.source)

    def test_real_powershell_helpers_reject_pscustomobject_tamper_and_unsafe_rollback(self):
        command = rf'''
. "{SCRIPT}" -InternalFunctionTest
$payload = [ordered]@{{ schema_version = 1; name = "evidence" }}
$unsigned = $payload | ConvertTo-Json -Depth 20 -Compress
$payload["record_sha256"] = Get-StringSha256Hex -Value $unsigned
$roundTrip = ($payload | ConvertTo-Json -Depth 20) | ConvertFrom-Json
$valid = Test-RecordHash -Record $roundTrip
$roundTrip.name = "tampered"
$tampered = Test-RecordHash -Record $roundTrip
$script:oldEnableCalled = $false
function Disable-ScheduledTask {{ throw "simulated disable failure" }}
function Enable-ScheduledTask {{ $script:oldEnableCalled = $true }}
$rollback = Invoke-FailSafeRollback -NewCreated $true -OldDisabled $true -InitialFailure "test"
[ordered]@{{
  valid_record = $valid
  tampered_record = $tampered
  new_secured = $rollback.new_task_secured
  old_enable_called = $script:oldEnableCalled
  old_restored = $rollback.old_task_restored
}} | ConvertTo-Json -Compress
'''
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["valid_record"])
        self.assertFalse(result["tampered_record"])
        self.assertFalse(result["new_secured"])
        self.assertFalse(result["old_enable_called"])
        self.assertFalse(result["old_restored"])


if __name__ == "__main__":
    unittest.main()
