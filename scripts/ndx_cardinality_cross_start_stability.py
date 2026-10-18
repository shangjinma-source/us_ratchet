r"""Compare cross-cardinality frontier roles across consumed training starts."""
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
    inputs = []
    rows = []
    all4_by_start = []
    track = None
    for value in args.manifest:
        manifest_path = _resolve(value)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("manifest_type") != "ndx_cross_cardinality_real_training_frontiers":
            raise ValueError(f"unexpected cross-cardinality manifest: {manifest_path}")
        identity = manifest["comparison_identity"]
        if track is None:
            track = identity["universe_track"]
        elif identity["universe_track"] != track:
            raise ValueError("cross-start frontier tracks differ")
        artifact = (manifest.get("artifacts") or {}).get("cross_cardinality_frontiers") or {}
        path = Path(str(artifact.get("path") or ""))
        if not path.is_absolute() or file_sha256(path) != artifact.get("sha256"):
            raise ValueError(f"cross-cardinality frontier artifact mismatch: {manifest_path}")
        frame = pd.read_csv(path, low_memory=False)
        if len(frame) != int(artifact.get("rows") or -1):
            raise ValueError(f"cross-cardinality frontier row count changed: {manifest_path}")
        selection_date = str(identity["selection_date"])
        if "selection_date" in frame.columns:
            if not frame["selection_date"].astype(str).eq(selection_date).all():
                raise ValueError(f"frontier selection date mismatch: {manifest_path}")
        else:
            frame.insert(0, "selection_date", selection_date)
        rows.append(frame)
        all4_by_start.append({
            "selection_date": selection_date,
            "four_dimension_incumbent_dominance_rows": int(
                manifest["four_dimension_incumbent_dominance_rows"]
            ),
        })
        inputs.append({
            "selection_date": selection_date,
            "manifest_path": manifest_path.as_posix(), "manifest_sha256": file_sha256(manifest_path),
            "frontier_path": path.as_posix(), "frontier_sha256": file_sha256(path),
        })
    detail = pd.concat(rows, ignore_index=True, sort=False).sort_values(
        ["cross_cardinality_frontier_role", "selection_date"], kind="stable"
    )
    expected_roles = {"RETURN", "BAD_TAIL", "DRAWDOWN", "012922_DISTANCE"}
    if set(detail["cross_cardinality_frontier_role"].astype(str)) != expected_roles:
        raise ValueError("cross-start frontier roles changed")
    start_count = detail["selection_date"].nunique()
    if detail.groupby("cross_cardinality_frontier_role").size().ne(start_count).any():
        raise ValueError("each frontier role must have exactly one row per start")
    summary_rows = []
    ticker_rows = []
    for role, group in detail.groupby("cross_cardinality_frontier_role", sort=True):
        counts = Counter()
        for value in group["tickers"].astype(str):
            counts.update(value.split(";"))
        k_values = group["holding_count"].astype(int).tolist()
        stable_tickers = sorted(ticker for ticker, count in counts.items() if count == start_count)
        summary_rows.append({
            "frontier_role": role,
            "selection_start_count": start_count,
            "holding_counts": ";".join(map(str, k_values)),
            "holding_count_min": min(k_values), "holding_count_max": max(k_values),
            "holding_count_stable": len(set(k_values)) == 1,
            "stable_holding_count": k_values[0] if len(set(k_values)) == 1 else None,
            "stable_tickers_all_starts": ";".join(stable_tickers),
            "stable_ticker_count": len(stable_tickers),
            "status": "DESCRIPTIVE_REUSED_TRAINING_STABILITY_ONLY",
        })
        for ticker, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            ticker_rows.append({
                "frontier_role": role, "ticker": ticker,
                "start_inclusion_count": count, "selection_start_count": start_count,
                "inclusion_rate": count / start_count,
                "included_all_starts": count == start_count,
            })
    summaries = pd.DataFrame(summary_rows)
    ticker_frequency = pd.DataFrame(ticker_rows)
    all4 = pd.DataFrame(all4_by_start).sort_values("selection_date", kind="stable")
    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "detail": output / "cross_start_frontiers.csv",
        "summary": output / "cross_start_role_stability.csv",
        "ticker_frequency": output / "cross_start_ticker_frequency.csv",
        "all4": output / "cross_start_incumbent_dominance.csv",
        "workbook": output / "ndx_cardinality_cross_start_stability.xlsx",
    }
    _atomic_csv(detail, paths["detail"])
    _atomic_csv(summaries, paths["summary"])
    _atomic_csv(ticker_frequency, paths["ticker_frequency"])
    _atomic_csv(all4, paths["all4"])
    temporary = paths["workbook"].with_name(paths["workbook"].stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summaries.to_excel(writer, sheet_name="持仓数稳定性", index=False)
            ticker_frequency.to_excel(writer, sheet_name="成分出现频率", index=False)
            detail.to_excel(writer, sheet_name="逐起点四类前沿", index=False)
            all4.to_excel(writer, sheet_name="四维支配计数", index=False)
        os.replace(temporary, paths["workbook"])
    finally:
        if temporary.exists():
            temporary.unlink()
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_cross_start_training_stability",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DESCRIPTIVE_REUSED_TRAINING_STABILITY_ONLY",
        "universe_track": track,
        "selection_dates": sorted(detail["selection_date"].unique()),
        "frontier_roles": sorted(expected_roles),
        "stable_holding_count_roles": sorted(
            summaries.loc[summaries["holding_count_stable"].astype(bool), "frontier_role"].astype(str)
        ),
        "all_start_stable_tickers": {
            row["frontier_role"]: str(row["stable_tickers_all_starts"])
            for _, row in summaries.iterrows()
        },
        "starts_with_four_dimension_incumbent_dominance": int(
            all4["four_dimension_incumbent_dominance_rows"].gt(0).sum()
        ),
        "fresh_oos_consumed": False, "promotion_allowed": False,
        "inputs": inputs,
        "artifacts": {
            name: {"path": path.as_posix(), "sha256": file_sha256(path), **(
                {"rows": len({"detail": detail, "summary": summaries,
                              "ticker_frequency": ticker_frequency, "all4": all4}[name])}
                if name != "workbook" else {}
            )}
            for name, path in paths.items()
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="跨选择日起点持仓数与成分稳定性")
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--output-dir", default="data/cache/research/ndx_cardinality_cross_start_stability_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"跨起点持仓数稳定性失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"跨起点持仓数稳定性完成 | starts={len(payload['selection_dates'])} | "
        f"stable_k_roles={payload['stable_holding_count_roles']} | promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
