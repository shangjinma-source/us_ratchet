"""Create a compact, reproducible decision report from a completed NDX lab."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_experiment_analysis import (
    analyze_ndx_experiment,
    write_ndx_analysis_bundle,
)
from core.config import load_config


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def _pct(value: object) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:+.2f}pct"


def _rate(value: object) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def _shape_label(shape: dict) -> str:
    profile = str(shape.get("profile_id") or "").strip()
    prefix = f"{profile} | " if profile else ""
    return (
        f"{prefix}LB={float(shape['lookback_years']):g} "
        f"top{int(shape['top_n'])} {shape['weight_mode']} "
        f"{int(shape['rebalance_months'])}m"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="分析已完成的纳指100个股白盒实验，不运行回测、不晋级实盘。"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--experiment-dir",
        default="data/cache/research/ndx_lab/ndx_012922_price_robustness_v3",
    )
    parser.add_argument("--canonical-cost-bps", type=float, default=10.0)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    experiment_dir = _resolve(args.experiment_dir)
    output_dir = (
        _resolve(args.output_dir)
        if args.output_dir
        else experiment_dir / "analysis"
    )
    config_path = _resolve(args.config)
    cfg = load_config(config_path)
    frames, summary = analyze_ndx_experiment(
        experiment_dir,
        cfg,
        canonical_cost_bps=args.canonical_cost_bps,
        strategy_config_path=config_path,
    )
    payload = write_ndx_analysis_bundle(frames, summary, output_dir)

    best = payload["best_training_shape"]
    compliant = payload.get("best_concentration_compliant_shape") or {}
    print("\n纳指100个股实验分析（research only）")
    print(
        f"候选 {payload['candidate_rows']} | 训练 {payload['training_candidate_rows']} | "
        f"锁定验证 {payload['locked_validation_candidate_rows']}"
    )
    print(
        f"训练主目标门 {payload['training_target_gate_passed_rows']} | "
        f"训练准入 {payload['training_admission_passed_rows']} | "
        f"{payload['canonical_cost_bps']:g}bp 集中度守门 "
        f"{payload['concentration_guard_passed_rows']} | 完整训练候选 "
        f"{payload['training_qualified_rows']}"
    )
    print(
        f"最接近主目标 {payload['primary_target']}: "
        f"{_shape_label(best)} "
        f"P50={_pct(best['target_excess_p50'])} "
        f"P10={_pct(best['target_excess_p10'])}"
    )
    if compliant:
        print(
            "集中度合规最佳: "
            f"{_shape_label(compliant)} "
            f"P50={_pct(compliant['target_excess_p50'])}"
        )
    if payload["locked_validation_executed"]:
        print(
            f"锁定验证: {payload['locked_validation_status']} | "
            f"通过 {payload['locked_validation_passed_rows']} | "
            f"失败 {payload['locked_validation_failed_rows']} | 验证期已消耗"
        )
        for result in payload["locked_validation_results"]:
            print(
                f"  {result['profile_id']} | {float(result['trade_cost_bps']):g}bp | "
                f"{int(result['windows'])} 窗口 | 起点 "
                f"{result['first_window_start']}~{result['last_window_start']} | "
                f"数据截至 {result['evaluation_end']}"
            )
            print(
                f"  vs {payload['primary_target']}: 胜率 {_rate(result['target_win_rate'])} | "
                f"XIRR差 P50/P10 {_pct(result['target_excess_p50'])}/"
                f"{_pct(result['target_excess_p10'])} | DD改善 P50/P10 "
                f"{_pct(result['target_dd_relief_p50'])}/"
                f"{_pct(result['target_dd_relief_p10'])}"
            )
            print(
                "  vs 当前组合: XIRR差 P50/P10 "
                f"{_pct(result['incumbent_xirr_p50_margin'])}/"
                f"{_pct(result['incumbent_xirr_p10_margin'])} | DD改善 P50/坏尾部 "
                f"{_pct(result['incumbent_dd_relief_p50'])}/"
                f"{_pct(result['incumbent_dd_relief_p90'])}"
            )
            print(
                f"  集中度: effective-N P10={float(result['effective_n_p10']):.2f} | "
                f"Top1/Top3 P90={_pct(result['top1_p90'])}/"
                f"{_pct(result['top3_p90'])} | "
                f"守门={'通过' if result['concentration_guard_passed'] else '失败'}"
            )
            print(f"  失败项: {result['failed_checks'] or '无'}")
    else:
        print("锁定验证: 未执行；验证期保持关闭。")
    print(f"结论: {payload['decision']}")
    print(f"分析结果: {output_dir}")
    print(json.dumps(payload["next_research"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
