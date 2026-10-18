"""Analyze completed v8c evidence and generate the v8d envelope experiment."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cap_frontier_analysis import build_cap_frontier_analysis_bundle
from core.config import load_config


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _pct(value: object) -> str:
    return f"{float(value) * 100:+.2f}pct"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按当前8只优先分析v8c单股上限前沿并生成v8d精确风险边界实验"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--experiment-dir",
        default=(
            "data/cache/research/ndx_lab/"
            "ndx_incumbent_source_cap_frontier_v8c"
        ),
    )
    parser.add_argument(
        "--source-v8b-manifest",
        default=(
            "data/cache/research/ndx_lab/"
            "ndx_incumbent_allocation_search_v8b/manifest.json"
        ),
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
    payload = build_cap_frontier_analysis_bundle(
        load_config(config_path),
        experiment_dir,
        _resolve(args.source_v8b_manifest),
        _resolve(args.shortlists),
        output_dir=output_dir,
        strategy_config_path=config_path,
    )
    result_dir = output_dir or experiment_dir / "analysis" / "cap_frontier"
    adjacent = payload["adjacent_cap_evidence"]
    best = payload["best_unconstrained"]
    compliant = payload["best_compliant"]
    print("\n纳指100单股上限前沿分析（研究用途）")
    print(
        f"候选 {payload['candidate_rows']} | "
        f"集中度合规 {payload['concentration_compliant_rows']} | "
        f"当前8只收益守门通过 {payload['incumbent_gate_passed_rows']}"
    )
    print(
        f"相邻上限 {adjacent['adjacent_comparisons']} 对 | "
        f"P50/P10收益改善 {adjacent['return_p50_improved']}/"
        f"{adjacent['return_p10_improved']} | "
        f"回撤压力恶化 {adjacent['drawdown_p90_worsened']}"
    )
    print(
        f"收益最接近: {best['profile_id']} | "
        f"P50/P10 {_pct(best['incumbent_xirr_p50_margin'])}/"
        f"{_pct(best['incumbent_xirr_p10_margin'])}"
    )
    print(
        f"集中度合规最佳: {compliant['profile_id']} | "
        f"P50/P10 {_pct(compliant['incumbent_xirr_p50_margin'])}/"
        f"{_pct(compliant['incumbent_xirr_p10_margin'])}"
    )
    print(f"结论: {payload['decision']}")
    print(f"中文报告: {result_dir / payload['files']['workbook']}")
    print(f"v8d规格: {result_dir / payload['files']['stage4']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
