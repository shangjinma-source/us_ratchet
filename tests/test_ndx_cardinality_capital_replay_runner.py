from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.ndx_cardinality_capital_replay_runner import _result_is_resumable


class CardinalityCapitalReplayRunnerTests(unittest.TestCase):
    def test_resume_identity_locks_shortlist_cash_and_source_batch(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidates = root / "candidates.csv"
            frontiers = root / "frontiers.csv"
            header = (
                "decision_data_end,security_ids,issuer_ids,risk_chains,"
                "cross_cardinality_frontier_tags,"
                "cross_cardinality_constrained_frontier_tags\n"
            )
            candidates.write_text(header + "2024-01-01,s1,i1,compute,RETURN,RETURN\n", encoding="utf-8")
            frontiers.write_text("portfolio_id\np1\n", encoding="utf-8")
            from data.versioning import file_sha256
            path = root / "manifest.json"
            path.write_text(json.dumps({
                "manifest_type": "ndx_cardinality_real_training_smoke",
                "status": "TRAINING_DISCOVERY_ONLY_NOT_ADMISSION",
                "candidate_replay_mode": True,
                "promotion_allowed": False,
                "frontier_comparison_scope": "WITHIN_CARDINALITY_AND_CROSS_CARDINALITY",
                "candidate_replay_source": {
                    "sha256": "shortlist-v1",
                    "target_portfolio_cash_usd": 25000,
                    "source_batches": ["exact"],
                },
                "artifacts": {
                    "candidates": {"path": candidates.as_posix(), "rows": 1, "sha256": file_sha256(candidates)},
                    "frontiers": {"path": frontiers.as_posix(), "rows": 1, "sha256": file_sha256(frontiers)},
                },
            }), encoding="utf-8")
            self.assertTrue(_result_is_resumable(
                path, shortlist_hash="shortlist-v1", target_cash=25000,
                source_batch="exact",
            ))
            self.assertFalse(_result_is_resumable(
                path, shortlist_hash="shortlist-v2", target_cash=25000,
                source_batch="exact",
            ))
            self.assertFalse(_result_is_resumable(
                path, shortlist_hash="shortlist-v1", target_cash=5000,
                source_batch="exact",
            ))
            self.assertFalse(_result_is_resumable(
                path, shortlist_hash="shortlist-v1", target_cash=25000,
                source_batch="bounded",
            ))
            candidates.write_text(header + "damaged\n", encoding="utf-8")
            self.assertFalse(_result_is_resumable(
                path, shortlist_hash="shortlist-v1", target_cash=25000,
                source_batch="exact",
            ))


if __name__ == "__main__":
    unittest.main()
