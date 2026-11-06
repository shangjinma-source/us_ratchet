param([Parameter(Mandatory=$true)][string]$ConfigPath,[Parameter(Mandatory=$true)][string]$ConfigSha256)
$ErrorActionPreference='Stop'
$global:RoaMockTaskXml='<Task><Triggers><CalendarTrigger /></Triggers><Actions><Exec><Command>old</Command></Exec></Actions></Task>'
$global:RoaMockAction=[pscustomobject]@{Execute='old';Arguments='old';WorkingDirectory='old'}
$global:RoaMockWrites=0
function Export-ScheduledTask {param($TaskName) return $global:RoaMockTaskXml}
function Get-ScheduledTask {param($TaskName) return [pscustomobject]@{State='Ready';Description='us_ratchet:roa-monthly-preparation:v1';Actions=@($global:RoaMockAction)}}
function New-ScheduledTaskAction {param($Execute,$Argument,$WorkingDirectory) return [pscustomobject]@{Execute=$Execute;Arguments=$Argument;WorkingDirectory=$WorkingDirectory}}
function Set-ScheduledTask {param($TaskName,$Action) $global:RoaMockWrites++;$global:RoaMockAction=$Action;$global:RoaMockTaskXml='<Task><Triggers><CalendarTrigger /></Triggers><Actions><Exec><Command>new</Command></Exec></Actions></Task>'}
$hash=[Security.Cryptography.SHA256]::Create()
$digest=([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($global:RoaMockTaskXml)))).Replace('-','').ToLowerInvariant();$hash.Dispose()
$evidence='tmp/rebind-isolated-'+[guid]::NewGuid().ToString('N')
& "$PSScriptRoot/../scripts/rebind_local_roa_monthly_preparation.ps1" -ConfigPath $ConfigPath -ConfigSha256 $ConfigSha256 -ExpectedTaskSha256 $digest -EvidenceDirectory $evidence -Apply
if($global:RoaMockWrites -ne 1){throw 'EXPECTED_ONE_FAKE_WRITE'}
$receipt=Get-Content "$PSScriptRoot/../$evidence/success.json" -Raw | ConvertFrom-Json
if($receipt.Status -ne 'ACTION_REBOUND_NO_TASK_STARTED' -or -not $receipt.NonActionFieldsUnchanged){throw 'SUCCESS_NOT_VERIFIED'}
$rejected=$false
try { & "$PSScriptRoot/../scripts/rebind_local_roa_monthly_preparation.ps1" -ConfigPath $ConfigPath -ConfigSha256 $ConfigSha256 -ExpectedTaskSha256 $digest -Apply -EvidenceDirectory ($evidence+'-retry') } catch {if($_.Exception.Message -ne 'EXISTING_TASK_CHANGED'){throw};$rejected=$true}
if(-not $rejected -or $global:RoaMockWrites -ne 1){throw 'STALE_TASK_NOT_REFUSED'}
'PASS: fake Action-only update and stale task rejection; real descriptor preflight; no Windows task changes'

