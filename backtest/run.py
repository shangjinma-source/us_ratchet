"""回测入口 + 诚实报告（含现金拖累说明）。

用法（Windows / PyCharm 终端）:
    python -m backtest.run
    python -m backtest.run --monthly 3000          # 每月再注资 3000（按 cap 权重分配）
    python -m backtest.run --injection-mode all_reserve   # 临时覆盖注资模式做 A/B
    python -m backtest.run --start 2018-01-01

    # 自定义篮子（不改 config.yaml，直接在命令行给硬件标的）：
    python -m backtest.run --basket "NVDA:100000,MU:60000,AMAT:80000" --monthly 3000
    python -m backtest.run --basket "MU,AMAT,LRCX,KLAC" --start 2019-01-01   # 省略金额则默认等额
    # 自定义篮子默认从 2018-01-01 起算（砍掉早期失真段）；取不到数据的标的默认跳过并列出（--strict 改为报错）。

初始本金 = config（或 --basket）中各标的 cap_total（即首日按计划建仓）。
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import load_config                       # noqa: E402
from core.helpers import setup_logging                     # noqa: E402
from backtest.engine import (run_backtest, run_basket_backtest,  # noqa: E402
                             run_basket_risk_sweep, run_basket_defensive_sweep,
                             run_defensive_sweep, run_voltarget_sweep,
                             run_basket_voltarget_sweep)

DEFAULT_BASKET_CAP = 100000.0   # --basket 中省略金额时的默认 cap
DEFAULT_BASKET_START = "2018-01-01"  # 自定义篮子未显式 --start 时的默认起算日


def _fmt_pct(x):
    return "n/a" if x is None else f"{x:+.1%}"


def _fmt_ratio(x):
    return "n/a" if x is None else f"{x:.2f}"


def _interp_for_target_dd(pts, target):
    """pts=[(w, maxdd, xirr)...]（按 W 升序、maxdd 随 W 递减）。线性插值反推达成
    target 回撤所需的安全资产权重 W 及对应资金加权 XIRR。返回一行中文结论。"""
    pts = sorted(pts, key=lambda x: x[0])
    if not pts:
        return ""
    w0, dd0, x0 = pts[0]
    wl, ddl, xl = pts[-1]
    head = f"目标回撤 {target:.0%}: "
    if target >= dd0:
        return head + f"W=0(纯篮子)回撤 {dd0:.1%} 已≤目标，无需现金腿；对应XIRR {_fmt_pct(x0)}。"
    if target < ddl:
        return (head + f"即便 W={wl:.0%} 回撤仍有 {ddl:.1%} > 目标，需更厚防御腿"
                f"（调高 --weights 上限再扫）；W={wl:.0%} 时XIRR {_fmt_pct(xl)}。")
    for (wa, dda, xa), (wb, ddb, xb) in zip(pts, pts[1:]):
        if dda >= target >= ddb and dda > ddb:
            f = (dda - target) / (dda - ddb)
            w_star = wa + f * (wb - wa)
            x_star = (xa + f * (xb - xa)) if (xa is not None and xb is not None) else None
            return (head + f"需约 W={w_star:.0%} 安全资产 ↔ 资金加权XIRR ≈ {_fmt_pct(x_star)}"
                    f"（在 {wa:.0%}~{wb:.0%} 间线性插值，仅估）。")
    return head + "无法插值（检查 --weights 是否单调覆盖目标）。"


def _parse_basket(s: str) -> list:
    """解析 --basket 字符串为 [(ticker, cap), ...]。
    每项 'TICKER' 或 'TICKER:CAP'；省略 CAP 用 DEFAULT_BASKET_CAP。"""
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            tk, cap = part.split(":", 1)
            tk = tk.strip().upper()
            try:
                cap_val = float(cap)
            except ValueError:
                raise SystemExit(f"--basket 金额解析失败: '{part}'")
            if cap_val <= 0:
                raise SystemExit(f"--basket 金额必须 > 0: '{part}'")
            out.append((tk, cap_val))
        else:
            out.append((part.upper(), DEFAULT_BASKET_CAP))
    if not out:
        raise SystemExit("--basket 解析为空")
    tks = [t for t, _ in out]
    if len(tks) != len(set(tks)):
        raise SystemExit(f"--basket 标的重复: {tks}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="us_ratchet 回测")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--monthly", type=float, default=0.0, help="每月再注资总额（按 cap 权重）")
    ap.add_argument("--start", default=None, help="覆盖回测起始日 YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="覆盖回测结束日 YYYY-MM-DD")
    ap.add_argument("--injection-mode", default=None,
                    choices=["lump_core", "all_reserve", "ladder_core"])
    ap.add_argument("--basket", default=None,
                    help='自定义篮子，如 "NVDA:100000,MU:60000,AMAT"（省略金额默认 100000）；'
                         f'不传则用 config 的 symbols。未显式 --start 时默认从 {DEFAULT_BASKET_START} 起算。')
    ap.add_argument("--strict", action="store_true",
                    help="自定义篮子里有标的取不到数据则直接报错（默认：跳过并列出）")
    ap.add_argument("--risk-sweep", action="store_true",
                    help="趋势风控扫描（C7）：跌破MA减仓压回撤，扫 floor 看回撤/收益权衡。需配 --basket")
    ap.add_argument("--ma", type=int, default=200, help="风控趋势MA窗口（交易日，默认200≈10月）")
    ap.add_argument("--floors", default="1.0,0.75,0.5,0.25,0.0",
                    help="风控下跌时保留的敞口档位（逗号分隔；1.0=基线不减仓）")
    ap.add_argument("--band", type=float, default=0.0, help="MA迟滞带（如0.02=±2%，抑制反复进出）")
    ap.add_argument("--cost", type=float, default=0.001, help="每次买卖单边成本（默认0.001=10bp）")
    ap.add_argument("--defensive-sweep", action="store_true",
                    help="防御层扫描（B）：篮子 + W%%安全资产(~0回撤)，扫 W 看回撤/收益曲线。需配 --basket")
    ap.add_argument("--weights", default="0,0.1,0.2,0.3,0.4,0.5",
                    help="防御层安全资产权重档位（逗号分隔；0=纯篮子基线）")
    ap.add_argument("--safe-rate", type=float, default=0.04,
                    help="安全资产年化收益（现金/短债，默认0.04=4%%，回撤≈0）")
    ap.add_argument("--rebal-days", type=int, default=21,
                    help="防御层再平衡周期(交易日；21≈月度，1=每日，0=不再平衡)")
    ap.add_argument("--rebal-band", type=float, default=0.0,
                    help="防御层漂移再平衡带(如0.05=现金权重偏离目标≥5pp才动；0=只按周期)")
    ap.add_argument("--target-dd", type=float, default=0.30,
                    help="防御层目标回撤(用于反推所需W与对应XIRR，线性插值，默认0.30)")
    ap.add_argument("--voltarget", action="store_true",
                    help="vol-target lite 评估(A)：动态防御层 vs 静态W前沿(同回撤口径)+样本外切分。需配 --basket 或用 config symbols")
    ap.add_argument("--vt-target-vol", type=float, default=None, help="vol-target 年化目标波动(默认固化0.25)")
    ap.add_argument("--vt-base", type=float, default=None, help="vol-target 静态基线安全权重(默认固化0.40)")
    ap.add_argument("--vt-band", type=float, default=None, help="vol-target 目标权重钳制带±(默认固化0.15)")
    ap.add_argument("--vt-vol-win", type=int, default=None, help="vol-target 实现波动回看窗(交易日，默认固化20)")
    ap.add_argument("--vt-exec-band", type=float, default=None, help="vol-target 执行带(偏离≥此值才snap，默认固化0.15)")
    ap.add_argument("--oos-split", default="2022-01-01", help="样本外切分日(默认2022-01-01；空串关闭)")
    ap.add_argument("--benchmark", default=None,
                    help="外部基准标的(如 QQQ 纳指100 / SPY)，画到同一(回撤,收益)平面 + 判定能否压制它。配 --voltarget 用")
    args = ap.parse_args()

    setup_logging(logging.WARNING)   # 抓取日志压到 WARNING，报告更清爽
    cfg = load_config(args.config)
    if args.start:
        cfg.data.start_date = args.start
    if args.end is not None:
        cfg.data.end_date = args.end
    if args.injection_mode:
        cfg.portfolio.injection_mode = args.injection_mode

    # ---- C7 趋势风控扫描：独立报告路径 ----
    if args.risk_sweep:
        if not args.basket:
            print("⚠ --risk-sweep 需配 --basket 指定标的池")
            return 2
        if not args.start:
            cfg.data.start_date = DEFAULT_BASKET_START
        basket = _parse_basket(args.basket)
        floors = tuple(float(x) for x in args.floors.split(","))
        print(f"\n趋势风控扫描（C7 原型）: {len(basket)} 标的池")
        print(f"起算 {cfg.data.start_date}  | MA{args.ma} 门  | 迟滞带 ±{args.band:.0%}"
              f"  | 单边成本 {args.cost*1e4:.0f}bp  | 每月注资 {args.monthly:,.0f}")
        print("规则: 基准NAV跌破MA→减仓到 floor*净值+暂停补跌；升破MA→回补满仓。floor=1.0 即基线。")
        print("抓取数据中...\n")
        r = run_basket_risk_sweep(cfg, basket, monthly=args.monthly, floors=floors,
                                  ma_days=args.ma, band=args.band, cost=args.cost,
                                  skip_missing=not args.strict, strict=args.strict)
        if r["dropped"]:
            print(f"⚠ 已跳过取不到数据的标的: {r['dropped']}\n")
        late = [c for c in r["coverage"] if c.get("late")]
        if late:
            print("⚠ 错峰起算 — 晚上市标的仅从各自上市日并入：")
            for c in late:
                print(f"    {c['ticker']:<6} 自 {c['start']} 起（{c['rows']} 行）")
            print()
        g = r["grid"]
        print(f"区间: {g[0].date()} .. {g[-1].date()}  | 累计投入 {r['contributed']:,.0f}"
              f"  | 风控触发(risk-off)天数占比 {r['frac_off']:.0%}\n")
        print(f"{'下跌保留敞口':<12}{'终值/投入':>10}{'资金加权XIRR':>14}{'最大回撤':>10}"
              f"{'Sharpe':>8}{'Sortino':>9}{'平均在场':>10}{'换手(x)':>9}")
        base_dd = None
        for fl, m in r["rows"]:
            tag = f"{fl:.0%}" + ("(基线)" if fl >= 1.0 else "")
            if fl >= 1.0:
                base_dd = m["maxdd"]
            mult = "n/a" if m["mult"] is None else f"{m['mult']:.2f}x"
            tx = "n/a" if m["turnover_x"] is None else f"{m['turnover_x']:.2f}"
            print(f"{tag:<12}{mult:>10}{_fmt_pct(m['xirr']):>14}{m['maxdd']:>9.1%}"
                  f"{_fmt_ratio(m['sharpe']):>8}{_fmt_ratio(m['sortino']):>9}"
                  f"{m['avg_invested']:>9.0%}{tx:>9}")
        b = r["bench"]
        bmult = "n/a" if b["mult"] is None else f"{b['mult']:.2f}x"
        print(f"{'即时全仓基准':<12}{bmult:>10}{_fmt_pct(b['xirr']):>14}{b['maxdd']:>9.1%}"
              f"{'':>8}{'':>9}{'100%':>10}{'—':>9}")
        print("\n" + "-" * 78)
        print("读法: 每往下一行=风控更狠(下跌时仓位留得更少)→ 回撤更浅，但XIRR被磨低、换手↑。")
        print("找“回撤明显下台阶、而XIRR还没掉太多”的那一档，就是你的甜点。")
        if base_dd is not None:
            print(f"基线(不卖)回撤 {base_dd:.0%} 是只买不卖的天花板；风控就是用收益换它下来。")
        print("注: 回撤为单位NAV口径(真实体验)。换手(x)=累计买卖额/投入，看交易摩擦。")
        print("注: 这是回测原型，信号=基准NAV过MA；参数定了再移植进 core 做实盘同源。")
        return 0

    # ---- B 防御层扫描：独立报告路径（不传 --basket 时回落到 config.yaml 的 symbols）----
    if args.defensive_sweep:
        weights = tuple(float(x) for x in args.weights.split(","))
        if args.basket:
            if not args.start:
                cfg.data.start_date = DEFAULT_BASKET_START   # 自定义篮子默认砍掉早期失真段
            basket = _parse_basket(args.basket)
            n_syms = len(basket)
        else:
            basket = None                                    # 用 config.yaml 的 symbols
            n_syms = len(cfg.symbols)
            if n_syms == 0:
                print("⚠ --defensive-sweep 未传 --basket 且 config.yaml 无 symbols")
                return 2
        parts = ([f"每{args.rebal_days}日"] if args.rebal_days >= 1 else []) \
            + ([f"漂移≥{args.rebal_band:.0%}"] if args.rebal_band > 0 else [])
        rebal_desc = " + ".join(parts) if parts else "不再平衡(只切新投入)"
        src = "config.yaml symbols" if basket is None else "命令行 --basket"
        print(f"\n防御层扫描（B 方向）: {n_syms} 标的篮子（来源: {src}）")
        print(f"起算 {cfg.data.start_date}  | 安全资产年化 {args.safe_rate:.0%}"
              f"  | 维持权重: {rebal_desc}  | 每月注资 {args.monthly:,.0f}")
        print("规则: 篮子(棘轮策略=风险腿) + W%安全资产(~0回撤=防御腿) 组合成一只基金；")
        print("      W=0 即策略基线；机械关系 组合回撤 ≈ (1-W)×板块回撤。")
        print("抓取数据中...\n")
        if basket is not None:
            r = run_basket_defensive_sweep(cfg, basket, monthly=args.monthly,
                                           weights=weights, safe_annual=args.safe_rate,
                                           rebal_days=args.rebal_days, rebal_band=args.rebal_band,
                                           skip_missing=not args.strict, strict=args.strict)
        else:
            r = run_defensive_sweep(cfg, monthly=args.monthly,
                                    weights=weights, safe_annual=args.safe_rate,
                                    rebal_days=args.rebal_days, rebal_band=args.rebal_band,
                                    skip_missing=not args.strict, strict=args.strict)
        if r["dropped"]:
            print(f"⚠ 已跳过取不到数据的标的: {r['dropped']}\n")
        late = [c for c in r["coverage"] if c.get("late")]
        if late:
            print("⚠ 错峰起算 — 晚上市标的仅从各自上市日并入：")
            for c in late:
                print(f"    {c['ticker']:<6} 自 {c['start']} 起（{c['rows']} 行）")
            print()
        g = r["grid"]
        base_dd = r["base_maxdd"]
        print(f"区间: {g[0].date()} .. {g[-1].date()}  | 累计投入 {r['contributed']:,.0f}"
              f"  | 策略基线(W=0)回撤 {base_dd:.1%}\n")
        print(f"{'安全资产W':<10}{'终值/投入':>10}{'资金加权XIRR':>14}{'最大回撤':>9}"
              f"{'≈(1-W)基线':>11}{'Sharpe':>8}{'Sortino':>9}{'再平衡(次/换手)':>15}")
        for w, m in r["rows"]:
            tag = f"{w:.0%}" + ("(基线)" if w <= 0 else "")
            mult = "n/a" if m["mult"] is None else f"{m['mult']:.2f}x"
            theo = base_dd * (1.0 - w)
            if w <= 0:
                rb = "—"
            else:
                tx = "n/a" if m["turnover_x"] is None else f"{m['turnover_x']:.2f}x"
                rb = f"{m['n_rebal']}/{tx}"
            print(f"{tag:<10}{mult:>10}{_fmt_pct(m['xirr']):>14}{m['maxdd']:>8.1%}"
                  f"{theo:>11.1%}{_fmt_ratio(m['sharpe']):>8}{_fmt_ratio(m['sortino']):>9}"
                  f"{rb:>15}")
        b = r["bench"]
        bmult = "n/a" if b["mult"] is None else f"{b['mult']:.2f}x"
        print(f"{'即时全仓基准':<10}{bmult:>10}{_fmt_pct(b['xirr']):>14}{b['maxdd']:>8.1%}"
              f"{'':>11}{'':>8}{'':>9}{'—':>15}")
        pts = [(w, m["maxdd"], m["xirr"]) for w, m in r["rows"]]
        print("\n" + "-" * 88)
        print("读法: 每往下一行=防御腿更厚→回撤更浅、XIRR被现金腿磨低；再平衡列(次数/换手)看机械化成本。")
        print(_interp_for_target_dd(pts, args.target_dd))
        print(f"注: 回撤为单位NAV口径(真实体验)；安全资产=每日固定 {args.safe_rate:.0%}/252、回撤≈0。")
        print("注: 维持 W 的再平衡=防御层纪律(涨多了把超出挪回防御腿)，独立于棘轮核心只买不卖。")
        print("    对照: --rebal-days 1 每日极限 / --rebal-band 0.05 漂移触发(交易少得多) / --rebal-days 0 不维持。")
        print("注: 这是回测原型，防御层在组合层；方案定了再移植进 core 做实盘同源。")
        return 0

    # ---- A: vol-target lite 评估：独立报告路径（不传 --basket 时回落到 config.yaml 的 symbols）----
    if args.voltarget:
        if args.basket:
            if not args.start:
                cfg.data.start_date = DEFAULT_BASKET_START
            basket = _parse_basket(args.basket)
            n_syms = len(basket)
        else:
            basket = None
            n_syms = len(cfg.symbols)
            if n_syms == 0:
                print("⚠ --voltarget 未传 --basket 且 config.yaml 无 symbols")
                return 2
        oos = args.oos_split if args.oos_split else None
        kw = dict(target_vol=args.vt_target_vol, base_w=args.vt_base, band=args.vt_band,
                  vol_win=args.vt_vol_win, exec_band=args.vt_exec_band, oos_split=oos,
                  safe_annual=args.safe_rate, benchmark_ticker=args.benchmark)
        src = "config.yaml symbols" if basket is None else "命令行 --basket"
        print(f"\nvol-target lite 评估（A 方向）: {n_syms} 标的篮子（来源: {src}）")
        print("规则: 静态W为底座(沿前沿滑)，vol-target在基线附近用快波动信号微调安全权重(把前沿往外推)。")
        print("      同回撤口径对比(看外推多少pp) + 样本外切分(看边际是否两窗都为正)。信号取即时全仓基准NAV。")
        print("抓取数据中...\n")
        if basket is not None:
            r = run_basket_voltarget_sweep(cfg, basket, monthly=args.monthly,
                                           skip_missing=not args.strict, strict=args.strict, **kw)
        else:
            r = run_voltarget_sweep(cfg, monthly=args.monthly,
                                    skip_missing=not args.strict, strict=args.strict, **kw)
        if r["dropped"]:
            print(f"⚠ 已跳过取不到数据的标的: {r['dropped']}\n")
        late = [c for c in r["coverage"] if c.get("late")]
        if late:
            print("⚠ 错峰起算 — 晚上市标的仅从各自上市日并入：")
            for c in late:
                print(f"    {c['ticker']:<6} 自 {c['start']} 起（{c['rows']} 行）")
            print()
        g = r["grid"]
        p = r["params"]
        print(f"区间: {g[0].date()} .. {g[-1].date()}  | 累计投入 {r['contributed']:,.0f}")
        print(f"固化参数: 目标波动 {p['target_vol']:.0%} | 基线W {p['base_w']:.0%} | 钳制带 ±{p['band']:.0%}"
              f" | 波动窗 {p['vol_win']}d | 执行带 {p['exec_band']:.0%} | 安全腿 {p['safe_annual']:.0%}\n")
        print("【静态W前沿（沿曲线滑）】")
        print(f"{'安全资产W':<10}{'终值/投入':>10}{'资金加权XIRR':>14}{'最大回撤':>9}{'Sharpe':>8}{'Sortino':>9}")
        for w, m in r["static_rows"]:
            tag = f"{w:.0%}" + ("(基线)" if w <= 0 else "")
            mult = "n/a" if m["mult"] is None else f"{m['mult']:.2f}x"
            print(f"{tag:<10}{mult:>10}{_fmt_pct(m['xirr']):>14}{m['maxdd']:>8.1%}"
                  f"{_fmt_ratio(m['sharpe']):>8}{_fmt_ratio(m['sortino']):>9}")
        vt = r["vt_row"]
        vmult = "n/a" if vt["mult"] is None else f"{vt['mult']:.2f}x"
        tx = "n/a" if vt["turnover_x"] is None else f"{vt['turnover_x']:.2f}x"
        print(f"\n【vol-target lite（把前沿往外推）】 平均仓位 {1 - r['vt_avg_w']:.0%}（安全腿均 {r['vt_avg_w']:.0%}）")
        print(f"{'动态防御层':<10}{vmult:>10}{_fmt_pct(vt['xirr']):>14}{vt['maxdd']:>8.1%}"
              f"{_fmt_ratio(vt['sharpe']):>8}{_fmt_ratio(vt['sortino']):>9}   换手 {tx} / {vt['n_rebal']}次")
        if r["vt_excess"] is not None:
            print(f"\n  → 全程同回撤口径: vol-target 在 {vt['maxdd']:.1%} 回撤处 XIRR {_fmt_pct(vt['xirr'])}，"
                  f"同回撤静态约 {_fmt_pct(r['vt_base_at_dd'])} → 前沿外推 {r['vt_excess']:+.1%}")
        if r["oos"]:
            print("\n【样本外切分（CAGR口径；边际要两窗都为正才可信）】")
            print(f"{'窗口':<18}{'天数':>6}{'vol-tgt回撤':>11}{'vol-tgt CAGR':>13}{'同回撤静态':>11}{'超额':>8}")
            for o in r["oos"]:
                cg = "n/a" if o["cagr"] is None else f"{o['cagr']:+.1%}"
                bs = "n/a" if o["static_cagr_at_dd"] is None else f"{o['static_cagr_at_dd']:+.1%}"
                ex = "n/a" if o["excess"] is None else f"{o['excess']:+.1%}"
                print(f"{o['win']:<18}{o['days']:>6}{o['maxdd']:>10.1%}{cg:>13}{bs:>11}{ex:>8}")
        bm = r.get("bench")
        if bm is not None:
            print("\n【对标外部基准（你的目标：跑赢它）】")
            if bm.get("error"):
                print(f"  ⚠ 基准 {bm['ticker']} 取数失败：{bm['error']}（本机用 sina 源应可抓 QQQ/SPY）")
            else:
                bmult = "n/a" if bm["mult"] is None else f"{bm['mult']:.2f}x"
                print(f"  {bm['ticker']}({bm.get('source','?')}) 买入持有(同资金时间表): "
                      f"{bmult} / XIRR {_fmt_pct(bm['xirr'])} / 回撤 {bm['maxdd']:.1%} / "
                      f"Sharpe {_fmt_ratio(bm['sharpe'])}")
                if bm.get("raw_beat") is not None:
                    sign = "赢" if bm["raw_beat"] > 0 else "输"
                    print(f"  (A) 比收益: 满仓篮子(W=0) {_fmt_pct(r['static_rows'][0][1]['xirr'])} "
                          f"vs {bm['ticker']} {_fmt_pct(bm['xirr'])} → {sign} {abs(bm['raw_beat']):.1%}"
                          f"（但满仓=47%回撤+纯后视镜赌注）")
                if bm.get("dominate_gap") is not None:
                    sign = "压制✓" if bm["dominate_gap"] > 0 else "被压✗"
                    print(f"  (B) 同回撤压制: 在 {bm['ticker']} 的 {bm['maxdd']:.1%} 回撤档，你静态前沿约需 "
                          f"W={bm['w_at_dd']:.0%}、给 XIRR {_fmt_pct(bm['static_xirr_at_dd'])} "
                          f"vs {bm['ticker']} {_fmt_pct(bm['xirr'])} → {sign} {abs(bm['dominate_gap']):+.1%}")
                print(f"  ⚠ 诚实: 这个赢 = 2018-26 半导体领涨 + 幸存者篮子的后视镜，是集中板块赌注，"
                      f"非稳赢大盘；半导体哑火则反过来大幅跑输 {bm['ticker']}。")
        print("\n" + "-" * 88)
        print("读法: 静态W是底座(选你回撤档)；vol-target在同回撤下多出的 pp = 前沿被往外推的幅度。")
        print("诚实保留①: 同一overlay在等权XSD上为负 → 这点外推绑定你这篮子的具体波动结构，换标的未必复制。")
        print("诚实保留②: 全在2018-26同一AI牛市区间；样本外只是切了它两段，不等于换十年仍成立。")
        print("注: 同源——动态目标权重仍只经 core.engine.compute_defensive_rebalance 决策，与静态防御层同一函数。")
        print("注: XIRR/回撤为单位NAV口径；此为毛收益(扣5bp换手成本)，税是落地阶段才叠加的二阶修正。")
        return 0

    dropped = []
    if args.basket:
        basket = _parse_basket(args.basket)
        if not args.start:
            cfg.data.start_date = DEFAULT_BASKET_START   # 自定义篮子默认砍掉早期失真段
        print(f"\n自定义篮子: {basket}")
        print(f"起算: {cfg.data.start_date}  | 每月再注资: {args.monthly:,.0f}"
              f"  | 注资模式: {cfg.portfolio.injection_mode}"
              f"  | 缺数标的: {'严格报错' if args.strict else '跳过并列出'}")
        print("引擎: 错峰起算 + 单位NAV真实回撤（各标的从自身上市日并入）")
        print("抓取数据中（多源降级 + 复权）...\n")
        res, dropped = run_basket_backtest(cfg, basket, monthly=args.monthly,
                                           skip_missing=not args.strict, strict=args.strict)
        initial = {t: cap for t, cap in basket if t not in dropped}
    else:
        initial = {s.ticker: s.cap_total for s in cfg.symbols}
        print(f"\n回测标的: {list(initial.keys())}")
        print(f"初始建仓本金: {sum(initial.values()):,.0f}  | 每月再注资: {args.monthly:,.0f}"
              f"  | 注资模式: {cfg.portfolio.injection_mode}")
        print("抓取数据中（多源降级 + 复权）...\n")
        res = run_backtest(cfg, initial, monthly=args.monthly)

    if dropped:
        print(f"⚠ 已跳过取不到数据的标的: {dropped}（如需严格报错用 --strict）\n")

    s = res.summary

    # 错峰覆盖报告：哪些标的上市晚于起点、只贡献自身区间（不再连累全篮被截短）
    cov = s.get("coverage")
    if cov:
        late = [c for c in cov if c.get("late")]
        if late:
            print("⚠ 错峰起算 — 以下标的上市晚于回测起点，仅从各自上市日并入：")
            for c in late:
                print(f"    {c['ticker']:<6} 自 {c['start']} 起（{c['rows']} 行）")
            print()

    print(f"区间: {res.dates[0].date()} .. {res.dates[-1].date()}  ({s['days']} 天)")
    print(f"实际回测标的: {list(initial.keys())}")
    print(f"累计投入本金: {s['contributed']:,.0f}\n")

    rows = ["策略"] + list(res.benchmarks.keys())
    print(f"{'方案':<16}{'终值':>14}{'终值/投入':>10}{'资金加权XIRR':>14}"
          f"{'最大回撤':>10}{'Sharpe':>8}{'Sortino':>9}{'平均在场':>10}")
    for name in rows:
        b = s[name]
        ai = b.get("avg_invested")
        ai_s = "n/a" if ai is None else f"{ai:.0%}"
        mult = "n/a" if b["mult"] is None else f"{b['mult']:.3f}x"
        print(f"{name:<16}{b['final']:>14,.0f}{mult:>10}{_fmt_pct(b['xirr']):>14}"
              f"{b['maxdd']:>9.1%}{_fmt_ratio(b['sharpe']):>8}{_fmt_ratio(b['sortino']):>9}{ai_s:>10}")

    # 超额（资金加权）
    base = s["即时全仓·权重"]["xirr"]
    st = s["策略"]["xirr"]
    if base is not None and st is not None:
        print(f"\n策略 vs 即时全仓·权重（资金加权超额）: {st - base:+.2%}")

    # 档位贡献
    tc = s.get("tier_contrib", {})
    if tc:
        print("\n回撤档位贡献（触发买入额）:")
        names = cfg.portfolio.tiers.thresholds
        for i in sorted(tc):
            print(f"  {names[i]:>6.0%} 档: 触发 {tc[i]['count']:>3} 次, 投放 {tc[i]['amount']:>12,.0f}")

    print("\n" + "-" * 78)
    print("现金拖累说明: 策略平均在场比例低于全仓基准，单边牛市里几乎必然跑输即时全仓——")
    print("这是设计代价，不是 bug。本策略价值在于(a)系统化投放持续注入的新钱、(b)风险调整后")
    print("指标(Sharpe/Sortino)、(c)更浅的最大回撤/可执行性，而非宣称收益更高。")
    if "coverage" in s:
        print("注：最大回撤为单位NAV(基金净值)口径——真实投资者体验，已剔除注资影响（C6a 错峰引擎）。")
    else:
        print("注：最大回撤算在含注资净值上、偏乐观，仅供横向对比。")
    print("注：资金加权 XIRR 为主指标；持续注资下简单 CAGR 会失真。结论请以你自己的风险承受度为准。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())