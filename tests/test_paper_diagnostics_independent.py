import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts import run_registered_paper_diagnosed as wrapper
from scripts.paper_failure_diagnostics import observe


class IndependentDiagnostics(unittest.TestCase):
    def test_readonly_wrapper_preserves_call_and_has_no_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pins = {}
            for name in ("scripts/run_registered_paper_diagnosed.py",
                         "scripts/paper_failure_diagnostics.py"):
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(Path(name).read_bytes())
                pins[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            path = root / "descriptor.json"
            path.write_text(json.dumps(dict(root=str(root), source_hashes=pins,
                                            log_directory="isolated/logs")))
            args = dict(descriptor_path=str(path),
                        expected_descriptor_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        mode="monthly", execute=False)
            before = {str(p.relative_to(root)): p.read_bytes()
                      for p in root.rglob("*") if p.is_file()}
            for status, code in (("PREFLIGHT_ONLY", 0), ("NEEDS_RECOVERY", 2)):
                response = dict(status=status)
                with patch.object(wrapper.original, "run", return_value=response) as run:
                    result, actual, _ = wrapper.run(**args)
                self.assertIs(result, response)
                self.assertEqual(actual, code)
                self.assertEqual(run.call_args.kwargs, args)
                self.assertIsNone(sys.gettrace())
            self.assertEqual(before, {str(p.relative_to(root)): p.read_bytes()
                                      for p in root.rglob("*") if p.is_file()})

    def test_diagnostic_bound_and_sensitive_text_omission(self):
        scope = {}
        filename = Path.cwd() / "scripts/run_registered_paper_automation.py"
        exec(compile(
            "def emit():\n"
            " for i in range(100):\n"
            "  try:\n"
            "   raise ValueError('CODE_'+str(i))\n"
            "  except ValueError: pass\n"
            " try:\n"
            "  raise RuntimeError('api_key=secret')\n"
            " except RuntimeError: pass\n"
            " return 7\n", str(filename), "exec"), scope)
        captures = []
        self.assertEqual(observe(scope["emit"], root=Path.cwd(), sink=captures.append), 7)
        self.assertLessEqual(len(captures[0]["records"]), 64)
        self.assertNotIn("secret", json.dumps(captures))
        self.assertIsNone(sys.gettrace())

    def test_existing_trace_refuses_without_replacing_it(self):
        tracer = lambda *args: None
        previous = sys.gettrace()
        try:
            sys.settrace(tracer)
            with self.assertRaisesRegex(ValueError, "EXISTING_TRACE"):
                observe(lambda: self.fail("MUST NOT RUN"), root=Path.cwd(), sink=lambda _: None)
            self.assertIs(sys.gettrace(), tracer)
        finally:
            sys.settrace(previous)


if __name__ == "__main__":
    unittest.main()
