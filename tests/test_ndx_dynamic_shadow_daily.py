from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from backtest.ndx_dynamic_shadow_daily import (
    NdxDynamicShadowDailyError,
    append_lane_path,
    append_target_012922_trace,
    build_daily_readiness,
    build_realized_lane_decisions,
    canonical_sha256,
    classify_daily_phase,
    load_daily_contract,
    load_target_012922_trace_ledger,
    replay_lane_path,
    validate_nominal_price_evidence,
    verify_realized_decision_chain,
    write_immutable_realized_decisions,
)
from backtest.ndx_dynamic_shadow_fresh_search import (
    EXECUTION_COORDINATE_RULE,
    coordinate_hash,
    write_final_candidate_snapshot,
)
from data.versioning import file_sha256
import scripts.ndx_dynamic_shadow_daily as daily_script


ROOT = Path(__file__).resolve().parents[1]


def _sessions(include_execution: bool = True, include_valuation: bool = True) -> pd.DataFrame:
    rows = [{
        "session_date": "2026-10-01",
        "open_timestamp_utc": "2026-10-01T13:30:00+00:00",
        "close_timestamp_utc": "2026-10-01T20:00:00+00:00",
        "completed": True,
        "is_first_observed_session_of_month": True,
        "origin": "PROSPECTIVE_OBSERVED_APPEND",
        "decision_eligible": True,
    }]
    if include_execution:
        rows.append({
            "session_date": "2026-10-02",
            "open_timestamp_utc": "2026-10-02T13:30:00+00:00",
            "close_timestamp_utc": "2026-10-02T20:00:00+00:00",
            "completed": True,
            "is_first_observed_session_of_month": False,
            "origin": "PROSPECTIVE_OBSERVED_APPEND",
            "decision_eligible": False,
        })
    if include_execution and include_valuation:
        rows.append({
            "session_date": "2026-10-05",
            "open_timestamp_utc": "2026-10-05T13:30:00+00:00",
            "close_timestamp_utc": "2026-10-05T20:00:00+00:00",
            "completed": True,
            "is_first_observed_session_of_month": False,
            "origin": "PROSPECTIVE_OBSERVED_APPEND",
            "decision_eligible": False,
        })
    return pd.DataFrame(rows)


def _final_candidate(directory: Path) -> Path:
    jobs = []
    candidates = []
    roles = []
    snapshot_hash = "d" * 64
    executor_hash = "e" * 64
    original_hash = "f" * 64
    for track, ticker in (
        ("strict_technology", "AAA"),
        ("technology_plus_adjacent", "BBB"),
    ):
        job = {
            "snapshot_fingerprint": "a" * 64,
            "universe_track": track,
            "decision_date": "2026-10-01",
            "execution_coordinate_rule": EXECUTION_COORDINATE_RULE,
            "decision_data_end": "2026-10-01",
            "holding_count": 1,
            "eligible_security_count": 1,
            "eligible_issuer_count": 1,
            "one_security_per_issuer_required": True,
            "theoretical_issuer_combinations": 1,
            "job_search_class": "EXACT_ENUMERATION",
            "search_completion_status": "PLANNED_NOT_EXECUTED",
            "global_optimality_claimed": False,
            "bounded_search_disclosure": "EXHAUSTIVE_ENUMERATION_REQUIRED_NOT_YET_EXECUTED",
            "checkpoint_key": f"{'a' * 64}/{track}/2026-10-01/holding_count_0001",
            "historical_candidate_replay_allowed": False,
            "promotion_allowed": False,
        }
        jobs.append(job)
        identity = coordinate_hash(
            job, snapshot_manifest_sha256=snapshot_hash,
            executor_sha256=executor_hash, original_8_sha256=original_hash,
        )
        portfolio_id = f"portfolio-{ticker.lower()}"
        candidates.append({
            "universe_track": track,
            "execution_coordinate_rule": EXECUTION_COORDINATE_RULE,
            "decision_data_end": "2026-10-01",
            "holding_count": 1,
            "portfolio_id": portfolio_id,
            "weight_spec": "equal_weight",
            "tickers": ticker,
            "weights": f"{ticker}:1.0000000000",
            "security_ids": f"security:{ticker.lower()}",
            "issuer_ids": f"issuer:{ticker.lower()}",
            "declared_constraints_passed": True,
            "return_p50": 0.1,
            "return_p10": -0.1,
            "max_drawdown_p50": 0.1,
            "max_drawdown_p90": 0.2,
            "target_012922_distance": 0.1,
            "turnover": 1.0,
            "coordinate_hash": identity,
        })
        for role in ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE"):
            roles.append({
                "selector_id": f"{track}__{role.lower()}__v1",
                "universe_track": track,
                "policy_role": role,
                "status": "SELECTED_FRESH_SHADOW_CANDIDATE",
                "portfolio_id": portfolio_id,
                "holding_count": 1,
                "reason": "",
                "replacement_allowed": False,
                "promotion_allowed": False,
            })
        roles.append({
            "selector_id": f"{track}__user_preference__v1",
            "universe_track": track,
            "policy_role": "USER_PREFERENCE",
            "status": "REFERENCE_UNAVAILABLE_NOT_REPLACED",
            "portfolio_id": "",
            "holding_count": None,
            "reason": "fixture has no preference quartet",
            "replacement_allowed": False,
            "promotion_allowed": False,
        })
    write_final_candidate_snapshot(
        directory, pd.DataFrame(candidates), pd.DataFrame(roles), pd.DataFrame(jobs),
        snapshot_manifest_sha256=snapshot_hash,
        snapshot_fingerprint="a" * 64,
        executor_sha256=executor_hash,
        original_8_sha256=original_hash,
    )
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["candidate_sealed_at_utc"] = "2026-10-02T02:00:00+00:00"
    manifest["roles_sealed_at_utc"] = "2026-10-02T02:00:00+00:00"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


class DynamicShadowDailyTests(unittest.TestCase):
    def test_execute_reverifies_activation_before_any_daily_side_effect(self) -> None:
        with patch.object(
            daily_script, "_verify_activation_before_execute",
            side_effect=NdxDynamicShadowDailyError("activation drift"),
        ) as gate, patch.object(daily_script, "_protected_hashes") as protected:
            with self.assertRaisesRegex(NdxDynamicShadowDailyError, "activation drift"):
                daily_script.execute()
        gate.assert_called_once_with()
        protected.assert_not_called()

    def test_contract_and_readiness_are_research_only(self) -> None:
        contract_path = ROOT / "config/ndx_dynamic_shadow_daily_v1.yaml"
        contract = load_daily_contract(contract_path)
        self.assertFalse(contract["mutation_boundary"]["task_registration_allowed"])
        readiness = build_daily_readiness(
            contract_path,
            calendar_manifest_path=(
                ROOT / "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json"
            ),
            repository_root=ROOT,
            as_of_utc="2026-09-05T00:00:00+00:00",
        )
        self.assertEqual(readiness["status"], "BLOCKED")
        self.assertIn("FIRST_PROSPECTIVE_DECISION_NOT_REACHED", readiness["blockers"])
        self.assertFalse(readiness["automation_registered"])

    def test_three_phase_clock_and_missed_window_fail_closed(self) -> None:
        decision_only = _sessions(include_execution=False)
        common = dict(
            sessions=decision_only, decision_date="2026-10-01",
            now_utc="2026-10-02T02:00:00+00:00",
            no_decision_disposition_exists=False, decisions_realized=False,
        )
        self.assertEqual(classify_daily_phase(
            **common, input_snapshot_exists=False, final_candidate_exists=False
        ), "SEAL_FRESH_PIT_INPUT")
        self.assertEqual(classify_daily_phase(
            **common, input_snapshot_exists=True, final_candidate_exists=False
        ), "RESUME_ALL_K_FRESH_SEARCH")
        self.assertEqual(classify_daily_phase(
            **common, input_snapshot_exists=True, final_candidate_exists=True,
            final_roles_sealed_at_utc="2026-10-02T02:00:00+00:00",
        ), "WAIT_FOR_NEXT_OBSERVED_SESSION")
        late = dict(common)
        late["now_utc"] = "2026-10-02T14:00:00+00:00"
        self.assertEqual(classify_daily_phase(
            **late, input_snapshot_exists=True, final_candidate_exists=False
        ), "NO_DECISION_NO_BACKFILL")
        self.assertEqual(classify_daily_phase(
            sessions=_sessions(include_valuation=False), decision_date="2026-10-01",
            now_utc="2026-10-03T00:00:00+00:00", input_snapshot_exists=True,
            final_candidate_exists=True, no_decision_disposition_exists=False,
            decisions_realized=False,
            final_roles_sealed_at_utc="2026-10-02T14:00:00+00:00",
        ), "NO_DECISION_NO_BACKFILL")

    def test_realize_ten_lanes_and_append_whole_lot_paths_idempotently(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = _final_candidate(root / "candidate")
            with patch(
                "backtest.ndx_dynamic_shadow_daily._system_utc_now",
                return_value=datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc),
            ):
                decisions = build_realized_lane_decisions(manifest_path, _sessions())
            self.assertEqual(len(decisions), 10)
            decision_paths = write_immutable_realized_decisions(root / "decisions", decisions)
            self.assertEqual(len(decision_paths), 10)
            write_immutable_realized_decisions(root / "decisions", decisions)
            verified = verify_realized_decision_chain(root / "decisions")
            self.assertEqual(len(verified), 1)
            self.assertEqual(verified[0]["lane_count"], 10)

            selected = next(item for item in decisions if item["selected_candidate"] is not None)
            selector_id = selected["selector_id"]
            lane = [item for item in decisions if item["selector_id"] == selector_id]
            index = pd.to_datetime(["2026-10-02", "2026-10-05"])
            closes = pd.DataFrame({"AAA": [101.0, 103.0], "BBB": [51.0, 52.0]}, index=index)
            opens = pd.DataFrame({"AAA": [100.0, 102.0], "BBB": [50.0, 51.0]}, index=index)
            summary, rebalances, trades, path = replay_lane_path(
                lane, sessions=_sessions(), valuation_closes=closes,
                execution_opens=opens, valuation_end_date="2026-10-05",
            )
            self.assertEqual(summary["rebalance_count"], 1)
            self.assertTrue(summary["cash_buffer_preserved"])
            self.assertTrue((trades["share_delta"].abs() % 1).eq(0).all())
            hashes = {"2026-10-02": "1" * 64, "2026-10-05": "2" * 64}
            ledger = root / "paths" / f"{selector_id}.jsonl"
            first = append_lane_path(
                ledger, selector_id=selector_id, path=path,
                rebalances=rebalances, trades=trades,
                price_evidence_sha256_by_date=hashes,
            )
            second = append_lane_path(
                ledger, selector_id=selector_id, path=path,
                rebalances=rebalances, trades=trades,
                price_evidence_sha256_by_date=hashes,
            )
            self.assertEqual(first, second)
            self.assertEqual(len(second), 2)

            unavailable = next(item for item in decisions if item["selected_candidate"] is None)
            cash_summary, _, _, cash_path = replay_lane_path(
                [unavailable], sessions=_sessions(), valuation_closes=closes,
                execution_opens=opens, valuation_end_date="2026-10-05",
            )
            self.assertEqual(cash_summary["terminal_value_usd"], 25000.0)
            self.assertTrue(cash_path["holding_count"].eq(0).all())

    def test_late_role_seal_cannot_be_realized(self) -> None:
        with TemporaryDirectory() as directory:
            manifest_path = _final_candidate(Path(directory) / "candidate")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["candidate_sealed_at_utc"] = "2026-10-02T14:00:00+00:00"
            manifest["roles_sealed_at_utc"] = "2026-10-02T14:00:00+00:00"
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(NdxDynamicShadowDailyError, "not frozen before"):
                with patch(
                    "backtest.ndx_dynamic_shadow_daily._system_utc_now",
                    return_value=datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc),
                ):
                    build_realized_lane_decisions(manifest_path, _sessions())

    def test_nominal_price_evidence_requires_exact_ticker_session_cartesian(self) -> None:
        sessions = _sessions()
        rows = [
            {"Date": date, "ticker": ticker, "Open": 100.0, "Close": 101.0}
            for date in ("2026-10-01", "2026-10-02", "2026-10-05")
            for ticker in ("AAA", "BBB")
        ]
        frame = pd.DataFrame(rows)
        result = validate_nominal_price_evidence(
            frame, sessions, tickers=["AAA", "BBB"], valuation_end_date="2026-10-05"
        )
        self.assertEqual(len(result), 6)
        with self.assertRaisesRegex(NdxDynamicShadowDailyError, "Cartesian"):
            validate_nominal_price_evidence(
                frame.iloc[:-1], sessions, tickers=["AAA", "BBB"],
                valuation_end_date="2026-10-05",
            )

    def test_target_trace_recomputes_value_from_immutable_source(self) -> None:
        with TemporaryDirectory() as directory:
            control = Path(directory) / "benchmark_controls"
            source_root = control / "target_012922_sources"
            source_root.mkdir(parents=True)
            csv_path = source_root / "source.csv"
            csv_path.write_text(
                "Date,Close\n2026-10-01,2.0\n2026-10-02,2.2\n",
                encoding="utf-8", newline="\n",
            )
            manifest_path = source_root / "source.manifest.json"
            manifest_path.write_text(json.dumps({
                "dataset_key": "012922", "content_sha256": file_sha256(csv_path),
                "row_count": 2, "fetched_at": "2026-10-05T20:30:00+00:00",
            }), encoding="utf-8")
            ledger = control / "target_012922_asof.jsonl"
            append_target_012922_trace(
                ledger, path_dates=["2026-10-02"], target_nav=pd.read_csv(csv_path),
                observed_at_utc="2026-10-05T21:00:00+00:00",
                source_csv_snapshot_path=csv_path,
                source_manifest_snapshot_path=manifest_path,
                source_csv_sha256=file_sha256(csv_path),
                source_manifest_sha256=file_sha256(manifest_path),
                source_fetched_at_utc="2026-10-05T20:30:00+00:00",
            )
            record = json.loads(ledger.read_text(encoding="utf-8"))
            record["source_close"] = 9.9
            record["normalized_value_usd"] = 25000.0
            unsigned = dict(record)
            unsigned.pop("record_sha256")
            record["record_sha256"] = canonical_sha256(unsigned)
            ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(NdxDynamicShadowDailyError, "available trace value"):
                load_target_012922_trace_ledger(ledger)


if __name__ == "__main__":
    unittest.main()
