"""Immutable six-axis Pareto expansion of the published $25k replay summary.

This module only re-reads and verifies already-computed historical training
artifacts.  It never runs a search, consumes fresh OOS observations, selects a
live portfolio, or writes broker/config/state/order data.  Pareto membership is
computed independently for each source/evaluator/universe/date coordinate.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Mapping

from backtest import ndx_cardinality_capital_replay_summary as v1
from backtest.ndx_historical_pareto import PARETO_AXES, historical_pareto_membership


SOURCE_V1_RELATIVE = v1.OUTPUT_RELATIVE / "manifest.json"
OUTPUT_RELATIVE = Path(
    "data/cache/research/ndx_cardinality_capital_replay_pareto_summary_v2"
)


class NdxCardinalityCapitalReplayParetoSummaryError(ValueError):
    """Raised when the historical Pareto report cannot be rebuilt safely."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _canonical_sha256(value: Any) -> str:
    return _sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _read_mapping(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            f"cannot read {label}: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            f"{label} must be a mapping"
        )
    return raw, value


def _integer_field(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise NdxCardinalityCapitalReplayParetoSummaryError(f"{label} is not an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            f"{label} is not an integer"
        ) from exc
    if str(parsed) != str(value) and not isinstance(value, int):
        raise NdxCardinalityCapitalReplayParetoSummaryError(f"{label} is not canonical")
    return parsed


def _source_v1_summary(
    source_manifest: str | Path, root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = (root / SOURCE_V1_RELATIVE).resolve()
    source = Path(source_manifest).resolve()
    if source != expected:
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "published v1 summary manifest path is not canonical"
        )
    manifest_raw, manifest = _read_mapping(source, "published v1 bundle manifest")
    summary_path = source.parent / "summary.json"
    summary_raw, summary = _read_mapping(summary_path, "published v1 summary")
    try:
        verified = v1.verify_summary_bundle(source)
    except v1.NdxCardinalityCapitalReplaySummaryError as exc:
        raise NdxCardinalityCapitalReplayParetoSummaryError(str(exc)) from exc
    if source.read_bytes() != manifest_raw or summary_path.read_bytes() != summary_raw:
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "published v1 bundle changed during verification"
        )
    if verified != manifest:
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "published v1 verifier returned a different manifest"
        )
    summary_descriptor = (manifest.get("artifacts") or {}).get("summary_json")
    if (
        not isinstance(summary_descriptor, Mapping)
        or summary_descriptor.get("filename") != "summary.json"
        or summary_descriptor.get("sha256") != _sha256(summary_raw)
    ):
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "published v1 summary descriptor changed"
        )
    return summary, {
        "path": source.as_posix(),
        "sha256": _sha256(manifest_raw),
        "summary_path": summary_path.as_posix(),
        "summary_sha256": _sha256(summary_raw),
    }


def _v1_start_index(summary: Mapping[str, Any]) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    groups = summary.get("evaluator_groups")
    if not isinstance(groups, list):
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "published v1 evaluator groups are missing"
        )
    result: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for group in groups:
        if not isinstance(group, Mapping) or not isinstance(group.get("per_start"), list):
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "published v1 evaluator group is invalid"
            )
        coordinate = (
            str(group.get("source_batch") or ""),
            str(group.get("job_search_class") or ""),
            str(group.get("evaluation_semantics_sha256") or ""),
            str(group.get("universe_track") or ""),
        )
        if any(not value for value in coordinate):
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "published v1 group coordinate is incomplete"
            )
        for start in group["per_start"]:
            if not isinstance(start, Mapping):
                raise NdxCardinalityCapitalReplayParetoSummaryError(
                    "published v1 per-start record is invalid"
                )
            key = (*coordinate, str(start.get("selection_date") or ""))
            if key in result:
                raise NdxCardinalityCapitalReplayParetoSummaryError(
                    "published v1 per-start coordinate is duplicated"
                )
            for name, value in zip(
                ("source_batch", "job_search_class", "evaluation_semantics_sha256", "universe_track"),
                coordinate,
            ):
                if start.get(name) != value:
                    raise NdxCardinalityCapitalReplayParetoSummaryError(
                        f"published v1 per-start {name} disagrees with its group"
                    )
            result[key] = dict(start)
    expected = _integer_field(
        summary.get("verified_child_job_count"), "published v1 verified child count"
    )
    if len(result) != expected or expected != _integer_field(
        summary.get("planned_job_count"), "published v1 planned job count"
    ):
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "published v1 per-start count disagrees with its manifest"
        )
    return result


def _preference_with_pareto_flag(
    reference: Mapping[str, Any], pareto_ids: set[str]
) -> dict[str, Any]:
    result = dict(reference)
    candidate = result.get("candidate")
    result.update(
        {
            "displayed_regardless_of_dominance_or_compliance": True,
            "overrides_pareto_membership": False,
            "overrides_admission": False,
            "included_in_source_reported_eligible_pareto": bool(
                isinstance(candidate, Mapping)
                and candidate.get("source_reported_replay_eligible") is True
                and candidate.get("portfolio_id") in pareto_ids
            ),
        }
    )
    return result


def _candidate_payload(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Return the full validated composition, weights, metrics, and path fields."""

    return dict(candidate)


def build_capital_replay_pareto_summary(
    source_v1_manifest: str | Path, *, repository_root: str | Path
) -> dict[str, Any]:
    """Rebuild every per-coordinate six-axis Pareto set from frozen candidate bytes."""

    root = Path(repository_root).resolve()
    source_summary, source_descriptor = _source_v1_summary(source_v1_manifest, root)
    if (
        source_summary.get("top_manifest_originally_bound_child_manifest_hashes")
        is not False
        or source_summary.get(
            "historical_child_manifest_authenticity_reconstructable_from_top"
        )
        is not False
        or source_summary.get("new_summary_records_child_manifest_hashes") is not True
        or not isinstance(
            source_summary.get("raw_historical_input_bytes_currently_recoverable"), bool
        )
    ):
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "published v1 provenance limitations changed"
        )
    _integer_field(
        source_summary.get("historical_input_unrecoverable_count"),
        "published v1 unrecoverable source count",
    )
    _integer_field(
        source_summary.get("source_input_drift_count"),
        "published v1 source drift count",
    )
    v1_starts = _v1_start_index(source_summary)
    try:
        top, lineages, jobs, top_evidence = v1._verify_top(
            root / v1.TOP_MANIFEST_RELATIVE, root
        )
    except v1.NdxCardinalityCapitalReplaySummaryError as exc:
        raise NdxCardinalityCapitalReplayParetoSummaryError(str(exc)) from exc
    if source_summary.get("evidence", {}).get("top_manifest") != top_evidence["top_manifest"]:
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "published v1 summary is not bound to the current verified replay top manifest"
        )
    if _integer_field(
        source_summary.get("verified_child_job_count"), "published v1 job count"
    ) != len(jobs):
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "published v1 job count changed"
        )

    replay_root = (root / v1.TOP_MANIFEST_RELATIVE).parent.resolve()
    shortlist_path = (root / v1.SHORTLIST_RELATIVE).resolve()
    starts: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for job in jobs:
        basic = (
            str(job.get("source_batch") or ""),
            str(job.get("universe_track") or ""),
            str(job.get("selection_date") or ""),
        )
        if basic in seen:
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "replay job coordinate is duplicated"
            )
        seen.add(basic)
        lineage = lineages.get(basic[0])
        if lineage is None:
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "replay job source lineage is missing"
            )
        key = (
            basic[0],
            str(lineage["job_search_class"]),
            str(lineage["evaluation_semantics_sha256"]),
            basic[1],
            basic[2],
        )
        published = v1_starts.pop(key, None)
        if published is None:
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "replay job is absent from the published v1 per-start summary"
            )

        child_path = replay_root / basic[0] / basic[1] / basic[2] / "manifest.json"
        child_raw, child_manifest = _read_mapping(child_path, "replay child manifest")
        candidate_path = child_path.parent / "training_candidates.csv"
        candidate_raw = candidate_path.read_bytes()
        try:
            child = v1._verify_child(
                job,
                root=root,
                replay_root=replay_root,
                shortlist_path=shortlist_path,
                shortlist_sha256=top_evidence["shortlist"]["historical_sha256"],
                lineage=lineage,
            )
        except v1.NdxCardinalityCapitalReplaySummaryError as exc:
            raise NdxCardinalityCapitalReplayParetoSummaryError(str(exc)) from exc
        child.pop("_recovered_source_bytes", None)
        if child_path.read_bytes() != child_raw or candidate_path.read_bytes() != candidate_raw:
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "replay child evidence changed during verification"
            )
        if child.get("source_manifest") != published.get("source_manifest") or child[
            "source_manifest"
        ] != {"path": child_path.as_posix(), "sha256": _sha256(child_raw)}:
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "published v1 child manifest binding changed"
            )
        descriptor = (child_manifest.get("artifacts") or {}).get("candidates")
        if (
            not isinstance(descriptor, Mapping)
            or Path(str(descriptor.get("path") or "")).resolve() != candidate_path.resolve()
            or descriptor.get("sha256") != _sha256(candidate_raw)
            or child.get("artifacts", {}).get("candidates", {}).get("historical_sha256")
            != _sha256(candidate_raw)
            or published.get("artifacts", {}).get("candidates", {}).get("historical_sha256")
            != _sha256(candidate_raw)
        ):
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "candidate artifact bytes are not consistently hash-bound"
            )
        fields, raw_rows = v1._csv_rows(candidate_raw, "replay candidate artifact")
        missing = sorted(v1.REQUIRED_CANDIDATE_COLUMNS - set(fields))
        if missing:
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                f"candidate fields are missing: {missing}"
            )
        try:
            candidates = [
                v1._validate_candidate(
                    row,
                    selection_date=basic[2],
                    training_end=str(child_manifest.get("training_end") or ""),
                )
                for row in raw_rows
            ]
        except v1.NdxCardinalityCapitalReplaySummaryError as exc:
            raise NdxCardinalityCapitalReplayParetoSummaryError(str(exc)) from exc
        eligible = [item for item in candidates if item["source_reported_replay_eligible"]]
        if (
            len(candidates) != _integer_field(descriptor.get("rows"), "candidate descriptor rows")
            or len(candidates) != _integer_field(child.get("candidate_rows"), "child candidate rows")
            or len(candidates) != _integer_field(published.get("candidate_rows"), "v1 candidate rows")
            or len(eligible)
            != _integer_field(
                child.get("source_reported_replay_eligible_rows"), "child eligible rows"
            )
            or len(eligible)
            != _integer_field(
                published.get("source_reported_replay_eligible_rows"), "v1 eligible rows"
            )
        ):
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "candidate total/eligible count disagrees with published v1"
            )
        pareto_rows = []
        for item in eligible:
            rolling = item["rolling_training_statistics"]
            pareto_rows.append(
                {
                    "source_batch": key[0],
                    "evaluation_semantics_sha256": key[2],
                    "universe_track": key[3],
                    "selection_date": key[4],
                    "portfolio_id": item["portfolio_id"],
                    **{metric: rolling[metric] for metric, _ in PARETO_AXES},
                }
            )
        try:
            pareto_ids = set(historical_pareto_membership(pareto_rows))
        except ValueError as exc:
            raise NdxCardinalityCapitalReplayParetoSummaryError(str(exc)) from exc
        candidate_by_id = {item["portfolio_id"]: item for item in eligible}
        if len(candidate_by_id) != len(eligible):
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "eligible portfolio IDs are duplicated"
            )
        pareto_candidates = [
            _candidate_payload(candidate_by_id[identity])
            for identity in sorted(pareto_ids)
        ]
        preference = _preference_with_pareto_flag(
            v1._user_preference_reference(candidates), pareto_ids
        )
        starts.append(
            {
                "source_batch": key[0],
                "job_search_class": key[1],
                "evaluation_semantics_sha256": key[2],
                "evaluation_semantics": lineage["evaluation_semantics"],
                "source_evaluator_manifest": lineage["source_run_manifest"],
                "universe_track": key[3],
                "selection_date": key[4],
                "training_end": str(child_manifest["training_end"]),
                "candidate_rows": len(candidates),
                "source_reported_replay_eligible_rows": len(eligible),
                "pareto_candidate_rows": len(pareto_candidates),
                "pareto_portfolio_ids": sorted(pareto_ids),
                "pareto_candidates": pareto_candidates,
                "user_preference_reference": preference,
                "source_child_manifest": {
                    "path": child_path.as_posix(), "sha256": _sha256(child_raw)
                },
                "source_candidate_artifact": {
                    "path": candidate_path.as_posix(),
                    "sha256": _sha256(candidate_raw),
                    "rows": len(candidates),
                },
            }
        )
    if v1_starts:
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "published v1 contains per-start coordinates absent from the replay index"
        )

    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for start in starts:
        coordinate = tuple(
            start[name]
            for name in (
                "source_batch", "job_search_class",
                "evaluation_semantics_sha256", "universe_track",
            )
        )
        grouped.setdefault(coordinate, []).append(start)
    groups = []
    for coordinate, values in sorted(grouped.items()):
        ordered = sorted(values, key=lambda item: item["selection_date"])
        source_batch, job_class, evaluator_hash, track = coordinate
        groups.append(
            {
                "group_id": _canonical_sha256(
                    {
                        "source_batch": source_batch,
                        "job_search_class": job_class,
                        "evaluation_semantics_sha256": evaluator_hash,
                        "universe_track": track,
                    }
                )[:20],
                "source_batch": source_batch,
                "job_search_class": job_class,
                "evaluation_semantics_sha256": evaluator_hash,
                "universe_track": track,
                "cross_group_or_start_ranking_allowed": False,
                "selection_dates": [item["selection_date"] for item in ordered],
                "start_count": len(ordered),
                "candidate_rows": sum(item["candidate_rows"] for item in ordered),
                "source_reported_replay_eligible_rows": sum(
                    item["source_reported_replay_eligible_rows"] for item in ordered
                ),
                "pareto_candidate_rows": sum(
                    item["pareto_candidate_rows"] for item in ordered
                ),
                "latest_coordinate_summary": {
                    "selection_date": ordered[-1]["selection_date"],
                    "candidate_rows": ordered[-1]["candidate_rows"],
                    "source_reported_replay_eligible_rows": ordered[-1][
                        "source_reported_replay_eligible_rows"
                    ],
                    "pareto_candidate_rows": ordered[-1]["pareto_candidate_rows"],
                    "user_preference_status": ordered[-1][
                        "user_preference_reference"
                    ]["status"],
                },
                "per_start": ordered,
            }
        )
    return {
        "schema_version": 2,
        "manifest_type": "ndx_cardinality_capital_replay_pareto_summary",
        "status": "HISTORICAL_SIX_AXIS_PARETO_COMPLETE",
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "source_v1_bundle": source_descriptor,
        "source_top_manifest": top_evidence["top_manifest"],
        "source_generated_at": top["generated_at"],
        "planned_job_count": int(top["planned_job_count"]),
        "verified_child_job_count": len(starts),
        "evaluator_group_count": len(groups),
        "evaluator_groups": groups,
        "pareto_axes": [
            {
                "metric": metric,
                "direction": "MAXIMUM" if maximize else "MINIMUM",
                "source_field": f"rolling_training_statistics.{metric}",
            }
            for metric, maximize in PARETO_AXES
        ],
        "rolling_return_metric_semantics": (
            "ANNUALIZED_ROLLING_WINDOW_RETURN_AS_FROZEN_BY_SOURCE_EVALUATOR"
        ),
        "continuous_whole_lot_path_return_semantics": "CUMULATIVE_FULL_PATH_RETURN_NET",
        "pareto_membership_scope": (
            "SOURCE_REPORTED_ELIGIBLE_WITHIN_EXACT_SOURCE_EVALUATOR_TRACK_DATE_ONLY"
        ),
        "all_nondominated_candidates_emitted_without_top_n_truncation": True,
        "ties_retained": True,
        "cross_source_ranking_allowed": False,
        "cross_evaluator_ranking_allowed": False,
        "cross_universe_track_ranking_allowed": False,
        "cross_selection_date_ranking_allowed": False,
        "user_preference_reference": {
            "tickers": list(v1.USER_PREFERENCE_TICKERS),
            "weights": {
                ticker: v1.USER_PREFERENCE_WEIGHT
                for ticker in v1.USER_PREFERENCE_TICKERS
            },
            "displayed_when_present_even_if_dominated_or_ineligible": True,
            "fixed_answer": False,
            "admission_authority": False,
        },
        "historical_candidate_rows_revalidated_with_v1_contract": True,
        "source_v1_provenance_limitations": {
            "top_manifest_originally_bound_child_manifest_hashes": source_summary[
                "top_manifest_originally_bound_child_manifest_hashes"
            ],
            "historical_child_manifest_authenticity_reconstructable_from_top": source_summary[
                "historical_child_manifest_authenticity_reconstructable_from_top"
            ],
            "v1_summary_records_current_verified_child_manifest_hashes": source_summary[
                "new_summary_records_child_manifest_hashes"
            ],
            "raw_historical_input_bytes_currently_recoverable": source_summary[
                "raw_historical_input_bytes_currently_recoverable"
            ],
            "historical_input_unrecoverable_count": source_summary[
                "historical_input_unrecoverable_count"
            ],
            "source_input_drift_count": source_summary["source_input_drift_count"],
            "v2_does_not_upgrade_v1_top_origin_authenticity": True,
        },
        "new_backtest_run": False,
        "fresh_oos_consumed": False,
        "optimality_claimed": False,
        "bounded_search_global_optimality_claimed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }


def render_pareto_markdown(summary: Mapping[str, Any]) -> str:
    """Render a compact Chinese review; the JSON remains the complete report."""

    lines = [
        "# NDX 25,000 美元历史资本回放六轴 Pareto 扩展",
        "",
        f"状态：`{summary['status']}`。已重证 {summary['verified_child_job_count']}/"
        f"{summary['planned_job_count']} 个历史作业；没有启动新回测。",
        "",
        "六轴中的收益 P50/P10 是冻结评估器定义的滚动窗口年化收益；连续整股路径"
        "收益是全路径累计净收益，两者不可混称。",
        "",
        "Pareto 只在完全相同的 source / evaluator / universe track / selection date 内"
        "比较，并输出 source-reported eligible 的全部非支配候选，不截取 top-N。",
        "",
    ]
    for group in summary["evaluator_groups"]:
        latest = group["latest_coordinate_summary"]
        lines.extend(
            [
                f"## {group['job_search_class']} / {group['universe_track']}",
                "",
                f"来源 `{group['source_batch']}`；评估器 "
                f"`{group['evaluation_semantics_sha256']}`；共 {group['start_count']} 个起点。",
                "",
                f"最新坐标 `{latest['selection_date']}`：总候选 {latest['candidate_rows']}，"
                f"source-reported eligible {latest['source_reported_replay_eligible_rows']}，"
                f"六轴非支配 {latest['pareto_candidate_rows']}。",
                "",
                "最新坐标 USER_PREFERENCE（AMAT/AVGO/CDNS/GOOG 等权）状态："
                f"`{latest['user_preference_status']}`。它只作参照，即使被支配或不合规也"
                "保留展示，不覆盖 Pareto、准入或持仓答案。",
                "",
            ]
        )
    lines.extend(
        [
            "## 边界",
            "",
            "- 完整逐起点候选组成、权重、六轴指标和连续整股路径指标只在 `summary.json`。",
            "- bounded 搜索仍是 heuristic，不声称全局最优。",
            "- 原始 replay top manifest 没有绑定每个 child manifest；v2 只能依托已发布"
            " v1 anchor 和当前可重证字节计算 Pareto，不能把它升级成可从原始 top 还原的"
            "历史真实性证明。v1 的源文件漂移/精确前缀恢复限制原样保留在 JSON。",
            "- 本报告不是 fresh OOS、策略准入、实盘晋级、今日建议或订单。",
        ]
    )
    return "\n".join(lines) + "\n"


def _manifest_payload(
    summary: Mapping[str, Any], summary_raw: bytes, markdown_raw: bytes
) -> dict[str, Any]:
    payload = {
        "schema_version": 2,
        "manifest_type": "ndx_cardinality_capital_replay_pareto_summary_bundle",
        "status": summary["status"],
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "source_v1_bundle": summary["source_v1_bundle"],
        "verified_child_job_count": summary["verified_child_job_count"],
        "artifacts": {
            "summary_json": {"filename": "summary.json", "sha256": _sha256(summary_raw)},
            "summary_markdown": {"filename": "summary.md", "sha256": _sha256(markdown_raw)},
        },
        "fresh_oos_consumed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    return {**payload, "manifest_sha256": _canonical_sha256(payload)}


def _infer_repository_root(source_path: Path) -> Path:
    parts = SOURCE_V1_RELATIVE.parts
    resolved = source_path.resolve()
    if tuple(resolved.parts[-len(parts):]) != parts:
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "source v1 descriptor is not canonical"
        )
    root = resolved
    for _ in parts:
        root = root.parent
    return root


def verify_pareto_bundle(
    manifest_path: str | Path, *, repository_root: str | Path | None = None
) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    _, manifest = _read_mapping(path, "Pareto bundle manifest")
    payload = dict(manifest)
    claimed = payload.pop("manifest_sha256", None)
    if claimed != _canonical_sha256(payload):
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "Pareto bundle manifest hash changed"
        )
    expected_keys = {
        "schema_version", "manifest_type", "status", "research_track",
        "migration_control_included", "source_v1_bundle", "verified_child_job_count",
        "artifacts", "fresh_oos_consumed", "admission_claimed", "promotion_allowed",
        "live_mutation_allowed", "order_creation_allowed", "manifest_sha256",
    }
    if set(manifest) != expected_keys or (
        manifest.get("schema_version") != 2
        or manifest.get("manifest_type")
        != "ndx_cardinality_capital_replay_pareto_summary_bundle"
        or manifest.get("status") != "HISTORICAL_SIX_AXIS_PARETO_COMPLETE"
        or manifest.get("research_track") != "portfolio_optimization"
        or manifest.get("migration_control_included") is not False
        or any(
            manifest.get(key) is not False
            for key in (
                "fresh_oos_consumed", "admission_claimed", "promotion_allowed",
                "live_mutation_allowed", "order_creation_allowed",
            )
        )
    ):
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "Pareto bundle safety boundary changed"
        )
    source = manifest.get("source_v1_bundle")
    if not isinstance(source, Mapping) or set(source) != {
        "path", "sha256", "summary_path", "summary_sha256"
    }:
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "source v1 bundle descriptor changed"
        )
    source_path = Path(str(source["path"])).resolve()
    root = (
        Path(repository_root).resolve()
        if repository_root is not None
        else _infer_repository_root(source_path)
    )
    if source_path != (root / SOURCE_V1_RELATIVE).resolve():
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "source v1 bundle path is not canonical"
        )
    if _sha256(source_path.read_bytes()) != source["sha256"]:
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "source v1 bundle hash changed"
        )
    summary_source = source_path.parent / "summary.json"
    if (
        Path(str(source["summary_path"])).resolve() != summary_source
        or _sha256(summary_source.read_bytes()) != source["summary_sha256"]
    ):
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "source v1 summary hash changed"
        )
    try:
        v1.verify_summary_bundle(source_path)
    except v1.NdxCardinalityCapitalReplaySummaryError as exc:
        raise NdxCardinalityCapitalReplayParetoSummaryError(str(exc)) from exc
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        "summary_json", "summary_markdown"
    }:
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "Pareto bundle artifact registry changed"
        )
    raw_artifacts = {}
    for name, filename in (
        ("summary_json", "summary.json"), ("summary_markdown", "summary.md")
    ):
        descriptor = artifacts[name]
        if not isinstance(descriptor, Mapping) or set(descriptor) != {"filename", "sha256"}:
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "Pareto artifact descriptor changed"
            )
        artifact = path.parent / filename
        raw = artifact.read_bytes()
        if descriptor.get("filename") != filename or descriptor.get("sha256") != _sha256(raw):
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "Pareto artifact hash changed"
            )
        raw_artifacts[name] = raw
    try:
        summary = json.loads(raw_artifacts["summary_json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "Pareto summary JSON is invalid"
        ) from exc
    if (
        not isinstance(summary, Mapping)
        or summary.get("schema_version") != 2
        or summary.get("manifest_type")
        != "ndx_cardinality_capital_replay_pareto_summary"
        or summary.get("status") != manifest["status"]
        or summary.get("source_v1_bundle") != source
        or summary.get("verified_child_job_count")
        != manifest["verified_child_job_count"]
        or summary.get("all_nondominated_candidates_emitted_without_top_n_truncation")
        is not True
        or summary.get("fresh_oos_consumed") is not False
        or summary.get("admission_claimed") is not False
        or summary.get("promotion_allowed") is not False
        or summary.get("live_mutation_allowed") is not False
        or summary.get("order_creation_allowed") is not False
    ):
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "Pareto summary JSON boundary changed"
        )
    recomputed = build_capital_replay_pareto_summary(
        source_path, repository_root=root
    )
    if summary != recomputed or raw_artifacts["summary_json"] != _json_bytes(recomputed):
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "Pareto summary does not match a fresh rebuild from frozen candidates"
        )
    if raw_artifacts["summary_markdown"] != render_pareto_markdown(recomputed).encode(
        "utf-8"
    ):
        raise NdxCardinalityCapitalReplayParetoSummaryError(
            "Pareto markdown does not match the rebuilt summary"
        )
    return manifest


def write_pareto_bundle(
    summary: Mapping[str, Any], *, output_dir: str | Path
) -> dict[str, Any]:
    """Atomically publish an immutable JSON/Markdown bundle."""

    output = Path(output_dir).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_raw = _json_bytes(summary)
    markdown_raw = render_pareto_markdown(summary).encode("utf-8")
    manifest = _manifest_payload(summary, summary_raw, markdown_raw)
    expected = {
        "summary.json": summary_raw,
        "summary.md": markdown_raw,
        "manifest.json": _json_bytes(manifest),
    }
    if output.exists():
        if not output.is_dir() or set(item.name for item in output.iterdir()) != set(expected):
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "immutable Pareto bundle collision"
            )
        if any((output / name).read_bytes() != raw for name, raw in expected.items()):
            raise NdxCardinalityCapitalReplayParetoSummaryError(
                "immutable Pareto bundle collision"
            )
        verify_pareto_bundle(output / "manifest.json")
        return manifest
    temporary = output.with_name(f"{output.name}.tmp.{uuid.uuid4().hex}")
    try:
        temporary.mkdir()
        for name, raw in expected.items():
            with (temporary / name).open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    verify_pareto_bundle(output / "manifest.json")
    return manifest


__all__ = [
    "NdxCardinalityCapitalReplayParetoSummaryError", "OUTPUT_RELATIVE",
    "SOURCE_V1_RELATIVE", "build_capital_replay_pareto_summary",
    "render_pareto_markdown", "verify_pareto_bundle", "write_pareto_bundle",
]
