"""Build staged Nasdaq-100 stock-screen and allocation-search evidence."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_experiment_lab import load_experiment_spec
from backtest.ndx_staged_search import (
    build_stock_screen_bundle,
    load_stock_screen_analysis_spec,
)
from core.config import load_config


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def _parse_sizes(value: str) -> tuple[int, ...]:
    sizes = tuple(sorted({
        int(item.strip())
        for item in str(value).replace(";", ",").split(",")
        if item.strip()
    }))
    if not sizes or min(sizes) < 12:
        raise argparse.ArgumentTypeError("shortlist sizes must all be at least 12")
    return sizes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="纳指100个股三阶段白盒搜索工具"
    )
    subparsers = parser.add_subparsers(dest="stage", required=True)
    screen = subparsers.add_parser(
        "screen",
        help="分析已完成的第一阶段并生成中文股票排名与第二阶段规格",
    )
    screen.add_argument(
        "--spec",
        default="config/ndx_experiment_lab_incumbent_v8a.yaml",
    )
    screen.add_argument("--config", default="config/config.yaml")
    screen.add_argument(
        "--analysis-spec",
        default="config/ndx_stock_screen_analysis_v8a2.yaml",
    )
    screen.add_argument("--experiment-dir", default="")
    screen.add_argument("--output-dir", default="")
    screen.add_argument("--shortlist-sizes", type=_parse_sizes, default=(18, 24, 30))
    screen.add_argument("--max-per-sic2", type=int, default=2)
    screen.add_argument("--required-top-n", type=int, default=12)
    args = parser.parse_args()

    if args.stage != "screen":
        parser.error(f"unsupported stage: {args.stage}")
    spec_path = _resolve(args.spec)
    spec = load_experiment_spec(spec_path)
    experiment_dir = (
        _resolve(args.experiment_dir)
        if args.experiment_dir
        else _resolve(spec.get("output_dir") or "data/cache/research/ndx_lab")
        / str(spec["experiment_id"])
    )
    output_dir = _resolve(args.output_dir) if args.output_dir else None
    config_path = _resolve(args.config)
    payload = build_stock_screen_bundle(
        load_config(config_path),
        experiment_dir,
        output_dir=output_dir,
        shortlist_sizes=args.shortlist_sizes,
        max_per_sic2=args.max_per_sic2,
        required_top_n=args.required_top_n,
        strategy_config_path=config_path,
        analysis_spec=load_stock_screen_analysis_spec(
            _resolve(args.analysis_spec)
        ),
    )
    result_dir = output_dir or experiment_dir / "analysis" / "staged_search"
    print("\n纳指100个股第一阶段分析（研究用途）")
    print("主比较基准: 当前8只 | 012922: 第二层参照 | QQQ: 成分代理")
    print(
        f"股票排名: {payload['ranked_stock_count']} | "
        f"冻结池: {len(payload['shortlists'])} | "
        f"第二阶段方案: {payload['stage2_profile_count']}"
    )
    for item in payload["shortlists"]:
        print(
            f"  {item['shortlist_id']}: {item['shortlist_size']}只 | "
            f"SIC二位 {item['sic2_group_count']}组 | "
            f"最弱历史时点仍有 {item['minimum_point_in_time_members']}只可参与"
        )
    print(f"中文报告: {result_dir / payload['files']['workbook']}")
    print(f"第二阶段规格: {result_dir / payload['files']['stage2_spec']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
