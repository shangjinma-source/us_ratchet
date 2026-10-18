[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$TaskName = "us_ratchet_service_at_logon",
    [switch]$Apply,
    [switch]$AcknowledgeExternalSchedulerDisabled
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$resolvedRoot = if ($ProjectRoot) {
    (Resolve-Path -LiteralPath $ProjectRoot).Path
} else {
    (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}
$startScript = Join-Path $resolvedRoot "start_service.ps1"
if (-not (Test-Path -LiteralPath $startScript -PathType Leaf)) {
    throw "start_service.ps1 not found: $startScript"
}

$windowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path -LiteralPath $windowsPowerShell -PathType Leaf)) {
    throw "Windows PowerShell not found: $windowsPowerShell"
}
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$actionArguments = (
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -ProjectRoot "{1}"' -f
    $startScript, $resolvedRoot
)

$plan = [ordered]@{
    schema_version = 1
    mode = if ($Apply) { "APPLY_REQUESTED" } else { "PLAN_ONLY" }
    task_name = $TaskName
    principal = $currentUser
    trigger = "AT_LOGON"
    executable = $windowsPowerShell
    arguments = $actionArguments
    health_check = "delegated_to_start_service.ps1_root_and_openapi"
    start_when_available = $true
    restart_count = 3
    restart_interval_minutes = 1
    multiple_instances = "IGNORE_NEW"
    external_scheduler_guard = "OpenClaw/Codex duplicate startup must be disabled before apply"
    state_or_order_write = $false
}

$plan | ConvertTo-Json -Depth 4
if (-not $Apply) {
    Write-Output "RESULT=plan_only"
    exit 0
}
if (-not $AcknowledgeExternalSchedulerDisabled) {
    throw (
        "Refusing to register a duplicate scheduler. Disable the matching OpenClaw/Codex " +
        "startup job, then rerun with -Apply -AcknowledgeExternalSchedulerDisabled."
    )
}

$action = New-ScheduledTaskAction -Execute $windowsPowerShell -Argument $actionArguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Start us_ratchet after Windows sign-in; start_service.ps1 verifies root and OpenAPI health." `
    -Force | Out-Null

Write-Output "RESULT=registered"
Write-Output "TASK_NAME=$TaskName"

