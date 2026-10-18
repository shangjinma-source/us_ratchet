"""Refresh current NDX/QQQ sources and build the security candidate registry.

PowerShell / PyCharm terminal examples:
    python scripts/candidate_pool_refresh.py
    python scripts/candidate_pool_refresh.py --local-only
    python scripts/candidate_pool_refresh.py --qqq-csv "C:\\path\\QQQHoldings.csv"
    python scripts/candidate_pool_refresh.py --qqq-csv "C:\\path\\QQQHoldings.csv" --qqq-as-of 2026-07-09
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import load_config
from data.candidate_pool import (
    build_current_candidate_registry,
    get_nasdaq_100_snapshot,
    import_invesco_qqq_export,
    refresh_candidate_price_caches,
    refresh_nasdaq_100_snapshot,
    save_security_candidate_registry,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="刷新当前 NDX/QQQ 候选池；只允许当前截面研究，不运行历史回测。"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="不联网，只读取已通过 manifest 校验的当前快照",
    )
    parser.add_argument(
        "--qqq-csv",
        default="",
        help="Invesco QQQ 官方 Export data 文件；不接受第三方持仓表",
    )
    parser.add_argument(
        "--qqq-as-of",
        default="",
        help="仅当官方导出文件未内嵌日期时，填写 Invesco 页面显示的 YYYY-MM-DD",
    )
    parser.add_argument(
        "--refresh-prices",
        action="store_true",
        help="通过现有 provider 链刷新目标产业层价格；仍不运行当前成分历史回测",
    )
    parser.add_argument("--json", action="store_true", help="输出完整 registry JSON")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.local_only:
        _, ndx_meta = get_nasdaq_100_snapshot(cfg)
    else:
        _, ndx_meta = refresh_nasdaq_100_snapshot(cfg)

    qqq_meta = None
    if args.qqq_csv:
        _, qqq_meta = import_invesco_qqq_export(
            cfg,
            args.qqq_csv,
            as_of_date=(args.qqq_as_of or None),
        )

    registry = build_current_candidate_registry(cfg)
    price_refresh = None
    if args.refresh_prices:
        target_tickers = [
            row["ticker"] for row in registry.get("candidates", [])
            if "strategy_target_pool" in (row.get("scopes") or [])
        ]
        price_refresh = refresh_candidate_price_caches(cfg, target_tickers)
        registry = build_current_candidate_registry(cfg)
    registry_manifest = save_security_candidate_registry(cfg, registry)
    if args.json:
        print(json.dumps(registry, ensure_ascii=False, indent=2))
        return 0

    summary = registry["summary"]
    print("\n当前证券候选池（research only）")
    print(
        f"NDX {summary['ndx_current_securities']} 个证券 | "
        f"策略目标层 {summary['strategy_target_pool']} | "
        f"当前截面数据就绪 {summary['current_screen_ready']}"
    )
    print(
        f"当前快照可历史回测 {summary['historical_backtest_ready']} | "
        f"实盘就绪 {summary['live_ready']} | 今日建议不变"
    )
    print(
        f"价格参考日 {summary.get('market_reference_date') or '-'} | "
        f"允许最多滞后 {summary.get('max_price_lag_business_days')} 个工作日"
    )
    print(
        f"NDX as-of {ndx_meta.as_of_date} | {ndx_meta.manifest.get('version_id')}"
        + (" | 使用完整旧快照（本次刷新失败）" if ndx_meta.stale else "")
    )
    if qqq_meta:
        print(f"QQQ as-of {qqq_meta.as_of_date} | {qqq_meta.manifest.get('version_id')}")
    elif registry.get("source_errors", {}).get("qqq"):
        print("QQQ 权重：无已验证官方导出快照，保持未知，不补猜。")
    if price_refresh is not None:
        print(
            f"价格刷新：{len(price_refresh['results'])} 个返回，"
            f"{len(price_refresh['errors'])} 个失败；最终是否就绪以 registry 新鲜度为准。"
        )
        if price_refresh["errors"]:
            print("价格失败: " + ", ".join(sorted(price_refresh["errors"])))
    print(f"Registry: {registry['registry_id']} | {registry_manifest.get('version_id')}")
    print("守门：当前快照只用于今日截面；历史竞争必须读取独立 SEC 点时成分数据集。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
