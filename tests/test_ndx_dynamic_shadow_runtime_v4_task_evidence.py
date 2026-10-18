"""Task metadata protocol tests; Windows and artifact validation are isolated."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_dynamic_shadow_runtime_v4_task_evidence as evidence

ROOT = Path(__file__).resolve().parents[1]


class TaskEvidenceTests(unittest.TestCase):
    def fixture(self):
        now = datetime.now(timezone.utc)
        old = dict(task_name=evidence.NEW_V4_TASK, task_path="\\", state="Ready",
            execute=str(evidence.PYTHON), arguments=f'-B "{ROOT / evidence.DAILY_RELATIVE}" --execute',
            working_directory=str(ROOT), definition_sha256="a" * 64,
            last_run_utc=(now - timedelta(days=1)).isoformat(), last_result=0)
        current = {**old, "last_run_utc": (now - timedelta(minutes=2)).isoformat()}
        before = {"schema_version": 1, "captured_at_utc": (now - timedelta(minutes=5)).isoformat(),
                  "task_before": old, "artifact_before": {"captured_at_utc": (now - timedelta(minutes=6)).isoformat()}}
        artifact = {"run_generated_at": (now - timedelta(minutes=1)).isoformat(),
                    "evidence_level": "PRE_DECISION_OPERATIONAL_ONLY"}
        return before, current, artifact

    def verify(self, before, tasks, artifact):
        with patch.object(evidence, "_task", side_effect=tasks), \
                patch.object(evidence.smoke, "verify", return_value=artifact) as verify:
            result = evidence.verify(ROOT, before)
            verify.assert_called_once_with(ROOT, before=before["artifact_before"])
            return result

    def test_new_task_run_and_current_artifact_are_both_required(self):
        before, task, artifact = self.fixture()
        result = self.verify(before, [task, task], artifact)
        self.assertIs(result["task_metadata_and_artifact_verified"], True)
        self.assertIs(result["task_instance_event_log_verified"], False)
        self.assertIs(result["authorization_granted"], False)

    def test_old_run_failure_running_or_definition_drift_rejected(self):
        before, task, artifact = self.fixture()
        for changed in ({**task, "last_run_utc": before["task_before"]["last_run_utc"]},
                        {**task, "last_result": 1}, {**task, "last_result": False},
                        {**task, "state": "Running"}, {**task, "definition_sha256": "b" * 64},
                        {**task, "working_directory": str(ROOT.parent)}):
            with self.assertRaises(ValueError):
                self.verify(before, [changed], artifact)

    def test_artifact_from_before_the_observed_task_is_rejected(self):
        before, task, artifact = self.fixture()
        artifact["run_generated_at"] = before["captured_at_utc"]
        with self.assertRaisesRegex(ValueError, "predates"):
            self.verify(before, [task], artifact)

    def test_task_change_during_artifact_proof_is_rejected(self):
        before, task, artifact = self.fixture()
        with self.assertRaisesRegex(ValueError, "changed during"):
            self.verify(before, [task, {**task, "state": "Running"}], artifact)

    def test_bad_artifact_and_unreadable_task_fail_closed(self):
        before, task, _ = self.fixture()
        with patch.object(evidence, "_task", return_value=task), \
                patch.object(evidence.smoke, "verify", side_effect=ValueError("bad artifact")):
            with self.assertRaisesRegex(ValueError, "bad artifact"):
                evidence.verify(ROOT, before)
        with patch.object(evidence, "_task", side_effect=OSError("unavailable")):
            with self.assertRaises(OSError):
                evidence.verify(ROOT, before)

    def test_snapshot_requires_stable_definition_and_stores_real_artifact_snapshot(self):
        _, task, artifact = self.fixture()
        with patch.object(evidence, "_task", side_effect=[task, task]), \
                patch.object(evidence.smoke, "snapshot", return_value=artifact):
            before = evidence.snapshot(ROOT)
            self.assertEqual(before["artifact_before"], artifact)
        with patch.object(evidence, "_task", side_effect=[task, {**task, "state": "Running"}]), \
                patch.object(evidence.smoke, "snapshot", return_value=artifact):
            with self.assertRaises(ValueError):
                evidence.snapshot(ROOT)

    def test_snapshot_schema_boolean_and_future_time_rejected(self):
        before, task, artifact = self.fixture()
        for changed in ({**before, "schema_version": True},
                        {**before, "captured_at_utc": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}):
            with self.assertRaises(ValueError):
                self.verify(changed, [task], artifact)

    def test_artifact_snapshot_cannot_postdate_completed_before_snapshot(self):
        before, task, artifact = self.fixture()
        before["artifact_before"]["captured_at_utc"] = task["last_run_utc"]
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.verify(before, [task], artifact)

    def test_same_second_task_timestamp_is_not_relaxed_into_fresh_evidence(self):
        before, task, artifact = self.fixture()
        captured = datetime.now(timezone.utc) - timedelta(minutes=5)
        captured = captured.replace(microsecond=500000)
        before["captured_at_utc"] = captured.isoformat()
        task["last_run_utc"] = captured.replace(microsecond=0).isoformat()
        with self.assertRaises(ValueError):
            self.verify(before, [task], artifact)
        task["last_run_utc"] = (captured.replace(microsecond=0) + timedelta(seconds=1)).isoformat()
        self.assertTrue(self.verify(before, [task, task], artifact)["task_metadata_and_artifact_verified"])

    def test_windows_collector_protocol_and_timeout(self):
        _, task, _ = self.fixture()
        raw = {key: value for key, value in task.items() if key != "definition_sha256"}
        raw["definition_xml"] = "<Task>synthetic</Task>"
        with patch.object(evidence.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps(raw))) as run:
            result = evidence._task(ROOT)
            self.assertEqual(len(result["definition_sha256"]), 64)
            self.assertNotIn("definition_xml", result)
            self.assertEqual(run.call_args.kwargs["timeout"], 60)
        raw["last_result"] = False
        with patch.object(evidence.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps(raw))):
            with self.assertRaises(ValueError):
                evidence._task(ROOT)


if __name__ == "__main__":
    unittest.main()
