"""Daily4 root checks, isolated from the activation4-frozen test namespace."""
from contextlib import ExitStack
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import pandas as pd
from backtest import ndx_dynamic_shadow_daily_v3 as adapter
from data.versioning import file_sha256


class Daily4RuntimeProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(TemporaryDirectory())).resolve()
        artifacts = {}
        real_root = Path(__file__).resolve().parents[1]
        for name, relative in adapter.RUNTIME_PATHS.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((real_root / relative).read_bytes() if name == "daily_contract" else b"fixture runtime\n")
            artifacts[name] = dict(path=path.as_posix(), sha256=file_sha256(path))
        artifacts.update(realized_batch_manifests={}, selector_lane_ledgers={},
                         original_8_control_ledger=None, target_012922_trace_ledger=None,
                         three_way_alignment_manifest=None, nominal_price_evidence_manifest=None)
        self.run = dict(schema_version=1, manifest_type="ndx_dynamic_shadow_daily_run",
            generated_at="2026-10-03T01:00:00+00:00", status="RESEARCH_DAILY_COMPLETE",
            calendar_manifest_sha256=artifacts["observed_calendar_manifest"]["sha256"],
            latest_observed_session="2026-10-02", decision_phases=[],
            realized_decision_batches=0, independent_lane_count=0, benchmark_control_count=0,
            appended_lane_path_records=0, original_8_control_rows=0, target_012922_trace_rows=0,
            target_012922_pending_rows=0, target_012922_source_error=None,
            three_way_alignment_manifest=None, research_artifacts=artifacts,
            single_instance_lock_used=True, historical_candidate_replay_used=False,
            retrospective_decision_backfill_used=False, automation_registered=False,
            promotion_allowed=False, live_mutation=False)
        self.path = self.root / adapter.RUN_RELATIVE
        self.path.parent.mkdir(parents=True)
        self.calendar = self.stack.enter_context(patch.object(adapter.reviewed,
            "load_reviewed_calendar_projection", return_value=({}, None,
            pd.DataFrame({"session_date": [pd.Timestamp("2026-10-02")]}))))
        self.write()

    def write(self):
        self.run.pop("run_manifest_sha256", None)
        self.run["run_manifest_sha256"] = adapter.reviewed.v1.canonical_sha256(self.run)
        self.path.write_text(json.dumps(self.run), encoding="utf-8")

    def test_valid_empty_run_is_read_only(self):
        before = self.path.read_bytes()
        self.assertEqual(adapter.verify_daily_run_manifest(self.path, repository_root=self.root), self.run)
        self.assertEqual(self.path.read_bytes(), before)
        self.calendar.assert_called_once()

    def test_noncanonical_run_is_rejected(self):
        other = self.root / "other.json"
        other.write_bytes(self.path.read_bytes())
        with self.assertRaisesRegex(ValueError, "not canonical"):
            adapter.verify_daily_run_manifest(other, repository_root=self.root)

    def test_rehashed_old_runtime_is_rejected(self):
        old = self.root / "scripts/ndx_dynamic_shadow_daily_v3.py"
        old.write_bytes(b"old runtime\n")
        self.run["research_artifacts"]["daily_script"] = dict(path=old.as_posix(), sha256=file_sha256(old))
        self.write()
        with self.assertRaisesRegex(ValueError, "runtime provenance"):
            adapter.verify_daily_run_manifest(self.path, repository_root=self.root)

    def test_calendar_latest_mismatch_is_rejected(self):
        self.calendar.return_value = ({}, None, pd.DataFrame({"session_date": [pd.Timestamp("2026-10-01")]}))
        with self.assertRaisesRegex(ValueError, "latest observed session"):
            adapter.verify_daily_run_manifest(self.path, repository_root=self.root)

    def test_artifact_hash_is_still_checked_by_real_parent(self):
        (self.root / adapter.RUNTIME_PATHS["daily_script"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "path/hash changed"):
            adapter.verify_daily_run_manifest(self.path, repository_root=self.root)
