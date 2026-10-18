r"""Fetch a purpose-locked nominal-price bundle for whole-lot runner execution."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import atomic_write_text
from data.ndx_execution_price import execution_cache_path, write_execution_cache
from data.ndx_price_basis import fetch_unadjusted_bars
from data.versioning import file_sha256, manifest_path


INCUMBENT = ["NVDA", "TXN", "ASML", "CDNS", "TSM", "MU", "MSFT", "GOOG"]


def _with_control_tickers(
    tickers: list[str],
    *,
    include_incumbent_controls: bool,
    include_lifecycle_controls: bool,
) -> list[str]:
    result = set(tickers)
    if include_incumbent_controls:
        result.update(INCUMBENT)
    if include_lifecycle_controls:
        result.update({"FISV", "FI"})
    return sorted(result)


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _verified_reuse_rows(manifest_value: str, *, requested_end: str) -> dict[str, dict]:
    if not manifest_value:
        return {}
    bundle_path = _resolve(manifest_value)
    manifest = json.loads(bundle_path.read_text(encoding="utf-8"))
    artifact = (manifest.get("artifacts") or {}).get("inventory") or {}
    inventory_path = Path(str(artifact.get("path") or ""))
    if (
        manifest.get("manifest_type") != "ndx_cardinality_whole_lot_execution_price_bundle"
        or manifest.get("status") != "READY"
        or manifest.get("whole_lot_execution_use_only") is not True
        or manifest.get("return_engine_cache_modified") is not False
        or str(manifest.get("requested_end")) != requested_end
        or not inventory_path.is_absolute()
        or not inventory_path.exists()
        or file_sha256(inventory_path) != artifact.get("sha256")
    ):
        raise ValueError("reusable execution price bundle contract mismatch")
    inventory = pd.read_csv(inventory_path, low_memory=False)
    if (
        len(inventory) != int(artifact.get("rows") or -1)
        or inventory["ticker"].duplicated().any()
    ):
        raise ValueError("reusable execution price inventory mismatch")
    result: dict[str, dict] = {}
    for row in inventory.to_dict("records"):
        ticker = str(row["ticker"])
        data_path = Path(str(row.get("path") or ""))
        sidecar_path = Path(str(row.get("sidecar_path") or ""))
        if (
            str(row.get("status")) != "FETCHED"
            or not data_path.is_absolute()
            or not sidecar_path.is_absolute()
            or not data_path.exists()
            or not sidecar_path.exists()
            or file_sha256(data_path) != str(row.get("sha256"))
            or file_sha256(sidecar_path) != str(row.get("sidecar_sha256"))
        ):
            raise ValueError(f"reusable execution price artifact mismatch: {ticker}")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        if (
            sidecar.get("dataset_key") != ticker
            or sidecar.get("price_basis") != "unadjusted_nominal_trade_price"
            or sidecar.get("whole_lot_execution_use_only") is not True
            or sidecar.get("return_usage_allowed") is not False
            or sidecar.get("content_sha256") != file_sha256(data_path)
            or int(sidecar.get("row_count") or -1) != int(row.get("rows") or -2)
            or str(sidecar.get("requested_end")) != requested_end
        ):
            raise ValueError(f"reusable execution price sidecar mismatch: {ticker}")
        reused = dict(row)
        reused["source_mode"] = f"verified_reuse:{row.get('source_mode')}"
        reused["reused_from_bundle"] = bundle_path.as_posix()
        result[ticker] = reused
    return result


def run(args) -> dict:
    selection = pd.Timestamp(args.selection_date).normalize()
    discovery = json.loads(_resolve(args.discovery_manifest).read_text(encoding="utf-8"))
    readiness = json.loads(_resolve(args.input_readiness_manifest).read_text(encoding="utf-8"))
    members_path = Path(discovery["artifacts"]["eligible_securities"]["path"])
    audit_path = Path(readiness["artifacts"]["membership_readiness"]["path"])
    if file_sha256(members_path) != discovery["artifacts"]["eligible_securities"]["sha256"]:
        raise ValueError("eligible security hash mismatch")
    if file_sha256(audit_path) != readiness["artifacts"]["membership_readiness"]["sha256"]:
        raise ValueError("membership readiness hash mismatch")
    members = pd.read_csv(members_path, low_memory=False)
    audit = pd.read_csv(audit_path, low_memory=False)
    ready = audit.loc[audit["input_ready"].astype(bool)].copy()
    if args.all_ready_coordinates:
        selection = pd.to_datetime(ready["selection_date"]).max().normalize()
        ready_ids = set(ready["security_id"].astype(str))
        tickers = sorted(set(members.loc[
            members["security_id"].astype(str).isin(ready_ids), "ticker"
        ].astype(str)))
        coordinate_scope = "ALL_DEGRADED_READY_COORDINATES"
        manifest_track = "ALL"
    else:
        ready_ids = set(ready.loc[
            ready["universe_track"].eq(args.track)
            & ready["selection_date"].eq(selection.date().isoformat()),
            "security_id",
        ].astype(str))
        tickers = sorted(set(members.loc[
            members["universe_track"].eq(args.track)
            & members["selection_date"].eq(selection.date().isoformat())
            & members["security_id"].astype(str).isin(ready_ids),
            "ticker",
        ].astype(str)))
        coordinate_scope = "SINGLE_COORDINATE"
        manifest_track = args.track
    requested_end = (selection - pd.Timedelta(days=1)).date().isoformat()
    tickers = _with_control_tickers(
        tickers,
        include_incumbent_controls=bool(args.include_incumbent_controls),
        include_lifecycle_controls=bool(args.include_lifecycle_controls),
    )
    output = _resolve(args.output_dir)
    reusable_rows = _verified_reuse_rows(
        args.reuse_bundle_manifest,
        requested_end=requested_end,
    )
    inventory_rows = []
    failures = []
    reused_count = fetched_count = 0
    for ticker in tickers:
        row = {"ticker": ticker, "status": "PLAN_ONLY", "error": ""}
        if args.execute:
            try:
                if ticker in reusable_rows:
                    row = reusable_rows[ticker]
                    reused_count += 1
                else:
                    bars, source_mode, source_errors = fetch_unadjusted_bars(
                        ticker, begin=args.begin, end=requested_end,
                    )
                    sidecar = write_execution_cache(
                        output, ticker, bars, source_mode=source_mode,
                        requested_begin=args.begin, requested_end=requested_end,
                    )
                    path = execution_cache_path(output, ticker)
                    row.update({
                        "status": "FETCHED", "rows": len(bars),
                        "data_start": bars.index.min().date().isoformat(),
                        "data_end": bars.index.max().date().isoformat(),
                        "path": path.as_posix(), "sha256": file_sha256(path),
                        "sidecar_path": manifest_path(path).as_posix(),
                        "sidecar_sha256": file_sha256(manifest_path(path)),
                        "source_mode": source_mode,
                        "source_errors": json.dumps(source_errors, sort_keys=True),
                        "purpose": sidecar["whole_lot_execution_use_only"],
                        "reused_from_bundle": "",
                    })
                    fetched_count += 1
            except Exception as exc:
                row.update({"status": "FAILED", "error": f"{type(exc).__name__}:{exc}"})
                failures.append(row.copy())
        inventory_rows.append(row)
    inventory = pd.DataFrame(inventory_rows)
    output.mkdir(parents=True, exist_ok=True)
    inventory_path = output / "execution_price_inventory.csv"
    _atomic_csv(inventory, inventory_path)
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_whole_lot_execution_price_bundle",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "READY" if args.execute and not failures else "PLAN_ONLY" if not args.execute else "FAILED",
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "universe_track": manifest_track,
        "coordinate_scope": coordinate_scope,
        "selection_date": selection.date().isoformat(),
        "requested_end": requested_end,
        "ticker_count": len(tickers),
        "reused_ticker_count": reused_count,
        "network_fetched_ticker_count": fetched_count,
        "failure_count": len(failures),
        "whole_lot_execution_use_only": True,
        "return_data_read": False,
        "return_engine_cache_modified": False,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "inputs": {
            "reuse_bundle_manifest": {
                "path": (
                    _resolve(args.reuse_bundle_manifest).as_posix()
                    if args.reuse_bundle_manifest else ""
                ),
                "sha256": (
                    file_sha256(_resolve(args.reuse_bundle_manifest))
                    if args.reuse_bundle_manifest else ""
                ),
            },
        },
        "artifacts": {
            "inventory": {"path": inventory_path.as_posix(), "rows": len(inventory), "sha256": file_sha256(inventory_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="整股执行专用未复权名义价格刷新")
    parser.add_argument("--track", default="strict_technology")
    parser.add_argument("--selection-date", default="2024-06-03")
    parser.add_argument("--begin", default="2020-01-01")
    parser.add_argument("--include-lifecycle-controls", action="store_true")
    parser.add_argument("--include-incumbent-controls", action="store_true")
    parser.add_argument("--reuse-bundle-manifest", default="")
    parser.add_argument("--all-ready-coordinates", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--discovery-manifest", default="data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json")
    parser.add_argument("--input-readiness-manifest", default="data/cache/research/ndx_variable_cardinality_input_readiness_v1/manifest.json")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_cardinality_execution_prices_20240603_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"整股执行名义价格刷新失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        "整股执行名义价格刷新完成 | "
        f"status={payload['status']} | tickers={payload['ticker_count']} | "
        f"failed={payload['failure_count']} | promotion_allowed=False"
    )
    return 0 if payload["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
