"""Artifact-smoke adversaries with the expensive daily verifier isolated."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import ndx_dynamic_shadow_runtime_v4_smoke as smoke

ROOT = Path(__file__).resolve().parents[1]


class RuntimeV4SmokeTests(unittest.TestCase):
    def prepare(self, root):
        for relative in ("config/config.yaml", "data/state.json", "data/broker_positions.json"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
        contract = root / "config/ndx_dynamic_shadow_daily_v1.yaml"
        contract.write_bytes((ROOT / contract.relative_to(root)).read_bytes())
        return smoke.snapshot(root)

    def run_file(self, root, **overrides):
        payload = dict(generated_at=datetime.now(timezone.utc).isoformat(),
                       run_manifest_sha256="a" * 64, status="RESEARCH_DAILY_COMPLETE",
                       latest_observed_session="2026-09-09", independent_lane_count=0,
                       realized_decision_batches=0, benchmark_control_count=0, decision_phases=[])
        payload.update(overrides)
        path = root / smoke.LATEST
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path, payload

    def test_fresh_predecision_run_is_not_economic_or_task_proof(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = self.prepare(root)
            _, run = self.run_file(root)
            with patch.object(smoke, "verify_daily_run_manifest", return_value=run):
                proof = smoke.verify(root, before=before)
                self.assertEqual(proof["evidence_level"], "PRE_DECISION_OPERATIONAL_ONLY")
                self.assertIs(proof["task_execution_verified_by_this_tool"], False)
                self.assertIs(proof["promotion_allowed"], False)
                self.assertEqual(smoke.verify(root, expected=proof), proof)
                proof["task_execution_verified_by_this_tool"] = 0
                with self.assertRaises(ValueError):
                    smoke.verify(root, expected=proof)

    def test_old_unchanged_future_and_naive_runs_fail(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = self.prepare(root)
            for generated in ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                              (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                              datetime.now().isoformat()):
                _, run = self.run_file(root, generated_at=generated)
                with patch.object(smoke, "verify_daily_run_manifest", return_value=run):
                    with self.assertRaises(ValueError):
                        smoke.verify(root, before=before)
            _, run = self.run_file(root)
            current = smoke.snapshot(root)
            with patch.object(smoke, "verify_daily_run_manifest", return_value=run):
                with self.assertRaises(ValueError):
                    smoke.verify(root, before=current)

    def test_protected_file_change_fails_even_if_daily_verifier_passes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = self.prepare(root)
            _, run = self.run_file(root)
            (root / "data/state.json").write_text('{"changed":true}', encoding="utf-8")
            with patch.object(smoke, "verify_daily_run_manifest", return_value=run):
                with self.assertRaises(ValueError):
                    smoke.verify(root, before=before)

    def test_changes_during_verification_and_real_verifier_failure_propagate(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = self.prepare(root)
            path, run = self.run_file(root)
            def drift(*args, **kwargs):
                path.write_text("{}", encoding="utf-8")
                return run
            with patch.object(smoke, "verify_daily_run_manifest", side_effect=drift):
                with self.assertRaises(ValueError):
                    smoke.verify(root, before=before)
            self.run_file(root)
            with patch.object(smoke, "verify_daily_run_manifest", side_effect=ValueError("bad v4 lineage")):
                with self.assertRaisesRegex(ValueError, "bad v4 lineage"):
                    smoke.verify(root, before=before)

    def test_no_economic_path_cannot_be_promoted_by_date_or_boolean_count(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = self.prepare(root)
            for changes in ({"latest_observed_session": "2026-10-02"},
                            {"realized_decision_batches": True},
                            {"independent_lane_count": False}):
                _, run = self.run_file(root, **changes)
                with patch.object(smoke, "verify_daily_run_manifest", return_value=run):
                    with self.assertRaises(ValueError):
                        smoke.verify(root, before=before)

    def test_before_schema_and_protected_drift_during_verify_fail(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = self.prepare(root)
            _, run = self.run_file(root)
            invalid = dict(before, schema_version=True)
            with patch.object(smoke, "verify_daily_run_manifest", return_value=run):
                with self.assertRaises(ValueError):
                    smoke.verify(root, before=invalid)
            def drift(*args, **kwargs):
                (root / "data/broker_positions.json").write_text('{"changed":true}', encoding="utf-8")
                return run
            with patch.object(smoke, "verify_daily_run_manifest", side_effect=drift):
                with self.assertRaises(ValueError):
                    smoke.verify(root, before=before)

    def test_late_restamp_with_stale_calendar_is_not_predecision(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare(root)
            _, run = self.run_file(root, generated_at="2026-10-03T01:15:00+00:00")
            with self.assertRaises(ValueError):
                smoke._level(run, root)

    def test_economic_level_requires_complete_independent_replay(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare(root)
            _, run = self.run_file(root, latest_observed_session="2026-10-02",
                independent_lane_count=10, realized_decision_batches=1, benchmark_control_count=2,
                decision_phases=[{"decision_date": "2026-10-01", "phase": "REALIZED"}])
            result = {"economic_replay_verified": True, "economic_lane_count": 11, "verified_rows": 11}
            with patch.object(smoke, "verify_daily_economic_replay", return_value=result) as replay:
                self.assertEqual(smoke._level(run, root)[0], "ECONOMIC_PATHS_VERIFIED")
                replay.assert_called_once_with(run, repository_root=root)
            for invalid in ({**result, "economic_lane_count": 10},
                            {**result, "verified_rows": True},
                            {**result, "economic_replay_verified": 1}):
                with patch.object(smoke, "verify_daily_economic_replay", return_value=invalid):
                    with self.assertRaises(ValueError):
                        smoke._level(run, root)

    def test_pending_requires_receipt_and_no_later_session(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare(root)
            _, run = self.run_file(root, latest_observed_session="2026-10-01",
                decision_phases=[{"decision_date": "2026-10-01", "phase": "WAIT_FOR_NEXT_OBSERVED_SESSION"}])
            with self.assertRaises((ValueError, OSError)):
                smoke._level(run, root)
            final = root / smoke.acceptance.SEARCH / "final/2026-10-01/manifest.json"
            receipt = root / smoke.acceptance.ACCEPTANCE / "2026-10-01/receipt.json"
            for path in (final, receipt):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            bound = {"decision_date": "2026-10-01", "final_binding": {
                "path": str(final), "sha256": smoke._hash(final.read_bytes())}}
            with patch.object(smoke.acceptance, "verify_acceptance", return_value=bound) as verify:
                self.assertEqual(smoke._level(run, root)[0], "DECISION_PENDING_EXECUTION")
                verify.assert_called_once_with(receipt)
                run["latest_observed_session"] = "2026-10-02"
                with self.assertRaises(ValueError):
                    smoke._level(run, root)

    def test_second_daily_verification_is_required_after_stage_checks(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = self.prepare(root)
            _, run = self.run_file(root)
            with patch.object(smoke, "verify_daily_run_manifest", side_effect=[run, ValueError("source drift")]):
                with self.assertRaisesRegex(ValueError, "source drift"):
                    smoke.verify(root, before=before)


if __name__ == "__main__":
    unittest.main()
