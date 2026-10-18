from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_dynamic_shadow_p4_gate_v2 import (
    COHORT_COLUMNS,
    NdxDynamicShadowP4GateV2Error,
    _cohort_dates_from_calendar,
    _path_metrics,
    _regime,
    load_proposed_dynamic_p4_contract,
    rebuild_dynamic_p4_cohorts_from_canonical_chain,
    summarize_dynamic_p4_cohorts,
)
from data.versioning import file_sha256
from backtest.ndx_dynamic_shadow_daily import _jsonable, canonical_sha256, replay_lane_path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/ndx_dynamic_shadow_p4_gate_v2.yaml"
TRACKS = ("strict_technology", "technology_plus_adjacent")
ROLES = ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")


def _selector(track: str, role: str) -> str:
    return f"{track}__{role.lower()}__v1"


def _counts(decisions: int = 12) -> dict[str, int]:
    return {
        _selector(track, role): decisions
        for track in TRACKS for role in ROLES
    }


def _cohorts() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2026-10-01", periods=12, freq="MS")
    for track in TRACKS:
        for role in ROLES:
            selector = _selector(track, role)
            for index, decision in enumerate(dates):
                holding_count = (3, 4, 6)[index % 3]
                rows.append({
                    "selector_id": selector,
                    "universe_track": track,
                    "policy_role": role,
                    "decision_date": decision.date().isoformat(),
                    "execution_date": (decision + pd.Timedelta(days=1)).date().isoformat(),
                    "exit_date": (decision + pd.Timedelta(days=190)).date().isoformat(),
                    "starting_portfolio_id": f"{selector}:{index}",
                    "evaluation_path_semantics": (
                        "SELECTOR_POLICY_CONTINUOUS_PATH_WITH_SUBSEQUENT_MONTHLY_REBALANCES"
                    ),
                    "fixed_starting_portfolio_hold_assumed": False,
                    "holding_count": holding_count,
                    "active_tickers": "[\"AAA\",\"BBB\"]",
                    "active_security_ids": "[\"security:a\",\"security:b\"]",
                    "horizon_trading_sessions": 126,
                    "return_basis": "126_SESSION_CUMULATIVE_RETURN_NOT_ANNUALIZED",
                    "observation_regime": "BULL" if index % 2 else "BEAR",
                    "portfolio_return": 0.12,
                    "original_8_return": 0.10,
                    "target_012922_return": 0.12,
                    "portfolio_max_drawdown": 0.10,
                    "original_8_max_drawdown": 0.12,
                    "target_012922_max_drawdown": 0.10,
                })
    return pd.DataFrame(rows, columns=sorted(COHORT_COLUMNS))


class DynamicShadowP4GateV2Tests(unittest.TestCase):
    def _nonzero_fixture(self, root: Path) -> dict[str, object]:
        contract = load_proposed_dynamic_p4_contract(CONTRACT)
        sources = contract["source_contract"]
        paths = {key: root / value for key, value in sources.items() if key in {
            "reviewed_calendar_manifest", "daily_run_manifest", "realized_decision_root",
            "selector_lane_root", "original_8_control_ledger",
            "target_012922_first_observed_trace", "target_012922_resolution_ledger",
            "fresh_search_final_root", "fresh_search_role_seal_ledger",
        }}
        decision_date = "2026-10-01"
        horizon_dates = pd.bdate_range("2026-10-02", periods=126).date.astype(str).tolist()
        calendar_dates = [decision_date, *horizon_dates]
        sessions = pd.DataFrame({
            "session_date": calendar_dates,
            "open_timestamp_utc": [f"{date}T13:30:00+00:00" for date in calendar_dates],
            "close_timestamp_utc": [f"{date}T20:00:00+00:00" for date in calendar_dates],
            "completed": True,
            "is_first_observed_session_of_month": [True, *([False] * 126)],
            "origin": "PROSPECTIVE_OBSERVED_APPEND",
            "decision_eligible": True,
        })
        prices = pd.DataFrame(
            {"AAA": [100.0, 98.0, *([110.0] * 125)]},
            index=pd.to_datetime(calendar_dates),
        )
        opens = pd.DataFrame(
            {"AAA": [100.0] * len(calendar_dates)}, index=pd.to_datetime(calendar_dates),
        )
        decision_root = paths["realized_decision_root"] / decision_date
        decision_root.mkdir(parents=True)
        final_path = paths["fresh_search_final_root"] / decision_date / "manifest.json"
        final_path.parent.mkdir(parents=True)
        final_path.write_text("{}\n", encoding="utf-8")
        paths["fresh_search_role_seal_ledger"].parent.mkdir(parents=True, exist_ok=True)
        paths["fresh_search_role_seal_ledger"].write_text("GOOD\n", encoding="utf-8")
        snapshot_sha = "a" * 64
        fingerprint = "b" * 64
        selectors = [_selector(track, role) for track in TRACKS for role in ROLES]
        candidate_rows = []
        role_rows = []
        payloads: dict[str, dict[str, object]] = {}
        for selector in selectors:
            track, role_text = selector.split("__", 1)
            role = role_text[:-4].upper()
            candidate_rows.append({
                "universe_track": track, "portfolio_id": f"{selector}:p",
                "holding_count": 1, "tickers": "AAA",
                "security_ids": f"security:{selector}",
                "issuer_ids": f"issuer:{selector}", "weights": "AAA:1",
            })
            role_rows.append({
                "selector_id": selector, "universe_track": track,
                "policy_role": role, "status": "SELECTED_FRESH_SHADOW_CANDIDATE",
                "portfolio_id": f"{selector}:p",
            })
            payload = {
                "selector_id": selector,
                "universe_track": track,
                "policy_role": role,
                "timing": {
                    "decision_date": decision_date, "execution_date": horizon_dates[0],
                    "execution_open_timestamp_utc": f"{horizon_dates[0]}T13:30:00+00:00",
                    "execution_close_timestamp_utc": f"{horizon_dates[0]}T20:00:00+00:00",
                    "candidate_sealed_at_utc": "2026-10-01T22:00:00+00:00",
                    "execution_realized_at_utc": f"{horizon_dates[0]}T21:00:00+00:00",
                },
                "status": "SELECTED_FRESH_SHADOW_CANDIDATE",
                "selected_candidate": {
                    "portfolio_id": f"{selector}:p", "holding_count": 1,
                    "targets": {
                        f"security:{selector}": {
                            "ticker": "AAA", "issuer_id": f"issuer:{selector}",
                            "target_weight": 1.0,
                        },
                    },
                },
                "provenance": {
                    "candidate_manifest_path": final_path.resolve().as_posix(),
                    "candidate_manifest_sha256": file_sha256(final_path),
                    "snapshot_manifest_sha256": snapshot_sha,
                    "snapshot_fingerprint": fingerprint,
                },
                "decision_sequence": 1,
                "previous_decision_sha256": None,
            }
            payload["payload_sha256"] = canonical_sha256(payload)
            payloads[selector] = payload
            (decision_root / f"{selector}.json").write_text(
                json.dumps(payload), encoding="utf-8",
            )
        candidates_path = final_path.parent / "candidates.csv"
        roles_path = final_path.parent / "role_lock.csv"
        pd.DataFrame(candidate_rows).to_csv(candidates_path, index=False)
        pd.DataFrame(role_rows).to_csv(roles_path, index=False)
        batch_path = decision_root / "batch_manifest.json"
        batch_path.write_text("{}\n", encoding="utf-8")

        lane_records: dict[str, list[dict[str, object]]] = {}
        replay_by_selector = {}
        for selector in selectors:
            _, rebalances, trades, path = replay_lane_path(
                [payloads[selector]], sessions=sessions,
                valuation_closes=prices, execution_opens=opens,
                valuation_end_date=horizon_dates[-1],
            )
            replay_by_selector[selector] = (rebalances, trades, path)
            records = []
            for row in path.to_dict("records"):
                date = str(row["date"])
                records.append({
                    "date": date,
                    "path_state": {
                        "cash_usd": float(row["cash_usd"]),
                        "holdings_value_usd": float(row["holdings_value_usd"]),
                        "total_value_usd": float(row["total_value_usd"]),
                        "holding_count": int(row["holding_count"]),
                        "active_security_ids": str(row["active_security_ids"]),
                        "active_tickers": str(row["active_tickers"]),
                        "holdings": str(row["holdings"]),
                    },
                    "rebalance_events": _jsonable(rebalances.loc[
                        rebalances["execution_date"].astype(str).eq(date)
                    ].to_dict("records")) if not rebalances.empty else [],
                    "trade_events": _jsonable(trades.loc[
                        trades["execution_date"].astype(str).eq(date)
                    ].to_dict("records")) if not trades.empty else [],
                    "price_evidence_sha256": "",
                })
            lane_records[selector] = records
            lane_path = paths["selector_lane_root"] / f"{selector}.jsonl"
            lane_path.parent.mkdir(parents=True, exist_ok=True)
            lane_path.write_text(selector + "\n", encoding="utf-8")
        original_records = copy.deepcopy(lane_records["strict_technology__return__v1"])
        for date in horizon_dates:
            manifest = paths["selector_lane_root"].parent / "nominal_price_evidence" / date / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text("{}\n", encoding="utf-8")
            digest = file_sha256(manifest)
            for records in [*lane_records.values(), original_records]:
                next(value for value in records if value["date"] == date)[
                    "price_evidence_sha256"
                ] = digest
        paths["original_8_control_ledger"].parent.mkdir(parents=True, exist_ok=True)
        paths["original_8_control_ledger"].write_text("original\n", encoding="utf-8")
        paths["target_012922_first_observed_trace"].write_text("trace\n", encoding="utf-8")
        paths["target_012922_resolution_ledger"].parent.mkdir(parents=True, exist_ok=True)
        paths["target_012922_resolution_ledger"].write_text("resolution\n", encoding="utf-8")
        target_source = paths["target_012922_resolution_ledger"].parent / "source_snapshots/source.csv"
        target_source.parent.mkdir(parents=True)
        pd.DataFrame({
            "Date": calendar_dates,
            "Close": [100.0, *([100.0] + [103.0] * 125)],
        }).to_csv(target_source, index=False)
        resolved = [{
            "session_date": date,
            "normalized_value_usd": 25000.0 if index == 0 else 25750.0,
            "source_close": 100.0,
            "source_csv_snapshot_path": target_source.resolve().as_posix(),
        } for index, date in enumerate(calendar_dates)]
        qqq = pd.DataFrame({
            "Date": pd.bdate_range(end=decision_date, periods=220).date.astype(str),
            "Close": list(range(100, 320)),
        }).to_csv(index=False).encode("utf-8")
        snapshot_id = "c" * 64
        calendar = SimpleNamespace(
            events=[{
                "event_type": "PROSPECTIVE_V2_SESSION_OBSERVED",
                "session_date": decision_date, "decision_eligible": True,
                "source_snapshot_id": snapshot_id,
            }],
            session_projection=[{
                "session_date": date, "source_price_replay_available": True,
                "decision_eligible": True,
                "is_first_observed_session_of_month": index == 0,
                "origin": "PROSPECTIVE_V2_SESSION_OBSERVED",
                "open_timestamp_utc": f"{date}T13:30:00+00:00",
                "close_timestamp_utc": f"{date}T20:00:00+00:00",
            } for index, date in enumerate(calendar_dates)],
            source_snapshots={snapshot_id: SimpleNamespace(raw_bytes={"QQQ": qqq})},
        )
        for key in ("reviewed_calendar_manifest", "daily_run_manifest"):
            paths[key].parent.mkdir(parents=True, exist_ok=True)
            paths[key].write_text("{}\n", encoding="utf-8")
        artifacts = {
            "observed_calendar_manifest": {
                "path": paths["reviewed_calendar_manifest"].resolve().as_posix(),
                "sha256": file_sha256(paths["reviewed_calendar_manifest"]),
            },
            "realized_batch_manifests": {decision_date: {
                "path": batch_path.resolve().as_posix(), "sha256": file_sha256(batch_path),
            }},
            "selector_lane_ledgers": {
                selector: {
                    "path": (paths["selector_lane_root"] / f"{selector}.jsonl").resolve().as_posix(),
                    "sha256": file_sha256(paths["selector_lane_root"] / f"{selector}.jsonl"),
                    "rows": 126,
                } for selector in selectors
            },
            "original_8_control_ledger": {
                "path": paths["original_8_control_ledger"].resolve().as_posix(),
                "sha256": file_sha256(paths["original_8_control_ledger"]), "rows": 126,
            },
            "target_012922_trace_ledger": {
                "path": paths["target_012922_first_observed_trace"].resolve().as_posix(),
                "sha256": file_sha256(paths["target_012922_first_observed_trace"]), "rows": 126,
            },
            "nominal_price_evidence_manifest": {
                "path": (
                    paths["selector_lane_root"].parent / "nominal_price_evidence"
                    / horizon_dates[-1] / "manifest.json"
                ).resolve().as_posix(),
                "sha256": file_sha256(
                    paths["selector_lane_root"].parent / "nominal_price_evidence"
                    / horizon_dates[-1] / "manifest.json"
                ),
            },
        }
        daily = {
            "realized_decision_batches": 1,
            "latest_observed_session": horizon_dates[-1],
            "research_artifacts": artifacts,
        }
        original_manifest = root / "data/cache/research/ndx_original_8_control_v1/manifest.json"
        original_manifest.parent.mkdir(parents=True)
        original_manifest.write_text(json.dumps({
            "definition": {"securities": [
                {"ticker": f"O{index}"} for index in range(8)
            ]},
        }), encoding="utf-8")
        nominal = pd.DataFrame({
            "Date": calendar_dates,
            "ticker": "AAA",
            "Open": [100.0] * len(calendar_dates),
            "Close": prices["AAA"].tolist(),
        })
        final_manifest = {
            "snapshot_manifest_sha256": snapshot_sha,
            "snapshot_fingerprint": fingerprint,
            "original_8_sha256": file_sha256(original_manifest),
            "roles_sealed_at_utc": "2026-10-01T22:00:00+00:00",
            "artifacts": {
                "candidates": {
                    "filename": candidates_path.name,
                    "rows": len(candidate_rows),
                    "sha256": file_sha256(candidates_path),
                },
                "role_lock": {
                    "filename": roles_path.name,
                    "rows": len(role_rows),
                    "sha256": file_sha256(roles_path),
                },
            },
        }
        final_path.write_text(
            json.dumps(final_manifest, sort_keys=True), encoding="utf-8",
        )
        final_sha256 = file_sha256(final_path)
        for selector, payload in payloads.items():
            payload["provenance"]["candidate_manifest_sha256"] = final_sha256
            payload["payload_sha256"] = canonical_sha256({
                key: value for key, value in payload.items()
                if key != "payload_sha256"
            })
            (decision_root / f"{selector}.json").write_text(
                json.dumps(payload), encoding="utf-8",
            )
        return {
            "contract": contract, "paths": paths, "calendar": calendar, "daily": daily,
            "batches": [{"decision_date": decision_date}], "lane_records": lane_records,
            "original_records": original_records, "resolved": resolved,
            "nominal": nominal,
            "original_replay": replay_by_selector["strict_technology__return__v1"],
            "original_manifest_sha256": file_sha256(original_manifest),
            "horizon_dates": horizon_dates, "final_manifest": final_manifest,
        }

    def _rebuild_nonzero(self, root: Path, fixture: dict[str, object]):
        paths = fixture["paths"]

        def lane_loader(path, selector):
            if selector == "ndx_original_8_incumbent_v0":
                return fixture["original_records"]
            return fixture["lane_records"][selector]

        def role_verifier(final, ledger, *, expected_final_root):
            if Path(ledger).read_text(encoding="utf-8") != "GOOD\n":
                raise NdxDynamicShadowP4GateV2Error("role seal tampered")
            self.assertEqual(Path(expected_final_root), paths["fresh_search_final_root"])
            return {
                "record_sha256": "d" * 64,
                "roles_sealed_at_utc": "2026-10-01T22:00:00+00:00",
                "final_manifest_sha256": file_sha256(final),
            }

        def nominal_loader(path, *, root, sessions):
            frozen = fixture["nominal"].copy()
            frozen["Date"] = pd.to_datetime(frozen["Date"])
            return {}, frozen, file_sha256(path)

        with (
            patch("backtest.ndx_dynamic_shadow_p4_gate_v2.verify_canonical_reviewed_calendar_v2", return_value=fixture["calendar"]),
            patch("backtest.ndx_dynamic_shadow_p4_gate_v2.verify_daily_run_manifest", return_value=fixture["daily"]),
            patch("backtest.ndx_dynamic_shadow_p4_gate_v2.verify_realized_decision_chain", return_value=fixture["batches"]),
            patch("backtest.ndx_dynamic_shadow_p4_gate_v2.load_lane_path_ledger", side_effect=lane_loader),
            patch("backtest.ndx_dynamic_shadow_p4_gate_v2.load_target_012922_trace_ledger", return_value=[{"session_date": value} for value in fixture["horizon_dates"]]),
            patch("backtest.ndx_dynamic_shadow_p4_gate_v2.load_resolution_ledger", return_value=fixture["resolved"]),
            patch("backtest.ndx_dynamic_shadow_p4_gate_v2.verify_final_candidate_snapshot", return_value=fixture["final_manifest"]),
            patch("backtest.ndx_dynamic_shadow_p4_gate_v2.verify_final_role_seal_record", side_effect=role_verifier),
            patch("backtest.ndx_dynamic_shadow_p4_gate_v2._load_frozen_nominal_snapshot", side_effect=nominal_loader),
            patch(
                "backtest.ndx_dynamic_shadow_p4_gate_v2.load_frozen_original_8_definition",
                return_value=([], {}, fixture["original_manifest_sha256"]),
            ),
            patch("backtest.ndx_dynamic_shadow_p4_gate_v2.replay_original8_control_path", return_value=({}, *fixture["original_replay"])),
        ):
            return rebuild_dynamic_p4_cohorts_from_canonical_chain(
                fixture["contract"], repository_root=root,
            )

    def test_contract_keeps_one_year_and_registered_v5_gates_separate(self) -> None:
        contract = load_proposed_dynamic_p4_contract(CONTRACT)
        self.assertEqual(
            contract["dynamic_shadow_research_gate"]["minimum_same_calendar_trading_sessions"],
            252,
        )
        self.assertEqual(
            contract["registered_formal_v5_boundary"]["primary_horizon_trading_days"],
            126,
        )
        self.assertTrue(
            contract["registered_formal_v5_boundary"]["remains_independently_required"]
        )
        self.assertFalse(
            contract["registered_formal_v5_boundary"]["dynamic_gate_substitution_allowed"]
        )

    def test_full_distributional_fixture_is_capability_evidence_only(self) -> None:
        result = summarize_dynamic_p4_cohorts(
            _cohorts(), resolved_session_count=252,
            monthly_decision_count=12, selector_decision_counts=_counts(),
        )
        self.assertEqual(
            result["status"],
            "SYNTHETIC_CAPABILITY_EVIDENCE_ONLY",
        )
        self.assertEqual(result["proposed_gate_passed_selector_ids"], [])
        self.assertEqual(len(result["synthetic_capability_passed_selector_ids"]), 8)
        self.assertFalse(any(
            "user_preference" in value
            for value in result["synthetic_capability_passed_selector_ids"]
        ))
        self.assertTrue(all(
            item["observed_holding_counts"] == [3, 4, 6]
            for item in result["selector_summaries"]
        ))
        self.assertTrue(all(
            item["fixed_holding_count_assumed"] is False
            for item in result["selector_summaries"]
        ))
        self.assertTrue(all(
            item["subsequent_monthly_rebalances_included"] is True
            for item in result["selector_summaries"]
        ))
        self.assertFalse(result["formal_v5_gate_substitution_allowed"])
        self.assertFalse(result["proposed_gate_registered"])
        self.assertFalse(result["p5_unlock_allowed"])
        self.assertFalse(result["promotion_allowed"])
        self.assertFalse(result["live_mutation"])

    def test_126_session_cohorts_do_not_reduce_252_session_research_gate(self) -> None:
        result = summarize_dynamic_p4_cohorts(
            _cohorts(), resolved_session_count=251,
            monthly_decision_count=12, selector_decision_counts=_counts(),
        )
        self.assertEqual(result["status"], "ACCUMULATING_252_SESSION_DYNAMIC_SHADOW")
        self.assertFalse(result["dynamic_shadow_one_year_research_gate_ready"])
        self.assertEqual(result["proposed_gate_passed_selector_ids"], [])

    def test_missing_lane_or_duplicate_coordinate_fails_closed(self) -> None:
        counts = _counts()
        counts.pop(next(iter(counts)))
        with self.assertRaisesRegex(NdxDynamicShadowP4GateV2Error, "2x5"):
            summarize_dynamic_p4_cohorts(
                _cohorts(), resolved_session_count=252,
                monthly_decision_count=12, selector_decision_counts=counts,
            )
        duplicated = pd.concat([_cohorts(), _cohorts().iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(NdxDynamicShadowP4GateV2Error, "duplicated"):
            summarize_dynamic_p4_cohorts(
                duplicated, resolved_session_count=252,
                monthly_decision_count=12, selector_decision_counts=_counts(),
            )

    def test_contract_cannot_enable_substitution_fixed_k_or_live_mutation(self) -> None:
        base = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
        mutations = (
            lambda value: value["registered_formal_v5_boundary"].__setitem__(
                "dynamic_gate_substitution_allowed", True,
            ),
            lambda value: value["proposed_distributional_gate"].__setitem__(
                "fixed_holding_count", 8,
            ),
            lambda value: value["mutation_boundary"].__setitem__(
                "live_config_mutation_allowed", True,
            ),
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "contract.yaml"
            for mutate in mutations:
                payload = copy.deepcopy(base)
                mutate(payload)
                path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
                with self.assertRaisesRegex(NdxDynamicShadowP4GateV2Error, "safety contract"):
                    load_proposed_dynamic_p4_contract(path)

    def test_contract_cannot_redirect_a_verified_source_inside_repository(self) -> None:
        payload = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
        payload["source_contract"]["selector_lane_root"] = "data/cache/research/evil/lane_paths"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "contract.yaml"
            path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            with self.assertRaisesRegex(NdxDynamicShadowP4GateV2Error, "safety contract"):
                load_proposed_dynamic_p4_contract(path)

    def test_exact_calendar_coordinate_cannot_compress_a_missing_session(self) -> None:
        sessions = pd.bdate_range("2026-10-01", periods=127).date.astype(str).tolist()
        exact = _cohort_dates_from_calendar(sessions, sessions[0])
        self.assertEqual(exact, sessions[:126])
        resolved_with_gap = set(exact)
        resolved_with_gap.remove(exact[40])
        resolved_with_gap.add(sessions[126])
        self.assertNotEqual(
            [date for date in sessions if date in resolved_with_gap][:126],
            exact,
        )

    def test_pretrade_baseline_captures_entry_cost_and_first_day_shock(self) -> None:
        closes = [98.0] + [110.0] * 125
        terminal, drawdown = _path_metrics(closes, baseline_value=100.0)
        self.assertAlmostEqual(terminal, 0.10)
        self.assertAlmostEqual(drawdown, 0.02)
        self.assertNotEqual(terminal, closes[-1] / closes[0] - 1.0)

    def test_regime_uses_full_frozen_history_not_only_prospective_suffix(self) -> None:
        full = {
            date.date().isoformat(): 100.0 + index
            for index, date in enumerate(pd.bdate_range("2025-01-02", periods=200))
        }
        decision = max(full)
        self.assertEqual(_regime(full, decision), "BULL")
        suffix = dict(list(full.items())[-20:])
        self.assertEqual(_regime(suffix, decision), "INSUFFICIENT_HISTORY")

    def test_nonzero_rebuild_binds_sources_and_counts_first_day_economics(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._nonzero_fixture(root)
            cohorts, evidence = self._rebuild_nonzero(root, fixture)
            self.assertEqual(len(cohorts), 10)
            strict_records = fixture["lane_records"]["strict_technology__return__v1"]
            baseline = strict_records[0]["rebalance_events"][0]["pretrade_equity_usd"]
            first_close = strict_records[0]["path_state"]["total_value_usd"]
            terminal = strict_records[-1]["path_state"]["total_value_usd"]
            expected_return = terminal / baseline - 1.0
            expected_drawdown = 1.0 - first_close / baseline
            self.assertTrue(np.allclose(cohorts["portfolio_return"], expected_return))
            self.assertTrue(np.allclose(
                cohorts["portfolio_max_drawdown"], expected_drawdown,
            ))
            self.assertTrue(np.allclose(cohorts["original_8_return"], expected_return))
            self.assertTrue(cohorts["observation_regime"].eq("BULL").all())
            self.assertEqual(len(evidence["verified_final_candidate_manifests"]), 1)

            payload_path = (
                fixture["paths"]["realized_decision_root"] / "2026-10-01"
                / "strict_technology__return__v1.json"
            )
            original_payload = payload_path.read_text(encoding="utf-8")
            payload = json.loads(original_payload)
            payload["selected_candidate"]["targets"][
                "security:strict_technology__return__v1"
            ]["ticker"] = "EVIL"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(NdxDynamicShadowP4GateV2Error, "role seal"):
                self._rebuild_nonzero(root, fixture)
            payload_path.write_text(original_payload, encoding="utf-8")

            bad_path = root / "data/cache/research/alternate/return.jsonl"
            bad_path.parent.mkdir(parents=True)
            bad_path.write_text("strict_technology__return__v1\n", encoding="utf-8")
            descriptor = fixture["daily"]["research_artifacts"]["selector_lane_ledgers"][
                "strict_technology__return__v1"
            ]
            descriptor["path"] = bad_path.resolve().as_posix()
            descriptor["sha256"] = file_sha256(bad_path)
            with self.assertRaisesRegex(NdxDynamicShadowP4GateV2Error, "canonical source path"):
                self._rebuild_nonzero(root, fixture)

    def test_nonzero_rebuild_rejects_missing_session_and_tampered_role_seal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._nonzero_fixture(root)
            missing = fixture["resolved"].pop(40)
            fixture["resolved"].append({**missing, "session_date": "2027-12-31"})
            with self.assertRaisesRegex(NdxDynamicShadowP4GateV2Error, "contiguous"):
                self._rebuild_nonzero(root, fixture)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._nonzero_fixture(root)
            record = fixture["lane_records"]["strict_technology__return__v1"][0]
            zero_holding = json.loads(record["rebalance_events"][0]["holdings"])
            zero_holding["security:strict_technology__return__v1"]["shares"] = 0
            record["rebalance_events"][0]["holdings"] = json.dumps(zero_holding)
            record["path_state"]["holdings"] = json.dumps(zero_holding)
            with self.assertRaisesRegex(
                NdxDynamicShadowP4GateV2Error,
                "execution rebalance|sealed nominal whole-lot replay",
            ):
                self._rebuild_nonzero(root, fixture)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._nonzero_fixture(root)
            record = fixture["lane_records"]["strict_technology__return__v1"][0]
            huge_holding = json.loads(record["rebalance_events"][0]["holdings"])
            huge_holding["security:strict_technology__return__v1"]["shares"] = 999999
            record["rebalance_events"][0]["holdings"] = json.dumps(
                huge_holding, sort_keys=True, separators=(",", ":"),
            )
            record["path_state"]["holdings"] = json.dumps(
                huge_holding, sort_keys=True, separators=(",", ":"),
            )
            with self.assertRaisesRegex(
                NdxDynamicShadowP4GateV2Error,
                "sealed nominal whole-lot replay",
            ):
                self._rebuild_nonzero(root, fixture)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._nonzero_fixture(root)
            fixture["paths"]["fresh_search_role_seal_ledger"].write_text(
                "EVIL\n", encoding="utf-8",
            )
            with self.assertRaisesRegex(NdxDynamicShadowP4GateV2Error, "role seal tampered"):
                self._rebuild_nonzero(root, fixture)

    def test_first_cohort_waits_for_a_decision_session_target_resolution(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._nonzero_fixture(root)
            fixture["resolved"].pop(0)
            cohorts, evidence = self._rebuild_nonzero(root, fixture)
            self.assertTrue(cohorts.empty)
            self.assertEqual(evidence["resolved_session_count"], 126)


if __name__ == "__main__":
    unittest.main()
