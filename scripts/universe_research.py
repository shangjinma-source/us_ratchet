"""候选美股池诊断与动态篮子建议。

PowerShell / PyCharm 终端示例:
    python scripts/universe_research.py --tickers "NVDA,AVGO,AMD,AMAT,KLAC,LRCX,ASML,TSM,MSFT,GOOG,AAPL,SNPS,CDNS" --monthly 3000
    python scripts/universe_research.py --from-cache --top-n 8 --local-only
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import load_config
from core.helpers import setup_logging
from backtest.universe import cached_universe, run_universe_research


def _pct(x, d=1):
    return "-" if x is None else f"{float(x) * 100:.{d}f}%"


def _num(x, d=2):
    return "-" if x is None else f"{float(x):.{d}f}"


def _fmt_rolling(label: str, item: dict) -> str:
    ex = (item or {}).get("excess_xirr") or {}
    dd = (item or {}).get("dd_relief") or {}
    rng = (item or {}).get("range") or ["-", "-"]
    return (
        f"{label}: 窗口 {int((item or {}).get('windows') or 0)} "
        f"({rng[0]}~{rng[1]}) | 跑赢率 {_pct((item or {}).get('win_rate'), 0)} "
        f"| 超额XIRR中位 {_pct(ex.get('p50'), 2)} "
        f"| DD改善中位 {_pct(dd.get('p50'), 1)}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="us_ratchet 候选美股池诊断/篮子建议")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--tickers", default="", help="逗号分隔 ticker；为空时配合 --from-cache 使用本地缓存候选")
    ap.add_argument("--from-cache", action="store_true", help="使用 data/cache 中已有标的，自动排除 QQQ/SPY/SGOV/SMH/XSD")
    ap.add_argument("--total-cap", type=float, default=37000.0, help="推荐篮子的风险腿总 cap_total")
    ap.add_argument("--monthly", type=float, default=3000.0, help="回测月度注资")
    ap.add_argument("--top-n", type=int, default=8, help="推荐标的数量")
    ap.add_argument("--max-weight", type=float, default=0.22, help="单名最大权重")
    ap.add_argument("--min-weight", type=float, default=0.04, help="入选后最小权重")
    ap.add_argument("--max-pair-corr", type=float, default=0.92, help="候选之间高于该相关系数时只保留分数更高者")
    ap.add_argument("--min-years", type=float, default=2.0, help="最低历史年限")
    ap.add_argument("--drawdown-budget", type=float, default=0.35, help="目标最大回撤预算，用于估算安全腿权重")
    ap.add_argument("--local-only", action=argparse.BooleanOptionalAction, default=True,
                    help="默认只用本地缓存；--no-local-only 会按配置尝试联网源")
    ap.add_argument("--no-backtest", action="store_true", help="只做排序/权重，不跑 NAV-DD 回测")
    args = ap.parse_args()

    setup_logging(logging.WARNING)
    cfg = load_config(args.config)
    tickers = args.tickers
    if args.from_cache or not tickers.strip():
        tickers = ",".join(cached_universe(cfg.cache_dir))
    res = run_universe_research(
        cfg, tickers,
        total_cap=args.total_cap,
        monthly=args.monthly,
        top_n=args.top_n,
        min_history_years=args.min_years,
        max_weight=args.max_weight,
        min_weight=args.min_weight,
        max_pair_corr=args.max_pair_corr,
        drawdown_budget=args.drawdown_budget,
        local_only=args.local_only,
        include_backtest=not args.no_backtest,
    )

    s = res["summary"]
    print("\n候选池诊断 / 动态篮子建议（research only）")
    print(f"候选 {len(res['used'])} 只；入选 {len(res['selected'])} 只；总 cap ${s['total_cap']:,.0f}")
    print(f"平均相关(3y): {_num(s['avg_pairwise_corr_3y'])} | 平均对QQQ相关: {_num(s['avg_corr_qqq_3y'])}")
    print(f"结论: {s['strategy_fit']}")
    if res["dropped"]:
        print("跳过标的:", ", ".join(f"{k}({v})" for k, v in res["dropped"].items()))
    if res.get("skipped_similar"):
        skipped = ", ".join(f"{x['skipped']}≈{x['kept']} corr {x['corr']:.2f}" for x in res["skipped_similar"])
        print("高相关重复跳过:", skipped)

    print("\n推荐篮子")
    print(f"{'Ticker':<8}{'权重':>8}{'cap_total':>12}{'分数':>8}{'1Y':>9}{'3Y':>9}{'3Y波动':>10}{'3Y回撤':>10}{'QQQ相关':>10}{'趋势':>8}")
    for r in res["selected"]:
        trend = "上行" if r.get("above_ma200") and r.get("ma50_above_ma200") else ("弱" if not r.get("above_ma200") else "修复")
        print(f"{r['ticker']:<8}{_pct(r.get('weight'), 1):>8}${r.get('cap_total', 0):>11,.0f}"
              f"{_num(r.get('score'), 2):>8}{_pct(r.get('ret_1y'), 1):>9}{_pct(r.get('ret_3y'), 1):>9}"
              f"{_pct(r.get('ann_vol_3y'), 1):>10}{_pct(r.get('maxdd_3y'), 1):>10}"
              f"{_num(r.get('corr_qqq_3y'), 2):>10}{trend:>8}")

    bt = res.get("backtest")
    if bt:
        cur = (bt.get("current_config") or {}).get("strategy") or {}
        cur_pr = (bt.get("current_config") or {}).get("pure_ratchet") or {}
        st = bt.get("strategy") or {}
        pr = bt.get("pure_ratchet") or {}
        print("\n同口径回测摘要")
        print(f"区间: {(bt.get('range') or ['-', '-'])[0]} ~ {(bt.get('range') or ['-', '-'])[1]}")
        if cur:
            print(f"当前配置+防御层: XIRR {_pct(cur.get('xirr'), 2)} | DD {_pct(cur.get('maxdd'), 1)} | 终值倍数 {_num(cur.get('mult'), 2)}x")
        if cur_pr:
            print(f"当前纯棘轮风险腿: XIRR {_pct(cur_pr.get('xirr'), 2)} | DD {_pct(cur_pr.get('maxdd'), 1)} | 终值倍数 {_num(cur_pr.get('mult'), 2)}x")
        print(f"推荐篮子+防御层: XIRR {_pct(st.get('xirr'), 2)} | DD {_pct(st.get('maxdd'), 1)} | 终值倍数 {_num(st.get('mult'), 2)}x")
        print(f"推荐篮子纯棘轮: XIRR {_pct(pr.get('xirr'), 2)} | DD {_pct(pr.get('maxdd'), 1)} | 终值倍数 {_num(pr.get('mult'), 2)}x")
        target = None
        for name, metrics in (bt.get("benchmarks") or {}).items():
            if "012922" in name:
                target = (name, metrics or {})
                break
        if target:
            name, m = target
            start = m.get("start")
            suffix = f"（自 {start}）" if start else ""
            print(f"{name}{suffix}: XIRR {_pct(m.get('xirr'), 2)} | DD {_pct(m.get('maxdd'), 1)} | 终值倍数 {_num(m.get('mult'), 2)}x")
        tr = bt.get("target_rolling") or {}
        if tr:
            print(f"\n对标 {tr.get('target')} 滚动验证（>= {tr.get('min_years')} 年，research only）")
            print(_fmt_rolling("当前配置+防御层", tr.get("current_config") or {}))
            print(_fmt_rolling("推荐篮子+防御层", tr.get("recommended") or {}))
        if bt.get("safe_weight_estimate_for_budget") is not None:
            print(f"若把纯风险腿回撤压到约 {_pct(s['drawdown_budget'], 0)}，粗略安全腿 W 估计: {_pct(bt['safe_weight_estimate_for_budget'], 0)}")
        if bt.get("benchmark_errors"):
            print("基准取数失败:", bt["benchmark_errors"])

    print("\n说明: 这是价格历史驱动的研究建议，不含基本面/估值/财报质量，不会自动改 config 或今日建议。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
