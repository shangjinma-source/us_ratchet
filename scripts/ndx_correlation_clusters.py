"""Create point-in-time correlation-cluster diagnostics from a completed NDX lab."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_correlation_clusters import (
    parse_positive_ints,
    parse_thresholds,
    plan_ndx_correlation_diagnostics,
    run_ndx_correlation_diagnostics,
    write_ndx_correlation_bundle,
)
from core.config import load_config


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="纳指100个股点时相关性簇诊断；research only，不运行收益回测。"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--experiment-dir",
        default="data/cache/research/ndx_lab/ndx_012922_price_robustness_v3",
    )
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--canonical-cost-bps", type=float, default=10.0)
    parser.add_argument("--lookback-days", default="126,252,504")
    parser.add_argument("--thresholds", default="0.65,0.75,0.85")
    parser.add_argument("--min-observations", type=int, default=60)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--no-xlsx", action="store_true")
    args = parser.parse_args()

    config_path = _resolve(args.config)
    experiment_dir = _resolve(args.experiment_dir)
    output_dir = (
        _resolve(args.output_dir)
        if args.output_dir
        else experiment_dir / "analysis" / "correlation_clusters"
    )
    lookbacks = parse_positive_ints(args.lookback_days)
    thresholds = parse_thresholds(args.thresholds)
    plan = plan_ndx_correlation_diagnostics(
        experiment_dir,
        strategy_config_path=config_path,
        canonical_cost_bps=args.canonical_cost_bps,
        lookback_days=lookbacks,
        thresholds=thresholds,
    )
    print("\n纳指100个股点时相关性簇计划")
    print(
        f"唯一日期/持仓集合 {plan['unique_date_ticker_universes']} | "
        f"唯一权重方案 {plan['unique_weight_scenarios']} | "
        f"预计相关矩阵 {plan['expected_correlation_matrices']}"
    )
    print(
        f"lookback={plan['lookback_days']} | threshold={plan['thresholds']} | "
        f"成本选择一致={plan['cost_invariance_passed']}"
    )
    if args.plan_only:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    cfg = load_config(config_path)
    frames, summary = run_ndx_correlation_diagnostics(
        experiment_dir,
        cfg,
        strategy_config_path=config_path,
        canonical_cost_bps=args.canonical_cost_bps,
        lookback_days=lookbacks,
        thresholds=thresholds,
        min_observations=args.min_observations,
    )
    payload = write_ndx_correlation_bundle(
        frames,
        summary,
        output_dir,
        write_xlsx=not args.no_xlsx,
    )
    print("\n点时相关性簇证据包")
    print(
        f"矩阵 {payload['correlation_matrices']} | "
        f"权重诊断 {payload['weighted_scenario_rows']} | "
        f"形态汇总 {payload['shape_summary_rows']} | "
        f"跳过 {payload['skipped_matrix_rows']}"
    )
    print(f"严格点时检查: {payload['strict_asof_passed']}")
    print(f"输出: {output_dir}")
    print("结论仅用于研究排序；不会晋级持仓或解锁验证期。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
