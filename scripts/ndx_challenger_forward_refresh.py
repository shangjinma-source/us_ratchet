r"""Refresh only the frozen challenger registry's price inputs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.helpers import atomic_write_text  # noqa: E402
from data.candidate_pool import refresh_candidate_price_caches  # noqa: E402
from data.funds import get_fund_nav  # noqa: E402
from data.versioning import file_sha256, utc_now_iso  # noqa: E402


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新冻结 challenger 前向登记所需行情")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--registry-manifest", default="data/cache/research/ndx_challenger_forward_registry_v3/manifest.json")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_challenger_forward_v3/latest_refresh")
    args = parser.parse_args()
    if not args.execute:
        parser.error("add --execute to refresh frozen challenger price caches")
    registry_path = _resolve(args.registry_manifest)
    config_path = _resolve(args.config)
    state_path = _resolve(args.state)
    before = {"config": file_sha256(config_path), "state": file_sha256(state_path)}
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        item = (registry.get("artifacts") or {}).get("risk_chain_map") or {}
        baseline_item = (registry.get("artifacts") or {}).get("baseline") or {}
        risk_path = Path(str(item.get("path") or ""))
        baseline_path = Path(str(baseline_item.get("path") or ""))
        if (
            registry.get("manifest_type") != "ndx_pure_equity_challenger_forward_registry"
            or not risk_path.is_absolute() or file_sha256(risk_path) != item.get("sha256")
            or not baseline_path.is_absolute() or file_sha256(baseline_path) != baseline_item.get("sha256")
        ):
            raise ValueError("frozen challenger registry evidence mismatch")
        cfg = load_config(config_path)
        risk_map = pd.read_csv(risk_path, low_memory=False, keep_default_na=False)
        baseline = pd.read_csv(baseline_path, low_memory=False, keep_default_na=False)
        market_gate_tickers = set(str(value).upper() for value in cfg.tactical_orders.market_gate_tickers)
        tickers = sorted(
            set(risk_map["ticker"].astype(str))
            .union(baseline["ticker"].astype(str))
            .union(market_gate_tickers)
        )
        result = refresh_candidate_price_caches(cfg, tickers)
        fund_error = None
        fund_rows = 0
        fund_end = None
        fund_meta = None
        try:
            fund, fund_meta = get_fund_nav("012922", cfg, local_only=False, refresh=True)
            fund_rows = len(fund)
            fund_end = fund.index[-1].strftime("%Y-%m-%d") if len(fund) else None
            if fund_meta.errors:
                fund_error = json.dumps(fund_meta.errors, ensure_ascii=False, sort_keys=True)
        except Exception as exc:
            fund_error = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        print(f"challenger 行情刷新失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    after = {"config": file_sha256(config_path), "state": file_sha256(state_path)}
    if before != after:
        raise RuntimeError("live config/state changed during challenger price refresh")
    rows = []
    for ticker in tickers:
        detail = result["results"].get(ticker) or {}
        rows.append({
            "ticker": ticker, "source": detail.get("source"), "cached": detail.get("cached"),
            "rows": detail.get("rows"), "data_start": detail.get("start"), "data_end": detail.get("end"),
            "provider_errors": json.dumps(detail.get("provider_errors") or {}, ensure_ascii=False, sort_keys=True),
            "terminal_error": result["errors"].get(ticker),
        })
    report = pd.DataFrame(rows)
    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "price_refresh.csv"
    report.to_csv(report_path, index=False, encoding="utf-8-sig")
    payload = {
        "schema_version": 1, "manifest_type": "ndx_challenger_forward_refresh",
        "generated_at": utc_now_iso(), "requested_tickers": len(tickers),
        "successful_or_cached": int(report["terminal_error"].isna().sum()),
        "terminal_errors": int(report["terminal_error"].notna().sum()),
        "target_012922_rows": fund_rows, "target_012922_data_end": fund_end,
        "target_012922_source": getattr(fund_meta, "source", None),
        "target_012922_refresh_error": fund_error,
        "return_data_read": False, "market_cache_write_only": True,
        "live_config_changed": False, "state_changed": False, "today_advice_changed": False,
        "registry_manifest_sha256": file_sha256(registry_path),
        "artifact": {"path": report_path.as_posix(), "rows": len(report), "sha256": file_sha256(report_path)},
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"challenger 行情刷新完成 | ok={payload['successful_or_cached']}/{len(tickers)} | errors={payload['terminal_errors']} | 012922_end={fund_end}")
    return 0 if payload["terminal_errors"] == 0 and fund_error is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
