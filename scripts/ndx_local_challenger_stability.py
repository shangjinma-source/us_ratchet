r"""Aggregate already-consumed local training searches across selection starts."""
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

from backtest.ndx_local_challenger import aggregate_local_challenger_stability
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
    manifests = [_resolve(value) for value in args.manifest]
    frames = {}
    inputs = []
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("manifest_type") != "ndx_local_challenger_training_search":
            raise ValueError(f"unexpected local challenger manifest: {manifest_path}")
        artifact = (manifest.get("artifacts") or {}).get("candidates") or {}
        candidate_path = Path(str(artifact.get("path") or ""))
        if not candidate_path.is_absolute() or file_sha256(candidate_path) != artifact.get("sha256"):
            raise ValueError(f"local challenger artifact mismatch: {manifest_path}")
        frame = pd.read_csv(candidate_path, low_memory=False)
        if len(frame) != int(artifact.get("rows") or -1):
            raise ValueError(f"local challenger row count changed: {manifest_path}")
        selection_date = str(manifest["selection_date"])
        if selection_date in frames:
            raise ValueError(f"duplicate local challenger selection date: {selection_date}")
        frames[selection_date] = frame
        inputs.append({
            "selection_date": selection_date,
            "manifest_path": manifest_path.as_posix(),
            "manifest_sha256": file_sha256(manifest_path),
            "candidates_path": candidate_path.as_posix(),
            "candidates_sha256": file_sha256(candidate_path),
        })
    stability = aggregate_local_challenger_stability(frames)
    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stability_path = output / "cross_start_stability.csv"
    workbook_path = output / "ndx_local_challenger_stability.xlsx"
    _atomic_csv(stability, stability_path)
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            stability.to_excel(writer, sheet_name="cross_start_stability", index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_local_challenger_cross_start_training_stability",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DESCRIPTIVE_REUSED_TRAINING_STABILITY_ONLY",
        "selection_dates": sorted(frames),
        "common_structure_count": len(stability),
        "all_start_four_dimension_pass_count": int(stability["four_dimension_pass_all_starts"].sum()),
        "at_least_two_start_pass_count": int(stability["four_dimension_pass_count"].ge(2).sum()),
        "return_tail_positive_all_starts_count": int(stability["return_tail_positive_all_starts"].sum()),
        "drawdown_nonworse_all_starts_count": int(stability["drawdown_nonworse_all_starts"].sum()),
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "inputs": inputs,
        "artifacts": {
            "stability": {"path": stability_path.as_posix(), "rows": len(stability), "sha256": file_sha256(stability_path)},
            "workbook": {"path": workbook_path.as_posix(), "sha256": file_sha256(workbook_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="局部组合跨训练起点稳定性审计")
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--output-dir", default="data/cache/research/ndx_local_challenger_stability_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"局部 challenger 稳定性审计失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"局部 challenger 稳定性审计完成 | common={payload['common_structure_count']} | "
        f"all_starts_pass={payload['all_start_four_dimension_pass_count']} | "
        f"pass_ge2={payload['at_least_two_start_pass_count']} | promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
