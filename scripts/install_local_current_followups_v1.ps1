param([switch]$Install)
$ErrorActionPreference = 'Stop'
$TaskName = 'UsRatchet-CurrentAdvice-Followup'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'BEIJING_SCHEDULER_TIMEZONE_REQUIRED' }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { throw 'EXISTING_TASK_REQUIRES_INSPECTION' }
$Launcher = Join-Path $PSScriptRoot 'run_local_current_followups_v1.ps1'
if ($Launcher.Contains('"')) { throw 'QUOTED_PATH_REFUSED' }
$Executable = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$Arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -File "' + $Launcher + '"'
$Descriptor = [ordered]@{status='PREVIEW_ONLY'; task_name=$TaskName; schedule='Daily 06:15 Asia/Shanghai'; start_when_available=$true; automatic_retries=0; account_writes=$false}
if (-not $Install) { $Descriptor | ConvertTo-Json; return }
$Action = New-ScheduledTaskAction -Execute $Executable -Argument $Arguments -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At '06:15'
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$Principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description 'us_ratchet:current-advice-followup:v1; closed-session price observations only'
Register-ScheduledTask -TaskName $TaskName -InputObject $Task | Out-Null
$Descriptor.status='REGISTERED_NOT_EXECUTED'
$Descriptor | ConvertTo-Json
