param(
    [Parameter(Mandatory=$true)][string]$ConfigPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ConfigSha256,
    [switch]$Execute
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$ResolvedConfig = $ConfigPath
$DiagnosticRoot = Join-Path $ProjectRoot 'data/local_scheduler/dynamic-daily-source'
$StartedAt = [DateTimeOffset]::UtcNow
$InvocationId = [Guid]::NewGuid().ToString('N')
New-Item -ItemType Directory -Path $DiagnosticRoot -Force | Out-Null
$OutputPath = Join-Path $DiagnosticRoot ($InvocationId + '.stdout.txt')
$ErrorPath = Join-Path $DiagnosticRoot ($InvocationId + '.stderr.txt')
New-Item -ItemType File -Path $OutputPath,$ErrorPath | Out-Null
$ExitStatus = 1
$Result = $null
Push-Location -LiteralPath $ProjectRoot
try {
    # Use this host's module, even when a parent process supplied PS7 module paths.
    Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1') -Force
    $ResolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
    if ((Get-FileHash -LiteralPath $ResolvedConfig -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ConfigSha256) {
        throw 'DAILY_PIPELINE_CONFIGURATION_CHANGED'
    }
    $Configuration = Get-Content -LiteralPath $ResolvedConfig -Raw | ConvertFrom-Json
    $LauncherPins = @($Configuration.source_pins | Where-Object { $_.path -eq 'scripts/run_local_dynamic_daily_sources.ps1' })
    if ($LauncherPins.Count -ne 1) {
        throw 'DYNAMIC_SOURCE_LAUNCHER_PIN_REQUIRED'
    }
    foreach ($Pin in $Configuration.source_pins) {
        if ([System.IO.Path]::IsPathRooted($Pin.path) -or ($Pin.path -split '[\\/]') -contains '..') {
            throw 'DAILY_SOURCE_PATH_INVALID'
        }
        if ((Get-FileHash -LiteralPath (Join-Path $ProjectRoot $Pin.path) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Pin.sha256) {
            throw 'DAILY_SOURCE_CHANGED'
        }
    }
    $PythonArguments = @('-X','utf8','-E','-B','-m','scripts.run_daily_dynamic_source_v1',
        '--root',$ProjectRoot,'--config-path',$ResolvedConfig,'--config-sha256',$ConfigSha256)
    if ($Execute) { $PythonArguments += '--execute' }
    & 'D:/python/python.exe' @PythonArguments 1> $OutputPath 2> $ErrorPath
    $ExitStatus = $LASTEXITCODE
    if ((Get-Item -LiteralPath $OutputPath).Length -eq 0) {
        throw 'DAILY_PIPELINE_RESULT_MISSING'
    }
    if ((Get-Item -LiteralPath $OutputPath).Length -gt 0) {
        $Result = Get-Content -LiteralPath $OutputPath -Raw | ConvertFrom-Json
        if ($null -eq $Result -or [string]::IsNullOrWhiteSpace([string]$Result.status)) {
            throw 'DAILY_PIPELINE_RESULT_MISSING'
        }
        if ($Result.status -eq 'NEEDS_RECOVERY') { $ExitStatus = 3 }
    }
} catch {
    $ExitStatus = 1
    $Result = @{ status='LOCAL_LAUNCHER_FAILED'; reason=$_.Exception.Message }
    $_.Exception.Message | Add-Content -LiteralPath $ErrorPath -Encoding UTF8
} finally {
    Pop-Location
    [ordered]@{
        schema='DYNAMIC_DAILY_SOURCE_LOCAL_INVOCATION_V1'; invocation_id=$InvocationId
        started_at=$StartedAt.ToString('o'); finished_at=[DateTimeOffset]::UtcNow.ToString('o')
        configuration_path=$ResolvedConfig; configuration_sha256=$ConfigSha256
        execute=[bool]$Execute; exit_code=$ExitStatus; result=$Result
        stdout_path=$OutputPath; stderr_path=$ErrorPath
    } | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $DiagnosticRoot ($InvocationId + '.json')) -Encoding UTF8
}
if ($null -ne $Result) { $Result | ConvertTo-Json -Depth 20 }
exit $ExitStatus
