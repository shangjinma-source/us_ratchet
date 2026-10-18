"""Generate the fixed 012922 style attribution report.

PowerShell / PyCharm examples:
    python scripts\fund_style_report.py --fund 012922
    python scripts\fund_style_report.py --fund 012922 --refresh
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.fund_style import run_fund_style_attribution
from core.config import load_config


def _pct(value, digits=1) -> str:
    return "-" if value is None else f"{float(value) * 100:.{digits}f}%"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="012922 fixed style attribution report (research only)"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--fund", default="012922")
    parser.add_argument("--benchmarks", default="QQQ,SMH,SPY")
    parser.add_argument("--start-year", type=int, default=2022)
    parser.add_argument("--end-year", type=int, default=0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    benchmarks = tuple(
        value.strip().upper() for value in args.benchmarks.split(",") if value.strip()
    )
    report = run_fund_style_attribution(
        cfg,
        fund_code=args.fund,
        benchmark_tickers=benchmarks,
        start_year=args.start_year,
        end_year=args.end_year or None,
        local_only=not args.refresh,
        refresh=args.refresh,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0

    summary = report["summary"]
    performance = report["performance"]
    print("\n012922 固定风格归因（research only）")
    print(
        f"报告: {summary['report_id']} | 区间: {summary['common_range'][0]} ~ "
        f"{summary['common_range'][1]}"
    )
    print("收益口径: 基金为人民币累计净值；ETF 为当前标准化价格收益代理，未额外计入分红。")
    print(f"{'标的':<10}{'累计收益':>12}{'年化':>10}{'年化波动':>12}{'最大回撤':>12}")
    for name, metrics in performance["metrics"].items():
        print(
            f"{name:<10}{_pct(metrics['total_return'], 1):>12}{_pct(metrics['cagr'], 1):>10}"
            f"{_pct(metrics['annual_volatility'], 1):>12}{_pct(metrics['max_drawdown'], 1):>12}"
        )

    latest_asset = report["asset_allocation"]["latest"]
    latest_industry = report["industry"]["latest"]
    latest_region = report["region"]["latest_expanded"]
    latest_concentration = report["concentration"]["latest"]
    latest_turnover = report["turnover"]["latest"]
    print("\n暴露与节奏")
    print(
        f"权益 {_pct(latest_asset['equity_weight'])} | 现金 {_pct(latest_asset['cash_weight'])} | "
        f"信息技术 {_pct(report['industry']['technology_weight']['latest'])}"
    )
    if latest_region:
        region_text = " / ".join(
            f"{item['label']} {_pct(item['nav_weight'])}"
            for item in latest_region["regions"] if item["nav_weight"] > 0
        )
        print(
            f"最近完整区域披露 {latest_region['report_date']}（覆盖 "
            f"{_pct(latest_region['disclosure_coverage'])}）: {region_text}"
        )
    print(
        f"最新前十集中度 {_pct(latest_concentration['top10_nav_weight'])} | "
        f"最新源端换手率 {_pct(latest_turnover['stock_turnover'])}"
    )
    print("最新行业: " + " / ".join(
        f"{item['sector']} {_pct(item['nav_weight'])}"
        for item in latest_industry["top_sectors"][:5]
    ))

    print("\n要学习什么")
    for item in report["interpretation"]["learn"]:
        print(f"- {item['title']}: {item['evidence']} {item['application']}")
    print("\n不能复制什么")
    for item in report["interpretation"]["cannot_copy"]:
        print(f"- {item['title']}: {item['reason']}")

    print("\n数据版本")
    for name, version in summary["data_versions"].items():
        print(f"- {name}: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
