from __future__ import annotations
import csv
from datetime import datetime
import json

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

from backtest.ndx_dynamic_shadow_activation_readiness import (
    BLOCKED_STATUS,
    estimate_monthly_search_cost,
    evaluate_activation_readiness,
    sha256_file,
    validate_bound_source_hashes,
    validate_selector_matrix,
    verify_observed_session_calendar_manifest,
    verify_original8_control_manifest,
)
from scripts.ndx_dynamic_shadow_activation_readiness import _validated_output
from backtest.ndx_observed_session_calendar import (
    append_records_durable,
    load_ohlc_rows,
    prepare_update,
    projection_rows,
)


ROOT = Path(__file__).resolve().parents[1]


def _healthy_observed_calendar_fixture(directory: str) -> tuple[Path, Path]:
    root = Path(directory).resolve()
    cache = root / "data/cache"
    cache.mkdir(parents=True)
    source_paths: dict[str, Path] = {}
    for offset, ticker in enumerate(("QQQ", "SPY")):
        path = cache / f"{ticker}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["Date", "Open", "High", "Low", "Close", "Volume"],
            )
            writer.writeheader()
            writer.writerow({
                "Date": "2026-09-30", "Open": 100 + offset,
                "High": 102 + offset, "Low": 99 + offset,
                "Close": 101 + offset, "Volume": 1_000_000 + offset,
            })
        source_paths[ticker] = path
    engine = root / "backtest/ndx_observed_session_calendar.py"
    runner = root / "scripts/ndx_observed_session_calendar.py"
    engine.parent.mkdir(parents=True)
    runner.parent.mkdir(parents=True)
    engine.write_text("# healthy fixture engine\n", encoding="utf-8")
    runner.write_text("# healthy fixture runner\n", encoding="utf-8")

    source_rows = {
        ticker: load_ohlc_rows(path, ticker=ticker)
        for ticker, path in source_paths.items()
    }
    source_hashes = {
        ticker: sha256_file(path) for ticker, path in source_paths.items()
    }
    records = prepare_update(
        [], completed_dates=["2026-09-30"], tickers=["QQQ", "SPY"],
        source_rows=source_rows, source_snapshot_sha256=source_hashes,
        prospective_start_date="2026-10-01",
        recorded_at_utc=datetime.fromisoformat("2026-10-01T01:00:00+00:00"),
        bootstrap=True,
    )
    output = root / "data/cache/research/ndx_observed_us_session_calendar_v1"
    output.mkdir(parents=True)
    ledger = output / "sessions.jsonl"
    append_records_durable(ledger, records)
    projection = projection_rows(records)
    projection_path = output / "sessions.csv"
    with projection_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(projection[0]))
        writer.writeheader()
        writer.writerows(projection)
    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_observed_us_session_calendar",
        "status": "OBSERVED_SESSION_CALENDAR_CURRENT",
        "calendar_scope": "OBSERVED_COMMON_QQQ_REFERENCE_OHLC_ONLY",
        "start_date": "2026-09-30",
        "prospective_start_date": "2026-10-01",
        "timezone": "America/New_York",
        "open_time_policy": "NOMINAL_REGULAR_SESSION_09_30_NEW_YORK",
        "close_time_policy": "CONSERVATIVE_REGULAR_SESSION_COMPLETION_BOUNDARY_16_00_NEW_YORK",
        "actual_early_close_timestamp_asserted": False,
        "future_or_in_progress_sessions_included": False,
        "append_only_ledger": True,
        "retrospective_backfill_allowed": False,
        "missed_multiple_session_action": "FAIL_CLOSED_REQUIRE_NEW_REVIEWED_CALENDAR_VERSION",
        "bootstrap_history_counts_as_fresh_evidence": False,
        "source_history_revision_allowed": False,
        "session_count": 1,
        "bootstrap_session_count": 1,
        "prospective_observed_session_count": 0,
        "decision_eligible_session_count": 0,
        "latest_session_date": "2026-09-30",
        "latest_record_sha256": records[-1]["record_sha256"],
        "monthly_first_session_dates": ["2026-09-30"],
        "verified_next_session_link_count": 0,
        "inputs": {
            "sources": [
                {
                    "ticker": ticker, "path": source_paths[ticker].as_posix(),
                    "sha256": source_hashes[ticker], "rows": 1,
                    "data_start": "2026-09-30", "data_end": "2026-09-30",
                }
                for ticker in ("QQQ", "SPY")
            ],
            "engine": {"path": engine.as_posix(), "sha256": sha256_file(engine)},
            "runner": {"path": runner.as_posix(), "sha256": sha256_file(runner)},
        },
        "artifacts": {
            "append_only_ledger": {
                "path": ledger.as_posix(), "rows": 1, "sha256": sha256_file(ledger),
            },
            "session_projection": {
                "path": projection_path.as_posix(), "rows": 1,
                "sha256": sha256_file(projection_path), "derived_from_ledger": True,
            },
        },
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "state_changed": False,
        "broker_snapshot_changed": False,
        "today_advice_changed": False,
        "order_creation_allowed": False,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return root, manifest_path


IMPLEMENTATION_KEYS = (
    "portfolio_optimization_track_only",
    "selector_matrix_exact",
    "dynamic_k_contract_exact",
    "point_in_time_snapshot_builder",
    "decision_close_cutoff_separated",
    "verified_us_session_calendar",
    "candidate_input_cutoff_recomputed",
    "candidate_training_end_recomputed",
    "snapshot_sealed_before_execution_open",
    "full_dynamic_k_orchestration",
    "fresh_search_only_enforced",
    "immutable_per_k_checkpoint_resume",
    "five_role_lock_deterministic",
    "missing_role_fail_closed",
    "decision_artifact_matrix_exact",
    "one_security_per_issuer_enforced",
    "lifecycle_identity_fail_closed",
    "return_and_execution_price_channels_separate",
    "immutable_incumbent_baseline",
    "append_only_monthly_runner",
    "artifact_verifier",
    "runner_registered",
    "selector_registry_active",
    "no_backfill_verified",
    "next_session_execution_verified",
    "append_only_verified",
    "live_isolation_verified",
)
INPUT_KEYS = (
    "fresh_membership_snapshot_available",
    "taxonomy_bound_to_membership_hash",
    "complete_k_coordinate_set_available",
    "training_prices_available_through_decision_close",
    "target_nav_asof_available",
    "original_8_same_calendar_available",
    "target_012922_same_calendar_available",
)


def _ready_facts() -> dict[str, bool]:
    return {key: True for key in (*IMPLEMENTATION_KEYS, *INPUT_KEYS)}


class DynamicShadowActivationReadinessTests(unittest.TestCase):
    def test_caller_supplied_true_booleans_can_never_activate(self) -> None:
        result = evaluate_activation_readiness(_ready_facts())
        self.assertEqual(result["status"], BLOCKED_STATUS)
        self.assertFalse(result["automation_registration_allowed"])
        self.assertFalse(result["decision_generation_allowed"])
        self.assertFalse(result["caller_supplied_booleans_can_activate"])
        self.assertIn(
            "immutable_artifact_evidence_not_evaluated",
            {row["code"] for row in result["blockers"]},
        )
        self.assertFalse(result["historical_candidate_replay_allowed"])
        self.assertFalse(result["retrospective_backfill_allowed"])
        self.assertFalse(result["frozen_forward_candidates_allowed_as_dynamic_source"])

    def test_missing_decision_cutoff_blocks_registration(self) -> None:
        facts = _ready_facts()
        facts["decision_close_cutoff_separated"] = False
        result = evaluate_activation_readiness(facts)
        self.assertEqual(result["status"], BLOCKED_STATUS)
        self.assertFalse(result["automation_registration_allowed"])
        self.assertEqual(
            {row["code"] for row in result["blockers"]},
            {"decision_close_cutoff_separated", "immutable_artifact_evidence_not_evaluated"},
        )

    def test_missing_future_inputs_blocks_decision_and_registration(self) -> None:
        facts = _ready_facts()
        facts["fresh_membership_snapshot_available"] = False
        result = evaluate_activation_readiness(facts)
        self.assertFalse(result["implementation_ready"])
        self.assertFalse(result["prospective_input_ready"])
        self.assertFalse(result["decision_generation_allowed"])
        self.assertFalse(result["automation_registration_allowed"])

    def test_original8_and_012922_same_calendar_are_independent_required_inputs(self) -> None:
        facts = _ready_facts()
        facts["original_8_same_calendar_available"] = False
        result = evaluate_activation_readiness(facts)
        self.assertFalse(result["prospective_input_ready"])
        self.assertIn(
            "original_8_same_calendar_available",
            {row["code"] for row in result["prospective_input_blockers"]},
        )
        facts = _ready_facts()
        facts["target_012922_same_calendar_available"] = False
        result = evaluate_activation_readiness(facts)
        self.assertFalse(result["prospective_input_ready"])
        self.assertIn(
            "target_012922_same_calendar_available",
            {row["code"] for row in result["prospective_input_blockers"]},
        )

    def test_monthly_cost_is_every_k_not_fixed_eight(self) -> None:
        plan = estimate_monthly_search_cost({"strict_technology": 16, "technology_plus_adjacent": 21})
        self.assertEqual(plan["total_track_k_shards"], 37)
        self.assertEqual(plan["exact_shards"], 27)
        self.assertEqual(plan["bounded_shards"], 10)
        self.assertEqual([row["k"] for row in plan["tracks"][0]["k_shards"]], list(range(1, 17)))
        self.assertEqual([row["k"] for row in plan["tracks"][1]["k_shards"]], list(range(1, 22)))

    def test_selector_matrix_must_be_exact_cartesian_product(self) -> None:
        roles = ["RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE"]
        tracks = ["strict_technology", "technology_plus_adjacent"]
        registry = {
            "selector_matrix": {
                "universe_tracks": tracks,
                "policy_roles": roles,
                "expected_selector_count": 10,
                "selectors": [
                    {"universe_track": track, "policy_role": role}
                    for track in tracks
                    for role in roles
                ],
            }
        }
        self.assertTrue(validate_selector_matrix(registry))
        registry_with_duplicate = copy.deepcopy(registry)
        registry_with_duplicate["selector_matrix"]["selectors"].append(
            copy.deepcopy(registry_with_duplicate["selector_matrix"]["selectors"][0])
        )
        self.assertFalse(validate_selector_matrix(registry_with_duplicate))
        registry["selector_matrix"]["selectors"].pop()
        self.assertFalse(validate_selector_matrix(registry))

    def test_source_hash_binding_rejects_path_masquerade_and_wrong_hash(self) -> None:
        registry_path = ROOT / "config" / "ndx_dynamic_shadow_selector_registry_v1.yaml"
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        sources = registry["source_contracts"]
        bindings = (
            ("objective", "objective_sha256"),
            ("dynamic_walkforward", "dynamic_walkforward_sha256"),
            ("selector_policy_module", "selector_policy_module_sha256"),
        )
        for section, hash_key in bindings:
            sources[hash_key] = sha256_file(ROOT / sources[section]["path"])
        self.assertTrue(validate_bound_source_hashes(registry, ROOT))
        wrong_hash = copy.deepcopy(registry)
        wrong_hash["source_contracts"]["objective_sha256"] = "0" * 64
        self.assertFalse(validate_bound_source_hashes(wrong_hash, ROOT))
        masquerade = copy.deepcopy(registry)
        masquerade["source_contracts"]["objective"]["path"] = "README.md"
        masquerade["source_contracts"]["objective_sha256"] = sha256_file(ROOT / "README.md")
        self.assertFalse(validate_bound_source_hashes(masquerade, ROOT))

    def test_output_cannot_escape_canonical_research_directory(self) -> None:
        with self.assertRaisesRegex(ValueError, "canonical research directory"):
            _validated_output(ROOT / "config" / "config.yaml")
        accepted = _validated_output(
            ROOT / "data/cache/research/ndx_dynamic_shadow_activation_readiness_v1/test.json"
        )
        self.assertEqual(
            accepted.parent,
            (ROOT / "data/cache/research/ndx_dynamic_shadow_activation_readiness_v1").resolve(),
        )

    def test_original8_control_is_reproduced_not_trusted_by_exists(self) -> None:
        canonical = ROOT / "data/cache/research/ndx_original_8_control_v1/manifest.json"
        result = verify_original8_control_manifest(canonical, ROOT)
        self.assertTrue(result["verified"])
        self.assertEqual(result["security_count"], 8)
        self.assertFalse(result["broker_current_overlay_included"])
        masquerade = verify_original8_control_manifest(ROOT / "README.md", ROOT)
        self.assertFalse(masquerade["verified"])
        self.assertIn("not canonical", masquerade["error"])

    def test_observed_calendar_is_reproduced_and_path_bound(self) -> None:
        with TemporaryDirectory() as directory:
            root, canonical = _healthy_observed_calendar_fixture(directory)
            result = verify_observed_session_calendar_manifest(canonical, root)
            self.assertTrue(result["verified"], result["error"])
            records = [
                json.loads(line)
                for line in canonical.with_name("sessions.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]
            self.assertEqual(result["session_count"], len(records))
            self.assertEqual(result["prospective_observed_session_count"], 0)
            self.assertEqual(result["decision_eligible_session_count"], 0)
            masquerade = verify_observed_session_calendar_manifest(
                root / "README.md", root,
            )
            self.assertFalse(masquerade["verified"])
            self.assertIn("not canonical", masquerade["error"])

    def test_observed_calendar_rejects_source_or_engine_hash_drift(self) -> None:
        with TemporaryDirectory() as directory:
            root, canonical = _healthy_observed_calendar_fixture(directory)
            qqq = (root / "data/cache/QQQ.csv").resolve()
            engine = (root / "backtest/ndx_observed_session_calendar.py").resolve()

            def drift_source(path: Path) -> str:
                return "0" * 64 if path.resolve() == qqq else sha256_file(path)

            with patch(
                "backtest.ndx_dynamic_shadow_activation_readiness.sha256_file",
                side_effect=drift_source,
            ):
                result = verify_observed_session_calendar_manifest(canonical, root)
            self.assertFalse(result["verified"])
            self.assertIn("source hash mismatch", result["error"])

            def drift_engine(path: Path) -> str:
                return "0" * 64 if path.resolve() == engine else sha256_file(path)

            with patch(
                "backtest.ndx_dynamic_shadow_activation_readiness.sha256_file",
                side_effect=drift_engine,
            ):
                result = verify_observed_session_calendar_manifest(canonical, root)
            self.assertFalse(result["verified"])
            self.assertIn("engine hash mismatch", result["error"])


if __name__ == "__main__":
    unittest.main()
