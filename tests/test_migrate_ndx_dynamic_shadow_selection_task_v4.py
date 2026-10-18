"""Offline PowerShell contract tests: no real scheduler operations are invoked."""
import base64
import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/migrate_ndx_dynamic_shadow_selection_task_v4.ps1'

XML = r'''<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><RegistrationInfo><URI>\old</URI></RegistrationInfo><Triggers><CalendarTrigger><StartBoundary>2026-09-01T11:20:00</StartBoundary><Enabled>true</Enabled><ScheduleByWeek><WeeksInterval>1</WeeksInterval><DaysOfWeek><Tuesday/><Wednesday/><Thursday/><Friday/><Saturday/></DaysOfWeek></ScheduleByWeek></CalendarTrigger></Triggers><Principals><Principal id="Author"><UserId>fixture-user</UserId><LogonType>InteractiveToken</LogonType></Principal></Principals><Settings><Enabled>true</Enabled><StartWhenAvailable>true</StartWhenAvailable><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><ExecutionTimeLimit>PT11H</ExecutionTimeLimit><RestartOnFailure><Interval>PT10M</Interval><Count>3</Count></RestartOnFailure></Settings><Actions Context="Author"><Exec><Command>D:\python\python.exe</Command><Arguments>-B "E:\Git\us_ratchet\scripts\ndx_dynamic_shadow_daily_v3.py" --execute</Arguments><WorkingDirectory>E:\Git\us_ratchet</WorkingDirectory></Exec></Actions></Task>'''

class InstallerTests(unittest.TestCase):
    def ps(self, body, shell='powershell'):
        executable = shutil.which(shell)
        if not executable:
            self.skipTest(f'{shell} unavailable')
        encoded_xml = base64.b64encode(XML.encode()).decode()
        source = f". '{SCRIPT}' -InternalFunctionTest\n$baseline=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_xml}'))\n$marker='us_ratchet_v4_attempt:' + ('a'*32)\n" + body
        result = subprocess.run([executable, '-NoProfile', '-NonInteractive', '-EncodedCommand', base64.b64encode(source.encode('utf-16-le')).decode()], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_definition_round_trip(self):
        self.ps("$new=New-DisabledV4Xml $baseline $marker; Assert-NewDefinition $baseline $new $false $marker")

    def test_windows_export_omitted_enabled_defaults(self):
        self.ps("""
$baseline=$baseline.Replace('<Enabled>true</Enabled>','')
Assert-WeeklyDefinition $baseline $dailyOld $true
$new=New-DisabledV4Xml $baseline $marker
Assert-NewDefinition $baseline $new $false $marker
$enabled=$new.Replace('<Enabled>false</Enabled>','').Replace('<Enabled>true</Enabled>','')
Assert-NewDefinition $baseline $enabled $true $marker
$invalid=$new.Replace('<Enabled>false</Enabled>','<Enabled>false</Enabled><Enabled>true</Enabled>')
$rejected=$false; try{Assert-NewDefinition $baseline $invalid $false $marker}catch{$rejected=$true}
if(-not $rejected){throw 'duplicate Enabled accepted'}
""")

    def test_extra_action_and_changed_principal_rejected(self):
        self.ps("""
foreach($kind in @('action','principal','owner')) {
 $new=New-DisabledV4Xml $baseline $marker
 if($kind -eq 'action') {$new=$new.Replace('</Exec>','</Exec><Exec/>')}
 if($kind -eq 'principal') {$new=$new.Replace('fixture-user','intruder')}
 if($kind -eq 'owner') {$new=$new.Replace($marker,'foreign-owner')}
 $rejected=$false; try {Assert-NewDefinition $baseline $new $false $marker} catch {$rejected=$true}
 if(-not $rejected){throw "accepted $kind"}
}
""")

    def test_acknowledgements_and_independent_hash_required(self):
        self.ps("""
$rejected=$false; try {Assert-ApplyAuthorization} catch {$rejected=$true}; if(-not $rejected){throw 'missing flags accepted'}
$AcknowledgeExplicitUserApproval=$true; $AcknowledgeResearchOnlyNoLiveMutation=$true
$ExpectedReviewSha256='a'*64; Assert-ApplyAuthorization
""")

    def test_foreign_collision_never_mutated(self):
        self.ps("""
$foreign=New-DisabledV4Xml $baseline ('us_ratchet_v4_attempt:'+('b'*32))
function Get-TaskRecord {return @{xml=$foreign;state='Disabled'}}
function Disable-ScheduledTask {throw 'MUTATION'}
function Stop-ScheduledTask {throw 'MUTATION'}
function Enable-ScheduledTask {throw 'MUTATION'}
$result=Invoke-FailSafeRollback $true $true $baseline $marker
if($result.new_task_secured -or $result.old_v3_restored -or ($result.errors -join '') -match 'MUTATION'){throw 'foreign task touched'}
""")

    def test_rollback_before_old_disable_leaves_old_alone(self):
        self.ps("""
$new=New-DisabledV4Xml $baseline $marker
$script:events=@()
function Get-TaskRecord {return @{xml=$new;state='Disabled'}}
function Disable-ScheduledTask {$script:events+='disable'}
function Stop-ScheduledTask {$script:events+='stop'}
function Enable-ScheduledTask {throw 'old must not be enabled'}
function Assert-Exclusive($Allowed) {if($Allowed -cne $oldName){throw 'untouched old must remain allowed'}}
$result=Invoke-FailSafeRollback $true $false $baseline $marker
if(-not $result.new_task_secured -or -not $result.old_v3_restored -or ($script:events -join ',') -cne 'disable,stop'){throw 'rollback failed'}
""")

    def test_changed_old_definition_not_restored(self):
        self.ps("""
$changed=$baseline.Replace('fixture-user','intruder').Replace('<Enabled>true</Enabled><StartWhenAvailable>','<Enabled>false</Enabled><StartWhenAvailable>')
function Get-TaskRecord {return @{xml=$changed;state='Disabled'}}
function Enable-ScheduledTask {throw 'MUTATION'}
$result=Invoke-FailSafeRollback $false $true $baseline $marker
if($result.old_v3_restored -or ($result.errors -join '') -match 'MUTATION'){throw 'modified old restored'}
""")

    def test_owned_new_secured_before_old_restored(self):
        self.ps("""
$new=New-DisabledV4Xml $baseline $marker
$oldDisabled=$baseline.Replace('<Enabled>true</Enabled><StartWhenAvailable>','<Enabled>false</Enabled><StartWhenAvailable>')
$script:restored=$false; $script:events=@()
function Get-TaskRecord($Name) {
 if($Name -ceq $newName){return @{xml=$new;state='Disabled'}}
 if($script:restored){return @{xml=$baseline;state='Ready'}}
 return @{xml=$oldDisabled;state='Disabled'}
}
function Disable-ScheduledTask {$script:events+='disable-new'}
function Stop-ScheduledTask {$script:events+='stop-new'}
function Assert-Exclusive($Allowed) {if($Allowed -cne ''){throw 'both disabled expected'}; $script:events+='idle-proven'}
function Enable-ScheduledTask {$script:events+='enable-old'; $script:restored=$true}
$result=Invoke-FailSafeRollback $true $true $baseline $marker
if(-not $result.new_task_secured -or -not $result.old_v3_restored -or ($script:events -join ',') -cne 'disable-new,stop-new,idle-proven,enable-old'){throw 'unsafe rollback order'}
""")

    def test_crosses_next_full_second(self):
        self.ps("""
$script:now=[datetime]::Parse('2026-09-11T00:00:00.200Z').ToUniversalTime(); $script:sleeps=0
function Get-UtcNow {return $script:now}
function Start-Sleep {param($Milliseconds); if($Milliseconds -gt 100){throw 'unbounded sleep'}; $script:now=$script:now.AddMilliseconds($Milliseconds); $script:sleeps++}
Wait-NextTaskSecond '2026-09-11T00:00:00.200Z'
if($script:now.Second -ne 1 -or $script:sleeps -eq 0){throw 'did not cross boundary'}
""")

    def test_json_timestamp_stays_string_both_shells(self):
        for shell in ('powershell', 'pwsh'):
            with self.subTest(shell=shell):
                self.ps("$value=Convert-EvidenceJson '{\"captured_at_utc\":\"2026-09-11T01:02:03.123456+00:00\"}'; if($value.captured_at_utc -isnot [string] -or $value.captured_at_utc -cne '2026-09-11T01:02:03.123456+00:00'){throw 'timestamp changed'}", shell)

    def test_wrong_timezone_rejected(self):
        self.ps("function Get-TimeZone {return @{Id='UTC'}}; $rejected=$false; try{Assert-BeijingTimezone}catch{$rejected=$true}; if(-not $rejected){throw 'wrong clock accepted'}")

    def test_no_force_or_delete_and_real_task_evidence(self):
        source = SCRIPT.read_text(encoding='utf-8')
        self.assertNotIn('Unregister-ScheduledTask', source)
        self.assertNotIn('-Force', source)
        self.assertIn("@('--verify','--before-path',$beforePath)", source)
        self.assertIn('UtcNow.AddHours(11)', source)

    def test_attempt_ownership_is_persisted_before_registration(self):
        source = SCRIPT.read_text(encoding='utf-8')
        creation = source.index("$ownershipMarker = 'us_ratchet_v4_attempt:'")
        before_write = source.index("Write-ImmutableJson (Join-Path $attempt 'pre_cutover.json')")
        registration = source.index('Register-ScheduledTask -TaskPath')
        self.assertLess(creation, before_write)
        self.assertLess(before_write, registration)
        self.assertIn('ownership_marker=$ownershipMarker', source[before_write:registration])

if __name__ == '__main__':
    unittest.main()
