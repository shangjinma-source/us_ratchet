"""Target-benchmark basket A/B research.

This script is intentionally research-only.  It tests deterministic basket
shapes against a target benchmark such as 012922 with rolling starts, then
prints whether return improvement survives the drawdown tradeoff.

PowerShell / PyCharm example:
    python scripts/target_basket_ab.py --tickers "NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM,MSFT,GOOG,AAPL,SNPS,CDNS" --monthly 3000
    python scripts/target_basket_ab.py --groups "semis=NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM;platform=MSFT,GOOG,AAPL;eda=SNPS,CDNS" --monthly 3000
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.preference import run_preference_portfolio_research
from core.config import load_config
from core.helpers import setup_logging


def _pct(x, d=1):
    return "-" if x is None else f"{float(x) * 100:.{d}f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description="对标 012922 的自选美股池/分组组合滚动 A/B（research only）")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--tickers", default="", help="逗号分隔的候选美股 ticker")
    ap.add_argument("--groups", default="", help="自选分组，如 semis=NVDA,AVGO;platform=MSFT,GOOG,AAPL")
    ap.add_argument("--monthly", type=float, default=3000.0)
    ap.add_argument("--total-cap", type=float, default=37000.0)
    ap.add_argument("--target", default="012922")
    ap.add_argument("--min-years", type=float, default=3.0)
    ap.add_argument("--safe-weights", default="0,0.14,0.26")
    ap.add_argument("--include-voltarget", action="store_true",
                    help="对静态W=0收益最强的几个篮子追加 vol-target 动态防御层滚动验证")
    ap.add_argument("--voltarget-top-k", type=int, default=4)
    ap.add_argument("--local-only", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args()

    setup_logging(logging.WARNING)
    cfg = load_config(args.config)
    if args.local_only:
        cfg.data.fallback_chain = ["local_cache"]

    if not args.tickers.strip() and not args.groups.strip():
        raise SystemExit("请提供 --tickers 或 --groups")

    res = run_preference_portfolio_research(
        cfg,
        tickers=args.tickers,
        groups=args.groups,
        total_cap=args.total_cap,
        monthly=args.monthly,
        target_benchmark=args.target,
        min_years=args.min_years,
        safe_weights=args.safe_weights,
        include_voltarget=args.include_voltarget,
        voltarget_top_k=args.voltarget_top_k,
        local_only=args.local_only,
    )
    s = res["summary"]
    rows = res["rows"]
    target = s["target_benchmark"]
    safe_weights = s["safe_weights"]

    print(f"\n对标 {target} 候选篮子 A/B（research only）")
    print(f"候选 {s['ticker_count']} 只；分组 {s['group_count']} 个；篮子形态 {s['basket_count']} 组；防御腿 {', '.join(_pct(w, 0) for w in safe_weights)}")
    if res.get("groups"):
        group_txt = " / ".join(f"{g['name']}:{','.join(g['tickers'])}" for g in res["groups"])
        print(f"自选分组: {group_txt}")
    pref = s.get("holding_preference") or {}
    if pref:
        print(f"持仓偏好: 优先 <= {pref.get('preferred_max_holdings')} 只；测试 topN={pref.get('tested_top_ns')}")
    print(f"{'篮子':<28}{'W':>6}{'N':>4}{'窗口':>6}{'跑赢':>8}{'超额P50':>10}{'DD改善P50':>12}{'策略XIRR P50':>14}{'策略DD P50':>12}{'准入':>10}")
    for r in rows:
        adm = (r.get("admission") or {}).get("label", "-")
        name = r["basket"] + ("[VT]" if r.get("defense_mode") == "voltarget" else "")
        w_label = "VT" if r.get("defense_mode") == "voltarget" else _pct(r["safe_weight"], 0)
        print(f"{name:<28}{w_label:>6}{r['n']:>4}{int(r['windows'] or 0):>6}"
              f"{_pct(r['win_rate'], 0):>8}{_pct(r['excess_p50'], 2):>10}"
              f"{_pct(r['dd_relief_p50'], 1):>12}{_pct(r['xirr_p50'], 2):>14}"
              f"{_pct(r['maxdd_p50'], 1):>12}{adm:>10}")

    viable = [r for r in rows if (r["win_rate"] or 0) >= 0.5 and (r["excess_p50"] or 0) > 0]
    compact = ((s.get("best") or {}).get("best_compact") or {})
    print("\n结论")
    if compact:
        print(f"最佳精简候选: {compact['basket']} W={_pct(compact.get('safe_weight'), 0)}，"
              f"N={compact.get('n')}，跑赢率 {_pct(compact.get('win_rate'), 0)}，"
              f"超额P50 {_pct(compact.get('excess_p50'), 2)}，DD改善P50 {_pct(compact.get('dd_relief_p50'), 1)}。")
    if not viable:
        print("没有篮子同时满足滚动胜率>=50%且超额XIRR中位为正。")
    else:
        best = viable[0]
        dd = best["dd_relief_p50"]
        best_w = "VT" if best.get("defense_mode") == "voltarget" else _pct(best["safe_weight"], 0)
        print(f"收益侧最接近目标: {best['basket']} W={best_w}，"
              f"跑赢率 {_pct(best['win_rate'], 0)}，超额XIRR中位 {_pct(best['excess_p50'], 2)}。")
        if dd is not None and dd < 0:
            print(f"但回撤中位比 {target} 深 {_pct(abs(dd), 1)}，只能作为候选研究，不能直接接入今日建议。")
    print("说明: 该脚本只验证自选池/分组下的组合形态，不写 config/state；通过后仍需样本外、动态权重和实盘准入验证。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
