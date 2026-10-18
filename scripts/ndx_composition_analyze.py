"""Analyze v8e single ablations and generate the v8f pair search."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_composition_analysis import build_composition_analysis_bundle
from core.config import load_config


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="分析v8e逐股剔除并生成v8f有限二元组成搜索"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--experiment-dir",
        default=(
            "data/cache/research/ndx_lab/"
            "ndx_incumbent_composition_ablation_v8e"
        ),
    )
    parser.add_argument(
        "--source-v8d-manifest",
        default=(
            "data/cache/research/ndx_lab/"
            "ndx_incumbent_envelope_projection_v8d/manifest.json"
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
    payload = build_composition_analysis_bundle(
        load_config(config_path),
        experiment_dir,
        _resolve(args.source_v8d_manifest),
        _resolve(args.shortlists),
        output_dir=output_dir,
        strategy_config_path=config_path,
    )
    result_dir = output_dir or experiment_dir / "analysis" / "composition"
    best = payload["best_single_ablation"]
    print("\n纳指100单股组成敏感度分析（研究用途）")
    print(
        f"候选 {payload['candidate_rows']} | "
        f"集中度合规 {payload['concentration_compliant_rows']} | "
        f"二元搜索种子 {payload['pair_search_seed_count']}"
    )
    print(
        f"当前8只口径最佳单股剔除: {best['omitted_ticker']} | "
        f"P50/P10改善 {best['candidate_p50_return_delta_median']:+.2%}/"
        f"{best['candidate_p10_return_delta_median']:+.2%} | "
        f"逐窗口收益改善率 {best['window_return_improvement_rate']:.1%}"
    )
    print("二元种子: " + ", ".join(payload["pair_search_seed_tickers"]))
    print(f"结论: {payload['decision']}")
    print(f"中文报告: {result_dir / payload['files']['workbook']}")
    print(f"v8f规格: {result_dir / payload['files']['stage6']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
