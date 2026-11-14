$ErrorActionPreference='Stop'
$Root='E:\Git\us_ratchet'
$LogRoot=Join-Path $Root 'outputs\service_logs'
New-Item -ItemType Directory -Force $LogRoot | Out-Null
$Stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$Log=Join-Path $LogRoot "scheduled_start_$Stamp.log"
try {
 & (Join-Path $Root 'start_service.ps1') -ProjectRoot $Root *>&1 | Out-File -LiteralPath $Log -Encoding utf8
 if($LASTEXITCODE -ne 0){throw "LAUNCHER_EXIT_$LASTEXITCODE"}
 $Deadline=(Get-Date).AddMinutes(10)
 do {
  try {
   $HomepageResponse=Invoke-WebRequest 'http://127.0.0.1:8010/' -UseBasicParsing -TimeoutSec 5
   $Config=Invoke-RestMethod 'http://127.0.0.1:8010/api/strategy-roa/config' -TimeoutSec 5
   if($HomepageResponse.StatusCode -eq 200 -and $Config.active -eq $true -and $Config.strategy_kind -eq 'ROA_DEFENSIVE_V1') {
    "$(Get-Date -Format o) RESULT=ready HOME=200 ROA_ACTIVE=true" | Add-Content -LiteralPath $Log
    exit 0
   }
   $Pending = [ordered]@{
    home_status = $HomepageResponse.StatusCode
    active_is_true = ($Config.active -eq $true)
    strategy_kind_matches = ($Config.strategy_kind -eq 'ROA_DEFENSIVE_V1')
   } | ConvertTo-Json -Compress
   "$(Get-Date -Format o) READINESS_PENDING=$Pending" | Add-Content -LiteralPath $Log
  } catch { "$(Get-Date -Format o) READINESS_RETRY=$($_.Exception.Message)" | Add-Content -LiteralPath $Log }
  Start-Sleep -Seconds 15
 } while((Get-Date) -lt $Deadline)
 throw 'READINESS_TIMEOUT_PROCESS_NOT_RESTARTED'
} catch {
 "$(Get-Date -Format o) RESULT=failed ERROR=$($_.Exception.Message)" | Add-Content -LiteralPath $Log
 exit 1
}
