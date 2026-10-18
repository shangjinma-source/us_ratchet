from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import yaml

from backtest.ndx_challenger_forward_evaluation import (
    summarize_forward_readiness,
    summarize_research_tracks,
)
from backtest.ndx_challenger_forward_cohort import _constraints
from backtest.ndx_local_action_execution import evaluate_local_action_execution
from backtest.ndx_dynamic_shadow_p4_evidence import verify_p4_evaluation_evidence
from backtest.ndx_dynamic_shadow_p4_replay import (
    NdxDynamicShadowP4ReplayError,
    assert_replayed_evaluations_match,
    freeze_p4_replay_source_bundle,
    replay_cohort_evaluations,
    verify_p4_economic_replay,
    verify_p4_replay_source_bundle,
)
from backtest.ndx_dynamic_shadow_transition import (
    assess_transition_readiness,
    load_transition_contract,
)
from backtest.ndx_marginal_forward import append_cohort_index
from data.versioning import file_sha256


RUN_ID = "20260905T020531.440564Z"


def _price_frame(values: list[float], dates: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({"Open": [100.0] * len(values), "Close": values}, index=dates)


def _active_and_cohort() -> tuple[pd.DataFrame, dict, dict[str, float]]:
    active_rows = [
        {
            "registry_entry_id": "FWD_PORTFOLIO", "candidate_id": "PORTFOLIO",
            "selection_role": "RETURN", "action_scope": "VARIABLE_CARDINALITY",
            "research_track": "portfolio_optimization",
            "holding_count_interpretation": "dynamic_k_portfolio_structure",
            "holding_count": 4, "candidate_tickers": "A;B;E;F",
            "frozen_target_weights": "A:0.25;B:0.25;E:0.25;F:0.25",
            "selection_rationale": "dynamic_k_return_fixture",
        },
        {
            "registry_entry_id": "FWD_MIGRATION", "candidate_id": "MIGRATION",
            "selection_role": "RETURN", "action_scope": "ADD_ONLY",
            "research_track": "migration_control",
            "holding_count_interpretation": "frozen_incumbent_migration_action_not_target_cardinality",
            "holding_count": 4, "candidate_tickers": "A;C;D;G",
            "frozen_target_weights": "A:0.25;C:0.25;D:0.25;G:0.25",
            "selection_rationale": "migration_fixture_not_target_cardinality",
        },
    ]
    active = pd.DataFrame(active_rows)
    original8 = {f"O{index}": 0.125 for index in range(8)}
    candidate_rows = []
    position_rows = []
    for row in active_rows:
        candidate_rows.append({
            **row, "track_role": "CHALLENGER",
            "execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
            "execution_constraint_failures": "",
        })
        weights = {
            item.split(":", 1)[0]: float(item.split(":", 1)[1])
            for item in row["frozen_target_weights"].split(";")
        }
        chains = {ticker: f"chain_{ticker}" for ticker in weights}
        allocation = evaluate_local_action_execution(
            weights, {ticker: 100.0 for ticker in weights}, chains,
            cash=25000, minimum_cash_buffer=100,
            **_constraints(row["action_scope"]),
        )
        for ticker, weight in weights.items():
            position_rows.append({
                "registry_entry_id": row["registry_entry_id"],
                "track_role": "CHALLENGER", "ticker": ticker,
                "target_weight": weight,
                "risk_chain": chains[ticker], "observation_close": 100.0,
                "cohort_whole_lot_shares": allocation["shares"][ticker],
            })
    original_tickers = ";".join(original8)
    original_weights = ";".join(f"{ticker}:{weight}" for ticker, weight in original8.items())
    candidate_rows.append({
        "registry_entry_id": "ORIGINAL_8_CONTROL", "candidate_id": "ORIGINAL_8",
        "selection_role": "SAME_DATE_CONTROL", "action_scope": "ORIGINAL_8_CONTROL",
        "research_track": "benchmark_control",
        "holding_count_interpretation": "original_8_incumbent_benchmark_not_target_cardinality",
        "holding_count": 8, "candidate_tickers": original_tickers,
        "frozen_target_weights": original_weights,
        "selection_rationale": "same_date_original_8_control",
        "track_role": "ORIGINAL_8_CONTROL",
        "execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
        "execution_constraint_failures": "",
    })
    for ticker, weight in original8.items():
        chains = {item: f"chain_{item}" for item in original8}
        allocation = evaluate_local_action_execution(
            original8, {item: 100.0 for item in original8}, chains,
            cash=25000, minimum_cash_buffer=100,
            **_constraints("ORIGINAL_8_CONTROL"),
        )
        position_rows.append({
            "registry_entry_id": "ORIGINAL_8_CONTROL",
            "track_role": "ORIGINAL_8_CONTROL", "ticker": ticker,
            "target_weight": weight,
            "risk_chain": chains[ticker], "observation_close": 100.0,
            "cohort_whole_lot_shares": allocation["shares"][ticker],
        })
    cohort = {
        "observation_date": "2026-01-30", "fresh_oos_eligible": True,
        "candidates": pd.DataFrame(candidate_rows),
        "positions": pd.DataFrame(position_rows),
    }
    return active, cohort, original8


def _economic_inputs() -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    observation = pd.DatetimeIndex([pd.Timestamp("2026-01-30")])
    future = pd.bdate_range("2026-02-02", periods=3)
    full = observation.append(future)
    prices = {
        "A": _price_frame([100, 100, 102, 104], full),
        "B": _price_frame([100, 100, 105, 110], full),
        "C": _price_frame([100, 100, 99, 98], full),
        "D": _price_frame([100, 100, 101, 102], full),
        "E": _price_frame([100, 100, 103, 106], full),
        "F": _price_frame([100, 100, 104, 108], full),
        "G": _price_frame([100, 100, 98, 96], full),
    }
    for index in range(8):
        prices[f"O{index}"] = _price_frame(
            [100, 100, 100 + index, 101 + index], full,
        )
    qqq_dates = pd.bdate_range(end="2026-01-30", periods=200)
    prices["QQQ"] = pd.DataFrame(
        {"Open": range(100, 300), "Close": range(100, 300)}, index=qqq_dates,
    )
    prices["QQQ"] = pd.concat([
        prices["QQQ"],
        pd.DataFrame({"Open": [300, 301, 302], "Close": [300, 301, 302]}, index=future),
    ])
    target = pd.DataFrame(
        {"Close": [1.0, 1.02, 1.04]}, index=future,
    )
    return prices, target


class EconomicReplayTests(unittest.TestCase):
    def test_replays_both_tracks_original8_and_012922(self) -> None:
        active, cohort, original8 = _active_and_cohort()
        prices, target = _economic_inputs()
        replayed = replay_cohort_evaluations(
            active, [cohort], prices, target,
            {
                "primary_horizon_trading_days": 3,
                "standardized_execution_cash_usd": 25000,
                "minimum_cash_buffer_usd": 100,
                "transaction_cost_bps": 10,
            },
            original8,
        )
        self.assertEqual(len(replayed), 2)
        self.assertEqual(
            set(replayed["research_track"]),
            {"portfolio_optimization", "migration_control"},
        )
        self.assertTrue(replayed["target_012922_mature"].all())
        self.assertTrue(replayed["paired_execution_evidence_eligible"].all())
        self.assertEqual(set(replayed["observation_regime"]), {"BULL"})
        self.assertTrue(replayed["continuous_control_return"].notna().all())

    def test_rejects_original8_or_candidate_position_substitution(self) -> None:
        active, cohort, original8 = _active_and_cohort()
        prices, target = _economic_inputs()
        changed = copy.deepcopy(cohort)
        mask = changed["positions"]["registry_entry_id"].eq("ORIGINAL_8_CONTROL")
        changed["positions"].loc[mask, "target_weight"] = [0.2] + [0.8 / 7] * 7
        with self.assertRaises(NdxDynamicShadowP4ReplayError):
            replay_cohort_evaluations(
                active, [changed], prices, target,
                {
                    "primary_horizon_trading_days": 3,
                    "standardized_execution_cash_usd": 25000,
                    "minimum_cash_buffer_usd": 100,
                    "transaction_cost_bps": 10,
                }, original8,
            )

        changed = copy.deepcopy(cohort)
        mask = changed["positions"]["registry_entry_id"].eq("FWD_PORTFOLIO")
        changed["positions"].loc[mask, "target_weight"] = [0.4, 0.2, 0.2, 0.2]
        with self.assertRaises(NdxDynamicShadowP4ReplayError):
            replay_cohort_evaluations(
                active, [changed], prices, target,
                {
                    "primary_horizon_trading_days": 3,
                    "standardized_execution_cash_usd": 25000,
                    "minimum_cash_buffer_usd": 100,
                    "transaction_cost_bps": 10,
                }, original8,
            )

    def test_raw_price_target_regime_and_archived_metric_tampering_is_detected(self) -> None:
        active, cohort, original8 = _active_and_cohort()
        prices, target = _economic_inputs()
        contract = {
            "primary_horizon_trading_days": 3,
            "standardized_execution_cash_usd": 25000,
            "minimum_cash_buffer_usd": 100,
            "transaction_cost_bps": 10,
        }
        archived = replay_cohort_evaluations(
            active, [cohort], prices, target, contract, original8,
        )
        for label in ("price", "target", "qqq", "archived"):
            with self.subTest(label=label):
                changed_prices = {key: value.copy() for key, value in prices.items()}
                changed_target = target.copy()
                changed_archived = archived.copy()
                if label == "price":
                    changed_prices["B"].iloc[-1, changed_prices["B"].columns.get_loc("Close")] = 140
                elif label == "target":
                    changed_target.iloc[-1, 0] = 1.4
                elif label == "qqq":
                    eligible = changed_prices["QQQ"].index <= pd.Timestamp(cohort["observation_date"])
                    changed_prices["QQQ"].loc[
                        changed_prices["QQQ"].index[eligible][-1], "Close"
                    ] = 1
                else:
                    changed_archived.loc[0, "continuous_return"] += 0.5
                replayed = replay_cohort_evaluations(
                    active, [cohort], changed_prices, changed_target, contract, original8,
                )
                with self.assertRaises(NdxDynamicShadowP4ReplayError):
                    assert_replayed_evaluations_match(replayed, changed_archived)

    def test_intraday_date_text_is_not_normalized_into_daily_evidence(self) -> None:
        from backtest.ndx_dynamic_shadow_p4_replay import _parse_price_bytes

        with self.assertRaises(NdxDynamicShadowP4ReplayError):
            _parse_price_bytes(
                b"Date,Open,Close\n2026-09-01T09:30:00,100,101\n", "A",
            )


class SourceBundleTests(unittest.TestCase):
    def _repository(self, root: Path) -> tuple[Path, Path]:
        spec = root / "config/ndx_challenger_forward_v5.yaml"
        registry = root / "data/cache/research/ndx_challenger_forward_registry_v5/manifest.json"
        run_dir = root / f"data/cache/research/ndx_challenger_forward_v5/evaluation_runs/{RUN_ID}"
        cache = root / "data/cache"
        funds = cache / "funds"
        for directory in (spec.parent, registry.parent, run_dir, funds):
            directory.mkdir(parents=True, exist_ok=True)
        spec.write_text("schema_version: 1\n", encoding="utf-8")
        registry.write_text("{}\n", encoding="utf-8")
        dates = pd.bdate_range("2026-01-01", periods=3)
        for ticker in ("A", "QQQ"):
            pd.DataFrame({
                "Date": dates, "Open": [100, 101, 102], "Close": [101, 102, 103],
            }).to_csv(cache / f"{ticker}.csv", index=False, lineterminator="\n")
        target = funds / "012922.csv"
        pd.DataFrame({"Date": dates, "Close": [1.0, 1.01, 1.02]}).to_csv(
            target, index=False, lineterminator="\n",
        )
        target_hash = file_sha256(target)
        target_sidecar = target.with_name(target.name + ".manifest.json")
        target_sidecar.write_text(json.dumps({
            "content_sha256": target_hash, "version_id": "TARGET_V1",
        }) + "\n", encoding="utf-8", newline="\n")
        inventory = pd.DataFrame([
            {"ticker": ticker, "path": (cache / f"{ticker}.csv").as_posix(),
             "sha256": file_sha256(cache / f"{ticker}.csv")}
            for ticker in ("A", "QQQ")
        ])
        inventory_path = run_dir / "price_inputs.csv"
        inventory.to_csv(inventory_path, index=False, lineterminator="\n")
        run = {
            "schema_version": 1,
            "manifest_type": "ndx_challenger_forward_evaluation_run",
            "evaluation_run_id": RUN_ID,
            "registered_cohorts": 1,
            "promotion_allowed": False, "live_config_changed": False,
            "state_changed": False, "today_advice_changed": False,
            "spec": {"path": spec.as_posix(), "sha256": file_sha256(spec)},
            "registry_manifest": {"path": registry.as_posix(), "sha256": file_sha256(registry)},
            "target_012922_version": {
                "path": target.as_posix(), "sha256": target_hash, "version_id": "TARGET_V1",
            },
            "artifacts": {"price_inputs": {
                "path": inventory_path.as_posix(), "rows": len(inventory),
                "sha256": file_sha256(inventory_path),
            }},
        }
        run_path = run_dir / "manifest.json"
        run_path.write_text(json.dumps(run) + "\n", encoding="utf-8", newline="\n")
        return run_path, cache / "A.csv"

    def test_freeze_reads_source_once_and_verifier_ignores_later_cache_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_path, a_path = self._repository(root)
            original = a_path.read_bytes()
            original_read_bytes = Path.read_bytes
            changed = False

            def race(path: Path) -> bytes:
                nonlocal changed
                raw = original_read_bytes(path)
                if path.resolve() == a_path.resolve() and not changed:
                    changed = True
                    path.write_text("Date,Open,Close\n2026-01-01,1,999\n", encoding="utf-8")
                return raw

            with patch.object(Path, "read_bytes", autospec=True, side_effect=race):
                manifest = freeze_p4_replay_source_bundle(run_path, repository_root=root)
            verified = verify_p4_replay_source_bundle(
                root / "data/cache/research/ndx_dynamic_shadow_p4_replay_inputs_v1"
                / RUN_ID / "manifest.json",
                repository_root=root,
            )
            self.assertEqual(verified.prices["A"].iloc[-1]["Close"], 103)
            self.assertEqual(manifest["boundaries"]["current_cache_read_during_replay"], False)
            self.assertNotEqual(file_sha256(a_path), hashlib.sha256(original).hexdigest())

    def test_frozen_price_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_path, _ = self._repository(root)
            freeze_p4_replay_source_bundle(run_path, repository_root=root)
            frozen = (
                root / "data/cache/research/ndx_dynamic_shadow_p4_replay_inputs_v1"
                / RUN_ID / "prices/A.csv"
            )
            frozen.write_text("Date,Open,Close\n2026-01-01,1,2\n", encoding="utf-8")
            with self.assertRaises(NdxDynamicShadowP4ReplayError):
                verify_p4_replay_source_bundle(
                    frozen.parent.parent / "manifest.json", repository_root=root,
                )

    def test_source_drift_before_freeze_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_path, a_path = self._repository(root)
            a_path.write_text("Date,Open,Close\n2026-01-01,1,2\n", encoding="utf-8")
            with self.assertRaises(NdxDynamicShadowP4ReplayError):
                freeze_p4_replay_source_bundle(run_path, repository_root=root)


class FullEconomicReplayIntegrationTests(unittest.TestCase):
    def _build_repository(self, root: Path, *, observation_date: str) -> Path:
        source_root = Path(__file__).resolve().parents[1]
        spec_path = root / "config/ndx_challenger_forward_v5.yaml"
        spec_path.parent.mkdir(parents=True)
        spec_path.write_bytes(
            (source_root / "config/ndx_challenger_forward_v5.yaml").read_bytes()
        )
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

        registry_dir = root / "data/cache/research/ndx_challenger_forward_registry_v5"
        registry_dir.mkdir(parents=True)
        active, cohort, original8 = _active_and_cohort()
        cohort["observation_date"] = observation_date
        active_path = registry_dir / "active_forward_registry.csv"
        active.to_csv(active_path, index=False, lineterminator="\n")
        baseline = pd.DataFrame([
            {
                "ticker": ticker, "frozen_weight": weight,
                "issuer_id": f"issuer_{ticker}", "risk_chain": f"chain_{ticker}",
            }
            for ticker, weight in original8.items()
        ])
        baseline_path = registry_dir / "original_8_forward_baseline.csv"
        baseline.to_csv(baseline_path, index=False, lineterminator="\n")
        risk_rows = []
        for row in active.to_dict("records"):
            for ticker in row["candidate_tickers"].split(";"):
                risk_rows.append({
                    "registry_entry_id": row["registry_entry_id"],
                    "ticker": ticker, "risk_chain": f"chain_{ticker}",
                })
        risk_frame = pd.DataFrame(risk_rows)
        risk_path = registry_dir / "frozen_candidate_risk_chain_map.csv"
        risk_frame.to_csv(risk_path, index=False, lineterminator="\n")
        registry_path = registry_dir / "manifest.json"
        registry = {
            "schema_version": 1,
            "manifest_type": "ndx_pure_equity_challenger_forward_registry",
            "registry_id": spec["registry_id"], "active_candidate_count": 2,
            "promotion_allowed": False,
            "inputs": {"spec": {
                "path": spec_path.as_posix(), "sha256": file_sha256(spec_path),
            }},
            "artifacts": {
                "active_registry": {
                    "path": active_path.as_posix(), "rows": len(active),
                    "sha256": file_sha256(active_path),
                },
                "baseline": {
                    "path": baseline_path.as_posix(), "rows": len(baseline),
                    "sha256": file_sha256(baseline_path),
                },
                "risk_chain_map": {
                    "path": risk_path.as_posix(), "rows": len(risk_frame),
                    "sha256": file_sha256(risk_path),
                },
            },
        }
        registry_path.write_text(
            json.dumps(registry) + "\n", encoding="utf-8", newline="\n",
        )

        observation_dir = (
            root / "data/cache/research/ndx_challenger_forward_v5/observations"
            / observation_date
        )
        observation_dir.mkdir(parents=True)
        candidates_path = observation_dir / "cohort_candidates.csv"
        positions_path = observation_dir / "cohort_positions.csv"
        cohort["candidates"].to_csv(candidates_path, index=False, lineterminator="\n")
        cohort["positions"].to_csv(positions_path, index=False, lineterminator="\n")
        cohort_manifest_path = observation_dir / "manifest.json"
        cohort_manifest = {
            "schema_version": 1,
            "manifest_type": "ndx_challenger_forward_cohort",
            "observation_date": observation_date,
            "fresh_oos_eligible": True, "cohort_origin": "same_day_registration",
            "active_candidate_count": 2, "same_date_original_8_control_count": 1,
            "promotion_allowed": False, "live_config_changed": False,
            "state_changed": False, "today_advice_changed": False,
            "inputs": {
                "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
                "registry_manifest": {
                    "path": registry_path.as_posix(), "sha256": file_sha256(registry_path),
                },
                "registry_content_sha256": file_sha256(active_path),
            },
            "artifacts": {
                "cohort_candidates": {
                    "path": candidates_path.as_posix(), "rows": len(cohort["candidates"]),
                    "sha256": file_sha256(candidates_path),
                },
                "cohort_positions": {
                    "path": positions_path.as_posix(), "rows": len(cohort["positions"]),
                    "sha256": file_sha256(positions_path),
                },
            },
        }
        cohort_manifest_path.write_text(
            json.dumps(cohort_manifest) + "\n", encoding="utf-8", newline="\n",
        )
        evaluation_root = root / "data/cache/research/ndx_challenger_forward_v5"
        index_path = evaluation_root / "cohort_index.jsonl"
        append_cohort_index(index_path, {
            "schema_version": 1, "observation_date": observation_date,
            "fresh_oos_eligible": True, "cohort_origin": "same_day_registration",
            "cohort_manifest_path": cohort_manifest_path.as_posix(),
            "cohort_manifest_sha256": file_sha256(cohort_manifest_path),
            "cohort_candidates_sha256": file_sha256(candidates_path),
            "cohort_positions_sha256": file_sha256(positions_path),
            "active_candidate_count": 2,
        })

        cache = root / "data/cache"
        observation_index = pd.DatetimeIndex([pd.Timestamp(observation_date)])
        future = pd.bdate_range(pd.Timestamp(observation_date) + pd.offsets.BDay(1), periods=126)
        all_dates = observation_index.append(future)
        price_frames: dict[str, pd.DataFrame] = {}
        for offset, ticker in enumerate(["A", "B", "C", "D", "E", "F", "G", *original8]):
            frame = pd.DataFrame({
                "Date": all_dates, "Open": [100.0] * 127,
                "Close": [100.0] + [100.0 + offset + index / 10 for index in range(126)],
            })
            frame.to_csv(cache / f"{ticker}.csv", index=False, lineterminator="\n")
            price_frames[ticker] = frame.set_index("Date")
        qqq_dates = pd.bdate_range(end=observation_date, periods=200)
        qqq = pd.DataFrame({
            "Date": qqq_dates, "Open": range(100, 300), "Close": range(100, 300),
        })
        qqq = pd.concat([
            qqq,
            pd.DataFrame({
                "Date": future, "Open": [300.0 + index for index in range(126)],
                "Close": [300.0 + index for index in range(126)],
            }),
        ], ignore_index=True)
        qqq.to_csv(cache / "QQQ.csv", index=False, lineterminator="\n")
        price_frames["QQQ"] = qqq.set_index("Date")
        funds = cache / "funds"
        funds.mkdir()
        target_path = funds / "012922.csv"
        target_frame = pd.DataFrame({
            "Date": future, "Close": [1.0 + index / 1000 for index in range(126)],
        })
        target_frame.to_csv(target_path, index=False, lineterminator="\n")
        target_hash = file_sha256(target_path)
        target_path.with_name(target_path.name + ".manifest.json").write_text(
            json.dumps({"content_sha256": target_hash, "version_id": "TARGET_FIXTURE"}) + "\n",
            encoding="utf-8", newline="\n",
        )
        target_nav = target_frame.copy()
        target_nav["Date"] = pd.to_datetime(target_nav["Date"])
        target_nav = target_nav.set_index("Date")
        replayed = replay_cohort_evaluations(
            active, [cohort], price_frames, target_nav,
            spec["forward_contract"], original8,
        )
        summary = summarize_forward_readiness(
            active, replayed, spec["forward_contract"], spec["promotion_contract"],
        )
        tracks = summarize_research_tracks(summary)

        run_dir = evaluation_root / "evaluation_runs" / RUN_ID
        run_dir.mkdir(parents=True)
        evaluations_path = run_dir / "cohort_evaluations.csv"
        summary_path = run_dir / "maturity_summary.csv"
        tracks_path = run_dir / "research_track_summary.csv"
        replayed.to_csv(evaluations_path, index=False, lineterminator="\n")
        summary.to_csv(summary_path, index=False, lineterminator="\n")
        tracks.to_csv(tracks_path, index=False, lineterminator="\n")
        inventory = pd.DataFrame([
            {"ticker": ticker, "path": (cache / f"{ticker}.csv").as_posix(),
             "sha256": file_sha256(cache / f"{ticker}.csv")}
            for ticker in sorted(price_frames)
        ])
        inventory_path = run_dir / "price_inputs.csv"
        inventory.to_csv(inventory_path, index=False, lineterminator="\n")
        artifacts = {
            "evaluations": {"path": evaluations_path.as_posix(), "rows": len(replayed), "sha256": file_sha256(evaluations_path)},
            "summary": {"path": summary_path.as_posix(), "rows": len(summary), "sha256": file_sha256(summary_path)},
            "research_track_summary": {"path": tracks_path.as_posix(), "rows": len(tracks), "sha256": file_sha256(tracks_path)},
            "price_inputs": {"path": inventory_path.as_posix(), "rows": len(inventory), "sha256": file_sha256(inventory_path)},
        }
        base = {
            "schema_version": 1, "status": "FORWARD_MONITORING_NOT_ADMISSION",
            "registered_cohorts": 1, "fresh_oos_cohorts": 1,
            "mature_evaluation_rows": 2,
            "portfolio_optimization_active_candidates": 1,
            "migration_control_active_candidates": 1,
            "policy_gate_ready_count": int(summary["policy_gate_ready"].astype(bool).sum()),
            "policy_gate_passed_count": int(summary["policy_gate_passed"].astype(bool).sum()),
            "candidate_admission_count": 0, "promotion_allowed": False,
            "live_config_changed": False, "state_changed": False,
            "today_advice_changed": False,
            "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
            "registry_manifest": {"path": registry_path.as_posix(), "sha256": file_sha256(registry_path)},
            "target_012922_version": {
                "path": target_path.as_posix(), "sha256": target_hash,
                "version_id": "TARGET_FIXTURE",
            },
        }
        run = {
            **base, "manifest_type": "ndx_challenger_forward_evaluation_run",
            "evaluation_run_id": RUN_ID,
            "cohort_index": {"path": index_path.as_posix(), "sha256": file_sha256(index_path)},
            "artifacts": artifacts,
        }
        run_path = run_dir / "manifest.json"
        run_path.write_text(json.dumps(run) + "\n", encoding="utf-8", newline="\n")
        latest_dir = evaluation_root / "latest_evaluation"
        latest_dir.mkdir()
        latest = {
            **base, "manifest_type": "ndx_challenger_forward_evaluation",
            "immutable_evaluation_run": {
                "path": run_path.as_posix(), "sha256": file_sha256(run_path),
                "evaluation_run_id": RUN_ID,
            },
        }
        latest_path = latest_dir / "manifest.json"
        latest_path.write_text(json.dumps(latest) + "\n", encoding="utf-8", newline="\n")
        freeze_p4_replay_source_bundle(run_path, repository_root=root)
        return latest_path

    def test_full_replay_then_p4_and_transition_consume_verified_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            latest_path = self._build_repository(root, observation_date="2026-10-01")
            bundle = (
                root / "data/cache/research/ndx_dynamic_shadow_p4_replay_inputs_v1"
                / RUN_ID / "manifest.json"
            )
            replay = verify_p4_economic_replay(bundle, repository_root=root)
            self.assertTrue(replay["raw_economic_path_replay_verified"])
            self.assertEqual(replay["portfolio_optimization_rows"], 1)
            self.assertEqual(replay["migration_control_rows"], 1)
            evidence = verify_p4_evaluation_evidence(latest_path, repository_root=root)
            self.assertTrue(evidence["raw_economic_path_replay_verified"])
            self.assertNotIn("RAW_ECONOMIC_REPLAY_BUNDLE_MISSING", str(evidence))
            transition = assess_transition_readiness(
                load_transition_contract(
                    Path(__file__).resolve().parents[1]
                    / "config/ndx_dynamic_shadow_transition_v1.yaml"
                ),
                repository_root=root,
            )
            self.assertNotIn("RAW_ECONOMIC_REPLAY_BUNDLE_MISSING", transition["blockers"])
            self.assertIn("P4_PORTFOLIO_OPTIMIZATION_GATE_NOT_VERIFIED", transition["blockers"])

    def test_full_replay_rejects_pre_v5_self_reported_fresh_cohort(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._build_repository(root, observation_date="2026-09-01")
            bundle = (
                root / "data/cache/research/ndx_dynamic_shadow_p4_replay_inputs_v1"
                / RUN_ID / "manifest.json"
            )
            with self.assertRaises(NdxDynamicShadowP4ReplayError):
                verify_p4_economic_replay(bundle, repository_root=root)


if __name__ == "__main__":
    unittest.main()
