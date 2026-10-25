from pathlib import Path
from hashlib import sha256
import json
import tempfile
import unittest
from unittest.mock import patch
from scripts import run_registered_paper_diagnosed as wrapper


class DiagnosedLauncherTests(unittest.TestCase):
    def test_original_failure_exit_and_diagnostic_only_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pins = {}
            for name in ("scripts/run_registered_paper_diagnosed.py", "scripts/paper_failure_diagnostics.py"):
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes((Path.cwd() / name).read_bytes())
                pins[name] = sha256(path.read_bytes()).hexdigest()
            descriptor = root / "descriptor.json"
            descriptor.write_text(json.dumps(dict(root=str(root), source_hashes=pins,
                                                  log_directory="new/logs")))
            args = dict(descriptor_path=str(descriptor),
                        expected_descriptor_sha256=sha256(descriptor.read_bytes()).hexdigest(),
                        mode="daily", execute=True)
            with patch.object(wrapper.original, "run", side_effect=ValueError("ORIGINAL_FAILURE")) as original:
                result, code, diagnostic = wrapper.run(**args)
                self.assertEqual(code, 2)
                self.assertEqual(result["reason"], "ORIGINAL_FAILURE")
                self.assertNotIn("clock", original.call_args.kwargs)
            self.assertEqual(len(list((root / "new/logs-diagnostics").glob("*.json"))), 1)
            scope = {}
            exec(compile("def fail(**kwargs):\n try:\n  raise ValueError('INITIAL_CAPTURE_FAILED')\n"
                         " finally:\n  raise ValueError('CLEANUP_FAILED')\n",
                         str(root / "scripts/run_registered_paper_automation.py"), "exec"), scope)
            with patch.object(wrapper.original, "run", side_effect=scope["fail"]):
                result, code, diagnostic = wrapper.run(**args)
                self.assertEqual(result["reason"], "CLEANUP_FAILED")
                self.assertEqual(code, 2)
                self.assertEqual([r["reason_code"] for r in diagnostic["snapshots"][0]["records"]],
                                 ["INITIAL_CAPTURE_FAILED", "CLEANUP_FAILED"])
            with patch.object(wrapper.original, "run", return_value={"status": "SKIPPED_NO_DISPATCH"}), \
                    patch.object(wrapper.registrar, "save", side_effect=OSError("full")):
                result, code, diagnostic = wrapper.run(**args)
                self.assertEqual(code, 0)
                self.assertTrue(diagnostic["persistence_failed"])
