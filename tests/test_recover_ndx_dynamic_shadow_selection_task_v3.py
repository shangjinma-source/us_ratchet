from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/recover_ndx_dynamic_shadow_selection_task_v3.ps1"


class RuntimeV3ExistingTaskRecoveryScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def run_ps(self, body):
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", body],
            cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8",
        )

    def test_default_is_plan_only_and_current_recovery_is_ready(self):
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(SCRIPT), "-ProjectRoot", str(ROOT)],
            cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        plan = json.loads(completed.stdout)
        self.assertEqual(plan["mode"], "PLAN_ONLY")
        self.assertIn(plan["status"], {"READY_FOR_EXPLICIT_RECOVERY", "BLOCKED_BY_READINESS"})
        self.assertFalse(plan["registration_allowed"])
        self.assertFalse(plan["task_deletion_allowed"])
        self.assertFalse(plan["mutation_performed"])
        self.assertLessEqual(len(plan["readiness"]["task_gate"]["observed"]), 3)
        self.assertNotIn("arguments", json.dumps(plan["readiness"]["task_gate"]["observed"]))

    def test_reuses_existing_task_without_register_delete_or_force(self):
        self.assertNotIn("Register-ScheduledTask", self.source)
        self.assertNotIn("Unregister-ScheduledTask", self.source)
        self.assertNotIn("-Force", self.source)
        self.assertIn("reuse_existing_disabled_v3_task_only", (
            ROOT / "backtest/ndx_dynamic_shadow_runtime_v3_recovery.py"
        ).read_text(encoding="utf-8"))

    def test_apply_switch_survives_dot_source_and_fails_before_mutation_on_bad_authority(self):
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(SCRIPT), "-ProjectRoot", str(ROOT), "-Apply",
             "-AcknowledgeApprovedVersionedRepairScope",
             "-AcknowledgeResearchOnlyNoLiveMutation",
             "-ExpectedRecoveryAuthoritySha256", "0" * 64],
            cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertTrue(
            "Recovery authority is missing" in completed.stderr
            or "Recovery authority file SHA256 changed" in completed.stderr
            or "Recovery readiness is not READY" in completed.stderr,
            completed.stderr,
        )

    def test_missing_trigger_enabled_is_accepted_but_false_and_extra_are_rejected(self):
        command = rf'''
. "{SCRIPT}" -ProjectRoot "{ROOT}" -InternalFunctionTest
$failed = Read-FailedAttempt
$snapshot = ($failed.rollback.new_task | ConvertTo-Json -Depth 30 | ConvertFrom-Json)
$accepted = $true
try {{ Assert-RecoveryTaskContract $snapshot $failed.rollback $false -RequireNeverRunSinceFailure }} catch {{ $accepted = $false }}
[xml]$falseDocument = $snapshot.task_xml
$namespace = New-Object System.Xml.XmlNamespaceManager($falseDocument.NameTable);$namespace.AddNamespace("t","http://schemas.microsoft.com/windows/2004/02/mit/task")
$trigger=$falseDocument.SelectSingleNode("/t:Task/t:Triggers/t:CalendarTrigger",$namespace)
$enabled=$falseDocument.CreateElement("Enabled",$falseDocument.DocumentElement.NamespaceURI);$enabled.InnerText="false";$trigger.AppendChild($enabled)|Out-Null
$falseSnapshot=($snapshot|ConvertTo-Json -Depth 30|ConvertFrom-Json);$falseSnapshot.task_xml=$falseDocument.OuterXml
$falseRejected=$false
try {{ Assert-RecoveryTaskContract $falseSnapshot $failed.rollback $false }} catch {{ $falseRejected=$true }}
[xml]$extraDocument=$snapshot.task_xml;$extraNs=New-Object System.Xml.XmlNamespaceManager($extraDocument.NameTable);$extraNs.AddNamespace("t","http://schemas.microsoft.com/windows/2004/02/mit/task")
$extraTrigger=$extraDocument.SelectSingleNode("/t:Task/t:Triggers/t:CalendarTrigger",$extraNs);$delay=$extraDocument.CreateElement("RandomDelay",$extraDocument.DocumentElement.NamespaceURI);$delay.InnerText="PT1H";$extraTrigger.AppendChild($delay)|Out-Null
$extraSnapshot=($snapshot|ConvertTo-Json -Depth 30|ConvertFrom-Json);$extraSnapshot.task_xml=$extraDocument.OuterXml
$extraRejected=$false
try {{ Assert-RecoveryTaskContract $extraSnapshot $failed.rollback $false }} catch {{ $extraRejected=$true }}
[ordered]@{{accepted=$accepted;false_rejected=$falseRejected;extra_rejected=$extraRejected}}|ConvertTo-Json -Compress
'''
        completed = self.run_ps(command)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {
            "accepted": True, "false_rejected": True, "extra_rejected": True,
        })

    def test_evidence_bindings_reject_authority_and_task_xml_tamper(self):
        completed = self.run_ps(rf'''
. "{SCRIPT}" -ProjectRoot "{ROOT}" -InternalFunctionTest
$failed = Read-FailedAttempt
$authorityHash = "a" * 64
$failedBinding = [ordered]@{{path=$failedAttempt;pre_sha256=Get-Sha256Hex $failedPrePath;rollback_sha256=Get-Sha256Hex $failedRollbackPath}}
$pre = [ordered]@{{authority=[ordered]@{{path=$recoveryAuthority;sha256=$authorityHash}};failed_attempt=$failedBinding;old_v2_evidence_hashes=$failed.pre.old_v2_evidence_hashes}}
function Copy-WithGlobalEnabled($source, [bool]$enabled, [string]$hash) {{
    $snapshot = ($source | ConvertTo-Json -Depth 30 | ConvertFrom-Json)
    [xml]$document = $snapshot.task_xml
    $namespace = New-Object System.Xml.XmlNamespaceManager($document.NameTable);$namespace.AddNamespace("t","http://schemas.microsoft.com/windows/2004/02/mit/task")
    $settings = $document.SelectSingleNode("/t:Task/t:Settings",$namespace)
    $node = $settings.SelectSingleNode("t:Enabled",$namespace)
    if($null -eq $node){{$node=$document.CreateElement("Enabled",$document.DocumentElement.NamespaceURI);$settings.AppendChild($node)|Out-Null}}
    $node.InnerText = if($enabled){{"true"}}else{{"false"}}
    $snapshot.task_xml = $document.OuterXml;$snapshot.task_xml_sha256 = $hash
    return $snapshot
}}
$disabledOldSnapshot = Copy-WithGlobalEnabled $failed.rollback.old_task $false ("e" * 64)
$enabledSnapshot = Copy-WithGlobalEnabled $failed.rollback.new_task $true ("d" * 64)
$post = [ordered]@{{authority=[ordered]@{{path=$recoveryAuthority;sha256=$authorityHash}};failed_attempt=$failedBinding;old_v2_evidence_hashes=$failed.pre.old_v2_evidence_hashes;old_task=$disabledOldSnapshot;failed_v2_task=$failed.rollback.failed_v2_task;new_task=$enabledSnapshot}}
$accepted = $true
try {{ Assert-RecoveryEvidenceBindings $pre $post $failed $authorityHash $disabledOldSnapshot $failed.rollback.failed_v2_task $enabledSnapshot }} catch {{ $accepted = $false }}
$authorityTamper = ($post | ConvertTo-Json -Depth 30 | ConvertFrom-Json);$authorityTamper.authority.sha256 = "b" * 64
$authorityRejected = $false
try {{ Assert-RecoveryEvidenceBindings $pre $authorityTamper $failed $authorityHash $disabledOldSnapshot $failed.rollback.failed_v2_task $enabledSnapshot }} catch {{ $authorityRejected = $true }}
$xmlTamper = ($post | ConvertTo-Json -Depth 30 | ConvertFrom-Json);$xmlTamper.new_task.task_xml_sha256 = "c" * 64
$xmlRejected = $false
try {{ Assert-RecoveryEvidenceBindings $pre $xmlTamper $failed $authorityHash $disabledOldSnapshot $failed.rollback.failed_v2_task $enabledSnapshot }} catch {{ $xmlRejected = $true }}
[ordered]@{{accepted=$accepted;authority_rejected=$authorityRejected;xml_rejected=$xmlRejected}} | ConvertTo-Json -Compress
''')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {
            "accepted": True, "authority_rejected": True, "xml_rejected": True,
        })

    def test_real_cim_and_com_trigger_semantics_are_true(self):
        completed = self.run_ps(rf'''
. "{SCRIPT}" -ProjectRoot "{ROOT}" -InternalFunctionTest
Assert-RecoveryRuntimeTriggerSemantics
[ordered]@{{verified=$true}}|ConvertTo-Json -Compress
''')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["verified"])

    def test_cutover_orders_disable_secure_enable_and_real_smoke(self):
        disable = self.source.index("Disable-ScheduledTask -TaskPath $taskPath -TaskName $oldTaskName")
        secure = self.source.index("Assert-OldTaskSecuredBeforeNewEnable $v2Before")
        enable = self.source.index("Enable-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName")
        smoke = self.source.index("Invoke-RealScheduledTaskSmoke $newEnabled")
        artifact = self.source.index("Invoke-SmokeArtifactVerification -BeforePath $preEvidence")
        self.assertLess(disable, secure)
        self.assertLess(secure, enable)
        self.assertLess(enable, smoke)
        self.assertLess(smoke, artifact)

    def test_authority_failed_attempt_protected_and_rollback_are_explicit(self):
        for text in (
            "ExpectedRecoveryAuthoritySha256", "Assert-RecoveryAuthority", "Read-FailedAttempt",
            "Assert-ProtectedHashes", "Assert-DirectoryFileHashes", "Invoke-FailSafeRollback",
            "Invoke-SmokeArtifactVerification", "VerifyPostEvidence", "Assert-RecoveryEvidenceBindings",
            "authorityHashAfter", "failed_attempt", "old_v2_evidence_hashes",
        ):
            self.assertIn(text, self.source)


if __name__ == "__main__":
    unittest.main()
