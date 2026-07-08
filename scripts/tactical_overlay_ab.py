"""Tactical fixed-limit overlay A/B with current-config promotion checks.

PowerShell / PyCharm example:
    python scripts/tactical_overlay_ab.py --monthly 3000 --local-only
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.engine import run_tactical_overlay_ab
from core.config import load_config
from core.helpers import setup_logging


def _pct(value, digits=1):
    return "-" if value is None else f"{float(value) * 100:.{digits}f}%"


def _money(value):
    return "-" if value is None else f"${float(value):,.0f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="战术固定限价 A/B：对比关闭战术单与当前实盘战术配置")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--monthly", type=float, default=3000.0)
    ap.add_argument("--safe-weight", type=float, default=None,
                    help="防御层权重；默认使用 config.safe_leg.target_weight")
    ap.add_argument("--rolling-min-years", type=float, default=5.0)
    ap.add_argument("--rolling-step-months", type=int, default=12)
    ap.add_argument("--local-only", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args()

    setup_logging(logging.WARNING)
    cfg = load_config(args.config)
    if args.local_only:
        cfg.data.fallback_chain = ["local_cache"]
    sl = getattr(cfg, "safe_leg", None)
    safe_weight = args.safe_weight
    if safe_weight is None:
        safe_weight = float(sl.target_weight) if sl is not None else 0.0
    rebal_band = float(sl.exec_band) if sl is not None else 0.0

    res = run_tactical_overlay_ab(
        cfg,
        monthly=float(args.monthly),
        safe_weight=float(safe_weight or 0.0),
        safe_annual=0.04,
        rebal_days=21,
        rebal_band=rebal_band,
        rolling_min_years=float(args.rolling_min_years),
        rolling_step_months=max(1, int(args.rolling_step_months)),
    )
    s = res["summary"]
    rows = list(res["rows"])
    rows = sorted(rows, key=lambda r: (
        {"candidate": 3, "watch": 2, "current": 1, "reject": 0}.get(r.get("promotion_stage"), 0),
        r.get("xirr_vs_current_tactical") or -9,
    ), reverse=True)

    print("\n战术固定限价 A/B（research only）")
    print(f"区间: {res['grid'][0].strftime('%Y-%m-%d')} ~ {res['grid'][-1].strftime('%Y-%m-%d')} | "
          f"W={_pct(s.get('safe_weight'), 0)} | 月投 {_money(args.monthly)}")
    print(f"最佳XIRR: {s.get('best_xirr')} | 最佳综合: {s.get('best_score')} | "
          f"替换候选 {s.get('promotion_candidate_count')} | 观察项 {s.get('promotion_watch_count')}")
    print(f"{'方案':<24}{'XIRR':>9}{'vs当前':>10}{'DD':>9}{'DDvs当前':>11}"
          f"{'成交':>7}{'动用':>10}{'折价':>9}{'20日后':>9}"
          f"{'滚动vs当前':>12}{'滚动候选':>10}  替换评审")
    for r in rows:
        m = r.get("metrics") or {}
        st = r.get("stats") or {}
        rv = r.get("rolling_vs_current") or {}
        rx = rv.get("xirr_vs_current") or {}
        print(f"{r['mode']:<24}{_pct(m.get('xirr'), 2):>9}"
              f"{_pct(r.get('xirr_vs_current_tactical'), 2):>10}"
              f"{_pct(m.get('maxdd'), 1):>9}"
              f"{_pct(r.get('dd_relief_vs_current_tactical'), 1):>11}"
              f"{int(st.get('fills') or 0):>7}{_money(st.get('fill_amount')):>10}"
              f"{_pct(st.get('avg_discount'), 2):>9}{_pct(st.get('avg_fwd20'), 2):>9}"
              f"{_pct(rx.get('p50'), 2):>12}{_pct(rv.get('candidate_rate'), 0):>10}  "
              f"{r.get('promotion_verdict') or '-'}")

    candidates = [r for r in rows if r.get("promotion_stage") == "candidate"]
    watches = [r for r in rows if r.get("promotion_stage") == "watch"]
    print("\n结论")
    if candidates:
        names = ", ".join(r["mode"] for r in candidates)
        print(f"存在可进入人工替换评审的战术配置候选: {names}。接入前仍需今日建议差异检查。")
    elif watches:
        best = watches[0]
        print(f"暂无可替换配置；最接近观察项是 {best['mode']}，但未同时通过全程和滚动 vs当前配置。")
    else:
        print("没有候选优于当前战术配置；维持现有实盘规则。")
    print("说明: 该脚本只读回测，不写 config/state，不改变今日建议。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
