"""Refresh only the market inputs required by immutable stage-1 cohorts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_marginal_forward import NdxMarginalForwardError, read_cohort_index  # noqa: E402
from core.config import load_config  # noqa: E402
from core.helpers import atomic_write_text  # noqa: E402
from data.candidate_pool import refresh_candidate_price_caches  # noqa: E402
from data.funds import get_fund_nav  # noqa: E402
from data.versioning import file_sha256, utc_now_iso, write_dataset_manifest  # noqa: E402


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def cohort_price_tickers(index_path: Path) -> list[str]:
    tickers: set[str] = set()
    for record in read_cohort_index(index_path):
        manifest_path = Path(record["cohort_manifest_path"])
        cohort_path = manifest_path.parent / "cohort_actions.csv"
        if file_sha256(manifest_path) != record["cohort_manifest_sha256"]:
            raise NdxMarginalForwardError(f"cohort manifest changed: {manifest_path}")
        if file_sha256(cohort_path) != record["cohort_csv_sha256"]:
            raise NdxMarginalForwardError(f"cohort actions changed: {cohort_path}")
        cohort = pd.read_csv(cohort_path, low_memory=False, keep_default_na=False)
        if cohort.empty:
            continue
        tickers.update(json.loads(str(cohort.iloc[0]["incumbent_weights_json"])))
        tickers.update(str(value).strip() for value in cohort["ticker"] if str(value).strip())
    return sorted(tickers)


def main() -> int:
    parser = argparse.ArgumentParser(description="精确刷新NDX阶段1前向链所需行情")
    parser.add_argument("--execute", action="store_true", help="显式允许联网刷新版本化缓存")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_marginal_forward_v1")
    parser.add_argument("--fund", default="012922")
    args = parser.parse_args()
    if not args.execute:
        parser.error("add --execute to refresh versioned market-data caches")
    output = _resolve(args.output_dir)
    config_path = _resolve(args.config)
    state_path = _resolve(args.state)
    config_before = file_sha256(config_path)
    state_before = file_sha256(state_path)
    try:
        tickers = cohort_price_tickers(output / "cohort_index.jsonl")
        if not tickers:
            raise NdxMarginalForwardError("no immutable cohort tickers to refresh")
        cfg = load_config(config_path)
        price_result = refresh_candidate_price_caches(cfg, tickers)
        nav, nav_meta = get_fund_nav(args.fund, cfg, local_only=False, refresh=True)
    except (NdxMarginalForwardError, OSError, ValueError, KeyError) as exc:
        print(f"前向行情刷新失败: {exc}", file=sys.stderr)
        return 2
    config_after = file_sha256(config_path)
    state_after = file_sha256(state_path)
    if config_before != config_after or state_before != state_after:
        raise RuntimeError("live config or state changed during market-data refresh")
    rows = []
    for ticker in tickers:
        item = price_result["results"].get(ticker) or {}
        error = price_result["errors"].get(ticker)
        rows.append({
            "ticker": ticker,
            "source": item.get("source"),
            "network_refresh_succeeded": bool(item and not item.get("cached")),
            "cache_fallback_used": bool(item.get("cached")) if item else False,
            "rows": item.get("rows"),
            "data_start": item.get("start"),
            "data_end": item.get("end"),
            "provider_errors": json.dumps(item.get("provider_errors") or {}, ensure_ascii=False, sort_keys=True),
            "terminal_error": error,
        })
    report = pd.DataFrame(rows)
    refresh_dir = output / "latest_refresh"
    refresh_dir.mkdir(parents=True, exist_ok=True)
    report_path = refresh_dir / "price_refresh.csv"
    report.to_csv(report_path, index=False, encoding="utf-8-sig")
    write_dataset_manifest(
        report_path,
        dataset_type="ndx_marginal_forward_refresh",
        dataset_key="price_refresh",
        source="configured_price_provider_chain",
        fetched_at_evidence="refresh_runtime_utc",
        row_count=len(report),
        extra={
            "return_data_read": False,
            "market_cache_write_only": True,
            "live_config_changed": False,
            "state_changed": False,
            "today_advice_changed": False,
        },
    )
    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_marginal_forward_refresh",
        "generated_at": utc_now_iso(),
        "requested_tickers": len(tickers),
        "price_network_refresh_succeeded": int(report["network_refresh_succeeded"].sum()),
        "price_cache_fallback_count": int(report["cache_fallback_used"].sum()),
        "price_terminal_error_count": int(report["terminal_error"].notna().sum()),
        "fund": args.fund,
        "fund_source": nav_meta.source,
        "fund_network_refresh_succeeded": bool(not nav_meta.cached and not nav_meta.errors),
        "fund_refresh_errors": nav_meta.errors,
        "fund_rows": len(nav),
        "fund_data_end": nav.index[-1].strftime("%Y-%m-%d"),
        "fund_version_id": (nav_meta.manifest or {}).get("version_id"),
        "fund_content_sha256": (nav_meta.manifest or {}).get("content_sha256"),
        "config_sha256_before": config_before,
        "config_sha256_after": config_after,
        "state_sha256_before": state_before,
        "state_sha256_after": state_after,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "artifact": {
            "path": report_path.as_posix(),
            "rows": len(report),
            "sha256": file_sha256(report_path),
        },
    }
    atomic_write_text(refresh_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(
        f"前向行情刷新完成 | prices={manifest['price_network_refresh_succeeded']}/{len(tickers)} | "
        f"fallback={manifest['price_cache_fallback_count']} | errors={manifest['price_terminal_error_count']} | "
        f"012922_end={manifest['fund_data_end']} | state/config unchanged"
    )
    return 0 if manifest["price_terminal_error_count"] == 0 and not nav_meta.errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
