param([switch]$Install)
$ErrorActionPreference = 'Stop'
$RootPath = 'E:\Git\us_ratchet'
$PythonPath = 'D:\python\python.exe'
$TaskName = 'UsRatchet-StrategySimulation-Daily'
$OwnerMarker = 'us_ratchet:quantity-v2-local-daily:v1'
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'EXPECTED_BEIJING_WINDOWS_TIMEZONE' }
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'PYTHON_MISSING' }
Push-Location -LiteralPath $RootPath
try {
    & $PythonPath -X utf8 -E -B -m scripts.run_local_scheduled_simulation
    if ($LASTEXITCODE -ne 0) { throw 'LOCAL_PREFLIGHT_FAILED' }
} finally { Pop-Location }
$Arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -Command "& ''D:\python\python.exe'' -X utf8 -E -B -m scripts.run_local_scheduled_simulation --execute; exit $LASTEXITCODE"'
$Executable = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    try {
        $CurrentOwnerSid = ([System.Security.Principal.NTAccount]::new($UserId)).Translate([System.Security.Principal.SecurityIdentifier]).Value
        $ExistingOwnerSid = ([System.Security.Principal.NTAccount]::new($Existing.Principal.UserId)).Translate([System.Security.Principal.SecurityIdentifier]).Value
    } catch { throw 'EXISTING_TASK_OWNER_IDENTITY_UNRESOLVED' }
    if ($Existing.Description -ne $OwnerMarker -or $Existing.Actions.Count -ne 1 -or
        $Existing.Actions[0].Execute -ne $Executable -or $Existing.Actions[0].Arguments -ne $Arguments -or
        $Existing.Actions[0].WorkingDirectory -ne $RootPath -or $ExistingOwnerSid -ne $CurrentOwnerSid) {
        throw 'EXISTING_TASK_NOT_OWNED_BY_THIS_CONFIGURATION'
    }
}
if (-not $Install) { Write-Output 'PREPARED_ONLY_NO_TASK_REGISTERED'; return }
$Action = New-ScheduledTaskAction -Execute $Executable -Argument $Arguments -WorkingDirectory $RootPath
$Days = @('Monday','Tuesday','Wednesday','Thursday','Friday')
$Triggers = @((New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Days -At '22:00'), (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Days -At '23:00'))
# Delayed launches retain actual time: the Python NY gate skips missed windows.
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 45)
$Principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited
$Task = New-ScheduledTask -Action $Action -Trigger $Triggers -Settings $Settings -Principal $Principal -Description $OwnerMarker
Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force | Out-Null
Write-Output 'REGISTERED_LOCAL_SIMULATION_ONLY'
