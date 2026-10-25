param(
    [Parameter(Mandatory=$true)][string]$ConfigurationPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ConfigurationSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedDailyXmlSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedMonthlyXmlSha256,
    [Parameter(Mandatory=$true)][string]$BackupDirectory,
    [string]$RootPath='E:\Git\us_ratchet',
    [string]$PythonPath='D:\python\python.exe',
    [switch]$Apply
)
$ErrorActionPreference='Stop'
$RootPath=(Resolve-Path -LiteralPath $RootPath).Path
$ConfigurationPath=(Resolve-Path -LiteralPath $ConfigurationPath).Path
$PythonPath=(Resolve-Path -LiteralPath $PythonPath).Path
if (-not $ConfigurationPath.StartsWith($RootPath+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'CONFIG_OUTSIDE_ROOT' }
$RelativeConfiguration=$ConfigurationPath.Substring($RootPath.Length+1).Replace('\','/')
function Hash-Text([string]$Text) {
    $Digest=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($Digest.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant() } finally { $Digest.Dispose() }
}
function Root-File([string]$Name) {
    if ([IO.Path]::IsPathRooted($Name) -or $Name.Contains(':') -or ($Name -split '[\\/]') -contains '..') { throw 'INVALID_SOURCE_PATH' }
    return Join-Path $RootPath $Name
}
function Quote-Literal([string]$Value) { return "'"+$Value.Replace("'","''")+"'" }
if ((Get-FileHash -LiteralPath $ConfigurationPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ConfigurationSha256) { throw 'CONFIG_CHANGED' }
$Configuration=Get-Content -LiteralPath $ConfigurationPath -Raw | ConvertFrom-Json
$DescriptorPath=Root-File $Configuration.descriptor.path
if ((Get-FileHash -LiteralPath $DescriptorPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Configuration.descriptor.sha256) { throw 'DESCRIPTOR_CHANGED' }
$Descriptor=Get-Content -LiteralPath $DescriptorPath -Raw | ConvertFrom-Json
$SelfPin=$Descriptor.code_sha256.'scripts/switch_prospective_paper_tasks_v2.ps1'
if (-not $SelfPin -or (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $SelfPin) { throw 'CUTOVER_SCRIPT_NOT_PINNED' }
if ((Get-Date).ToUniversalTime() -ge ([datetimeoffset]$Descriptor.plan.first_session.decision_at).UtcDateTime) { throw 'FIRST_WINDOW_ALREADY_DUE' }
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'EXPECTED_BEIJING_TIMEZONE' }
$Names=@('UsRatchet-StrategySimulation-Daily','UsRatchet-RegisteredPaper-Monthly')
$Expected=@($ExpectedDailyXmlSha256,$ExpectedMonthlyXmlSha256)
function Check-Tasks {
    $Result=@()
    for ($Index=0;$Index -lt $Names.Count;$Index++) {
        $Task=Get-ScheduledTask -TaskName $Names[$Index]
        $Xml=Export-ScheduledTask -TaskName $Names[$Index]
        if ((Hash-Text $Xml) -ne $Expected[$Index]) { throw 'TASK_CHANGED' }
        if ($Task.State -eq 'Running') { throw 'TASK_RUNNING' }
        if (-not $Task.Settings.Enabled -or [string]$Task.Settings.MultipleInstances -ne 'IgnoreNew') { throw 'TASK_SETTINGS_UNEXPECTED' }
        $Owner=([Security.Principal.NTAccount]::new($Task.Principal.UserId)).Translate([Security.Principal.SecurityIdentifier]).Value
        if ($Owner -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) { throw 'TASK_OWNER_CHANGED' }
        $Result+=@{Task=$Task;Xml=$Xml}
    }
    $Times=@($Result[0].Task.Triggers | ForEach-Object { ([datetime]$_.StartBoundary).ToString('HH:mm') } | Sort-Object)
    if (($Times -join ',') -ne '22:00,23:00') { throw 'DAILY_TRIGGERS_UNEXPECTED' }
    return $Result
}
$Snapshot=Check-Tasks
Push-Location -LiteralPath $RootPath
try {
    $Output=& $PythonPath -X utf8 -E -B -m scripts.run_prospective_paper_diagnosed_v2 --root $RootPath --configuration-path $RelativeConfiguration --expected-sha256 $ConfigurationSha256
    if ($LASTEXITCODE -ne 0) { throw 'RUNTIME_PREFLIGHT_FAILED' }
    $Preflight=($Output -join "`n") | ConvertFrom-Json
    if ($Preflight.status -ne 'WAIT_REGISTERED_START' -or $Preflight.account_writes -ne $false) { throw 'UNEXPECTED_PREFLIGHT_STATE' }
} finally { Pop-Location }
$Snapshot=Check-Tasks
if (-not $Apply) {
    @{status='PREVIEW_READY';configuration_sha256=$ConfigurationSha256;tasks=$Names;trigger_changes=$false;preflight=$Preflight} | ConvertTo-Json -Depth 5
    return
}
if (Test-Path -LiteralPath $BackupDirectory) { throw 'BACKUP_ALREADY_EXISTS' }
New-Item -ItemType Directory -Path $BackupDirectory | Out-Null
for ($Index=0;$Index -lt $Names.Count;$Index++) {
    [IO.File]::WriteAllText((Join-Path $BackupDirectory ($Names[$Index]+'.xml')),$Snapshot[$Index].Xml,[Text.UTF8Encoding]::new($false))
}
@{status='PREPARED';configuration_sha256=$ConfigurationSha256;old_xml_sha256=$Expected;tasks=$Names;rollback='Restore each saved XML with Register-ScheduledTask -Xml after confirming tasks are not running.'} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $BackupDirectory 'manifest.json') -Encoding UTF8
$Command='& '+(Quote-Literal $PythonPath)+' -X utf8 -E -B -m scripts.run_prospective_paper_diagnosed_v2 --root '+(Quote-Literal $RootPath)+' --configuration-path '+(Quote-Literal $RelativeConfiguration)+' --expected-sha256 '+(Quote-Literal $ConfigurationSha256)+[Environment]::NewLine+'exit $LASTEXITCODE'
$Encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
$Action=New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand '+$Encoded) -WorkingDirectory $RootPath
try {
    foreach ($Name in $Names) { Disable-ScheduledTask -TaskName $Name | Out-Null }
    foreach ($Name in $Names) { if ((Get-ScheduledTask -TaskName $Name).State -eq 'Running') { throw 'TASK_RUNNING_AFTER_DISABLE' } }
    foreach ($Name in $Names) { Set-ScheduledTask -TaskName $Name -Action $Action | Out-Null }
    foreach ($Name in $Names) { Enable-ScheduledTask -TaskName $Name | Out-Null }
    $Readback=@()
    for ($Index=0;$Index -lt $Names.Count;$Index++) {
        $Actual=Get-ScheduledTask -TaskName $Names[$Index]
        $Xml=Export-ScheduledTask -TaskName $Names[$Index]
        if ($Actual.Actions.Count -ne 1 -or $Actual.Actions.Execute -ne $Action.Execute -or $Actual.Actions.Arguments -ne $Action.Arguments -or $Actual.Actions.WorkingDirectory -ne $RootPath) { throw 'ACTION_READBACK_MISMATCH' }
        $Before=[xml]$Snapshot[$Index].Xml;$After=[xml]$Xml
        foreach ($Field in @('Triggers','Principals','Settings')) {
            if ($Before.Task.$Field.OuterXml -ne $After.Task.$Field.OuterXml) { throw 'NON_ACTION_SETTINGS_CHANGED' }
        }
        $Readback+=@{task=$Names[$Index];xml_sha256=(Hash-Text $Xml);state=[string]$Actual.State}
    }
    @{status='TASK_ACTIONS_UPDATED_AND_VERIFIED';configuration_sha256=$ConfigurationSha256;tasks=$Readback;trigger_changes=$false;account_initialized=$false} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $BackupDirectory 'complete.json') -Encoding UTF8
    Get-Content -LiteralPath (Join-Path $BackupDirectory 'complete.json') -Raw
} catch {
    @{status='RECONCILIATION_REQUIRED';reason=$_.Exception.Message;automatic_retry=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $BackupDirectory 'failed.json') -Encoding UTF8
    throw
}
