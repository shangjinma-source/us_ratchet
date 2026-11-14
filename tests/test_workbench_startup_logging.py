"""Exercise the scheduler wrapper with isolated service and HTTP substitutes."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('powershell.exe'), 'Windows PowerShell required')
class StartupLoggingTest(unittest.TestCase):
    def test_pending_checks_are_logged_before_recovery(self):
        source = (pathlib.Path(__file__).resolve().parents[1]
                  / 'scripts/run_workbench_startup.ps1').read_text(encoding='utf-8-sig')
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / 'start_service.ps1').write_text(
                'param($ProjectRoot)\n$global:LASTEXITCODE=0\n"RESULT=already_running"',
                encoding='utf-8')
            source = source.replace("$Root='E:\\Git\\us_ratchet'",
                                    "$Root='" + directory.replace("'", "''") + "'")
            wrapper = root / 'wrapper.ps1'
            wrapper.write_text(source, encoding='utf-8')
            harness = root / 'harness.ps1'
            harness.write_text('''$global:Attempt=0
function Invoke-WebRequest { param($Uri, [switch]$UseBasicParsing, $TimeoutSec)
 return [pscustomobject]@{StatusCode=200}
}
function Invoke-RestMethod { param($Uri, $TimeoutSec)
 $global:Attempt++
 return [pscustomobject]@{active=($global:Attempt -gt 1); strategy_kind='ROA_DEFENSIVE_V1'}
}
function Start-Sleep { param($Seconds) }
& (Join-Path $PSScriptRoot 'wrapper.ps1')
''', encoding='utf-8')
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive',
                                     '-File', str(harness)], capture_output=True,
                                    text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            logs = list((root / 'outputs/service_logs').glob('scheduled_start_*.log'))
            self.assertEqual(len(logs), 1)
            content = logs[0].read_text(encoding='utf-8-sig')
            self.assertIn('"home_status":200', content)
            self.assertIn('"active_is_true":false', content)
            self.assertIn('"strategy_kind_matches":true', content)
            self.assertIn('RESULT=ready', content)
            self.assertLess(content.index('READINESS_PENDING'), content.index('RESULT=ready'))


if __name__ == '__main__':
    unittest.main()
