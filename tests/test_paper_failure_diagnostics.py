from pathlib import Path
import sys
import unittest

from scripts.paper_failure_diagnostics import observe


class DiagnosticsTests(unittest.TestCase):
    def test_capture_original_before_replacement_without_message_secrets(self):
        filename = Path.cwd() / "scripts/bootstrap_current_quantity_v2_simulation.py"
        scope = {}
        exec(compile("def fail():\n try:\n  raise ValueError('https://secret.invalid/token')\n"
                     " except Exception:\n  raise RuntimeError('CLOCK_WINDOW_EXPIRED')\n",
                     str(filename), "exec"), scope)
        outputs = []
        with self.assertRaisesRegex(RuntimeError, "CLOCK_WINDOW_EXPIRED"):
            observe(scope["fail"], root=Path.cwd(), sink=outputs.append)
        self.assertIsNone(sys.gettrace())
        records = outputs[0]["records"]
        self.assertEqual([r["exception_type"] for r in records], ["ValueError", "RuntimeError"])
        self.assertEqual([r["reason_code"] for r in records], [None, "CLOCK_WINDOW_EXPIRED"])
        self.assertNotIn("secret", str(outputs))

    def test_success_passthrough(self):
        outputs = []
        self.assertEqual(observe(lambda: 5, root=Path.cwd(), sink=outputs.append), 5)
        self.assertEqual(outputs[0]["records"], [])

    def test_sink_failure_does_not_replace_original(self):
        def sink(_):
            raise OSError("sink error")
        def fail():
            raise ValueError("ORIGINAL")
        with self.assertRaisesRegex(ValueError, "ORIGINAL"):
            observe(fail, root=Path.cwd(), sink=sink)
        self.assertEqual(observe(lambda: 7, root=Path.cwd(), sink=sink), 7)

    def test_broken_exception_string_preserves_exception(self):
        filename = Path.cwd() / "scripts/bootstrap_current_quantity_v2_simulation.py"
        scope = {}
        exec(compile("class Broken(Exception):\n def __str__(self):\n  raise RuntimeError('format')\n"
                     "def fail():\n raise Broken()\n", str(filename), "exec"), scope)
        outputs = []
        with self.assertRaises(scope["Broken"]):
            observe(scope["fail"], root=Path.cwd(), sink=outputs.append)
        self.assertIsNone(sys.gettrace())
