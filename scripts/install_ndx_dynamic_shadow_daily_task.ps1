[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$TaskName = "us_ratchet_ndx_dynamic_shadow_readiness_daily",
    [string]$PythonExecutable = "D:\python\python.exe",
    [string]$DailyTime = "11:20",
    [string]$RunnerScript = "scripts\ndx_dynamic_shadow_runner.py",
    [string]$ReadinessManifest = "data\cache\research\ndx_dynamic_shadow_activation_readiness_v1\manifest.json",
    [switch]$Apply,
    [switch]$AcknowledgeExternalSchedulerDisabled,
    [switch]$AcknowledgeReadinessOnlyNoDecisionGeneration
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Get-OptionalProperty {
    param(
        [AllowNull()]$InputObject,
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()]$Default = $null
    )
    if ($null -eq $InputObject) {
        return $Default
    }
    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $Default
    }
    return $property.Value
}

function Resolve-RepositoryPath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $Path))
}

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $algorithm = [System.Security.Cryptography.SHA256]::Create()
        try {
            $bytes = $algorithm.ComputeHash($stream)
        } finally {
            $algorithm.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
    return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
}

function Test-ReadinessInputHashes {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [AllowNull()]$Inputs
    )
    $checks = @()
    if ($null -eq $Inputs) {
        return [ordered]@{ passed = $false; checked = 0; checks = @() }
    }
    $entries = @()
    if ($Inputs -is [System.Array]) {
        for ($index = 0; $index -lt $Inputs.Count; $index++) {
            $entries += [ordered]@{ name = "input_$index"; value = $Inputs[$index] }
        }
    } else {
        foreach ($property in $Inputs.PSObject.Properties) {
            $entries += [ordered]@{ name = $property.Name; value = $property.Value }
        }
    }
    foreach ($entry in $entries) {
        $item = $entry.value
        $declaredPath = [string](Get-OptionalProperty -InputObject $item -Name "path" -Default "")
        $declaredHash = ([string](Get-OptionalProperty -InputObject $item -Name "sha256" -Default "")).ToLowerInvariant()
        if (-not $declaredPath -or -not $declaredHash) {
            $checks += [ordered]@{ name = $entry.name; path = $declaredPath; passed = $false; reason = "PATH_OR_SHA256_MISSING" }
            continue
        }
        $resolvedPath = Resolve-RepositoryPath -Root $Root -Path $declaredPath
        $rootPrefix = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
        if (-not $resolvedPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            $checks += [ordered]@{ name = $entry.name; path = $resolvedPath; passed = $false; reason = "PATH_OUTSIDE_REPOSITORY" }
            continue
        }
        if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf)) {
            $checks += [ordered]@{ name = $entry.name; path = $resolvedPath; passed = $false; reason = "FILE_MISSING" }
            continue
        }
        $actualHash = Get-Sha256Hex -Path $resolvedPath
        $checks += [ordered]@{
            name = $entry.name
            path = $resolvedPath
            passed = ($actualHash -eq $declaredHash)
            reason = if ($actualHash -eq $declaredHash) { "MATCH" } else { "SHA256_MISMATCH" }
        }
    }
    $failed = @($checks | Where-Object { -not $_.passed })
    return [ordered]@{
        passed = ($checks.Count -gt 0 -and $failed.Count -eq 0)
        checked = $checks.Count
        checks = $checks
    }
}

$resolvedRoot = if ($ProjectRoot) {
    (Resolve-Path -LiteralPath $ProjectRoot).Path
} else {
    (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}
$resolvedRunner = Resolve-RepositoryPath -Root $resolvedRoot -Path $RunnerScript
$resolvedReadiness = Resolve-RepositoryPath -Root $resolvedRoot -Path $ReadinessManifest
$canonicalRunner = [System.IO.Path]::GetFullPath((Join-Path $resolvedRoot "scripts\ndx_dynamic_shadow_runner.py"))
$canonicalReadiness = [System.IO.Path]::GetFullPath((Join-Path $resolvedRoot "data\cache\research\ndx_dynamic_shadow_activation_readiness_v1\manifest.json"))
$activationVerifier = [System.IO.Path]::GetFullPath((Join-Path $resolvedRoot "scripts\ndx_dynamic_shadow_activation_readiness.py"))
$selectionWrapper = [System.IO.Path]::GetFullPath((Join-Path $resolvedRoot "scripts\ndx_dynamic_shadow_daily.py"))
$selectionContract = [System.IO.Path]::GetFullPath((Join-Path $resolvedRoot "config\ndx_dynamic_shadow_daily_v1.yaml"))
$activationVerifierPresent = Test-Path -LiteralPath $activationVerifier -PathType Leaf
$selectionWrapperPresent = Test-Path -LiteralPath $selectionWrapper -PathType Leaf
$selectionContractPresent = Test-Path -LiteralPath $selectionContract -PathType Leaf
$canonicalPathsSelected = (
    $resolvedRunner -eq $canonicalRunner -and $resolvedReadiness -eq $canonicalReadiness
)
$runnerPresent = Test-Path -LiteralPath $resolvedRunner -PathType Leaf
$pythonPresent = Test-Path -LiteralPath $PythonExecutable -PathType Leaf
$systemTimeZoneId = (Get-TimeZone).Id
$beijingTimeZone = $systemTimeZoneId -eq "China Standard Time"

$readiness = $null
$readinessParseError = $null
if (Test-Path -LiteralPath $resolvedReadiness -PathType Leaf) {
    try {
        $readiness = Get-Content -LiteralPath $resolvedReadiness -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        $readinessParseError = $_.Exception.Message
    }
}

$guards = Get-OptionalProperty -InputObject $readiness -Name "guards"
$requiredGuards = @(
    "runner_registered",
    "selector_registry_active",
    "decision_generation_allowed",
    "no_backfill_verified",
    "next_session_execution_verified",
    "append_only_verified",
    "live_isolation_verified",
    "immutable_artifact_evidence_verified"
)
$guardChecks = [ordered]@{}
foreach ($name in $requiredGuards) {
    $guardChecks[$name] = ((Get-OptionalProperty -InputObject $guards -Name $name -Default $false) -eq $true)
}
$allGuardsPassed = -not ($guardChecks.Values -contains $false)
$inputHashChecks = Test-ReadinessInputHashes `
    -Root $resolvedRoot `
    -Inputs (Get-OptionalProperty -InputObject $readiness -Name "inputs")
$runnerHashBound = @(
    $inputHashChecks.checks | Where-Object {
        $_.passed -and [System.IO.Path]::GetFullPath([string]$_.path) -eq $resolvedRunner
    }
).Count -eq 1
$activationVerifierHashBound = @(
    $inputHashChecks.checks | Where-Object {
        $_.passed -and [System.IO.Path]::GetFullPath([string]$_.path) -eq $activationVerifier
    }
).Count -eq 1
$selectionWrapperHashBound = @(
    $inputHashChecks.checks | Where-Object {
        $_.passed -and [System.IO.Path]::GetFullPath([string]$_.path) -eq $selectionWrapper
    }
).Count -eq 1
$selectionContractHashBound = @(
    $inputHashChecks.checks | Where-Object {
        $_.passed -and [System.IO.Path]::GetFullPath([string]$_.path) -eq $selectionContract
    }
).Count -eq 1

$manifestType = [string](Get-OptionalProperty -InputObject $readiness -Name "manifest_type" -Default "MISSING")
$readinessStatus = [string](Get-OptionalProperty -InputObject $readiness -Name "status" -Default "MISSING")
$automationRegistrationAllowed = (
    (Get-OptionalProperty -InputObject $readiness -Name "automation_registration_allowed" -Default $false) -eq $true
)
$historicalReplayDisabled = (
    (Get-OptionalProperty -InputObject $readiness -Name "historical_candidate_replay_allowed" -Default $true) -eq $false
)
$retrospectiveBackfillDisabled = (
    (Get-OptionalProperty -InputObject $readiness -Name "retrospective_backfill_allowed" -Default $true) -eq $false
)
$frozenForwardSourceDisabled = (
    (Get-OptionalProperty -InputObject $readiness -Name "frozen_forward_candidates_allowed_as_dynamic_source" -Default $true) -eq $false
)
$callerBooleansCannotActivate = (
    (Get-OptionalProperty -InputObject $readiness -Name "caller_supplied_booleans_can_activate" -Default $true) -eq $false
)
$readinessGatePassed = (
    $runnerPresent -and
    $pythonPresent -and
    $beijingTimeZone -and
    $canonicalPathsSelected -and
    $activationVerifierPresent -and
    $null -eq $readinessParseError -and
    $manifestType -eq "ndx_dynamic_shadow_activation_readiness" -and
    $readinessStatus -eq "READY_FOR_AUTOMATION_REGISTRATION" -and
    $automationRegistrationAllowed -and
    $allGuardsPassed -and
    $historicalReplayDisabled -and
    $retrospectiveBackfillDisabled -and
    $frozenForwardSourceDisabled -and
    $callerBooleansCannotActivate -and
    $inputHashChecks.passed -and
    $runnerHashBound -and
    $activationVerifierHashBound
)

$windowsDuplicates = @()
if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {
    foreach ($task in Get-ScheduledTask) {
        foreach ($taskAction in @($task.Actions)) {
            $actionExecute = [string](Get-OptionalProperty -InputObject $taskAction -Name "Execute" -Default "")
            $actionArgumentsValue = [string](Get-OptionalProperty -InputObject $taskAction -Name "Arguments" -Default "")
            $actionText = "$actionExecute $actionArgumentsValue"
            if (
                $task.TaskName -ne $TaskName -and
                ($actionText -match "(?i)ndx_dynamic_shadow_runner\.py.*--readiness" -or $task.TaskName -match "(?i)ndx.*dynamic.*shadow.*readiness")
            ) {
                $windowsDuplicates += [ordered]@{
                    task_name = $task.TaskName
                    state = [string]$task.State
                    enabled = [bool]$task.Settings.Enabled
                    action = $actionText
                }
            }
        }
    }
}

$openClawDefinitions = @()
$openClawJobsPath = Join-Path $env:USERPROFILE ".openclaw\cron\jobs.json"
if (Test-Path -LiteralPath $openClawJobsPath -PathType Leaf) {
    try {
        $openClawRaw = Get-Content -LiteralPath $openClawJobsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $openClawJobs = if ($null -ne (Get-OptionalProperty -InputObject $openClawRaw -Name "jobs")) {
            @($openClawRaw.jobs)
        } else {
            @($openClawRaw)
        }
        foreach ($job in $openClawJobs) {
            $jobText = $job | ConvertTo-Json -Depth 20 -Compress
            if ($jobText -match "(?i)ndx_dynamic_shadow_runner\.py.*--readiness|ndx.*dynamic.*shadow.*readiness") {
                $openClawDefinitions += [ordered]@{
                    id = [string](Get-OptionalProperty -InputObject $job -Name "id" -Default "")
                    name = [string](Get-OptionalProperty -InputObject $job -Name "name" -Default "")
                    enabled = ((Get-OptionalProperty -InputObject $job -Name "enabled" -Default $false) -eq $true)
                }
            }
        }
    } catch {
        $openClawDefinitions += [ordered]@{ id = ""; name = "PARSE_ERROR"; enabled = $true }
    }
}
$activeWindowsDuplicates = @($windowsDuplicates | Where-Object { $_.enabled })
$activeOpenClawDuplicates = @($openClawDefinitions | Where-Object { $_.enabled })

try {
    $runAt = [datetime]::ParseExact($DailyTime, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
} catch {
    throw "DailyTime must use 24-hour HH:mm format: $DailyTime"
}
$conservativeSealWindowStart = [TimeSpan]::ParseExact(
    "06:00",
    "hh\:mm",
    [Globalization.CultureInfo]::InvariantCulture
)
$conservativeSealWindowEndExclusive = [TimeSpan]::ParseExact(
    "21:30",
    "hh\:mm",
    [Globalization.CultureInfo]::InvariantCulture
)
$scheduledTimeOfDay = $runAt.TimeOfDay
$scheduledInsideConservativeSealWindow = (
    $scheduledTimeOfDay -ge $conservativeSealWindowStart -and
    $scheduledTimeOfDay -lt $conservativeSealWindowEndExclusive
)
$plannedSelectionTaskExecutionLimitMinutes = 660
$readinessGatePassed = $readinessGatePassed -and $scheduledInsideConservativeSealWindow
$readinessMonitorGatePassed = (
    $runnerPresent -and
    $pythonPresent -and
    $beijingTimeZone -and
    $canonicalPathsSelected -and
    $activationVerifierPresent -and
    $null -eq $readinessParseError -and
    $manifestType -eq "ndx_dynamic_shadow_activation_readiness" -and
    $historicalReplayDisabled -and
    $retrospectiveBackfillDisabled -and
    $frozenForwardSourceDisabled -and
    $callerBooleansCannotActivate -and
    $inputHashChecks.passed -and
    $runnerHashBound -and
    $activationVerifierHashBound -and
    $scheduledInsideConservativeSealWindow
)
$actionArguments = '-B "{0}" --readiness' -f $resolvedRunner
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

$plan = [ordered]@{
    schema_version = 1
    mode = if ($Apply) { "APPLY_REQUESTED" } else { "PLAN_ONLY" }
    task_name = $TaskName
    principal = $currentUser
    research_track = "portfolio_optimization_dynamic_shadow"
    action_mode = "READINESS_ONLY_NO_DECISION_GENERATION"
    executable = $PythonExecutable
    arguments = $actionArguments
    working_directory = $resolvedRoot
    trigger = [ordered]@{
        kind = "WEEKLY"
        timezone = "Asia/Shanghai"
        days = @("Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
        time = $runAt.ToString("HH:mm")
        rationale = "after US close and after the 10:05 challenger daily window"
    }
    start_when_available = $true
    start_when_available_role = "resume_readiness_check_only; it never seals a selection"
    readiness_monitor_registration_gate = [ordered]@{
        passed = $readinessMonitorGatePassed
        user_authorization_still_required = $true
        activation_ready_required = $false
        action_is_readiness_only = $true
        canonical_runner_present = $runnerPresent
        canonical_activation_verifier_present = $activationVerifierPresent
        canonical_paths_selected = $canonicalPathsSelected
        blocked_activation_status_is_allowed = ($readinessStatus -eq "BLOCKED")
        all_manifest_input_hashes_current = $inputHashChecks.passed
        canonical_runner_hash_bound = $runnerHashBound
        canonical_activation_verifier_hash_bound = $activationVerifierHashBound
        beijing_timezone = $beijingTimeZone
        scheduled_time_inside_conservative_window = $scheduledInsideConservativeSealWindow
    }
    two_phase_execution_contract = [ordered]@{
        selection_seal_phase_enabled_in_this_task = $false
        selection_seal_coordinate_rule = "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION"
        execution_date_known_at_selection_seal = $false
        execution_realization_phase_enabled_in_this_task = $false
        execution_realization_evidence = "append-only observed common-session calendar"
        realized_execution_requires_seal_before_realized_open = $true
        late_or_missed_selection_seal_action = "NO_DECISION_NO_BACKFILL"
        retrospective_execution_realization_without_prior_seal_allowed = $false
    }
    prospective_selection_scheduler_contract = [ordered]@{
        registration_allowed_by_this_installer = $false
        activation_readiness_gate_passed = $readinessGatePassed
        planned_task_name = "us_ratchet_ndx_dynamic_shadow_selection_daily"
        planned_executable = $PythonExecutable
        planned_arguments = ('-B "{0}" --execute' -f $selectionWrapper)
        planned_working_directory = $resolvedRoot
        selection_wrapper_present = $selectionWrapperPresent
        selection_contract_present = $selectionContractPresent
        selection_wrapper_hash_bound_by_activation_manifest = $selectionWrapperHashBound
        selection_contract_hash_bound_by_activation_manifest = $selectionContractHashBound
        reviewed_selection_wrapper_present = (
            $selectionWrapperPresent -and $selectionContractPresent -and
            $selectionWrapperHashBound -and $selectionContractHashBound
        )
        planned_trigger_days = @("Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
        planned_trigger_time = $runAt.ToString("HH:mm")
        planned_multiple_instances = "IGNORE_NEW"
        planned_failure_retry_count = 3
        planned_execution_time_limit_mode = "WINDOW_COVERING_11_HOURS_WRAPPER_SELF_LIMITS"
        planned_execution_time_limit_minutes = $plannedSelectionTaskExecutionLimitMinutes
        wrapper_enforces_remaining_pre_open_seconds = $true
        task_scheduler_start_when_available_is_sufficient_for_selection_seal = $false
        system_clock_window_required = $true
        timezone = "Asia/Shanghai"
        conservative_window_start = $conservativeSealWindowStart.ToString("hh\:mm")
        conservative_window_end_exclusive = $conservativeSealWindowEndExclusive.ToString("hh\:mm")
        scheduled_time_inside_conservative_window = $scheduledInsideConservativeSealWindow
        wake_after_window_action = "NO_DECISION_NO_BACKFILL"
        rationale = "06:00 is after normal US close in both New York offsets; 21:30 is the earliest normal next Open in Beijing time"
    }
    restart_count = 3
    restart_interval_minutes = 10
    multiple_instances = "IGNORE_NEW"
    execution_time_limit_minutes = 20
    api_service_dependency = $false
    retrospective_backfill_allowed = $false
    historical_candidate_replay_allowed = $false
    live_state_or_order_write = $false
    readiness_gate = [ordered]@{
        passed = $readinessGatePassed
        manifest_path = $resolvedReadiness
        manifest_type = $manifestType
        status = $readinessStatus
        automation_registration_allowed = $automationRegistrationAllowed
        runner_present = $runnerPresent
        python_present = $pythonPresent
        system_timezone_id = $systemTimeZoneId
        beijing_timezone = $beijingTimeZone
        scheduled_time_inside_conservative_window = $scheduledInsideConservativeSealWindow
        canonical_paths_selected = $canonicalPathsSelected
        parse_error = $readinessParseError
        guards = $guardChecks
        caller_supplied_booleans_can_activate = (-not $callerBooleansCannotActivate)
        input_hashes = $inputHashChecks
        scheduled_runner_hash_bound = $runnerHashBound
        activation_verifier_present = $activationVerifierPresent
        activation_verifier_hash_bound = $activationVerifierHashBound
    }
    duplicate_scheduler_gate = [ordered]@{
        passed = ($activeWindowsDuplicates.Count -eq 0 -and $activeOpenClawDuplicates.Count -eq 0)
        windows_definitions = $windowsDuplicates
        openclaw_definitions = $openClawDefinitions
        active_windows_count = $activeWindowsDuplicates.Count
        active_openclaw_count = $activeOpenClawDuplicates.Count
    }
}

$plan | ConvertTo-Json -Depth 12
if (-not $Apply) {
    Write-Output "RESULT=plan_only"
    exit 0
}
if (-not $AcknowledgeReadinessOnlyNoDecisionGeneration) {
    throw "Refusing registration without -AcknowledgeReadinessOnlyNoDecisionGeneration."
}
if (-not $AcknowledgeExternalSchedulerDisabled) {
    throw "Refusing registration without -AcknowledgeExternalSchedulerDisabled."
}
if (-not $readinessMonitorGatePassed) {
    throw "Readiness-only monitor prerequisites are not satisfied; registration refused."
}
if ($activeWindowsDuplicates.Count -gt 0 -or $activeOpenClawDuplicates.Count -gt 0) {
    throw "An enabled duplicate Windows/OpenClaw dynamic shadow scheduler exists; registration refused."
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw "Scheduled task already exists; refusing to replace without a separate reviewed migration: $TaskName"
}
$action = New-ScheduledTaskAction `
    -Execute $PythonExecutable `
    -Argument $actionArguments `
    -WorkingDirectory $resolvedRoot
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Tuesday, Wednesday, Thursday, Friday, Saturday `
    -At $runAt
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Readiness-only dynamic portfolio shadow audit; no decisions, backfill, live state, or orders." | Out-Null

Write-Output "RESULT=registered"
Write-Output "TASK_NAME=$TaskName"
