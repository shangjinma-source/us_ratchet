"""Explain completed NDX quality/SIC experiments without retuning or promotion."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_quality_attribution import (
    analyze_quality_attribution,
    write_quality_attribution_bundle,
)
from core.config import load_config


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "归因已完成的纳指100质量/SIC实验：比较替换、质量袖套、行业暴露"
            "与同窗口结果；不调参、不解锁验证期、不改实盘。"
        )
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--experiment-dir",
        default="data/cache/research/ndx_lab/ndx_012922_quality_sic_v5",
    )
    parser.add_argument("--canonical-cost-bps", type=float, default=10.0)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    experiment_dir = _resolve(args.experiment_dir)
    output_dir = (
        _resolve(args.output_dir)
        if args.output_dir
        else experiment_dir / "analysis" / "quality_attribution"
    )
    config_path = _resolve(args.config)
    cfg = load_config(config_path)
    frames, summary = analyze_quality_attribution(
        experiment_dir,
        cfg,
        canonical_cost_bps=args.canonical_cost_bps,
        strategy_config_path=config_path,
    )
    payload = write_quality_attribution_bundle(frames, summary, output_dir)

    print("\n纳指100质量/SIC归因（diagnostic only）")
    print(
        f"基线: {payload['baseline_profile_id']} | "
        f"配对窗口: {payload['paired_window_rows']} | "
        f"匹配重选: {payload['matched_replacement_event_rows']} | "
        f"调仓日不一致: {payload['schedule_mismatch_rows']}"
    )
    for row in payload["profile_summary"]:
        print(
            f"{row['alternative_profile_id']}: "
            f"窗口 {row['paired_windows']} | "
            f"超额ΔP50 {row['target_excess_xirr_delta_p50'] * 100:+.2f}pct | "
            f"回撤改善率 {row['target_dd_relief_delta_improvement_rate']:.1%}"
        )
    print("结论: DIAGNOSTIC_ONLY_NO_PROMOTION；重叠窗口关联不得作因果推断。")
    print(f"证据目录: {output_dir}")
    print(json.dumps(payload["next_action"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
