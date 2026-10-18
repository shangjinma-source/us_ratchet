import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from backtest.ndx_incumbent_frontier import (
    NdxIncumbentFrontierError,
    read_verified_incumbent_curve_bundle,
)


class NdxIncumbentCurveBundleTests(unittest.TestCase):
    def _write_bundle(self, root: Path) -> tuple[Path, Path]:
        manifest_path = root / "manifest.json"
        manifest = {
            "experiment_id": "ndx_v8b_test",
            "planned_jobs": 3,
            "completed_jobs": 3,
            "failed_jobs": 0,
        }
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8"
        )
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        curves_path = root / "portfolio_curves.json"
        payload = {
            "schema_version": 2,
            "available": True,
            "research_only": True,
            "source_experiment_id": "ndx_v8b_test",
            "source_manifest_sha256": manifest_hash,
            "secondary_reference": "012922",
            "dates": ["2024-01-02", "2024-01-03"],
            "nav_series": {
                "current_config": [1.0, 1.1],
                "solution_1": [1.0, 1.05],
                "012922": [1.0, 1.02],
            },
            "drawdown_series": {
                "current_config": [0.0, 0.0],
                "solution_1": [0.0, -0.01],
                "012922": [0.0, -0.02],
            },
            "solutions": [{"solution_id": "solution_1"}],
        }
        curves_path.write_text(json.dumps(payload), encoding="utf-8")
        return curves_path, manifest_path

    def test_verified_bundle_requires_manifest_identity_and_aligned_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            curves_path, manifest_path = self._write_bundle(Path(tmp))

            payload = read_verified_incumbent_curve_bundle(
                curves_path, manifest_path
            )

        self.assertTrue(payload["available"])
        self.assertEqual(len(payload["dates"]), 2)

    def test_manifest_change_invalidates_static_curve_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            curves_path, manifest_path = self._write_bundle(Path(tmp))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["completed_jobs"] = 2
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(
                NdxIncumbentFrontierError, "source manifest changed"
            ):
                read_verified_incumbent_curve_bundle(curves_path, manifest_path)

    def test_misaligned_curve_series_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            curves_path, manifest_path = self._write_bundle(Path(tmp))
            payload = json.loads(curves_path.read_text(encoding="utf-8"))
            payload["nav_series"]["solution_1"] = [1.0]
            curves_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(
                NdxIncumbentFrontierError, "does not align with dates"
            ):
                read_verified_incumbent_curve_bundle(curves_path, manifest_path)

    def test_non_finite_curve_values_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            curves_path, manifest_path = self._write_bundle(Path(tmp))
            payload = json.loads(curves_path.read_text(encoding="utf-8"))
            payload["drawdown_series"]["solution_1"] = [0.0, None]
            curves_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(
                NdxIncumbentFrontierError, "contains non-finite values"
            ):
                read_verified_incumbent_curve_bundle(curves_path, manifest_path)


if __name__ == "__main__":
    unittest.main()
