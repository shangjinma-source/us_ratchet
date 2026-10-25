param(
    [Parameter(Mandatory=$true)][string]$ConfigPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ConfigSha256,
    [switch]$Install
)
$ErrorActionPreference = 'Stop'
$TaskName = 'UsRatchet-DailySource-Evidence'
$OwnerMarker = 'us_ratchet:daily-source-evidence:v1'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$ResolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
if ((Get-FileHash -LiteralPath $ResolvedConfig -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ConfigSha256) {
    throw 'DAILY_PIPELINE_CONFIGURATION_CHANGED'
}
# This fixed local trigger is before NY 10:00 in both US daylight and standard time.
# The Python exchange calendar decides whether today's session is eligible.
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'BEIJING_SCHEDULER_TIMEZONE_REQUIRED' }
$Executable = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$Launcher = Join-Path $PSScriptRoot 'run_local_daily_sources.ps1'
foreach ($Value in @($Launcher,$ResolvedConfig)) {
    if ($Value.Contains('"')) { throw 'QUOTED_PATH_REFUSED' }
}
$Arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -File "' + $Launcher +
    '" -ConfigPath "' + $ResolvedConfig + '" -ConfigSha256 ' + $ConfigSha256 + ' -Execute'
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) { throw 'EXISTING_DAILY_SOURCE_TASK_REQUIRES_INSPECTION' }
$Descriptor = [ordered]@{
    status='PREVIEW_ONLY_NO_TASK_REGISTERED'; task_name=$TaskName
    executable=$Executable; arguments=$Arguments; working_directory=$ProjectRoot
    schedule='Daily 21:10 Asia/Shanghai'; start_when_available=$true
    logon_type='Interactive'; execution_limit='30 minutes'; retries=0
}
if (-not $Install) { $Descriptor | ConvertTo-Json; return }
$Action = New-ScheduledTaskAction -Execute $Executable -Argument $Arguments -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At '21:10'
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited
$Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description $OwnerMarker
Register-ScheduledTask -TaskName $TaskName -InputObject $Task | Out-Null
$Descriptor.status = 'REGISTERED_NOT_EXECUTED'
$Descriptor | ConvertTo-Json
