from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import ndx_dynamic_shadow_runtime_v3_smoke as smoke


class RuntimeSmokeTests(unittest.TestCase):
    def fixture(self, root, before):
        path = root / smoke.LATEST
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_manifest_sha256": "fixture",
            "status": "RESEARCH_DAILY_COMPLETE",
            "latest_observed_session": "2026-09-04",
            "independent_lane_count": 0,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path, payload

    def test_fresh_run_and_exact_post_proof(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = smoke.snapshot(root)
            _, payload = self.fixture(root, before)
            with patch.object(smoke, "verify_daily_run_manifest", return_value=payload) as verifier:
                proof = smoke.verify(root, before=before)
                self.assertEqual(smoke.verify(root, expected=proof), proof)
                self.assertEqual(verifier.call_count, 2)

    def test_unchanged_run_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root, None)
            before = smoke.snapshot(root)
            with self.assertRaisesRegex(ValueError, "no fresh"):
                smoke.verify(root, before=before)

    def test_rewritten_old_run_does_not_count_as_new(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = smoke.snapshot(root)
            path, payload = self.fixture(root, before)
            payload["generated_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no fresh"):
                smoke.verify(root, before=before)

    def test_full_verifier_failure_propagates(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = smoke.snapshot(root)
            self.fixture(root, before)
            with patch.object(smoke, "verify_daily_run_manifest", side_effect=ValueError("bad artifact")):
                with self.assertRaisesRegex(ValueError, "bad artifact"):
                    smoke.verify(root, before=before)

    def test_future_timestamp_and_external_snapshot_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = smoke.snapshot(root)
            path, payload = self.fixture(root, before)
            payload["generated_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "future"):
                smoke.verify(root, before=before)
            self.fixture(root, before)
            before["latest_run_path"] = (root / "external.json").as_posix()
            with self.assertRaisesRegex(ValueError, "no fresh"):
                smoke.verify(root, before=before)

    def test_changed_expected_proof_is_not_accepted(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = smoke.snapshot(root)
            _, payload = self.fixture(root, before)
            with patch.object(smoke, "verify_daily_run_manifest", return_value=payload):
                proof = smoke.verify(root, before=before)
                proof["latest_run_sha256"] = "0" * 64
                with self.assertRaisesRegex(ValueError, "superseded"):
                    smoke.verify(root, expected=proof)

    def test_mutation_during_verification_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = smoke.snapshot(root)
            path, payload = self.fixture(root, before)
            def mutate(*args, **kwargs):
                path.write_text("{}", encoding="utf-8")
                return payload
            with patch.object(smoke, "verify_daily_run_manifest", side_effect=mutate):
                with self.assertRaisesRegex(ValueError, "changed during"):
                    smoke.verify(root, before=before)


if __name__ == "__main__":
    unittest.main()
