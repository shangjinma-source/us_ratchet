"""参数扫描：一次抓数，多组参数复用，输出对比表。

用法（PyCharm 终端）:
    python -m scripts.sweep                 # 每月再注资默认 3000
    python -m scripts.sweep --monthly 0     # 只看初始建仓
    python -m scripts.sweep --start 2018-01-01

每个预设只改 core_ratio / 档位 / 投放比例 / 注资模式，数据与现金流完全相同 → 对比公平。
表里「超额」= 该方案资金加权 XIRR − 即时全仓·权重 的 XIRR。
想加自己的组合，直接在下面 PRESETS 里加一行。
"""
from __future__ import annotations

import argparse
import copy
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import load_config              # noqa: E402
from core.helpers import setup_logging            # noqa: E402
from backtest.engine import run_backtest, _align_prices  # noqa: E402

# ---- 扫描网格：每行一个方案。thresholds 与 deploy_ratios 必须等长、ratios 和≤1 ----
PRESETS = [
    {"name": "当前基线",            "core": 0.65, "thr": [-0.10, -0.20, -0.30, -0.40], "ratio": [0.25, 0.25, 0.25, 0.25]},
    {"name": "深档+越跌越狠",        "core": 0.65, "thr": [-0.15, -0.25, -0.40, -0.55], "ratio": [0.10, 0.20, 0.30, 0.40]},
    {"name": "高核心·小储备(新手荐)", "core": 0.80, "thr": [-0.20, -0.35, -0.50],         "ratio": [0.25, 0.35, 0.40]},
    {"name": "极高核心·近全仓",      "core": 0.90, "thr": [-0.25, -0.45],                  "ratio": [0.40, 0.60]},
    {"name": "中核心·深档",         "core": 0.70, "thr": [-0.15, -0.30, -0.45],          "ratio": [0.20, 0.35, 0.45]},
    {"name": "低核心·多干火药",      "core": 0.50, "thr": [-0.10, -0.20, -0.30, -0.40],   "ratio": [0.25, 0.25, 0.25, 0.25]},
    {"name": "注资全进储备",         "core": 0.65, "thr": [-0.10, -0.20, -0.30, -0.40],   "ratio": [0.25, 0.25, 0.25, 0.25], "inj": "all_reserve"},
]


def _apply(cfg, preset):
    c = copy.deepcopy(cfg)
    p = c.portfolio
    p.core_ratio = preset["core"]
    p.tiers.thresholds = list(preset["thr"])
    p.tiers.deploy_ratios = list(preset["ratio"])
    p.injection_mode = preset.get("inj", "lump_core")
    return c


def _fmt(x, pct=True):
    if x is None:
        return "n/a"
    return f"{x:+.1%}" if pct else f"{x:.2f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="us_ratchet 参数扫描")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--monthly", type=float, default=3000.0)
    ap.add_argument("--start", default=None)
    args = ap.parse_args()

    setup_logging(logging.WARNING)
    cfg = load_config(args.config)
    if args.start:
        cfg.data.start_date = args.start

    initial = {s.ticker: s.cap_total for s in cfg.symbols}
    print(f"\n标的: {list(initial.keys())}  初始 {sum(initial.values()):,.0f}  每月 {args.monthly:,.0f}")
    dates, px, _ = _align_prices(cfg)          # 只抓一次
    prepared = (dates, px)
    print(f"区间: {dates[0].date()} .. {dates[-1].date()}  ({len(dates)} 交易日)\n")

    # 基准（跑一次基线、开 benchmark 拿参考）
    ref = run_backtest(cfg, initial, monthly=args.monthly, prepared=prepared, run_benchmarks=True)
    full = ref.summary["即时全仓·权重"]["xirr"]

    # 各预设（仅策略，省算力）
    results = []
    for preset in PRESETS:
        c = _apply(cfg, preset)
        r = run_backtest(c, initial, monthly=args.monthly, prepared=prepared, run_benchmarks=False)
        s = r.summary["策略"]
        tc = r.summary.get("tier_contrib", {})
        fires = "/".join(str(tc.get(i, {}).get("count", 0)) for i in range(len(preset["thr"])))
        results.append((preset["name"], s, fires))

    # 排序：按 XIRR 降序
    results.sort(key=lambda x: (x[1]["xirr"] is not None, x[1]["xirr"]), reverse=True)

    print(f"{'方案':<20}{'XIRR':>9}{'超额vs全仓':>11}{'最大回撤':>9}{'终值倍数':>10}"
          f"{'平均在场':>9}{'档触发(浅→深)':>16}")
    print("-" * 86)
    for name, s, fires in results:
        excess = (s["xirr"] - full) if (s["xirr"] is not None and full is not None) else None
        ai = s.get("avg_invested")
        print(f"{name:<20}{_fmt(s['xirr']):>9}{_fmt(excess):>11}{s['maxdd']:>8.1%}"
              f"{s['mult']:>9.1f}x{(ai if ai else 0):>8.0%}{fires:>16}")

    print("-" * 86)
    for bname in ["即时全仓·权重", "定投DCA·权重", "即时全仓·等权"]:
        b = ref.summary[bname]
        print(f"{bname:<20}{_fmt(b['xirr']):>9}{'(基准)':>11}{b['maxdd']:>8.1%}{b['mult']:>9.1f}x")

    print("\n读表提示：")
    print("  · 想要'几个买点+长期持有'：看 平均在场高(≈全仓) 且 超额接近0/为正、回撤≤全仓 的行。")
    print("  · 档触发'浅→深'：若最深档常年 0 次，说明该档形同虚设，可去掉或收紧。")
    print("  · 没有哪行能在这种超强趋势里既高收益又低回撤——这本身就是结论：集中科技/AI/芯片=高收益高波动。")
    print("  · XIRR 为资金加权主指标；最大回撤算在含注资净值上、偏乐观，仅供横向对比。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())