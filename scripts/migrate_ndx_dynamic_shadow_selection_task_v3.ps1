[CmdletBinding()]
param(
    [string]$ProjectRoot = "E:\Git\us_ratchet",
    [string]$PythonExecutable = "D:\python\python.exe",
    [switch]$Apply,
    [switch]$VerifyPostEvidence,
    [switch]$AcknowledgeExplicitUserApproval,
    [switch]$AcknowledgeResearchOnlyNoLiveMutation,
    [string]$EvidenceAttemptRoot = "",
    [string]$ExpectedMigrationAuthoritySha256 = "",
    [switch]$InternalFunctionTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$root = [System.IO.Path]::GetFullPath($ProjectRoot)
$taskPath = "\"
$oldTaskName = "us_ratchet_ndx_dynamic_shadow_selection_daily"
$failedV2TaskName = "us_ratchet_ndx_dynamic_shadow_selection_daily_v2_budgeted"
$newTaskName = "us_ratchet_ndx_dynamic_shadow_selection_daily_v3_reviewed_calendar"
$readinessScript = Join-Path $root "scripts\ndx_dynamic_shadow_runtime_v3_migration.py"
$activationScript = Join-Path $root "scripts\ndx_dynamic_shadow_activation_v4.py"
$activationManifest = Join-Path $root "data\cache\research\ndx_dynamic_shadow_activation_v4\manifest.json"
$dailyV3 = Join-Path $root "scripts\ndx_dynamic_shadow_daily_v3.py"
$smokeEvidenceScript = Join-Path $root "scripts\ndx_dynamic_shadow_runtime_v3_smoke.py"
$oldV2NotaryScript = Join-Path $root "scripts\ndx_dynamic_shadow_task_migration_notary.py"
$evidenceBase = Join-Path $root "data\cache\research\ndx_dynamic_shadow_task_migration_v3"
$authorityManifest = Join-Path $evidenceBase "reviewed_source_manifest.json"
$evidenceRoot = if ($EvidenceAttemptRoot) {
    [System.IO.Path]::GetFullPath($EvidenceAttemptRoot)
} elseif ($Apply) {
    Join-Path $evidenceBase ("attempts\{0}_{1}" -f [datetime]::UtcNow.ToString("yyyyMMddTHHmmssfffffffZ"), [guid]::NewGuid().ToString("N"))
} else {
    $evidenceBase
}
$evidenceBasePrefix = [System.IO.Path]::GetFullPath($evidenceBase).TrimEnd('\') + '\'
if (
    [System.IO.Path]::GetFullPath($evidenceRoot) -ne [System.IO.Path]::GetFullPath($evidenceBase) -and
    -not [System.IO.Path]::GetFullPath($evidenceRoot).StartsWith($evidenceBasePrefix, [StringComparison]::OrdinalIgnoreCase)
) {
    throw "EvidenceAttemptRoot must remain inside the runtime-v3 migration evidence base."
}
$oldV2EvidenceRoot = Join-Path $root "data\cache\research\ndx_dynamic_shadow_task_migration_v2"
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

function Get-DirectoryFileHashes {
    param([Parameter(Mandatory = $true)][string]$Directory)
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
        throw "Immutable predecessor evidence directory is missing: $Directory"
    }
    $directoryPath = [System.IO.Path]::GetFullPath($Directory).TrimEnd('\')
    $result = [ordered]@{}
    foreach ($file in @(Get-ChildItem -LiteralPath $directoryPath -File -Recurse | Sort-Object FullName)) {
        $relative = $file.FullName.Substring($directoryPath.Length).TrimStart('\').Replace('\', '/')
        $result[$relative] = Get-Sha256Hex -Path $file.FullName
    }
    if ($result.Count -eq 0) {
        throw "Immutable predecessor evidence directory is empty: $Directory"
    }
    return $result
}

function Assert-DirectoryFileHashes {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)]$Expected
    )
    $current = Get-DirectoryFileHashes -Directory $Directory
    $expectedDictionary = [ordered]@{}
    if ($Expected -is [System.Collections.IDictionary]) {
        foreach ($key in $Expected.Keys) { $expectedDictionary[[string]$key] = [string]$Expected[$key] }
    } else {
        foreach ($property in $Expected.PSObject.Properties) {
            $expectedDictionary[$property.Name] = [string]$property.Value
        }
    }
    if (($current.Keys -join "`n") -ne ($expectedDictionary.Keys -join "`n")) {
        throw "Immutable predecessor evidence file inventory changed."
    }
    foreach ($key in $current.Keys) {
        if ([string]$current[$key] -ne [string]$expectedDictionary[$key]) {
            throw "Immutable predecessor evidence hash changed: $key"
        }
    }
}

function Assert-SourceDescriptor {
    param([Parameter(Mandatory = $true)]$Descriptor)
    $path = [string]$Descriptor.path
    if (
        -not (Test-Path -LiteralPath $path -PathType Leaf) -or
        (Get-Sha256Hex -Path $path) -ne [string]$Descriptor.sha256
    ) {
        throw "Migration-bound source changed: $path"
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
    # Hash the exact embedded payload string.  Verification reparses both this
    # string and the outer JSON with the reader's PowerShell version, avoiding
    # DateTime/escaping drift between Windows PowerShell and PowerShell 7.
    $unsigned = $Payload | ConvertTo-Json -Depth 30 -Compress
    $Payload["record_hash_algorithm"] = "SHA256_UTF8_EXACT_RECORD_PAYLOAD_JSON_V1"
    $Payload["record_payload_json"] = $unsigned
    $Payload["record_sha256"] = Get-StringSha256Hex -Value $unsigned
    $temporary = $Path + ".tmp." + [guid]::NewGuid().ToString("N")
    try {
        [System.IO.File]::WriteAllText(
            $temporary,
            (($Payload | ConvertTo-Json -Depth 30) + "`n"),
            [System.Text.UTF8Encoding]::new($false)
        )
        [System.IO.File]::Move($temporary, $Path)
    } finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function Test-RecordHash {
    param([Parameter(Mandatory = $true)]$Record)
    $payloadProperty = $Record.PSObject.Properties["record_payload_json"]
    $hashProperty = $Record.PSObject.Properties["record_sha256"]
    $algorithmProperty = $Record.PSObject.Properties["record_hash_algorithm"]
    if (
        $null -eq $payloadProperty -or
        $null -eq $hashProperty -or
        $null -eq $algorithmProperty -or
        [string]$algorithmProperty.Value -ne "SHA256_UTF8_EXACT_RECORD_PAYLOAD_JSON_V1"
    ) {
        return $false
    }
    $storedPayload = [string]$payloadProperty.Value
    $declared = [string]$Record.record_sha256
    if ((Get-StringSha256Hex -Value $storedPayload) -ne $declared) {
        return $false
    }
    try {
        $expected = $storedPayload | ConvertFrom-Json
    } catch {
        return $false
    }
    $current = [ordered]@{}
    foreach ($property in $Record.PSObject.Properties) {
        if ($property.Name -notin @("record_hash_algorithm", "record_payload_json", "record_sha256")) {
            $current[$property.Name] = $property.Value
        }
    }
    return (
        ($expected | ConvertTo-Json -Depth 30 -Compress) -eq
        ($current | ConvertTo-Json -Depth 30 -Compress)
    )
}

function Get-TaskSnapshot {
    param([Parameter(Mandatory = $true)][string]$TaskName)
    $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $TaskName -ErrorAction Stop
    $actions = @($task.Actions)
    $triggers = @($task.Triggers)
    if ($actions.Count -ne 1 -or $triggers.Count -ne 1) {
        throw "Task $TaskName must have exactly one action and one trigger."
    }
    $info = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $TaskName -ErrorAction Stop
    $xml = Export-ScheduledTask -TaskPath $taskPath -TaskName $TaskName
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
        runtime = [ordered]@{
            last_run_time = [datetime]$info.LastRunTime
            next_run_time = [datetime]$info.NextRunTime
            last_task_result = [int]$info.LastTaskResult
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
        throw "Runtime-v3 migration readiness did not return valid JSON (exit=$exitCode)."
    }
    return [ordered]@{ exit_code = $exitCode; document = $document }
}

function Assert-ActivationVerifier {
    param([string]$ExpectedManifestSha256 = "")
    $output = & $PythonExecutable -B $activationScript --verify 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Activation-v4 full verification failed: $($output | Out-String)"
    }
    if (-not (Test-Path -LiteralPath $activationManifest -PathType Leaf)) {
        throw "Activation-v4 manifest disappeared after verification."
    }
    $currentHash = Get-Sha256Hex -Path $activationManifest
    if ($ExpectedManifestSha256 -and $currentHash -ne $ExpectedManifestSha256) {
        throw "Activation-v4 manifest changed after the migration plan was frozen."
    }
    return $currentHash
}

function Assert-MigrationAuthority {
    param([Parameter(Mandatory = $true)][string]$ExpectedFileSha256)
    if (-not $ExpectedFileSha256) {
        throw "Apply/verification requires an independently reviewed migration authority file SHA256."
    }
    if (-not (Test-Path -LiteralPath $authorityManifest -PathType Leaf)) {
        throw "Reviewed migration authority manifest is missing."
    }
    $actual = Get-Sha256Hex -Path $authorityManifest
    if ($actual -ne $ExpectedFileSha256.ToLowerInvariant()) {
        throw "Reviewed migration authority file SHA256 differs from the explicit expected value."
    }
    $output = & $PythonExecutable -B $readinessScript --verify-authority $authorityManifest 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Reviewed migration authority verification failed: $($output | Out-String)"
    }
    return $actual
}

function Invoke-SmokeEvidenceSnapshot {
    $output = & $PythonExecutable -B $smokeEvidenceScript --snapshot 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Could not capture the canonical daily-run pre-smoke snapshot: $($output | Out-String)"
    }
    try {
        return (($output | Out-String).Trim() | ConvertFrom-Json)
    } catch {
        throw "Pre-smoke artifact snapshot did not return valid JSON."
    }
}

function Invoke-OldV2NotaryVerifier {
    $output = & $PythonExecutable -B $oldV2NotaryScript --verify 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed-v2 rollback notary verification failed: $($output | Out-String)"
    }
    try {
        return (($output | Out-String).Trim() | ConvertFrom-Json)
    } catch {
        throw "Failed-v2 rollback notary did not return valid JSON."
    }
}

function Invoke-SmokeArtifactVerification {
    param(
        [string]$BeforePath = "",
        [string]$ExpectedPath = ""
    )
    if ([bool]$BeforePath -eq [bool]$ExpectedPath) {
        throw "Exactly one smoke verification evidence path is required."
    }
    $arguments = @("-B", $smokeEvidenceScript, "--verify")
    if ($BeforePath) { $arguments += @("--before-path", $BeforePath) }
    if ($ExpectedPath) { $arguments += @("--expected-path", $ExpectedPath) }
    $output = & $PythonExecutable @arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Canonical daily-run smoke artifact verification failed: $($output | Out-String)"
    }
    try {
        return (($output | Out-String).Trim() | ConvertFrom-Json)
    } catch {
        throw "Smoke artifact verifier did not return valid JSON."
    }
}

function Get-MatchingDailyProcesses {
    return @(
        Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
            (
                [string]$_.CommandLine -match "(?i)ndx_dynamic_shadow_daily(?:_v2|_v3)?\.py" -or
                [string]$_.CommandLine -match "(?i)ndx_dynamic_shadow_fresh_search(?:_v2|_v3)?\.py"
            ) -and
            [string]$_.CommandLine -match "(?i)--execute"
        } | Select-Object ProcessId, Name, CommandLine
    )
}

function Get-ActiveDuplicateSchedulers {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$AllowedEnabledTaskName)
    $duplicates = @()
    foreach ($task in @(Get-ScheduledTask -ErrorAction Stop)) {
        $taskNameLower = ([string]$task.TaskName).ToLowerInvariant()
        $actionText = ((@($task.Actions) | ForEach-Object {
            $executeProperty = $_.PSObject.Properties["Execute"]
            $argumentsProperty = $_.PSObject.Properties["Arguments"]
            $execute = if ($null -eq $executeProperty) { "" } else { [string]$executeProperty.Value }
            $arguments = if ($null -eq $argumentsProperty) { "" } else { [string]$argumentsProperty.Value }
            "{0} {1}" -f $execute, $arguments
        }) -join " ").ToLowerInvariant()
        $related = (
            $taskNameLower.Contains("dynamic_shadow_selection") -or
            $actionText.Contains("ndx_dynamic_shadow_daily") -or
            $actionText.Contains("ndx_dynamic_shadow_fresh_search")
        )
        $isAllowed = (
            [string]$task.TaskPath -eq $taskPath -and
            [string]$task.TaskName -eq $AllowedEnabledTaskName
        )
        if ($related -and [string]$task.State -ne "Disabled" -and -not $isAllowed) {
            $duplicates += [ordered]@{
                kind = "WINDOWS_SCHEDULED_TASK"
                task_path = [string]$task.TaskPath
                task_name = [string]$task.TaskName
                state = [string]$task.State
            }
        }
    }
    $jobsPath = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".openclaw\cron\jobs.json"
    if (Test-Path -LiteralPath $jobsPath -PathType Leaf) {
        try {
            $raw = Get-Content -LiteralPath $jobsPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $jobsProperty = $raw.PSObject.Properties["jobs"]
            $jobs = if ($null -ne $jobsProperty) { @($jobsProperty.Value) } else { @($raw) }
            foreach ($job in $jobs) {
                $serialized = ($job | ConvertTo-Json -Depth 30 -Compress).ToLowerInvariant()
                $enabledProperty = $job.PSObject.Properties["enabled"]
                $nameProperty = $job.PSObject.Properties["name"]
                if (
                    $null -ne $enabledProperty -and $enabledProperty.Value -eq $true -and
                    (
                        $serialized.Contains("ndx_dynamic_shadow_daily") -or
                        $serialized.Contains("dynamic_shadow_selection") -or
                        $serialized.Contains("ndx_dynamic_shadow_fresh_search")
                    )
                ) {
                    $jobName = if ($null -eq $nameProperty) { "" } else { [string]$nameProperty.Value }
                    $duplicates += [ordered]@{
                        kind = "OPENCLAW"
                        name = $jobName
                        enabled = $true
                    }
                }
            }
        } catch {
            $duplicates += [ordered]@{ kind = "OPENCLAW_PARSE_ERROR_FAIL_CLOSED"; name = ""; enabled = $true }
        }
    }
    return @($duplicates)
}

function Assert-ExclusiveSchedulerAndNoRuntimeProcess {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$AllowedEnabledTaskName)
    $duplicates = @(Get-ActiveDuplicateSchedulers -AllowedEnabledTaskName $AllowedEnabledTaskName)
    $processes = @(Get-MatchingDailyProcesses)
    if ($duplicates.Count -ne 0) {
        throw "Another enabled dynamic-shadow scheduler exists."
    }
    if ($processes.Count -ne 0) {
        throw "A dynamic-shadow daily or fresh-search executor process is running."
    }
}

function Assert-FailedV2Unchanged {
    param([Parameter(Mandatory = $true)]$Expected)
    $current = Get-TaskSnapshot -TaskName $failedV2TaskName
    if (
        $current.enabled -or
        $current.state -eq "Running" -or
        $current.task_xml_sha256 -ne $Expected.task_xml_sha256
    ) {
        throw "Failed v2 task must remain stopped, disabled, and byte-identical."
    }
    return $current
}

function Set-XmlNodeText {
    param(
        [Parameter(Mandatory = $true)][xml]$Document,
        [Parameter(Mandatory = $true)]$Parent,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)]$Namespace
    )
    $node = $Parent.SelectSingleNode("t:$Name", $Namespace)
    if ($null -eq $node) {
        $node = $Document.CreateElement($Name, $Document.DocumentElement.NamespaceURI)
        $Parent.AppendChild($node) | Out-Null
    }
    $node.InnerText = $Value
    return $node
}

function New-DisabledV3TaskXml {
    param([Parameter(Mandatory = $true)][string]$OldXml)
    [xml]$document = $OldXml
    $namespace = New-Object System.Xml.XmlNamespaceManager($document.NameTable)
    $namespace.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")

    $action = $document.SelectSingleNode("/t:Task/t:Actions/t:Exec", $namespace)
    $calendarTrigger = $document.SelectSingleNode("/t:Task/t:Triggers/t:CalendarTrigger", $namespace)
    $schedule = $calendarTrigger.SelectSingleNode("t:ScheduleByWeek", $namespace)
    $settings = $document.SelectSingleNode("/t:Task/t:Settings", $namespace)
    if ($null -eq $action -or $null -eq $calendarTrigger -or $null -eq $schedule -or $null -eq $settings) {
        throw "Old task XML is not the expected single weekly execution task."
    }
    $triggerChildren = @(
        $calendarTrigger.ChildNodes |
            Where-Object { $_.NodeType -eq [System.Xml.XmlNodeType]::Element } |
            ForEach-Object { $_.LocalName }
    )
    $unsupportedTriggerChildren = @(
        $triggerChildren | Where-Object { $_ -notin @("StartBoundary", "Enabled", "ScheduleByWeek") }
    )
    $scheduleChildren = @(
        $schedule.ChildNodes |
            Where-Object { $_.NodeType -eq [System.Xml.XmlNodeType]::Element } |
            ForEach-Object { $_.LocalName }
    )
    if (
        $unsupportedTriggerChildren.Count -ne 0 -or
        @($triggerChildren | Where-Object { $_ -eq "StartBoundary" }).Count -ne 1 -or
        @($triggerChildren | Where-Object { $_ -eq "ScheduleByWeek" }).Count -ne 1 -or
        @($triggerChildren | Where-Object { $_ -eq "Enabled" }).Count -gt 1 -or
        @($scheduleChildren | Where-Object { $_ -notin @("DaysOfWeek", "WeeksInterval") }).Count -ne 0 -or
        @($scheduleChildren | Where-Object { $_ -eq "DaysOfWeek" }).Count -ne 1 -or
        @($scheduleChildren | Where-Object { $_ -eq "WeeksInterval" }).Count -ne 1
    ) {
        throw "Old task trigger contains unsupported repetition, boundary, delay, or schedule semantics."
    }

    (Set-XmlNodeText -Document $document -Parent $action -Name "Command" -Value $PythonExecutable -Namespace $namespace) | Out-Null
    (Set-XmlNodeText -Document $document -Parent $action -Name "Arguments" -Value ('-B "{0}" --execute' -f $dailyV3) -Namespace $namespace) | Out-Null
    (Set-XmlNodeText -Document $document -Parent $action -Name "WorkingDirectory" -Value $root -Namespace $namespace) | Out-Null

    $startBoundary = $calendarTrigger.SelectSingleNode("t:StartBoundary", $namespace)
    if ($null -eq $startBoundary) {
        throw "Old task XML has no StartBoundary."
    }
    $startDate = [datetime]::Parse($startBoundary.InnerText, [Globalization.CultureInfo]::InvariantCulture)
    $startBoundary.InnerText = $startDate.ToString("yyyy-MM-dd") + "T11:20:00"
    (Set-XmlNodeText -Document $document -Parent $calendarTrigger -Name "Enabled" -Value "true" -Namespace $namespace) | Out-Null
    (Set-XmlNodeText -Document $document -Parent $schedule -Name "WeeksInterval" -Value "1" -Namespace $namespace) | Out-Null
    $days = $schedule.SelectSingleNode("t:DaysOfWeek", $namespace)
    if ($null -eq $days) {
        $days = $document.CreateElement("DaysOfWeek", $document.DocumentElement.NamespaceURI)
        $schedule.AppendChild($days) | Out-Null
    }
    while ($days.HasChildNodes) { $days.RemoveChild($days.FirstChild) | Out-Null }
    foreach ($day in @("Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")) {
        $days.AppendChild($document.CreateElement($day, $document.DocumentElement.NamespaceURI)) | Out-Null
    }

    foreach ($pair in @(
        @("StartWhenAvailable", "true"),
        @("DisallowStartIfOnBatteries", "false"),
        @("StopIfGoingOnBatteries", "false"),
        @("MultipleInstancesPolicy", "IgnoreNew"),
        @("ExecutionTimeLimit", "PT11H"),
        @("Enabled", "false")
    )) {
        (Set-XmlNodeText -Document $document -Parent $settings -Name $pair[0] -Value $pair[1] -Namespace $namespace) | Out-Null
    }
    $restart = $settings.SelectSingleNode("t:RestartOnFailure", $namespace)
    if ($null -eq $restart) {
        $restart = $document.CreateElement("RestartOnFailure", $document.DocumentElement.NamespaceURI)
        $settings.AppendChild($restart) | Out-Null
    }
    (Set-XmlNodeText -Document $document -Parent $restart -Name "Interval" -Value "PT10M" -Namespace $namespace) | Out-Null
    (Set-XmlNodeText -Document $document -Parent $restart -Name "Count" -Value "3" -Namespace $namespace) | Out-Null
    return $document.OuterXml
}

function Assert-NewTaskContract {
    param(
        [Parameter(Mandatory = $true)]$Old,
        [Parameter(Mandatory = $true)]$New,
        [Parameter(Mandatory = $true)][bool]$ExpectedEnabled
    )
    $expectedArguments = '-B "{0}" --execute' -f $dailyV3
    $startTime = ([datetime]::Parse(
        [string]$New.trigger.start_boundary,
        [Globalization.CultureInfo]::InvariantCulture
    )).ToString("HH:mm")
    [xml]$taskDocument = $New.task_xml
    $taskNamespace = New-Object System.Xml.XmlNamespaceManager($taskDocument.NameTable)
    $taskNamespace.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")
    $calendarTrigger = $taskDocument.SelectSingleNode("/t:Task/t:Triggers/t:CalendarTrigger", $taskNamespace)
    $schedule = if ($null -eq $calendarTrigger) { $null } else {
        $calendarTrigger.SelectSingleNode("t:ScheduleByWeek", $taskNamespace)
    }
    $triggerChildNames = if ($null -eq $calendarTrigger) { @() } else {
        @($calendarTrigger.ChildNodes | Where-Object {
            $_.NodeType -eq [System.Xml.XmlNodeType]::Element
        } | ForEach-Object { $_.LocalName })
    }
    $scheduleChildNames = if ($null -eq $schedule) { @() } else {
        @($schedule.ChildNodes | Where-Object {
            $_.NodeType -eq [System.Xml.XmlNodeType]::Element
        } | ForEach-Object { $_.LocalName })
    }
    $dayNames = if ($null -eq $schedule) { @() } else {
        $daysNode = $schedule.SelectSingleNode("t:DaysOfWeek", $taskNamespace)
        if ($null -eq $daysNode) { @() } else {
            @($daysNode.ChildNodes | Where-Object {
                $_.NodeType -eq [System.Xml.XmlNodeType]::Element
            } | ForEach-Object { $_.LocalName })
        }
    }
    $exactTriggerXml = (
        ((($triggerChildNames | Sort-Object) -join ",") -eq "Enabled,ScheduleByWeek,StartBoundary") -and
        ((($scheduleChildNames | Sort-Object) -join ",") -eq "DaysOfWeek,WeeksInterval") -and
        ($dayNames -join ",") -eq "Tuesday,Wednesday,Thursday,Friday,Saturday" -and
        $calendarTrigger.SelectSingleNode("t:Enabled", $taskNamespace).InnerText -eq "true"
    )
    if (
        $New.enabled -ne $ExpectedEnabled -or
        [System.IO.Path]::GetFullPath($New.action.execute) -ne [System.IO.Path]::GetFullPath($PythonExecutable) -or
        $New.action.arguments -ne $expectedArguments -or
        [System.IO.Path]::GetFullPath($New.action.working_directory) -ne $root -or
        $startTime -ne "11:20" -or
        $New.trigger.days_of_week_bitmask -ne 124 -or
        $New.trigger.weeks_interval -ne 1 -or
        $New.principal.user_id -ne $Old.principal.user_id -or
        $New.principal.logon_type -ne $Old.principal.logon_type -or
        $New.principal.run_level -ne $Old.principal.run_level -or
        $New.settings.start_when_available -ne $true -or
        $New.settings.multiple_instances -ne "IGNORENEW" -or
        $New.settings.restart_count -ne 3 -or
        $New.settings.restart_interval -ne "PT10M" -or
        $New.settings.execution_time_limit -ne "PT11H" -or
        $New.settings.disallow_start_if_on_batteries -ne $false -or
        $New.settings.stop_if_going_on_batteries -ne $false -or
        (-not $exactTriggerXml)
    ) {
        throw "New v3 Scheduled Task differs from the approved exact contract."
    }
}

function Assert-ThreeTaskCutoverState {
    param(
        [Parameter(Mandatory = $true)]$OldBaseline,
        [Parameter(Mandatory = $true)]$FailedV2Baseline,
        [Parameter(Mandatory = $true)][bool]$ExpectedOldEnabled,
        [Parameter(Mandatory = $true)][bool]$ExpectedNewEnabled
    )
    $old = Get-TaskSnapshot -TaskName $oldTaskName
    $failedV2 = Assert-FailedV2Unchanged -Expected $FailedV2Baseline
    $new = Get-TaskSnapshot -TaskName $newTaskName
    if (
        $old.enabled -ne $ExpectedOldEnabled -or
        $old.state -eq "Running" -or
        $new.state -eq "Running"
    ) {
        throw "Three-task cutover state differs from the expected exclusive enablement."
    }
    Assert-NewTaskContract -Old $OldBaseline -New $new -ExpectedEnabled $ExpectedNewEnabled
    $allowed = if ($ExpectedNewEnabled) { $newTaskName } else { $oldTaskName }
    Assert-ExclusiveSchedulerAndNoRuntimeProcess -AllowedEnabledTaskName $allowed
    return [ordered]@{ old = $old; failed_v2 = $failedV2; new = $new }
}

function Assert-OldTaskSecuredBeforeNewEnable {
    param([Parameter(Mandatory = $true)]$FailedV2Baseline)
    $oldAfterDisable = Get-TaskSnapshot -TaskName $oldTaskName
    if ($oldAfterDisable.enabled -or $oldAfterDisable.state -eq "Running") {
        throw "Old v1 task is not proven disabled and stopped; v3 will not be enabled."
    }
    Assert-FailedV2Unchanged -Expected $FailedV2Baseline | Out-Null
    Assert-ExclusiveSchedulerAndNoRuntimeProcess -AllowedEnabledTaskName ""
    return $oldAfterDisable
}

function Invoke-RealScheduledTaskSmoke {
    param([Parameter(Mandatory = $true)]$Before)
    Start-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName -ErrorAction Stop
    $deadline = [datetime]::UtcNow.AddMinutes(10)
    do {
        Start-Sleep -Seconds 2
        $snapshot = Get-TaskSnapshot -TaskName $newTaskName
        $ranAfterStart = ([datetime]$snapshot.runtime.last_run_time) -gt ([datetime]$Before.runtime.last_run_time)
        if ($ranAfterStart -and $snapshot.state -ne "Running") { break }
    } while ([datetime]::UtcNow -lt $deadline)
    if (-not $ranAfterStart -or $snapshot.state -eq "Running") {
        throw "Real v3 Scheduled Task smoke did not finish within 10 minutes."
    }
    if ([int]$snapshot.runtime.last_task_result -ne 0) {
        throw "Real v3 Scheduled Task smoke failed with LastTaskResult=$($snapshot.runtime.last_task_result)."
    }
    return $snapshot
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
            Disable-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName -ErrorAction Stop | Out-Null
            $newState = (Get-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName -ErrorAction Stop).State.ToString()
            if ($newState -eq "Running") {
                Stop-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName -ErrorAction Stop
                for ($attempt = 0; $attempt -lt 40; $attempt++) {
                    Start-Sleep -Milliseconds 250
                    $newState = (Get-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName -ErrorAction Stop).State.ToString()
                    if ($newState -ne "Running") { break }
                }
            }
            $newSnapshot = Get-TaskSnapshot -TaskName $newTaskName
            $remainingProcesses = @(Get-MatchingDailyProcesses)
            $newSecured = (
                -not $newSnapshot.enabled -and
                $newSnapshot.state -ne "Running" -and
                $remainingProcesses.Count -eq 0
            )
            if ($remainingProcesses.Count -ne 0) {
                $failure = "$failure; matching runtime child processes remain; old task stays disabled for manual recovery"
            }
        } catch {
            $newSecured = $false
            $failure = "$failure; failed to secure new task during rollback: $($_.Exception.Message)"
        }
    }
    if ($OldDisabled -and $newSecured) {
        try {
            Enable-ScheduledTask -TaskPath $taskPath -TaskName $oldTaskName -ErrorAction Stop | Out-Null
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
    if (-not $EvidenceAttemptRoot) {
        throw "VerifyPostEvidence requires the immutable -EvidenceAttemptRoot produced by Apply."
    }
    Assert-MigrationAuthority -ExpectedFileSha256 $ExpectedMigrationAuthoritySha256 | Out-Null
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
    $activationHash = [string]$post.activation_manifest.sha256
    if (
        $activationHash -ne [string]$pre.activation_manifest.sha256 -or
        $activationHash -ne [string]$disabled.activation_manifest_sha256 -or
        $activationHash -ne (Get-Sha256Hex -Path $activationManifest)
    ) {
        throw "Activation-v4 manifest differs from the cutover-frozen hash."
    }
    Assert-ActivationVerifier -ExpectedManifestSha256 $activationHash | Out-Null
    Invoke-SmokeArtifactVerification -ExpectedPath $postEvidence | Out-Null
    foreach ($descriptor in @(
        $pre.migration_authority,
        $pre.old_v2_notary.script,
        $pre.activation_script,
        $pre.readiness_script,
        $pre.daily_v3_script,
        $pre.smoke_evidence_script,
        $pre.migration_script
    )) {
        Assert-SourceDescriptor -Descriptor $descriptor
    }
    $currentTasks = Assert-ThreeTaskCutoverState `
        -OldBaseline $pre.old_task `
        -FailedV2Baseline $pre.failed_v2_task `
        -ExpectedOldEnabled $false `
        -ExpectedNewEnabled $true
    $old = $currentTasks.old
    $failedV2 = $currentTasks.failed_v2
    $new = $currentTasks.new
    if ($old.enabled -or $failedV2.enabled -or $failedV2.state -eq "Running" -or -not $new.enabled) {
        throw "Current three-task enablement differs from post-cutover evidence."
    }
    if (
        $old.task_xml_sha256 -ne $post.old_task.task_xml_sha256 -or
        $failedV2.task_xml_sha256 -ne $post.failed_v2_task.task_xml_sha256 -or
        $new.task_xml_sha256 -ne $post.new_task.task_xml_sha256
    ) {
        throw "Current Scheduled Task XML differs from immutable post-cutover evidence."
    }
    Assert-ProtectedHashes -Expected $post.protected_hashes
    Assert-DirectoryFileHashes -Directory $oldV2EvidenceRoot -Expected $post.old_v2_evidence_hashes
    [ordered]@{ status = "V3_POST_CUTOVER_VERIFIED"; mutation_performed = $false } | ConvertTo-Json
    exit 0
}

$readiness = Invoke-Readiness
$plan = [ordered]@{
    schema_version = 1
    manifest_type = "ndx_dynamic_shadow_selection_task_v3_atomic_migration_plan"
    mode = if ($Apply) { "APPLY_REQUESTED" } else { "PLAN_ONLY" }
    status = if (
        $readiness.exit_code -eq 0 -and
        $readiness.document.status -eq "READY_FOR_EXPLICITLY_AUTHORIZED_V3_DISABLED_REGISTRATION_AND_CUTOVER"
    ) { "READY_FOR_EXPLICIT_APPROVAL" } else { "BLOCKED_BY_READINESS" }
    old_task = $oldTaskName
    failed_v2_task = $failedV2TaskName
    new_task = $newTaskName
    new_task_initial_state = "DISABLED"
    never_parallel_enable = $true
    task_deletion_allowed = $false
    rollback = "DISABLE_STOP_NEW_V3_THEN_ENABLE_OLD_V1_PRESERVE_ALL_TASKS_AND_EVIDENCE"
    approved_schedule = [ordered]@{
        timezone = "Asia/Shanghai"
        days_of_week_bitmask = 124
        local_time = "11:20"
        weeks_interval = 1
        start_when_available = $true
        disallow_start_if_on_batteries = $false
        stop_if_going_on_batteries = $false
        multiple_instances = "IGNORE_NEW"
        execution_time_limit = "PT11H"
        restart_count = 3
        restart_interval = "PT10M"
    }
    activation_manifest = [ordered]@{
        path = $activationManifest
        sha256 = if (Test-Path -LiteralPath $activationManifest) { Get-Sha256Hex -Path $activationManifest } else { $null }
    }
    migration_authority = [ordered]@{
        path = $authorityManifest
        file_sha256 = if (Test-Path -LiteralPath $authorityManifest) { Get-Sha256Hex -Path $authorityManifest } else { $null }
        independently_reviewed_expected_sha256_required_for_apply = $true
    }
    new_evidence_root = $evidenceRoot
    old_v2_evidence_root = $oldV2EvidenceRoot
    old_v2_evidence_overwrite_allowed = $false
    protected_live_files = $protectedPaths
    protected_live_mutation_allowed = $false
    readiness = $readiness.document
    mutation_performed = $false
}

if (-not $Apply) {
    $plan | ConvertTo-Json -Depth 30
    exit 0
}

if (-not $AcknowledgeExplicitUserApproval -or -not $AcknowledgeResearchOnlyNoLiveMutation) {
    throw "Apply requires both explicit approval acknowledgements."
}
$authorityFileHash = Assert-MigrationAuthority -ExpectedFileSha256 $ExpectedMigrationAuthoritySha256
if ($plan.status -ne "READY_FOR_EXPLICIT_APPROVAL") {
    throw "Migration readiness is not READY; current tasks remain unchanged."
}
if (Test-Path -LiteralPath $evidenceRoot) {
    throw "Runtime-v3 migration evidence root already exists; refusing overwrite or second cutover."
}
if (Get-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName -ErrorAction SilentlyContinue) {
    throw "New v3 task already exists; refusing replacement."
}

$protectedBefore = Get-ProtectedHashes
$oldV2EvidenceBefore = Get-DirectoryFileHashes -Directory $oldV2EvidenceRoot
$activationHash = Assert-ActivationVerifier
$oldBefore = Get-TaskSnapshot -TaskName $oldTaskName
$failedV2Before = Get-TaskSnapshot -TaskName $failedV2TaskName
if (-not $oldBefore.enabled -or $oldBefore.state -eq "Running") {
    throw "Old v1 task must be enabled and not running before cutover."
}
if ($failedV2Before.enabled -or $failedV2Before.state -eq "Running") {
    throw "Failed v2 task must remain disabled and not running."
}
Assert-ExclusiveSchedulerAndNoRuntimeProcess -AllowedEnabledTaskName $oldTaskName
$smokeBefore = Invoke-SmokeEvidenceSnapshot
$oldV2NotaryVerification = Invoke-OldV2NotaryVerifier

$pre = [ordered]@{
    schema_version = 1
    manifest_type = "ndx_dynamic_shadow_selection_task_v3_pre_cutover"
    captured_at_utc = [datetime]::UtcNow.ToString("o")
    authorization = [ordered]@{
        evidence = "USER_APPROVED_BUDGETED_MIGRATION_AND_BATTERY_WITH_VERSIONED_V3_REPAIR"
        authorization_recorded_date_asia_shanghai = "2026-09-06"
        scope = "RESEARCH_SCHEDULED_TASK_ONLY_NO_LIVE_CONFIG_STATE_BROKER_ADVICE_OR_ORDER_MUTATION"
    }
    activation_manifest = [ordered]@{ path = $activationManifest; sha256 = $activationHash }
    migration_authority = [ordered]@{ path = $authorityManifest; sha256 = $authorityFileHash }
    activation_script = [ordered]@{ path = $activationScript; sha256 = Get-Sha256Hex -Path $activationScript }
    readiness_script = [ordered]@{ path = $readinessScript; sha256 = Get-Sha256Hex -Path $readinessScript }
    daily_v3_script = [ordered]@{ path = $dailyV3; sha256 = Get-Sha256Hex -Path $dailyV3 }
    smoke_evidence_script = [ordered]@{ path = $smokeEvidenceScript; sha256 = Get-Sha256Hex -Path $smokeEvidenceScript }
    old_v2_notary = [ordered]@{
        script = [ordered]@{ path = $oldV2NotaryScript; sha256 = Get-Sha256Hex -Path $oldV2NotaryScript }
        verification = $oldV2NotaryVerification
    }
    migration_script = [ordered]@{ path = $PSCommandPath; sha256 = Get-Sha256Hex -Path $PSCommandPath }
    old_task = $oldBefore
    failed_v2_task = $failedV2Before
    old_v2_evidence_root = $oldV2EvidenceRoot
    old_v2_evidence_hashes = $oldV2EvidenceBefore
    old_v2_evidence_overwrite_allowed = $false
    matching_daily_process_count = @(Get-MatchingDailyProcesses).Count
    smoke_before = $smokeBefore
    protected_hashes = $protectedBefore
}
Write-ImmutableRecord -Path $preEvidence -Payload $pre

$newCreated = $false
$oldDisabled = $false
try {
    $newXml = New-DisabledV3TaskXml -OldXml $oldBefore.task_xml
    Register-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName -Xml $newXml -Force:$false | Out-Null
    $newCreated = $true
    $newDisabled = Get-TaskSnapshot -TaskName $newTaskName
    Assert-ThreeTaskCutoverState `
        -OldBaseline $oldBefore `
        -FailedV2Baseline $failedV2Before `
        -ExpectedOldEnabled $true `
        -ExpectedNewEnabled $false | Out-Null
    Assert-ActivationVerifier -ExpectedManifestSha256 $activationHash | Out-Null
    Assert-ProtectedHashes -Expected $protectedBefore
    Assert-DirectoryFileHashes -Directory $oldV2EvidenceRoot -Expected $oldV2EvidenceBefore
    foreach ($descriptor in @(
        $pre.migration_authority,
        $pre.old_v2_notary.script,
        $pre.activation_script,
        $pre.readiness_script,
        $pre.daily_v3_script,
        $pre.smoke_evidence_script,
        $pre.migration_script
    )) {
        Assert-SourceDescriptor -Descriptor $descriptor
    }

    $disabled = [ordered]@{
        schema_version = 1
        manifest_type = "ndx_dynamic_shadow_selection_task_v3_disabled_registration"
        captured_at_utc = [datetime]::UtcNow.ToString("o")
        activation_manifest_sha256 = $activationHash
        pre_cutover_record_sha256 = $pre.record_sha256
        old_task = Get-TaskSnapshot -TaskName $oldTaskName
        failed_v2_task = Get-TaskSnapshot -TaskName $failedV2TaskName
        new_task = $newDisabled
        old_v2_evidence_hashes = $oldV2EvidenceBefore
        protected_hashes = Get-ProtectedHashes
    }
    Write-ImmutableRecord -Path $disabledEvidence -Payload $disabled

    Assert-ThreeTaskCutoverState `
        -OldBaseline $oldBefore `
        -FailedV2Baseline $failedV2Before `
        -ExpectedOldEnabled $true `
        -ExpectedNewEnabled $false | Out-Null
    Disable-ScheduledTask -TaskPath $taskPath -TaskName $oldTaskName -ErrorAction Stop | Out-Null
    $oldDisabled = $true
    Assert-OldTaskSecuredBeforeNewEnable -FailedV2Baseline $failedV2Before | Out-Null
    Enable-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName -ErrorAction Stop | Out-Null
    $newEnabled = Get-TaskSnapshot -TaskName $newTaskName
    Assert-ThreeTaskCutoverState `
        -OldBaseline $oldBefore `
        -FailedV2Baseline $failedV2Before `
        -ExpectedOldEnabled $false `
        -ExpectedNewEnabled $true | Out-Null

    $smokeResult = Invoke-RealScheduledTaskSmoke -Before $newEnabled
    $artifactVerification = Invoke-SmokeArtifactVerification -BeforePath $preEvidence
    $threeTaskAfter = Assert-ThreeTaskCutoverState `
        -OldBaseline $oldBefore `
        -FailedV2Baseline $failedV2Before `
        -ExpectedOldEnabled $false `
        -ExpectedNewEnabled $true
    $oldAfter = $threeTaskAfter.old
    $failedV2After = $threeTaskAfter.failed_v2
    $smokeResult = $threeTaskAfter.new
    Assert-ActivationVerifier -ExpectedManifestSha256 $activationHash | Out-Null
    Assert-ProtectedHashes -Expected $protectedBefore
    Assert-DirectoryFileHashes -Directory $oldV2EvidenceRoot -Expected $oldV2EvidenceBefore
    foreach ($descriptor in @(
        $pre.migration_authority,
        $pre.old_v2_notary.script,
        $pre.activation_script,
        $pre.readiness_script,
        $pre.daily_v3_script,
        $pre.smoke_evidence_script,
        $pre.migration_script
    )) {
        Assert-SourceDescriptor -Descriptor $descriptor
    }

    $post = [ordered]@{
        schema_version = 1
        manifest_type = "ndx_dynamic_shadow_selection_task_v3_post_cutover"
        captured_at_utc = [datetime]::UtcNow.ToString("o")
        status = "V3_REAL_SMOKE_PASSED_NEW_ENABLED_OLD_AND_FAILED_V2_DISABLED"
        activation_manifest = [ordered]@{ path = $activationManifest; sha256 = $activationHash }
        pre_cutover_record_sha256 = $pre.record_sha256
        disabled_registration_record_sha256 = $disabled.record_sha256
        old_task = $oldAfter
        failed_v2_task = $failedV2After
        new_task = $smokeResult
        matching_daily_process_count_after_smoke = 0
        old_v2_evidence_hashes = $oldV2EvidenceBefore
        smoke = [ordered]@{
            execution_path = "WINDOWS_SCHEDULED_TASK_START"
            last_run_time = $smokeResult.runtime.last_run_time
            last_task_result = $smokeResult.runtime.last_task_result
            artifact_verification = $artifactVerification
            passed = $true
        }
        protected_hashes = Get-ProtectedHashes
    }
    Write-ImmutableRecord -Path $postEvidence -Payload $post
    [ordered]@{
        status = "ATOMIC_V3_MIGRATION_AND_REAL_SMOKE_COMPLETE"
        old_v1_task_enabled = $false
        failed_v2_task_enabled = $false
        new_v3_task_enabled = $true
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
    $failedV2AfterRollback = Assert-FailedV2Unchanged -Expected $failedV2Before
    Assert-DirectoryFileHashes -Directory $oldV2EvidenceRoot -Expected $oldV2EvidenceBefore
    if (-not (Test-Path -LiteralPath $rollbackEvidence)) {
        $rollback = [ordered]@{
            schema_version = 1
            manifest_type = "ndx_dynamic_shadow_selection_task_v3_rollback"
            captured_at_utc = [datetime]::UtcNow.ToString("o")
            reason = $failure
            new_task_secured_before_old_restore = $newSecured
            old_task_restored = [bool]$rollbackResult.old_task_restored
            old_task = Get-TaskSnapshot -TaskName $oldTaskName
            failed_v2_task = $failedV2AfterRollback
            new_task = if (Get-ScheduledTask -TaskPath $taskPath -TaskName $newTaskName -ErrorAction SilentlyContinue) {
                Get-TaskSnapshot -TaskName $newTaskName
            } else { $null }
            rollback_contract = "NEW_V3_DISABLED_AND_STOPPED_THEN_OLD_V1_ENABLED_FAILED_V2_UNCHANGED_NO_TASK_DELETION"
            pre_cutover_record_sha256 = $pre.record_sha256
            disabled_registration_record_sha256 = if (Test-Path -LiteralPath $disabledEvidence) {
                (Get-Content -LiteralPath $disabledEvidence -Raw -Encoding UTF8 | ConvertFrom-Json).record_sha256
            } else { $null }
            old_v2_evidence_root = $oldV2EvidenceRoot
            old_v2_evidence_hashes = $oldV2EvidenceBefore
            protected_hashes = Get-ProtectedHashes
        }
        Write-ImmutableRecord -Path $rollbackEvidence -Payload $rollback
    }
    throw "Atomic runtime-v3 migration failed and rollback was attempted: $failure"
}
