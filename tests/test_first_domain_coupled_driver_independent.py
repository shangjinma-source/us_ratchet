"""Independent driver integration checks; no real-domain preparation/search."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backtest import quantity_coupled_joint_loss_iterator as engine
from test_quantity_coupled_joint_loss_iterator import synthetic

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location(
        "independent_coupled_driver",
        ROOT / "tmp/run_first_domain_coupled_joint_iterator_20261019_v1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture():
    inputs, context, sources = synthetic()
    parent = dict(
        lower_product=context[1]["lower_product"],
        new_rows=[dict(id="target", upper_product="100"),
                  dict(id="other", upper_product="200")],
        inherited_closed_rows=context[0]["inherited_closed_rows"],
        inherited_fixing_rows=context[0]["inherited_fixing_rows"])
    helper = SimpleNamespace(PINS={}, check=lambda *args: None)
    proof = dict(id="other", upper_product=parent["lower_product"],
                 status="CLOSED_BY_VERIFIED_COMPLETE_ENUMERATION")
    return context, (helper, helper, helper, parent, sources, {}, {}, inputs, proof)


class IndependentCoupledDriver(unittest.TestCase):
    def test_default_and_tiny_complete_create_only(self):
        module = load()
        context, prepared = fixture()
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(module, "ROOT", Path(temporary)), \
                patch.object(module, "OUTPUT", "result"), \
                patch.object(module, "prepare", return_value=prepared), \
                patch.object(module, "check"), \
                patch.object(engine, "_context", return_value=context), \
                redirect_stdout(io.StringIO()):
            with patch("sys.argv", ["driver"]), \
                    patch.object(engine, "build", side_effect=AssertionError("NO DEFAULT SEARCH")):
                module.main()
            self.assertFalse((Path(temporary) / "result").exists())
            with patch("sys.argv", ["driver", "--execute"]):
                module.main()
            out = Path(temporary) / "result"
            certificate = json.loads((out / "certificate.json").read_bytes())
            report = json.loads((out / "report.json").read_bytes())
            self.assertEqual(certificate["node_budget"], 100000)
            self.assertEqual(certificate["objective_budget"], 10000)
            self.assertTrue(certificate["domain_complete"])
            self.assertEqual(report["second_domain_proof"], prepared[-1])
            self.assertEqual(report["inherited_closed_rows"], prepared[3]["inherited_closed_rows"])
            self.assertEqual(report["inherited_fixing_rows"], prepared[3]["inherited_fixing_rows"])
            self.assertEqual(report["whole_upper_product"], certificate["candidate_product"])
            self.assertFalse(report["global_objective_value_optimal"])
            before = {p.name: p.read_bytes() for p in out.iterdir()}
            with patch("sys.argv", ["driver", "--execute"]), \
                    patch.object(engine, "build", side_effect=AssertionError("NO RESTART")):
                with self.assertRaises(FileExistsError):
                    module.main()
            self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})

    def test_source_drift_after_build_preserves_certificate(self):
        module = load()
        context, prepared = fixture()
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(module, "ROOT", Path(temporary)), \
                patch.object(module, "OUTPUT", "result"), \
                patch.object(module, "prepare", return_value=prepared), \
                patch.object(module, "check", side_effect=[None, ValueError("SOURCE_CHANGED")]), \
                patch.object(engine, "_context", return_value=context), \
                patch("sys.argv", ["driver", "--execute"]), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "SOURCE_CHANGED"):
                module.main()
            out = Path(temporary) / "result"
            self.assertTrue((out / "certificate.json").exists())
            self.assertTrue((out / "verification.json").exists())
            self.assertFalse((out / "terminal.json").exists())
            self.assertFalse((out / "report.json").exists())
            self.assertIs(json.loads((out / "failed.json").read_bytes())["retry_allowed"], False)

    def test_verification_failure_never_publishes_success(self):
        module = load()
        context, prepared = fixture()
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(module, "ROOT", Path(temporary)), \
                patch.object(module, "OUTPUT", "result"), \
                patch.object(module, "prepare", return_value=prepared), \
                patch.object(module, "check"), \
                patch.object(engine, "_context", return_value=context), \
                patch.object(engine, "verify", side_effect=ValueError("BAD_CERTIFICATE")), \
                patch("sys.argv", ["driver", "--execute"]):
            with self.assertRaisesRegex(ValueError, "BAD_CERTIFICATE"):
                module.main()
            out = Path(temporary) / "result"
            self.assertTrue((out / "certificate.json").exists())
            self.assertTrue((out / "failed.json").exists())
            self.assertFalse((out / "terminal.json").exists())


if __name__ == "__main__":
    unittest.main()
