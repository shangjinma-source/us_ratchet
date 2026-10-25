param(
    [Parameter(Mandatory=$true)][string]$DescriptorPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$DescriptorSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedDailyXmlSha256,
    [Parameter(Mandatory=$true)][string]$BackupDirectory,
    [string]$ExpectedMonthlyXmlSha256 = 'ABSENT',
    [string]$PythonPath = 'D:\python\python.exe',
    [switch]$Apply
)
$ErrorActionPreference='Stop'
$DailyName='UsRatchet-StrategySimulation-Daily'
$MonthlyName='UsRatchet-RegisteredPaper-Monthly'
$DescriptorPath=(Resolve-Path -LiteralPath $DescriptorPath).Path
if ((Get-FileHash -LiteralPath $DescriptorPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $DescriptorSha256) { throw 'DESCRIPTOR_CHANGED' }
$Descriptor=Get-Content -LiteralPath $DescriptorPath -Raw | ConvertFrom-Json
$RootPath=(Resolve-Path -LiteralPath $Descriptor.root).Path
$PythonPath=(Resolve-Path -LiteralPath $PythonPath).Path
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'EXPECTED_BEIJING_WINDOWS_TIMEZONE' }
foreach ($Pin in $Descriptor.source_hashes.PSObject.Properties) {
    if ([IO.Path]::IsPathRooted($Pin.Name) -or ($Pin.Name -split '[\\/]') -contains '..') { throw 'INVALID_SOURCE_PIN' }
    if ((Get-FileHash -LiteralPath (Join-Path $RootPath $Pin.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Pin.Value) { throw 'SOURCE_CHANGED' }
}
if (-not $Descriptor.source_hashes.'scripts/preflight_registered_paper_task_cutover.py' -or -not $Descriptor.source_hashes.'scripts/switch_registered_paper_tasks.ps1') { throw 'CUTOVER_SOURCE_PINS_REQUIRED' }
function Hash-Text([string]$Text) {
    $Digest=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($Digest.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant() } finally { $Digest.Dispose() }
}
function Quote-Literal([string]$Value) { return "'"+$Value.Replace("'","''")+"'" }
function Check-Tasks {
    $Daily=Get-ScheduledTask -TaskName $DailyName -ErrorAction Stop
    $Monthly=Get-ScheduledTask -TaskName $MonthlyName -ErrorAction SilentlyContinue
    $DailyXml=Export-ScheduledTask -TaskName $DailyName
    if ((Hash-Text $DailyXml) -ne $ExpectedDailyXmlSha256) { throw 'DAILY_TASK_CHANGED' }
    $MonthlyXml=$null
    if ($Monthly) {
        $MonthlyXml=Export-ScheduledTask -TaskName $MonthlyName
        if ((Hash-Text $MonthlyXml) -ne $ExpectedMonthlyXmlSha256) { throw 'MONTHLY_TASK_CHANGED' }
    } elseif ($ExpectedMonthlyXmlSha256 -ne 'ABSENT') { throw 'EXPECTED_MONTHLY_MISSING' }
    foreach ($Task in @($Daily,$Monthly)) {
        if (-not $Task) { continue }
        if ($Task.State -eq 'Running') { throw 'TASK_RUNNING' }
        $Owner=([Security.Principal.NTAccount]::new($Task.Principal.UserId)).Translate([Security.Principal.SecurityIdentifier]).Value
        if ($Owner -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) { throw 'TASK_OWNER_MISMATCH' }
    }
    if ([string]$Daily.Settings.MultipleInstances -ne 'IgnoreNew' -or [string]$Daily.Principal.RunLevel -ne 'Limited') { throw 'DAILY_SETTINGS_UNEXPECTED' }
    $Times=@($Daily.Triggers | ForEach-Object { ([datetime]$_.StartBoundary).ToString('HH:mm') } | Sort-Object)
    if (($Times -join ',') -ne '22:00,23:00') { throw 'DAILY_TRIGGERS_UNEXPECTED' }
    return @{Daily=$Daily;Monthly=$Monthly;DailyXml=$DailyXml;MonthlyXml=$MonthlyXml}
}
function Check-Admission([string]$Token) {
    Push-Location -LiteralPath $RootPath
    try {
        $Options=@('-X','utf8','-E','-B','-m','scripts.preflight_registered_paper_task_cutover','--descriptor-path',$DescriptorPath,'--expected-descriptor-sha256',$DescriptorSha256)
        if ($Token) { $Options+=@('--owned-lock-token',$Token) }
        & $PythonPath @Options
        if ($LASTEXITCODE -ne 0) { throw 'REGISTERED_BUNDLE_NOT_ADMITTED' }
    } finally { Pop-Location }
}
function Make-Action([string]$Mode) {
    $Command='& '+(Quote-Literal $PythonPath)+' -X utf8 -E -B -m scripts.run_registered_paper_automation --descriptor-path '+(Quote-Literal $DescriptorPath)+' --expected-descriptor-sha256 '+(Quote-Literal $DescriptorSha256)+' --mode '+$Mode+' --execute; exit $LASTEXITCODE'
    $Encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
    return New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand '+$Encoded) -WorkingDirectory $RootPath
}
$Snapshot=Check-Tasks
Check-Admission ''
if (-not $Apply) {
    [pscustomobject]@{Status='PREVIEW_ONLY';Daily=$DailyName;Monthly=$MonthlyName;DailyCadence='Existing 22:00/23:00 BJT; Python NY gate';MonthlyCadence='15 minutes';DescriptorSha256=$DescriptorSha256;BackupDirectory=$BackupDirectory;Heartbeat11='Root to retain followup only; script does not edit automation';Rollback='Restore daily.xml/monthly.xml with Register-ScheduledTask -Xml; remove newly created monthly only if manifest says previously absent'} | ConvertTo-Json
    return
}
$LockPath=Join-Path $RootPath 'data/local_scheduler/quantity_v2_daily/running.lock'
$Token=[guid]::NewGuid().ToString('N')
$BackupCreated=$false
$Handle=[IO.File]::Open($LockPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try { $Bytes=[Text.Encoding]::UTF8.GetBytes($Token);$Handle.Write($Bytes,0,$Bytes.Length) } finally { $Handle.Dispose() }
try {
    $Snapshot=Check-Tasks
    Check-Admission $Token
    if (Test-Path -LiteralPath $BackupDirectory) { throw 'CREATE_ONLY_BACKUP_EXISTS' }
    New-Item -ItemType Directory -Path $BackupDirectory | Out-Null
    $BackupCreated=$true
    [IO.File]::WriteAllText((Join-Path $BackupDirectory 'daily.xml'),$Snapshot.DailyXml,[Text.UTF8Encoding]::new($false))
    if ($Snapshot.MonthlyXml) { [IO.File]::WriteAllText((Join-Path $BackupDirectory 'monthly.xml'),$Snapshot.MonthlyXml,[Text.UTF8Encoding]::new($false)) }
    @{descriptor_sha256=$DescriptorSha256;daily_xml_sha256=$ExpectedDailyXmlSha256;monthly_xml_sha256=$ExpectedMonthlyXmlSha256;monthly_previously_absent=($null -eq $Snapshot.Monthly);status='PREPARED_BEFORE_TASK_WRITES'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $BackupDirectory 'manifest.json') -Encoding UTF8
    # Only the existing daily Action changes; its actual schedule is preserved.
    Set-ScheduledTask -TaskName $DailyName -Action (Make-Action 'daily') | Out-Null
    $Trigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
    $Settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3) -Hidden
    $Principal=New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $Task=New-ScheduledTask -Action (Make-Action 'monthly') -Trigger $Trigger -Settings $Settings -Principal $Principal -Description 'us_ratchet:registered-paper-monthly:v1'
    Register-ScheduledTask -TaskName $MonthlyName -InputObject $Task -Force | Out-Null
    'TASK_ACTIONS_UPDATED_REQUIRES_READBACK' | Set-Content -LiteralPath (Join-Path $BackupDirectory 'complete.txt')
} catch {
    # Preserve partial changes and backup; never blindly retry or auto-rollback.
    if ($BackupCreated) { 'RECONCILIATION_REQUIRED' | Set-Content -LiteralPath (Join-Path $BackupDirectory 'failed.txt') }
    throw
} finally {
    if ([IO.File]::ReadAllText($LockPath) -ne $Token) { throw 'CUTOVER_LOCK_OWNERSHIP_CHANGED' }
    Remove-Item -LiteralPath $LockPath
}
