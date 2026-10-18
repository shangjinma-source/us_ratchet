"""Export a daily trace for one pre-registered NDX construction profile."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_competition import run_ndx_profile_trace
from core.config import load_config
from core.helpers import atomic_write_text


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _load_profile(spec_path: Path, profile_id: str, phase_id: str | None) -> tuple[dict, dict]:
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    phases = [
        phase for phase in raw.get("phases") or []
        if phase.get("enabled") is True and (not phase_id or phase.get("phase_id") == phase_id)
    ]
    if len(phases) != 1:
        raise ValueError("trace requires exactly one enabled matching phase")
    phase = phases[0]
    profiles = {
        str(item.get("id") or item.get("profile_id")): item
        for item in phase.get("construction_profiles") or []
    }
    if profile_id not in profiles:
        raise ValueError(f"unknown profile {profile_id!r}; available={sorted(profiles)}")
    return phase, profiles[profile_id]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay one NDX lab profile and export its daily drawdown evidence."
    )
    parser.add_argument(
        "--spec", default="config/ndx_experiment_lab_012922_v4b.yaml"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--phase", default="")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--trade-cost-bps", type=float, default=10.0)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    spec_path = _resolve(args.spec)
    phase, profile = _load_profile(spec_path, args.profile, args.phase or None)
    cfg = load_config(_resolve(args.config))
    cfg.data.start_date = str(phase["start"])
    cfg.data.end_date = str(phase.get("end")) if phase.get("end") else None
    result = run_ndx_profile_trace(
        cfg,
        profile,
        window_start=args.window_start,
        target_benchmark=str(phase.get("target") or "012922"),
        total_cap=float(phase.get("total_cap") or 37000.0),
        monthly=float(phase.get("monthly") or 3000.0),
        lookback_years=float(phase.get("lookback_years") or 1.0),
        min_history_years=float(phase.get("min_history_years") or 0.5),
        trade_cost_bps=float(args.trade_cost_bps),
        safe_annual=float(phase.get("safe_annual") or 0.04),
        local_only=True,
    )

    experiment_id = str((yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}).get("experiment_id"))
    output_dir = (
        _resolve(args.output_dir)
        if args.output_dir
        else ROOT / "data" / "cache" / "research" / "ndx_lab" / experiment_id / "analysis" / "traces"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.profile}__{args.window_start}__cost-{args.trade_cost_bps:g}bp"
    daily_path = output_dir / f"{stem}.csv"
    summary_path = output_dir / f"{stem}.json"
    workbook_path = output_dir / f"{stem}.xlsx"
    result["daily"].to_csv(daily_path, index=False, encoding="utf-8-sig")
    summary = {key: value for key, value in result.items() if key != "daily"}
    atomic_write_text(
        summary_path,
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            default=_json_default,
        ) + "\n",
    )
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    try:
        summary_frame = pd.DataFrame([
            {"field": key, "value": json.dumps(value, ensure_ascii=False, default=_json_default)}
            for key, value in summary.items()
            if key != "risk_stats"
        ])
        selections = pd.DataFrame((summary.get("risk_stats") or {}).get("selections") or [])
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summary_frame.to_excel(writer, sheet_name="summary", index=False)
            result["daily"].to_excel(writer, sheet_name="daily", index=False)
            selections.to_excel(writer, sheet_name="selections", index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()

    print(f"Daily trace: {daily_path}")
    print(f"Summary: {summary_path}")
    print(f"Workbook: {workbook_path}")
    print(json.dumps({
        "strategy_maxdd_event": summary["strategy_maxdd_event"],
        "incumbent_maxdd_event": summary["incumbent_maxdd_event"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
