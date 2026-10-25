$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$LogDirectory = Join-Path $ProjectRoot 'data\strategy_advice_followup\runner_v1\launcher_logs'
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$RunId = [guid]::NewGuid().ToString('N')
$OutputPath = Join-Path $LogDirectory ($RunId + '.stdout.json')
$ErrorPath = Join-Path $LogDirectory ($RunId + '.stderr.txt')
Push-Location -LiteralPath $ProjectRoot
try {
    & 'D:\python\python.exe' -X utf8 -E -B -m scripts.run_current_daily_followups_v2 --root $ProjectRoot --execute 1> $OutputPath 2> $ErrorPath
    $RunExitCode = $LASTEXITCODE
    [ordered]@{ finished_at=(Get-Date).ToUniversalTime().ToString('o'); exit_code=$RunExitCode; stdout=$OutputPath; stderr=$ErrorPath } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $LogDirectory ($RunId + '.receipt.json')) -Encoding UTF8
} finally { Pop-Location }
exit $RunExitCode
