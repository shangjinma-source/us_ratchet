r"""Aggregate comparable real-training frontiers across holding counts."""
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

from backtest.ndx_cardinality_discovery import pareto_mask
from core.helpers import atomic_write_text
from data.versioning import file_sha256


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


def _winner(frame: pd.DataFrame, column: str, ascending: bool) -> pd.Series:
    return frame.sort_values(
        [column, "tickers", "weight_spec"], ascending=[ascending, True, True], kind="stable"
    ).iloc[0]


def run(args: argparse.Namespace) -> dict:
    inputs = []
    all_frames = []
    summary_rows = []
    frontier_rows = []
    identity = None
    selectors = {
        "RETURN": ("return_p50", False),
        "BAD_TAIL": ("return_p10", False),
        "DRAWDOWN": ("max_drawdown_p90", True),
        "012922_DISTANCE": ("target_012922_distance", True),
    }
    for value in args.manifest:
        manifest_path = _resolve(value)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("manifest_type") != "ndx_cardinality_real_training_smoke":
            raise ValueError(f"unexpected cardinality manifest: {manifest_path}")
        current_identity = (
            manifest.get("universe_track"), manifest.get("selection_date"),
            manifest.get("universe_mode"), manifest.get("incumbent_weights_source"),
        )
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise ValueError("cardinality manifests do not share a comparison identity")
        artifact = (manifest.get("artifacts") or {}).get("candidates") or {}
        candidate_path = Path(str(artifact.get("path") or ""))
        if not candidate_path.is_absolute() or file_sha256(candidate_path) != artifact.get("sha256"):
            raise ValueError(f"cardinality candidate artifact mismatch: {manifest_path}")
        frame = pd.read_csv(candidate_path, low_memory=False)
        if len(frame) != int(artifact.get("rows") or -1):
            raise ValueError(f"cardinality candidate row count changed: {manifest_path}")
        k = int(manifest["holding_count"])
        if not frame["holding_count"].eq(k).all():
            raise ValueError(f"candidate holding count mismatch: {manifest_path}")
        frame = frame.copy()
        frame["source_manifest"] = manifest_path.as_posix()
        all_frames.append(frame)
        compliant = frame.loc[frame["declared_constraints_passed"].astype(bool)].copy()
        audit = manifest["search_audit"]
        all4 = compliant.loc[
            compliant["paired_return_p50_vs_incumbent"].gt(0)
            & compliant["paired_return_p10_vs_incumbent"].gt(0)
            & compliant["paired_drawdown_cost_p50_vs_incumbent"].le(0)
            & compliant["paired_drawdown_cost_p90_vs_incumbent"].le(0)
        ] if not compliant.empty else compliant
        failure_reasons = sorted({
            reason
            for value in frame.loc[~frame["declared_constraints_passed"].astype(bool), "constraint_failure_reasons"].fillna("")
            for reason in str(value).split(";") if reason
        })
        summary_rows.append({
            "holding_count": k,
            "candidate_rows": len(frame),
            "compliant_rows": len(compliant),
            "compliant_status": "READY" if not compliant.empty else "NO_COMPLIANT_CANDIDATE",
            "constraint_failure_reasons": ";".join(failure_reasons),
            "evaluated_security_sets": int(audit["first_stage_security_sets"]),
            "theoretical_feasible_security_sets": int(audit["theoretical_feasible_portfolios"]),
            "equal_weight_security_set_coverage": (
                int(audit["first_stage_security_sets"]) / int(audit["theoretical_feasible_portfolios"])
            ),
            "second_stage_security_sets": int(audit["second_stage_security_sets"]),
            "second_stage_security_set_coverage": (
                int(audit["second_stage_security_sets"]) / int(audit["first_stage_security_sets"])
            ),
            "second_stage_failed_evaluations": int(audit["second_stage_failed_evaluations"]),
            "four_dimension_incumbent_dominance_rows": len(all4),
            "search_exhaustive": bool(audit["search_exhaustive"]),
            "optimality_claim_allowed": bool(audit["optimality_claim_allowed"]),
        })
        if not compliant.empty:
            for role, (column, ascending) in selectors.items():
                row = _winner(compliant, column, ascending).copy()
                row["cardinality_frontier_role"] = role
                frontier_rows.append(row)
        inputs.append({
            "holding_count": k,
            "manifest_path": manifest_path.as_posix(),
            "manifest_sha256": file_sha256(manifest_path),
            "candidates_path": candidate_path.as_posix(),
            "candidates_sha256": file_sha256(candidate_path),
        })
    combined = pd.concat(all_frames, ignore_index=True, sort=False)
    counts = sorted(int(value) for value in combined["holding_count"].astype(int).unique())
    if len(inputs) != len(counts):
        raise ValueError("duplicate holding-count manifests are not allowed")
    if counts != list(range(min(counts), max(counts) + 1)):
        raise ValueError("cardinality manifest range is not contiguous")
    compliant_all = combined.loc[combined["declared_constraints_passed"].astype(bool)].copy()
    if compliant_all.empty:
        raise ValueError("no compliant candidates across any holding count")
    cross_pareto = compliant_all.loc[pareto_mask(compliant_all)].copy().sort_values(
        ["holding_count", "target_012922_distance", "return_p10"], ascending=[True, True, False]
    )
    frontiers = pd.DataFrame(frontier_rows).sort_values(
        ["holding_count", "cardinality_frontier_role"], kind="stable"
    )
    summaries = pd.DataFrame(summary_rows).sort_values("holding_count", kind="stable")
    global_rows = []
    for role, (column, ascending) in selectors.items():
        row = _winner(compliant_all, column, ascending).copy()
        row["cross_cardinality_frontier_role"] = role
        global_rows.append(row)
    global_frontiers = pd.DataFrame(global_rows)

    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output / "cardinality_summary.csv",
        "frontiers": output / "cardinality_frontiers.csv",
        "cross_cardinality_frontiers": output / "cross_cardinality_frontiers.csv",
        "cross_cardinality_pareto": output / "cross_cardinality_pareto.csv",
        "workbook": output / "ndx_cardinality_frontiers.xlsx",
    }
    _atomic_csv(summaries, paths["summary"])
    _atomic_csv(frontiers, paths["frontiers"])
    _atomic_csv(global_frontiers, paths["cross_cardinality_frontiers"])
    _atomic_csv(cross_pareto, paths["cross_cardinality_pareto"])
    temporary = paths["workbook"].with_name(paths["workbook"].stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summaries.to_excel(writer, sheet_name="持仓数覆盖", index=False)
            global_frontiers.to_excel(writer, sheet_name="跨持仓数前沿", index=False)
            frontiers.to_excel(writer, sheet_name="逐持仓数前沿", index=False)
            cross_pareto.to_excel(writer, sheet_name="跨持仓数Pareto", index=False)
        os.replace(temporary, paths["workbook"])
    finally:
        if temporary.exists():
            temporary.unlink()
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cross_cardinality_real_training_frontiers",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "CURRENT_SEARCHED_TRAINING_FRONTIERS_ONLY",
        "holding_count_range": [min(counts), max(counts)],
        "holding_counts": counts,
        "comparison_identity": {
            "universe_track": identity[0], "selection_date": identity[1],
            "universe_mode": identity[2], "incumbent_weights_source": identity[3],
        },
        "all_cardinalities_equal_weight_security_sets_exhaustive": bool(
            summaries["equal_weight_security_set_coverage"].eq(1.0).all()
        ),
        "all_cardinalities_weight_space_exhaustive": False,
        "optimality_claim_allowed": False,
        "four_dimension_incumbent_dominance_rows": int(
            summaries["four_dimension_incumbent_dominance_rows"].sum()
        ),
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "inputs": inputs,
        "artifacts": {
            name: {"path": path.as_posix(), "sha256": file_sha256(path), **(
                {"rows": len({"summary": summaries, "frontiers": frontiers,
                              "cross_cardinality_frontiers": global_frontiers,
                              "cross_cardinality_pareto": cross_pareto}[name])}
                if name != "workbook" else {}
            )}
            for name, path in paths.items()
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="跨持仓数真实训练前沿聚合")
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--output-dir", default="data/cache/research/ndx_cross_cardinality_frontiers_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"跨持仓数前沿聚合失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"跨持仓数前沿完成 | k={payload['holding_count_range'][0]}..{payload['holding_count_range'][1]} | "
        f"all4={payload['four_dimension_incumbent_dominance_rows']} | promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
