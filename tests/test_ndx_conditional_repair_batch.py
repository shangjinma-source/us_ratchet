from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backtest import ndx_conditional_repair_batch as batch


ROOT = Path(__file__).resolve().parents[1]


class NdxConditionalRepairBatchTests(unittest.TestCase):
    def _storage_fixture(self, root: Path):
        binding = root / "binding.bin"
        binding.write_bytes(b"fixed")
        descriptor = {
            "path": binding.resolve().as_posix(),
            "sha256": batch._sha256(binding.read_bytes()),
        }
        candidates = []
        for index, role in enumerate(("CONTROL_EXACT_REUSE", "CONDITIONAL_REPAIR")):
            key = f"candidate-{index}"
            candidates.append(
                {
                    "candidate_key": key,
                    "candidate_identity_sha256": str(index + 1) * 64,
                    "universe_track": f"track-{index}",
                    "holding_count": index + 1,
                    "processing_role": role,
                    "source_checkpoint": {
                        "path": f"source-{index}.json",
                        "sha256": str(index + 3) * 64,
                    },
                    "source_result_sha256": str(index + 5) * 64,
                    "source_a_summary": {"row": index},
                    "source_a_daily_risk_audit_sha256": str(index + 7) * 64,
                    "source_candidate": {"candidate_key": key},
                }
            )
        payload = {
            "schema_version": 1,
            "plan_type": "ndx_conditional_whole_lot_repair_batch",
            "status": "LOCKED_HISTORICAL_RESEARCH_PLAN",
            "research_track": "portfolio_optimization_execution_diagnostic",
            "source_plan_fingerprint": batch.SOURCE_FINGERPRINT,
            "source_verifier_status": "VERIFIED_COMPLETE",
            "source_files": {"source": descriptor},
            "code_bindings": {"module": descriptor},
            "counts": {"total": 2, "CONTROL_EXACT_REUSE": 1, "CONDITIONAL_REPAIR": 1},
            "max_repair_evaluations_per_rebalance": 262_144,
            "candidates": candidates,
            "candidate_set_or_weight_search_run": False,
            "rebalance_cadence_changed": False,
            "risk_thresholds_changed": False,
            "portfolio_cash_changed": False,
            "transaction_cost_changed": False,
            "cross_track_or_evaluator_ranking_allowed": False,
            "fresh_oos_consumed": False,
            "admission_claimed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "order_creation_allowed": False,
        }
        plan = {**payload, "plan_fingerprint": batch._canonical_sha256(payload)}

        def rebuilt(candidate, _source_checkpoint):
            repaired = candidate["processing_role"] == "CONDITIONAL_REPAIR"
            return {
                "candidate_key": candidate["candidate_key"],
                "processing_role": candidate["processing_role"],
                "conditional_c": {
                    "status": "COMPLETE_RISK_CONSTRAINTS_PRESERVED",
                    "execution_eligible": True,
                    "successful_repair_count": 1 if repaired else 0,
                    "unresolved_rebalance_count": 0,
                },
            }

        return plan, rebuilt

    def _source_result(self, *, failure_on_rebalance: bool):
        failure_date = "2024-03-04" if failure_on_rebalance else "2024-03-01"
        return {
            "continued_schedule_a": {
                "schedule_dates": ["2024-02-01", "2024-03-04"],
                "daily_risk_audit": {
                    "failure_sessions": [
                        {
                            "session_date": failure_date,
                            "failure_reasons": ["MIN_SINGLE_WEIGHT"],
                        }
                    ]
                },
            }
        }

    def test_role_uses_rebalance_intersection_not_any_daily_failure(self):
        self.assertEqual(
            batch._source_role(self._source_result(failure_on_rebalance=True)),
            "CONDITIONAL_REPAIR",
        )
        self.assertEqual(
            batch._source_role(self._source_result(failure_on_rebalance=False)),
            "CONTROL_EXACT_REUSE",
        )

    def test_plan_boundary_rejects_resigned_ranking_permission(self):
        plan = {
            "schema_version": 1,
            "plan_type": "ndx_conditional_whole_lot_repair_batch",
            "status": "LOCKED_HISTORICAL_RESEARCH_PLAN",
            "research_track": "portfolio_optimization_execution_diagnostic",
            "source_plan_fingerprint": batch.SOURCE_FINGERPRINT,
            "source_verifier_status": "VERIFIED_COMPLETE",
            "source_files": {},
            "code_bindings": {},
            "counts": dict(batch.EXPECTED_COUNTS),
            "max_repair_evaluations_per_rebalance": 262_144,
            "candidates": [],
            "candidate_set_or_weight_search_run": False,
            "rebalance_cadence_changed": False,
            "risk_thresholds_changed": False,
            "portfolio_cash_changed": False,
            "transaction_cost_changed": False,
            "cross_track_or_evaluator_ranking_allowed": True,
            "fresh_oos_consumed": False,
            "admission_claimed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "order_creation_allowed": False,
        }
        plan["plan_fingerprint"] = batch._canonical_sha256(plan)
        with self.assertRaisesRegex(batch.NdxConditionalRepairBatchError, "plan changed"):
            batch._validate_plan(plan)

    def test_result_summary_keeps_controls_and_repairs_separate(self):
        control = {
            "processing_role": "CONTROL_EXACT_REUSE",
            "conditional_c": {
                "status": "COMPLETE_WITH_DAILY_MARK_TO_MARKET_RISK_FAILURES",
                "execution_eligible": False,
                "successful_repair_count": 0,
                "unresolved_rebalance_count": 0,
            },
        }
        repair = {
            "processing_role": "CONDITIONAL_REPAIR",
            "conditional_c": {
                "status": "COMPLETE_RISK_CONSTRAINTS_PRESERVED",
                "execution_eligible": True,
                "successful_repair_count": 3,
                "unresolved_rebalance_count": 0,
            },
        }
        result = batch._result_summary([control, repair])
        self.assertEqual(result["control_exact_reuse_rows"], 1)
        self.assertEqual(result["conditional_repair_rows"], 1)
        self.assertEqual(result["successful_repair_events"], 3)
        self.assertEqual(result["conditional_c_execution_eligible_rows"], 1)
        self.assertFalse(result["ranking_or_winner_selected"])

    def test_checkpoint_hash_is_bound_to_source_descriptor(self):
        candidate = {
            "candidate_key": "a" * 24,
            "candidate_identity_sha256": "b" * 64,
            "processing_role": "CONTROL_EXACT_REUSE",
            "source_checkpoint": {"path": "x", "sha256": "c" * 64},
        }
        checkpoint = batch._checkpoint_payload(
            plan_fingerprint="d" * 64,
            candidate=candidate,
            result={"safe": True},
        )
        changed = dict(checkpoint)
        changed["source_checkpoint"] = {"path": "x", "sha256": "e" * 64}
        payload = dict(changed)
        claimed = payload.pop("checkpoint_sha256")
        self.assertNotEqual(claimed, batch._canonical_sha256(payload))

    def test_cli_help_runs_without_writing(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts/ndx_conditional_repair_batch.py"),
                "--help",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--verify", completed.stdout)

    def test_execute_and_verify_reject_output_outside_research_namespace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "not-research"
            for operation in (
                batch.execute_conditional_repair_batch,
                batch.verify_conditional_repair_batch,
            ):
                with self.assertRaisesRegex(
                    batch.NdxConditionalRepairBatchError,
                    "outside the research namespace",
                ):
                    operation(repository_root=root, output_root=outside)

    def test_storage_execute_resume_and_read_only_verify(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "data/cache/research/test-repair"
            plan, rebuilt = self._storage_fixture(root)
            counts = {
                "total": 2,
                "CONTROL_EXACT_REUSE": 1,
                "CONDITIONAL_REPAIR": 1,
            }
            with (
                mock.patch.dict(batch.EXPECTED_COUNTS, counts, clear=True),
                mock.patch.object(
                    batch, "build_conditional_repair_plan", return_value=plan
                ),
                mock.patch.object(
                    batch, "_load_source_checkpoint", return_value={"sealed": True}
                ),
                mock.patch.object(batch, "rebuild_candidate_result", side_effect=rebuilt),
            ):
                partial = batch.execute_conditional_repair_batch(
                    repository_root=root, output_root=output, max_candidates=1
                )
                self.assertEqual(partial["status"], "PARTIAL_OR_FAILED")
                run_dir = output / "runs" / plan["plan_fingerprint"]
                first_path = batch._checkpoint_path(run_dir, plan["candidates"][0])
                first_raw = first_path.read_bytes()
                complete = batch.execute_conditional_repair_batch(
                    repository_root=root, output_root=output, resume=True
                )
                self.assertEqual(complete["status"], "COMPLETE")
                self.assertEqual(first_path.read_bytes(), first_raw)
                before = {
                    name: (run_dir / name).read_bytes()
                    for name in ("manifest.json", "checkpoint_index.json", "results.json")
                }
                verified = batch.verify_conditional_repair_batch(
                    repository_root=root, output_root=output
                )
                self.assertEqual(verified["status"], "VERIFIED_COMPLETE")
                self.assertEqual(
                    before,
                    {
                        name: (run_dir / name).read_bytes()
                        for name in before
                    },
                )
                extra = run_dir / "checkpoints/extra.json"
                extra.write_bytes(b"{}")
                with self.assertRaisesRegex(
                    batch.NdxConditionalRepairBatchError, "exactly 323"
                ):
                    batch.verify_conditional_repair_batch(
                        repository_root=root, output_root=output
                    )
                extra.unlink()

    def test_source_or_code_drift_blocks_complete_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "data/cache/research/test-repair"
            plan, rebuilt = self._storage_fixture(root)
            counts = {
                "total": 2,
                "CONTROL_EXACT_REUSE": 1,
                "CONDITIONAL_REPAIR": 1,
            }
            with (
                mock.patch.dict(batch.EXPECTED_COUNTS, counts, clear=True),
                mock.patch.object(
                    batch, "build_conditional_repair_plan", return_value=plan
                ),
                mock.patch.object(
                    batch, "_load_source_checkpoint", return_value={"sealed": True}
                ),
                mock.patch.object(batch, "rebuild_candidate_result", side_effect=rebuilt),
            ):
                batch.execute_conditional_repair_batch(
                    repository_root=root, output_root=output, max_candidates=1
                )
                run_dir = output / "runs" / plan["plan_fingerprint"]
                manifest_before = (run_dir / "manifest.json").read_bytes()
                Path(plan["source_files"]["source"]["path"]).write_bytes(b"drift")
                with self.assertRaisesRegex(
                    batch.NdxConditionalRepairBatchError, "file changed"
                ):
                    batch.execute_conditional_repair_batch(
                        repository_root=root, output_root=output, resume=True
                    )
                self.assertEqual((run_dir / "manifest.json").read_bytes(), manifest_before)
                self.assertFalse((run_dir / "results.json").exists())

    def test_verify_rejects_tampered_aggregate_without_repairing_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "data/cache/research/test-repair"
            plan, rebuilt = self._storage_fixture(root)
            counts = {
                "total": 2,
                "CONTROL_EXACT_REUSE": 1,
                "CONDITIONAL_REPAIR": 1,
            }
            with (
                mock.patch.dict(batch.EXPECTED_COUNTS, counts, clear=True),
                mock.patch.object(
                    batch, "build_conditional_repair_plan", return_value=plan
                ),
                mock.patch.object(
                    batch, "_load_source_checkpoint", return_value={"sealed": True}
                ),
                mock.patch.object(batch, "rebuild_candidate_result", side_effect=rebuilt),
            ):
                batch.execute_conditional_repair_batch(
                    repository_root=root, output_root=output
                )
                run_dir = output / "runs" / plan["plan_fingerprint"]
                for name in ("manifest.json", "checkpoint_index.json", "results.json"):
                    path = run_dir / name
                    original = path.read_bytes()
                    value = json.loads(original.decode("utf-8"))
                    if isinstance(value, list):
                        value[0]["status"] = "TAMPERED"
                    else:
                        value["status"] = "TAMPERED"
                        if name == "manifest.json":
                            payload = dict(value)
                            payload.pop("manifest_sha256", None)
                            value["manifest_sha256"] = batch._canonical_sha256(payload)
                    tampered = batch._json_bytes(value)
                    path.write_bytes(tampered)
                    with self.assertRaises(batch.NdxConditionalRepairBatchError):
                        batch.verify_conditional_repair_batch(
                            repository_root=root, output_root=output
                        )
                    self.assertEqual(path.read_bytes(), tampered)
                    path.write_bytes(original)

    def test_verify_fails_when_the_same_run_lock_is_held(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "data/cache/research/test-repair"
            plan, rebuilt = self._storage_fixture(root)
            counts = {
                "total": 2,
                "CONTROL_EXACT_REUSE": 1,
                "CONDITIONAL_REPAIR": 1,
            }
            with (
                mock.patch.dict(batch.EXPECTED_COUNTS, counts, clear=True),
                mock.patch.object(
                    batch, "build_conditional_repair_plan", return_value=plan
                ),
                mock.patch.object(
                    batch, "_load_source_checkpoint", return_value={"sealed": True}
                ),
                mock.patch.object(batch, "rebuild_candidate_result", side_effect=rebuilt),
            ):
                batch.execute_conditional_repair_batch(
                    repository_root=root, output_root=output
                )
                run_dir = output / "runs" / plan["plan_fingerprint"]
                with batch.source_runner._single_instance_lock(run_dir / ".runner.lock"):
                    with self.assertRaisesRegex(ValueError, "another replay"):
                        batch.verify_conditional_repair_batch(
                            repository_root=root, output_root=output
                        )


if __name__ == "__main__":
    unittest.main()
