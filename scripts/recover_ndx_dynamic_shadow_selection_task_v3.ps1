[CmdletBinding()]
param(
    [string]$ProjectRoot = "E:\Git\us_ratchet",
    [string]$PythonExecutable = "D:\python\python.exe",
    [switch]$Apply,
    [switch]$VerifyPostEvidence,
    [switch]$AcknowledgeApprovedVersionedRepairScope,
    [switch]$AcknowledgeResearchOnlyNoLiveMutation,
    [string]$EvidenceAttemptRoot = "",
    [string]$ExpectedRecoveryAuthoritySha256 = "",
    [switch]$InternalFunctionTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$root = [System.IO.Path]::GetFullPath($ProjectRoot)
$recoveryCallerParameters = [ordered]@{
    Apply = [bool]$Apply
    VerifyPostEvidence = [bool]$VerifyPostEvidence
    AcknowledgeApprovedVersionedRepairScope = [bool]$AcknowledgeApprovedVersionedRepairScope
    AcknowledgeResearchOnlyNoLiveMutation = [bool]$AcknowledgeResearchOnlyNoLiveMutation
    EvidenceAttemptRoot = [string]$EvidenceAttemptRoot
    ExpectedRecoveryAuthoritySha256 = [string]$ExpectedRecoveryAuthoritySha256
    InternalFunctionTest = [bool]$InternalFunctionTest
}

# Reuse only the already reviewed primitive hash/task/smoke/rollback helpers.
# -InternalFunctionTest guarantees that the predecessor installer performs no main action.
. (Join-Path $root "scripts\migrate_ndx_dynamic_shadow_selection_task_v3.ps1") `
    -ProjectRoot $root -PythonExecutable $PythonExecutable -InternalFunctionTest
$Apply = $recoveryCallerParameters.Apply
$VerifyPostEvidence = $recoveryCallerParameters.VerifyPostEvidence
$AcknowledgeApprovedVersionedRepairScope = $recoveryCallerParameters.AcknowledgeApprovedVersionedRepairScope
$AcknowledgeResearchOnlyNoLiveMutation = $recoveryCallerParameters.AcknowledgeResearchOnlyNoLiveMutation
$EvidenceAttemptRoot = $recoveryCallerParameters.EvidenceAttemptRoot
$ExpectedRecoveryAuthoritySha256 = $recoveryCallerParameters.ExpectedRecoveryAuthoritySha256
$InternalFunctionTest = $recoveryCallerParameters.InternalFunctionTest

$failedAttempt = Join-Path $root "data\cache\research\ndx_dynamic_shadow_task_migration_v3\attempts\20260905T2020425499105Z_84f18f027ff34a3bb639e40976169081"
$failedPrePath = Join-Path $failedAttempt "pre_cutover.json"
$failedRollbackPath = Join-Path $failedAttempt "rollback.json"
$recoveryScript = Join-Path $root "scripts\ndx_dynamic_shadow_runtime_v3_recovery.py"
$recoveryBase = Join-Path $root "data\cache\research\ndx_dynamic_shadow_task_migration_v3_recovery"
$recoveryAuthority = Join-Path $recoveryBase "reviewed_source_manifest.json"
$recoveryRoot = if ($EvidenceAttemptRoot) {
    [System.IO.Path]::GetFullPath($EvidenceAttemptRoot)
} elseif ($Apply) {
    Join-Path $recoveryBase ("attempts\{0}_{1}" -f [datetime]::UtcNow.ToString("yyyyMMddTHHmmssfffffffZ"), [guid]::NewGuid().ToString("N"))
} else { $recoveryBase }
$recoveryPrefix = [System.IO.Path]::GetFullPath($recoveryBase).TrimEnd('\') + '\'
if (
    [System.IO.Path]::GetFullPath($recoveryRoot) -ne [System.IO.Path]::GetFullPath($recoveryBase) -and
    -not [System.IO.Path]::GetFullPath($recoveryRoot).StartsWith($recoveryPrefix, [StringComparison]::OrdinalIgnoreCase)
) { throw "EvidenceAttemptRoot must remain inside the recovery evidence base." }
$preEvidence = Join-Path $recoveryRoot "pre_recovery.json"
$postEvidence = Join-Path $recoveryRoot "post_recovery.json"
$rollbackEvidence = Join-Path $recoveryRoot "rollback.json"

function Invoke-RecoveryReadiness {
    $output = & $PythonExecutable -B $recoveryScript --readiness 2>&1
    $exitCode = $LASTEXITCODE
    try { $document = (($output | Out-String).Trim() | ConvertFrom-Json) }
    catch { throw "Recovery readiness did not return valid JSON (exit=$exitCode)." }
    return [ordered]@{ exit_code = $exitCode; document = $document }
}

function Assert-RecoveryAuthority {
    param([Parameter(Mandatory = $true)][string]$ExpectedFileSha256)
    if (-not $ExpectedFileSha256) { throw "An independently reviewed recovery authority SHA256 is required." }
    if (-not (Test-Path -LiteralPath $recoveryAuthority -PathType Leaf)) { throw "Recovery authority is missing." }
    $actual = Get-Sha256Hex -Path $recoveryAuthority
    if ($actual -ne $ExpectedFileSha256.ToLowerInvariant()) { throw "Recovery authority file SHA256 changed." }
    $output = & $PythonExecutable -B $recoveryScript --verify-authority $recoveryAuthority 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Recovery authority full verification failed: $($output | Out-String)" }
    return $actual
}

function Read-FailedAttempt {
    foreach ($path in @($failedPrePath, $failedRollbackPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Failed attempt evidence is missing: $path" }
    }
    $pre = Get-Content -LiteralPath $failedPrePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $rollback = Get-Content -LiteralPath $failedRollbackPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not (Test-RecordHash $pre) -or -not (Test-RecordHash $rollback)) {
        throw "Failed attempt record envelope/hash changed."
    }
    if (
        [string]$rollback.pre_cutover_record_sha256 -ne [string]$pre.record_sha256 -or
        $null -ne $rollback.disabled_registration_record_sha256 -or
        [string]$rollback.reason -ne "New v3 Scheduled Task differs from the approved exact contract." -or
        $rollback.new_task_secured_before_old_restore -ne $true -or
        $rollback.old_task_restored -ne $true
    ) { throw "Failed attempt is not the reviewed disabled-registration rollback." }
    return [ordered]@{ pre = $pre; rollback = $rollback }
}

function Get-RecoveryTaskXmlWithoutGlobalEnabled {
    param([Parameter(Mandatory = $true)][string]$TaskXml)
    [xml]$document = $TaskXml
    $namespace = New-Object System.Xml.XmlNamespaceManager($document.NameTable)
    $namespace.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")
    $nodes = @($document.SelectNodes("/t:Task/t:Settings/t:Enabled", $namespace))
    if ($nodes.Count -gt 1) { throw "Task XML contains multiple global Enabled settings." }
    if ($nodes.Count -eq 1) { $nodes[0].ParentNode.RemoveChild($nodes[0]) | Out-Null }
    return $document.OuterXml
}

function Assert-RecoveryEvidenceBindings {
    param(
        [Parameter(Mandatory = $true)]$Pre,
        [Parameter(Mandatory = $true)]$Post,
        [Parameter(Mandatory = $true)]$Failed,
        [Parameter(Mandatory = $true)][string]$AuthorityHash,
        [Parameter(Mandatory = $true)]$OldSnapshot,
        [Parameter(Mandatory = $true)]$FailedV2Snapshot,
        [Parameter(Mandatory = $true)]$NewSnapshot
    )
    $failedPreSha256 = Get-Sha256Hex $failedPrePath
    $failedRollbackSha256 = Get-Sha256Hex $failedRollbackPath
    $canonicalAuthorityPath = [System.IO.Path]::GetFullPath($recoveryAuthority)
    $canonicalFailedAttemptPath = [System.IO.Path]::GetFullPath($failedAttempt)
    foreach ($record in @($Pre, $Post)) {
        if (
            [System.IO.Path]::GetFullPath([string]$record.authority.path) -ne $canonicalAuthorityPath -or
            [string]$record.authority.sha256 -ne $AuthorityHash -or
            [System.IO.Path]::GetFullPath([string]$record.failed_attempt.path) -ne $canonicalFailedAttemptPath -or
            [string]$record.failed_attempt.pre_sha256 -ne $failedPreSha256 -or
            [string]$record.failed_attempt.rollback_sha256 -ne $failedRollbackSha256
        ) { throw "Recovery authority or failed-attempt binding changed." }
        Assert-DirectoryFileHashes $oldV2EvidenceRoot $record.old_v2_evidence_hashes
    }
    if (
        [string]$OldSnapshot.task_xml_sha256 -ne [string]$Post.old_task.task_xml_sha256 -or
        [string]$FailedV2Snapshot.task_xml_sha256 -ne [string]$Post.failed_v2_task.task_xml_sha256 -or
        [string]$NewSnapshot.task_xml_sha256 -ne [string]$Post.new_task.task_xml_sha256 -or
        [string]$FailedV2Snapshot.task_xml_sha256 -ne [string]$Failed.rollback.failed_v2_task.task_xml_sha256 -or
        (Get-RecoveryTaskXmlWithoutGlobalEnabled ([string]$OldSnapshot.task_xml)) -cne
            (Get-RecoveryTaskXmlWithoutGlobalEnabled ([string]$Failed.rollback.old_task.task_xml)) -or
        (Get-RecoveryTaskXmlWithoutGlobalEnabled ([string]$NewSnapshot.task_xml)) -cne
            (Get-RecoveryTaskXmlWithoutGlobalEnabled ([string]$Failed.rollback.new_task.task_xml))
    ) { throw "Recovery post task XML binding changed." }
}

function Assert-RecoveryTaskContract {
    param(
        [Parameter(Mandatory = $true)]$Snapshot,
        [Parameter(Mandatory = $true)]$FrozenRollback,
        [Parameter(Mandatory = $true)][bool]$ExpectedEnabled,
        [switch]$RequireNeverRunSinceFailure
    )
    $frozen = $FrozenRollback.new_task
    [xml]$document = $Snapshot.task_xml
    $namespace = New-Object System.Xml.XmlNamespaceManager($document.NameTable)
    $namespace.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")
    $trigger = $document.SelectSingleNode("/t:Task/t:Triggers/t:CalendarTrigger", $namespace)
    $schedule = if ($null -eq $trigger) { $null } else { $trigger.SelectSingleNode("t:ScheduleByWeek", $namespace) }
    if ($null -eq $trigger -or $null -eq $schedule) { throw "Recovery task is not the expected weekly CalendarTrigger." }
    $triggerNames = @($trigger.ChildNodes | Where-Object { $_.NodeType -eq [Xml.XmlNodeType]::Element } | ForEach-Object { $_.LocalName })
    $scheduleNames = @($schedule.ChildNodes | Where-Object { $_.NodeType -eq [Xml.XmlNodeType]::Element } | ForEach-Object { $_.LocalName })
    $daysNode = $schedule.SelectSingleNode("t:DaysOfWeek", $namespace)
    $days = @($daysNode.ChildNodes | Where-Object { $_.NodeType -eq [Xml.XmlNodeType]::Element } | ForEach-Object { $_.LocalName })
    $triggerEnabledNode = $trigger.SelectSingleNode("t:Enabled", $namespace)
    $triggerEnabledSemantic = $null -eq $triggerEnabledNode -or $triggerEnabledNode.InnerText -eq "true"
    $allowedTriggerShape = (
        (($triggerNames | Sort-Object) -join ",") -in @("ScheduleByWeek,StartBoundary", "Enabled,ScheduleByWeek,StartBoundary") -and
        (($scheduleNames | Sort-Object) -join ",") -eq "DaysOfWeek,WeeksInterval" -and
        ($days -join ",") -eq "Tuesday,Wednesday,Thursday,Friday,Saturday" -and
        $triggerEnabledSemantic
    )
    $startTime = ([datetime]::Parse([string]$Snapshot.trigger.start_boundary, [Globalization.CultureInfo]::InvariantCulture)).ToString("HH:mm")
    if (
        $Snapshot.enabled -ne $ExpectedEnabled -or
        $Snapshot.state -eq "Running" -or
        [System.IO.Path]::GetFullPath($Snapshot.action.execute) -ne [System.IO.Path]::GetFullPath($PythonExecutable) -or
        $Snapshot.action.arguments -ne ('-B "{0}" --execute' -f $dailyV3) -or
        [System.IO.Path]::GetFullPath($Snapshot.action.working_directory) -ne $root -or
        $startTime -ne "11:20" -or $Snapshot.trigger.days_of_week_bitmask -ne 124 -or $Snapshot.trigger.weeks_interval -ne 1 -or
        $Snapshot.settings.start_when_available -ne $true -or
        $Snapshot.settings.disallow_start_if_on_batteries -ne $false -or $Snapshot.settings.stop_if_going_on_batteries -ne $false -or
        $Snapshot.settings.multiple_instances -ne "IGNORENEW" -or $Snapshot.settings.execution_time_limit -ne "PT11H" -or
        $Snapshot.settings.restart_count -ne 3 -or $Snapshot.settings.restart_interval -ne "PT10M" -or
        $Snapshot.principal.user_id -ne $frozen.principal.user_id -or
        $Snapshot.principal.logon_type -ne $frozen.principal.logon_type -or
        $Snapshot.principal.run_level -ne $frozen.principal.run_level -or
        -not $allowedTriggerShape
    ) { throw "Existing v3 task differs from the reviewed recovery contract." }
    if ($RequireNeverRunSinceFailure -and (
        $Snapshot.task_xml_sha256 -ne $frozen.task_xml_sha256 -or
        [int]$Snapshot.runtime.last_task_result -ne 267011 -or
        [int]$Snapshot.runtime.last_task_result -ne [int]$frozen.runtime.last_task_result
    )) { throw "Existing v3 task changed or ran after the failed registration attempt." }
}

function Assert-RecoveryRuntimeTriggerSemantics {
    $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName -ErrorAction Stop
    $triggers = @($task.Triggers)
    if ($triggers.Count -ne 1 -or [bool]$triggers[0].Enabled -ne $true) {
        throw "Existing v3 task CIM trigger is not exactly one enabled trigger."
    }
    $service = New-Object -ComObject "Schedule.Service"
    $service.Connect()
    $registered = $service.GetFolder($taskPath).GetTask($newTaskName)
    $comTriggers = $registered.Definition.Triggers
    if (
        $comTriggers.Count -ne 1 -or
        [int]$comTriggers.Item(1).Type -ne 3 -or
        [bool]$comTriggers.Item(1).Enabled -ne $true
    ) { throw "Existing v3 task COM trigger is not exactly one enabled weekly trigger." }
}

if ($InternalFunctionTest) { return }
if ($Apply -and $VerifyPostEvidence) { throw "Choose only one of Apply or VerifyPostEvidence." }

if ($VerifyPostEvidence) {
    if (-not $EvidenceAttemptRoot) { throw "VerifyPostEvidence requires its immutable EvidenceAttemptRoot." }
    $authorityHash = Assert-RecoveryAuthority $ExpectedRecoveryAuthoritySha256
    foreach ($path in @($preEvidence, $postEvidence)) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Recovery evidence missing: $path" } }
    $pre = Get-Content -LiteralPath $preEvidence -Raw -Encoding UTF8 | ConvertFrom-Json
    $post = Get-Content -LiteralPath $postEvidence -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not (Test-RecordHash $pre) -or -not (Test-RecordHash $post) -or $post.pre_recovery_record_sha256 -ne $pre.record_sha256) { throw "Recovery evidence chain changed." }
    $failed = Read-FailedAttempt
    Assert-ActivationVerifier -ExpectedManifestSha256 $post.activation_manifest_sha256 | Out-Null
    Invoke-SmokeArtifactVerification -ExpectedPath $postEvidence | Out-Null
    $old = Get-TaskSnapshot $oldTaskName; $v2 = Get-TaskSnapshot $failedV2TaskName; $new = Get-TaskSnapshot $newTaskName
    if ($old.enabled -or $v2.enabled -or $v2.state -eq "Running") { throw "Post-recovery three-task state changed." }
    Assert-RecoveryEvidenceBindings -Pre $pre -Post $post -Failed $failed -AuthorityHash $authorityHash -OldSnapshot $old -FailedV2Snapshot $v2 -NewSnapshot $new
    Assert-RecoveryTaskContract -Snapshot $new -FrozenRollback $failed.rollback -ExpectedEnabled $true
    Assert-RecoveryRuntimeTriggerSemantics
    Assert-ExclusiveSchedulerAndNoRuntimeProcess -AllowedEnabledTaskName $newTaskName
    Assert-ProtectedHashes $post.protected_hashes
    [ordered]@{status="V3_RECOVERY_POST_VERIFIED";mutation_performed=$false}|ConvertTo-Json
    exit 0
}

$readiness = Invoke-RecoveryReadiness
$plan = [ordered]@{
    schema_version=1; manifest_type="ndx_dynamic_shadow_runtime_v3_existing_task_recovery_plan"; mode=if($Apply){"APPLY_REQUESTED"}else{"PLAN_ONLY"}
    status=if($readiness.exit_code -eq 0 -and $readiness.document.status -eq "READY_FOR_REVIEWED_EXISTING_TASK_RECOVERY"){"READY_FOR_EXPLICIT_RECOVERY"}else{"BLOCKED_BY_READINESS"}
    failed_attempt=$failedAttempt; existing_v3_task=$newTaskName; registration_allowed=$false; task_deletion_allowed=$false
    recovery_authority=[ordered]@{path=$recoveryAuthority;file_sha256=if(Test-Path $recoveryAuthority){Get-Sha256Hex $recoveryAuthority}else{$null};expected_sha256_required=$true}
    evidence_root=$recoveryRoot; readiness=$readiness.document; mutation_performed=$false
}
if (-not $Apply) { $plan|ConvertTo-Json -Depth 30; exit 0 }
if (-not $AcknowledgeApprovedVersionedRepairScope -or -not $AcknowledgeResearchOnlyNoLiveMutation) { throw "Apply requires both approved-scope acknowledgements." }
if ($plan.status -ne "READY_FOR_EXPLICIT_RECOVERY") { throw "Recovery readiness is not READY." }
if (Test-Path -LiteralPath $recoveryRoot) { throw "Versioned recovery attempt evidence already exists." }
$authorityHash = Assert-RecoveryAuthority $ExpectedRecoveryAuthoritySha256
$failed = Read-FailedAttempt
$protectedBefore = Get-ProtectedHashes
Assert-ProtectedHashes $failed.rollback.protected_hashes
$oldV2Hashes = Get-DirectoryFileHashes $oldV2EvidenceRoot
Assert-DirectoryFileHashes $oldV2EvidenceRoot $failed.pre.old_v2_evidence_hashes
Assert-ActivationVerifier -ExpectedManifestSha256 $failed.pre.activation_manifest.sha256 | Out-Null
$oldBefore=Get-TaskSnapshot $oldTaskName; $v2Before=Get-TaskSnapshot $failedV2TaskName; $newBefore=Get-TaskSnapshot $newTaskName
if (-not $oldBefore.enabled -or $oldBefore.state -eq "Running" -or $oldBefore.task_xml_sha256 -ne $failed.rollback.old_task.task_xml_sha256) { throw "Old v1 task differs from failed-attempt rollback." }
if ($v2Before.enabled -or $v2Before.state -eq "Running" -or $v2Before.task_xml_sha256 -ne $failed.rollback.failed_v2_task.task_xml_sha256) { throw "Failed v2 task differs from failed-attempt rollback." }
Assert-RecoveryTaskContract -Snapshot $newBefore -FrozenRollback $failed.rollback -ExpectedEnabled $false -RequireNeverRunSinceFailure
Assert-RecoveryRuntimeTriggerSemantics
Assert-ExclusiveSchedulerAndNoRuntimeProcess $oldTaskName
$smokeBefore=Invoke-SmokeEvidenceSnapshot
$pre=[ordered]@{schema_version=1;manifest_type="ndx_dynamic_shadow_runtime_v3_pre_recovery";captured_at_utc=[datetime]::UtcNow.ToString("o");authority=[ordered]@{path=$recoveryAuthority;sha256=$authorityHash};failed_attempt=[ordered]@{path=$failedAttempt;pre_sha256=Get-Sha256Hex $failedPrePath;rollback_sha256=Get-Sha256Hex $failedRollbackPath};old_task=$oldBefore;failed_v2_task=$v2Before;new_task=$newBefore;smoke_before=$smokeBefore;old_v2_evidence_hashes=$oldV2Hashes;protected_hashes=$protectedBefore}
Write-ImmutableRecord $preEvidence $pre
$oldDisabled=$false
try {
    Disable-ScheduledTask -TaskPath $taskPath -TaskName $oldTaskName -ErrorAction Stop|Out-Null; $oldDisabled=$true
    Assert-OldTaskSecuredBeforeNewEnable $v2Before|Out-Null
    Enable-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName -ErrorAction Stop|Out-Null
    $newEnabled=Get-TaskSnapshot $newTaskName
    Assert-RecoveryTaskContract -Snapshot $newEnabled -FrozenRollback $failed.rollback -ExpectedEnabled $true
    Assert-RecoveryRuntimeTriggerSemantics
    if ((Get-TaskSnapshot $oldTaskName).enabled) { throw "Old and recovered v3 tasks are both enabled." }
    Assert-ExclusiveSchedulerAndNoRuntimeProcess $newTaskName
    $smoke=Invoke-RealScheduledTaskSmoke $newEnabled
    $artifact=Invoke-SmokeArtifactVerification -BeforePath $preEvidence
    $oldAfter=Get-TaskSnapshot $oldTaskName;$v2After=Get-TaskSnapshot $failedV2TaskName;$newAfter=Get-TaskSnapshot $newTaskName
    if ($oldAfter.enabled -or $v2After.enabled -or $v2After.state -eq "Running") { throw "Post-smoke predecessor task state changed." }
    Assert-RecoveryTaskContract -Snapshot $newAfter -FrozenRollback $failed.rollback -ExpectedEnabled $true
    Assert-RecoveryRuntimeTriggerSemantics
    Assert-ExclusiveSchedulerAndNoRuntimeProcess $newTaskName
    Assert-ActivationVerifier -ExpectedManifestSha256 $failed.pre.activation_manifest.sha256|Out-Null
    $authorityHashAfter = Assert-RecoveryAuthority $ExpectedRecoveryAuthoritySha256
    $failedAfter = Read-FailedAttempt
    if (
        $authorityHashAfter -ne $authorityHash -or
        (Get-Sha256Hex $failedPrePath) -ne [string]$pre.failed_attempt.pre_sha256 -or
        (Get-Sha256Hex $failedRollbackPath) -ne [string]$pre.failed_attempt.rollback_sha256
    ) { throw "Recovery authority or failed-attempt evidence drifted during smoke." }
    Assert-ProtectedHashes $protectedBefore;Assert-DirectoryFileHashes $oldV2EvidenceRoot $oldV2Hashes
    $post=[ordered]@{schema_version=1;manifest_type="ndx_dynamic_shadow_runtime_v3_post_recovery";captured_at_utc=[datetime]::UtcNow.ToString("o");status="V3_EXISTING_TASK_RECOVERY_SMOKE_PASSED";pre_recovery_record_sha256=$pre.record_sha256;authority=[ordered]@{path=$recoveryAuthority;sha256=$authorityHashAfter};failed_attempt=[ordered]@{path=$failedAttempt;pre_sha256=Get-Sha256Hex $failedPrePath;rollback_sha256=Get-Sha256Hex $failedRollbackPath};old_v2_evidence_hashes=$oldV2Hashes;activation_manifest_sha256=$failedAfter.pre.activation_manifest.sha256;old_task=$oldAfter;failed_v2_task=$v2After;new_task=$newAfter;smoke=[ordered]@{last_run_time=$smoke.runtime.last_run_time;last_task_result=$smoke.runtime.last_task_result;artifact_verification=$artifact};protected_hashes=Get-ProtectedHashes}
    Assert-RecoveryEvidenceBindings -Pre $pre -Post $post -Failed $failedAfter -AuthorityHash $authorityHashAfter -OldSnapshot $oldAfter -FailedV2Snapshot $v2After -NewSnapshot $newAfter
    Write-ImmutableRecord $postEvidence $post
    [ordered]@{status="V3_EXISTING_TASK_RECOVERY_COMPLETE";old_v1_enabled=$false;failed_v2_enabled=$false;new_v3_enabled=$true;evidence_root=$recoveryRoot;mutation_performed=$true}|ConvertTo-Json;exit 0
} catch {
    $result=Invoke-FailSafeRollback -NewCreated $true -OldDisabled $oldDisabled -InitialFailure $_.Exception.Message
    Assert-ProtectedHashes $protectedBefore;Assert-DirectoryFileHashes $oldV2EvidenceRoot $oldV2Hashes
    if(-not(Test-Path $rollbackEvidence)){$record=[ordered]@{schema_version=1;manifest_type="ndx_dynamic_shadow_runtime_v3_recovery_rollback";captured_at_utc=[datetime]::UtcNow.ToString("o");reason=$result.failure;new_task_secured=$result.new_task_secured;old_task_restored=$result.old_task_restored;pre_recovery_record_sha256=$pre.record_sha256;old_task=Get-TaskSnapshot $oldTaskName;failed_v2_task=Get-TaskSnapshot $failedV2TaskName;new_task=Get-TaskSnapshot $newTaskName;protected_hashes=Get-ProtectedHashes};Write-ImmutableRecord $rollbackEvidence $record}
    throw "Runtime-v3 existing-task recovery failed and rollback was attempted: $($result.failure)"
}
