"""Build a resumable SEC Company Facts readiness report for NDX research."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import load_config
from core.helpers import atomic_write_text
from data.ndx_fundamentals import (
    CIK_LOOKUP_URL,
    COMPANYFACTS_URL,
    METRIC_CONCEPTS,
    build_cik_crosswalk,
    concept_inventory,
    fundamental_cache_dir,
    load_companyfacts_records,
    parse_cik_lookup,
    point_in_time_coverage,
    raw_bundle_sha256,
    selection_universe_plan,
    validate_companyfacts_payload,
)
from data.ndx_history import (
    _company_tickers_path,
    _sec_headers,
    _sec_user_agent,
    get_ndx_point_in_time_history,
)
from data.versioning import utc_now_iso, write_dataset_manifest


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_bytes(content: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _fetch_bytes(session: requests.Session, url: str, *, timeout: int = 90) -> bytes:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def _selection_dates(path: Path | None, history: pd.DataFrame) -> list[str]:
    if path and path.exists():
        frame = pd.read_csv(path, usecols=["selection_date"])
        values = sorted(set(frame["selection_date"].dropna().astype(str).str[:10]))
        if values:
            return values
    return sorted(set(history["available_date"].dropna().astype(str).str[:10]))


def _download_companyfacts(
    session: requests.Session,
    raw_dir: Path,
    ciks: list[int],
    *,
    force: bool,
    max_companies: int,
) -> list[dict]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    fetched = 0
    for position, cik in enumerate(ciks, start=1):
        path = raw_dir / f"CIK{cik:010d}.json"
        status = "cached"
        error = None
        if force or not path.exists():
            if max_companies and fetched >= max_companies:
                rows.append({
                    "cik": cik,
                    "status": "pending_limit",
                    "error": None,
                    "path": path.as_posix(),
                })
                continue
            started = time.monotonic()
            try:
                content = _fetch_bytes(session, COMPANYFACTS_URL.format(cik=cik))
                payload = json.loads(content.decode("utf-8"))
                validate_companyfacts_payload(payload, cik)
                _atomic_bytes(content, path)
                status = "fetched"
                fetched += 1
            except Exception as exc:
                status = "failed"
                error = f"{type(exc).__name__}: {exc}"
            elapsed = time.monotonic() - started
            if elapsed < 0.15:
                time.sleep(0.15 - elapsed)
        rows.append({
            "cik": cik,
            "position": position,
            "status": status,
            "error": error,
            "path": path.as_posix(),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit point-in-time SEC fundamental coverage before any NDX factor scoring."
        )
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--selection-evidence",
        default=(
            "data/cache/research/ndx_lab/ndx_012922_drawdown_hysteresis_v4d/"
            "selections.csv"
        ),
    )
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--refresh-cik-lookup", action="store_true")
    parser.add_argument(
        "--max-companies",
        type=int,
        default=0,
        help="Limit new Company Facts downloads for a smoke run; zero means all.",
    )
    args = parser.parse_args()

    cfg = load_config(_resolve(args.config))
    history, history_meta = get_ndx_point_in_time_history(cfg)
    output = _resolve(args.output_dir) if args.output_dir else fundamental_cache_dir(cfg)
    output.mkdir(parents=True, exist_ok=True)
    raw_dir = output / "raw_companyfacts"
    cik_lookup_path = output / "sec_cik_lookup_data.txt"
    ticker_path = _company_tickers_path(cfg)
    if not ticker_path.exists():
        raise FileNotFoundError(
            f"SEC ticker cache is missing; refresh NDX history first: {ticker_path}"
        )
    ticker_payload = json.loads(ticker_path.read_text(encoding="utf-8"))

    session = None
    if not args.offline and not args.plan_only:
        explicit_agent = os.environ.get("SEC_USER_AGENT")
        if not explicit_agent:
            raise ValueError(
                "Set SEC_USER_AGENT to an identifying client string with a real contact email."
            )
        agent = _sec_user_agent(explicit_agent)
        session = requests.Session()
        session.headers.update(_sec_headers(agent))
    historical_names = None
    if (
        not args.plan_only
        and not args.offline
        and (args.refresh_cik_lookup or not cik_lookup_path.exists())
    ):
        cik_lookup_content = _fetch_bytes(session, CIK_LOOKUP_URL)
        historical_names = parse_cik_lookup(cik_lookup_content.decode("latin-1"))
        _atomic_bytes(cik_lookup_content, cik_lookup_path)

    if historical_names is None and cik_lookup_path.exists():
        historical_names = parse_cik_lookup(
            cik_lookup_path.read_text(encoding="latin-1")
        )
    crosswalk = build_cik_crosswalk(
        history,
        company_ticker_payload=ticker_payload,
        historical_cik_names=historical_names,
    )
    crosswalk_path = output / "cik_crosswalk.csv"
    _atomic_csv(crosswalk, crosswalk_path)
    write_dataset_manifest(
        crosswalk_path,
        dataset_type="ndx_sec_cik_crosswalk",
        dataset_key="historical_ndx_tickers",
        source="sec_ticker_exchange_plus_historical_cik_names",
        source_locator=CIK_LOOKUP_URL,
        row_count=len(crosswalk),
        data_start=crosswalk["first_report_date"].min(),
        data_end=crosswalk["last_report_date"].max(),
        extra={
            "mapped_tickers": int(crosswalk["cik"].notna().sum()),
            "unresolved_tickers": sorted(
                crosswalk.loc[crosswalk["cik"].isna(), "ticker"].astype(str)
            ),
            "historical_cik_empty_name_rows_skipped": int(
                historical_names.attrs.get("skipped_empty_name_rows", 0)
                if historical_names is not None else 0
            ),
            "publication_time_known": False,
        },
    )
    selection_path = _resolve(args.selection_evidence) if args.selection_evidence else None
    dates = _selection_dates(selection_path, history)
    universe = selection_universe_plan(history, dates)
    plan = universe.merge(
        crosswalk[["ticker", "cik", "mapping_status", "mapping_method"]],
        on="ticker",
        how="left",
        validate="many_to_one",
    )
    plan_path = output / "plan.csv"
    _atomic_csv(plan, plan_path)

    mapped_ciks = sorted(set(crosswalk["cik"].dropna().astype(int)))
    cached_ciks = {
        int(path.stem.replace("CIK", ""))
        for path in raw_dir.glob("CIK*.json")
        if path.stem.replace("CIK", "").isdigit()
    }
    print("\nNDX point-in-time fundamental readiness plan")
    print(
        f"Historical tickers: {len(crosswalk)} | CIK mapped: "
        f"{crosswalk['cik'].notna().sum()} | unresolved: {crosswalk['cik'].isna().sum()}"
    )
    print(
        f"Selection dates: {len(dates)} | universe rows: {len(universe)} | "
        f"Company Facts cached: {len(cached_ciks)}/{len(mapped_ciks)}"
    )
    print(f"Plan: {plan_path}")
    if args.plan_only:
        if not cik_lookup_path.exists():
            print("Historical CIK lookup is not cached; unresolved legacy tickers are expected.")
        return 0
    if crosswalk["cik"].isna().any():
        unresolved = ",".join(crosswalk.loc[crosswalk["cik"].isna(), "ticker"])
        raise ValueError(
            f"CIK crosswalk remains incomplete ({unresolved}); factor coverage is not comparable."
        )

    download_rows = []
    if args.offline:
        download_rows = [
            {
                "cik": cik,
                "status": "cached" if cik in cached_ciks else "missing_offline",
                "error": None,
                "path": (raw_dir / f"CIK{cik:010d}.json").as_posix(),
            }
            for cik in mapped_ciks
        ]
    else:
        download_rows = _download_companyfacts(
            session,
            raw_dir,
            mapped_ciks,
            force=bool(args.force),
            max_companies=max(0, int(args.max_companies)),
        )
    download_status = pd.DataFrame(download_rows)
    _atomic_csv(download_status, output / "download_status.csv")

    records, raw_index = load_companyfacts_records(raw_dir, mapped_ciks)
    if raw_index.empty:
        raise ValueError("No valid Company Facts payloads are cached")
    raw_index_path = output / "raw_index.csv"
    records_path = output / "fact_availability.csv"
    inventory_path = output / "concept_inventory.csv"
    _atomic_csv(raw_index, raw_index_path)
    _atomic_csv(records, records_path)
    inventory = concept_inventory(records)
    _atomic_csv(inventory, inventory_path)
    detail, coverage = point_in_time_coverage(universe, crosswalk, records)
    detail_path = output / "coverage_detail.csv"
    coverage_path = output / "coverage_summary.csv"
    _atomic_csv(detail, detail_path)
    _atomic_csv(coverage, coverage_path)

    bundle_hash = raw_bundle_sha256(raw_index)
    common_extra = {
        "raw_bundle_sha256": bundle_hash,
        "company_count": len(raw_index),
        "mapped_cik_count": len(mapped_ciks),
        "history_version_id": history_meta.to_dict().get("version_id"),
        "publication_time_known": True,
        "availability_policy": "filed_date_plus_one_calendar_day",
        "future_data_guard": "available_date <= selection_date and period_end < selection_date",
        "scoring_allowed": False,
    }
    for path, dataset_type, row_count in (
        (raw_index_path, "sec_companyfacts_raw_index", len(raw_index)),
        (records_path, "sec_companyfacts_fact_availability", len(records)),
        (inventory_path, "sec_companyfacts_concept_inventory", len(inventory)),
        (detail_path, "ndx_fundamental_coverage_detail", len(detail)),
        (coverage_path, "ndx_fundamental_coverage_summary", len(coverage)),
    ):
        write_dataset_manifest(
            path,
            dataset_type=dataset_type,
            dataset_key="historical_ndx_companyfacts_readiness",
            source="sec_companyfacts_api",
            source_locator="https://data.sec.gov/api/xbrl/companyfacts/",
            row_count=row_count,
            data_start=min(dates) if dates else None,
            data_end=max(dates) if dates else None,
            extra=common_extra,
        )

    workbook = output / "ndx_fundamental_readiness.xlsx"
    temporary = workbook.with_name(workbook.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            crosswalk.to_excel(writer, sheet_name="cik_crosswalk", index=False)
            download_status.to_excel(writer, sheet_name="download_status", index=False)
            coverage.to_excel(writer, sheet_name="coverage_summary", index=False)
            detail.to_excel(writer, sheet_name="coverage_detail", index=False)
            inventory.to_excel(writer, sheet_name="concept_inventory", index=False)
        os.replace(temporary, workbook)
    finally:
        if temporary.exists():
            temporary.unlink()
    payload = {
        "generated_at": utc_now_iso(),
        "research_only": True,
        "scoring_allowed": False,
        "historical_tickers": len(crosswalk),
        "mapped_tickers": int(crosswalk["cik"].notna().sum()),
        "mapped_ciks": len(mapped_ciks),
        "cached_companyfacts": len(raw_index),
        "selection_dates": len(dates),
        "metrics": list(METRIC_CONCEPTS),
        "raw_bundle_sha256": bundle_hash,
        "minimum_coverage_by_metric": {
            metric: float(frame["coverage"].min())
            for metric, frame in coverage.groupby("metric")
        },
        "future_data_guard_passed": bool(coverage["future_data_guard_passed"].all()),
        "files": {
            "crosswalk": crosswalk_path.name,
            "plan": plan_path.name,
            "download_status": "download_status.csv",
            "raw_index": raw_index_path.name,
            "fact_availability": records_path.name,
            "concept_inventory": inventory_path.name,
            "coverage_detail": detail_path.name,
            "coverage_summary": coverage_path.name,
            "workbook": workbook.name,
        },
    }
    atomic_write_text(
        output / "readiness_summary.json",
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    print(
        f"Company Facts ready: {len(raw_index)}/{len(mapped_ciks)} CIKs | "
        f"fact rows: {len(records)} | coverage rows: {len(detail)}"
    )
    print(f"Workbook: {workbook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
