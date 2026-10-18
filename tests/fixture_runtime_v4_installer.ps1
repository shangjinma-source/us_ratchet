param([string]$FixtureRoot,[string]$Scenario)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$global:ratchetFixture_fixtureRoot=$FixtureRoot
$global:ratchetFixture_scenario=$Scenario
$global:ratchetFixture_calls=[Collections.Generic.List[string]]::new()
$global:ratchetFixture_tasks=@{}
$global:ratchetFixture_v3='us_ratchet_ndx_dynamic_shadow_selection_daily_v3_reviewed_calendar'
$global:ratchetFixture_v4='us_ratchet_ndx_dynamic_shadow_selection_daily_v4_accepted_receipts'
$global:ratchetFixture_jobsPath=Join-Path ([Environment]::GetFolderPath('UserProfile')) '.openclaw\cron\jobs.json'
function Get-Content {
 param($LiteralPath,[switch]$Raw,$Encoding)
 if($LiteralPath -ceq $global:ratchetFixture_jobsPath){return '{"jobs":[]}'}
 if(-not ([IO.Path]::GetFullPath($LiteralPath).StartsWith($global:ratchetFixture_fixtureRoot+'\'))){throw 'read outside fixture'}
 return Microsoft.PowerShell.Management\Get-Content -LiteralPath $LiteralPath -Raw -Encoding UTF8
}
function Get-FileHash {
 param($LiteralPath,$Algorithm)
 if($LiteralPath -ceq $global:ratchetFixture_jobsPath){return @{Hash=('a'*64)}}
 if(-not ([IO.Path]::GetFullPath($LiteralPath).StartsWith($global:ratchetFixture_fixtureRoot+'\'))){throw 'hash outside fixture'}
 $hasher=[Security.Cryptography.SHA256]::Create()
 try {return @{Hash=([BitConverter]::ToString($hasher.ComputeHash([IO.File]::ReadAllBytes($LiteralPath))).Replace('-',''))}} finally {$hasher.Dispose()}
}
function Set-FixtureEnabled($Name,$Enabled) {
 [xml]$x=$global:ratchetFixture_tasks[$Name].Xml
 if($null -eq $x.Task.Settings.SelectSingleNode('*[local-name()="Enabled"]')) {
  $node=$x.CreateElement('Enabled',$x.DocumentElement.NamespaceURI)
  $x.Task.Settings.AppendChild($node) | Out-Null
 }
 $x.Task.Settings.Enabled=$Enabled.ToString().ToLowerInvariant()
 $global:ratchetFixture_tasks[$Name].Xml=$x.OuterXml
 $global:ratchetFixture_tasks[$Name].State=if($Enabled){'Ready'}else{'Disabled'}
}
function Assert-FixtureTarget($TaskName,$TaskPath) {
 if($TaskPath -cne '\' -or $TaskName -cnotin @($global:ratchetFixture_v3,$global:ratchetFixture_v4)){throw 'unsupported mutation target'}
}
function Get-ScheduledTask {param($ErrorAction); return @($global:ratchetFixture_tasks.Values)}
function Get-ScheduledTaskInfo {param($TaskName,$TaskPath,$ErrorAction); if(-not $global:ratchetFixture_tasks.ContainsKey($TaskName)){throw 'unknown task'}; return @{LastRunTime=$global:ratchetFixture_tasks[$TaskName].Last;LastTaskResult=0}}
function Export-ScheduledTask {
 param($TaskName,$TaskPath)
 if(-not $global:ratchetFixture_tasks.ContainsKey($TaskName)){throw 'unknown task'}
 $exported=$global:ratchetFixture_tasks[$TaskName].Xml
 if($global:ratchetFixture_scenario -ceq 'omitted_enabled') {
  # Windows may omit schema-default true on every export, including new v4.
  $exported=$exported.Replace('<Enabled>true</Enabled>','')
  if($TaskName -ceq $global:ratchetFixture_v4 -and $global:ratchetFixture_tasks[$TaskName].State -ceq 'Ready') {
   $global:ratchetFixture_newDefaultExports++
  }
 }
 return $exported
}
function Register-ScheduledTask {
 param($TaskName,$TaskPath,$Xml,$ErrorAction)
 Assert-FixtureTarget $TaskName $TaskPath
 if($TaskName -cne $global:ratchetFixture_v4 -or $global:ratchetFixture_tasks.ContainsKey($TaskName)){throw 'unexpected register'}
 $global:ratchetFixture_calls.Add('register')
 if($global:ratchetFixture_scenario -ceq 'register_before'){throw 'register rejected'}
 if($global:ratchetFixture_scenario -ceq 'collision'){$Xml=$Xml -replace 'us_ratchet_v4_attempt:[a-f0-9]{32}','foreign-owner'}
 $global:ratchetFixture_tasks[$TaskName]=@{TaskName=$TaskName;TaskPath='\';State='Disabled';Xml=$Xml;Last=[datetime]'2000-01-01';Actions=@(@{Execute='D:\python\python.exe';Arguments='ndx_dynamic_shadow_daily_v4.py'})}
 if($global:ratchetFixture_scenario -cin @('register_after','collision')){throw 'register response uncertain'}
 if($global:ratchetFixture_scenario -ceq 'old_drift'){$global:ratchetFixture_tasks[$global:ratchetFixture_v3].Xml=$global:ratchetFixture_tasks[$global:ratchetFixture_v3].Xml.Replace('fixture-user','changed-user')}
}
function Disable-ScheduledTask {param($TaskName,$TaskPath,$ErrorAction); Assert-FixtureTarget $TaskName $TaskPath; $global:ratchetFixture_calls.Add('disable:'+ $TaskName); Set-FixtureEnabled $TaskName $false}
function Enable-ScheduledTask {
 param($TaskName,$TaskPath,$ErrorAction); Assert-FixtureTarget $TaskName $TaskPath
 $global:ratchetFixture_calls.Add('enable:'+ $TaskName)
 if($global:ratchetFixture_scenario -ceq 'enable_fail' -and $TaskName -ceq $global:ratchetFixture_v4){throw 'enable rejected'}
 Set-FixtureEnabled $TaskName $true
 if($global:ratchetFixture_scenario -ceq 'owner_replaced' -and $TaskName -ceq $global:ratchetFixture_v4){$global:ratchetFixture_tasks[$TaskName].Xml=$global:ratchetFixture_tasks[$TaskName].Xml -replace 'us_ratchet_v4_attempt:[a-f0-9]{32}','foreign-owner'}
}
function Stop-ScheduledTask {param($TaskName,$TaskPath,$ErrorAction); Assert-FixtureTarget $TaskName $TaskPath; $global:ratchetFixture_calls.Add('stop:'+ $TaskName)}
function Start-ScheduledTask {
 param($TaskName,$TaskPath,$ErrorAction); Assert-FixtureTarget $TaskName $TaskPath
 if($TaskName -cne $global:ratchetFixture_v4){throw 'unexpected start'}
 $global:ratchetFixture_calls.Add('start:'+ $TaskName)
 if($global:ratchetFixture_scenario -ceq 'start_fail'){throw 'start rejected'}
 $global:ratchetFixture_tasks[$TaskName].Last=[datetime]::Now
}
function Get-CimInstance {param($ClassName,$ErrorAction); if($ClassName -cne 'Win32_Process'){throw 'unsupported CIM'}; return @()}
function Get-TimeZone {return @{Id='China Standard Time'}}
$baseline=[IO.File]::ReadAllText((Join-Path $FixtureRoot 'baseline.xml'))
foreach($name in @('us_ratchet_ndx_dynamic_shadow_selection_daily','us_ratchet_ndx_dynamic_shadow_selection_daily_v2_budgeted',$global:ratchetFixture_v3)) {
 $global:ratchetFixture_tasks[$name]=@{TaskName=$name;TaskPath='\';State='Ready';Xml=$baseline;Last=[datetime]'2000-01-01';Actions=@(@{Execute='D:\python\python.exe';Arguments='ndx_dynamic_shadow_daily_v3.py'})}
 if($name -cne $global:ratchetFixture_v3){Set-FixtureEnabled $name $false}
}
# Every potentially mutating command must resolve to this fixture, never a cmdlet.
foreach($name in @('Register-ScheduledTask','Disable-ScheduledTask','Enable-ScheduledTask','Stop-ScheduledTask','Start-ScheduledTask')) {
 $command=Get-Command $name
 if($command.CommandType -ne 'Function' -or $command.ScriptBlock.File -cne $PSCommandPath){throw 'unsafe shim resolution'}
}
$failed=$false
$global:ratchetFixture_newDefaultExports=0
$failure=''
try { & (Join-Path $FixtureRoot 'scripts\migrate_ndx_dynamic_shadow_selection_task_v4.ps1') -ProjectRoot $FixtureRoot -Apply -AcknowledgeExplicitUserApproval -AcknowledgeResearchOnlyNoLiveMutation -ExpectedReviewSha256 ('a'*64) | Out-Null } catch {$failed=$true; $failure=$_.Exception.Message}
@{failed=$failed;failure=$failure;calls=@($global:ratchetFixture_calls);tasks=$global:ratchetFixture_tasks;new_default_exports=$global:ratchetFixture_newDefaultExports} | ConvertTo-Json -Depth 30 -Compress
