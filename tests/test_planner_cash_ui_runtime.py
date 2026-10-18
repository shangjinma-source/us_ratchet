"""Current HTML cash race regressions with synthetic transport and minimal DOM.

No browser layout, live account, production API, cash-history or economic engine
is exercised. Node is optional; its absence produces an explicit unittest skip.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node.js is required for current HTML JavaScript regression tests")
class PlannerCashUiRuntimeTests(unittest.TestCase):
    def run_javascript(self, filename, expected_status, expected_count):
        html = ROOT / "web" / "index.html"
        before = hashlib.sha256(html.read_bytes()).hexdigest()
        completed = subprocess.run(
            [NODE, str(ROOT / "tests" / filename)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], expected_status)
        self.assertEqual(result["tests"], expected_count)
        self.assertFalse(result["real_browser_layout_verified"] if "real_browser_layout_verified" in result else result["real_dom_layout_verified"])
        self.assertEqual(hashlib.sha256(html.read_bytes()).hexdigest(), before)

    def test_cash_budget_and_stale_core_responses(self):
        self.run_javascript(
            "planner_cash_budget_runtime.mjs", "CURRENT_HTML_FUNCTION_RUNTIME_PASS", 8
        )

    def test_latest_state_pending_failure_and_recovery(self):
        self.run_javascript(
            "planner_cash_refresh_pending.mjs", "LATEST_STATE_PENDING_FAILURE_RUNTIME_PASS", 7
        )

    def test_storage_preferences_keep_cash_fallback_and_original_priority(self):
        self.run_javascript(
            "planner_cash_storage_preferences.mjs", "CURRENT_HTML_STORAGE_PREFERENCES_PASS", 14
        )


if __name__ == "__main__":
    unittest.main()
