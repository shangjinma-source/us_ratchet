"""Independent attacks on persisted conditional-repair evidence."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backtest import ndx_conditional_repair_batch as batch
import test_ndx_conditional_repair_batch as storage_fixtures


class ConditionalRepairIndependentTests(unittest.TestCase):
    def test_resigned_economic_checkpoint_is_rejected_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan, rebuilt = storage_fixtures.NdxConditionalRepairBatchTests()._storage_fixture(root)
            output = root / "data/cache/research/independent"
            with (
                mock.patch.dict(batch.EXPECTED_COUNTS, plan["counts"], clear=True),
                mock.patch.object(batch, "build_conditional_repair_plan", return_value=plan),
                mock.patch.object(batch, "_load_source_checkpoint", return_value={}),
                mock.patch.object(batch, "rebuild_candidate_result", side_effect=rebuilt),
            ):
                batch.execute_conditional_repair_batch(repository_root=root, output_root=output)
                run_dir = output / "runs" / plan["plan_fingerprint"]
                path = batch._checkpoint_path(run_dir, plan["candidates"][1])
                checkpoint = json.loads(path.read_bytes())
                checkpoint["result"]["conditional_c"]["successful_repair_count"] = 999
                checkpoint.pop("checkpoint_sha256")
                checkpoint["checkpoint_sha256"] = batch._canonical_sha256(checkpoint)
                raw = batch._json_bytes(checkpoint)
                path.write_bytes(raw)
                manifest_before = (run_dir / "manifest.json").read_bytes()
                for operation, extra in (
                    (batch.verify_conditional_repair_batch, {}),
                    (batch.execute_conditional_repair_batch, {"resume": True}),
                ):
                    with self.assertRaisesRegex(
                        batch.NdxConditionalRepairBatchError, "economic result does not rebuild"
                    ):
                        operation(repository_root=root, output_root=output, **extra)
                    self.assertEqual(path.read_bytes(), raw)
                    self.assertEqual((run_dir / "manifest.json").read_bytes(), manifest_before)


if __name__ == "__main__":
    unittest.main()
