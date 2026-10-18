from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import backtest.ndx_dynamic_shadow_activation_v3 as activation_v3

from backtest.ndx_dynamic_shadow_activation_v3 import (
    NdxDynamicShadowActivationV3Error, build_activation_v3_manifest,
    verify_activation_v3_manifest, verify_synthetic_budget_e2e,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v3/manifest.json"


class ActivationV3Test(unittest.TestCase):
    def test_canonical_activation_and_synthetic_rebuild(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            activation_v3, "MANIFEST", str(Path(directory) / "manifest.json")
        ), patch.object(
            activation_v3, "SYNTHETIC", str(Path(directory) / "synthetic.json")
        ), patch.object(
            activation_v3, "verify_activation_v2_manifest", return_value={}
        ):
            result = build_activation_v3_manifest(ROOT)
            synthetic = verify_synthetic_budget_e2e(result["synthetic_e2e"]["path"])
        self.assertEqual(result["status"], "READY_FOR_RESEARCH_AUTOMATION_MIGRATION_PLAN_ONLY")
        self.assertFalse(result["guards"]["external_task_migration_performed"])
        self.assertFalse(synthetic["scenarios"]["near_deadline_exact_refused"]["aggregation_allowed"])
        self.assertEqual(synthetic["scenarios"]["verified_resume"]["pending_shard_count"], 1)
        self.assertTrue(synthetic["claims"]["real_checkpoint_and_controller_verifiers_exercised"])
        self.assertTrue(synthetic["claims"]["dual_track_full_dynamic_k_verified"])
        self.assertTrue(synthetic["claims"]["malicious_job_plans_all_rejected"])
        self.assertTrue(result["controller_verifier"]["verified"])

    def test_noncanonical_or_tampered_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "canonical" / "manifest.json"
            synthetic = Path(directory) / "canonical" / "synthetic.json"
            with patch.object(activation_v3, "MANIFEST", str(manifest)), patch.object(
                activation_v3, "SYNTHETIC", str(synthetic)
            ), patch.object(
                activation_v3, "verify_activation_v2_manifest", return_value={}
            ):
                build_activation_v3_manifest(ROOT)
                copy = Path(directory) / "noncanonical.json"
                copy.write_bytes(manifest.read_bytes())
                with self.assertRaises(NdxDynamicShadowActivationV3Error):
                    verify_activation_v3_manifest(copy, repository_root=ROOT)
                payload = json.loads(manifest.read_text(encoding="utf-8"))
                payload["guards"]["partial_aggregation_forbidden"] = False
                manifest.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(NdxDynamicShadowActivationV3Error):
                    verify_activation_v3_manifest(manifest, repository_root=ROOT)


if __name__ == "__main__":
    unittest.main()
