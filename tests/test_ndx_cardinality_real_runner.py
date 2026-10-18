import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.ndx_cardinality_real_runner import (
    NdxCardinalityRealRunnerError,
    build_job_queue,
    checkpoint_with_hash,
    coordinate_payload,
    safe_part,
    verify_completed_checkpoint,
)
from data.versioning import file_sha256


class NdxCardinalityRealRunnerTests(unittest.TestCase):
    def test_queue_filters_ready_and_sorts_numeric_k(self):
        jobs = pd.DataFrame([
            {"universe_track": "strict_technology", "selection_date": "2024-01-02", "holding_count": 10, "shard_id": 0, "coordinate_sha256": "a", "degraded_research_job_ready": True, "degraded_search_method": "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND"},
            {"universe_track": "strict_technology", "selection_date": "2024-01-02", "holding_count": 2, "shard_id": 0, "coordinate_sha256": "b", "degraded_research_job_ready": True, "degraded_search_method": "EXACT_ENUMERATION"},
            {"universe_track": "strict_technology", "selection_date": "2024-01-02", "holding_count": 1, "shard_id": 0, "coordinate_sha256": "c", "degraded_research_job_ready": False, "degraded_search_method": "EXACT_ENUMERATION"},
        ])
        queue = build_job_queue(jobs, holding_counts=[2, 10])
        self.assertEqual(queue["holding_count"].tolist(), [2, 10])
        exact = build_job_queue(jobs, search_classes=["EXACT_ENUMERATION"])
        self.assertEqual(exact["holding_count"].tolist(), [2])

    def test_path_part_rejects_escape(self):
        self.assertEqual(safe_part("strict_technology"), "strict_technology")
        with self.assertRaises(NdxCardinalityRealRunnerError):
            safe_part("../escape")

    def test_completed_checkpoint_detects_artifact_damage(self):
        coordinate = coordinate_payload({
            "universe_track": "strict_technology", "selection_date": "2024-06-03",
            "holding_count": 2, "shard_id": 0, "coordinate_sha256": "source",
        }, "run")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "job"
            output.mkdir()
            artifact = output / "training_candidates.csv"
            artifact.write_text("x\n1\n", encoding="utf-8")
            manifest_path = output / "manifest.json"
            manifest = {
                "manifest_type": "ndx_cardinality_real_training_smoke",
                "universe_track": coordinate["universe_track"],
                "selection_date": coordinate["selection_date"],
                "holding_count": coordinate["holding_count"],
                "research_track": "portfolio_optimization",
                "migration_control_included": False,
                "whole_lot_execution_mode": "CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_REAL_CLOSES",
                "whole_lot_execution_price_basis": "unadjusted_nominal_trade_price",
                "adjusted_return_prices_used_for_whole_lot_shares": False,
                "selection_date_or_later_execution_prices_used": False,
                "whole_lot_shares_and_cash_carried_between_rebalances": True,
                "whole_lot_transaction_costs_deducted_from_cash": True,
                "whole_lot_constraints_checked_daily": True,
                "promotion_allowed": False, "fresh_oos_consumed": False,
                "selection_date_or_later_returns_read": False,
                "artifacts": {"candidates": {"path": artifact.as_posix(), "rows": 1, "sha256": file_sha256(artifact)}},
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            checkpoint_path = Path(temporary) / "checkpoint.json"
            checkpoint = checkpoint_with_hash({
                **coordinate, "status": "COMPLETED",
                "result_manifest_path": manifest_path.as_posix(),
                "result_manifest_sha256": file_sha256(manifest_path),
            })
            checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
            verify_completed_checkpoint(checkpoint_path, coordinate=coordinate, expected_output_dir=output)
            referenced_coordinate = {**coordinate, "run_fingerprint": "new-run", "coordinate_id": "new-id"}
            referenced_path = Path(temporary) / "referenced.json"
            referenced = checkpoint_with_hash({
                **referenced_coordinate, "status": "COMPLETED",
                "result_manifest_path": manifest_path.as_posix(),
                "result_manifest_sha256": file_sha256(manifest_path),
                "result_storage_mode": "REFERENCED_COMPATIBLE_PRIOR_RUN",
                "source_checkpoint_path": checkpoint_path.as_posix(),
                "source_checkpoint_sha256": file_sha256(checkpoint_path),
            })
            referenced_path.write_text(json.dumps(referenced), encoding="utf-8")
            verify_completed_checkpoint(
                referenced_path, coordinate=referenced_coordinate,
                expected_output_dir=Path(temporary) / "new-job",
            )
            artifact.write_text("x\n2\n", encoding="utf-8")
            with self.assertRaises(NdxCardinalityRealRunnerError):
                verify_completed_checkpoint(checkpoint_path, coordinate=coordinate, expected_output_dir=output)


if __name__ == "__main__":
    unittest.main()
