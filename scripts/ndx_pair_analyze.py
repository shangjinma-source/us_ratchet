"""Analyze v8f pairs and generate v8g sensitivity."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_pair_analysis import build_pair_analysis_bundle
from core.config import load_config


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="分析v8f二元组成并生成v8g回看期与成本敏感性"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--experiment-dir",
        default="data/cache/research/ndx_lab/ndx_incumbent_composition_pairs_v8f",
    )
    parser.add_argument(
        "--source-v8e-manifest",
        default=(
            "data/cache/research/ndx_lab/"
            "ndx_incumbent_composition_ablation_v8e/manifest.json"
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
    payload = build_pair_analysis_bundle(
        load_config(config_path),
        experiment_dir,
        _resolve(args.source_v8e_manifest),
        _resolve(args.shortlists),
        output_dir=output_dir,
        strategy_config_path=config_path,
    )
    result_dir = output_dir or experiment_dir / "analysis" / "pairs"
    print("\n纳指100二元组成分析（研究用途）")
    print(
        f"候选 {payload['candidate_rows']} | "
        f"集中度合规 {payload['concentration_compliant_rows']}"
    )
    for row in payload["finalists"]:
        print(
            f"{row['analysis_role_cn']}: {row['omitted_tickers']} | "
            f"P50/P10 {row['candidate_p50_return_delta_median']:+.2%}/"
            f"{row['candidate_p10_return_delta_median']:+.2%}"
        )
    print(f"结论: {payload['decision']}")
    print(f"中文报告: {result_dir / payload['files']['workbook']}")
    print(f"v8g规格: {result_dir / payload['files']['stage7']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
