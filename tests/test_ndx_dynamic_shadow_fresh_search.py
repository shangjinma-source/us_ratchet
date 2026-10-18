from __future__ import annotations

import copy
import json
import unittest
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd

import scripts.ndx_dynamic_shadow_fresh_search as fresh_search_cli

from backtest.ndx_dynamic_shadow_fresh_search import (
    EXECUTION_COORDINATE_RULE,
    FINAL_STATUS,
    NdxDynamicShadowFreshSearchError,
    append_role_seal_record,
    coordinate_hash,
    execute_fresh_shard,
    freeze_cross_k_roles,
    load_executor_contract,
    load_frozen_original_8_definition,
    verify_completed_shard,
    verify_final_candidate_snapshot,
    verify_final_role_seal_record,
    write_completed_shard,
    write_final_candidate_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
INCUMBENT = ["NVDA", "TXN", "ASML", "CDNS", "TSM", "MU", "MSFT", "GOOG"]


def _eligible() -> pd.DataFrame:
    rows = []
    chains = ["semiconductor_equipment", "eda_ip", "analog_power"]
    for track in ("strict_technology", "technology_plus_adjacent"):
        for index, ticker in enumerate(("AAA", "BBB", "CCC")):
            rows.append({
                "universe_track": track,
                "selection_date": "2026-10-01",
                "membership_snapshot_date": "2026-10-01",
                "evidence_available_date": "2026-09-01",
                "ticker": ticker,
                "security_id": f"security:{ticker.lower()}",
                "issuer_id": f"issuer:{ticker.lower()}",
                "risk_chain": chains[index],
            })
    return pd.DataFrame(rows)


def _panels():
    dates = pd.bdate_range(end="2026-10-01", periods=300)
    tickers = ["AAA", "BBB", "CCC", *INCUMBENT]
    adjusted = pd.DataFrame({"Date": dates})
    nominal = pd.DataFrame({"Date": dates})
    for index, ticker in enumerate(tickers):
        trend = 50.0 + index * 5 + np.arange(len(dates)) * (0.02 + index / 10000)
        cycle = np.sin(np.arange(len(dates)) / (8.0 + index)) * (0.2 + index / 100)
        adjusted[ticker] = trend + cycle
        nominal[ticker] = (trend + cycle) * (1.0 + index / 1000)
    target = pd.DataFrame({"Date": dates, "Close": 1.0 + np.arange(len(dates)) / 1000})
    liquidity = pd.DataFrame({
        "ticker": ["AAA", "BBB", "CCC"],
        "median_dollar_volume_usd": [100_000_000.0] * 3,
    })
    return adjusted, nominal, target, liquidity


def _jobs() -> pd.DataFrame:
    rows = []
    for track in ("strict_technology", "technology_plus_adjacent"):
        for k in range(1, 4):
            rows.append({
                "snapshot_fingerprint": "a" * 64,
                "universe_track": track,
                "decision_date": "2026-10-01",
                "execution_coordinate_rule": EXECUTION_COORDINATE_RULE,
                "decision_data_end": "2026-10-01",
                "holding_count": k,
                "eligible_security_count": 3,
                "eligible_issuer_count": 3,
                "one_security_per_issuer_required": True,
                "theoretical_issuer_combinations": {1: 3, 2: 3, 3: 1}[k],
                "job_search_class": "EXACT_ENUMERATION",
                "global_optimality_claimed": False,
                "bounded_search_disclosure": "NOT_APPLICABLE_EXACT",
                "checkpoint_key": f"{'a' * 64}/{track}/2026-10-01/holding_count_{k:04d}",
                "historical_candidate_replay_allowed": False,
                "promotion_allowed": False,
            })
    return pd.DataFrame(rows)


def _contract() -> dict:
    contract = copy.deepcopy(load_executor_contract(ROOT / "config/ndx_dynamic_shadow_fresh_search_v1.yaml"))
    search = contract["search_contract"]
    search.update({
        "fit_days": 42,
        "window_days": 42,
        "step_days": 21,
        "second_stage_per_frontier": 3,
        "max_single_weight": 1.0,
        "min_single_weight": 0.01,
        "top_weight_cap": 1.0,
        "minimum_effective_n_ratio": 0.1,
        "risk_chain_top1_cap": 1.0,
        "minimum_median_dollar_volume_usd": 1.0,
    })
    return contract


def _weights() -> dict[str, float]:
    return {ticker: 1.0 / len(INCUMBENT) for ticker in INCUMBENT}


class DynamicShadowFreshSearchTests(unittest.TestCase):
    def test_cli_rejects_noncanonical_snapshot_before_parsing_it(self) -> None:
        with TemporaryDirectory() as directory:
            snapshot = Path(directory) / "manifest.json"
            snapshot.write_text("{}\n", encoding="utf-8")
            args = Namespace(
                snapshot_manifest=str(snapshot),
                contract=str(fresh_search_cli.CANONICAL_CONTRACT),
                output_root=str(fresh_search_cli.CANONICAL_OUTPUT_ROOT),
                original_8_manifest=str(fresh_search_cli.CANONICAL_ORIGINAL8),
                resume=True,
                max_jobs=0,
            )
            with patch.object(
                fresh_search_cli, "verify_snapshot_bundle",
                side_effect=AssertionError("noncanonical snapshot was parsed"),
            ), self.assertRaisesRegex(
                NdxDynamicShadowFreshSearchError, "canonical generator root"
            ):
                fresh_search_cli.execute(args)

    def test_original8_definition_is_hash_bound_and_not_live_state(self) -> None:
        canonical = ROOT / "data/cache/research/ndx_original_8_control_v1/manifest.json"
        tickers, weights, digest = load_frozen_original_8_definition(canonical)
        self.assertEqual(tickers, INCUMBENT)
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertEqual(len(digest), 64)
        with TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "original8.json"
            changed = json.loads(canonical.read_text(encoding="utf-8"))
            changed["manifest_type"] = "caller_claimed_frozen"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(NdxDynamicShadowFreshSearchError, "unexpected original-8"):
                load_frozen_original_8_definition(path)
        mutations = (
            ("broker overlay", lambda value: value.__setitem__("broker_current_overlay_included", True), "broker overlay"),
            ("duplicate issuer", lambda value: value["definition"]["securities"][1].__setitem__(
                "issuer_id", value["definition"]["securities"][0]["issuer_id"]
            ), "not unique"),
            ("live mutation", lambda value: value["live_mutation"].__setitem__("orders", True), "live mutation"),
        )
        for label, mutate, error in mutations:
            with self.subTest(label=label), TemporaryDirectory(dir=ROOT) as directory:
                path = Path(directory) / "original8.json"
                changed = json.loads(canonical.read_text(encoding="utf-8"))
                mutate(changed)
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaisesRegex(NdxDynamicShadowFreshSearchError, error):
                    load_frozen_original_8_definition(path)

    def test_one_fresh_exact_shard_runs_without_historical_candidates(self) -> None:
        adjusted, nominal, target, liquidity = _panels()
        job = _jobs().iloc[0].to_dict()
        results, audit = execute_fresh_shard(
            job,
            eligible=_eligible(), adjusted_close=adjusted, nominal_close=nominal,
            target_aligned=target, liquidity=liquidity, incumbent=INCUMBENT,
            incumbent_weights=_weights(), contract=_contract(),
        )
        self.assertFalse(results.empty)
        self.assertFalse(results["fresh_oos"].all())
        self.assertTrue(results["fresh_point_in_time_search"].all())
        self.assertFalse(results["future_outcomes_consumed"].all())
        self.assertFalse(results["historical_consumed"].all())
        self.assertFalse(audit["search_audit"]["historical_candidate_replay_used"])
        self.assertTrue(audit["search_audit"]["security_set_enumeration_exhaustive"])
        self.assertFalse(audit["search_audit"]["weight_space_global_optimality_claimed"])

    def test_caller_bound_execution_or_wrong_search_class_fails_closed(self) -> None:
        adjusted, nominal, target, liquidity = _panels()
        for field, value, error in (
            ("execution_coordinate_rule", "2026-10-02", "execution coordinate"),
            ("job_search_class", "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND", "planned exact/bounded"),
        ):
            with self.subTest(field=field):
                job = _jobs().iloc[0].to_dict()
                job[field] = value
                with self.assertRaisesRegex(NdxDynamicShadowFreshSearchError, error):
                    execute_fresh_shard(
                        job,
                        eligible=_eligible(), adjusted_close=adjusted, nominal_close=nominal,
                        target_aligned=target, liquidity=liquidity, incumbent=INCUMBENT,
                        incumbent_weights=_weights(), contract=_contract(),
                    )

    def test_completed_checkpoint_resume_rejects_input_hash_change(self) -> None:
        adjusted, nominal, target, liquidity = _panels()
        job = _jobs().iloc[0].to_dict()
        results, audit = execute_fresh_shard(
            job, eligible=_eligible(), adjusted_close=adjusted, nominal_close=nominal,
            target_aligned=target, liquidity=liquidity, incumbent=INCUMBENT,
            incumbent_weights=_weights(), contract=_contract(),
        )
        identity = coordinate_hash(
            job, snapshot_manifest_sha256="d" * 64,
            executor_sha256="b" * 64, original_8_sha256="c" * 64,
        )
        results = results.copy()
        results["coordinate_hash"] = identity
        with TemporaryDirectory() as directory:
            write_completed_shard(directory, results, audit, coordinate_hash=identity)
            resumed, _ = verify_completed_shard(
                Path(directory) / "checkpoint.json", coordinate_hash=identity,
                expected_job=job,
            )
            self.assertEqual(len(resumed), len(results))
            with self.assertRaisesRegex(NdxDynamicShadowFreshSearchError, "identity/hash mismatch"):
                verify_completed_shard(Path(directory) / "checkpoint.json", coordinate_hash="d" * 64)

    def test_checkpoint_cannot_smuggle_foreign_job_coordinates(self) -> None:
        adjusted, nominal, target, liquidity = _panels()
        job = _jobs().iloc[0].to_dict()
        results, audit = execute_fresh_shard(
            job, eligible=_eligible(), adjusted_close=adjusted, nominal_close=nominal,
            target_aligned=target, liquidity=liquidity, incumbent=INCUMBENT,
            incumbent_weights=_weights(), contract=_contract(),
        )
        identity = coordinate_hash(
            job, snapshot_manifest_sha256="d" * 64,
            executor_sha256="b" * 64, original_8_sha256="c" * 64,
        )
        results = results.copy()
        results["coordinate_hash"] = identity
        results.loc[results.index[0], "coordinate_hash"] = "9" * 64
        with TemporaryDirectory() as directory, self.assertRaisesRegex(
            NdxDynamicShadowFreshSearchError, "do not match"
        ):
            write_completed_shard(directory, results, audit, coordinate_hash=identity)

    def test_end_to_end_all_k_then_cross_k_ten_role_freeze(self) -> None:
        adjusted, nominal, target, liquidity = _panels()
        jobs = _jobs()
        frames = []
        executor_hash = "b" * 64
        original_hash = "c" * 64
        for row in jobs.itertuples(index=False):
            job = row._asdict()
            results, _ = execute_fresh_shard(
                job, eligible=_eligible(), adjusted_close=adjusted, nominal_close=nominal,
                target_aligned=target, liquidity=liquidity, incumbent=INCUMBENT,
                incumbent_weights=_weights(), contract=_contract(),
            )
            results["coordinate_hash"] = coordinate_hash(
                job, snapshot_manifest_sha256="d" * 64,
                executor_sha256=executor_hash, original_8_sha256=original_hash,
            )
            frames.append(results)
        candidates, roles = freeze_cross_k_roles(pd.concat(frames, ignore_index=True))
        self.assertEqual(len(roles), 10)
        self.assertEqual(roles["selector_id"].nunique(), 10)
        unavailable = roles.loc[roles["policy_role"].eq("USER_PREFERENCE")]
        self.assertTrue(unavailable["status"].eq("REFERENCE_UNAVAILABLE_NOT_REPLACED").all())
        with TemporaryDirectory() as directory:
            final_root = Path(directory) / "final"
            final_dir = final_root / "2026-10-01"
            manifest = write_final_candidate_snapshot(
                final_dir, candidates, roles, jobs,
                snapshot_manifest_sha256="d" * 64,
                snapshot_fingerprint="a" * 64,
                executor_sha256=executor_hash,
                original_8_sha256=original_hash,
            )
            self.assertEqual(manifest["status"], FINAL_STATUS)
            verify_final_candidate_snapshot(final_dir / "manifest.json")
            resumed = write_final_candidate_snapshot(
                final_dir, candidates, roles, jobs,
                snapshot_manifest_sha256="d" * 64,
                snapshot_fingerprint="a" * 64,
                executor_sha256=executor_hash,
                original_8_sha256=original_hash,
            )
            self.assertEqual(resumed["candidate_sealed_at_utc"], manifest["candidate_sealed_at_utc"])
            ledger = Path(directory) / "role_seals.jsonl"
            first = append_role_seal_record(
                ledger, final_dir / "manifest.json", expected_final_root=final_root,
            )
            second = append_role_seal_record(
                ledger, final_dir / "manifest.json", expected_final_root=final_root,
            )
            self.assertEqual(first, second)
            verify_final_role_seal_record(
                final_dir / "manifest.json", ledger, expected_final_root=final_root,
            )

            manifest_path = final_dir / "manifest.json"
            changed = json.loads(manifest_path.read_text(encoding="utf-8"))
            changed["roles_sealed_at_utc"] = "2026-10-02T02:00:00+00:00"
            changed["candidate_sealed_at_utc"] = "2026-10-02T02:00:00+00:00"
            manifest_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(NdxDynamicShadowFreshSearchError, "manifest binding"):
                verify_final_role_seal_record(
                    manifest_path, ledger, expected_final_root=final_root,
                )

    def test_role_seal_missing_or_tampered_ledger_and_late_freeze_fail_closed(self) -> None:
        adjusted, nominal, target, liquidity = _panels()
        jobs = _jobs()
        frames = []
        for row in jobs.itertuples(index=False):
            job = row._asdict()
            results, _ = execute_fresh_shard(
                job, eligible=_eligible(), adjusted_close=adjusted, nominal_close=nominal,
                target_aligned=target, liquidity=liquidity, incumbent=INCUMBENT,
                incumbent_weights=_weights(), contract=_contract(),
            )
            results["coordinate_hash"] = coordinate_hash(
                job, snapshot_manifest_sha256="d" * 64,
                executor_sha256="b" * 64, original_8_sha256="c" * 64,
            )
            frames.append(results)
        candidates, roles = freeze_cross_k_roles(pd.concat(frames, ignore_index=True))
        with TemporaryDirectory() as directory:
            final_root = Path(directory) / "final"
            final_dir = final_root / "2026-10-01"
            with patch(
                "backtest.ndx_dynamic_shadow_fresh_search._system_utc_now",
                return_value=datetime(2026, 10, 2, 2, tzinfo=timezone.utc),
            ):
                write_final_candidate_snapshot(
                    final_dir, candidates, roles, jobs,
                    snapshot_manifest_sha256="d" * 64,
                    snapshot_fingerprint="a" * 64,
                    executor_sha256="b" * 64,
                    original_8_sha256="c" * 64,
                    snapshot_seal_record_sha256="8" * 64,
                    snapshot_conservative_deadline_utc="2026-10-02T13:30:00+00:00",
                )
            missing = Path(directory) / "missing.jsonl"
            with self.assertRaisesRegex(NdxDynamicShadowFreshSearchError, "no unique"):
                verify_final_role_seal_record(
                    final_dir / "manifest.json", missing, expected_final_root=final_root,
                )
            ledger = Path(directory) / "role_seals.jsonl"
            append_role_seal_record(ledger, final_dir / "manifest.json", expected_final_root=final_root)
            value = json.loads(ledger.read_text(encoding="utf-8"))
            value["record_sha256"] = "0" * 64
            ledger.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(NdxDynamicShadowFreshSearchError, "hash/boundary"):
                verify_final_role_seal_record(
                    final_dir / "manifest.json", ledger, expected_final_root=final_root,
                )

        with TemporaryDirectory() as directory, patch(
            "backtest.ndx_dynamic_shadow_fresh_search._system_utc_now",
            return_value=datetime(2026, 10, 2, 14, tzinfo=timezone.utc),
        ), self.assertRaisesRegex(NdxDynamicShadowFreshSearchError, "missed"):
            write_final_candidate_snapshot(
                directory, candidates, roles, jobs,
                snapshot_manifest_sha256="d" * 64,
                snapshot_fingerprint="a" * 64,
                executor_sha256="b" * 64,
                original_8_sha256="c" * 64,
                snapshot_seal_record_sha256="8" * 64,
                snapshot_conservative_deadline_utc="2026-10-02T13:30:00+00:00",
            )

    def test_role_lock_cannot_point_outside_frozen_candidates(self) -> None:
        adjusted, nominal, target, liquidity = _panels()
        jobs = _jobs()
        frames = []
        for row in jobs.itertuples(index=False):
            job = row._asdict()
            results, _ = execute_fresh_shard(
                job, eligible=_eligible(), adjusted_close=adjusted, nominal_close=nominal,
                target_aligned=target, liquidity=liquidity, incumbent=INCUMBENT,
                incumbent_weights=_weights(), contract=_contract(),
            )
            results["coordinate_hash"] = coordinate_hash(
                job, snapshot_manifest_sha256="d" * 64,
                executor_sha256="b" * 64, original_8_sha256="c" * 64,
            )
            frames.append(results)
        candidates, roles = freeze_cross_k_roles(pd.concat(frames, ignore_index=True))
        selected = roles.index[roles["status"].eq("SELECTED_FRESH_SHADOW_CANDIDATE")][0]
        roles.loc[selected, "portfolio_id"] = "not-a-frozen-candidate"
        with TemporaryDirectory() as directory, self.assertRaisesRegex(
            NdxDynamicShadowFreshSearchError, "does not reference"
        ):
            write_final_candidate_snapshot(
                directory, candidates, roles, jobs,
                snapshot_manifest_sha256="d" * 64,
                snapshot_fingerprint="a" * 64,
                executor_sha256="b" * 64,
                original_8_sha256="c" * 64,
            )

    def test_missing_k_coordinate_prevents_final_aggregation(self) -> None:
        jobs = _jobs()
        candidates = pd.DataFrame({"coordinate_hash": []})
        roles = pd.DataFrame({"selector_id": [f"lane-{i}" for i in range(10)]})
        with TemporaryDirectory() as directory, self.assertRaisesRegex(
            NdxDynamicShadowFreshSearchError, "does not cover every planned"
        ):
            write_final_candidate_snapshot(
                directory, candidates, roles, jobs,
                snapshot_manifest_sha256="d" * 64,
                snapshot_fingerprint="a" * 64,
                executor_sha256="b" * 64,
                original_8_sha256="c" * 64,
            )


if __name__ == "__main__":
    unittest.main()
