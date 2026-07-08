"""Point-in-time quarterly mirror research for a target fund's US holdings.

PowerShell / PyCharm example:
    python scripts/fund_quarterly_mirror_research.py --fund 012922 --monthly 3000
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.fund_mirror import run_fund_quarterly_mirror_research
from core.config import load_config
from core.helpers import setup_logging


def _pct(value, digits=1):
    return "-" if value is None else f"{float(value) * 100:.{digits}f}%"


def _num(value, digits=1):
    return "-" if value is None else f"{float(value):.{digits}f}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="012922季度披露US持仓点时镜像研究（research only，不改今日建议）"
    )
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--fund", default="012922")
    ap.add_argument("--target", default="012922")
    ap.add_argument("--monthly", type=float, default=3000.0)
    ap.add_argument("--total-cap", type=float, default=37000.0)
    ap.add_argument("--min-years", type=float, default=3.0)
    ap.add_argument("--start-year", type=int, default=2021)
    ap.add_argument("--end-year", type=int, default=0)
    ap.add_argument("--top-ns", default="4,6,8")
    ap.add_argument("--weight-modes", default="fund_weight,capped_fund_weight,score_risk")
    ap.add_argument("--safe-weights", default="0.26,0.34,0.40")
    ap.add_argument("--core-ratios", default="0.90,0.95")
    ap.add_argument("--max-weight", type=float, default=0.30)
    ap.add_argument("--min-weight", type=float, default=0.04)
    ap.add_argument("--availability-delay-days", type=int, default=30)
    ap.add_argument("--rebalance-months", type=int, default=3)
    ap.add_argument("--rebalance-same-report", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--trade-cost-bps", type=float, default=10.0)
    ap.add_argument("--step-months", type=int, default=3)
    ap.add_argument("--max-windows", type=int, default=0)
    ap.add_argument("--local-only", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--include-samples", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    setup_logging(logging.ERROR)
    cfg = load_config(args.config)
    res = run_fund_quarterly_mirror_research(
        cfg,
        fund_code=args.fund,
        total_cap=args.total_cap,
        monthly=args.monthly,
        target_benchmark=args.target,
        min_years=args.min_years,
        start_year=args.start_year or None,
        end_year=args.end_year or None,
        top_ns=args.top_ns,
        weight_modes=args.weight_modes,
        safe_weights=args.safe_weights,
        core_ratios=args.core_ratios,
        max_weight=args.max_weight,
        min_weight=args.min_weight,
        availability_delay_days=args.availability_delay_days,
        rebalance_months=args.rebalance_months,
        rebalance_same_report=args.rebalance_same_report,
        trade_cost_bps=args.trade_cost_bps,
        step_months=args.step_months,
        max_windows=args.max_windows,
        local_only=args.local_only,
        include_samples=args.include_samples,
    )
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    s = res["summary"]
    print("\n012922季度披露US持仓点时镜像研究（research only）")
    print(f"基金: {s['fund_code']} {s.get('fund_name') or ''} | 最新报告期: {s.get('latest_report_date') or '-'}")
    print(f"点时规则: report_date + {s['availability_delay_days']}天后可用；每{s['rebalance_months']}个月检查一次；成本 {s['trade_cost_bps']:.1f}bp")
    print(f"US历史ticker: {s['us_ticker_count']} | 可用行情: {s['available_ticker_count']} | 滚动起点: {s['start_count']}")
    print(f"{'组合':<34}{'core':>7}{'W':>6}{'窗':>5}{'胜率':>7}"
          f"{'超额P50':>10}{'DD改善P50':>12}{'策略DD':>10}{'换手x':>8}{'准入':>10}")
    for r in res["rows"][:30]:
        adm = (r.get("admission") or {}).get("label", "-")
        print(f"{r['basket']:<34}{_pct(r.get('core_ratio'), 0):>7}{_pct(r.get('safe_weight'), 0):>6}"
              f"{int(r.get('windows') or 0):>5}{_pct(r.get('win_rate'), 0):>7}"
              f"{_pct(r.get('excess_p50'), 2):>10}{_pct(r.get('dd_relief_p50'), 1):>12}"
              f"{_pct(r.get('maxdd_p50'), 1):>10}{_num(r.get('turnover_x_p50'), 1):>8}{adm:>10}")

    print("\n最近披露覆盖")
    for item in res.get("history_coverage", [])[:6]:
        print(f"  {item['report_date']}: 股票合计 {_pct(item.get('reported_nav_weight'), 2)} | "
              f"US {_pct(item.get('us_nav_weight'), 2)} | US数 {item.get('us_count')} | "
              f"{', '.join(item.get('top_us') or [])}")

    best = (s.get("best") or {}).get("best_balanced") or (res["rows"][0] if res.get("rows") else None)
    print("\n结论")
    if not best:
        print("没有生成有效样本；不改变今日建议。")
    else:
        print(f"当前扫描中相对均衡的候选: {best['basket']} core={_pct(best.get('core_ratio'), 0)} "
              f"W={_pct(best.get('safe_weight'), 0)}，胜率 {_pct(best.get('win_rate'), 0)}，"
              f"超额P50 {_pct(best.get('excess_p50'), 2)}，DD改善P50 {_pct(best.get('dd_relief_p50'), 1)}。")
        print("这是严格点时研究，不接入 config/state，也不会改变今日限价单。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
