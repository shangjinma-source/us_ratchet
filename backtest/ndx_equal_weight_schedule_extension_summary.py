"""Immutable Chinese summary of the verified 323-row schedule-extension replay.

The report is a read-only research diagnostic.  It reuses the canonical runner
verifier, summarizes each universe track independently, and never ranks or
admits a candidate.  The full 323-row economic payload remains in the source
results artifact; this bundle stores a hash-bound reference for every row.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from backtest import ndx_equal_weight_schedule_extension_runner as runner


SOURCE_OUTPUT_RELATIVE = Path("data/cache/research/eqcad_v1")
OUTPUT_RELATIVE = Path("data/cache/research/eqsum_v1")
MODULE_RELATIVE = Path("backtest/ndx_equal_weight_schedule_extension_summary.py")
SCRIPT_RELATIVE = Path("scripts/ndx_equal_weight_schedule_extension_summary.py")
EXPECTED_TRANSITIONS = {
    "PASS_TO_PASS": 213,
    "FAIL_TO_PASS": 62,
    "FAIL_TO_FAIL": 48,
    "PASS_TO_FAIL": 0,
}
EXPECTED_NONWORSE_CORRECTED = 133
USER_PREFERENCE_TICKERS = ("AMAT", "AVGO", "CDNS", "GOOG")


class NdxEqualWeightScheduleExtensionSummaryError(ValueError):
    """Raised when a source or rendered summary fails closed."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return _sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise NdxEqualWeightScheduleExtensionSummaryError(f"{label} is not numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise NdxEqualWeightScheduleExtensionSummaryError(
            f"{label} is not numeric"
        ) from exc
    if not math.isfinite(result):
        raise NdxEqualWeightScheduleExtensionSummaryError(f"{label} is not finite")
    return result


def _read_mapping(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxEqualWeightScheduleExtensionSummaryError(
            f"cannot read {label}: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            f"{label} must be a mapping"
        )
    return raw, value


def _direction_counts(values: Sequence[float], *, lower_is_better: bool) -> dict[str, Any]:
    tolerance = 1e-12
    improved = 0
    unchanged = 0
    degraded = 0
    for value in values:
        if abs(value) <= tolerance:
            unchanged += 1
        elif (value < 0) == lower_is_better:
            improved += 1
        else:
            degraded += 1
    return {
        "improved_rows": improved,
        "unchanged_rows": unchanged,
        "degraded_rows": degraded,
        "change_min": min(values),
        "change_median": statistics.median(values),
        "change_max": max(values),
    }


def _transition(result: Mapping[str, Any]) -> str:
    before = result["original_schedule_b"]["daily_risk_audit"][
        "failure_session_count"
    ]
    after = result["continued_schedule_a"]["daily_risk_audit"][
        "failure_session_count"
    ]
    if type(before) is not int or type(after) is not int or min(before, after) < 0:
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "risk failure session counts are invalid"
        )
    return ("FAIL" if before else "PASS") + "_TO_" + (
        "FAIL" if after else "PASS"
    )


def _validate_result_boundary(result: Mapping[str, Any], index: int) -> None:
    coordinate = result.get("source_coordinate")
    if (
        not isinstance(coordinate, Mapping)
        or coordinate.get("source_batch") != runner.SOURCE_BATCH
        or coordinate.get("job_search_class") != runner.JOB_SEARCH_CLASS
        or coordinate.get("evaluation_semantics_sha256") != runner.EVALUATOR_SHA256
        or coordinate.get("selection_date") != runner.SELECTION_DATE
        or coordinate.get("universe_track") not in runner.TRACK_EXPECTED_COUNTS
        or result.get("stored_identity_weights_trace_and_13_summary_reproduced_before_a")
        is not True
        or result.get("candidate_set_or_weight_search_run") is not False
        or result.get("threshold_changed") is not False
        or result.get("portfolio_cash_changed") is not False
        or result.get("transaction_cost_changed") is not False
        or result.get("fresh_oos_consumed") is not False
        or result.get("admission_claimed") is not False
        or result.get("promotion_allowed") is not False
        or result.get("live_mutation_allowed") is not False
        or result.get("order_creation_allowed") is not False
    ):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            f"source result boundary changed at row {index}"
        )
    tickers = result.get("tickers")
    weights = result.get("weights")
    if (
        not isinstance(tickers, list)
        or not tickers
        or len(tickers) != result.get("holding_count")
        or len(set(tickers)) != len(tickers)
        or not isinstance(weights, Mapping)
        or list(weights) != tickers
        or not math.isclose(
            sum(_finite(weights[ticker], "candidate weight") for ticker in tickers),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    ):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            f"source result identity changed at row {index}"
        )
    comparison = result.get("ab_comparison")
    if (
        not isinstance(comparison, Mapping)
        or comparison.get("ranking_score_computed") is not False
        or type(comparison.get("a_nonworse_return_and_corrected_drawdown"))
        is not bool
    ):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            f"source corrected comparison is missing at row {index}"
        )


def _track_summary(track: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    transitions = Counter(_transition(row) for row in rows)
    return_changes = [
        _finite(row["ab_comparison"]["cumulative_path_return_change"], "return change")
        for row in rows
    ]
    corrected_dd_changes = [
        _finite(
            row["ab_comparison"]["corrected_path_max_drawdown_change"],
            "corrected drawdown change",
        )
        for row in rows
    ]
    fee_changes = [
        _finite(
            row["ab_comparison"]["transaction_cost_usd_change"], "fee change"
        )
        for row in rows
    ]
    remaining_candidate_reasons: Counter[str] = Counter()
    remaining_session_reasons: Counter[str] = Counter()
    for row in rows:
        audit = row["continued_schedule_a"]["daily_risk_audit"]
        reasons = audit.get("failure_reason_counts")
        if not isinstance(reasons, Mapping):
            raise NdxEqualWeightScheduleExtensionSummaryError(
                "continued risk failure reasons are invalid"
            )
        if audit["failure_session_count"]:
            remaining_candidate_reasons.update(reasons.keys())
        for reason, count in reasons.items():
            if type(count) is not int or count < 0:
                raise NdxEqualWeightScheduleExtensionSummaryError(
                    "continued risk reason count is invalid"
                )
            remaining_session_reasons[str(reason)] += count
    return {
        "universe_track": track,
        "candidate_rows": len(rows),
        "source_reported_eligible_rows": sum(
            row["source_failure_class"] == "SOURCE_REPORTED_ELIGIBLE"
            for row in rows
        ),
        "source_whole_lot_only_failure_rows": sum(
            row["source_failure_class"] == "WHOLE_LOT_EXECUTABILITY_FAILED_ONLY"
            for row in rows
        ),
        "risk_status_transitions": {
            key: transitions[key]
            for key in ("PASS_TO_PASS", "FAIL_TO_PASS", "FAIL_TO_FAIL", "PASS_TO_FAIL")
        },
        "a_nonworse_return_and_corrected_drawdown_rows": sum(
            row["ab_comparison"]["a_nonworse_return_and_corrected_drawdown"]
            for row in rows
        ),
        "cumulative_path_return_change": _direction_counts(
            return_changes, lower_is_better=False
        ),
        "corrected_path_max_drawdown_change": _direction_counts(
            corrected_dd_changes, lower_is_better=True
        ),
        "transaction_cost_usd_change": _direction_counts(
            fee_changes, lower_is_better=True
        ),
        "remaining_failure_candidate_rows": transitions["FAIL_TO_FAIL"],
        "remaining_failure_candidate_reason_counts": dict(
            sorted(remaining_candidate_reasons.items())
        ),
        "remaining_failure_session_reason_counts": dict(
            sorted(remaining_session_reasons.items())
        ),
    }


def summarize_verified_results(
    results_payload: Mapping[str, Any], *, source_evidence: Mapping[str, Any]
) -> dict[str, Any]:
    """Summarize an already-verified full result without ranking candidates."""

    rows = results_payload.get("results")
    if (
        results_payload.get("schema_version") != 1
        or results_payload.get("result_type")
        != "ndx_equal_weight_schedule_extension_full_ab_report"
        or results_payload.get("status") != "COMPLETE"
        or results_payload.get("cross_track_or_evaluator_ranking_performed") is not False
        or results_payload.get("candidate_set_or_weight_search_run") is not False
        or results_payload.get("admission_claimed") is not False
        or results_payload.get("promotion_allowed") is not False
        or results_payload.get("live_mutation_allowed") is not False
        or results_payload.get("order_creation_allowed") is not False
        or not isinstance(rows, list)
        or len(rows) != runner.EXPECTED_TOTALS["total"]
    ):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "verified full result contract changed"
        )
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise NdxEqualWeightScheduleExtensionSummaryError(
                f"source result row {index} is invalid"
            )
        _validate_result_boundary(row, index)
    candidate_keys = [str(row.get("candidate_key") or "") for row in rows]
    if (
        any(len(key) != 24 for key in candidate_keys)
        or len(set(candidate_keys)) != len(candidate_keys)
    ):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "source candidate references are incomplete or duplicated"
        )
    grouped = {
        track: [
            row
            for row in rows
            if row["source_coordinate"]["universe_track"] == track
        ]
        for track in runner.TRACK_EXPECTED_COUNTS
    }
    if any(
        len(grouped[track]) != runner.TRACK_EXPECTED_COUNTS[track]["total"]
        for track in grouped
    ):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "source track coverage changed"
        )
    track_summaries = [
        _track_summary(track, grouped[track]) for track in runner.TRACK_EXPECTED_COUNTS
    ]
    combined_transitions = {
        key: sum(item["risk_status_transitions"][key] for item in track_summaries)
        for key in EXPECTED_TRANSITIONS
    }
    nonworse = sum(
        item["a_nonworse_return_and_corrected_drawdown_rows"]
        for item in track_summaries
    )
    if combined_transitions != EXPECTED_TRANSITIONS or nonworse != EXPECTED_NONWORSE_CORRECTED:
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "verified full result no longer matches the preregistered aggregate checks"
        )
    preference_rows = [
        row
        for row in rows
        if tuple(row["tickers"]) == USER_PREFERENCE_TICKERS
        and all(
            math.isclose(
                _finite(row["weights"][ticker], "user preference weight"),
                0.25,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            for ticker in USER_PREFERENCE_TICKERS
        )
    ]
    if (
        len(preference_rows) != 2
        or {row["source_coordinate"]["universe_track"] for row in preference_rows}
        != set(runner.TRACK_EXPECTED_COUNTS)
    ):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "USER_PREFERENCE reference coverage changed"
        )
    preference = []
    for row in preference_rows:
        before = row["original_schedule_b"]
        after = row["continued_schedule_a"]
        preference.append(
            {
                "reference_role": "USER_PREFERENCE_REFERENCE_ONLY",
                "universe_track": row["source_coordinate"]["universe_track"],
                "candidate_key": row["candidate_key"],
                "portfolio_id": row["portfolio_id"],
                "holding_count": row["holding_count"],
                "tickers": list(row["tickers"]),
                "b_cumulative_path_return": _finite(
                    before["summary"]["whole_lot_path_return_net"], "preference B return"
                ),
                "a_cumulative_path_return": _finite(
                    after["summary"]["whole_lot_path_return_net"], "preference A return"
                ),
                "return_change": _finite(
                    row["ab_comparison"]["cumulative_path_return_change"],
                    "preference return change",
                ),
                "b_corrected_max_drawdown": _finite(
                    before["daily_risk_audit"][
                        "corrected_drawdown_with_initial_capital_peak"
                    ],
                    "preference B corrected drawdown",
                ),
                "a_corrected_max_drawdown": _finite(
                    after["daily_risk_audit"][
                        "corrected_drawdown_with_initial_capital_peak"
                    ],
                    "preference A corrected drawdown",
                ),
                "corrected_max_drawdown_change": _finite(
                    row["ab_comparison"]["corrected_path_max_drawdown_change"],
                    "preference corrected drawdown change",
                ),
                "b_transaction_cost_usd": _finite(
                    before["summary"]["whole_lot_total_transaction_cost_usd"],
                    "preference B fee",
                ),
                "a_transaction_cost_usd": _finite(
                    after["summary"]["whole_lot_total_transaction_cost_usd"],
                    "preference A fee",
                ),
                "transaction_cost_usd_change": _finite(
                    row["ab_comparison"]["transaction_cost_usd_change"],
                    "preference fee change",
                ),
                "terminal_value_usd_change": _finite(
                    after["summary"]["whole_lot_terminal_value_usd"],
                    "preference A terminal value",
                )
                - _finite(
                    before["summary"]["whole_lot_terminal_value_usd"],
                    "preference B terminal value",
                ),
                "b_risk_failure_sessions": before["daily_risk_audit"][
                    "failure_session_count"
                ],
                "a_risk_failure_sessions": after["daily_risk_audit"][
                    "failure_session_count"
                ],
                "added_rebalance_dates": list(after["added_rebalance_dates"]),
                "admission_effect": "NONE",
            }
        )
    preference.sort(key=lambda item: item["universe_track"])
    references = [
        {
            "source_result_index": index,
            "candidate_key": row["candidate_key"],
            "candidate_identity_sha256": row["candidate_identity_sha256"],
            "portfolio_id": row["portfolio_id"],
            "universe_track": row["source_coordinate"]["universe_track"],
            "holding_count": row["holding_count"],
            "tickers": list(row["tickers"]),
            "risk_status_transition": _transition(row),
            "a_nonworse_return_and_corrected_drawdown": row["ab_comparison"][
                "a_nonworse_return_and_corrected_drawdown"
            ],
        }
        for index, row in enumerate(rows)
    ]
    downside = [
        {
            "universe_track": row["source_coordinate"]["universe_track"],
            "candidate_key": row["candidate_key"],
            "portfolio_id": row["portfolio_id"],
            "holding_count": row["holding_count"],
            "tickers": list(row["tickers"]),
            "cumulative_path_return_change": _finite(
                row["ab_comparison"]["cumulative_path_return_change"],
                "downside return change",
            ),
            "corrected_path_max_drawdown_change": _finite(
                row["ab_comparison"]["corrected_path_max_drawdown_change"],
                "downside corrected drawdown change",
            ),
        }
        for row in rows
        if _finite(
            row["ab_comparison"]["corrected_path_max_drawdown_change"],
            "downside corrected drawdown change",
        )
        > 1e-12
    ]
    payload = {
        "schema_version": 1,
        "summary_type": "ndx_equal_weight_schedule_extension_summary",
        "status": "VERIFIED_HISTORICAL_RESEARCH_SUMMARY",
        "scope": {
            "source_batch": runner.SOURCE_BATCH,
            "job_search_class": runner.JOB_SEARCH_CLASS,
            "evaluation_semantics_sha256": runner.EVALUATOR_SHA256,
            "selection_date": runner.SELECTION_DATE,
            "candidate_rows": 323,
            "source_reported_eligible_rows": 213,
            "source_whole_lot_only_failure_rows": 110,
            "mechanism": "CONTINUE_EXISTING_EQUAL_WEIGHT_21_SESSION_CADENCE_TO_FROZEN_PATH_END",
            "portfolio_optimization_track": True,
            "migration_control_included": False,
            "dynamic_holding_count_preserved": True,
        },
        "source_evidence": dict(source_evidence),
        "aggregate_audit": {
            "risk_status_transitions": combined_transitions,
            "a_nonworse_return_and_corrected_drawdown_rows": nonworse,
            "remaining_failure_candidate_rows": combined_transitions["FAIL_TO_FAIL"],
            "blanket_win_claimed": False,
        },
        "per_track": track_summaries,
        "user_preference_reference": preference,
        "corrected_drawdown_degradation_examples": downside,
        "all_candidate_references": references,
        "interpretation_boundaries": {
            "full_economic_payload_remains_in_hash_bound_source_results": True,
            "cross_track_or_evaluator_ranking_performed": False,
            "winner_selected": False,
            "user_preference_is_fixed_answer": False,
            "candidate_set_or_weight_search_run": False,
            "fresh_oos_consumed": False,
            "admission_claimed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "order_creation_allowed": False,
        },
    }
    return {**payload, "summary_sha256": _canonical_sha256(payload)}


def _source_capture(repository_root: Path, source_output_root: Path):
    expected = (repository_root / SOURCE_OUTPUT_RELATIVE).resolve()
    if source_output_root.resolve() != expected:
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "source runner output root is not canonical"
        )
    runs = [path for path in (expected / "runs").iterdir() if path.is_dir()]
    if len(runs) != 1:
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "canonical source must contain exactly one fingerprint run"
        )
    run_dir = runs[0]
    manifest_path = run_dir / "manifest.json"
    results_path = run_dir / "results.json"
    manifest_raw, manifest = _read_mapping(manifest_path, "source runner manifest")
    results_raw, results = _read_mapping(results_path, "source full results")
    verified = runner.verify_locked_replay_output(
        repository_root=repository_root,
        output_root=expected,
    )
    if (
        manifest_path.read_bytes() != manifest_raw
        or results_path.read_bytes() != results_raw
        or verified.get("status") != "VERIFIED_COMPLETE"
        or verified.get("verified_candidate_rows") != 323
        or verified.get("verified_track_count") != 2
        or verified.get("plan_fingerprint") != run_dir.name
    ):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "canonical source changed during full verification"
        )
    descriptor = manifest.get("full_results")
    if (
        manifest.get("status") != "COMPLETE"
        or manifest.get("plan_fingerprint") != run_dir.name
        or manifest.get("completed_candidate_rows") != 323
        or manifest.get("remaining_candidate_rows") != 0
        or manifest.get("failed_batch_count") != 0
        or not isinstance(descriptor, Mapping)
        or Path(str(descriptor.get("path"))).resolve() != results_path.resolve()
        or descriptor.get("sha256") != _sha256(results_raw)
        or descriptor.get("rows") != 323
    ):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "canonical source result descriptor changed"
        )
    evidence = {
        "canonical_runner_verifier_status": verified["status"],
        "source_output_root": expected.as_posix(),
        "source_run_fingerprint": run_dir.name,
        "source_manifest_path": manifest_path.as_posix(),
        "source_manifest_file_sha256": _sha256(manifest_raw),
        "source_manifest_internal_sha256": manifest.get("manifest_sha256"),
        "source_results_path": results_path.as_posix(),
        "source_results_file_sha256": _sha256(results_raw),
        "source_result_rows": 323,
        "canonical_source_recapture_track_loads": verified[
            "canonical_source_recapture_track_loads"
        ],
    }
    return results, evidence


def build_extension_summary(
    *, repository_root: str | Path,
    source_output_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    source = (
        Path(source_output_root).resolve()
        if source_output_root is not None
        else root / SOURCE_OUTPUT_RELATIVE
    )
    results, evidence = _source_capture(root, source)
    summary = summarize_verified_results(results, source_evidence=evidence)
    code_bindings = {
        "summary_module": {
            "path": (root / MODULE_RELATIVE).as_posix(),
            "sha256": _sha256((root / MODULE_RELATIVE).read_bytes()),
        },
        "summary_cli": {
            "path": (root / SCRIPT_RELATIVE).as_posix(),
            "sha256": _sha256((root / SCRIPT_RELATIVE).read_bytes()),
        },
    }
    payload = dict(summary)
    payload.pop("summary_sha256")
    payload["code_bindings"] = code_bindings
    return {**payload, "summary_sha256": _canonical_sha256(payload)}


def render_summary_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# 等权 21 会话日程延续：323 个候选历史 A/B 汇总",
        "",
        "本报告只总结已经 canonical verifier 重建通过的历史结果。A 仅把原有等权 21 会话节奏延续到冻结路径末端；B 为旧日程。没有重新选股、调权、排名或准入。",
        "",
        "## 总体结论",
        "",
        "- 323 个候选中，213 个维持通过，62 个从失败修复为通过，48 个延续后仍失败，0 个从通过变失败。",
        "- 以累计路径收益与包含初始资本峰值的修正最大回撤同时非劣计，共 133 个候选。该数字不代表整体胜出。",
        "- 完整逐候选经济数据保留在源 results.json；本报告 JSON 提供 323 条哈希绑定索引。",
    ]
    for item in summary["corrected_drawdown_degradation_examples"]:
        lines.append(
            "- 明确下行样本："
            f"{item['universe_track']} k={item['holding_count']} "
            f"({'/'.join(item['tickers'])})，累计收益变化 "
            f"{item['cumulative_path_return_change']:+.4%}，修正最大回撤变化 "
            f"{item['corrected_path_max_drawdown_change']:+.4%}。"
        )
    lines.extend(
        [
            "",
            "## 分轨结果",
            "",
            "| 轨道 | 候选 | 通过→通过 | 失败→通过 | 失败→失败 | 通过→失败 | 收益改善/不变/退化 | 修正回撤改善/不变/退化 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in summary["per_track"]:
        transitions = item["risk_status_transitions"]
        returns = item["cumulative_path_return_change"]
        drawdown = item["corrected_path_max_drawdown_change"]
        lines.append(
            f"| {item['universe_track']} | {item['candidate_rows']} | "
            f"{transitions['PASS_TO_PASS']} | {transitions['FAIL_TO_PASS']} | "
            f"{transitions['FAIL_TO_FAIL']} | {transitions['PASS_TO_FAIL']} | "
            f"{returns['improved_rows']}/{returns['unchanged_rows']}/{returns['degraded_rows']} | "
            f"{drawdown['improved_rows']}/{drawdown['unchanged_rows']}/{drawdown['degraded_rows']} |"
        )
    lines.extend(
        [
            "",
            "## 延续后仍存在的风险失败",
            "",
            "下表的“候选数”按候选是否出现该原因计，“会话数”是该原因出现的逐日总次数；两者不可混用。",
            "",
            "| 轨道 | 剩余失败候选 | 原因（候选数；会话数） |",
            "|---|---:|---|",
        ]
    )
    for item in summary["per_track"]:
        candidate_counts = item["remaining_failure_candidate_reason_counts"]
        session_counts = item["remaining_failure_session_reason_counts"]
        reasons = "；".join(
            f"{reason}（{candidate_counts[reason]}；{session_counts[reason]}）"
            for reason in sorted(candidate_counts)
        ) or "无"
        lines.append(
            f"| {item['universe_track']} | {item['remaining_failure_candidate_rows']} | {reasons} |"
        )
    lines.extend(
        [
            "",
            "## USER_PREFERENCE 四只参照",
            "",
            "AMAT/AVGO/CDNS/GOOG 仅作为历史参照展示，不是固定答案，也不限制动态 k。收益为完整路径累计收益，不是 CAGR。",
            "",
            "| 轨道 | B收益 | A收益 | 变化 | B/A修正回撤 | B/A费用(USD) | 终值变化(USD) | B/A风险失败会话 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in summary["user_preference_reference"]:
        lines.append(
            f"| {item['universe_track']} | {item['b_cumulative_path_return']:.4%} | "
            f"{item['a_cumulative_path_return']:.4%} | {item['return_change']:+.4%} | "
            f"{item['b_corrected_max_drawdown']:.4%}/{item['a_corrected_max_drawdown']:.4%} | "
            f"{item['b_transaction_cost_usd']:.2f}/{item['a_transaction_cost_usd']:.2f} | "
            f"{item['terminal_value_usd_change']:+.2f} | "
            f"{item['b_risk_failure_sessions']}/{item['a_risk_failure_sessions']} |"
        )
    lines.extend(
        [
            "",
            "## 使用边界",
            "",
            "- 分轨统计不跨轨比较或排名。",
            "- 本报告没有产生候选赢家、正式准入、promotion、实盘变更或订单。",
            "- 这是冻结历史路径上的机制诊断，不能替代 prospective fresh PIT 动态组合证据。",
            "",
        ]
    )
    return "\n".join(lines)


def _immutable_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".eqsum-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise NdxEqualWeightScheduleExtensionSummaryError(
                    f"immutable summary artifact collision: {path.name}"
                )
    finally:
        temporary.unlink(missing_ok=True)


def write_summary_bundle(
    summary: Mapping[str, Any], *, output_dir: str | Path
) -> dict[str, Any]:
    output = Path(output_dir).resolve()
    summary_raw = _json_bytes(summary)
    report_raw = render_summary_markdown(summary).encode("utf-8")
    manifest_payload = {
        "schema_version": 1,
        "manifest_type": "ndx_equal_weight_schedule_extension_summary",
        "status": "VERIFIED_HISTORICAL_RESEARCH_SUMMARY",
        "source_results_file_sha256": summary["source_evidence"][
            "source_results_file_sha256"
        ],
        "summary_sha256": summary["summary_sha256"],
        "candidate_rows": 323,
        "artifacts": {
            "summary_json": {
                "filename": "summary.json",
                "sha256": _sha256(summary_raw),
            },
            "report_zh_markdown": {
                "filename": "report_zh.md",
                "sha256": _sha256(report_raw),
            },
        },
        "ranking_or_winner_selected": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    manifest = {
        **manifest_payload,
        "manifest_sha256": _canonical_sha256(manifest_payload),
    }
    _immutable_write(output / "summary.json", summary_raw)
    _immutable_write(output / "report_zh.md", report_raw)
    _immutable_write(output / "manifest.json", _json_bytes(manifest))
    return manifest


def verify_summary_bundle(
    manifest_path: str | Path, *, repository_root: str | Path
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    expected = (root / OUTPUT_RELATIVE / "manifest.json").resolve()
    path = Path(manifest_path).resolve()
    if path != expected:
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "summary manifest path is not canonical"
        )
    manifest_raw, manifest = _read_mapping(path, "summary manifest")
    payload = dict(manifest)
    claimed = payload.pop("manifest_sha256", None)
    if claimed != _canonical_sha256(payload) or manifest_raw != _json_bytes(manifest):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "summary manifest is not canonical"
        )
    summary_path = path.parent / "summary.json"
    report_path = path.parent / "report_zh.md"
    summary_raw, summary = _read_mapping(summary_path, "summary JSON")
    try:
        report_raw = report_path.read_bytes()
    except OSError as exc:
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "cannot read Chinese summary report"
        ) from exc
    artifacts = manifest.get("artifacts")
    if (
        not isinstance(artifacts, Mapping)
        or artifacts.get("summary_json")
        != {"filename": "summary.json", "sha256": _sha256(summary_raw)}
        or artifacts.get("report_zh_markdown")
        != {"filename": "report_zh.md", "sha256": _sha256(report_raw)}
    ):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "summary artifact descriptors changed"
        )
    rebuilt = build_extension_summary(repository_root=root)
    if summary != rebuilt or summary_raw != _json_bytes(rebuilt):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "summary JSON does not rebuild from canonical source"
        )
    if report_raw != render_summary_markdown(rebuilt).encode("utf-8"):
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "Chinese summary report does not rebuild"
        )
    write_manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_equal_weight_schedule_extension_summary",
        "status": "VERIFIED_HISTORICAL_RESEARCH_SUMMARY",
        "source_results_file_sha256": rebuilt["source_evidence"][
            "source_results_file_sha256"
        ],
        "summary_sha256": rebuilt["summary_sha256"],
        "candidate_rows": 323,
        "artifacts": {
            "summary_json": {
                "filename": "summary.json",
                "sha256": _sha256(summary_raw),
            },
            "report_zh_markdown": {
                "filename": "report_zh.md",
                "sha256": _sha256(report_raw),
            },
        },
        "ranking_or_winner_selected": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    expected_manifest = {
        **write_manifest,
        "manifest_sha256": _canonical_sha256(write_manifest),
    }
    if manifest != expected_manifest:
        raise NdxEqualWeightScheduleExtensionSummaryError(
            "summary manifest does not rebuild"
        )
    return manifest


__all__ = [
    "NdxEqualWeightScheduleExtensionSummaryError",
    "OUTPUT_RELATIVE",
    "SOURCE_OUTPUT_RELATIVE",
    "build_extension_summary",
    "render_summary_markdown",
    "summarize_verified_results",
    "verify_summary_bundle",
    "write_summary_bundle",
]
