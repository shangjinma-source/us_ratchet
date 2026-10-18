from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from backtest.ndx_dynamic_shadow_candidate_snapshot import (
    NdxDynamicShadowCandidateSnapshotError,
    READY_STATUS,
    build_fresh_candidate_input_snapshot,
    build_runtime_official_eligible_membership,
    load_generator_contract,
    verify_full_dynamic_k_plan,
    verify_snapshot_bundle,
    write_snapshot_bundle,
)
from data.versioning import file_sha256
from scripts.ndx_dynamic_shadow_candidate_generator import (
    CANONICAL_ARGUMENT_PATHS,
    DEFAULT_CALENDAR,
    DEFAULT_ROOT,
    _append_decision_seal,
    _load_and_validate_seal_ledger,
    _registration_clock,
    _require_canonical_seal_paths,
    _validate_decision_seal_timing,
)


ROOT = Path(__file__).resolve().parents[1]


def _eligible(issuer_count: int = 3) -> pd.DataFrame:
    rows = []
    for track in ("strict_technology", "technology_plus_adjacent"):
        for index in range(issuer_count):
            rows.append({
                "universe_track": track,
                "selection_date": "2026-10-01",
                "membership_snapshot_date": "2026-08-28",
                "ticker": f"T{index:02d}",
                "security_id": f"security:{index:02d}",
                "issuer_id": f"issuer:{index:02d}",
                "risk_chain": "semiconductor",
                "evidence_available_date": "2026-09-01",
            })
    return pd.DataFrame(rows)


def _prices(issuer_count: int = 3) -> dict[str, pd.DataFrame]:
    dates = pd.bdate_range(end="2026-10-01", periods=300)
    return {
        f"T{index:02d}": pd.DataFrame({"Date": dates, "Close": [100.0 + index + n / 100 for n in range(len(dates))]})
        for index in range(issuer_count)
    }


def _nominal_prices(issuer_count: int = 3, *, volume: float = 1_000_000.0) -> dict[str, pd.DataFrame]:
    dates = pd.bdate_range(end="2026-10-01", periods=300)
    return {
        f"T{index:02d}": pd.DataFrame({
            "Date": dates,
            "Close": [100.0 + index + n / 100 for n in range(len(dates))],
            "Volume": [volume] * len(dates),
        })
        for index in range(issuer_count)
    }


def _target() -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-09-30", periods=300)
    return pd.DataFrame({"Date": dates, "Close": [1.0 + n / 1000 for n in range(len(dates))]})


def _snapshot(issuer_count: int = 3):
    source_path = (ROOT / "config/ndx_dynamic_shadow_candidate_generator_v1.yaml").resolve()
    price_count = max(issuer_count, 8)
    return build_fresh_candidate_input_snapshot(
        _eligible(issuer_count),
        _prices(price_count),
        _nominal_prices(price_count),
        _target(),
        decision_date="2026-10-01",
        decision_close_timestamp_utc="2026-10-01T20:00:00+00:00",
        seal_timestamp_utc="2026-10-01T20:05:00+00:00",
        conservative_seal_deadline_utc="2026-10-02T13:30:00+00:00",
        source_versions={"membership": file_sha256(source_path)},
        source_paths={"membership": source_path.as_posix()},
        frozen_original8_tickers=[f"T{index:02d}" for index in range(8)],
    )


class DynamicShadowCandidateSnapshotTests(unittest.TestCase):
    def test_official_runtime_is_primary_and_identity_issue_is_explicitly_excluded(self) -> None:
        tickers = [f"X{index:03d}" for index in range(100)]
        official = pd.DataFrame({
            "ticker": tickers,
            "as_of_date": ["2026-10-01"] * 100,
            "source_id": ["nasdaq_100"] * 100,
            "source_type": ["index_constituent"] * 100,
            "source_locator": ["https://www.nasdaq.com/official"] * 100,
        })
        taxonomy = pd.DataFrame([{
            "ticker": ticker,
            "security_id": f"security:{ticker}",
            "issuer_id": f"issuer:{ticker}",
            "risk_chain": "semiconductor",
            "status": "accepted",
            "evidence_available_date": "2026-09-01",
            "selection_date_end": "2026-10-01",
        } for ticker in tickers[:3]])
        search_plan = {"universe_tracks": {
            "strict_technology": {"accepted_risk_chains": ["semiconductor"]},
            "technology_plus_adjacent": {
                "inherits": "strict_technology", "additional_risk_chains": ["software"]
            },
        }}
        eligible, audit = build_runtime_official_eligible_membership(
            official,
            pd.DataFrame({"ticker": tickers}),
            taxonomy,
            search_plan,
            decision_date="2026-10-01",
            observed_at_utc="2026-10-01T20:05:00+00:00",
            decision_close_timestamp_utc="2026-10-01T20:00:00+00:00",
            seal_timestamp_utc="2026-10-01T20:10:00+00:00",
            conservative_seal_deadline_utc="2026-10-02T13:30:00+00:00",
            allow_degraded_reviewed_taxonomy_subset=True,
            excluded_identity_security_ids={"security:X002"},
            excluded_identity_issuer_ids={"issuer:X002"},
            excluded_identity_tickers={"X002"},
        )
        self.assertEqual(set(eligible["ticker"]), {"X000", "X001"})
        self.assertEqual(audit["membership_source"], "NASDAQ_OFFICIAL_CURRENT_RUNTIME_SNAPSHOT")
        self.assertFalse(audit["membership_source_effective_date_known"])
        self.assertIn("X002", audit["excluded_identity_tickers"])
        self.assertTrue(audit["degraded"])

    def test_contract_preserves_dynamic_portfolio_optimization_boundary(self) -> None:
        contract = load_generator_contract(ROOT / "config/ndx_dynamic_shadow_candidate_generator_v1.yaml")
        self.assertEqual(contract["universe_contract"]["fixed_holding_count"], None)
        self.assertFalse(contract["input_contract"]["historical_runner_registry_read_allowed"])
        self.assertFalse(contract["search_contract"]["bounded_global_optimality_claimed"])

    def test_builds_every_k_for_both_tracks_with_decision_close_cutoff(self) -> None:
        snapshot = _snapshot(3)
        jobs = snapshot["job_plan"]
        self.assertEqual(len(jobs), 6)
        for track in ("strict_technology", "technology_plus_adjacent"):
            self.assertEqual(
                jobs.loc[jobs["universe_track"].eq(track), "holding_count"].tolist(),
                [1, 2, 3],
            )
        self.assertEqual(snapshot["training_adjusted_close"]["Date"].iloc[-1], "2026-10-01")
        self.assertEqual(snapshot["target_012922_asof_date"], "2026-09-30")
        self.assertIsNone(snapshot["execution_date"])
        self.assertEqual(
            snapshot["execution_coordinate_rule"],
            "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION",
        )
        self.assertTrue(jobs["historical_candidate_replay_allowed"].eq(False).all())
        self.assertTrue(jobs["global_optimality_claimed"].eq(False).all())

    def test_large_pool_marks_beam_shards_heuristic_without_optimality(self) -> None:
        snapshot = _snapshot(20)
        bounded = snapshot["job_plan"].loc[
            snapshot["job_plan"]["job_search_class"].eq("MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND")
        ]
        self.assertFalse(bounded.empty)
        self.assertTrue(bounded["global_optimality_claimed"].eq(False).all())
        self.assertTrue(bounded["bounded_search_disclosure"].eq("HEURISTIC_NO_GLOBAL_OPTIMALITY_CLAIM").all())

    def test_future_taxonomy_evidence_fails_closed(self) -> None:
        eligible = _eligible(3)
        eligible.loc[0, "evidence_available_date"] = "2026-10-02"
        with self.assertRaisesRegex(NdxDynamicShadowCandidateSnapshotError, "future membership or taxonomy"):
            build_fresh_candidate_input_snapshot(
                eligible, _prices(3), _nominal_prices(3), _target(), decision_date="2026-10-01",
                decision_close_timestamp_utc="2026-10-01T20:00:00+00:00",
                seal_timestamp_utc="2026-10-01T20:05:00+00:00",
                conservative_seal_deadline_utc="2026-10-02T13:30:00+00:00",
                source_versions={"x": "a" * 64},
                source_paths={"x": (ROOT / "README.md").resolve().as_posix()},
                frozen_original8_tickers=[f"T{index:02d}" for index in range(8)],
            )

    def test_price_missing_decision_close_fails_closed(self) -> None:
        prices = _prices(8)
        prices["T01"] = prices["T01"].iloc[:-1]
        with self.assertRaisesRegex(NdxDynamicShadowCandidateSnapshotError, "do not end at decision close"):
            build_fresh_candidate_input_snapshot(
                _eligible(3), prices, _nominal_prices(8), _target(), decision_date="2026-10-01",
                decision_close_timestamp_utc="2026-10-01T20:00:00+00:00",
                seal_timestamp_utc="2026-10-01T20:05:00+00:00",
                conservative_seal_deadline_utc="2026-10-02T13:30:00+00:00",
                source_versions={"x": "a" * 64},
                source_paths={"x": (ROOT / "README.md").resolve().as_posix()},
                frozen_original8_tickers=[f"T{index:02d}" for index in range(8)],
            )

    def test_incomplete_k_plan_is_rejected(self) -> None:
        snapshot = _snapshot(3)
        jobs = snapshot["job_plan"].loc[~snapshot["job_plan"]["holding_count"].eq(2)]
        with self.assertRaisesRegex(NdxDynamicShadowCandidateSnapshotError, "coordinate set is incomplete"):
            verify_full_dynamic_k_plan(jobs, snapshot["eligible_securities"])

    def test_immutable_bundle_verifier_detects_artifact_tampering(self) -> None:
        with TemporaryDirectory() as directory:
            manifest = write_snapshot_bundle(directory, _snapshot(3))
            self.assertEqual(manifest["status"], READY_STATUS)
            manifest_path = Path(directory) / "manifest.json"
            verify_snapshot_bundle(manifest_path)
            write_snapshot_bundle(directory, _snapshot(3))
            job_path = Path(directory) / "job_plan.csv"
            job_path.write_text(job_path.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")
            with self.assertRaisesRegex(NdxDynamicShadowCandidateSnapshotError, "artifact hash mismatch"):
                verify_snapshot_bundle(manifest_path)

    def test_bundle_manifest_never_claims_final_candidates_or_promotion(self) -> None:
        with TemporaryDirectory() as directory:
            write_snapshot_bundle(directory, _snapshot(3))
            manifest = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifest_type"], "ndx_dynamic_shadow_candidate_input_snapshot")
            self.assertFalse(manifest["historical_runner_registry_read"])
            self.assertFalse(manifest["frozen_forward_candidate_source_used"])
            self.assertFalse(manifest["promotion_allowed"])
            self.assertFalse(manifest["candidate_results_complete"])
            self.assertEqual(manifest["completed_policy_lane_count"], 0)

    def test_manifest_fields_cannot_be_changed_without_reproducible_fingerprint(self) -> None:
        with TemporaryDirectory() as directory:
            write_snapshot_bundle(directory, _snapshot(3))
            manifest_path = Path(directory) / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_versions"]["membership"] = "f" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(NdxDynamicShadowCandidateSnapshotError, "cannot be reproduced"):
                verify_snapshot_bundle(manifest_path)

    def test_unknown_search_class_and_planned_optimality_claim_fail_closed(self) -> None:
        snapshot = _snapshot(3)
        jobs = snapshot["job_plan"].copy()
        jobs.loc[0, "job_search_class"] = "FAKE_EXACT"
        with self.assertRaisesRegex(NdxDynamicShadowCandidateSnapshotError, "unknown search class"):
            verify_full_dynamic_k_plan(jobs, snapshot["eligible_securities"])
        jobs = snapshot["job_plan"].copy()
        jobs.loc[0, "global_optimality_claimed"] = True
        with self.assertRaisesRegex(NdxDynamicShadowCandidateSnapshotError, "cannot claim global optimality"):
            verify_full_dynamic_k_plan(jobs, snapshot["eligible_securities"])

    def test_target_forward_fill_retains_nonfuture_source_date(self) -> None:
        snapshot = _snapshot(3)
        target = snapshot["target_012922_aligned"]
        self.assertIn("source_date", target.columns)
        self.assertTrue(
            (pd.to_datetime(target["source_date"]) <= pd.to_datetime(target["Date"])).all()
        )
        self.assertEqual(target["source_date"].iloc[-1], "2026-09-30")

    def test_liquidity_gate_shrinks_pool_before_dynamic_k_planning(self) -> None:
        nominal = _nominal_prices(8)
        nominal["T02"]["Volume"] = 1.0
        source_path = (ROOT / "config/ndx_dynamic_shadow_candidate_generator_v1.yaml").resolve()
        snapshot = build_fresh_candidate_input_snapshot(
            _eligible(3), _prices(8), nominal, _target(),
            decision_date="2026-10-01",
            decision_close_timestamp_utc="2026-10-01T20:00:00+00:00",
            seal_timestamp_utc="2026-10-01T20:05:00+00:00",
            conservative_seal_deadline_utc="2026-10-02T13:30:00+00:00",
            source_versions={"membership": file_sha256(source_path)},
            source_paths={"membership": source_path.as_posix()},
            frozen_original8_tickers=[f"T{index:02d}" for index in range(8)],
        )
        self.assertEqual(set(snapshot["eligible_securities"]["ticker"]), {"T00", "T01"})
        self.assertEqual(set(snapshot["job_plan"]["holding_count"]), {1, 2})
        self.assertEqual(snapshot["liquidity_exclusions"]["ticker"].tolist(), ["T02"])
        self.assertIn("training_nominal_close", snapshot)

    def test_system_clock_rejects_caller_backfill_timestamp(self) -> None:
        with self.assertRaisesRegex(NdxDynamicShadowCandidateSnapshotError, "system clock"):
            _registration_clock(
                "2026-10-01T20:05:00+00:00",
                observed_now_utc=pd.Timestamp("2026-10-03T20:05:00+00:00"),
            )

    def test_decision_seal_rejects_bootstrap_and_late_completed_session(self) -> None:
        rows = pd.DataFrame([{
            "session_date": "2026-10-01",
            "close_timestamp_utc": "2026-10-01T20:00:00+00:00",
            "completed": True,
            "is_first_observed_session_of_month": True,
            "origin": "HISTORICAL_BOOTSTRAP_NOT_FRESH_EVIDENCE",
            "decision_eligible": False,
        }])
        with self.assertRaisesRegex(NdxDynamicShadowCandidateSnapshotError, "prospectively observed"):
            _validate_decision_seal_timing(
                rows,
                decision_date="2026-10-01",
                observed_system_utc=pd.Timestamp("2026-10-01T20:05:00+00:00"),
            )
        rows.loc[0, ["origin", "decision_eligible"]] = ["PROSPECTIVE_OBSERVED_APPEND", True]
        with self.assertRaisesRegex(NdxDynamicShadowCandidateSnapshotError, "next-weekday open"):
            _validate_decision_seal_timing(
                rows,
                decision_date="2026-10-01",
                observed_system_utc=pd.Timestamp("2026-10-02T14:00:00+00:00"),
            )
        rows = pd.concat([rows, pd.DataFrame([{
            "session_date": "2026-10-02",
            "close_timestamp_utc": "2026-10-02T20:00:00+00:00",
            "completed": True,
            "is_first_observed_session_of_month": False,
            "origin": "PROSPECTIVE_OBSERVED_APPEND",
            "decision_eligible": True,
        }])], ignore_index=True)
        with self.assertRaisesRegex(NdxDynamicShadowCandidateSnapshotError, "late decision sealing"):
            _validate_decision_seal_timing(
                rows,
                decision_date="2026-10-01",
                observed_system_utc=pd.Timestamp("2026-10-03T00:00:00+00:00"),
            )

    def test_noncanonical_source_path_masquerade_is_rejected(self) -> None:
        values = {field: str(path) for field, path in CANONICAL_ARGUMENT_PATHS.items()}
        values.update({
            "output_root": str(DEFAULT_ROOT),
            "session_calendar_manifest": str(DEFAULT_CALENDAR),
        })
        args = SimpleNamespace(**values)
        _require_canonical_seal_paths(args)
        args.contract = str(ROOT / "README.md")
        with self.assertRaisesRegex(NdxDynamicShadowCandidateSnapshotError, "non-canonical"):
            _require_canonical_seal_paths(args)

    def test_decision_seal_ledger_is_idempotent_and_hash_chained(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest_path = root / "2026-10-01" / "manifest.json"
            manifest_path.parent.mkdir(parents=True)
            manifest = {
                "decision_date": "2026-10-01",
                "decision_close_timestamp_utc": "2026-10-01T20:00:00+00:00",
                "seal_timestamp_utc": "2026-10-01T20:05:00+00:00",
                "conservative_seal_deadline_utc": "2026-10-02T13:30:00+00:00",
                "execution_coordinate_rule": (
                    "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION"
                ),
                "snapshot_fingerprint": "a" * 64,
                "source_versions": {
                    "session_calendar_manifest_sha256": "b" * 64,
                    "official_snapshot_sha256": "c" * 64,
                },
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            ledger_path = root / "decision_seals.jsonl"

            first = _append_decision_seal(
                ledger_path, manifest_path, manifest, expected_root=root
            )
            second = _append_decision_seal(
                ledger_path, manifest_path, manifest, expected_root=root
            )
            self.assertEqual(first, second)
            self.assertEqual(
                len(_load_and_validate_seal_ledger(ledger_path, expected_root=root)), 1
            )

            record = json.loads(ledger_path.read_text(encoding="utf-8"))
            record["seal_timestamp_utc"] = "2026-10-01T20:06:00+00:00"
            ledger_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateSnapshotError, "hash chain changed"
            ):
                _load_and_validate_seal_ledger(ledger_path, expected_root=root)


if __name__ == "__main__":
    unittest.main()
