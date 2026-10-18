"""Analyze completed v8b allocation evidence and generate the v8c cap frontier."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_allocation_analysis import build_allocation_analysis_bundle
from core.config import load_config


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _pct(value: object) -> str:
    return f"{float(value) * 100:+.2f}pct"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按当前8只优先分析v8b，并生成窄范围源权重封顶实验"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--experiment-dir",
        default="data/cache/research/ndx_lab/ndx_incumbent_allocation_search_v8b",
    )
    parser.add_argument(
        "--shortlists",
        default=(
            "data/cache/research/ndx_lab/ndx_incumbent_stock_screen_v8a/"
            "analysis/staged_search/stage1_frozen_shortlists.csv"
        ),
    )
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    config_path = _resolve(args.config)
    experiment_dir = _resolve(args.experiment_dir)
    output_dir = _resolve(args.output_dir) if args.output_dir else None
    payload = build_allocation_analysis_bundle(
        load_config(config_path),
        experiment_dir,
        _resolve(args.shortlists),
        output_dir=output_dir,
        strategy_config_path=config_path,
    )
    result_dir = output_dir or experiment_dir / "analysis" / "incumbent_first"
    best = payload["best_unconstrained"]
    compliant = payload["best_compliant"]
    print("\n纳指100持仓数量与权重分析（研究用途）")
    print(
        f"方案 {payload['candidate_rows']} | 集中度合规 "
        f"{payload['concentration_compliant_rows']} | "
        f"收益战胜当前8只 {payload['incumbent_beating_rows']}"
    )
    print(
        f"收益最接近: {best['profile_id']} | "
        f"P50/P10 {_pct(best['incumbent_xirr_p50_margin'])}/"
        f"{_pct(best['incumbent_xirr_p10_margin'])} | "
        f"Top3 {float(best['top3_p90']) * 100:.2f}%"
    )
    print(
        f"集中度合规最佳: {compliant['profile_id']} | "
        f"P50/P10 {_pct(compliant['incumbent_xirr_p50_margin'])}/"
        f"{_pct(compliant['incumbent_xirr_p10_margin'])}"
    )
    print(f"结论: {payload['decision']}")
    print(f"中文报告: {result_dir / payload['files']['workbook']}")
    print(f"v8c规格: {result_dir / payload['files']['stage3']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
