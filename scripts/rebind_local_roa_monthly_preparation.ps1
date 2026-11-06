param(
    [Parameter(Mandatory=$true)][string]$ConfigPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ConfigSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedTaskSha256,
    [string]$EvidenceDirectory,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$TaskName = 'UsRatchet-ROA-Monthly-Preparation'
$OwnerMarker = 'us_ratchet:roa-monthly-preparation:v1'
$ResolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
if ((Get-FileHash -LiteralPath $ResolvedConfig -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ConfigSha256) { throw 'LAUNCHER_DESCRIPTOR_CHANGED' }
$Descriptor = Get-Content -LiteralPath $ResolvedConfig -Raw | ConvertFrom-Json
$RootPath = [string]$Descriptor.root
$PythonPath = [string]$Descriptor.python_path
if (-not [System.IO.Path]::IsPathRooted($RootPath) -or -not [System.IO.Path]::IsPathRooted($PythonPath)) { throw 'ABSOLUTE_PATHS_REQUIRED' }
$RootPath = (Resolve-Path -LiteralPath $RootPath).Path
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
if ($Descriptor.schema -ne 'ROA_MONTHLY_PREPARATION_LAUNCHER_V1') { throw 'DESCRIPTOR_SCHEMA' }
if (-not $ResolvedConfig.StartsWith($RootPath.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'DESCRIPTOR_OUTSIDE_ROOT' }
$RelativeDescriptor = $ResolvedConfig.Substring($RootPath.Length).TrimStart('\','/')
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
    & $PythonPath -X utf8 -E -B -m scripts.run_local_roa_monthly_preparation --descriptor-path $RelativeDescriptor --descriptor-sha256 $ConfigSha256
    if ($LASTEXITCODE -ne 0) { throw 'LAUNCHER_PREFLIGHT_FAILED' }
} finally { Pop-Location }
$Command = '& ' + (Quote-Literal $PythonPath) + ' -X utf8 -E -B -m scripts.run_local_roa_monthly_preparation --descriptor-path ' + (Quote-Literal $RelativeDescriptor) + ' --descriptor-sha256 ' + (Quote-Literal $ConfigSha256) + ' --execute; exit $LASTEXITCODE'
$Encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
$Executable = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$Arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand ' + $Encoded

function Hash-Text([string]$Text) {
    $Hasher=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($Hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant() }
    finally { $Hasher.Dispose() }
}
function NonAction-Xml([string]$Text) {
    [xml]$Document=$Text
    $Node=$Document.SelectSingleNode("/*[local-name()='Task']/*[local-name()='Actions']")
    if(-not $Node){throw 'TASK_ACTIONS_MISSING'}
    [void]$Node.ParentNode.RemoveChild($Node)
    return $Document.OuterXml
}
$Before=Export-ScheduledTask -TaskName $TaskName
if((Hash-Text $Before) -ne $ExpectedTaskSha256){throw 'EXISTING_TASK_CHANGED'}
$Existing=Get-ScheduledTask -TaskName $TaskName
if($Existing.Description -ne $OwnerMarker){throw 'OWNER_MISMATCH'}
if([string]$Existing.State -eq 'Running'){throw 'TASK_CURRENTLY_RUNNING'}
if(-not $Apply){
    [pscustomobject]@{Status='PREVIEW_ONLY_ACTION_REBIND_NOT_APPLIED';TaskName=$TaskName;ConfigSha256=$ConfigSha256;ExpectedTaskSha256=$ExpectedTaskSha256} | ConvertTo-Json
    return
}
if(-not $EvidenceDirectory){throw 'EVIDENCE_DIRECTORY_REQUIRED'}
$Evidence=[IO.Path]::GetFullPath((Join-Path $RootPath $EvidenceDirectory))
$PrivateRoot=(Join-Path $RootPath 'tmp').TrimEnd('\')+'\'
if(-not $Evidence.StartsWith($PrivateRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'EVIDENCE_MUST_BE_PRIVATE_TMP'}
if(Test-Path -LiteralPath $Evidence){throw 'EVIDENCE_ALREADY_EXISTS_RECONCILE'}
New-Item -ItemType Directory -Path $Evidence | Out-Null
[IO.File]::WriteAllText((Join-Path $Evidence 'task-before.xml'),$Before,[Text.UTF8Encoding]::new($false))
$Action=New-ScheduledTaskAction -Execute $Executable -Argument $Arguments -WorkingDirectory $RootPath
# Recheck both task identity and descriptor immediately before changing only Action.
if((Hash-Text (Export-ScheduledTask -TaskName $TaskName)) -ne $ExpectedTaskSha256){throw 'TASK_CHANGED_BEFORE_UPDATE'}
if([string](Get-ScheduledTask -TaskName $TaskName).State -eq 'Running'){throw 'TASK_STARTED_BEFORE_UPDATE'}
if((Get-FileHash -LiteralPath $ResolvedConfig).Hash.ToLowerInvariant() -ne $ConfigSha256){throw 'DESCRIPTOR_CHANGED_BEFORE_UPDATE'}
Push-Location -LiteralPath $RootPath
try {
    & $PythonPath -X utf8 -E -B -m scripts.run_local_roa_monthly_preparation --descriptor-path $RelativeDescriptor --descriptor-sha256 $ConfigSha256
    if($LASTEXITCODE -ne 0){throw 'FINAL_PREFLIGHT_FAILED'}
} finally {Pop-Location}
if((Hash-Text (Export-ScheduledTask -TaskName $TaskName)) -ne $ExpectedTaskSha256 -or [string](Get-ScheduledTask -TaskName $TaskName).State -eq 'Running'){throw 'TASK_CHANGED_DURING_PREFLIGHT'}
Set-ScheduledTask -TaskName $TaskName -Action $Action | Out-Null
$After=Export-ScheduledTask -TaskName $TaskName
[IO.File]::WriteAllText((Join-Path $Evidence 'task-after.xml'),$After,[Text.UTF8Encoding]::new($false))
if((NonAction-Xml $Before) -ne (NonAction-Xml $After)){throw 'NON_ACTION_TASK_FIELDS_CHANGED_REVIEW_REQUIRED'}
$Updated=Get-ScheduledTask -TaskName $TaskName
if($Updated.Actions.Count -ne 1 -or $Updated.Actions[0].Execute -ne $Executable -or $Updated.Actions[0].Arguments -ne $Arguments -or $Updated.Actions[0].WorkingDirectory -ne $RootPath){throw 'TASK_ACTION_READBACK_MISMATCH'}
$Receipt=[pscustomobject]@{Status='ACTION_REBOUND_NO_TASK_STARTED';TaskName=$TaskName;ConfigSha256=$ConfigSha256;BeforeSha256=$ExpectedTaskSha256;AfterSha256=(Hash-Text $After);NonActionFieldsUnchanged=$true}
$Receipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Evidence 'success.json') -Encoding UTF8
$Receipt | ConvertTo-Json
