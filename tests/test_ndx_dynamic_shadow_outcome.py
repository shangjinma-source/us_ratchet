from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from backtest.ndx_dynamic_shadow_daily import (
    append_lane_path,
    append_target_012922_trace,
    canonical_sha256,
)
from backtest.ndx_dynamic_shadow_outcome import (
    NdxDynamicShadowOutcomeError,
    append_resolution_events,
    evaluate_dynamic_shadow_outcomes,
    load_outcome_contract,
    load_resolution_ledger,
)
from data.versioning import file_sha256


ROOT = Path(__file__).resolve().parents[1]
TRACKS = ("strict_technology", "technology_plus_adjacent")
ROLES = ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")


def _source(directory: Path, dates: list[str], values: list[float], fetched_at: str) -> tuple[pd.DataFrame, Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"Date": dates, "Close": values})
    csv_path = directory / "source.csv"
    frame.to_csv(csv_path, index=False, lineterminator="\n")
    manifest_path = directory / "source.manifest.json"
    manifest_path.write_text(json.dumps({
        "dataset_key": "012922", "content_sha256": file_sha256(csv_path),
        "row_count": len(frame), "fetched_at": fetched_at,
        "publication_time_known": False,
    }), encoding="utf-8")
    return frame, csv_path, manifest_path


def _lane(directory: Path, selector_id: str, dates: list[str], values: list[float]) -> Path:
    path = pd.DataFrame({
        "date": dates, "cash_usd": [100.0] * len(dates),
        "holdings_value_usd": [value - 100.0 for value in values],
        "total_value_usd": values, "holding_count": [1] * len(dates),
        "active_security_ids": ["security:test"] * len(dates),
        "active_tickers": ["TEST"] * len(dates),
        "holdings": ["security:test:1"] * len(dates),
    })
    destination = directory / f"{selector_id}.jsonl"
    append_lane_path(
        destination, selector_id=selector_id, path=path,
        rebalances=pd.DataFrame(), trades=pd.DataFrame(),
        price_evidence_sha256_by_date={date: "a" * 64 for date in dates},
    )
    return destination


class DynamicShadowOutcomeTests(unittest.TestCase):
    def test_contract_keeps_early_results_out_of_admission_and_v5(self) -> None:
        contract = load_outcome_contract(ROOT / "config/ndx_dynamic_shadow_outcome_v1.yaml")
        self.assertFalse(contract["evaluation_contract"]["early_performance_veto_allowed"])
        self.assertFalse(
            contract["formal_forward_v5_boundary"]["dynamic_shadow_substitutes_formal_v5_gate"]
        )

    def test_resolution_is_linked_to_first_observed_and_recomputed_from_source(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            daily_control = root / "daily/benchmark_controls"
            dates = ["2026-01-02", "2026-01-05"]
            first_frame, first_csv, first_manifest = _source(
                daily_control / "target_012922_sources", dates, [2.0, 2.1],
                "2026-01-06T00:00:00+00:00",
            )
            first_trace = daily_control / "target_012922_asof.jsonl"
            append_target_012922_trace(
                first_trace, path_dates=dates, target_nav=first_frame,
                observed_at_utc="2026-01-06T01:00:00+00:00",
                source_csv_snapshot_path=first_csv,
                source_manifest_snapshot_path=first_manifest,
                source_csv_sha256=file_sha256(first_csv),
                source_manifest_sha256=file_sha256(first_manifest),
                source_fetched_at_utc="2026-01-06T00:00:00+00:00",
            )
            ledger = root / "outcome/target_012922_resolved_outcomes.jsonl"
            outcome_frame, outcome_csv, outcome_manifest = _source(
                ledger.parent / "source_snapshots", dates, [2.0, 2.2],
                "2026-01-07T00:00:00+00:00",
            )
            records = append_resolution_events(
                ledger, first_observed_trace_path=first_trace, target_nav=outcome_frame,
                source_csv_snapshot_path=outcome_csv,
                source_manifest_snapshot_path=outcome_manifest,
            )
            self.assertEqual(len(records), 2)
            self.assertAlmostEqual(records[-1]["normalized_value_usd"], 27500.0)
            payloads = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
            payloads[-1]["source_close"] = 9.9
            unsigned = dict(payloads[-1])
            unsigned.pop("record_sha256")
            payloads[-1]["record_sha256"] = canonical_sha256(unsigned)
            ledger.write_text("\n".join(json.dumps(value) for value in payloads) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(NdxDynamicShadowOutcomeError, "source boundary"):
                load_resolution_ledger(ledger, first_observed_trace_path=first_trace)

    def test_early_paired_metrics_are_diagnostic_only(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dates = ["2026-01-02", "2026-01-05"]
            daily_control = root / "daily/benchmark_controls"
            source_frame, source_csv, source_manifest = _source(
                daily_control / "target_012922_sources", dates, [2.0, 2.1],
                "2026-01-06T00:00:00+00:00",
            )
            first_trace = daily_control / "target_012922_asof.jsonl"
            append_target_012922_trace(
                first_trace, path_dates=dates, target_nav=source_frame,
                observed_at_utc="2026-01-06T01:00:00+00:00",
                source_csv_snapshot_path=source_csv,
                source_manifest_snapshot_path=source_manifest,
                source_csv_sha256=file_sha256(source_csv),
                source_manifest_sha256=file_sha256(source_manifest),
                source_fetched_at_utc="2026-01-06T00:00:00+00:00",
            )
            resolution = root / "outcome/target_012922_resolved_outcomes.jsonl"
            resolved_frame, resolved_csv, resolved_manifest = _source(
                resolution.parent / "source_snapshots", dates, [2.0, 2.1],
                "2026-01-07T00:00:00+00:00",
            )
            append_resolution_events(
                resolution, first_observed_trace_path=first_trace,
                target_nav=resolved_frame, source_csv_snapshot_path=resolved_csv,
                source_manifest_snapshot_path=resolved_manifest,
            )
            lane_root = root / "daily/lane_paths"
            lane_paths = {
                f"{track}__{role.lower()}__v1": _lane(
                    lane_root, f"{track}__{role.lower()}__v1", dates, [25000.0, 26000.0],
                )
                for track in TRACKS for role in ROLES
            }
            original = _lane(
                daily_control, "ndx_original_8_incumbent_v0", dates, [25000.0, 25500.0],
            )
            result = evaluate_dynamic_shadow_outcomes(
                selector_lane_ledgers=lane_paths, original_8_ledger=original,
                resolution_ledger=resolution, first_observed_trace_path=first_trace,
                realized_decision_root=root / "daily/realized_decisions",
            )
            self.assertEqual(result["status"], "EARLY_PROGRESS_FALSIFICATION_DIAGNOSTIC_ONLY")
            self.assertEqual(result["resolved_trading_session_count"], 2)
            self.assertFalse(result["performance_admission_allowed"])
            self.assertFalse(result["performance_veto_allowed"])
            self.assertFalse(result["formal_v5_gate_substitution_allowed"])
            self.assertEqual(len(result["metrics"]), 10)

    def test_resolution_carries_latest_no_future_nav_across_calendar_mismatch(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / "daily/benchmark_controls"
            us_dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
            first_frame, first_csv, first_manifest = _source(
                control / "target_012922_sources", ["2026-01-02", "2026-01-06"],
                [2.0, 2.2], "2026-01-07T00:00:00+00:00",
            )
            first_trace = control / "target_012922_asof.jsonl"
            append_target_012922_trace(
                first_trace, path_dates=us_dates, target_nav=first_frame,
                observed_at_utc="2026-01-07T01:00:00+00:00",
                source_csv_snapshot_path=first_csv,
                source_manifest_snapshot_path=first_manifest,
                source_csv_sha256=file_sha256(first_csv),
                source_manifest_sha256=file_sha256(first_manifest),
                source_fetched_at_utc="2026-01-07T00:00:00+00:00",
            )
            ledger = root / "outcome/target_012922_resolved_outcomes.jsonl"
            outcome_frame, outcome_csv, outcome_manifest = _source(
                ledger.parent / "source_snapshots", ["2026-01-02", "2026-01-06"],
                [2.0, 2.2], "2026-01-08T00:00:00+00:00",
            )
            records = append_resolution_events(
                ledger, first_observed_trace_path=first_trace, target_nav=outcome_frame,
                source_csv_snapshot_path=outcome_csv,
                source_manifest_snapshot_path=outcome_manifest,
            )
            self.assertEqual(len(records), 3)
            self.assertEqual(records[1]["source_date"], "2026-01-02")
            self.assertEqual(records[1]["lag_calendar_days"], 3)
            self.assertTrue(records[1]["carry_forward_used"])
            self.assertLessEqual(records[1]["source_date"], records[1]["session_date"])

    def test_one_year_threshold_is_review_only_and_does_not_replace_v5(self) -> None:
        dates = pd.bdate_range("2026-01-02", periods=252).date.astype(str).tolist()
        lane_records = [
            {"date": date, "path_state": {"total_value_usd": 25000.0 + index}}
            for index, date in enumerate(dates)
        ]
        target_records = [
            {"session_date": date, "normalized_value_usd": 25000.0 + index / 2.0}
            for index, date in enumerate(dates)
        ]
        decisions = [
            {"decision_date": f"2026-{month:02d}-01"} for month in range(1, 13)
        ]
        selector_paths = {
            f"{track}__{role.lower()}__v1": Path(f"{track}-{role}.jsonl")
            for track in TRACKS for role in ROLES
        }
        with patch(
            "backtest.ndx_dynamic_shadow_outcome.load_lane_path_ledger",
            return_value=lane_records,
        ), patch(
            "backtest.ndx_dynamic_shadow_outcome.load_resolution_ledger",
            return_value=target_records,
        ), patch(
            "backtest.ndx_dynamic_shadow_outcome.verify_realized_decision_chain",
            return_value=decisions,
        ):
            result = evaluate_dynamic_shadow_outcomes(
                selector_lane_ledgers=selector_paths, original_8_ledger="original.jsonl",
                resolution_ledger="target.jsonl", first_observed_trace_path="trace.jsonl",
                realized_decision_root="realized",
            )
        self.assertEqual(result["status"], "ONE_YEAR_SHADOW_RESEARCH_REVIEW_READY_NON_ADMISSION")
        self.assertFalse(result["performance_admission_allowed"])
        self.assertFalse(result["performance_veto_allowed"])
        self.assertFalse(result["formal_v5_gate_substitution_allowed"])


if __name__ == "__main__":
    unittest.main()
