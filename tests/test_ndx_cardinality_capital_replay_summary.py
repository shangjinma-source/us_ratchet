from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from backtest.ndx_cardinality_capital_replay_summary import (
    CAPITAL_MANIFEST_RELATIVE,
    CHILD_ARTIFACT_NAMES,
    CHILD_INPUT_NAMES,
    EXECUTION_COLUMNS,
    IDENTITY_COLUMNS,
    NdxCardinalityCapitalReplaySummaryError,
    RISK_COLUMNS,
    ROLLING_COLUMNS,
    SHORTLIST_RELATIVE,
    TOP_MANIFEST_RELATIVE,
    build_capital_replay_summary,
    verify_summary_bundle,
    write_summary_bundle,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class ReplayFixture:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.replay_root = (self.root / TOP_MANIFEST_RELATIVE).parent
        self.shared_inputs: dict[str, dict[str, object]] = {}
        for name in sorted(CHILD_INPUT_NAMES):
            path = (
                self.root / "data/cache/funds/012922.csv"
                if name == "target_nav"
                else self.root / "fixture_inputs" / f"{name}.txt"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "date,value\n2024-01-01,1\n"
                if name == "target_nav" else f"historical {name}\n",
                encoding="utf-8",
            )
            self.shared_inputs[name] = {"path": path.as_posix(), "sha256": _sha(path)}
        self.jobs = [
            ("exact_batch", "strict_technology", "2024-01-02", 4, "EXACT_ENUMERATION"),
            ("exact_batch", "strict_technology", "2024-02-01", 12, "EXACT_ENUMERATION"),
            (
                "bounded_batch", "technology_plus_adjacent", "2024-02-01", 9,
                "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND",
            ),
        ]
        self.child_manifests: list[Path] = []
        self._build()

    def candidate(
        self, selection_date: str, k: int, *, eligible: bool = True,
        tickers: list[str] | None = None,
    ) -> dict[str, object]:
        tickers = tickers or [f"T{index:02d}" for index in range(k)]
        weight = 1.0 / k
        row: dict[str, object] = {
            key: "0.1" for key in ROLLING_COLUMNS | RISK_COLUMNS | EXECUTION_COLUMNS
        }
        row.update({key: "True" for key in (
            "fit_strictly_before_evaluation", "declared_max_single_passed",
            "declared_security_top3_weight_passed",
            "declared_risk_chain_top1_weight_passed", "declared_effective_n_passed",
            "liquidity_constraint_passed", "whole_lot_executable_all_windows",
            "whole_lot_cash_buffer_preserved",
            "whole_lot_constraints_preserved_all_days", "declared_constraints_passed",
        )})
        row.update({
            "selection_date": selection_date,
            "decision_data_end": "2023-12-29",
            "portfolio_id": f"p{k}",
            "holding_count": str(k),
            "weight_spec": "equal_weight",
            "tickers": ";".join(tickers),
            "weights": ";".join(f"{ticker}:{weight:.12f}" for ticker in tickers),
            "security_ids": ";".join(f"security:{index:04d}" for index in range(k)),
            "issuer_ids": ";".join(f"issuer:{index:04d}" for index in range(k)),
            "risk_chains": ";".join("energy_technology" for _ in tickers),
            "rolling_fit_window_count": "8",
            "last_fit_evaluation_boundary": "2023-12-28<2023-12-29",
            "return_p50": "0.12",
            "return_p10": "-0.03",
            "max_drawdown_p50": "0.18",
            "max_drawdown_p90": "0.25",
            # Deliberately distinct from candidate marginal metrics: these are
            # stored paired statistics and must survive without recomputation.
            "paired_return_p50_vs_incumbent": "0.007",
            "paired_return_p10_vs_incumbent": "0.002",
            "paired_drawdown_cost_p50_vs_incumbent": "-0.004",
            "paired_drawdown_cost_p90_vs_incumbent": "-0.001",
            "return_p50_vs_012922": "0.011",
            "return_p10_vs_012922": "0.003",
            "max_drawdown_p50_vs_012922": "-0.002",
            "max_drawdown_p90_vs_012922": "0.006",
            "target_012922_distance": "0.44",
            "portfolio_cash_usd": "25000",
            "minimum_cash_buffer_usd": "100",
            "whole_lot_rebalance_count": "4",
            "whole_lot_share_change_count": "9",
            "whole_lot_total_trade_notional_usd": "12000",
            "whole_lot_total_transaction_cost_usd": "12",
            "whole_lot_min_cash_usd": "120",
            "whole_lot_terminal_value_usd": "27000",
            "whole_lot_path_return_net": "0.08",
            "whole_lot_path_max_drawdown": "0.16",
            "whole_lot_initial_shares": ";".join(f"{ticker}:1" for ticker in tickers),
            "whole_lot_terminal_shares": ";".join(f"{ticker}:2" for ticker in tickers),
            "whole_lot_rebalance_trace_sha256": "a" * 64,
            "whole_lot_execution_mode":
                "CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_REAL_CLOSES",
            "constraint_failure_reasons": "",
            "search_mode": "LOCKED_CANDIDATE_CAPITAL_REPLAY",
            "promotion_allowed": "False",
            "return_basis": "NET_OF_MODELED_ENTRY_TURNOVER_COST",
        })
        if not eligible:
            row.update({
                "declared_constraints_passed": "False",
                "whole_lot_executable_all_windows": "False",
                "whole_lot_constraints_preserved_all_days": "False",
                "constraint_failure_reasons": "WHOLE_LOT_EXECUTABILITY_FAILED",
            })
        return row

    def _source_run(self, batch: str, search_class: str) -> dict[str, object]:
        path = self.root / "source_runs" / batch / "manifest.json"
        semantics = {"forward_horizon_sessions": 126, "step_sessions": 21}
        payload = {
            "manifest_type": "ndx_cardinality_real_training_runner",
            "research_track": "portfolio_optimization",
            "migration_control_included": False,
            "failed": 0,
            "fresh_oos_consumed": False,
            "promotion_allowed": False,
            "run_contract": {
                "job_search_classes": [search_class],
                **semantics,
            },
        }
        _write_json(path, payload)
        return {
            "source_batch": batch,
            "run_manifest": path.as_posix(),
            "run_manifest_sha256": _sha(path),
            "evaluation_semantics": semantics,
            "evaluation_semantics_sha256": _canonical_hash(semantics),
        }

    def _build_child(self, batch: str, track: str, date: str, k: int) -> dict[str, object]:
        child_dir = self.replay_root / batch / track / date
        candidate_path = child_dir / "training_candidates.csv"
        preferred = ["AMAT", "AVGO", "CDNS", "GOOG"] if k == 4 else None
        rows = [
            self.candidate(date, k, tickers=preferred),
            self.candidate(date, k, eligible=False),
        ]
        fields = sorted(IDENTITY_COLUMNS | ROLLING_COLUMNS | RISK_COLUMNS | EXECUTION_COLUMNS)
        _write_csv(candidate_path, rows, fields)
        artifacts: dict[str, dict[str, object]] = {}
        names = {
            "candidates": "training_candidates.csv",
            "frontiers": "training_frontiers.csv",
            "price_inventory": "price_input_inventory.csv",
            "lifecycle_coverage": "lifecycle_coverage.csv",
            "workbook": "ndx_cardinality_real_training_smoke.xlsx",
        }
        for artifact_name in sorted(CHILD_ARTIFACT_NAMES):
            path = child_dir / names[artifact_name]
            if artifact_name == "candidates":
                artifact_rows = len(rows)
            elif artifact_name == "workbook":
                path.write_bytes(b"fixture workbook")
                artifact_rows = None
            else:
                _write_csv(path, [{"value": artifact_name}], ["value"])
                artifact_rows = 1
            artifacts[artifact_name] = {
                "path": path.as_posix(), "rows": artifact_rows, "sha256": _sha(path),
            }
        manifest = {
            "schema_version": 1,
            "manifest_type": "ndx_cardinality_real_training_smoke",
            "status": "TRAINING_DISCOVERY_ONLY_NOT_ADMISSION",
            "research_track": "portfolio_optimization",
            "migration_control_included": False,
            "universe_track": track,
            "selection_date": date,
            "training_end": "2023-12-29",
            "training_return_rows": 800,
            "holding_count": 0,
            "holding_counts": [k],
            "candidate_replay_mode": True,
            "portfolio_cash_usd": 25000.0,
            "fit_strictly_before_selection": True,
            "return_data_read": True,
            "selection_date_or_later_returns_read": False,
            "portfolio_returns_calculated": True,
            "fresh_oos_consumed": False,
            "promotion_allowed": False,
            "live_config_changed": False,
            "state_changed": False,
            "today_advice_changed": False,
            "whole_lot_execution_mode":
                "CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_REAL_CLOSES",
            "whole_lot_execution_price_basis": "unadjusted_nominal_trade_price",
            "adjusted_return_prices_used_for_whole_lot_shares": False,
            "selection_date_or_later_execution_prices_used": False,
            "whole_lot_shares_and_cash_carried_between_rebalances": True,
            "whole_lot_transaction_costs_deducted_from_cash": True,
            "whole_lot_constraints_checked_daily": True,
            "candidate_replay_source": {
                "path": (self.root / SHORTLIST_RELATIVE).as_posix(),
                "sha256": _sha(self.root / SHORTLIST_RELATIVE),
                "source_batches": [batch],
                "target_portfolio_cash_usd": 25000.0,
            },
            "search_audit": {
                "search_mode": "LOCKED_CANDIDATE_CAPITAL_REPLAY",
                "search_exhaustive": False,
                "optimality_claim_allowed": False,
                "holding_counts": [k],
            },
            "inputs": self.shared_inputs,
            "artifacts": artifacts,
        }
        manifest_path = child_dir / "manifest.json"
        _write_json(manifest_path, manifest)
        self.child_manifests.append(manifest_path)
        return {
            "source_batch": batch,
            "universe_track": track,
            "selection_date": date,
            "holding_counts": str(k),
            "shortlist_rows": str(len(rows)),
            "output_dir": child_dir.as_posix(),
            "status": "COMPLETED",
        }

    def _build(self) -> None:
        shortlist = self.root / SHORTLIST_RELATIVE
        _write_csv(shortlist, [{"portfolio_id": "locked"}], ["portfolio_id"])
        source_runs = [
            self._source_run("exact_batch", "EXACT_ENUMERATION"),
            self._source_run("bounded_batch", "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND"),
        ]
        capital_path = self.root / CAPITAL_MANIFEST_RELATIVE
        capital = {
            "schema_version": 1,
            "manifest_type": "ndx_cardinality_capital_sensitivity",
            "research_track": "portfolio_optimization",
            "migration_control_included": False,
            "cross_runner_semantics_compatible": False,
            "cross_runner_merge_allowed": False,
            "target_replay_cash_usd": 25000.0,
            "minimum_cash_buffer_usd": 100.0,
            "transaction_cost_bps": 10.0,
            "fresh_oos_consumed": False,
            "promotion_allowed": False,
            "source_runs": source_runs,
            "counts": {"capital_replay_shortlist_rows": 1},
            "artifacts": {
                "shortlist": {
                    "path": shortlist.as_posix(), "rows": 1, "sha256": _sha(shortlist),
                }
            },
        }
        _write_json(capital_path, capital)
        job_rows = [self._build_child(*job[:4]) for job in self.jobs]
        index_path = (self.root / TOP_MANIFEST_RELATIVE).parent / "job_index.csv"
        fields = [
            "source_batch", "universe_track", "selection_date", "holding_counts",
            "shortlist_rows", "output_dir", "status",
        ]
        _write_csv(index_path, job_rows, fields)
        top_path = self.root / TOP_MANIFEST_RELATIVE
        top = {
            "schema_version": 1,
            "manifest_type": "ndx_cardinality_capital_replay_runner",
            "generated_at": "2026-09-05T01:09:50+08:00",
            "status": "CAPITAL_REPLAY_COMPLETE",
            "research_track": "portfolio_optimization",
            "migration_control_included": False,
            "target_portfolio_cash_usd": 25000.0,
            "planned_job_count": len(job_rows),
            "completed": len(job_rows),
            "failed": 0,
            "fresh_oos_consumed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "inputs": {
                "capital_manifest": {
                    "path": capital_path.as_posix(), "sha256": _sha(capital_path),
                },
                "shortlist": {
                    "path": shortlist.as_posix(), "sha256": _sha(shortlist),
                },
            },
            "artifacts": {
                "job_index": {
                    "path": index_path.as_posix(), "rows": len(job_rows),
                    "sha256": _sha(index_path),
                }
            },
        }
        _write_json(top_path, top)

    def build_summary(self) -> dict[str, object]:
        return build_capital_replay_summary(
            self.root / TOP_MANIFEST_RELATIVE, repository_root=self.root
        )


class NdxCardinalityCapitalReplaySummaryTests(unittest.TestCase):
    def test_rebuilds_separate_frontiers_and_preserves_paired_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplayFixture(Path(temporary))
            summary = fixture.build_summary()
            self.assertEqual(summary["verified_child_job_count"], 3)
            self.assertEqual(summary["evaluator_group_count"], 2)
            exact = next(
                group for group in summary["evaluator_groups"]
                if group["job_search_class"] == "EXACT_ENUMERATION"
            )
            self.assertEqual(exact["start_count"], 2)
            self.assertEqual(exact["latest_frontiers"][0]["holding_count"], 12)
            self.assertEqual(
                exact["user_preference_reference_by_start"][0]["status"],
                "PRESENT_SOURCE_REPORTED_REPLAY_ELIGIBLE",
            )
            rolling = exact["latest_frontiers"][0]["rolling_training_statistics"]
            self.assertEqual(rolling["paired_return_p50_vs_incumbent"], 0.007)
            self.assertEqual(exact["four_gate_incumbent_dominance_rows"], 2)
            self.assertTrue(
                summary["rolling_training_statistics_and_continuous_whole_lot_path_separated"]
            )
            self.assertFalse(summary["cross_universe_track_selection_allowed"])
            self.assertTrue(summary["strict_technology_is_not_current_gics_technology_admission"])

    def test_missing_risk_column_fails_closed_after_artifact_rebind(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplayFixture(Path(temporary))
            manifest_path = fixture.child_manifests[0]
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            candidate_path = Path(manifest["artifacts"]["candidates"]["path"])
            with candidate_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            fields = [key for key in rows[0] if key != "effective_n_p10"]
            for row in rows:
                row.pop("effective_n_p10", None)
            _write_csv(candidate_path, rows, fields)
            manifest["artifacts"]["candidates"]["sha256"] = _sha(candidate_path)
            manifest["artifacts"]["candidates"]["rows"] = len(rows)
            _write_json(manifest_path, manifest)
            with self.assertRaisesRegex(
                NdxCardinalityCapitalReplaySummaryError, "risk/source fields are missing"
            ):
                fixture.build_summary()

    def test_mixed_or_unknown_evaluator_lineage_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplayFixture(Path(temporary))
            capital_path = fixture.root / CAPITAL_MANIFEST_RELATIVE
            capital = json.loads(capital_path.read_text(encoding="utf-8"))
            capital["source_runs"][1]["evaluation_semantics_sha256"] = "0" * 64
            _write_json(capital_path, capital)
            top_path = fixture.root / TOP_MANIFEST_RELATIVE
            top = json.loads(top_path.read_text(encoding="utf-8"))
            top["inputs"]["capital_manifest"]["sha256"] = _sha(capital_path)
            _write_json(top_path, top)
            with self.assertRaisesRegex(
                NdxCardinalityCapitalReplaySummaryError, "evaluation semantics hash changed"
            ):
                fixture.build_summary()

    def test_unarchived_mutable_source_drift_is_reported_not_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplayFixture(Path(temporary))
            Path(fixture.shared_inputs["target_nav"]["path"]).write_text(
                "vendor revision\n", encoding="utf-8"
            )
            summary = fixture.build_summary()
            self.assertEqual(
                summary["status"],
                "HISTORICAL_SUMMARY_COMPLETE_WITH_UNRECOVERABLE_SOURCE_DRIFT",
            )
            self.assertFalse(summary["raw_historical_input_bytes_currently_recoverable"])
            self.assertEqual(summary["source_input_drift_count"], 1)

    def test_append_only_target_nav_recovers_exact_historical_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplayFixture(Path(temporary))
            target = Path(fixture.shared_inputs["target_nav"]["path"])
            with target.open("ab") as handle:
                handle.write(b"2024-01-02,2\n")
            summary = fixture.build_summary()
            self.assertEqual(
                summary["status"],
                "HISTORICAL_SUMMARY_COMPLETE_WITH_EXACT_PREFIX_RECOVERY",
            )
            self.assertTrue(summary["raw_historical_input_bytes_currently_recoverable"])
            self.assertEqual(summary["historical_input_unrecoverable_count"], 0)
            self.assertEqual(len(summary["historical_source_prefix_recoveries"]), 1)
            recovery = summary["historical_source_prefix_recoveries"][0]
            self.assertEqual(recovery["sha256"], fixture.shared_inputs["target_nav"]["sha256"])

    def test_bundle_is_immutable_and_tamper_evident(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplayFixture(Path(temporary) / "repo")
            summary = fixture.build_summary()
            output = Path(temporary) / "bundle"
            first = write_summary_bundle(summary, output_dir=output)
            second = write_summary_bundle(summary, output_dir=output)
            self.assertEqual(first, second)
            verify_summary_bundle(output / "manifest.json")
            (output / "summary.md").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(
                NdxCardinalityCapitalReplaySummaryError, "artifact hash changed"
            ):
                verify_summary_bundle(output / "manifest.json")


if __name__ == "__main__":
    unittest.main()
