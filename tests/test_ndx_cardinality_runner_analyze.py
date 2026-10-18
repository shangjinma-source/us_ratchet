import unittest

from scripts.ndx_cardinality_runner_analyze import (
    completed_manifests,
    merge_completed_manifest_groups,
    validate_runner_semantics,
)


class NdxCardinalityRunnerAnalyzeTests(unittest.TestCase):
    def test_missing_runner_manifest_fails(self):
        with self.assertRaises(FileNotFoundError):
            completed_manifests(__import__("pathlib").Path("missing-runner-manifest.json"))

    def test_merge_rejects_duplicate_track_date_k(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text(json.dumps({"holding_count": 4}), encoding="utf-8")
            batch = {("strict_technology", "2024-01-02"): [path]}
            with self.assertRaisesRegex(Exception, "duplicate completed"):
                merge_completed_manifest_groups([batch, batch])

    def test_semantic_contract_rejects_different_evaluator_hashes(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temporary:
            paths = []
            for name, module_hash in (("exact", "aaa"), ("bounded", "bbb")):
                path = Path(temporary) / f"{name}.json"
                path.write_text(json.dumps({
                    "run_contract": {
                        "spec_sha256": "spec",
                        "discovery_module_sha256": module_hash,
                        "whole_lot_module_sha256": "whole",
                    }
                }), encoding="utf-8")
                paths.append(path)
            with self.assertRaisesRegex(Exception, "semantics are incompatible"):
                validate_runner_semantics(paths)

    def test_semantic_contract_accepts_identical_batches(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temporary:
            payload = {"run_contract": {
                "spec_sha256": "spec", "discovery_module_sha256": "same",
                "whole_lot_module_sha256": "whole",
            }}
            paths = []
            for name in ("one", "two"):
                path = Path(temporary) / f"{name}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                paths.append(path)
            result = validate_runner_semantics(paths)
            self.assertTrue(result["compatible"])
            self.assertEqual(len(result["batches"]), 2)


if __name__ == "__main__":
    unittest.main()
