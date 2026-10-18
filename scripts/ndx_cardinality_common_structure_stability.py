r"""Evaluate identical equal-weight issuer structures across completed training starts."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import atomic_write_text
from data.versioning import file_sha256
from scripts.ndx_cardinality_runner_analyze import (
    completed_manifests,
    merge_completed_manifest_groups,
)


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


CONSERVATIVE_OPTIONAL_METRICS = {
    "return_p50_vs_012922": ("return_p50_vs_012922_conservative", "min"),
    "return_p10_vs_012922": ("return_p10_vs_012922_conservative", "min"),
    "max_drawdown_p50_vs_012922": ("max_drawdown_p50_vs_012922_conservative", "max"),
    "max_drawdown_p90_vs_012922": ("max_drawdown_p90_vs_012922_conservative", "max"),
    "risk_chain_top1_p90": ("risk_chain_top1_p90_conservative", "max"),
    "weight_top1_p90": ("weight_top1_p90_conservative", "max"),
    "weight_top3_p90": ("weight_top3_p90_conservative", "max"),
    "effective_n_min": ("effective_n_min_conservative", "min"),
    "turnover_p90": ("turnover_p90_conservative", "max"),
    "turnover_max": ("turnover_max_conservative", "max"),
    "initial_transaction_cost": ("initial_transaction_cost_conservative", "max"),
    "transaction_cost": ("transaction_cost_conservative", "max"),
    "portfolio_min_median_dollar_volume_usd": ("portfolio_min_median_dollar_volume_usd_conservative", "min"),
    "whole_lot_residual_cash_p50": ("whole_lot_residual_cash_p50_conservative", "max"),
    "whole_lot_total_transaction_cost_usd": ("whole_lot_total_transaction_cost_usd_conservative", "max"),
    "whole_lot_min_cash_usd": ("whole_lot_min_cash_usd_conservative", "min"),
}


def _conservative_numeric(series: pd.Series, reducer: str) -> float:
    values = pd.to_numeric(series, errors="coerce")
    return float(values.min() if reducer == "min" else values.max())


def aggregate_common_structures(
    detail: pd.DataFrame,
    *,
    expected_dates: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    observed_dates = sorted(detail["selection_date"].astype(str).unique())
    dates = sorted(str(value) for value in (expected_dates or observed_dates))
    missing_dates = sorted(set(dates) - set(observed_dates))
    if missing_dates:
        raise ValueError(f"entire selection start has no compliant candidate rows: {missing_dates}")
    date_count = len(dates)
    per_date_rows = []
    group_columns = ["holding_count", "issuer_structure", "selection_date"]
    for keys, group in detail.groupby(group_columns, sort=True):
        k, structure, date = keys
        per_date_row = {
            "holding_count": int(k), "issuer_structure": structure, "selection_date": date,
            "security_variants": " || ".join(sorted(group["tickers"].astype(str).unique())),
            "canonical_tickers": sorted(group["tickers"].astype(str).unique())[0],
            "security_variant_count": group["tickers"].nunique(),
            "return_p50_conservative": group["return_p50"].min(),
            "return_p10_conservative": group["return_p10"].min(),
            "max_drawdown_p50_conservative": group["max_drawdown_p50"].max(),
            "max_drawdown_p90_conservative": group["max_drawdown_p90"].max(),
            "paired_return_p50_vs_incumbent_conservative": group["paired_return_p50_vs_incumbent"].min(),
            "paired_return_p10_vs_incumbent_conservative": group["paired_return_p10_vs_incumbent"].min(),
            "paired_drawdown_cost_p50_vs_incumbent_conservative": group["paired_drawdown_cost_p50_vs_incumbent"].max(),
            "paired_drawdown_cost_p90_vs_incumbent_conservative": group["paired_drawdown_cost_p90_vs_incumbent"].max(),
            "target_012922_distance_conservative": group["target_012922_distance"].max(),
        }
        for source, (target, reducer) in CONSERVATIVE_OPTIONAL_METRICS.items():
            if source in group.columns:
                per_date_row[target] = _conservative_numeric(group[source], reducer)
        per_date_rows.append(per_date_row)
    per_date = pd.DataFrame(per_date_rows)
    common_keys = per_date.groupby(["holding_count", "issuer_structure"])["selection_date"].nunique()
    common_keys = common_keys.loc[common_keys.eq(date_count)].index
    common = per_date.set_index(["holding_count", "issuer_structure"]).loc[common_keys].reset_index()
    rows = []
    for (k, structure), group in common.groupby(["holding_count", "issuer_structure"], sort=True):
        structure_row = {
            "holding_count": int(k), "issuer_structure": structure,
            "selection_start_count": date_count,
            "security_variants_by_start": " | ".join(
                f"{row.selection_date}:{row.security_variants}" for row in group.sort_values("selection_date").itertuples()
            ),
            "latest_selection_date": group["selection_date"].astype(str).max(),
            "canonical_tickers": group.sort_values(
                ["selection_date", "canonical_tickers"], ascending=[False, True], kind="stable",
            ).iloc[0]["canonical_tickers"],
            "worst_return_p50": group["return_p50_conservative"].min(),
            "worst_return_p10": group["return_p10_conservative"].min(),
            "worst_max_drawdown_p50": group["max_drawdown_p50_conservative"].max(),
            "worst_max_drawdown_p90": group["max_drawdown_p90_conservative"].max(),
            "worst_paired_return_p50_vs_incumbent": group["paired_return_p50_vs_incumbent_conservative"].min(),
            "worst_paired_return_p10_vs_incumbent": group["paired_return_p10_vs_incumbent_conservative"].min(),
            "worst_paired_drawdown_cost_p50_vs_incumbent": group["paired_drawdown_cost_p50_vs_incumbent_conservative"].max(),
            "worst_paired_drawdown_cost_p90_vs_incumbent": group["paired_drawdown_cost_p90_vs_incumbent_conservative"].max(),
            "worst_target_012922_distance": group["target_012922_distance_conservative"].max(),
        }
        for _, (source, reducer) in CONSERVATIVE_OPTIONAL_METRICS.items():
            if source in group.columns:
                label = source.removesuffix("_conservative")
                structure_row[f"worst_{label}"] = _conservative_numeric(group[source], reducer)
        rows.append(structure_row)
    structures = pd.DataFrame(rows)
    if structures.empty:
        return per_date, structures
    structures["all_start_four_dimension_incumbent_dominance"] = (
        structures["worst_paired_return_p50_vs_incumbent"].gt(0)
        & structures["worst_paired_return_p10_vs_incumbent"].gt(0)
        & structures["worst_paired_drawdown_cost_p50_vs_incumbent"].le(0)
        & structures["worst_paired_drawdown_cost_p90_vs_incumbent"].le(0)
    )
    return per_date, structures


def run(args: argparse.Namespace) -> dict:
    values = args.runner_manifest if isinstance(args.runner_manifest, list) else [args.runner_manifest]
    runner_manifest_paths = [_resolve(value) for value in values]
    runners = [json.loads(path.read_text(encoding="utf-8")) for path in runner_manifest_paths]
    grouped_all = merge_completed_manifest_groups([
        completed_manifests(path) for path in runner_manifest_paths
    ])
    selected_track = str(args.track)
    grouped = {
        key: manifests for key, manifests in grouped_all.items() if key[0] == selected_track
    }
    if not grouped:
        raise ValueError(f"common structure analysis track is absent: {selected_track}")
    runner = runners[0]
    discovery_path = Path(str(((runner.get("inputs") or {}).get("discovery_manifest") or {}).get("path") or ""))
    if not discovery_path.is_absolute() or file_sha256(discovery_path) != runner["inputs"]["discovery_manifest"]["sha256"]:
        raise ValueError("runner discovery manifest mismatch")
    for item in runners[1:]:
        if ((item.get("inputs") or {}).get("discovery_manifest") or {}).get("sha256") != file_sha256(discovery_path):
            raise ValueError("runner discovery manifests differ")
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    members_artifact = (discovery.get("artifacts") or {}).get("eligible_securities") or {}
    members_path = Path(str(members_artifact.get("path") or ""))
    if not members_path.is_absolute() or file_sha256(members_path) != members_artifact.get("sha256"):
        raise ValueError("point-in-time members artifact mismatch")
    members = pd.read_csv(members_path, low_memory=False)

    detail_frames = []
    inputs = []
    for (track, selection_date), manifests in sorted(grouped.items()):
        metadata = members.loc[
            members["universe_track"].eq(track)
            & members["selection_date"].eq(selection_date)
        ][["ticker", "issuer_id"]].drop_duplicates("ticker").set_index("ticker")
        for manifest_path in manifests:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifact = (manifest.get("artifacts") or {}).get("candidates") or {}
            path = Path(str(artifact.get("path") or ""))
            if not path.is_absolute() or file_sha256(path) != artifact.get("sha256"):
                raise ValueError(f"candidate artifact mismatch: {manifest_path}")
            frame = pd.read_csv(path, low_memory=False)
            if len(frame) != int(artifact.get("rows") or -1):
                raise ValueError(f"candidate rows changed: {manifest_path}")
            frame = frame.loc[
                frame["weight_spec"].eq("equal_weight")
                & frame["declared_constraints_passed"].astype(bool)
                & frame["whole_lot_executable_all_windows"].astype(bool)
            ].copy()
            def issuer_structure(tickers: str) -> str:
                values = str(tickers).split(";")
                if any(ticker not in metadata.index for ticker in values):
                    raise ValueError(f"issuer metadata missing for structure: {tickers}")
                issuers = sorted(str(metadata.loc[ticker, "issuer_id"]) for ticker in values)
                if len(set(issuers)) != len(issuers):
                    raise ValueError(f"issuer duplicate survived candidate search: {tickers}")
                return ";".join(issuers)
            frame["issuer_structure"] = frame["tickers"].map(issuer_structure)
            detail_frames.append(frame)
            inputs.append({"path": manifest_path.as_posix(), "sha256": file_sha256(manifest_path)})
    detail = pd.concat(detail_frames, ignore_index=True)
    expected_dates = sorted({selection_date for _, selection_date in grouped})
    per_date, structures = aggregate_common_structures(detail, expected_dates=expected_dates)
    if structures.empty:
        raise ValueError("no equal-weight issuer structure is common across all starts")
    selectors = {
        "RETURN": ("worst_paired_return_p50_vs_incumbent", False),
        "BAD_TAIL": ("worst_paired_return_p10_vs_incumbent", False),
        "DRAWDOWN": ("worst_paired_drawdown_cost_p90_vs_incumbent", True),
        "012922_DISTANCE": ("worst_target_012922_distance", True),
    }
    frontier_rows = []
    for role, (column, ascending) in selectors.items():
        row = structures.sort_values(
            [column, "holding_count", "issuer_structure"],
            ascending=[ascending, True, True], kind="stable",
        ).iloc[0].copy()
        row["common_structure_frontier_role"] = role
        frontier_rows.append(row)
    frontiers = pd.DataFrame(frontier_rows)

    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    per_date_path = output / "common_structure_per_start.csv"
    structures_path = output / "common_structures.csv"
    frontiers_path = output / "common_structure_frontiers.csv"
    workbook_path = output / "ndx_cardinality_common_structure_stability.xlsx"
    _atomic_csv(per_date, per_date_path)
    _atomic_csv(structures, structures_path)
    _atomic_csv(frontiers, frontiers_path)
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            frontiers.to_excel(writer, sheet_name="共同结构前沿", index=False)
            structures.to_excel(writer, sheet_name="全部共同结构", index=False)
            per_date.to_excel(writer, sheet_name="逐起点保守聚合", index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_common_structure_stability",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "REUSED_TRAINING_COMMON_STRUCTURE_ONLY_NOT_ADMISSION",
        "selection_dates": sorted(detail["selection_date"].astype(str).unique()),
        "holding_counts": sorted(structures["holding_count"].astype(int).unique().tolist()),
        "common_structure_count": len(structures),
        "all_start_four_dimension_dominance_count": int(structures["all_start_four_dimension_incumbent_dominance"].sum()),
        "weight_spec": "equal_weight_only_no_weight_parameter_selection",
        "same_day_share_class_aggregation": "CONSERVATIVE_BY_ISSUER_STRUCTURE",
        "portfolio_scope": "HSBC_US_EQUITY_SLEEVE_ONLY",
        "safe_leg_included": False,
        "external_index_included": False,
        "strategy_baseline": "ORIGINAL_8_CAP_TOTAL_NORMALIZED",
        "personal_off_strategy_positions_included": False,
        "fresh_oos_consumed": False, "promotion_allowed": False,
        "inputs": {
            "runner_manifests": [
                {"path": path.as_posix(), "sha256": file_sha256(path)}
                for path in runner_manifest_paths
            ],
            "members": {"path": members_path.as_posix(), "sha256": file_sha256(members_path)},
            "jobs": inputs,
        },
        "artifacts": {
            "per_date": {"path": per_date_path.as_posix(), "rows": len(per_date), "sha256": file_sha256(per_date_path)},
            "structures": {"path": structures_path.as_posix(), "rows": len(structures), "sha256": file_sha256(structures_path)},
            "frontiers": {"path": frontiers_path.as_posix(), "rows": len(frontiers), "sha256": file_sha256(frontiers_path)},
            "workbook": {"path": workbook_path.as_posix(), "sha256": file_sha256(workbook_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="跨起点同一发行人结构稳定性")
    parser.add_argument("--runner-manifest", action="append", required=True)
    parser.add_argument(
        "--track", required=True,
        choices=["strict_technology", "technology_plus_adjacent"],
    )
    parser.add_argument("--output-dir", default="data/cache/research/ndx_cardinality_common_structure_stability_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"共同结构稳定性失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"共同结构稳定性完成 | structures={payload['common_structure_count']} | "
        f"all4={payload['all_start_four_dimension_dominance_count']} | promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
