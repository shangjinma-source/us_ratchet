"""Point-in-time competition among Nasdaq-100 individual securities.

PowerShell / PyCharm example:
    python scripts/ndx_competition.py --lookback-years 3 --step-months 1
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

from backtest.ndx_competition import run_ndx_competition_research
from core.config import load_config
from core.helpers import atomic_write_text, setup_logging
from data.candidate_pool import get_nasdaq_100_snapshot, refresh_candidate_price_caches
from data.ndx_history import get_ndx_point_in_time_history


def _pct(value, digits=1):
    return "-" if value is None else f"{float(value) * 100:.{digits}f}%"


def _num(value, digits=2):
    return "-" if value is None else f"{float(value):.{digits}f}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="纳指100成分股点时竞争回测（默认主目标012922，QQQ为辅助参照）"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--monthly", type=float, default=3000.0)
    parser.add_argument("--total-cap", type=float, default=37000.0)
    parser.add_argument("--target", default="012922")
    parser.add_argument("--start", default="", help="研究区间起点 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="研究区间终点 YYYY-MM-DD")
    parser.add_argument("--min-years", type=float, default=1.5)
    parser.add_argument("--lookback-years", type=float, default=3.0)
    parser.add_argument("--min-history-years", type=float, default=0.5)
    parser.add_argument("--top-ns", default="4,6,8,10")
    parser.add_argument(
        "--weight-modes",
        default="equal,inverse_vol,risk_parity,score_risk,source_weight",
    )
    parser.add_argument("--safe-weights", default="0,0.26")
    parser.add_argument("--rebalance-months", default="6,12")
    parser.add_argument("--max-weights", default="0.25,0.35")
    parser.add_argument("--trade-cost-bps", type=float, default=10.0)
    parser.add_argument("--safe-annual", type=float, default=0.04)
    parser.add_argument("--step-months", type=int, default=1)
    parser.add_argument("--max-windows", type=int, default=0)
    parser.add_argument("--local-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--refresh-history",
        action="store_true",
        help="显式联网刷新 QQQ SEC N-PORT 点时成分历史",
    )
    parser.add_argument(
        "--refresh-prices",
        action="store_true",
        help="显式联网刷新历史/当前成分并集行情缓存",
    )
    parser.add_argument("--include-samples", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--output",
        default="data/cache/research/ndx_competition_latest.json",
        help="完整JSON结果路径；传空字符串可关闭落盘",
    )
    args = parser.parse_args()

    setup_logging(logging.ERROR)
    cfg = load_config(args.config)
    if args.refresh_history:
        _, history_meta = get_ndx_point_in_time_history(cfg, refresh=True)
        if history_meta.stale or history_meta.errors:
            raise SystemExit(
                "SEC点时成分刷新失败，保留旧缓存: "
                + json.dumps(history_meta.errors, ensure_ascii=False)
            )
    if args.refresh_prices:
        history, _ = get_ndx_point_in_time_history(cfg)
        current, _ = get_nasdaq_100_snapshot(cfg)
        tickers = sorted(
            set(history["ticker"].astype(str).str.upper())
            | set(current["ticker"].astype(str).str.upper())
            | {symbol.ticker for symbol in cfg.symbols}
        )
        refreshed = refresh_candidate_price_caches(cfg, tickers)
        if refreshed["errors"]:
            raise SystemExit(
                "历史竞争池行情刷新不完整: "
                + ", ".join(sorted(refreshed["errors"]))
            )
    if args.start:
        cfg.data.start_date = args.start
    if args.end:
        cfg.data.end_date = args.end
    result = run_ndx_competition_research(
        cfg,
        total_cap=args.total_cap,
        monthly=args.monthly,
        target_benchmark=args.target,
        min_years=args.min_years,
        lookback_years=args.lookback_years,
        min_history_years=args.min_history_years,
        top_ns=args.top_ns,
        weight_modes=args.weight_modes,
        safe_weights=args.safe_weights,
        rebalance_months=args.rebalance_months,
        max_weights=args.max_weights,
        trade_cost_bps=args.trade_cost_bps,
        safe_annual=args.safe_annual,
        step_months=args.step_months,
        max_windows=args.max_windows,
        local_only=args.local_only,
        include_samples=args.include_samples,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = ROOT / output
        atomic_write_text(output, payload + "\n")

    if args.json:
        print(payload)
        return 0

    summary = result["summary"]
    print("\n纳指100成分股点时竞争回测（research only）")
    print(
        f"证券角色: NDX个股参与竞争，主目标 {summary['target_benchmark']}，"
        f"QQQ仅辅助参照 | "
        f"lookback {summary['lookback_years']:.1f}年 | 起点 {summary['start_count']}"
    )
    print(
        f"历史成分: {result['history_coverage']['report_count']}期 | "
        f"{result['history_coverage']['first_available_date']}.."
        f"{result['history_coverage']['last_available_date']} | "
        f"未来数据守门: {result['data_manifest']['future_data_guard']}"
    )
    print(
        f"{'组合':<26}{'上限':>7}{'W':>7}{'调仓':>7}{'窗口':>7}"
        f"{'胜率':>8}{'超额P50':>11}{'QQQ超额':>10}{'DD改善P50':>13}{'准入':>8}"
    )
    for row in result["rows"][:25]:
        print(
            f"{row['basket']:<26}{_pct(row.get('max_weight'), 0):>7}"
            f"{_pct(row.get('safe_weight'), 0):>7}{int(row['rebalance_months']):>7}"
            f"{int(row.get('windows') or 0):>7}{_pct(row.get('win_rate'), 0):>8}"
            f"{_pct(row.get('excess_p50'), 2):>11}{_pct(row.get('qqq_excess_p50'), 2):>10}"
            f"{_pct(row.get('dd_relief_p50'), 1):>13}"
            f"{('通过' if row.get('admission_passed') else '阻断'):>8}"
        )

    print("\n当前横截面")
    current = (
        result.get("current_selection_best_qqq")
        or result.get("current_selection")
        or {}
    )
    if not current.get("available"):
        print("没有可核验的当前权重；未猜测持仓。")
    else:
        holdings = ", ".join(
            f"{item['ticker']} {_pct(item['portfolio_weight'], 1)}"
            for item in current.get("holdings", [])
        )
        print(
            f"最接近QQQ的失败形态之当前横截面: {holdings}; "
            f"安全腿 {_pct(current.get('safe_weight'), 0)}"
        )
        print(
            f"发行人 {current.get('issuer_count')} / 证券 {current.get('security_count')}，"
            f"单发行人上限 {_pct(current.get('max_weight'), 0)}。"
        )
    print("结论仅进入研究台账，不写config/state，不改变今日建议。")
    if args.output:
        print(f"完整结果: {Path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
