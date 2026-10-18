"""Activation5 unit adversaries; calendar/lineage/proof processes are fixtures.

These tests do not assert full live daily execution or authorize task cutover.
"""
from contextlib import ExitStack, nullcontext
import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backtest import ndx_dynamic_shadow_activation_v5 as activation


ROOT = Path(__file__).resolve().parents[1]


class ActivationV5Tests(unittest.TestCase):
    def fixture(self, root):
        for name in activation.SOURCES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        predecessor = root / activation.PREDECESSOR
        predecessor.parent.mkdir(parents=True, exist_ok=True)
        predecessor.write_text("{}", encoding="utf-8")
        proofs = [{"suite": name, "tests": 1, "verified_exit_code": 0}
                  for name in activation.TEST_SUITES]
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(activation, "verify_activation_v4_static_sources", return_value={}))
        stack.enter_context(patch.object(activation, "_runtime_proofs", return_value=proofs))
        calendar = SimpleNamespace(events=[{"sequence": 1, "fixture": "sealed"}])
        stack.enter_context(patch.object(activation, "verify_canonical_reviewed_calendar_v2", return_value=calendar))
        return calendar

    def test_real_contract_is_validated_not_mocked(self):
        self.assertEqual(activation._contract(ROOT)["runner_id"], "ndx_dynamic_shadow_runner_v4")

    def test_actual_missing_manifest_blocks_daily_before_refresh(self):
        from scripts import ndx_dynamic_shadow_daily_v4 as daily
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(daily, "ROOT", root), \
                    patch.object(daily, "ACTIVATION", root / activation.MANIFEST), \
                    patch.object(daily.engine, "single_instance_lock", return_value=nullcontext()), \
                    patch.object(daily.engine, "_protected_hashes", return_value={}), \
                    patch.object(daily.previous, "_refresh_calendar") as refresh, \
                    patch.object(daily.engine, "execute") as execute:
                with self.assertRaises((FileNotFoundError, activation.ActivationV5Error)):
                    daily.execute()
                refresh.assert_not_called()
                execute.assert_not_called()

    def test_build_static_and_append_preserve_research_boundary(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            calendar = self.fixture(root)
            built = activation.build_activation_v5_manifest(root)
            self.assertFalse(built["boundaries"]["task_registration_performed"])
            self.assertFalse(built["boundaries"]["live_mutation_allowed"])
            calendar.events.append({"sequence": 2, "fixture": "later"})
            self.assertEqual(activation.verify_activation_v5_manifest(
                root / activation.MANIFEST, repository_root=root), built)
            calendar.events[0]["fixture"] = "rewritten"
            with self.assertRaises(activation.ActivationV5Error):
                activation.verify_activation_v5_manifest(root / activation.MANIFEST, repository_root=root)

    def test_new_adapter_source_change_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            activation.build_activation_v5_manifest(root)
            (root / "scripts/ndx_dynamic_shadow_fresh_search_v4.py").write_text("changed", encoding="utf-8")
            with self.assertRaises(activation.ActivationV5Error):
                activation.verify_activation_v5_static_sources(root / activation.MANIFEST, repository_root=root)

    def test_taxonomy_policy_change_rejected(self):
        relative = "config/candidate_taxonomy_v2.yaml"
        self.assertIn(relative, activation.SOURCES)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            activation.build_activation_v5_manifest(root)
            policy = root / relative
            policy.write_bytes(policy.read_bytes() + b"\n# policy drift\n")
            with self.assertRaises(activation.ActivationV5Error):
                activation.verify_activation_v5_static_sources(root / activation.MANIFEST, repository_root=root)

    def test_numeric_false_cannot_replace_contract_boolean(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            path = root / activation.CONTRACT
            path.write_text(path.read_text(encoding="utf-8").replace(
                "live_mutation_allowed: false", "live_mutation_allowed: 0"), encoding="utf-8")
            with self.assertRaises(activation.ActivationV5Error):
                activation._contract(root)

    def test_boolean_test_count_rejected(self):
        proofs = [{"suite": name, "tests": True, "verified_exit_code": 0}
                  for name in activation.TEST_SUITES]
        with self.assertRaises(activation.ActivationV5Error):
            activation._validate_proofs(proofs)

    def test_interrupted_publication_does_not_leave_canonical_partial_bundle(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            with patch.object(activation.os, "rename", side_effect=OSError("injected interruption")):
                with self.assertRaises(OSError):
                    activation.build_activation_v5_manifest(root)
            self.assertFalse((root / activation.MANIFEST).parent.exists())
            built = activation.build_activation_v5_manifest(root)
            self.assertEqual(built["status"], activation.STATUS)

    def test_static_verification_rejects_noncanonical_manifest_copy(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            activation.build_activation_v5_manifest(root)
            alternate = root / "copied-manifest.json"
            alternate.write_bytes((root / activation.MANIFEST).read_bytes())
            with self.assertRaises(activation.ActivationV5Error):
                activation.verify_activation_v5_static_sources(alternate, repository_root=root)

    def test_unknown_manifest_authority_even_resigned_is_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            value = activation.build_activation_v5_manifest(root)
            value["task_registration_allowed"] = True
            value.pop("manifest_sha256")
            value["manifest_sha256"] = activation._hash(value)
            path = root / activation.MANIFEST
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(activation.ActivationV5Error):
                activation.verify_activation_v5_static_sources(path, repository_root=root)

    def test_predecessor_changes_during_proofs_cannot_publish(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            def mutate(_root):
                (root / activation.PREDECESSOR).write_text('{"changed":true}', encoding="utf-8")
                return [{"suite": name, "tests": 1, "verified_exit_code": 0}
                        for name in activation.TEST_SUITES]
            with patch.object(activation, "_runtime_proofs", side_effect=mutate):
                with self.assertRaises(activation.ActivationV5Error):
                    activation.build_activation_v5_manifest(root)
            self.assertFalse((root / activation.MANIFEST).exists())

    def test_source_inventory_includes_new_evidence_consumers(self):
        for name in ("scripts/ndx_dynamic_shadow_candidate_generator_v3.py",
                     "backtest/ndx_dynamic_shadow_candidate_generator_v3.py",
                     "scripts/ndx_dynamic_shadow_fresh_search_v4.py",
                     "scripts/ndx_dynamic_shadow_daily_v4.py",
                     "backtest/ndx_dynamic_shadow_daily_v3.py",
                     "data/ndx_filing_identity.py", "data/ndx_sic_history.py",
                     "data/ndx_fundamentals.py", "data/cn_source.py",
                     "core/__init__.py", "backtest/__init__.py",
                     "data/__init__.py", "scripts/__init__.py"):
            with self.subTest(name=name):
                self.assertIn(name, activation.SOURCES)

    def test_local_test_fixture_imports_are_also_hash_bound(self):
        sources = set(activation.SOURCES)
        for name in sources:
            if not name.startswith("tests/") or not name.endswith(".py"):
                continue
            tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                           else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
                for module in modules:
                    candidate = "tests/" + module.replace(".", "/") + ".py"
                    if (ROOT / candidate).is_file():
                        with self.subTest(source=name, dependency=candidate):
                            self.assertIn(candidate, sources)


if __name__ == "__main__":
    unittest.main()
