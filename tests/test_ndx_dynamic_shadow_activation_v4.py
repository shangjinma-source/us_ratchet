from contextlib import ExitStack
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backtest import ndx_dynamic_shadow_activation_v4 as activation

ROOT = Path(__file__).resolve().parents[1]


class ActivationV4Tests(unittest.TestCase):
    def fixture(self, root):
        for name in activation.SOURCES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n", encoding="utf-8")
        predecessor = root / activation.PREDECESSOR
        predecessor.parent.mkdir(parents=True, exist_ok=True)
        predecessor.write_text("{}", encoding="utf-8")
        proof = [{"suite": name, "tests": 1, "verified_exit_code": 0}
                 for name in activation.TEST_SUITES]
        stack = ExitStack()
        stack.enter_context(patch.object(activation, "_contract", return_value={"fixture": True}))
        stack.enter_context(patch.object(activation, "_runtime_proofs", return_value=proof))
        stack.enter_context(patch.object(activation, "verify_activation_v3_static_sources", return_value={}))
        calendar = SimpleNamespace(events=[{"sequence": 1, "fixture": "sealed"}])
        stack.enter_context(patch.object(activation, "verify_canonical_reviewed_calendar_v2", return_value=calendar))
        self.addCleanup(stack.close)
        return calendar

    def test_build_verify_and_normal_append_preserve_prefix(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            calendar = self.fixture(root)
            built = activation.build_activation_v4_manifest(root)
            self.assertEqual(built["status"], activation.STATUS)
            self.assertFalse(built["boundaries"]["task_registration_performed"])
            calendar.events.append({"sequence": 2, "fixture": "later"})
            self.assertEqual(activation.verify_activation_v4_manifest(
                root / activation.MANIFEST, repository_root=root,
            ), built)
            calendar.events[0]["fixture"] = "rewritten"
            with self.assertRaisesRegex(activation.ActivationV4Error, "prefix"):
                activation.verify_activation_v4_manifest(root / activation.MANIFEST, repository_root=root)

    def test_changed_runtime_source_cannot_reuse_activation(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            activation.build_activation_v4_manifest(root)
            (root / activation.SOURCES[1]).write_text("changed", encoding="utf-8")
            with self.assertRaises(activation.ActivationV4Error):
                activation.verify_activation_v4_static_sources(root / activation.MANIFEST, repository_root=root)

    def test_interrupted_bundle_publication_retries_after_calendar_append(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            calendar = self.fixture(root)
            with patch.object(activation.os, "rename", side_effect=OSError("injected crash")):
                with self.assertRaisesRegex(OSError, "injected crash"):
                    activation.build_activation_v4_manifest(root)
            self.assertFalse((root / activation.MANIFEST).parent.exists())
            calendar.events.append({"sequence": 2, "fixture": "later"})
            self.assertEqual(activation.build_activation_v4_manifest(root)["status"], activation.STATUS)

    def test_proof_side_effect_cannot_publish_poisoned_calendar(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            calendar = self.fixture(root)
            def corrupt_calendar(_root):
                calendar.events[0]["fixture"] = "rewritten"
                return [{"suite": name, "tests": 1, "verified_exit_code": 0}
                        for name in activation.TEST_SUITES]
            with patch.object(activation, "_runtime_proofs", side_effect=corrupt_calendar):
                with self.assertRaisesRegex(activation.ActivationV4Error, "calendar changed"):
                    activation.build_activation_v4_manifest(root)
            self.assertFalse((root / activation.MANIFEST).parent.exists())

    def test_self_resigned_empty_proof_inventory_is_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            payload = activation.build_activation_v4_manifest(root)
            payload["runtime_proofs"] = []
            payload.pop("manifest_sha256")
            payload["manifest_sha256"] = activation._hash(payload)
            path = root / activation.MANIFEST
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(activation.ActivationV4Error, "coverage"):
                activation.verify_activation_v4_static_sources(path, repository_root=root)

    def test_immutable_artifact_never_overwrites_existing_bytes(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "proof.json"
            activation._immutable_bytes(path, b"first")
            activation._immutable_bytes(path, b"first")
            with self.assertRaises(activation.ActivationV4Error):
                activation._immutable_bytes(path, b"second")
            self.assertEqual(path.read_bytes(), b"first")

    def test_self_resigned_unknown_top_level_authority_is_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            payload = activation.build_activation_v4_manifest(root)
            payload["task_registration_allowed"] = True
            payload["live_allowed"] = True
            payload.pop("manifest_sha256")
            payload["manifest_sha256"] = activation._hash(payload)
            path = root / activation.MANIFEST
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(activation.ActivationV4Error):
                activation.verify_activation_v4_manifest(path, repository_root=root)

    def test_missing_or_zero_test_proof_cannot_pass(self):
        with self.assertRaises(activation.ActivationV4Error):
            activation._validate_proofs([])
        invalid = [{"suite": name, "tests": 0, "verified_exit_code": 0}
                   for name in activation.TEST_SUITES]
        with self.assertRaises(activation.ActivationV4Error):
            activation._validate_proofs(invalid)

    def test_repository_hash_helper_cannot_mask_source_change(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            activation.build_activation_v4_manifest(root)
            with patch("data.versioning.file_sha256", return_value="0" * 64):
                (root / "data/versioning.py").write_text("changed", encoding="utf-8")
                with self.assertRaises(activation.ActivationV4Error):
                    activation.verify_activation_v4_static_sources(root / activation.MANIFEST, repository_root=root)

    def test_canonical_runner_contract_matches_unchanged_predecessor(self):
        self.assertEqual(activation._contract(ROOT)["runner_id"], "ndx_dynamic_shadow_runner_v3")


if __name__ == "__main__":
    unittest.main()
