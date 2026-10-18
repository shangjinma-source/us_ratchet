[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$TaskName = "us_ratchet_ndx_dynamic_shadow_selection_daily",
    [string]$PythonExecutable = "D:\python\python.exe",
    [string]$DailyTime = "11:20",
    [string]$DailyScript = "scripts\ndx_dynamic_shadow_daily.py",
    [string]$ActivationManifest = "data\cache\research\ndx_dynamic_shadow_activation_v2\manifest.json",
    [string]$RegistrationEvidence = "data\cache\research\ndx_dynamic_shadow_activation_v2\selection_task_registration.json",
    [switch]$Apply,
    [switch]$CaptureExistingRegistrationEvidence,
    [switch]$VerifyRegistrationEvidence,
    [switch]$AcknowledgeResearchOnlyNoLiveMutation,
    [switch]$AcknowledgeExternalSchedulerDisabled
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

function Test-PathInsideRepository {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $rootPrefix = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    return [System.IO.Path]::GetFullPath($Path).StartsWith(
        $rootPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )
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

function Get-StringSha256Hex {
    param([Parameter(Mandatory = $true)][string]$Value)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Value)
        $digest = $algorithm.ComputeHash($bytes)
    } finally {
        $algorithm.Dispose()
    }
    return ([System.BitConverter]::ToString($digest)).Replace("-", "").ToLowerInvariant()
}

function New-RegistrationEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$ExpectedExecutable,
        [Parameter(Mandatory = $true)][string]$ExpectedArguments,
        [Parameter(Mandatory = $true)][string]$ExpectedWorkingDirectory,
        [Parameter(Mandatory = $true)][string]$ExpectedTime,
        [Parameter(Mandatory = $true)][string]$ActivationPath,
        [Parameter(Mandatory = $true)][string]$ActivationFileSha256,
        [Parameter(Mandatory = $true)][string]$ActivationDeclaredSha256,
        [Parameter(Mandatory = $true)][string]$RegistrationSource
    )
    $task = Get-ScheduledTask -TaskName $Name -ErrorAction Stop
    $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction Stop
    $actions = @($task.Actions)
    $triggers = @($task.Triggers)
    if ($actions.Count -ne 1 -or $triggers.Count -ne 1) {
        throw "Registered selection task must have exactly one action and one trigger."
    }
    $actualAction = $actions[0]
    $actualTrigger = $triggers[0]
    $triggerStart = [datetimeoffset]::Parse([string]$actualTrigger.StartBoundary)
    $expectedClock = [datetime]::ParseExact(
        $ExpectedTime,
        "HH:mm",
        [Globalization.CultureInfo]::InvariantCulture
    ).TimeOfDay
    $exact = (
        [string]$task.State -ne "Disabled" -and
        [string]$actualAction.Execute -eq $ExpectedExecutable -and
        [string]$actualAction.Arguments -eq $ExpectedArguments -and
        [System.IO.Path]::GetFullPath([string]$actualAction.WorkingDirectory) -eq
            [System.IO.Path]::GetFullPath($ExpectedWorkingDirectory) -and
        $triggerStart.TimeOfDay -eq $expectedClock -and
        [int]$actualTrigger.DaysOfWeek -eq 124 -and
        [int]$actualTrigger.WeeksInterval -eq 1 -and
        $task.Settings.StartWhenAvailable -eq $true -and
        $task.Settings.DisallowStartIfOnBatteries -eq $false -and
        $task.Settings.StopIfGoingOnBatteries -eq $false -and
        $task.Settings.MultipleInstances.ToString() -eq "IgnoreNew" -and
        [int]$task.Settings.RestartCount -eq 3 -and
        [string]$task.Settings.RestartInterval -eq "PT10M" -and
        [string]$task.Settings.ExecutionTimeLimit -eq "PT11H"
    )
    if (-not $exact) {
        throw "Registered selection task differs from the reviewed plan; evidence capture refused."
    }
    $xml = Export-ScheduledTask -TaskName $Name
    $taskFile = Join-Path $env:WINDIR ("System32\Tasks\" + $Name)
    $registeredAt = if (Test-Path -LiteralPath $taskFile -PathType Leaf) {
        (Get-Item -LiteralPath $taskFile).CreationTimeUtc.ToString("o")
    } else {
        $null
    }
    $taskSnapshot = [ordered]@{
        state = [string]$task.State
        enabled = ([string]$task.State -ne "Disabled")
        action = [ordered]@{
            execute = [string]$actualAction.Execute
            arguments = [string]$actualAction.Arguments
            working_directory = [string]$actualAction.WorkingDirectory
        }
        trigger = [ordered]@{
            start_boundary = [string]$actualTrigger.StartBoundary
            days_of_week_bitmask = [int]$actualTrigger.DaysOfWeek
            weeks_interval = [int]$actualTrigger.WeeksInterval
            timezone = "Asia/Shanghai"
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
            logon_type = [string]$task.Principal.LogonType
            run_level = [string]$task.Principal.RunLevel
        }
        last_run_time = $info.LastRunTime.ToUniversalTime().ToString("o")
        last_task_result = [int]$info.LastTaskResult
        next_run_time = $info.NextRunTime.ToUniversalTime().ToString("o")
        task_xml = $xml
        task_xml_sha256 = Get-StringSha256Hex -Value $xml
    }
    $snapshotJson = $taskSnapshot | ConvertTo-Json -Depth 14 -Compress
    $record = [ordered]@{
        schema_version = 1
        manifest_type = "ndx_dynamic_shadow_selection_task_registration"
        task_name = $Name
        registration_source = $RegistrationSource
        registered_at_utc = $registeredAt
        captured_at_utc = [datetime]::UtcNow.ToString("o")
        activation_manifest = [ordered]@{
            path = $ActivationPath
            file_sha256 = $ActivationFileSha256
            declared_manifest_sha256 = $ActivationDeclaredSha256
        }
        task_snapshot = $taskSnapshot
        task_snapshot_sha256 = Get-StringSha256Hex -Value $snapshotJson
        registration_result = "REGISTERED_CONFIGURATION_RECONSTRUCTED_AND_VERIFIED"
        immutable = $true
        overwrite_allowed = $false
    }
    $unsigned = $record | ConvertTo-Json -Depth 16 -Compress
    $record["registration_record_sha256"] = Get-StringSha256Hex -Value $unsigned
    return $record
}

function Write-ImmutableJson {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )
    if (Test-Path -LiteralPath $Path) {
        throw "Registration evidence already exists; refusing to overwrite immutable evidence."
    }
    $parent = Split-Path -Parent $Path
    [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    $temporary = $Path + ".tmp." + [guid]::NewGuid().ToString("N")
    try {
        $content = ($Value | ConvertTo-Json -Depth 16) + "`n"
        [System.IO.File]::WriteAllText($temporary, $content, [System.Text.UTF8Encoding]::new($false))
        [System.IO.File]::Move($temporary, $Path)
    } finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function Test-RegistrationEvidenceAgainstTask {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedPath
    )
    if ([System.IO.Path]::GetFullPath($Path) -ne [System.IO.Path]::GetFullPath($ExpectedPath)) {
        throw "Registration evidence path is not canonical."
    }
    try {
        $record = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "Registration evidence is missing or invalid JSON."
    }
    $declaredRecordHash = [string]$record.registration_record_sha256
    $record.PSObject.Properties.Remove("registration_record_sha256")
    $unsignedRecord = $record | ConvertTo-Json -Depth 16 -Compress
    if ((Get-StringSha256Hex -Value $unsignedRecord) -ne $declaredRecordHash) {
        throw "Registration evidence record hash mismatch."
    }
    if (
        $record.manifest_type -ne "ndx_dynamic_shadow_selection_task_registration" -or
        $record.immutable -ne $true -or
        $record.overwrite_allowed -ne $false
    ) {
        throw "Registration evidence boundary changed."
    }
    $snapshot = $record.task_snapshot
    $snapshotJson = $snapshot | ConvertTo-Json -Depth 14 -Compress
    if ((Get-StringSha256Hex -Value $snapshotJson) -ne [string]$record.task_snapshot_sha256) {
        throw "Registration task snapshot hash mismatch."
    }
    if ((Get-StringSha256Hex -Value ([string]$snapshot.task_xml)) -ne [string]$snapshot.task_xml_sha256) {
        throw "Registration task XML hash mismatch."
    }
    $task = Get-ScheduledTask -TaskName ([string]$record.task_name) -ErrorAction Stop
    $actions = @($task.Actions)
    $triggers = @($task.Triggers)
    if ($actions.Count -ne 1 -or $triggers.Count -ne 1) {
        throw "Current selection task action/trigger cardinality changed."
    }
    $currentXml = Export-ScheduledTask -TaskName ([string]$record.task_name)
    if (
        $currentXml -ne [string]$snapshot.task_xml -or
        [string]$actions[0].Execute -ne [string]$snapshot.action.execute -or
        [string]$actions[0].Arguments -ne [string]$snapshot.action.arguments -or
        [System.IO.Path]::GetFullPath([string]$actions[0].WorkingDirectory) -ne
            [System.IO.Path]::GetFullPath([string]$snapshot.action.working_directory) -or
        [string]$triggers[0].StartBoundary -ne [string]$snapshot.trigger.start_boundary -or
        [int]$triggers[0].DaysOfWeek -ne [int]$snapshot.trigger.days_of_week_bitmask -or
        [int]$triggers[0].WeeksInterval -ne [int]$snapshot.trigger.weeks_interval -or
        [bool]$task.Settings.StartWhenAvailable -ne [bool]$snapshot.settings.start_when_available -or
        $task.Settings.MultipleInstances.ToString().ToUpperInvariant() -ne [string]$snapshot.settings.multiple_instances -or
        [int]$task.Settings.RestartCount -ne [int]$snapshot.settings.restart_count -or
        [string]$task.Settings.RestartInterval -ne [string]$snapshot.settings.restart_interval -or
        [string]$task.Settings.ExecutionTimeLimit -ne [string]$snapshot.settings.execution_time_limit
    ) {
        throw "Current selection task differs from immutable registration evidence."
    }
    $activationPath = [System.IO.Path]::GetFullPath([string]$record.activation_manifest.path)
    if (
        -not (Test-Path -LiteralPath $activationPath -PathType Leaf) -or
        (Get-Sha256Hex -Path $activationPath) -ne [string]$record.activation_manifest.file_sha256
    ) {
        throw "Registration-time activation manifest bytes changed."
    }
    $activationPayload = Get-Content -LiteralPath $activationPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (
        [string]$activationPayload.manifest_sha256 -ne
        [string]$record.activation_manifest.declared_manifest_sha256
    ) {
        throw "Registration-time activation manifest identity changed."
    }
    return [ordered]@{
        schema_version = 1
        manifest_type = "ndx_dynamic_shadow_selection_task_registration_verification"
        status = "VERIFIED_CURRENT_TASK_MATCHES_IMMUTABLE_REGISTRATION_EVIDENCE"
        evidence_path = $Path
        registration_record_sha256 = $declaredRecordHash
        task_xml_sha256 = [string]$snapshot.task_xml_sha256
        activation_manifest_file_sha256 = [string]$record.activation_manifest.file_sha256
        verified_at_utc = [datetime]::UtcNow.ToString("o")
        live_mutation_performed = $false
    }
}

function ConvertTo-ArtifactEntries {
    param([AllowNull()]$Artifacts)
    $entries = @()
    if ($null -eq $Artifacts) {
        return $entries
    }
    if ($Artifacts -is [System.Array]) {
        foreach ($item in $Artifacts) {
            $entries += $item
        }
        return $entries
    }
    foreach ($property in $Artifacts.PSObject.Properties) {
        $value = $property.Value
        if ($null -ne $value -and $null -ne $value.PSObject.Properties["path"]) {
            $entries += $value
        }
    }
    return $entries
}

function Test-ActivationArtifacts {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [AllowNull()]$Artifacts,
        [Parameter(Mandatory = $true)][string[]]$RequiredPaths
    )
    $checks = @()
    $seen = @{}
    foreach ($item in @(ConvertTo-ArtifactEntries -Artifacts $Artifacts)) {
        $declaredPath = [string](Get-OptionalProperty -InputObject $item -Name "path" -Default "")
        $declaredHash = ([string](Get-OptionalProperty -InputObject $item -Name "sha256" -Default "")).ToLowerInvariant()
        if (-not $declaredPath -or $declaredHash -notmatch "^[0-9a-f]{64}$") {
            $checks += [ordered]@{ path = $declaredPath; passed = $false; reason = "PATH_OR_SHA256_INVALID" }
            continue
        }
        $resolved = Resolve-RepositoryPath -Root $Root -Path $declaredPath
        if (-not (Test-PathInsideRepository -Root $Root -Path $resolved)) {
            $checks += [ordered]@{ path = $resolved; passed = $false; reason = "PATH_OUTSIDE_REPOSITORY" }
            continue
        }
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            $checks += [ordered]@{ path = $resolved; passed = $false; reason = "FILE_MISSING" }
            continue
        }
        $actualHash = Get-Sha256Hex -Path $resolved
        $match = $actualHash -eq $declaredHash
        $checks += [ordered]@{
            path = $resolved
            passed = $match
            reason = if ($match) { "MATCH" } else { "SHA256_MISMATCH" }
        }
        if ($match) {
            $seen[$resolved.ToLowerInvariant()] = $true
        }
    }
    $required = @()
    foreach ($relative in $RequiredPaths) {
        $canonical = Resolve-RepositoryPath -Root $Root -Path $relative
        $present = $seen.ContainsKey($canonical.ToLowerInvariant())
        $required += [ordered]@{ path = $canonical; hash_bound = $present }
    }
    $failedChecks = @($checks | Where-Object { -not $_.passed })
    $missingRequired = @($required | Where-Object { -not $_.hash_bound })
    return [ordered]@{
        passed = ($checks.Count -gt 0 -and $failedChecks.Count -eq 0 -and $missingRequired.Count -eq 0)
        checked = $checks.Count
        checks = $checks
        required = $required
        missing_required_count = $missingRequired.Count
    }
}

$resolvedRoot = if ($ProjectRoot) {
    (Resolve-Path -LiteralPath $ProjectRoot).Path
} else {
    (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}
$resolvedDaily = Resolve-RepositoryPath -Root $resolvedRoot -Path $DailyScript
$resolvedActivation = Resolve-RepositoryPath -Root $resolvedRoot -Path $ActivationManifest
$resolvedRegistrationEvidence = Resolve-RepositoryPath -Root $resolvedRoot -Path $RegistrationEvidence
$canonicalDaily = Resolve-RepositoryPath -Root $resolvedRoot -Path "scripts\ndx_dynamic_shadow_daily.py"
$canonicalActivation = Resolve-RepositoryPath -Root $resolvedRoot -Path "data\cache\research\ndx_dynamic_shadow_activation_v2\manifest.json"
$canonicalRegistrationEvidence = Resolve-RepositoryPath -Root $resolvedRoot -Path "data\cache\research\ndx_dynamic_shadow_activation_v2\selection_task_registration.json"
$activationVerifier = Resolve-RepositoryPath -Root $resolvedRoot -Path "scripts\ndx_dynamic_shadow_activation_v2.py"
$canonicalPathsSelected = (
    $resolvedDaily -eq $canonicalDaily -and
    $resolvedActivation -eq $canonicalActivation -and
    $resolvedRegistrationEvidence -eq $canonicalRegistrationEvidence
)
$dailyPresent = Test-Path -LiteralPath $resolvedDaily -PathType Leaf
$pythonPresent = Test-Path -LiteralPath $PythonExecutable -PathType Leaf
$activationVerifierPresent = Test-Path -LiteralPath $activationVerifier -PathType Leaf
$activationVerifierSupportsManifestVerification = $false
if ($activationVerifierPresent) {
    $activationVerifierSource = Get-Content -LiteralPath $activationVerifier -Raw -Encoding UTF8
    $activationVerifierSupportsManifestVerification = $activationVerifierSource.Contains("--verify-activation-manifest")
}
$systemTimeZoneId = (Get-TimeZone).Id
$beijingTimeZone = $systemTimeZoneId -eq "China Standard Time"

try {
    $runAt = [datetime]::ParseExact($DailyTime, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
} catch {
    throw "DailyTime must use 24-hour HH:mm format: $DailyTime"
}
$sealWindowStart = [TimeSpan]::ParseExact("06:00", "hh\:mm", [Globalization.CultureInfo]::InvariantCulture)
$sealWindowEndExclusive = [TimeSpan]::ParseExact("21:30", "hh\:mm", [Globalization.CultureInfo]::InvariantCulture)
$scheduledInsideSealWindow = (
    $runAt.TimeOfDay -ge $sealWindowStart -and
    $runAt.TimeOfDay -lt $sealWindowEndExclusive
)

$activation = $null
$activationParseError = $null
$activationManifestSha256 = $null
if (Test-Path -LiteralPath $resolvedActivation -PathType Leaf) {
    try {
        $activation = Get-Content -LiteralPath $resolvedActivation -Raw -Encoding UTF8 | ConvertFrom-Json
        $activationManifestSha256 = Get-Sha256Hex -Path $resolvedActivation
    } catch {
        $activationParseError = $_.Exception.Message
    }
}
$manifestType = [string](Get-OptionalProperty -InputObject $activation -Name "manifest_type" -Default "MISSING")
$activationStatus = [string](Get-OptionalProperty -InputObject $activation -Name "status" -Default "MISSING")
$registrationAllowed = (
    (Get-OptionalProperty -InputObject $activation -Name "research_automation_registration_allowed" -Default $false) -eq $true
)
$researchOnly = (
    (Get-OptionalProperty -InputObject $activation -Name "decision_and_path_generation_research_only" -Default $false) -eq $true
)
$promotionDisabled = (
    (Get-OptionalProperty -InputObject $activation -Name "promotion_allowed" -Default $true) -eq $false
)
$liveMutationDisabled = (
    (Get-OptionalProperty -InputObject $activation -Name "live_mutation_allowed" -Default $true) -eq $false
)
$automationNotAlreadyRegistered = (
    (Get-OptionalProperty -InputObject $activation -Name "task_registration_performed" -Default $true) -eq $false
)
$manifestSealed = (
    [string](Get-OptionalProperty -InputObject $activation -Name "manifest_sha256" -Default "") -match "^[0-9a-f]{64}$"
)
$researchTrackVerified = (
    [string](Get-OptionalProperty -InputObject $activation -Name "research_track" -Default "") -eq "portfolio_optimization"
)
$migrationControlExcluded = (
    (Get-OptionalProperty -InputObject $activation -Name "migration_control_included" -Default $true) -eq $false
)
$formalForwardGateNotSubstituted = (
    (Get-OptionalProperty -InputObject $activation -Name "formal_forward_gate_substitution_allowed" -Default $true) -eq $false
)
$activationGuards = Get-OptionalProperty -InputObject $activation -Name "guards"
$requiredActivationGuards = @(
    "canonical_sources_hash_bound",
    "componentwise_gate_preserved",
    "no_backfill_preserved",
    "prospective_prefix_not_due_or_rebuilt",
    "synthetic_dynamic_k_rebuilt",
    "synthetic_original_8_control_rebuilt",
    "synthetic_target_no_future_trace_rebuilt",
    "synthetic_ten_lanes_rebuilt",
    "synthetic_three_way_calendar_rebuilt",
    "versioned_contracts_rebuilt"
)
$guardChecks = [ordered]@{}
foreach ($name in $requiredActivationGuards) {
    $guardChecks[$name] = (
        (Get-OptionalProperty -InputObject $activationGuards -Name $name -Default $false) -eq $true
    )
}
$allActivationGuardsPassed = -not ($guardChecks.Values -contains $false)

$requiredHashBoundArtifacts = @(
    "config\ndx_portfolio_objective_v2.yaml",
    "config\ndx_dynamic_shadow_selector_registry_v2.yaml",
    "config\ndx_dynamic_shadow_runner_v2.yaml",
    "config\ndx_dynamic_shadow_daily_v1.yaml",
    "backtest\ndx_dynamic_shadow_activation_v2.py",
    "backtest\ndx_dynamic_shadow_daily.py",
    "scripts\ndx_dynamic_shadow_activation_v2.py",
    "scripts\ndx_dynamic_shadow_daily.py",
    "data\cache\research\ndx_original_8_control_v1\manifest.json",
    "data\cache\research\ndx_dynamic_shadow_activation_v2\observed_calendar_activation_prefix.jsonl"
)
$activationArtifacts = @(
    ConvertTo-ArtifactEntries -Artifacts (
        Get-OptionalProperty -InputObject $activation -Name "canonical_source_bindings"
    )
)
foreach ($topLevelArtifact in @("original_8_definition", "synthetic_e2e")) {
    $item = Get-OptionalProperty -InputObject $activation -Name $topLevelArtifact
    if ($null -ne $item) {
        $activationArtifacts += $item
    }
}
$syntheticE2E = Get-OptionalProperty -InputObject $activation -Name "synthetic_e2e"
$syntheticE2EPath = [string](Get-OptionalProperty -InputObject $syntheticE2E -Name "path" -Default "")
$syntheticE2ECanonicalPattern = $false
if ($syntheticE2EPath) {
    $resolvedSyntheticE2E = [System.IO.Path]::GetFullPath($syntheticE2EPath)
    $normalizedRootPrefix = [System.IO.Path]::GetFullPath($resolvedRoot).TrimEnd('\', '/').Replace("\", "/") + "/"
    $normalizedSyntheticE2E = $resolvedSyntheticE2E.Replace("\", "/")
    $relativeSyntheticE2E = if (
        $normalizedSyntheticE2E.StartsWith(
            $normalizedRootPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        $normalizedSyntheticE2E.Substring($normalizedRootPrefix.Length)
    } else {
        ""
    }
    $syntheticE2ECanonicalPattern = (
        (Test-PathInsideRepository -Root $resolvedRoot -Path $resolvedSyntheticE2E) -and
        $relativeSyntheticE2E -match "^data/cache/research/ndx_dynamic_shadow_activation_v2_synthetic_e2e_v[0-9]+/manifest\.json$"
    )
}
$observedCalendar = Get-OptionalProperty -InputObject $activation -Name "observed_calendar"
$calendarPrefix = Get-OptionalProperty -InputObject $observedCalendar -Name "prefix_snapshot"
if ($null -ne $calendarPrefix) {
    $activationArtifacts += $calendarPrefix
}
$canonicalCalendarManifest = Resolve-RepositoryPath `
    -Root $resolvedRoot `
    -Path "data\cache\research\ndx_observed_us_session_calendar_v1\manifest.json"
$canonicalCalendarLedger = Resolve-RepositoryPath `
    -Root $resolvedRoot `
    -Path "data\cache\research\ndx_observed_us_session_calendar_v1\sessions.jsonl"
$calendarAppendOnlyExtensionContract = (
    [string](Get-OptionalProperty -InputObject $observedCalendar -Name "extension_policy" -Default "") -eq
        "CURRENT_LEDGER_MUST_REBUILD_AND_PRESERVE_EXACT_ACTIVATION_PREFIX" -and
    [System.IO.Path]::GetFullPath(
        [string](Get-OptionalProperty -InputObject $observedCalendar -Name "canonical_manifest_path" -Default "")
    ) -eq $canonicalCalendarManifest -and
    [System.IO.Path]::GetFullPath(
        [string](Get-OptionalProperty -InputObject $observedCalendar -Name "canonical_ledger_path" -Default "")
    ) -eq $canonicalCalendarLedger
)
$artifactChecks = Test-ActivationArtifacts `
    -Root $resolvedRoot `
    -Artifacts $activationArtifacts `
    -RequiredPaths $requiredHashBoundArtifacts

$windowsDefinitions = @()
if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {
    foreach ($task in Get-ScheduledTask) {
        foreach ($taskAction in @($task.Actions)) {
            $execute = [string](Get-OptionalProperty -InputObject $taskAction -Name "Execute" -Default "")
            $arguments = [string](Get-OptionalProperty -InputObject $taskAction -Name "Arguments" -Default "")
            $actionText = "$execute $arguments"
            if (
                $task.TaskName -ne $TaskName -and
                (
                    $actionText -match "(?i)ndx_dynamic_shadow_daily\.py.*--execute" -or
                    $task.TaskName -match "(?i)ndx.*dynamic.*shadow.*selection"
                )
            ) {
                $windowsDefinitions += [ordered]@{
                    task_name = $task.TaskName
                    state = [string]$task.State
                    enabled = ([string]$task.State -ne "Disabled")
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
            if ($jobText -match "(?i)ndx_dynamic_shadow_daily\.py.*--execute|ndx.*dynamic.*shadow.*selection") {
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
$activeWindowsDuplicates = @($windowsDefinitions | Where-Object { $_.enabled })
$activeOpenClawDuplicates = @($openClawDefinitions | Where-Object { $_.enabled })
$targetTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$targetTaskExists = $null -ne $targetTask
$currentDisallowStartIfOnBatteries = if ($targetTaskExists) {
    [bool]$targetTask.Settings.DisallowStartIfOnBatteries
} else {
    $null
}
$currentStopIfGoingOnBatteries = if ($targetTaskExists) {
    [bool]$targetTask.Settings.StopIfGoingOnBatteries
} else {
    $null
}
$duplicateGatePassed = (
    $activeWindowsDuplicates.Count -eq 0 -and
    $activeOpenClawDuplicates.Count -eq 0
)

$activationGatePassed = (
    $pythonPresent -and
    $dailyPresent -and
    $activationVerifierPresent -and
    $activationVerifierSupportsManifestVerification -and
    $beijingTimeZone -and
    $scheduledInsideSealWindow -and
    $canonicalPathsSelected -and
    $null -eq $activationParseError -and
    $manifestType -eq "ndx_dynamic_shadow_activation_v2" -and
    $activationStatus -eq "READY_FOR_RESEARCH_AUTOMATION_REGISTRATION" -and
    $registrationAllowed -and
    $researchOnly -and
    $promotionDisabled -and
    $liveMutationDisabled -and
    $automationNotAlreadyRegistered -and
    $manifestSealed -and
    $researchTrackVerified -and
    $migrationControlExcluded -and
    $formalForwardGateNotSubstituted -and
    $allActivationGuardsPassed -and
    $calendarAppendOnlyExtensionContract -and
    $syntheticE2ECanonicalPattern -and
    $artifactChecks.passed
)

$actionArguments = '-B "{0}" --execute' -f $resolvedDaily
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$executionLimitMinutes = 660
$plan = [ordered]@{
    schema_version = 1
    mode = if ($Apply) {
        "APPLY_REQUESTED"
    } elseif ($CaptureExistingRegistrationEvidence) {
        "CAPTURE_EXISTING_REGISTRATION_EVIDENCE_REQUESTED"
    } else {
        "PLAN_ONLY"
    }
    task_name = $TaskName
    principal = $currentUser
    research_track = "portfolio_optimization_dynamic_shadow"
    action_mode = "RESEARCH_SELECTION_AND_PATH_ONLY"
    executable = $PythonExecutable
    arguments = $actionArguments
    working_directory = $resolvedRoot
    trigger = [ordered]@{
        kind = "WEEKLY"
        timezone = "Asia/Shanghai"
        days = @("Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
        time = $runAt.ToString("HH:mm")
    }
    start_when_available = $true
    start_when_available_boundary = "wrapper must still be before 21:30 Asia/Shanghai; otherwise NO_DECISION_NO_BACKFILL"
    multiple_instances = "IGNORE_NEW"
    restart_count = 3
    restart_interval_minutes = 10
    execution_time_limit_minutes = $executionLimitMinutes
    wrapper_self_limits_to_remaining_pre_open_window = $true
    conservative_window = [ordered]@{
        start = $sealWindowStart.ToString("hh\:mm")
        end_exclusive = $sealWindowEndExclusive.ToString("hh\:mm")
        scheduled_time_inside = $scheduledInsideSealWindow
        missed_or_late_action = "NO_DECISION_NO_BACKFILL"
        retrospective_backfill_allowed = $false
    }
    api_service_dependency = $false
    live_state_or_order_write = $false
    readiness_monitor_is_separate_task = $true
    readiness_monitor_execution_limit_minutes = 20
    battery_reliability = [ordered]@{
        risk = if (
            $targetTaskExists -and
            ($currentDisallowStartIfOnBatteries -or $currentStopIfGoingOnBatteries)
        ) { "P1_MAY_SKIP_OR_STOP_WHILE_COMPUTER_IS_ON_BATTERY" } else { "NONE" }
        current_disallow_start_if_on_batteries = $currentDisallowStartIfOnBatteries
        current_stop_if_going_on_batteries = $currentStopIfGoingOnBatteries
        desired_disallow_start_if_on_batteries = $false
        desired_stop_if_going_on_batteries = $false
        migration_required = (
            $targetTaskExists -and
            ($currentDisallowStartIfOnBatteries -or $currentStopIfGoingOnBatteries)
        )
        migration_mode = "EXISTING_TASK_SETTINGS_ONLY_PRESERVE_ACTION_TRIGGER_PRINCIPAL_AND_LIMITS"
        proposed_cmdlet = "Set-ScheduledTask"
        user_authorization_required = $true
        migration_performed_by_this_plan = $false
    }
    activation_v2_gate = [ordered]@{
        passed = $activationGatePassed
        manifest_path = $resolvedActivation
        manifest_sha256 = $activationManifestSha256
        manifest_type = $manifestType
        status = $activationStatus
        research_automation_registration_allowed = $registrationAllowed
        decision_and_path_generation_research_only = $researchOnly
        promotion_allowed = (-not $promotionDisabled)
        live_mutation_allowed = (-not $liveMutationDisabled)
        automation_already_registered = (-not $automationNotAlreadyRegistered)
        manifest_sealed = $manifestSealed
        research_track_verified = $researchTrackVerified
        migration_control_excluded = $migrationControlExcluded
        formal_forward_gate_not_substituted = $formalForwardGateNotSubstituted
        guards = $guardChecks
        calendar_append_only_extension_contract = $calendarAppendOnlyExtensionContract
        dynamic_calendar_manifest_exact_hash_not_required_after_registration = $true
        synthetic_e2e_canonical_versioned_path = $syntheticE2ECanonicalPattern
        parse_error = $activationParseError
        canonical_paths_selected = $canonicalPathsSelected
        activation_verifier_present = $activationVerifierPresent
        activation_verifier_supports_manifest_verification = $activationVerifierSupportsManifestVerification
        canonical_artifact_hashes = $artifactChecks
    }
    duplicate_scheduler_gate = [ordered]@{
        passed = $duplicateGatePassed
        windows_definitions = $windowsDefinitions
        openclaw_definitions = $openClawDefinitions
        active_windows_count = $activeWindowsDuplicates.Count
        active_openclaw_count = $activeOpenClawDuplicates.Count
    }
    registration_gate = [ordered]@{
        passed = ($activationGatePassed -and $duplicateGatePassed -and -not $targetTaskExists)
        explicit_user_authorization_required = $true
        installer_replaces_existing_task = $false
        target_task_already_exists = $targetTaskExists
    }
    registration_evidence = [ordered]@{
        path = $resolvedRegistrationEvidence
        canonical_path_selected = ($resolvedRegistrationEvidence -eq $canonicalRegistrationEvidence)
        exists = (Test-Path -LiteralPath $resolvedRegistrationEvidence -PathType Leaf)
        immutable_create_new_only = $true
        capture_existing_without_task_replacement_supported = $true
    }
}

$selectedModes = @(@(
    [bool]$Apply,
    [bool]$CaptureExistingRegistrationEvidence,
    [bool]$VerifyRegistrationEvidence
) | Where-Object { $_ })
if ($selectedModes.Count -gt 1) {
    throw "Choose only one of -Apply, -CaptureExistingRegistrationEvidence, or -VerifyRegistrationEvidence."
}
if ($VerifyRegistrationEvidence) {
    $verification = Test-RegistrationEvidenceAgainstTask `
        -Path $resolvedRegistrationEvidence `
        -ExpectedPath $canonicalRegistrationEvidence
    $activationVerificationOutput = & $PythonExecutable -B $activationVerifier --verify-activation-manifest 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Current activation-v2 verification failed: $activationVerificationOutput"
    }
    $verification | ConvertTo-Json -Depth 8
    Write-Output "RESULT=registration_evidence_verified"
    exit 0
}
$plan | ConvertTo-Json -Depth 14
if (-not $Apply -and -not $CaptureExistingRegistrationEvidence) {
    Write-Output "RESULT=plan_only"
    exit 0
}
if (-not $AcknowledgeResearchOnlyNoLiveMutation) {
    throw "Refusing registration without -AcknowledgeResearchOnlyNoLiveMutation."
}
if (-not $AcknowledgeExternalSchedulerDisabled) {
    throw "Refusing registration without -AcknowledgeExternalSchedulerDisabled."
}
if (-not $activationGatePassed) {
    throw "Verified activation-v2 prerequisites are not satisfied; registration refused."
}
if (-not $duplicateGatePassed) {
    throw "An enabled duplicate Windows/OpenClaw selection scheduler exists; registration refused."
}
if ($CaptureExistingRegistrationEvidence) {
    if (-not $targetTaskExists) {
        throw "Selection task does not exist; evidence capture refused."
    }
    if (Test-Path -LiteralPath $resolvedRegistrationEvidence) {
        throw "Registration evidence already exists; refusing to overwrite immutable evidence."
    }
    & $PythonExecutable -B $activationVerifier --verify-activation-manifest
    if ($LASTEXITCODE -ne 0) {
        throw "Activation-v2 independent manifest verification failed; evidence capture refused."
    }
    $evidence = New-RegistrationEvidence `
        -Name $TaskName `
        -ExpectedExecutable $PythonExecutable `
        -ExpectedArguments $actionArguments `
        -ExpectedWorkingDirectory $resolvedRoot `
        -ExpectedTime $DailyTime `
        -ActivationPath $resolvedActivation `
        -ActivationFileSha256 (Get-Sha256Hex -Path $resolvedActivation) `
        -ActivationDeclaredSha256 ([string](Get-OptionalProperty -InputObject $activation -Name "manifest_sha256" -Default "")) `
        -RegistrationSource "EXISTING_TASK_POST_REGISTRATION_CAPTURE"
    Write-ImmutableJson -Path $resolvedRegistrationEvidence -Value $evidence
    Write-Output "RESULT=registration_evidence_captured"
    exit 0
}
if ($targetTaskExists) {
    throw "Scheduled task already exists; refusing to replace it."
}
if (Test-Path -LiteralPath $resolvedRegistrationEvidence) {
    throw "Registration evidence already exists; refusing task registration without an immutable evidence target."
}

& $PythonExecutable -B $activationVerifier --verify-activation-manifest
if ($LASTEXITCODE -ne 0) {
    throw "Activation-v2 independent manifest verification failed; registration refused."
}
$postVerificationManifestSha256 = Get-Sha256Hex -Path $resolvedActivation
$postVerificationArtifactChecks = Test-ActivationArtifacts `
    -Root $resolvedRoot `
    -Artifacts $activationArtifacts `
    -RequiredPaths $requiredHashBoundArtifacts
if (
    $postVerificationManifestSha256 -ne $activationManifestSha256 -or
    -not $postVerificationArtifactChecks.passed
) {
    throw "Activation-v2 manifest or hash-bound inputs changed during verification; registration refused."
}
$action = New-ScheduledTaskAction `
    -Execute $PythonExecutable `
    -Argument $actionArguments `
    -WorkingDirectory $resolvedRoot
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Tuesday, Wednesday, Thursday, Friday, Saturday `
    -At $runAt
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes $executionLimitMinutes)
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal | Out-Null
$evidence = New-RegistrationEvidence `
    -Name $TaskName `
    -ExpectedExecutable $PythonExecutable `
    -ExpectedArguments $actionArguments `
    -ExpectedWorkingDirectory $resolvedRoot `
    -ExpectedTime $DailyTime `
    -ActivationPath $resolvedActivation `
    -ActivationFileSha256 (Get-Sha256Hex -Path $resolvedActivation) `
    -ActivationDeclaredSha256 ([string](Get-OptionalProperty -InputObject $activation -Name "manifest_sha256" -Default "")) `
    -RegistrationSource "INSTALLER_APPLY_SUCCESS"
Write-ImmutableJson -Path $resolvedRegistrationEvidence -Value $evidence
Write-Output "RESULT=registered"
