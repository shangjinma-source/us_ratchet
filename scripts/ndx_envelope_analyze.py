"""Analyze completed v8d evidence and generate v8e composition ablations."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_envelope_analysis import build_envelope_analysis_bundle
from core.config import load_config


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _pct(value: object) -> str:
    return f"{float(value) * 100:+.2f}pct"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="分析v8d精确风险边界并生成v8e逐股组成敏感度实验"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--experiment-dir",
        default=(
            "data/cache/research/ndx_lab/"
            "ndx_incumbent_envelope_projection_v8d"
        ),
    )
    parser.add_argument(
        "--source-v8c-manifest",
        default=(
            "data/cache/research/ndx_lab/"
            "ndx_incumbent_source_cap_frontier_v8c/manifest.json"
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
    payload = build_envelope_analysis_bundle(
        load_config(config_path),
        experiment_dir,
        _resolve(args.source_v8c_manifest),
        _resolve(args.shortlists),
        output_dir=output_dir,
        strategy_config_path=config_path,
    )
    result_dir = output_dir or experiment_dir / "analysis" / "envelope"
    conservative = payload["pair_summaries"][0]
    print("\n纳指100精确风险边界分析（研究用途）")
    print(
        f"候选 {payload['candidate_rows']} | "
        f"集中度合规 {payload['concentration_compliant_rows']} | "
        f"当前8只收益守门通过 {payload['incumbent_gate_passed_rows']}"
    )
    print(
        "精确Top3 对 13.63%统一上限: "
        f"P50/P10中位改善 {_pct(conservative['candidate_p50_return_delta_median'])}/"
        f"{_pct(conservative['candidate_p10_return_delta_median'])} | "
        f"逐窗口收益改善率 {conservative['window_return_improvement_rate']:.1%}"
    )
    print(
        "回撤代价: "
        f"P50/P90 {_pct(conservative['candidate_dd_p50_delta_median'])}/"
        f"{_pct(conservative['candidate_dd_p90_delta_median'])}"
    )
    print(f"结论: {payload['decision']}")
    print(f"中文报告: {result_dir / payload['files']['workbook']}")
    print(f"v8e规格: {result_dir / payload['files']['stage5']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
