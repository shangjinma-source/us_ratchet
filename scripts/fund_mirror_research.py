"""Mirror a target fund's latest disclosed US holdings into us_ratchet research.

PowerShell / PyCharm example:
    python scripts/fund_mirror_research.py --fund 012922 --monthly 3000
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

from backtest.fund_mirror import run_fund_mirror_research
from core.config import load_config
from core.helpers import setup_logging


def _pct(value, digits=1):
    return "-" if value is None else f"{float(value) * 100:.{digits}f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description="镜像目标基金最新披露 US 持仓做棘轮研究（research only）")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--fund", default="012922")
    ap.add_argument("--report-date", default="", help="可选报告期 YYYY-MM-DD；默认取最新披露")
    ap.add_argument("--monthly", type=float, default=3000.0)
    ap.add_argument("--total-cap", type=float, default=37000.0)
    ap.add_argument("--target", default="012922")
    ap.add_argument("--min-years", type=float, default=3.0)
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--safe-weights", default="0,0.14,0.26,0.40")
    ap.add_argument("--core-ratios", default="0.90,0.95")
    ap.add_argument("--include-equal", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--local-only", action=argparse.BooleanOptionalAction, default=False,
                    help="只用本地缓存；默认允许联网抓基金持仓和缺失美股行情")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    setup_logging(logging.WARNING)
    cfg = load_config(args.config)
    res = run_fund_mirror_research(
        cfg,
        fund_code=args.fund,
        report_date=(args.report_date or None),
        total_cap=args.total_cap,
        monthly=args.monthly,
        target_benchmark=args.target,
        min_years=args.min_years,
        top_n=args.top_n,
        safe_weights=args.safe_weights,
        core_ratios=args.core_ratios,
        include_equal=args.include_equal,
        local_only=args.local_only,
    )
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    s = res["summary"]
    cov = s["coverage"]
    print("\n目标基金最新披露 US 持仓镜像研究（research only）")
    print(f"基金: {s['fund_code']} {s.get('fund_name') or ''} | 报告期: {s.get('report_date') or '-'}")
    print(f"披露股票合计占净值: {_pct(cov.get('reported_nav_weight'), 2)} | "
          f"US子集占净值: {_pct(cov.get('us_nav_weight'), 2)} | "
          f"US/披露股票: {_pct(cov.get('us_share_of_reported'), 1)}")
    by_cls = cov.get("by_asset_class") or {}
    if by_cls:
        print("资产分类覆盖: " + " / ".join(f"{k}:{_pct(v, 1)}" for k, v in sorted(by_cls.items())))

    us_holdings = [h for h in res["holdings"] if h.get("asset_class") == "US"]
    if us_holdings:
        desc = ", ".join(f"{h['ticker']}({_pct(h.get('nav_weight'), 2)})" for h in us_holdings[:args.top_n])
        print(f"用于美股镜像的 US ticker: {desc}")

    print(f"{'组合':<28}{'core':>7}{'W':>6}{'窗口':>6}{'跑赢':>8}"
          f"{'超额P50':>10}{'DD改善P50':>12}{'策略DD P50':>12}{'准入':>10}")
    for r in res["rows"]:
        adm = (r.get("admission") or {}).get("label", "-")
        print(f"{r['basket']:<28}{_pct(r.get('core_ratio'), 0):>7}{_pct(r.get('safe_weight'), 0):>6}"
              f"{int(r.get('windows') or 0):>6}{_pct(r.get('win_rate'), 0):>8}"
              f"{_pct(r.get('excess_p50'), 2):>10}{_pct(r.get('dd_relief_p50'), 1):>12}"
              f"{_pct(r.get('maxdd_p50'), 1):>12}{adm:>10}")

    viable = [r for r in res["rows"] if (r.get("win_rate") or 0) >= 0.5 and (r.get("excess_p50") or 0) > 0]
    print("\n结论")
    if not viable:
        print("镜像 012922 最新披露 US 子集后，暂无组合通过收益侧初筛；不能接入实盘。")
    else:
        best = viable[0]
        print(f"收益侧最接近: {best['basket']} core={_pct(best.get('core_ratio'), 0)} "
              f"W={_pct(best.get('safe_weight'), 0)}，跑赢率 {_pct(best.get('win_rate'), 0)}，"
              f"超额P50 {_pct(best.get('excess_p50'), 2)}。")
        if (best.get("dd_relief_p50") or 0) < 0:
            print(f"但回撤中位仍深于 {s['target_benchmark']}，只能继续研究，不改变今日建议。")
    print("说明: 这是最新披露持仓的 US 子集镜像，不是 012922 完整历史持仓复刻。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
