"""Read-only live gate for dynamic preference baskets.

PowerShell / PyCharm examples:
    python scripts/live_candidate_gate.py --groups "semis=NVDA,AVGO,AMD;platform=MSFT,GOOG,AAPL" --monthly 3000
    python scripts/live_candidate_gate.py --tickers "NVDA,AVGO,AMD,MSFT,GOOG,AAPL" --include-voltarget --json
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

from backtest.live_gate import run_preference_live_gate
from core.config import load_config
from core.helpers import setup_logging


def _pct(value, digits=1):
    return "-" if value is None else f"{float(value) * 100:.{digits}f}%"


def _money(value):
    return "-" if value is None else f"${float(value):,.0f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="动态候选美股篮子实盘准入预检（read-only）")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--tickers", default="", help="逗号分隔的候选美股 ticker")
    ap.add_argument("--groups", default="", help="自选分组，如 semis=NVDA,AVGO;platform=MSFT,GOOG,AAPL")
    ap.add_argument("--monthly", type=float, default=3000.0)
    ap.add_argument("--total-cap", type=float, default=37000.0)
    ap.add_argument("--target", default="012922")
    ap.add_argument("--min-years", type=float, default=3.0)
    ap.add_argument("--safe-weights", default="0,0.14,0.26")
    ap.add_argument("--include-voltarget", action="store_true")
    ap.add_argument("--voltarget-top-k", type=int, default=4)
    ap.add_argument("--local-only", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = ap.parse_args()

    setup_logging(logging.WARNING)
    cfg = load_config(args.config)
    if args.local_only:
        cfg.data.fallback_chain = ["local_cache"]
    if not args.tickers.strip() and not args.groups.strip():
        raise SystemExit("请提供 --tickers 或 --groups")

    gate = run_preference_live_gate(
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
    if args.json:
        print(json.dumps(gate, ensure_ascii=False, indent=2))
        return 0

    hist = gate.get("history") or {}
    best = hist.get("best") or {}
    best_compact = hist.get("best_compact") or {}
    pref = hist.get("holding_preference") or {}
    preview = gate.get("config_diff_preview") or {}
    guard = gate.get("incumbent_guard") or {}

    print("\n动态候选篮子实盘准入预检（read-only）")
    print(f"决策: {gate.get('decision')} | live_connected={gate.get('live_connected')} | "
          f"does_change_today_advice={gate.get('does_change_today_advice')}")
    print(f"目标基准: {gate.get('target_benchmark')}")
    if best:
        print(f"最佳行: {best.get('basket')} / {best.get('defense_mode')} / "
              f"准入={((best.get('admission') or {}).get('label') or '-')}")
        print(f"滚动窗口: {best.get('windows')} | 胜率 {_pct(best.get('win_rate'), 0)} | "
              f"超额P50 {_pct(best.get('excess_p50'), 2)} | "
              f"DD改善P50 {_pct(best.get('dd_relief_p50'), 1)} | "
              f"策略DD P50 {_pct(best.get('maxdd_p50'), 1)}")
        print("标的: " + ", ".join(best.get("tickers") or []))
    if pref:
        print("\n持仓数量偏好")
        print(f"- 偏好最多 {pref.get('preferred_max_holdings')} 只；{pref.get('rule') or ''}")
        if best_compact:
            print(f"- 最佳精简候选: {best_compact.get('basket')} / N={best_compact.get('n')} / "
                  f"胜率 {_pct(best_compact.get('win_rate'), 0)} / "
                  f"超额P50 {_pct(best_compact.get('excess_p50'), 2)} / "
                  f"DD改善P50 {_pct(best_compact.get('dd_relief_p50'), 1)}")
    print("\n阻断原因")
    for item in gate.get("blockers") or []:
        print(f"- {item}")
    print("\n相对当前写死配置")
    if guard.get("available"):
        inc = guard.get("incumbent") or {}
        cand = guard.get("candidate") or {}
        margins = guard.get("margins") or {}
        print(f"- 通过: {guard.get('passed')} | {guard.get('reason')}")
        print(f"- 候选 XIRR P50 {_pct(cand.get('xirr_p50'), 2)} / DD P50 {_pct(cand.get('maxdd_p50'), 1)}")
        print(f"- 当前配置 XIRR P50 {_pct(inc.get('xirr_p50'), 2)} / DD P50 {_pct(inc.get('maxdd_p50'), 1)}")
        print(f"- 差值 XIRR {_pct(margins.get('xirr_p50_vs_incumbent'), 2)} / DD改善 {_pct(margins.get('dd_relief_p50_vs_incumbent'), 1)}")
    else:
        print(f"- 未能计算: {guard.get('reason') or '-'}")
    print("\n今天是否改变建议")
    print(f"- {((gate.get('today') or {}).get('reason') or '不改变')}")
    print("\n配置差异预览（不会应用）")
    print(f"- total_cap: {_money(preview.get('total_cap'))}; safe: {preview.get('safe_weight_target')}")
    for item in (preview.get("symbols") or [])[:12]:
        print(f"  {item['ticker']:<6} {item['weight']*100:>5.1f}% "
              f"cap {_money(item['cap_total'])} delta {_money(item['delta_cap_total'])} "
              f"{item['status']}")
    removed = preview.get("removed") or []
    if removed:
        print("- 会从候选配置中移除: " + ", ".join(x["ticker"] for x in removed))
    print("\n说明: 这是准入预检，不写 config/state，不生成限价单。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
