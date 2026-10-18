r"""Compare whole-lot execution-aware frontier roles across training starts."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def run(args: argparse.Namespace) -> dict:
    frames = []
    inputs = []
    for value in args.manifest:
        manifest_path = _resolve(value)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("manifest_type") != "ndx_cardinality_execution_aware_frontiers":
            raise ValueError(f"unexpected execution frontier manifest: {manifest_path}")
        if manifest.get("promotion_allowed") is not False:
            raise ValueError("execution frontier unexpectedly permits promotion")
        artifact = (manifest.get("artifacts") or {}).get("selected") or {}
        path = Path(str(artifact.get("path") or ""))
        if not path.is_absolute() or file_sha256(path) != artifact.get("sha256"):
            raise ValueError(f"execution frontier artifact mismatch: {manifest_path}")
        frame = pd.read_csv(path, low_memory=False)
        if len(frame) != int(artifact.get("rows") or -1):
            raise ValueError(f"execution frontier row count changed: {manifest_path}")
        if not frame["execution_constraints_passed"].astype(bool).all():
            raise ValueError("selected execution frontier is not compliant")
        frames.append(frame)
        inputs.append({"path": manifest_path.as_posix(), "sha256": file_sha256(manifest_path)})
    detail = pd.concat(frames, ignore_index=True)
    if detail["selection_date"].nunique() != len(frames):
        raise ValueError("execution frontier selection dates are not unique")
    roles = sorted(detail["execution_frontier_role"].astype(str).unique())
    start_count = detail["selection_date"].nunique()
    summary_rows = []
    issuer_rows = []
    for role in roles:
        group = detail.loc[detail["execution_frontier_role"].eq(role)].copy()
        if len(group) != start_count:
            raise ValueError(f"execution frontier role coverage incomplete: {role}")
        k_values = group.sort_values("selection_date")["holding_count"].astype(int).tolist()
        ticker_sets = [set(str(value).split(";")) for value in group["tickers"]]
        issuer_sets = [set(str(value).split(";")) for value in group["execution_issuer_ids"]]
        stable_tickers = sorted(set.intersection(*ticker_sets))
        stable_issuers = sorted(set.intersection(*issuer_sets))
        summary_rows.append({
            "frontier_role": role, "selection_start_count": start_count,
            "holding_counts": ";".join(map(str, k_values)),
            "holding_count_min": min(k_values), "holding_count_max": max(k_values),
            "holding_count_stable": len(set(k_values)) == 1,
            "stable_tickers_all_starts": ";".join(stable_tickers),
            "stable_issuer_ids_all_starts": ";".join(stable_issuers),
            "status": "DESCRIPTIVE_REUSED_TRAINING_EXECUTION_STABILITY_ONLY",
        })
        counts = Counter(issuer for values in issuer_sets for issuer in values)
        for issuer, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            issuer_rows.append({
                "frontier_role": role, "issuer_id": issuer,
                "start_inclusion_count": count, "selection_start_count": start_count,
                "inclusion_rate": count / start_count, "included_all_starts": count == start_count,
            })
    summary = pd.DataFrame(summary_rows)
    issuer_frequency = pd.DataFrame(issuer_rows)
    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    detail_path = output / "execution_cross_start_frontiers.csv"
    summary_path = output / "execution_cross_start_stability.csv"
    issuer_path = output / "execution_cross_start_issuer_frequency.csv"
    workbook_path = output / "ndx_cardinality_execution_stability.xlsx"
    _atomic_csv(detail, detail_path)
    _atomic_csv(summary, summary_path)
    _atomic_csv(issuer_frequency, issuer_path)
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summary.to_excel(writer, sheet_name="整股跨起点稳定性", index=False)
            issuer_frequency.to_excel(writer, sheet_name="发行人出现频率", index=False)
            detail.to_excel(writer, sheet_name="逐起点整股前沿", index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_execution_cross_start_stability",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DESCRIPTIVE_REUSED_TRAINING_EXECUTION_STABILITY_ONLY",
        "selection_dates": sorted(detail["selection_date"].astype(str).unique()),
        "holding_count_stable_roles": sorted(summary.loc[summary["holding_count_stable"], "frontier_role"]),
        "strategy_baseline": "ORIGINAL_8_CAP_TOTAL_NORMALIZED",
        "personal_off_strategy_positions_included": False,
        "fresh_oos_consumed": False, "promotion_allowed": False,
        "inputs": inputs,
        "artifacts": {
            "detail": {"path": detail_path.as_posix(), "rows": len(detail), "sha256": file_sha256(detail_path)},
            "summary": {"path": summary_path.as_posix(), "rows": len(summary), "sha256": file_sha256(summary_path)},
            "issuer_frequency": {"path": issuer_path.as_posix(), "rows": len(issuer_frequency), "sha256": file_sha256(issuer_path)},
            "workbook": {"path": workbook_path.as_posix(), "sha256": file_sha256(workbook_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="整股可执行前沿跨起点稳定性")
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--output-dir", default="data/cache/research/ndx_cardinality_execution_stability_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"整股前沿跨起点稳定性失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"整股前沿跨起点稳定性完成 | starts={len(payload['selection_dates'])} | "
        f"stable_k_roles={payload['holding_count_stable_roles']} | promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
