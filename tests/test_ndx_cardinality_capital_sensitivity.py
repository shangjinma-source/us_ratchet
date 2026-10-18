from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backtest.ndx_cardinality_capital_sensitivity import (
    capital_replay_reason,
    evaluation_semantics_sha256,
    is_user_preference,
    noncapital_constraints_passed,
    shortlist_coordinate_rows,
)
from data.versioning import file_sha256
from scripts.ndx_cardinality_capital_sensitivity import (
    OUTPUT_FIELDS,
    CoordinateAccumulator,
    _candidate_manifests,
    _validate_capital_contract,
    _verified_candidate_path,
)


class CardinalityCapitalSensitivityTests(unittest.TestCase):
    def _row(self, portfolio_id, p50, p10, dd, distance, failures="", turnover=.1):
        return {
            "portfolio_id": portfolio_id, "weight_spec": "equal_weight",
            "tickers": "AMAT;AVGO;CDNS;GOOG" if portfolio_id == "pref" else portfolio_id,
            "weights": "", "return_p50": p50, "return_p10": p10,
            "max_drawdown_p50": dd, "max_drawdown_p90": dd,
            "target_012922_distance": distance, "turnover": turnover,
            "constraint_failure_reasons": failures,
        }

    def test_only_whole_lot_failure_is_noncapital_eligible(self):
        row = self._row("x", 1, 1, 1, 1, "WHOLE_LOT_EXECUTABILITY_FAILED")
        self.assertTrue(noncapital_constraints_passed(row))
        row["constraint_failure_reasons"] += ";DECLARED_MAX_SINGLE_WEIGHT_FAILED"
        self.assertFalse(noncapital_constraints_passed(row))

    def test_shortlist_keeps_distinct_frontiers_and_user_preference(self):
        rows = [
            self._row("return", .4, -.2, .5, .8),
            self._row("tail", .2, .1, .4, .5),
            self._row("drawdown", .1, 0, .1, .4),
            self._row("target", .15, .05, .3, .05),
            self._row("pref", .12, .02, .2, .2, "WHOLE_LOT_EXECUTABILITY_FAILED"),
            self._row("invalid", 9, 9, 0, 0, "DECLARED_MAX_SINGLE_WEIGHT_FAILED"),
        ]
        result = shortlist_coordinate_rows(
            rows, per_frontier=1,
            user_preference_tickers=["AMAT", "AVGO", "CDNS", "GOOG"],
        )
        ids = {row["portfolio_id"] for row in result}
        self.assertNotIn("invalid", ids)
        self.assertTrue({"return", "tail", "drawdown", "target", "pref"}.issubset(ids))
        pref = next(row for row in result if row["portfolio_id"] == "pref")
        self.assertIn("USER_PREFERENCE", pref["capital_replay_frontiers"])
        self.assertTrue(is_user_preference(pref, ["GOOG", "CDNS", "AVGO", "AMAT"]))

    def test_capital_change_always_requires_path_replay(self):
        self.assertEqual(
            capital_replay_reason(self._row("x", 0, 0, 0, 0), 5000, 25000),
            "CAPITAL_SCALE_CHANGED_REQUIRES_REPLAY",
        )

    def test_semantics_hash_changes_with_evaluator_hash(self):
        a = {"run_contract": {"spec_sha256": "s", "discovery_module_sha256": "a"}}
        b = {"run_contract": {"spec_sha256": "s", "discovery_module_sha256": "b"}}
        self.assertNotEqual(evaluation_semantics_sha256(a), evaluation_semantics_sha256(b))

    def test_pareto_shortlist_matches_canonical_drawdown_and_turnover_dimensions(self):
        dominant_except_turnover = self._row(
            "high-turnover", .40, .20, .20, .10, turnover=.50,
        )
        low_turnover = self._row(
            "low-turnover", .30, .10, .30, .20, turnover=.01,
        )
        result = shortlist_coordinate_rows(
            [dominant_except_turnover, low_turnover],
            per_frontier=10,
            user_preference_tickers=[],
        )
        selected = {row["portfolio_id"]: row for row in result}
        self.assertIn("PARETO", selected["low-turnover"]["capital_replay_frontiers"])
        self.assertIn("turnover", OUTPUT_FIELDS)

        accumulator = CoordinateAccumulator(limit=10, preference=[])
        for row in (dominant_except_turnover, low_turnover):
            accumulator.add(row, dict(row))
        streamed = {row["portfolio_id"]: row for row in accumulator.finish()}
        self.assertIn("PARETO", streamed["low-turnover"]["capital_replay_frontiers"])

    def test_capital_contract_rejects_infeasible_cash_buffer_and_cost(self):
        valid = {
            "source_training_cash_usd": 5000,
            "primary_full_sleeve_cash_usd": 25000,
            "minimum_cash_buffer_usd": 100,
            "transaction_cost_bps": 10,
        }
        self.assertEqual(_validate_capital_contract(valid), (5000, 25000, 100, 10))
        for change in (
            {"source_training_cash_usd": 100},
            {"primary_full_sleeve_cash_usd": 100},
            {"transaction_cost_bps": -1},
        ):
            with self.subTest(change=change):
                with self.assertRaisesRegex(ValueError, "feasible finite"):
                    _validate_capital_contract({**valid, **change})

    def test_completed_checkpoint_chain_must_remain_hash_complete(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            result_path = (root / "result.json").resolve()
            result_path.write_text('{"status":"ok"}\n', encoding="utf-8")
            checkpoint_path = (root / "checkpoint.json").resolve()
            checkpoint_path.write_text(json.dumps({
                "status": "COMPLETED",
                "result_manifest_path": result_path.as_posix(),
                "result_manifest_sha256": file_sha256(result_path),
            }), encoding="utf-8")
            index_path = (root / "checkpoint_index.csv").resolve()
            with index_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "status", "checkpoint_path", "checkpoint_file_sha256",
                ])
                writer.writeheader()
                writer.writerow({
                    "status": "COMPLETED",
                    "checkpoint_path": checkpoint_path.as_posix(),
                    "checkpoint_file_sha256": file_sha256(checkpoint_path),
                })
            run_manifest = {
                "planned_job_count": 1,
                "artifacts": {"checkpoint_index": {
                    "path": index_path.as_posix(),
                    "rows": 1,
                    "sha256": file_sha256(index_path),
                }},
            }
            self.assertEqual(
                _candidate_manifests(root / "manifest.json", run_manifest),
                [result_path],
            )
            result_path.write_text('{"status":"tampered"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                _candidate_manifests(root / "manifest.json", run_manifest)

    def test_candidate_artifact_hash_rows_and_source_cash_are_locked(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_path = (root / "candidates.csv").resolve()
            candidate_path.write_text("portfolio_id\nabc\n", encoding="utf-8")
            manifest = {
                "manifest_type": "ndx_cardinality_real_training_smoke",
                "research_track": "portfolio_optimization",
                "migration_control_included": False,
                "promotion_allowed": False,
                "portfolio_cash_usd": 5000,
                "artifacts": {"candidates": {
                    "path": candidate_path.as_posix(),
                    "rows": 1,
                    "sha256": file_sha256(candidate_path),
                }},
            }
            self.assertEqual(
                _verified_candidate_path(root / "manifest.json", manifest, source_cash=5000),
                (candidate_path, 1),
            )
            with self.assertRaisesRegex(ValueError, "capital/safety"):
                _verified_candidate_path(root / "manifest.json", manifest, source_cash=25000)
            candidate_path.write_text("portfolio_id\ntampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact mismatch"):
                _verified_candidate_path(root / "manifest.json", manifest, source_cash=5000)


if __name__ == "__main__":
    unittest.main()
