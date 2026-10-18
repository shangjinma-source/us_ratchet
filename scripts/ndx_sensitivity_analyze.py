"""Build the final v8g training-evidence report and curve bundle."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_sensitivity_analysis import build_sensitivity_analysis_bundle
from core.config import load_config


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="生成v8g组成敏感性中文报告与前端曲线证据"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--experiment-dir",
        default=(
            "data/cache/research/ndx_lab/"
            "ndx_incumbent_composition_sensitivity_v8g"
        ),
    )
    parser.add_argument(
        "--source-v8f-manifest",
        default=(
            "data/cache/research/ndx_lab/"
            "ndx_incumbent_composition_pairs_v8f/manifest.json"
        ),
    )
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    config_path = _resolve(args.config)
    experiment_dir = _resolve(args.experiment_dir)
    output_dir = _resolve(args.output_dir) if args.output_dir else None
    payload = build_sensitivity_analysis_bundle(
        load_config(config_path),
        experiment_dir,
        _resolve(args.source_v8f_manifest),
        output_dir=output_dir,
        strategy_config_path=config_path,
    )
    result_dir = output_dir or experiment_dir / "analysis" / "sensitivity"
    best = payload["best_absolute"]
    print("\n纳指100组成敏感性最终分析（研究用途）")
    print(
        f"候选 {payload['candidate_rows']} | "
        f"集中度合规 {payload['concentration_compliant_rows']} | "
        f"当前8只收益守门通过 {payload['incumbent_gate_passed_rows']}"
    )
    print(
        f"最接近当前8只: {best['profile_id']} | "
        f"P50/P10 {best['incumbent_xirr_p50_margin']:+.2%}/"
        f"{best['incumbent_xirr_p10_margin']:+.2%}"
    )
    print(f"结论: {payload['decision']}")
    print(f"中文报告: {result_dir / payload['files']['workbook']}")
    print(f"前端曲线: {result_dir / payload['files']['curves']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
