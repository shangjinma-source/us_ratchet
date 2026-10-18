[CmdletBinding()]
param(
    [string]$ProjectRoot = "E:\Git\us_ratchet",
    [string]$PythonExecutable = "D:\python\python.exe",
    [switch]$Apply,
    [switch]$VerifyPostEvidence,
    [switch]$AcknowledgeExplicitUserApproval,
    [switch]$AcknowledgeResearchOnlyNoLiveMutation,
    [switch]$InternalFunctionTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$root = [System.IO.Path]::GetFullPath($ProjectRoot)
$oldTaskName = "us_ratchet_ndx_dynamic_shadow_selection_daily"
$newTaskName = "us_ratchet_ndx_dynamic_shadow_selection_daily_v2_budgeted"
$readinessScript = Join-Path $root "scripts\ndx_dynamic_shadow_search_budget_task_migration.py"
$activationScript = Join-Path $root "scripts\ndx_dynamic_shadow_activation_v3.py"
$activationManifest = Join-Path $root "data\cache\research\ndx_dynamic_shadow_activation_v3\manifest.json"
$dailyV2 = Join-Path $root "scripts\ndx_dynamic_shadow_daily_v2.py"
$evidenceRoot = Join-Path $root "data\cache\research\ndx_dynamic_shadow_task_migration_v2"
$preEvidence = Join-Path $evidenceRoot "pre_cutover.json"
$disabledEvidence = Join-Path $evidenceRoot "new_disabled.json"
$postEvidence = Join-Path $evidenceRoot "post_cutover.json"
$rollbackEvidence = Join-Path $evidenceRoot "rollback.json"
$protectedPaths = @(
    (Join-Path $root "config\config.yaml"),
    (Join-Path $root "data\state.json"),
    (Join-Path $root "data\broker_positions.json")
)

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $algorithm = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([System.BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
        } finally {
            $algorithm.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Get-StringSha256Hex {
    param([Parameter(Mandatory = $true)][string]$Value)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Value)
        return ([System.BitConverter]::ToString($algorithm.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
    }
}

function Get-ProtectedHashes {
    $result = [ordered]@{}
    foreach ($path in $protectedPaths) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Protected live file is missing: $path"
        }
        $result[$path] = Get-Sha256Hex -Path $path
    }
    return $result
}

function Assert-ProtectedHashes {
    param([Parameter(Mandatory = $true)]$Expected)
    $current = Get-ProtectedHashes
    foreach ($path in $protectedPaths) {
        $expectedValue = if ($Expected -is [System.Collections.IDictionary]) {
            $Expected[$path]
        } else {
            $property = $Expected.PSObject.Properties[$path]
            if ($null -eq $property) { $null } else { $property.Value }
        }
        if ([string]$current[$path] -ne [string]$expectedValue) {
            throw "Protected live file changed during task migration: $path"
        }
    }
}

function Write-ImmutableRecord {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Payload
    )
    if (Test-Path -LiteralPath $Path) {
        throw "Immutable migration evidence already exists: $Path"
    }
    [System.IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    $unsigned = $Payload | ConvertTo-Json -Depth 20 -Compress
    $Payload["record_sha256"] = Get-StringSha256Hex -Value $unsigned
    $temporary = $Path + ".tmp." + [guid]::NewGuid().ToString("N")
    try {
        [System.IO.File]::WriteAllText(
            $temporary,
            (($Payload | ConvertTo-Json -Depth 20) + "`n"),
            [System.Text.UTF8Encoding]::new($false)
        )
        [System.IO.File]::Move($temporary, $Path)
    } finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function Get-TaskSnapshot {
    param([Parameter(Mandatory = $true)][string]$TaskName)
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $actions = @($task.Actions)
    $triggers = @($task.Triggers)
    if ($actions.Count -ne 1 -or $triggers.Count -ne 1) {
        throw "Task $TaskName must have exactly one action and one trigger."
    }
    $xml = Export-ScheduledTask -TaskName $TaskName
    return [ordered]@{
        task_name = $TaskName
        state = [string]$task.State
        enabled = ([string]$task.State -ne "Disabled")
        action = [ordered]@{
            execute = [string]$actions[0].Execute
            arguments = [string]$actions[0].Arguments
            working_directory = [string]$actions[0].WorkingDirectory
        }
        trigger = [ordered]@{
            start_boundary = [string]$triggers[0].StartBoundary
            days_of_week_bitmask = [int]$triggers[0].DaysOfWeek
            weeks_interval = [int]$triggers[0].WeeksInterval
        }
        settings = [ordered]@{
            start_when_available = [bool]$task.Settings.StartWhenAvailable
            disallow_start_if_on_batteries = [bool]$task.Settings.DisallowStartIfOnBatteries
            stop_if_going_on_batteries = [bool]$task.Settings.StopIfGoingOnBatteries
            multiple_instances = $task.Settings.MultipleInstances.ToString().ToUpperInvariant()
            restart_count = [int]$task.Settings.RestartCount
            restart_interval = [string]$task.Settings.RestartInterval
            execution_time_limit = [string]$task.Settings.ExecutionTimeLimit
        }
        principal = [ordered]@{
            user_id = [string]$task.Principal.UserId
            logon_type = $task.Principal.LogonType.ToString()
            run_level = $task.Principal.RunLevel.ToString()
        }
        task_xml = $xml
        task_xml_sha256 = Get-StringSha256Hex -Value $xml
    }
}

function Invoke-Readiness {
    $output = & $PythonExecutable -B $readinessScript --readiness 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | Out-String).Trim()
    try {
        $document = $text | ConvertFrom-Json
    } catch {
        throw "Migration readiness did not return valid JSON (exit=$exitCode)."
    }
    return [ordered]@{ exit_code = $exitCode; document = $document }
}

function Assert-ActivationVerifier {
    $output = & $PythonExecutable -B $activationScript --verify-activation-manifest 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Activation-v3 verification failed: $($output | Out-String)"
    }
}

function Get-OldExecutorProcesses {
    $escaped = [regex]::Escape("ndx_dynamic_shadow_daily.py")
    return @(
        Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
            [string]$_.CommandLine -match $escaped -and
            [string]$_.CommandLine -match "(?i)--execute" -and
            [string]$_.CommandLine -notmatch "ndx_dynamic_shadow_daily_v2\.py"
        } | Select-Object ProcessId, Name, CommandLine
    )
}

function New-DisabledV2TaskXml {
    param([Parameter(Mandatory = $true)][string]$OldXml)
    [xml]$document = $OldXml
    $namespace = New-Object System.Xml.XmlNamespaceManager($document.NameTable)
    $namespace.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")
    $document.SelectSingleNode("/t:Task/t:RegistrationInfo/t:URI", $namespace).InnerText = "\$newTaskName"
    $document.SelectSingleNode("/t:Task/t:Actions/t:Exec/t:Command", $namespace).InnerText = $PythonExecutable
    $document.SelectSingleNode("/t:Task/t:Actions/t:Exec/t:Arguments", $namespace).InnerText = '-B "{0}" --execute' -f $dailyV2
    $document.SelectSingleNode("/t:Task/t:Actions/t:Exec/t:WorkingDirectory", $namespace).InnerText = $root
    $settings = $document.SelectSingleNode("/t:Task/t:Settings", $namespace)
    foreach ($name in @("DisallowStartIfOnBatteries", "StopIfGoingOnBatteries")) {
        $node = $settings.SelectSingleNode("t:$name", $namespace)
        if ($null -eq $node) {
            $node = $document.CreateElement($name, $document.DocumentElement.NamespaceURI)
            $settings.AppendChild($node) | Out-Null
        }
        $node.InnerText = "false"
    }
    $enabled = $settings.SelectSingleNode("t:Enabled", $namespace)
    if ($null -eq $enabled) {
        $enabled = $document.CreateElement("Enabled", $document.DocumentElement.NamespaceURI)
        $settings.AppendChild($enabled) | Out-Null
    }
    $enabled.InnerText = "false"
    return $document.OuterXml
}

function Assert-NewTaskContract {
    param(
        [Parameter(Mandatory = $true)]$Old,
        [Parameter(Mandatory = $true)]$New,
        [Parameter(Mandatory = $true)][bool]$ExpectedEnabled
    )
    $expectedArguments = '-B "{0}" --execute' -f $dailyV2
    if (
        $New.enabled -ne $ExpectedEnabled -or
        $New.action.execute -ne $PythonExecutable -or
        $New.action.arguments -ne $expectedArguments -or
        [System.IO.Path]::GetFullPath($New.action.working_directory) -ne $root -or
        $New.trigger.start_boundary -ne $Old.trigger.start_boundary -or
        $New.trigger.days_of_week_bitmask -ne $Old.trigger.days_of_week_bitmask -or
        $New.trigger.weeks_interval -ne $Old.trigger.weeks_interval -or
        $New.principal.user_id -ne $Old.principal.user_id -or
        $New.principal.logon_type -ne $Old.principal.logon_type -or
        $New.principal.run_level -ne $Old.principal.run_level -or
        $New.settings.start_when_available -ne $Old.settings.start_when_available -or
        $New.settings.multiple_instances -ne $Old.settings.multiple_instances -or
        $New.settings.restart_count -ne $Old.settings.restart_count -or
        $New.settings.restart_interval -ne $Old.settings.restart_interval -or
        $New.settings.execution_time_limit -ne $Old.settings.execution_time_limit -or
        $New.settings.disallow_start_if_on_batteries -ne $false -or
        $New.settings.stop_if_going_on_batteries -ne $false
    ) {
        throw "New v2 Scheduled Task differs from the approved migration contract."
    }
}

function Test-RecordHash {
    param([Parameter(Mandatory = $true)]$Record)
    $declared = [string]$Record.record_sha256
    $unsigned = [ordered]@{}
    foreach ($property in $Record.PSObject.Properties) {
        if ($property.Name -ne "record_sha256") {
            $unsigned[$property.Name] = $property.Value
        }
    }
    return (Get-StringSha256Hex -Value ($unsigned | ConvertTo-Json -Depth 20 -Compress)) -eq $declared
}

function Invoke-FailSafeRollback {
    param(
        [Parameter(Mandatory = $true)][bool]$NewCreated,
        [Parameter(Mandatory = $true)][bool]$OldDisabled,
        [Parameter(Mandatory = $true)][string]$InitialFailure
    )
    $failure = $InitialFailure
    $newSecured = -not $NewCreated
    $oldRestored = -not $OldDisabled
    if ($NewCreated) {
        try {
            Disable-ScheduledTask -TaskName $newTaskName -ErrorAction Stop | Out-Null
            $newState = (Get-ScheduledTask -TaskName $newTaskName -ErrorAction Stop).State.ToString()
            if ($newState -eq "Running") {
                Stop-ScheduledTask -TaskName $newTaskName -ErrorAction Stop
                for ($attempt = 0; $attempt -lt 20; $attempt++) {
                    Start-Sleep -Milliseconds 250
                    $newState = (Get-ScheduledTask -TaskName $newTaskName -ErrorAction Stop).State.ToString()
                    if ($newState -ne "Running") { break }
                }
            }
            $newSnapshot = Get-TaskSnapshot -TaskName $newTaskName
            $newSecured = (-not $newSnapshot.enabled -and $newSnapshot.state -ne "Running")
        } catch {
            $newSecured = $false
            $failure = "$failure; failed to secure new task during rollback: $($_.Exception.Message)"
        }
    }
    if ($OldDisabled -and $newSecured) {
        try {
            Enable-ScheduledTask -TaskName $oldTaskName -ErrorAction Stop | Out-Null
            $oldRestored = (Get-TaskSnapshot -TaskName $oldTaskName).enabled -eq $true
            if (-not $oldRestored) {
                $failure = "$failure; old task enable command did not restore enabled state"
            }
        } catch {
            $oldRestored = $false
            $failure = "$failure; failed to restore old task: $($_.Exception.Message)"
        }
    } elseif ($OldDisabled -and -not $newSecured) {
        $failure = "$failure; old task intentionally left disabled because new task could not be proven stopped+disabled"
    }
    return [ordered]@{
        failure = $failure
        new_task_secured = $newSecured
        old_task_restored = $oldRestored
    }
}

if ($InternalFunctionTest) {
    return
}

if ($Apply -and $VerifyPostEvidence) {
    throw "Choose only one of -Apply or -VerifyPostEvidence."
}

if ($VerifyPostEvidence) {
    foreach ($path in @($preEvidence, $disabledEvidence, $postEvidence)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Migration evidence is missing: $path"
        }
    }
    $pre = Get-Content -LiteralPath $preEvidence -Raw -Encoding UTF8 | ConvertFrom-Json
    $disabled = Get-Content -LiteralPath $disabledEvidence -Raw -Encoding UTF8 | ConvertFrom-Json
    $post = Get-Content -LiteralPath $postEvidence -Raw -Encoding UTF8 | ConvertFrom-Json
    if (
        -not (Test-RecordHash -Record $pre) -or
        -not (Test-RecordHash -Record $disabled) -or
        -not (Test-RecordHash -Record $post)
    ) {
        throw "Migration evidence record hash mismatch."
    }
    if (
        [string]$post.pre_cutover_record_sha256 -ne [string]$pre.record_sha256 -or
        [string]$post.disabled_registration_record_sha256 -ne [string]$disabled.record_sha256
    ) {
        throw "Post-cutover evidence chain link mismatch."
    }
    $frozenActivationHash = [string]$post.activation_manifest.sha256
    if (
        $frozenActivationHash -ne [string]$pre.activation_manifest.sha256 -or
        $frozenActivationHash -ne [string]$disabled.activation_manifest_sha256 -or
        $frozenActivationHash -ne (Get-Sha256Hex -Path $activationManifest)
    ) {
        throw "Activation manifest differs from the cutover-frozen hash."
    }
    $old = Get-TaskSnapshot -TaskName $oldTaskName
    $new = Get-TaskSnapshot -TaskName $newTaskName
    if ($old.enabled -or -not $new.enabled) {
        throw "Current task enablement differs from post-cutover evidence."
    }
    if ($old.task_xml_sha256 -ne $post.old_task.task_xml_sha256 -or $new.task_xml_sha256 -ne $post.new_task.task_xml_sha256) {
        throw "Current task XML differs from immutable post-cutover evidence."
    }
    Assert-ProtectedHashes -Expected $post.protected_hashes
    Assert-ActivationVerifier
    [ordered]@{ status = "POST_CUTOVER_VERIFIED"; mutation_performed = $false } | ConvertTo-Json
    exit 0
}

$readiness = Invoke-Readiness
$plan = [ordered]@{
    schema_version = 1
    manifest_type = "ndx_dynamic_shadow_selection_task_v2_atomic_migration_plan"
    mode = if ($Apply) { "APPLY_REQUESTED" } else { "PLAN_ONLY" }
    status = if ($readiness.exit_code -eq 0 -and $readiness.document.status -eq "READY_FOR_EXPLICITLY_AUTHORIZED_ATOMIC_MIGRATION") {
        "READY_FOR_EXPLICIT_APPROVAL"
    } else {
        "BLOCKED_BY_READINESS"
    }
    old_task = $oldTaskName
    new_task = $newTaskName
    new_task_initial_state = "DISABLED"
    never_parallel_enable = $true
    rollback = "DISABLE_NEW_THEN_ENABLE_OLD_PRESERVE_BOTH_TASKS_AND_EVIDENCE"
    activation_manifest = [ordered]@{
        path = $activationManifest
        sha256 = if (Test-Path -LiteralPath $activationManifest) { Get-Sha256Hex -Path $activationManifest } else { $null }
    }
    protected_live_files = $protectedPaths
    protected_live_mutation_allowed = $false
    readiness = $readiness.document
    mutation_performed = $false
}

if (-not $Apply) {
    $plan | ConvertTo-Json -Depth 20
    exit 0
}

if (-not $AcknowledgeExplicitUserApproval -or -not $AcknowledgeResearchOnlyNoLiveMutation) {
    throw "Apply requires both explicit approval acknowledgements."
}
if ($plan.status -ne "READY_FOR_EXPLICIT_APPROVAL") {
    throw "Migration readiness is not READY; current task remains unchanged."
}
if (
    (Test-Path -LiteralPath $preEvidence) -or
    (Test-Path -LiteralPath $disabledEvidence) -or
    (Test-Path -LiteralPath $postEvidence)
) {
    throw "Migration evidence already exists; refusing a second cutover."
}
if (Get-ScheduledTask -TaskName $newTaskName -ErrorAction SilentlyContinue) {
    throw "New v2 task already exists; refusing replacement."
}

$protectedBefore = Get-ProtectedHashes
$oldBefore = Get-TaskSnapshot -TaskName $oldTaskName
if (-not $oldBefore.enabled -or $oldBefore.state -eq "Running") {
    throw "Old task must be enabled and not running before cutover."
}
if (@(Get-OldExecutorProcesses).Count -ne 0) {
    throw "Old executor process is running; cutover refused without stopping it."
}
Assert-ActivationVerifier

$pre = [ordered]@{
    schema_version = 1
    manifest_type = "ndx_dynamic_shadow_selection_task_v2_pre_cutover"
    captured_at_utc = [datetime]::UtcNow.ToString("o")
    authorization = [ordered]@{
        evidence = "USER_EXPLICITLY_APPROVED_ATOMIC_V2_BUDGETED_MIGRATION_AND_BATTERY_OPERATION"
        approval_date_asia_shanghai = "2026-09-06"
        scope = "RESEARCH_SCHEDULED_TASK_ONLY_NO_LIVE_CONFIG_STATE_BROKER_ADVICE_OR_ORDER_MUTATION"
    }
    activation_manifest = [ordered]@{ path = $activationManifest; sha256 = Get-Sha256Hex -Path $activationManifest }
    readiness_script = [ordered]@{ path = $readinessScript; sha256 = Get-Sha256Hex -Path $readinessScript }
    migration_script = [ordered]@{ path = $PSCommandPath; sha256 = Get-Sha256Hex -Path $PSCommandPath }
    old_task = $oldBefore
    protected_hashes = $protectedBefore
}
Write-ImmutableRecord -Path $preEvidence -Payload $pre

$newCreated = $false
$oldDisabled = $false
try {
    $newXml = New-DisabledV2TaskXml -OldXml $oldBefore.task_xml
    Register-ScheduledTask -TaskName $newTaskName -Xml $newXml -Force:$false | Out-Null
    $newCreated = $true
    $newDisabled = Get-TaskSnapshot -TaskName $newTaskName
    Assert-NewTaskContract -Old $oldBefore -New $newDisabled -ExpectedEnabled $false
    if (-not (Get-TaskSnapshot -TaskName $oldTaskName).enabled) {
        throw "Old task changed before the atomic enablement cutover."
    }
    $disabled = [ordered]@{
        schema_version = 1
        manifest_type = "ndx_dynamic_shadow_selection_task_v2_disabled_registration"
        captured_at_utc = [datetime]::UtcNow.ToString("o")
        activation_manifest_sha256 = Get-Sha256Hex -Path $activationManifest
        old_task = Get-TaskSnapshot -TaskName $oldTaskName
        new_task = $newDisabled
        protected_hashes = Get-ProtectedHashes
    }
    Write-ImmutableRecord -Path $disabledEvidence -Payload $disabled
    Assert-ProtectedHashes -Expected $protectedBefore

    Disable-ScheduledTask -TaskName $oldTaskName | Out-Null
    $oldDisabled = $true
    if ((Get-TaskSnapshot -TaskName $oldTaskName).enabled) {
        throw "Old task did not enter Disabled state."
    }
    if (@(Get-OldExecutorProcesses).Count -ne 0) {
        throw "Old executor process remained after disable; rolling back without enabling v2."
    }
    Enable-ScheduledTask -TaskName $newTaskName | Out-Null
    $newEnabled = Get-TaskSnapshot -TaskName $newTaskName
    Assert-NewTaskContract -Old $oldBefore -New $newEnabled -ExpectedEnabled $true
    $oldAfter = Get-TaskSnapshot -TaskName $oldTaskName
    if ($oldAfter.enabled) {
        throw "Old and new tasks would be enabled together."
    }
    Assert-ActivationVerifier
    Assert-ProtectedHashes -Expected $protectedBefore

    $post = [ordered]@{
        schema_version = 1
        manifest_type = "ndx_dynamic_shadow_selection_task_v2_post_cutover"
        captured_at_utc = [datetime]::UtcNow.ToString("o")
        status = "V2_ENABLED_OLD_DISABLED_POST_VERIFIED"
        activation_manifest = [ordered]@{ path = $activationManifest; sha256 = Get-Sha256Hex -Path $activationManifest }
        pre_cutover_record_sha256 = $pre.record_sha256
        disabled_registration_record_sha256 = $disabled.record_sha256
        old_task = $oldAfter
        new_task = $newEnabled
        old_executor_process_count = @(Get-OldExecutorProcesses).Count
        smoke = "ACTIVATION_REBUILD_AND_SCHEDULED_TASK_CONFIGURATION_VERIFIED_NO_MANUAL_SELECTION_RUN"
        protected_hashes = Get-ProtectedHashes
    }
    Write-ImmutableRecord -Path $postEvidence -Payload $post
    [ordered]@{
        status = "ATOMIC_MIGRATION_COMPLETE"
        old_task_enabled = $false
        new_task_enabled = $true
        evidence_root = $evidenceRoot
        mutation_performed = $true
    } | ConvertTo-Json
    exit 0
} catch {
    $rollbackResult = Invoke-FailSafeRollback `
        -NewCreated $newCreated `
        -OldDisabled $oldDisabled `
        -InitialFailure $_.Exception.Message
    $failure = [string]$rollbackResult.failure
    $newSecured = [bool]$rollbackResult.new_task_secured
    Assert-ProtectedHashes -Expected $protectedBefore
    if (-not (Test-Path -LiteralPath $rollbackEvidence)) {
        $rollback = [ordered]@{
            schema_version = 1
            manifest_type = "ndx_dynamic_shadow_selection_task_v2_rollback"
            captured_at_utc = [datetime]::UtcNow.ToString("o")
            reason = $failure
            new_task_secured_before_old_restore = $newSecured
            old_task_restored = [bool]$rollbackResult.old_task_restored
            old_task = Get-TaskSnapshot -TaskName $oldTaskName
            new_task = if (Get-ScheduledTask -TaskName $newTaskName -ErrorAction SilentlyContinue) {
                Get-TaskSnapshot -TaskName $newTaskName
            } else { $null }
            rollback_contract = "NEW_DISABLED_OLD_ENABLED_NO_TASK_DELETION"
            protected_hashes = Get-ProtectedHashes
        }
        Write-ImmutableRecord -Path $rollbackEvidence -Payload $rollback
    }
    throw "Atomic migration failed and rollback was attempted: $failure"
}
