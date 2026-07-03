"""数据层自检 / 复权校验报告。

用法（Windows）:
    python -m scripts.check_data
    python -m scripts.check_data --cross   # 额外跑 eastmoney vs sina 跨源复权一致性

对 config 中每只标的：抓取 → 复权校验 → 打印来源、区间、行数、疑似未复权跳变、
以及由 cap 推导出的 weight / core_target / reserve_quota。
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 允许从项目根直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import load_config          # noqa: E402
from core.helpers import setup_logging        # noqa: E402
from data.fetch import get_bars, cross_provider_check, DataError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="us_ratchet 数据层自检")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--cross", action="store_true", help="跑跨源复权一致性校验")
    args = ap.parse_args()

    setup_logging(logging.INFO)
    cfg = load_config(args.config)

    print("\n=== 组合推导（来自每只 cap_total）===")
    total = sum(s.cap_total for s in cfg.symbols)
    print(f"计划总资金: {total:,.0f}  | core_ratio={cfg.portfolio.core_ratio}  "
          f"档位={cfg.portfolio.tiers.thresholds} 比例={cfg.portfolio.tiers.deploy_ratios}")
    print(f"{'标的':<8}{'cap_total':>12}{'权重':>8}{'核心目标':>12}{'储备配额':>12}")
    for s in cfg.symbols:
        print(f"{s.ticker:<8}{s.cap_total:>12,.0f}{s.weight:>7.1%}"
              f"{s.core_target:>12,.0f}{s.reserve_quota:>12,.0f}")

    print("\n=== 数据抓取 + 复权校验 ===")
    ok, fail = 0, 0
    from data import cn_source
    tol = getattr(cfg.data, "split_detect_tol", 0.06)
    for s in cfg.symbols:
        try:
            _df, meta = get_bars(s.ticker, cfg)
            jumps = meta.suspicious_jumps
            split_like = [(d, p) for d, p in jumps if cn_source.is_clean_split_jump(1 + p, tol)]
            real_moves = [(d, p) for d, p in jumps if (d, p) not in split_like]
            if split_like:
                flag = f"⚠ {len(split_like)} 处未复权拆股残留"
            elif jumps:
                flag = f"OK（{len(real_moves)} 处真实大波动，非拆股）"
            else:
                flag = "OK"
            print(f"  {s.ticker:<6} [{meta.source:<6}] {meta.start}..{meta.end} "
                  f"{meta.rows:>5} 行  {flag}")
            for d, p in split_like[:5]:
                print(f"          ⚠ 拆股残留(应复权): {d}  Δ{p:+.1%}")
            for d, p in real_moves[:5]:
                print(f"          · 真实波动(正常): {d}  Δ{p:+.1%}")
            ok += 1
        except DataError as e:
            print(f"  {s.ticker:<6} [失败] {e}")
            fail += 1

    if args.cross:
        print("\n=== 跨源复权一致性 (eastmoney vs sina) ===")
        for s in cfg.symbols:
            r = cross_provider_check(s.ticker, cfg)
            tag = "OK" if r["ok"] else "⚠"
            md = f"{r['median_div']:.2%}" if r["median_div"] is not None else "n/a"
            print(f"  {s.ticker:<6} {tag}  中位偏差 {md:<8} {r['reason']}")

    print(f"\n完成：成功 {ok} / 失败 {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
