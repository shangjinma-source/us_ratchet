"""Active-rebalance research for grouped US-stock preferences.

PowerShell / PyCharm example:
    python scripts/preference_rebalance.py --groups "semis=NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM;platform=MSFT,GOOG,AAPL;eda=SNPS,CDNS" --monthly 3000
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

from backtest.preference_walkforward import run_preference_rebalance_research
from core.config import load_config
from core.helpers import setup_logging


def _pct(value, digits=1):
    return "-" if value is None else f"{float(value) * 100:.{digits}f}%"


def _num(value, digits=1):
    return "-" if value is None else f"{float(value):.{digits}f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="自选美股低频主动重选/调仓成本回放（research only）")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--tickers", default="", help="逗号分隔的候选美股 ticker")
    ap.add_argument("--groups", default="", help="自选分组，如 semis=NVDA,AVGO;platform=MSFT,GOOG,AAPL")
    ap.add_argument("--monthly", type=float, default=3000.0)
    ap.add_argument("--total-cap", type=float, default=37000.0)
    ap.add_argument("--target", default="012922")
    ap.add_argument("--min-years", type=float, default=3.0)
    ap.add_argument("--lookback-years", type=float, default=3.0)
    ap.add_argument("--min-history-years", type=float, default=2.0)
    ap.add_argument("--safe-weights", default="0,0.26")
    ap.add_argument("--modes", default="", help="逗号分隔模式；默认 top4/top6/top8/group-balanced/all score-risk")
    ap.add_argument("--rebalance-months", default="6,12", help="持有期内重选间隔，逗号分隔，如 6,12")
    ap.add_argument("--trade-cost-bps", type=float, default=10.0, help="内部轮换买卖名义额成本，bp")
    ap.add_argument("--step-months", type=int, default=1)
    ap.add_argument("--max-windows", type=int, default=0, help="调试用：只跑前 N 个滚动起点")
    ap.add_argument("--local-only", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--include-samples", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    setup_logging(logging.WARNING)
    cfg = load_config(args.config)
    if args.local_only:
        cfg.data.fallback_chain = ["local_cache"]
    if not args.tickers.strip() and not args.groups.strip():
        raise SystemExit("请提供 --tickers 或 --groups")

    res = run_preference_rebalance_research(
        cfg,
        tickers=args.tickers,
        groups=args.groups,
        total_cap=args.total_cap,
        monthly=args.monthly,
        target_benchmark=args.target,
        min_years=args.min_years,
        lookback_years=args.lookback_years,
        min_history_years=args.min_history_years,
        safe_weights=args.safe_weights,
        modes=(args.modes or None),
        rebalance_months=args.rebalance_months,
        trade_cost_bps=args.trade_cost_bps,
        step_months=args.step_months,
        max_windows=args.max_windows,
        local_only=args.local_only,
        include_samples=args.include_samples or args.json,
    )
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    s = res["summary"]
    print("\n自选美股低频主动重选/调仓成本回放（research only）")
    print(f"目标基准: {s['target_benchmark']} | 起点数 {s['start_count']} | "
          f"重选间隔 {','.join(str(x) for x in s['rebalance_months'])}个月 | 成本 {s['trade_cost_bps']:.1f}bp")
    pref = s.get("holding_preference") or {}
    if pref:
        print(f"持仓偏好: 优先 <= {pref.get('preferred_max_holdings')} 只；测试 topN={pref.get('tested_top_ns')}")
    if res.get("groups"):
        group_txt = " / ".join(f"{g['name']}:{','.join(g['tickers'])}" for g in res["groups"])
        print(f"自选分组: {group_txt}")
    if res.get("dropped"):
        print("跳过标的:", ", ".join(f"{k}({v})" for k, v in res["dropped"].items()))

    print(f"{'模式':<44}{'W':>6}{'窗口':>6}{'跑赢':>8}{'超额P50':>10}"
          f"{'DD改善P50':>12}{'策略DD P50':>12}{'换手P50':>10}{'成本P50':>10}{'准入':>10}")
    for r in res["rows"]:
        adm = (r.get("admission") or {}).get("label", "-")
        print(f"{r['basket']:<44}{_pct(r['safe_weight'], 0):>6}{int(r['windows'] or 0):>6}"
              f"{_pct(r.get('win_rate'), 0):>8}{_pct(r.get('excess_p50'), 2):>10}"
              f"{_pct(r.get('dd_relief_p50'), 1):>12}{_pct(r.get('maxdd_p50'), 1):>12}"
              f"{_num(r.get('rotation_turnover_x_p50'), 2) + 'x':>10}"
              f"{_pct(r.get('rotation_cost_x_p50'), 2):>10}{adm:>10}")

    viable = [r for r in res["rows"] if (r.get("win_rate") or 0) >= 0.5 and (r.get("excess_p50") or 0) > 0]
    compact = ((s.get("best") or {}).get("best_compact") or {})
    print("\n结论")
    if compact:
        print(f"最佳精简候选: {compact['basket']} W={_pct(compact.get('safe_weight'), 0)}，"
              f"N均 {_num(compact.get('n'), 1)}，跑赢率 {_pct(compact.get('win_rate'), 0)}，"
              f"超额P50 {_pct(compact.get('excess_p50'), 2)}，DD改善P50 {_pct(compact.get('dd_relief_p50'), 1)}。")
    if not viable:
        print("低频主动重选后，没有形态通过收益侧初筛；不能接入实盘。")
    else:
        best = viable[0]
        print(f"收益侧最接近: {best['basket']} W={_pct(best['safe_weight'], 0)}，"
              f"跑赢率 {_pct(best.get('win_rate'), 0)}，超额P50 {_pct(best.get('excess_p50'), 2)}。")
        if (best.get("dd_relief_p50") or 0) < 0:
            print(f"但回撤中位仍深于 {s['target_benchmark']}，只能继续研究，不能改变今日建议。")
    print("说明: 主动卖出/重建仅用于研究；不写 config/state，不生成限价单。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
