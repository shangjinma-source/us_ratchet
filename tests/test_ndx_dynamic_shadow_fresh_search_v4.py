"""Acceptance orchestration tests with explicit simulated parent execution."""
from contextlib import ExitStack
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import ndx_dynamic_shadow_fresh_search_v4 as v4


class FreshSearchV4Tests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(TemporaryDirectory())).resolve()
        self.stack.enter_context(patch.object(v4, "ROOT", self.root))
        for name in v4.CODE_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"frozen test source\n")
        self.path = self.root / v4.INPUT / "2026-10-01" / "manifest.json"
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"candidate snapshot\n")
        self.snapshot = dict(decision_date="2026-10-01", snapshot_fingerprint="a" * 64,
                             source_versions={"candidate_v3": "b" * 64, "frozen_original8_manifest_sha256": "9" * 64},
                             membership_evidence={"candidate_v3_source_archive": {"sha256": "c" * 64}})
        self.final_path = self.root / v4.SEARCH / "final" / "2026-10-01" / "manifest.json"
        self.final_path.parent.mkdir(parents=True)
        self.final_path.write_bytes(b"legacy final role seal\n")
        self.final = dict(decision_date="2026-10-01", snapshot_manifest_sha256=v4.digest(self.path),
                          snapshot_fingerprint="a" * 64, snapshot_seal_record_sha256="d" * 64)
        self.result = dict(controller_stop_reason="FINAL_ROLE_SEAL_VERIFIED", final_role_seal_verified=True,
                           controller_status="FINAL_ROLE_SEAL_VERIFIED", pending_shard_count=0,
                           planned_shard_count=2, verified_completed_shard_count=2, aggregation_allowed=True,
                           snapshot_manifest_sha256=v4.digest(self.path))
        executor = v4.bound_executor_hash({"wrapper_sources": {name: v4.digest(self.root / name) for name in v4.CODE_FILES}})
        self.final["executor_sha256"] = executor
        self.final["original_8_sha256"] = "9" * 64
        self.result["v1_executor_sha256"] = executor
        self.candidate_verify = self.stack.enter_context(patch.object(v4.candidate, "verify", side_effect=lambda p: copy.deepcopy(self.snapshot)))
        self.parent = self.stack.enter_context(patch.object(v4, "execute_budgeted", side_effect=lambda p: copy.deepcopy(self.result)))
        self.stack.enter_context(patch.object(v4, "verify_final_candidate_snapshot", side_effect=lambda p: copy.deepcopy(self.final)))
        self.stack.enter_context(patch.object(v4, "verify_final_role_seal_record", return_value={"record_sha256": "e" * 64}))
        self.stack.enter_context(patch.object(v4.candidate.v1, "_verify_manifest_seal_record", return_value={"record_sha256": "d" * 64}))
        self.receipt = self.root / v4.ACCEPTANCE / "2026-10-01" / "receipt.json"

    def test_completed_parent_requires_separate_acceptance_and_is_idempotent(self):
        self.assertFalse(self.receipt.exists())
        result = v4.execute(self.path)
        self.assertTrue(result["v4_verified"])
        before = self.receipt.read_bytes()
        self.assertTrue(v4.execute(self.path)["v4_verified"])
        self.assertEqual(self.parent.call_count, 1)
        self.assertEqual(self.receipt.read_bytes(), before)

    def test_candidate_failure_stops_before_parent(self):
        self.candidate_verify.side_effect = ValueError("missing v3 archive")
        with self.assertRaisesRegex(ValueError, "missing v3"):
            v4.execute(self.path)
        self.parent.assert_not_called()
        self.assertFalse(self.receipt.exists())

    def test_midrun_input_change_does_not_accept_existing_legacy_seal(self):
        def mutate(path):
            path.write_bytes(b"changed snapshot")
            return self.result
        self.parent.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed during controller"):
            v4.execute(self.path)
        self.assertTrue(self.final_path.exists())
        self.assertFalse(self.receipt.exists())

    def test_partial_budget_has_no_receipt(self):
        self.result.update(final_role_seal_verified=False,
                           controller_stop_reason="DEADLINE_BUDGET_DID_NOT_ADMIT_NEXT_SHARD")
        result = v4.execute(self.path)
        self.assertFalse(result["v4_verified"])
        self.assertEqual(result["completion"]["exit_code"], 4)
        self.assertFalse(self.receipt.exists())

    def test_wrong_final_input_is_rejected(self):
        self.final["snapshot_manifest_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "different candidate"):
            v4.execute(self.path)
        self.assertFalse(self.receipt.exists())

    def test_self_consistent_other_final_executor_is_rejected(self):
        self.final["executor_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "final role seal executor"):
            v4.execute(self.path)
        self.assertFalse(self.receipt.exists())

    def test_other_controller_executor_is_rejected(self):
        self.result["v1_executor_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "controller executor"):
            v4.execute(self.path)
        self.assertFalse(self.receipt.exists())

    def test_missing_original8_binding_rejected_before_controller(self):
        self.snapshot["source_versions"].pop("frozen_original8_manifest_sha256")
        with self.assertRaisesRegex(ValueError, "original8 source binding"):
            v4.execute(self.path)
        self.parent.assert_not_called()
        self.assertFalse(self.receipt.exists())

    def test_other_final_original8_is_rejected(self):
        self.final["original_8_sha256"] = "8" * 64
        with self.assertRaisesRegex(ValueError, "final original8 differs"):
            v4.execute(self.path)
        self.assertFalse(self.receipt.exists())

    def test_executor_hash_uses_bound_bytes_and_matches_v2_mapping(self):
        from scripts import ndx_dynamic_shadow_fresh_search_v2 as controller
        captured = {"wrapper_sources": {name: v4.digest(self.root / name) for name in v4.CODE_FILES}}
        with patch.object(controller, "ROOT", self.root):
            expected = controller._executor_hash()
            self.assertEqual(v4.bound_executor_hash(captured), expected)
            (self.root / v4.EXECUTOR_SOURCE_KEYS["search_kernel_sha256"]).write_bytes(b"later kernel")
            self.assertNotEqual(controller._executor_hash(), expected)
            self.assertEqual(v4.bound_executor_hash(captured), expected)

    def test_acceptance_rejects_claim_injection_and_is_readonly(self):
        v4.execute(self.path)
        receipt = json.loads(self.receipt.read_bytes())
        receipt["admission_allowed"] = True
        self.receipt.write_bytes(v4.canonical(receipt))
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(ValueError, "schema changed"):
            v4.verify_acceptance(self.receipt)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_valid_verify_is_readonly_and_source_drift_fails(self):
        v4.execute(self.path)
        before = self.receipt.read_bytes()
        v4.verify_acceptance(self.receipt)
        self.assertEqual(before, self.receipt.read_bytes())
        (self.root / v4.CODE_FILES[0]).write_bytes(b"new code")
        with self.assertRaisesRegex(ValueError, "input binding changed"):
            v4.verify_acceptance(self.receipt)

    def test_unsafe_date_fails_before_controller(self):
        self.snapshot["decision_date"] = "../2026-10-01"
        with self.assertRaises(ValueError):
            v4.execute(self.path)
        self.parent.assert_not_called()

    def test_integer_boolean_and_schema_boolean_are_rejected(self):
        v4.execute(self.path)
        original = json.loads(self.receipt.read_bytes())
        for field in ("schema_version", "boundaries"):
            receipt = copy.deepcopy(original)
            if field == "schema_version":
                receipt[field] = True
            else:
                receipt[field]["admission_allowed"] = 0
            self.receipt.write_bytes(v4.canonical(receipt))
            with self.assertRaisesRegex(ValueError, "boundary changed"):
                v4.verify_acceptance(self.receipt)

    def test_existing_receipt_is_not_accepted_after_final_changes(self):
        v4.execute(self.path)
        self.final_path.write_bytes(b"later final bytes")
        with self.assertRaisesRegex(ValueError, "final binding changed"):
            v4.execute(self.path)
        self.assertTrue(self.receipt.exists())
        self.assertEqual(self.parent.call_count, 1)

    def test_controller_failure_preserves_old_output_but_no_acceptance(self):
        self.parent.side_effect = RuntimeError("controller failed after old final write")
        with self.assertRaisesRegex(RuntimeError, "controller failed"):
            v4.execute(self.path)
        self.assertTrue(self.final_path.exists())
        self.assertFalse(self.receipt.exists())

    def test_inconsistent_final_completion_does_not_publish(self):
        self.result["verified_completed_shard_count"] = 1
        with self.assertRaisesRegex(ValueError, "completion disagree"):
            v4.execute(self.path)
        self.assertFalse(self.receipt.exists())

    def test_final_drift_before_publication_does_not_publish(self):
        first = dict(path="fixture", sha256="a" * 64, role_seal_record_sha256="b" * 64)
        second = dict(first, sha256="c" * 64)
        with patch.object(v4, "final_binding", side_effect=[first, second]):
            with self.assertRaisesRegex(ValueError, "final changed before acceptance"):
                v4.execute(self.path)
        self.assertFalse(self.receipt.exists())


class FreshSearchV4RealCandidateTests(unittest.TestCase):
    def test_actual_candidate_public_verifier_is_required_for_receipt(self):
        # Only the search engine/final output are simulated; candidate/calendar/input
        # ledger/archive validators run their complete public implementations.
        import test_ndx_dynamic_shadow_candidate_v3_public_verify as public_fixture
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory).resolve()
            control_source = root / "original8_fixture.json"
            control_source.write_bytes(b'{"fixture":"control binding only, not definition validation"}')
            control_hash = v4.digest(control_source)
            path, snapshot = public_fixture._complete_fixture(
                root,
                additional_source_versions={"frozen_original8_manifest_sha256": control_hash},
                additional_source_paths={"frozen_original8_manifest_sha256": control_source.as_posix()},
            )
            public_fixture._temporary_public_paths(stack, root)
            stack.enter_context(patch.object(v4, "ROOT", root))
            for name in v4.CODE_FILES:
                source = root / name
                source.parent.mkdir(parents=True, exist_ok=True)
                if not source.exists():
                    source.write_bytes(b"frozen search fixture\n")
            record = v4.candidate.v1._verify_manifest_seal_record(path, snapshot)
            final_path = root / v4.SEARCH / "final" / "2026-10-01" / "manifest.json"
            final_path.parent.mkdir(parents=True)
            final_path.write_bytes(b"simulated final\n")
            final = dict(decision_date="2026-10-01", snapshot_manifest_sha256=v4.digest(path),
                         snapshot_fingerprint=snapshot["snapshot_fingerprint"],
                         snapshot_seal_record_sha256=record["record_sha256"])
            result = dict(controller_stop_reason="FINAL_ROLE_SEAL_VERIFIED", final_role_seal_verified=True,
                          controller_status="FINAL_ROLE_SEAL_VERIFIED", pending_shard_count=0,
                          planned_shard_count=2, verified_completed_shard_count=2, aggregation_allowed=True,
                          snapshot_manifest_sha256=v4.digest(path))
            executor = v4.bound_executor_hash({"wrapper_sources": {name: v4.digest(root / name) for name in v4.CODE_FILES}})
            final["executor_sha256"] = executor
            final["original_8_sha256"] = control_hash
            result["v1_executor_sha256"] = executor
            stack.enter_context(patch.object(v4, "execute_budgeted", return_value=result))
            stack.enter_context(patch.object(v4, "verify_final_candidate_snapshot", return_value=final))
            stack.enter_context(patch.object(v4, "verify_final_role_seal_record", return_value={"record_sha256": "e" * 64}))
            accepted = v4.execute(path)
            receipt_path = Path(accepted["receipt_path"])
            self.assertTrue(v4.verify_acceptance(receipt_path)["v4_verified"])
            archive_path = Path(snapshot["membership_evidence"]["candidate_v3_source_archive"]["path"])
            archive = json.loads(archive_path.read_bytes())
            archived = archive_path.parent / archive["source_descriptors"][0]["archive_filename"]
            archived.write_bytes(b"corrupt archived source")
            with self.assertRaisesRegex(ValueError, "source archive bytes changed"):
                v4.verify_acceptance(receipt_path)


if __name__ == "__main__":
    unittest.main()
