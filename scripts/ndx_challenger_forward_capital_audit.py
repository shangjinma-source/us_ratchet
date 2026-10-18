"""Audit a prospective full-sleeve cash contract without reading returns."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_challenger_forward_capital import audit_observation_capital  # noqa: E402
from core.helpers import atomic_write_text  # noqa: E402
from data.versioning import file_sha256  # noqa: E402


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
    roots = [_resolve(value) for value in args.observation_dir]
    inputs = []
    audits = []
    for root in roots:
        path = root / "cohort_positions.csv"
        frame = pd.read_csv(path, low_memory=False, keep_default_na=False)
        audits.append(audit_observation_capital(
            frame, args.cash, minimum_cash_buffer=float(args.minimum_cash_buffer),
        ))
        inputs.append({"path": path.resolve().as_posix(), "sha256": file_sha256(path), "rows": len(frame)})
    audit = pd.concat(audits, ignore_index=True)
    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    audit_path = output / "capital_feasibility.csv"
    _atomic_csv(audit, audit_path)
    by_cash = []
    for cash, group in audit.groupby("cash_usd", sort=True):
        by_cash.append({
            "cash_usd": float(cash), "tracks_tested": len(group),
            "compliant_tracks": int(group["constraints_passed"].astype(bool).sum()),
            "all_tracks_compliant": bool(group["constraints_passed"].astype(bool).all()),
        })
    maximum_threshold = float(pd.to_numeric(audit["one_share_weight_threshold_usd"], errors="raise").max())
    rounded_contract_cash = float(math.ceil(maximum_threshold / 5000.0) * 5000.0)
    rounded_rows = audit.loc[audit["cash_usd"].eq(rounded_contract_cash)]
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_challenger_forward_execution_capital_feasibility",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "method": "observation_close_only_no_return_or_post_observation_price_read",
        "capital_role": "full_sleeve_comparison_capital_not_incremental_funding",
        "maximum_one_share_weight_threshold_usd": maximum_threshold,
        "mechanical_rounded_contract_cash_usd": rounded_contract_cash,
        "mechanical_rounded_contract_cash_audited": not rounded_rows.empty,
        "mechanical_rounded_contract_all_tracks_compliant": (
            bool(rounded_rows["constraints_passed"].astype(bool).all()) if not rounded_rows.empty else None
        ),
        "minimum_cash_buffer_usd": float(args.minimum_cash_buffer),
        "cash_level_summary": by_cash,
        "return_data_read": False,
        "promotion_allowed": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "inputs": inputs,
        "artifact": {"path": audit_path.resolve().as_posix(), "rows": len(audit), "sha256": file_sha256(audit_path)},
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="冻结 challenger 全仓整股比较资本可行性审计")
    parser.add_argument("--observation-dir", action="append", required=True)
    parser.add_argument("--cash", action="append", type=float, required=True)
    parser.add_argument("--minimum-cash-buffer", type=float, default=100.0)
    parser.add_argument("--output-dir", default="data/cache/research/ndx_challenger_forward_capital_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"challenger 执行资本审计失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload["cash_level_summary"], ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
