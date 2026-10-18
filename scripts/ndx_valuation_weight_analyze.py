"""Analyze the completed v9 FCF Yield weight experiment."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_valuation_weight_analysis import (
    build_valuation_weight_analysis_bundle,
)


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description="生成v9估值权重中文配对分析报告")
    parser.add_argument(
        "--experiment-dir",
        default=(
            "data/cache/research/ndx_lab/"
            "ndx_incumbent_fcf_value_sensitivity_v9"
        ),
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    experiment_dir = _resolve(args.experiment_dir)
    output_dir = _resolve(args.output_dir) if args.output_dir else None
    payload = build_valuation_weight_analysis_bundle(
        experiment_dir,
        output_dir=output_dir,
        strategy_config_path=_resolve(args.config),
    )
    result_dir = output_dir or experiment_dir / "analysis" / "valuation_weight"
    weights = ", ".join(f"{weight:.0%}" for weight in payload["shortlisted_weights"])
    print("\n纳指100 FCF Yield权重配对分析（研究用途）")
    print(
        f"候选配对: {payload['candidate_pairs']} | "
        f"逐窗口配对: {payload['window_pairs']}"
    )
    print(f"组件训练候选权重: {weights or '无'}")
    print(f"结论: {payload['decision']}")
    print(f"中文报告: {result_dir / 'v9_fcf_valuation_weight_analysis.xlsx'}")
    print("组件通过不等于组合准入；不会自动修改实盘配置。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
