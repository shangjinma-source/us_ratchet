from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_us_ratchet_startup_task.ps1"


@unittest.skipUnless(os.name == "nt", "Windows Scheduled Task installer is Windows-only")
class StartupTaskInstallerTests(unittest.TestCase):
    def test_default_invocation_is_plan_only(self):
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-ProjectRoot",
                str(ROOT),
                "-TaskName",
                "us_ratchet_test_plan_only",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"mode":  "PLAN_ONLY"', completed.stdout)
        self.assertIn('"trigger":  "AT_LOGON"', completed.stdout)
        self.assertIn("start_service.ps1", completed.stdout)
        self.assertIn("RESULT=plan_only", completed.stdout)
        self.assertNotIn("RESULT=registered", completed.stdout)

    def test_apply_requires_duplicate_scheduler_acknowledgement(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("if (-not $AcknowledgeExternalSchedulerDisabled)", source)
        self.assertLess(
            source.index("if (-not $AcknowledgeExternalSchedulerDisabled)"),
            source.index("Register-ScheduledTask"),
        )
        self.assertIn("start_service.ps1_root_and_openapi", source)
        self.assertNotIn("Unregister-ScheduledTask", source)


if __name__ == "__main__":
    unittest.main()
