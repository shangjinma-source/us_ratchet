from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/migrate_ndx_dynamic_shadow_selection_task_v3.ps1"


class AtomicRuntimeV3TaskMigrationScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_default_mode_is_plan_only_and_does_not_mutate(self):
        completed = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
                "-ProjectRoot", str(ROOT),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        plan = json.loads(completed.stdout)
        self.assertEqual(plan["mode"], "PLAN_ONLY")
        self.assertFalse(plan["mutation_performed"])
        self.assertFalse(plan["protected_live_mutation_allowed"])
        self.assertEqual(plan["failed_v2_task"], "us_ratchet_ndx_dynamic_shadow_selection_daily_v2_budgeted")
        self.assertEqual(plan["approved_schedule"]["days_of_week_bitmask"], 124)
        self.assertEqual(plan["approved_schedule"]["execution_time_limit"], "PT11H")

    def test_disabled_registration_precedes_exclusive_cutover_and_smoke(self):
        register = self.source.index("Register-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName")
        disabled_record = self.source.index("Write-ImmutableRecord -Path $disabledEvidence")
        disable_old = self.source.index(
            "Disable-ScheduledTask -TaskPath $taskPath -TaskName $oldTaskName"
        )
        secure_old = self.source.index(
            "Assert-OldTaskSecuredBeforeNewEnable -FailedV2Baseline $failedV2Before"
        )
        enable_new = self.source.index(
            "Enable-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName"
        )
        smoke = self.source.index("Invoke-RealScheduledTaskSmoke -Before $newEnabled")
        artifact = self.source.index("Invoke-SmokeArtifactVerification -BeforePath $preEvidence")
        self.assertLess(register, disabled_record)
        self.assertLess(disabled_record, disable_old)
        self.assertLess(disable_old, secure_old)
        self.assertLess(secure_old, enable_new)
        self.assertLess(enable_new, smoke)
        self.assertLess(smoke, artifact)

    def test_exact_approved_scheduler_contract_is_enforced(self):
        for value in (
            '"Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"',
            '"T11:20:00"',
            '"StartWhenAvailable", "true"',
            '"DisallowStartIfOnBatteries", "false"',
            '"StopIfGoingOnBatteries", "false"',
            '"MultipleInstancesPolicy", "IgnoreNew"',
            '"ExecutionTimeLimit", "PT11H"',
            '"Interval" -Value "PT10M"',
            '"Count" -Value "3"',
            "$New.trigger.days_of_week_bitmask -ne 124",
        ):
            self.assertIn(value, self.source)

    def test_generated_xml_has_exact_schedule_and_preserves_principal_bytes(self):
        command = rf'''
. "{SCRIPT}" -InternalFunctionTest
$old = Get-TaskSnapshot -TaskName $oldTaskName
[xml]$before = $old.task_xml
[xml]$after = New-DisabledV3TaskXml -OldXml $old.task_xml
$beforeNs = New-Object System.Xml.XmlNamespaceManager($before.NameTable)
$afterNs = New-Object System.Xml.XmlNamespaceManager($after.NameTable)
$beforeNs.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")
$afterNs.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")
$days = @($after.SelectSingleNode("/t:Task/t:Triggers/t:CalendarTrigger/t:ScheduleByWeek/t:DaysOfWeek", $afterNs).ChildNodes | ForEach-Object {{ $_.LocalName }})
[ordered]@{{
  arguments = $after.SelectSingleNode("/t:Task/t:Actions/t:Exec/t:Arguments", $afterNs).InnerText
  start = $after.SelectSingleNode("/t:Task/t:Triggers/t:CalendarTrigger/t:StartBoundary", $afterNs).InnerText
  days = $days
  principal_same = ($before.SelectSingleNode("/t:Task/t:Principals", $beforeNs).OuterXml -eq $after.SelectSingleNode("/t:Task/t:Principals", $afterNs).OuterXml)
  enabled = $after.SelectSingleNode("/t:Task/t:Settings/t:Enabled", $afterNs).InnerText
}} | ConvertTo-Json -Depth 5 -Compress
'''
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["principal_same"])
        self.assertTrue(result["start"].endswith("T11:20:00"))
        self.assertEqual(result["days"], ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"])
        self.assertEqual(result["enabled"], "false")
        self.assertIn("ndx_dynamic_shadow_daily_v3.py", result["arguments"])

    def test_trigger_repetition_end_boundary_and_random_delay_are_rejected(self):
        command = rf'''
. "{SCRIPT}" -InternalFunctionTest
$old = Get-TaskSnapshot -TaskName $oldTaskName
$results = [ordered]@{{}}
foreach ($name in @("Repetition", "EndBoundary", "RandomDelay")) {{
  [xml]$document = $old.task_xml
  $namespace = New-Object System.Xml.XmlNamespaceManager($document.NameTable)
  $namespace.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")
  $trigger = $document.SelectSingleNode("/t:Task/t:Triggers/t:CalendarTrigger", $namespace)
  $node = $document.CreateElement($name, $document.DocumentElement.NamespaceURI)
  $node.InnerText = if ($name -eq "EndBoundary") {{ "2027-01-01T00:00:00" }} else {{ "PT1H" }}
  $trigger.AppendChild($node) | Out-Null
  try {{
    New-DisabledV3TaskXml -OldXml $document.OuterXml | Out-Null
    $results[$name] = $false
  }} catch {{
    $results[$name] = $_.Exception.Message -like "*unsupported*"
  }}
}}
$results | ConvertTo-Json -Compress
'''
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            {"Repetition": True, "EndBoundary": True, "RandomDelay": True},
        )

    def test_activation_authority_smoke_and_three_task_gates_are_replayed(self):
        self.assertGreaterEqual(self.source.count("Assert-ActivationVerifier"), 5)
        self.assertIn("Assert-MigrationAuthority", self.source)
        self.assertIn("ExpectedMigrationAuthoritySha256", self.source)
        self.assertIn("--verify-authority", self.source)
        self.assertIn("Invoke-SmokeEvidenceSnapshot", self.source)
        self.assertIn("--expected-path", self.source)
        self.assertIn("Assert-ThreeTaskCutoverState", self.source)
        self.assertIn("Assert-FailedV2Unchanged", self.source)
        self.assertIn("old_v2_evidence_hashes", self.source)
        self.assertIn("Invoke-OldV2NotaryVerifier", self.source)
        self.assertIn("ndx_dynamic_shadow_task_migration_notary.py", self.source)
        self.assertIn("matching_daily_process_count_after_smoke = 0", self.source)

    def test_duplicate_and_process_detection_is_case_insensitive_and_includes_fresh_search(self):
        self.assertIn("ToLowerInvariant()", self.source)
        self.assertIn(".openclaw\\cron\\jobs.json", self.source)
        self.assertIn("ndx_dynamic_shadow_fresh_search(?:_v2|_v3)?", self.source)
        self.assertGreaterEqual(
            self.source.count("Assert-ExclusiveSchedulerAndNoRuntimeProcess"), 3
        )

    def test_evidence_is_versioned_and_old_lineage_is_never_overwritten(self):
        self.assertIn('"attempts\\{0}_{1}"', self.source)
        self.assertIn("old_v2_evidence_overwrite_allowed = $false", self.source)
        self.assertIn("Get-DirectoryFileHashes", self.source)
        self.assertIn("Assert-DirectoryFileHashes", self.source)
        self.assertNotIn("Unregister-ScheduledTask", self.source)
        self.assertNotIn("Remove-Item -LiteralPath $oldV2EvidenceRoot", self.source)

    def test_pscustomobject_record_hash_roundtrip_and_tamper(self):
        command = rf'''
. "{SCRIPT}" -InternalFunctionTest
$payload = [ordered]@{{
  schema_version = 1
  captured_at_utc = [datetime]::UtcNow.ToString("o")
  nested = [ordered]@{{ value = "evidence"; count = 3 }}
}}
$unsigned = $payload | ConvertTo-Json -Depth 30 -Compress
$payload["record_hash_algorithm"] = "SHA256_UTF8_EXACT_RECORD_PAYLOAD_JSON_V1"
$payload["record_payload_json"] = $unsigned
$payload["record_sha256"] = Get-StringSha256Hex -Value $unsigned
$roundTrip = ($payload | ConvertTo-Json -Depth 30) | ConvertFrom-Json
$valid = Test-RecordHash -Record $roundTrip
$roundTrip.nested.value = "tampered"
$tampered = Test-RecordHash -Record $roundTrip
[ordered]@{{valid=$valid; tampered=$tampered}} | ConvertTo-Json -Compress
'''
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["valid"])
        self.assertFalse(result["tampered"])

    def test_record_written_by_windows_powershell_verifies_in_powershell_7(self):
        pwsh = shutil.which("pwsh.exe")
        if not pwsh:
            self.skipTest("PowerShell 7 is not installed")
        with TemporaryDirectory() as temporary:
            record_path = Path(temporary) / "record.json"
            writer = rf'''
. "{SCRIPT}" -InternalFunctionTest
$payload = [ordered]@{{
  schema_version = 1
  captured_at_utc = [datetime]::UtcNow.ToString("o")
  nested = [ordered]@{{ when = [datetime]::UtcNow; value = "evidence" }}
}}
Write-ImmutableRecord -Path "{record_path}" -Payload $payload
'''
            written = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", writer],
                cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(written.returncode, 0, written.stderr)
            reader = rf'''
. "{SCRIPT}" -InternalFunctionTest
$record = Get-Content -LiteralPath "{record_path}" -Raw -Encoding UTF8 | ConvertFrom-Json
[ordered]@{{
  edition = $PSVersionTable.PSEdition
  valid = Test-RecordHash -Record $record
}} | ConvertTo-Json -Compress
'''
            checked = subprocess.run(
                [pwsh, "-NoProfile", "-NonInteractive", "-Command", reader],
                cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            result = json.loads(checked.stdout)
            self.assertEqual(result["edition"], "Core")
            self.assertTrue(result["valid"])

    def test_rollback_never_restores_old_while_runtime_child_remains(self):
        command = rf'''
. "{SCRIPT}" -InternalFunctionTest
$script:oldEnableCalled = $false
function Disable-ScheduledTask {{}}
function Stop-ScheduledTask {{}}
function Get-ScheduledTask {{ [pscustomobject]@{{ State = "Disabled" }} }}
function Get-TaskSnapshot {{
  param([string]$TaskName)
  if ($TaskName -eq $script:newTaskName) {{
    return [ordered]@{{ enabled = $false; state = "Disabled" }}
  }}
  return [ordered]@{{ enabled = $true; state = "Ready" }}
}}
function Get-MatchingDailyProcesses {{ return @([ordered]@{{ process_id = 99 }}) }}
function Enable-ScheduledTask {{ $script:oldEnableCalled = $true }}
$result = Invoke-FailSafeRollback -NewCreated $true -OldDisabled $true -InitialFailure "test"
[ordered]@{{
  new_secured = $result.new_task_secured
  old_restored = $result.old_task_restored
  old_enable_called = $script:oldEnableCalled
}} | ConvertTo-Json -Compress
'''
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertFalse(result["new_secured"])
        self.assertFalse(result["old_restored"])
        self.assertFalse(result["old_enable_called"])

    def test_old_task_running_after_disable_prevents_new_enable(self):
        command = rf'''
. "{SCRIPT}" -InternalFunctionTest
$script:newEnableCalled = $false
function Get-TaskSnapshot {{ return [ordered]@{{ enabled = $false; state = "Running" }} }}
function Enable-ScheduledTask {{ $script:newEnableCalled = $true }}
$rejected = $false
try {{
  Assert-OldTaskSecuredBeforeNewEnable -FailedV2Baseline ([ordered]@{{}}) | Out-Null
  Enable-ScheduledTask
}} catch {{
  $rejected = $_.Exception.Message -like "*not proven disabled and stopped*"
}}
[ordered]@{{ rejected = $rejected; new_enable_called = $script:newEnableCalled }} | ConvertTo-Json -Compress
'''
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["rejected"])
        self.assertFalse(result["new_enable_called"])

    def test_empty_allowed_task_name_is_a_real_no_enabled_scheduler_gate(self):
        command = rf'''
. "{SCRIPT}" -InternalFunctionTest
$bindingWorked = $false
try {{
  Assert-ExclusiveSchedulerAndNoRuntimeProcess -AllowedEnabledTaskName ""
}} catch {{
  $bindingWorked = $_.Exception.Message -like "*Another enabled dynamic-shadow scheduler exists*"
}}
[ordered]@{{ binding_worked = $bindingWorked }} | ConvertTo-Json -Compress
'''
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["binding_worked"])

    def test_windows_com_handler_action_without_execute_is_ignored_safely(self):
        command = rf'''
. "{SCRIPT}" -InternalFunctionTest
function Get-ScheduledTask {{
  return [pscustomobject]@{{
    TaskName = "SystemComHandler"
    TaskPath = "\Microsoft\Windows\"
    State = "Ready"
    Actions = @([pscustomobject]@{{ ClassId = "fixture" }})
  }}
}}
$result = @(Get-ActiveDuplicateSchedulers -AllowedEnabledTaskName "")
[ordered]@{{ count = $result.Count }} | ConvertTo-Json -Compress
'''
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["count"], 0)


if __name__ == "__main__":
    unittest.main()
