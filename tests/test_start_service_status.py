"""Execute real PowerShell startup script with process/network boundaries mocked.
No real service process is started, killed, or contacted.
"""
import unittest,tempfile,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SHELL='C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'

class StartupStatusTests(unittest.TestCase):
    def run_case(self,mode):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            escaped=str(ROOT/'start_service.ps1').replace("'","''")
            temp=str(root).replace("'","''")
            code="""
$global:testMode='MODE'
$global:testRoot='TEMP'
function Invoke-WebRequest { throw 'isolated unavailable' }
function Invoke-RestMethod { throw 'isolated unavailable' }
function Start-Sleep {}
function Stop-Process { throw 'TEST_MUST_NOT_STOP_PROCESS' }
function Get-NetTCPConnection {
 if ($global:testMode -eq 'listener') { [pscustomobject]@{OwningProcess=777} }
}
function Get-CimInstance {
 if ($global:testMode -in @('listener','recorded')) {
  [pscustomobject]@{Name='python.exe';CommandLine='python -B -m api.server --host 127.0.0.1 --port 8010';CreationDate=(Get-Date)}
 }
}
function Start-Process {
 if ($global:testMode -in @('listener','recorded')) { throw 'TEST_MUST_NOT_DUPLICATE_START' }
 $item=[pscustomobject]@{Id=777;HasExited=($global:testMode -eq 'exited');ExitCode=7}
 $item | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
 return $item
}
if ($global:testMode -eq 'recorded') {
 $logs=Join-Path $global:testRoot 'outputs/service_logs'
 New-Item -ItemType Directory -Path $logs -Force | Out-Null
 '777' | Set-Content -LiteralPath (Join-Path $logs 'server_fixture.pid')
}
& 'SCRIPT' -ProjectRoot $global:testRoot -PythonPath 'D:/python/python.exe'
exit $LASTEXITCODE
""".replace('MODE',mode).replace('TEMP',temp).replace('SCRIPT',escaped)
            harness=root/'harness.ps1';harness.write_text(code,encoding='utf-8-sig')
            return subprocess.run([SHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(harness)],capture_output=True,text=True,timeout=20)

    def test_alive_is_nonterminal_starting(self):
        result=self.run_case('alive');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('RESULT=starting',result.stdout);self.assertIn('TERMINAL=false',result.stdout)
        self.assertNotIn('RESULT=start_failed',result.stdout)

    def test_exited_is_failed(self):
        result=self.run_case('exited');self.assertEqual(result.returncode,1,result.stdout+result.stderr)
        self.assertIn('RESULT=start_failed',result.stdout);self.assertIn('EXIT_CODE=7',result.stdout)

    def test_existing_initializing_process_not_restarted(self):
        for mode in ('listener','recorded'):
            with self.subTest(mode=mode):
                result=self.run_case(mode);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('RESULT=starting',result.stdout)
                self.assertNotIn('TEST_MUST_NOT',result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
