param(
    [Parameter(Mandatory=$true)][string]$ConfigPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ConfigSha256,
    [switch]$Install
)
$ErrorActionPreference = 'Stop'
$TaskName = 'UsRatchet-RealMonthly-Update'
$OwnerMarker = 'us_ratchet:real-monthly-local:v1'
$ResolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
if ((Get-FileHash -LiteralPath $ResolvedConfig -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ConfigSha256) { throw 'LAUNCHER_DESCRIPTOR_CHANGED' }
$Descriptor = Get-Content -LiteralPath $ResolvedConfig -Raw | ConvertFrom-Json
$RootPath = [string]$Descriptor.root
$PythonPath = [string]$Descriptor.python_path
if (-not [System.IO.Path]::IsPathRooted($RootPath) -or -not [System.IO.Path]::IsPathRooted($PythonPath)) { throw 'ABSOLUTE_PATHS_REQUIRED' }
$RootPath = (Resolve-Path -LiteralPath $RootPath).Path
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
# Validate the descriptor's approved source closure before importing Python code.
foreach ($Pin in $Descriptor.source_pins.PSObject.Properties) {
    if ([System.IO.Path]::IsPathRooted($Pin.Name) -or ($Pin.Name -split '[\\/]') -contains '..') { throw 'SOURCE_PIN_PATH_INVALID' }
    $SourcePath = Join-Path $RootPath $Pin.Name
    if ((Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Pin.Value) { throw 'SOURCE_PIN_CHANGED' }
}
# Single-quote escaping is PowerShell literal escaping; no string-built shell IO.
function Quote-Literal([string]$Value) { return "'" + $Value.Replace("'", "''") + "'" }
Push-Location -LiteralPath $RootPath
try {
    & $PythonPath -X utf8 -E -B -m scripts.run_local_real_monthly_update --config-path $ResolvedConfig --config-sha256 $ConfigSha256
    if ($LASTEXITCODE -ne 0) { throw 'LAUNCHER_PREFLIGHT_FAILED' }
} finally { Pop-Location }
$Command = '& ' + (Quote-Literal $PythonPath) + ' -X utf8 -E -B -m scripts.run_local_real_monthly_update --config-path ' + (Quote-Literal $ResolvedConfig) + ' --config-sha256 ' + (Quote-Literal $ConfigSha256) + ' --execute; exit $LASTEXITCODE'
$Encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
$Executable = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$Arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand ' + $Encoded
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$CurrentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    $ExistingSid = ([System.Security.Principal.NTAccount]::new($Existing.Principal.UserId)).Translate([System.Security.Principal.SecurityIdentifier]).Value
    if ($Existing.Description -ne $OwnerMarker -or $Existing.Actions.Count -ne 1 -or
        $Existing.Actions[0].Execute -ne $Executable -or $Existing.Actions[0].Arguments -ne $Arguments -or
        $Existing.Actions[0].WorkingDirectory -ne $RootPath -or $ExistingSid -ne $CurrentSid -or
        $Existing.Triggers.Count -ne 1 -or $Existing.Triggers[0].Repetition.Interval -ne 'PT15M' -or
        [string]$Existing.Settings.MultipleInstances -ne 'IgnoreNew' -or -not $Existing.Settings.StartWhenAvailable -or
        $Existing.Settings.ExecutionTimeLimit -ne 'PT3H') {
        throw 'EXISTING_TASK_CONFIGURATION_CONFLICT'
    }
    Write-Output 'EXISTING_MATCHING_TASK_NO_CHANGE'
    return
}
# Interval triggers cover every timezone/DST; the Python pinned calendar owns timing.
if (-not $Install) {
    [pscustomobject]@{ Status='PREVIEW_ONLY_NO_TASK_REGISTERED'; TaskName=$TaskName;
        Executable=$Executable; Arguments=$Arguments; WorkingDirectory=$RootPath;
        Interval='Every 15 minutes, continuously'; StartWhenAvailable=$true;
        MultipleInstances='IgnoreNew'; WindowStyle='Hidden'; LogonType='Interactive';
        ExecutionTimeLimit='PT3H'; ConfigPath=$ResolvedConfig; ConfigSha256=$ConfigSha256 } | ConvertTo-Json
    return
}
$Action = New-ScheduledTaskAction -Execute $Executable -Argument $Arguments -WorkingDirectory $RootPath
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$Principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited
$Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description $OwnerMarker
Register-ScheduledTask -TaskName $TaskName -InputObject $Task | Out-Null
Write-Output 'REGISTERED_REAL_MONTHLY_ONLY'
