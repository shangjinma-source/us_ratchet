[CmdletBinding()]
param(
    [string]$ProjectRoot = 'E:\Git\us_ratchet',
    [string]$PythonExecutable = 'D:\python\python.exe',
    [switch]$Apply,
    [switch]$AcknowledgeExplicitUserApproval,
    [switch]$AcknowledgeResearchOnlyNoLiveMutation,
    [string]$ExpectedReviewSha256 = '',
    [switch]$InternalFunctionTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$root = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
$taskPath = '\'
$legacyNames = @('us_ratchet_ndx_dynamic_shadow_selection_daily', 'us_ratchet_ndx_dynamic_shadow_selection_daily_v2_budgeted')
$oldName = 'us_ratchet_ndx_dynamic_shadow_selection_daily_v3_reviewed_calendar'
$newName = 'us_ratchet_ndx_dynamic_shadow_selection_daily_v4_accepted_receipts'
$dailyOld = Join-Path $root 'scripts\ndx_dynamic_shadow_daily_v3.py'
$dailyNew = Join-Path $root 'scripts\ndx_dynamic_shadow_daily_v4.py'
$reviewPath = Join-Path $root 'data\cache\research\ndx_dynamic_shadow_task_migration_v4\review_draft.json'
$reviewScript = Join-Path $root 'scripts\ndx_dynamic_shadow_runtime_v4_migration_review.py'
$readinessScript = Join-Path $root 'scripts\ndx_dynamic_shadow_runtime_v4_migration.py'
$taskEvidenceScript = Join-Path $root 'scripts\ndx_dynamic_shadow_runtime_v4_task_evidence.py'
$protectedPaths = @('config\config.yaml','data\state.json','data\broker_positions.json')

function Get-Digest([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Get-Protected {
    $result = [ordered]@{}
    foreach ($relative in $protectedPaths) { $result[$relative] = Get-Digest (Join-Path $root $relative) }
    return $result
}
function Assert-Protected($Before) {
    $after = Get-Protected
    foreach ($relative in $protectedPaths) {
        if ($after[$relative] -cne $Before[$relative]) { throw 'Protected live file changed.' }
    }
}
function Write-ImmutableJson([string]$Path, $Value) {
    if (Test-Path -LiteralPath $Path) { throw 'Evidence collision; refusing overwrite.' }
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Value | ConvertTo-Json -Depth 60 -Compress) + "`n")
    $temporary = $Path + '.staging.' + [guid]::NewGuid().ToString('N')
    $stream = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
    # File.Move is create-only. Interrupted staging is retained for diagnosis.
    [IO.File]::Move($temporary, $Path)
}
function Invoke-PythonJson([string]$Script, [string[]]$Arguments) {
    $output = & $PythonExecutable -B $Script @Arguments 2>&1
    $code = $LASTEXITCODE
    try { $value = Convert-EvidenceJson (($output | Out-String).Trim()) } catch { throw 'Python evidence protocol invalid.' }
    return @{ code = $code; value = $value }
}
function Convert-EvidenceJson([string]$Json) {
    if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey('DateKind')) {
        return ConvertFrom-Json -InputObject $Json -DateKind String
    }
    return ConvertFrom-Json -InputObject $Json
}
function Assert-BeijingTimezone {
    if ((Get-TimeZone).Id -cne 'China Standard Time') { throw 'Local schedule requires China Standard Time.' }
}
function Assert-ApplyAuthorization {
    if (-not $AcknowledgeExplicitUserApproval -or -not $AcknowledgeResearchOnlyNoLiveMutation -or
        $ExpectedReviewSha256 -cnotmatch '^[0-9a-f]{64}$') {
        throw 'Apply requires two explicit acknowledgements and an independently approved exact review SHA256.'
    }
}
function Assert-Review([string]$ExpectedFileHash = '') {
    $before = Get-Digest $reviewPath
    if ($ExpectedFileHash -and $before -cne $ExpectedFileHash) { throw 'Review file changed.' }
    $result = Invoke-PythonJson $reviewScript @('--verify', $reviewPath)
    if ($result.code -ne 0 -or $result.value.review_sha256 -cne $ExpectedReviewSha256 -or
        $result.value.status -cne 'REVIEW_DRAFT_NOT_AUTHORIZATION' -or
        @($result.value.missing_required_components).Count -ne 0 -or
        [string]::IsNullOrWhiteSpace([string]$result.value.activation_snapshot.sha256) -or
        (Get-Digest $reviewPath) -cne $before) { throw 'Exact approved review/components/activation binding is not valid.' }
    return $before
}
function Get-TaskRecord([string]$Name) {
    $matches = @(Get-ScheduledTask -ErrorAction Stop | Where-Object { $_.TaskName -eq $Name })
    if ($matches.Count -ne 1 -or $matches[0].TaskPath -cne '\') { throw 'Task absent, duplicate or noncanonical.' }
    $task = $matches[0]
    $info = Get-ScheduledTaskInfo -TaskPath '\' -TaskName $Name -ErrorAction Stop
    return @{ name=$Name; state=[string]$task.State; xml=[string](Export-ScheduledTask -TaskPath '\' -TaskName $Name);
        last_run=[datetime]$info.LastRunTime; result=[int64]$info.LastTaskResult }
}
function Get-XmlParts([string]$Xml) {
    [xml]$document = $Xml
    $ns = [Xml.XmlNamespaceManager]::new($document.NameTable)
    $ns.AddNamespace('t','http://schemas.microsoft.com/windows/2004/02/mit/task')
    # Windows omits default Enabled=true on export. Normalize only these two
    # documented defaults in the parsed copy, never in the registered task.
    # https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema
    $containers = @($document.SelectNodes('/t:Task/t:Settings|/t:Task/t:Triggers/*',$ns))
    foreach ($container in $containers) {
        $enabledNodes = @($container.SelectNodes('t:Enabled',$ns))
        if ($enabledNodes.Count -gt 1) { throw 'Duplicate Enabled field.' }
        if ($enabledNodes.Count -eq 0) {
            $node = $document.CreateElement('Enabled',$ns.LookupNamespace('t'))
            $node.InnerText = 'true'
        } else {
            $node = $enabledNodes[0]
            $container.RemoveChild($node) | Out-Null
        }
        if ($container.LocalName -ceq 'Settings') { $container.AppendChild($node) | Out-Null }
        else { $container.PrependChild($node) | Out-Null }
    }
    $parts = @{ document=$document; ns=$ns }
    foreach ($name in @('Actions','Triggers','Principals','Settings')) {
        $nodes = @($document.SelectNodes("/t:Task/t:$name",$ns))
        if ($nodes.Count -ne 1) { throw 'Task XML section absent or duplicated.' }
        $parts[$name] = $nodes[0]
    }
    return $parts
}
function Assert-WeeklyDefinition([string]$Xml, [string]$Daily, [bool]$Enabled) {
    $p = Get-XmlParts $Xml
    $ns = $p.ns
    $actions = @($p.Actions.ChildNodes | Where-Object NodeType -eq Element)
    $triggers = @($p.Triggers.ChildNodes | Where-Object NodeType -eq Element)
    $principals = @($p.Principals.ChildNodes | Where-Object NodeType -eq Element)
    if ($actions.Count -ne 1 -or $actions[0].LocalName -cne 'Exec' -or
        $triggers.Count -ne 1 -or $triggers[0].LocalName -cne 'CalendarTrigger' -or
        $principals.Count -ne 1 -or $principals[0].LocalName -cne 'Principal') { throw 'Task must have one Exec, weekly trigger and principal.' }
    $action = $actions[0]
    $actionFields = @($action.ChildNodes | Where-Object NodeType -eq Element | ForEach-Object LocalName | Sort-Object)
    if (($actionFields -join ',') -cne 'Arguments,Command,WorkingDirectory' -or
        $action.SelectSingleNode('t:Command',$ns).InnerText -cne $PythonExecutable -or
        $action.SelectSingleNode('t:Arguments',$ns).InnerText -cne ('-B "{0}" --execute' -f $Daily) -or
        $action.SelectSingleNode('t:WorkingDirectory',$ns).InnerText -cne $root) { throw 'Task action differs from exact contract.' }
    $trigger = $triggers[0]
    $fields = @($trigger.ChildNodes | Where-Object NodeType -eq Element | ForEach-Object LocalName | Sort-Object)
    if (($fields -join ',') -cne 'Enabled,ScheduleByWeek,StartBoundary' -or
        $trigger.SelectSingleNode('t:Enabled',$ns).InnerText -cne 'true' -or
        $trigger.SelectSingleNode('t:StartBoundary',$ns).InnerText -notmatch '^\d{4}-\d{2}-\d{2}T11:20:00$') { throw 'Task trigger must be local Tue-Sat 11:20 without repetition.' }
    $week = $trigger.SelectSingleNode('t:ScheduleByWeek',$ns)
    $weekFields = @($week.ChildNodes | Where-Object NodeType -eq Element | ForEach-Object LocalName | Sort-Object)
    $days = @($week.SelectSingleNode('t:DaysOfWeek',$ns).ChildNodes | Where-Object NodeType -eq Element | ForEach-Object LocalName | Sort-Object)
    if (($weekFields -join ',') -cne 'DaysOfWeek,WeeksInterval' -or
        ($days -join ',') -cne 'Friday,Saturday,Thursday,Tuesday,Wednesday' -or
        $week.SelectSingleNode('t:WeeksInterval',$ns).InnerText -cne '1') { throw 'Weekly schedule changed.' }
    $settings = @{StartWhenAvailable='true';DisallowStartIfOnBatteries='false';StopIfGoingOnBatteries='false';MultipleInstancesPolicy='IgnoreNew';ExecutionTimeLimit='PT11H';Enabled=$Enabled.ToString().ToLowerInvariant()}
    foreach ($key in $settings.Keys) {
        $nodes = @($p.Settings.SelectNodes("t:$key",$ns))
        if ($nodes.Count -ne 1 -or $nodes[0].InnerText -cne $settings[$key]) { throw "Task setting changed: $key" }
    }
    if ($p.Settings.SelectSingleNode('t:RestartOnFailure/t:Interval',$ns).InnerText -cne 'PT10M' -or
        $p.Settings.SelectSingleNode('t:RestartOnFailure/t:Count',$ns).InnerText -cne '3') { throw 'Restart contract changed.' }
}
function New-DisabledV4Xml([string]$OldXml, [string]$OwnershipMarker) {
    if ($OwnershipMarker -cnotmatch '^us_ratchet_v4_attempt:[0-9a-f]{32}$') { throw 'Invalid attempt ownership marker.' }
    Assert-WeeklyDefinition $OldXml $dailyOld $true
    $p = Get-XmlParts $OldXml
    $p.Actions.SelectSingleNode('t:Exec/t:Arguments',$p.ns).InnerText = '-B "{0}" --execute' -f $dailyNew
    $p.Settings.SelectSingleNode('t:Enabled',$p.ns).InnerText = 'false'
    $uri = $p.document.SelectSingleNode('/t:Task/t:RegistrationInfo/t:URI',$p.ns)
    if ($null -ne $uri) { $uri.InnerText = '\' + $newName }
    $registration = $p.document.SelectSingleNode('/t:Task/t:RegistrationInfo',$p.ns)
    if ($null -eq $registration) { throw 'RegistrationInfo is required for attempt ownership.' }
    $description = $registration.SelectSingleNode('t:Description',$p.ns)
    if ($null -eq $description) {
        $description = $p.document.CreateElement('Description',$p.document.DocumentElement.NamespaceURI)
        $registration.AppendChild($description) | Out-Null
    }
    $description.InnerText = $OwnershipMarker
    return $p.document.OuterXml
}
function Assert-NewDefinition([string]$OldXml, [string]$NewXml, [bool]$Enabled, [string]$OwnershipMarker) {
    Assert-WeeklyDefinition $NewXml $dailyNew $Enabled
    $expected = Get-XmlParts (New-DisabledV4Xml $OldXml $OwnershipMarker)
    $expected.Settings.SelectSingleNode('t:Enabled',$expected.ns).InnerText = $Enabled.ToString().ToLowerInvariant()
    $actual = Get-XmlParts $NewXml
    if ($actual.document.SelectSingleNode('/t:Task/t:RegistrationInfo/t:Description',$actual.ns).InnerText -cne $OwnershipMarker) { throw 'New task is not owned by this attempt.' }
    foreach ($key in @('Actions','Triggers','Principals','Settings')) {
        if ($expected[$key].OuterXml -cne $actual[$key].OuterXml) { throw 'New task inherited definition changed.' }
    }
}
function Assert-NoRuntime {
    foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction Stop)) {
        if ($process.ProcessId -eq $PID) { continue }
        $command = [string]$process.CommandLine
        if ($process.Name -match '^python(w|\d+(\.\d+)*)?\.exe$' -and [string]::IsNullOrWhiteSpace($command)) { throw 'Python command line unavailable.' }
        if ($command -match 'ndx_dynamic_shadow_(daily|fresh_search|candidate_generator)(_v\d+)?(\.py)?(?=[\s"'']|$)') { throw 'Research runtime or candidate process is active.' }
    }
}
function Assert-Exclusive([string]$Allowed) {
    foreach ($task in @(Get-ScheduledTask -ErrorAction Stop)) {
        $text = [string]$task.TaskName + ' ' + ((@($task.Actions) | ForEach-Object { [string]$_.Execute + ' ' + [string]$_.Arguments }) -join ' ')
        if ($text -match 'dynamic_shadow_selection|ndx_dynamic_shadow_(daily|fresh_search|candidate_generator)' -and
            [string]$task.State -ne 'Disabled' -and -not ($task.TaskPath -ceq '\' -and $task.TaskName -ceq $Allowed)) { throw 'Duplicate enabled scheduler.' }
    }
    $jobsPath = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.openclaw\cron\jobs.json'
    $before = Get-Digest $jobsPath
    $value = Get-Content -LiteralPath $jobsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $value.PSObject.Properties['jobs'] -or $value.jobs -isnot [Array]) { throw 'OpenClaw jobs schema unknown.' }
    foreach ($job in $value.jobs) {
        if ($job.enabled -isnot [bool]) { throw 'OpenClaw enabled state unknown.' }
        if ($job.enabled -and ($job | ConvertTo-Json -Depth 60 -Compress) -match 'dynamic_shadow_selection|ndx_dynamic_shadow_(daily|fresh_search|candidate_generator)') { throw 'OpenClaw duplicate scheduler.' }
    }
    if ((Get-Digest $jobsPath) -cne $before) { throw 'OpenClaw inventory drift.' }
    Assert-NoRuntime
}
function Assert-LegacyUnchanged($Baseline) {
    foreach ($name in $legacyNames) {
        $now = Get-TaskRecord $name
        if ($now.state -cne 'Disabled' -or $now.xml -cne $Baseline[$name].xml) { throw 'Legacy v1/v2 changed.' }
    }
}
function Get-UtcNow { return [datetime]::UtcNow }
function Wait-NextTaskSecond([string]$CapturedAtUtc) {
    $captured = [datetimeoffset]::Parse($CapturedAtUtc).UtcDateTime
    $boundary = $captured.AddTicks(-($captured.Ticks % [timespan]::TicksPerSecond)).AddSeconds(1)
    $deadline = (Get-UtcNow).AddSeconds(2)
    while ((Get-UtcNow) -lt $boundary) {
        if ((Get-UtcNow) -ge $deadline) { throw 'Could not cross task metadata timestamp boundary.' }
        Start-Sleep -Milliseconds 50
    }
}
function Assert-V3State([string]$Baseline, [bool]$Enabled) {
    $record = Get-TaskRecord $oldName
    $state = if ($Enabled) { 'Ready' } else { 'Disabled' }
    if ($record.state -cne $state) { throw 'v3 state changed.' }
    $expected = Get-XmlParts $Baseline
    $expected.Settings.SelectSingleNode('t:Enabled',$expected.ns).InnerText = $Enabled.ToString().ToLowerInvariant()
    $actual = Get-XmlParts $record.xml
    foreach ($key in @('Actions','Triggers','Principals','Settings')) {
        if ($expected[$key].OuterXml -cne $actual[$key].OuterXml) { throw 'v3 definition changed.' }
    }
}
function Invoke-FailSafeRollback([bool]$NewMayExist, [bool]$OldMayBeDisabled, [string]$OldBaselineXml, [string]$OwnershipMarker) {
    $secured = -not $NewMayExist
    $restored = -not $OldMayBeDisabled
    $errors = @()
    $oldAlreadyReady = $false
    if ($NewMayExist) {
        try {
            $current = Get-TaskRecord $newName
            $parts = Get-XmlParts $current.xml
            $enabled = $parts.Settings.SelectSingleNode('t:Enabled',$parts.ns).InnerText -ceq 'true'
            Assert-NewDefinition $OldBaselineXml $current.xml $enabled $OwnershipMarker
            if ($OldMayBeDisabled -and (Get-TaskRecord $oldName).state -ceq 'Ready') {
                Assert-V3State $OldBaselineXml $true
                $oldAlreadyReady = $true
                $restored = $true
            }
            Disable-ScheduledTask -TaskPath '\' -TaskName $newName -ErrorAction Stop | Out-Null
            Assert-NewDefinition $OldBaselineXml (Get-TaskRecord $newName).xml $false $OwnershipMarker
            Stop-ScheduledTask -TaskPath '\' -TaskName $newName -ErrorAction Stop
            $deadline = [datetime]::UtcNow.AddSeconds(30)
            do { $current = Get-TaskRecord $newName; if ($current.state -cne 'Running') { break }; Start-Sleep -Milliseconds 250 } while ([datetime]::UtcNow -lt $deadline)
            if ($current.state -cne 'Disabled') { throw 'New task not disabled and stopped.' }
            Assert-NewDefinition $OldBaselineXml $current.xml $false $OwnershipMarker
            $allowed = if (-not $OldMayBeDisabled -or $oldAlreadyReady) { $oldName } else { '' }
            Assert-Exclusive $allowed
            $secured = $true
        } catch { $errors += $_.Exception.Message; $secured = $false }
    }
    if ($OldMayBeDisabled -and -not $oldAlreadyReady -and $secured) {
        try {
            Assert-V3State $OldBaselineXml $false
            Enable-ScheduledTask -TaskPath '\' -TaskName $oldName -ErrorAction Stop | Out-Null
            $restored = (Get-TaskRecord $oldName).state -ceq 'Ready'
            if (-not $restored) { throw 'Old v3 not restored Ready.' }
        } catch { $errors += $_.Exception.Message; $restored = $false }
    }
    return @{new_task_secured=$secured;old_v3_restored=$restored;errors=$errors;task_deletion_performed=$false}
}

if ($InternalFunctionTest) { return }
if ($root -cne [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\') -or
    $PythonExecutable -cne 'D:\python\python.exe') { throw 'Noncanonical project or Python.' }
if ($Apply) { Assert-ApplyAuthorization; Assert-BeijingTimezone }
$readiness = Invoke-PythonJson $readinessScript @('--readiness')
if (-not $Apply) {
    @{mode='PLAN_ONLY';readiness=$readiness.value;migration_performed=$false;task_mutation_performed=$false;approval_recorded=$false} | ConvertTo-Json -Depth 60
    exit 0
}
if ($readiness.code -ne 0 -or $readiness.value.status -cne 'READY_FOR_V4_MIGRATION_REVIEW_ONLY') { throw 'Readiness blocks migration.' }
$reviewHash = Assert-Review
$protectedBefore = Get-Protected
$legacyBefore = @{}
foreach ($name in $legacyNames) { $legacyBefore[$name] = Get-TaskRecord $name }
Assert-LegacyUnchanged $legacyBefore
$oldBefore = Get-TaskRecord $oldName
if ($oldBefore.state -cne 'Ready') { throw 'v3 must be enabled Ready.' }
Assert-WeeklyDefinition $oldBefore.xml $dailyOld $true
Assert-Exclusive $oldName
if (@(Get-ScheduledTask -ErrorAction Stop | Where-Object TaskName -eq $newName).Count -ne 0) { throw 'v4 already exists; no replacement allowed.' }
$attempt = Join-Path $root ('data\cache\research\ndx_dynamic_shadow_task_migration_v4\attempts\' + [datetime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '_' + [guid]::NewGuid().ToString('N'))
$ownershipMarker = 'us_ratchet_v4_attempt:' + [guid]::NewGuid().ToString('N')
Write-ImmutableJson (Join-Path $attempt 'pre_cutover.json') @{ownership_marker=$ownershipMarker;review_file_sha256=$reviewHash;independently_approved_review_sha256=$ExpectedReviewSha256;old=$oldBefore;legacy=$legacyBefore;protected=$protectedBefore;readiness=$readiness.value;captured_at_utc=[datetime]::UtcNow.ToString('o')}
$newMayExist = $false
$oldMayBeDisabled = $false
try {
    Assert-Review $reviewHash | Out-Null
    Assert-Protected $protectedBefore
    $xml = New-DisabledV4Xml $oldBefore.xml $ownershipMarker
    Assert-V3State $oldBefore.xml $true
    $newMayExist = $true
    Register-ScheduledTask -TaskPath '\' -TaskName $newName -Xml $xml -ErrorAction Stop | Out-Null
    $newMayExist = $true
    $disabled = Get-TaskRecord $newName
    if ($disabled.state -cne 'Disabled') { throw 'New task did not register disabled.' }
    Assert-NewDefinition $oldBefore.xml $disabled.xml $false $ownershipMarker
    Assert-LegacyUnchanged $legacyBefore
    Assert-Exclusive $oldName
    Assert-Review $reviewHash | Out-Null
    Write-ImmutableJson (Join-Path $attempt 'new_disabled.json') $disabled
    Assert-V3State $oldBefore.xml $true
    $oldMayBeDisabled = $true
    Disable-ScheduledTask -TaskPath '\' -TaskName $oldName -ErrorAction Stop | Out-Null
    Assert-V3State $oldBefore.xml $false
    Assert-Exclusive ''
    Assert-LegacyUnchanged $legacyBefore
    Assert-Protected $protectedBefore
    Assert-Review $reviewHash | Out-Null
    Assert-V3State $oldBefore.xml $false
    Assert-NewDefinition $oldBefore.xml (Get-TaskRecord $newName).xml $false $ownershipMarker
    Enable-ScheduledTask -TaskPath '\' -TaskName $newName -ErrorAction Stop | Out-Null
    $enabled = Get-TaskRecord $newName
    if ($enabled.state -cne 'Ready') { throw 'v4 not Ready before smoke.' }
    Assert-NewDefinition $oldBefore.xml $enabled.xml $true $ownershipMarker
    $smokeBefore = Invoke-PythonJson $taskEvidenceScript @('--snapshot')
    if ($smokeBefore.code -ne 0) { throw 'Task evidence snapshot failed.' }
    $beforePath = Join-Path $attempt 'task_smoke_before.json'
    Write-ImmutableJson $beforePath $smokeBefore.value
    Wait-NextTaskSecond ([string]$smokeBefore.value.captured_at_utc)
    Assert-V3State $oldBefore.xml $false
    Assert-NewDefinition $oldBefore.xml (Get-TaskRecord $newName).xml $true $ownershipMarker
    Start-ScheduledTask -TaskPath '\' -TaskName $newName -ErrorAction Stop
    $deadline = [datetime]::UtcNow.AddHours(11)
    do {
        Start-Sleep -Seconds 2
        $running = Get-TaskRecord $newName
        if ($running.last_run -gt $enabled.last_run -and $running.state -cne 'Running') { break }
    } while ([datetime]::UtcNow -lt $deadline)
    if ($running.state -cne 'Ready' -or $running.last_run -le $enabled.last_run -or $running.result -ne 0) { throw 'Current real task run failed or timed out.' }
    $proof = Invoke-PythonJson $taskEvidenceScript @('--verify','--before-path',$beforePath)
    if ($proof.code -ne 0) { throw 'Current task/artifact evidence failed.' }
    Assert-NewDefinition $oldBefore.xml (Get-TaskRecord $newName).xml $true $ownershipMarker
    Assert-V3State $oldBefore.xml $false
    Assert-Exclusive $newName
    Assert-LegacyUnchanged $legacyBefore
    Assert-Protected $protectedBefore
    Assert-Review $reviewHash | Out-Null
    Write-ImmutableJson (Join-Path $attempt 'post_cutover.json') @{status='V4_METADATA_AND_ARTIFACT_SMOKE_VERIFIED';task_evidence=$proof.value;review_file_sha256=$reviewHash;protected=$protectedBefore;task_instance_event_log_verified=$false}
    @{status='V4_MIGRATION_COMPLETED';evidence_root=$attempt;artifact_evidence_level=$proof.value.artifact_verification.evidence_level;economic_execution_claimed=($proof.value.artifact_verification.evidence_level -ceq 'ECONOMIC_PATHS_VERIFIED')} | ConvertTo-Json
} catch {
    $failure = $_.Exception.Message
    $rollback = Invoke-FailSafeRollback $newMayExist $oldMayBeDisabled $oldBefore.xml $ownershipMarker
    $checks = @()
    try { Assert-Protected $protectedBefore } catch { $checks += $_.Exception.Message }
    try { Assert-LegacyUnchanged $legacyBefore } catch { $checks += $_.Exception.Message }
    Write-ImmutableJson (Join-Path $attempt 'rollback.json') @{failure=$failure;rollback=$rollback;post_checks=$checks;captured_at_utc=[datetime]::UtcNow.ToString('o')}
    throw 'v4 migration failed; rollback evidence retained. Inspect evidence before any recovery.'
}
