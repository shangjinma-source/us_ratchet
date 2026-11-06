param(
    [Parameter(Mandatory=$true)][string]$ManifestPath,
    [Parameter(Mandatory=$true)][string]$ManifestSha256
)
$ErrorActionPreference='Stop'
if((Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ManifestSha256){throw 'HANDOFF_MANIFEST_CHANGED'}
$Manifest=Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$Root=(Resolve-Path -LiteralPath $Manifest.root).Path
foreach($Pin in $Manifest.source_pins.PSObject.Properties){
    if([IO.Path]::IsPathRooted($Pin.Name) -or ($Pin.Name -split '[\\/]') -contains '..'){throw 'SOURCE_PATH_INVALID'}
    $Source=Join-Path $Root $Pin.Name
    if((Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Pin.Value){throw ('SOURCE_CHANGED:'+ $Pin.Name)}
}
$Logs=Join-Path $Root $Manifest.log_directory
if([IO.Path]::IsPathRooted($Manifest.log_directory) -or ($Manifest.log_directory -split '[\\/]') -contains '..'){throw 'LOG_PATH_INVALID'}
New-Item -ItemType Directory -Path $Logs -Force | Out-Null
$RunId=[guid]::NewGuid().ToString('N')
Push-Location -LiteralPath $Root
try{
    $Output=& $Manifest.python_path -X utf8 -E -B -m scripts.research.build_roa_monthly_adoption_request --descriptor-path $Manifest.descriptor.path --descriptor-sha256 $Manifest.descriptor.sha256 --handoff-directory $Manifest.state_directory --follow --execute 2>&1
    $Code=$LASTEXITCODE
    $Text=($Output | Out-String)
    [IO.File]::WriteAllText((Join-Path $Logs ($RunId+'.log')),$Text)
    if($Code -ne 0){throw ('HANDOFF_FAILED_SEE_LOCAL_LOG:'+ $RunId)}
    $Result=$Text | ConvertFrom-Json
    if($Result.status -notin @('WAIT_PREPARED_MONTH','MONTH_RUNTIME_AND_NEXT_TASK_VERIFIED')){
        throw ('HANDOFF_REVIEW_REQUIRED:'+ $Result.status)
    }
    $Result | ConvertTo-Json -Depth 20
}finally{Pop-Location}
