"""Register the v11 fresh forward observation and optionally fetch SEC facts.

PowerShell / PyCharm terminal:
    python -B scripts\ndx_v11_forward_watch.py --plan-only --observation-date 2026-07-13
    python -B scripts\ndx_v11_forward_watch.py --smoke --observation-date 2026-07-13
    $env:SEC_USER_AGENT="us_ratchet/1.0 your-real-email@example.com"
    python -B scripts\ndx_v11_forward_watch.py --fetch-companyfacts --resume --observation-date 2026-07-13

The SEC mode only builds a current Company Facts evidence bundle.  It does
not normalize factors, score securities, read returns, run a backtest, or
change live configuration/state/today advice.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_forward_watch import (  # noqa: E402
    NdxForwardWatchError,
    build_bundle,
    build_sec_companyfacts_plan,
)
from core.config import load_config  # noqa: E402
from data.ndx_fundamentals import (  # noqa: E402
    COMPANYFACTS_URL,
    concept_inventory,
    load_companyfacts_records,
    point_in_time_coverage,
    raw_bundle_sha256,
    validate_companyfacts_payload,
)
from data.ndx_history import _sec_headers, _sec_user_agent  # noqa: E402
from data.versioning import (  # noqa: E402
    file_sha256,
    manifest_path,
    utc_now_iso,
    write_dataset_manifest,
)


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
    temporary.replace(path)


def _write_frame_manifest(
    frame: pd.DataFrame,
    path: Path,
    *,
    dataset_type: str,
    dataset_key: str,
    observation_date: str,
) -> dict:
    _atomic_csv(frame, path)
    return write_dataset_manifest(
        path,
        dataset_type=dataset_type,
        dataset_key=dataset_key,
        source="derived_from_sec_companyfacts_api",
        source_locator="https://data.sec.gov/api/xbrl/companyfacts/",
        fetched_at_evidence="derived_runtime_utc",
        row_count=len(frame),
        data_start=observation_date,
        data_end=observation_date,
        extra={
            "research_only": True,
            "observation_date": observation_date,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
            "scoring_allowed": False,
            "live_config_mutation_allowed": False,
            "today_advice_impact": "none",
        },
    )


def _download_companyfacts(
    plan: pd.DataFrame,
    *,
    output_dir: Path,
    observation_date: str,
    resume: bool,
    force: bool,
    max_companies: int,
) -> pd.DataFrame:
    explicit_agent = os.environ.get("SEC_USER_AGENT")
    if not explicit_agent:
        raise NdxForwardWatchError(
            "Set SEC_USER_AGENT to an identifying client string with a real contact email."
        )
    agent = _sec_user_agent(explicit_agent)
    session = requests.Session()
    session.headers.update(_sec_headers(agent))
    raw_dir = output_dir / "raw_companyfacts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    ciks = sorted({int(value) for value in plan.loc[plan["cik"].ne(""), "cik"]})
    rows = []
    fetched_new = 0
    for position, cik in enumerate(ciks, start=1):
        raw_path = raw_dir / f"CIK{cik:010d}.json"
        status = "cached" if raw_path.exists() else "missing"
        error = ""
        should_fetch = bool(force or not raw_path.exists() or not resume)
        if should_fetch:
            if max_companies and fetched_new >= max_companies:
                status = "pending_limit"
            else:
                started = time.monotonic()
                try:
                    response = session.get(
                        COMPANYFACTS_URL.format(cik=cik),
                        timeout=90,
                    )
                    response.raise_for_status()
                    content = response.content
                    payload = json.loads(content.decode("utf-8"))
                    validate_companyfacts_payload(payload, cik)
                    _atomic_bytes(raw_path, content)
                    write_dataset_manifest(
                        raw_path,
                        dataset_type="ndx_v11_forward_companyfacts_raw",
                        dataset_key=f"CIK{cik:010d}",
                        source="sec_companyfacts_api",
                        source_locator=COMPANYFACTS_URL.format(cik=cik),
                        fetched_at_evidence="runtime_fetch_utc",
                        row_count=1,
                        data_start=observation_date,
                        data_end=observation_date,
                        extra={
                            "observation_date": observation_date,
                            "research_only": True,
                            "return_data_read": False,
                            "price_data_used": False,
                            "backtest_results_used": False,
                            "scoring_allowed": False,
                        },
                    )
                    status = "fetched"
                    fetched_new += 1
                except Exception as exc:  # pragma: no cover - network branch
                    status = "failed"
                    error = f"{type(exc).__name__}: {exc}"
                elapsed = time.monotonic() - started
                if elapsed < 0.15:
                    time.sleep(0.15 - elapsed)
        rows.append({
            "position": position,
            "cik": f"{cik:010d}",
            "status": status,
            "error": error,
            "raw_path": raw_path.as_posix(),
            "observation_date": observation_date,
        })
    return pd.DataFrame(rows)


def _write_companyfacts_bundle(
    plan: pd.DataFrame,
    download_status: pd.DataFrame,
    *,
    output_dir: Path,
    observation_date: str,
) -> dict:
    raw_dir = output_dir / "raw_companyfacts"
    ciks = sorted({int(value) for value in plan.loc[plan["cik"].ne(""), "cik"]})
    records, raw_index = load_companyfacts_records(raw_dir, ciks)
    raw_index_path = output_dir / "raw_index.csv"
    records_path = output_dir / "fact_availability.csv"
    inventory_path = output_dir / "concept_inventory.csv"
    status_path = output_dir / "download_status.csv"
    _write_frame_manifest(
        download_status,
        status_path,
        dataset_type="ndx_v11_forward_companyfacts",
        dataset_key="download_status",
        observation_date=observation_date,
    )
    raw_index_manifest = _write_frame_manifest(
        raw_index,
        raw_index_path,
        dataset_type="ndx_v11_forward_companyfacts",
        dataset_key="raw_index",
        observation_date=observation_date,
    )
    _write_frame_manifest(
        records,
        records_path,
        dataset_type="ndx_v11_forward_companyfacts",
        dataset_key="fact_availability",
        observation_date=observation_date,
    )
    inventory = concept_inventory(records)
    _write_frame_manifest(
        inventory,
        inventory_path,
        dataset_type="ndx_v11_forward_companyfacts",
        dataset_key="concept_inventory",
        observation_date=observation_date,
    )

    mapped = plan[plan["cik"].ne("")].copy()
    mapped["selection_date"] = observation_date
    mapped["report_date"] = mapped["observation_date"]
    mapped["membership_available_date"] = mapped["observation_date"]
    crosswalk = mapped[["ticker", "cik"]].copy()
    crosswalk["cik"] = pd.to_numeric(crosswalk["cik"], errors="coerce")
    crosswalk["mapping_status"] = "mapped"
    crosswalk["mapping_method"] = "sec_current_ticker_crosswalk"
    detail, coverage = point_in_time_coverage(mapped, crosswalk, records)
    detail_path = output_dir / "coverage_detail.csv"
    coverage_path = output_dir / "coverage_summary.csv"
    _write_frame_manifest(
        detail,
        detail_path,
        dataset_type="ndx_v11_forward_companyfacts",
        dataset_key="coverage_detail",
        observation_date=observation_date,
    )
    coverage_manifest = _write_frame_manifest(
        coverage,
        coverage_path,
        dataset_type="ndx_v11_forward_companyfacts",
        dataset_key="coverage_summary",
        observation_date=observation_date,
    )

    chinese = {
        "下载状态": download_status.rename(columns={
            "position": "顺序", "cik": "SEC CIK", "status": "状态",
            "error": "错误", "raw_path": "原始文件", "observation_date": "观察日期",
        }),
        "事实覆盖": coverage.rename(columns={
            "selection_date": "观察日期", "metric": "指标", "universe_count": "证券数",
            "cik_mapped_count": "CIK已映射数", "available_count": "可用数",
            "coverage": "覆盖率", "future_data_guard_passed": "未来数据守门通过",
        }),
        "事实明细": detail.rename(columns={
            "selection_date": "观察日期", "ticker": "股票代码", "cik": "SEC CIK",
            "metric": "指标", "available": "可用", "latest_fact_available_date": "事实可用日",
            "latest_period_end": "事实期末", "future_data_guard_passed": "未来数据守门通过",
        }),
        "概念库存": inventory.rename(columns={
            "cik": "SEC CIK", "entity_name": "发行人名称", "metric": "指标",
            "concept": "XBRL概念", "record_count": "记录数",
            "first_available_date": "最早可用日", "last_available_date": "最后可用日",
        }),
    }
    workbook = output_dir / "ndx_v11_forward_companyfacts.xlsx"
    temporary = workbook.with_name(workbook.stem + ".tmp.xlsx")
    with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
        for sheet, frame in chinese.items():
            frame.to_excel(writer, sheet_name=sheet, index=False)
    temporary.replace(workbook)
    workbook_manifest = write_dataset_manifest(
        workbook,
        dataset_type="ndx_v11_forward_companyfacts_workbook",
        dataset_key="companyfacts",
        source="derived_from_sec_companyfacts_api",
        fetched_at_evidence="derived_runtime_utc",
        row_count=len(records),
        data_start=observation_date,
        data_end=observation_date,
        extra={
            "observation_date": observation_date,
            "research_only": True,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
            "scoring_allowed": False,
        },
    )
    summary = {
        "schema_version": 1,
        "manifest_type": "ndx_v11_forward_companyfacts_bundle",
        "generated_at": utc_now_iso(),
        "observation_date": observation_date,
        "research_only": True,
        "return_data_read": False,
        "price_data_used": False,
        "backtest_results_used": False,
        "scoring_allowed": False,
        "raw_company_count": len(raw_index),
        "requested_cik_count": len(ciks),
        "fact_rows": len(records),
        "coverage_rows": len(coverage),
        "raw_bundle_sha256": raw_bundle_sha256(raw_index) if not raw_index.empty else None,
        "download_status_counts": download_status["status"].value_counts().to_dict() if not download_status.empty else {},
        "future_data_guard_passed": bool(coverage["future_data_guard_passed"].all()) if not coverage.empty else False,
        "artifacts": {
            "download_status": {"path": status_path.name, "sha256": file_sha256(status_path)},
            "raw_index": {"path": raw_index_path.name, "sha256": raw_index_manifest["content_sha256"]},
            "fact_availability": {"path": records_path.name, "sha256": file_sha256(records_path)},
            "concept_inventory": {"path": inventory_path.name, "sha256": file_sha256(inventory_path)},
            "coverage_detail": {"path": detail_path.name, "sha256": file_sha256(detail_path)},
            "coverage_summary": {"path": coverage_path.name, "sha256": coverage_manifest["content_sha256"]},
            "workbook": {"path": workbook.name, "sha256": workbook_manifest["content_sha256"]},
        },
    }
    summary_path = output_dir / "companyfacts_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_manifest = write_dataset_manifest(
        summary_path,
        dataset_type="ndx_v11_forward_companyfacts_summary",
        dataset_key="companyfacts_summary",
        source="derived_from_sec_companyfacts_api",
        fetched_at_evidence="derived_runtime_utc",
        row_count=1,
        data_start=observation_date,
        data_end=observation_date,
        extra={
            "observation_date": observation_date,
            "research_only": True,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
            "scoring_allowed": False,
        },
    )
    summary["summary_manifest_sha256"] = summary_manifest["content_sha256"]
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Register NDX v11 fresh forward observation without scoring or backtesting")
    parser.add_argument("--spec", default="config/ndx_v11_forward_watch.yaml")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_v11_forward_watch_v1")
    parser.add_argument("--observation-date", required=True, help="fresh point-in-time observation date, e.g. 2026-07-13")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument("--fetch-companyfacts", action="store_true")
    parser.add_argument("--resume", action="store_true", help="reuse successfully fetched SEC Company Facts JSON")
    parser.add_argument("--force", action="store_true", help="refetch existing SEC Company Facts JSON")
    parser.add_argument("--max-companies", type=int, default=0, help="limit new CIK downloads; zero means all")
    args = parser.parse_args()

    try:
        output = _resolve(args.output_dir)
        if args.smoke and args.output_dir == "data/cache/research/ndx_v11_forward_watch_v1":
            output = output / "smoke"
        if args.fetch_companyfacts:
            plan, plan_audit = build_sec_companyfacts_plan(
                spec_path=_resolve(args.spec),
                output_dir=output,
                observation_date=args.observation_date,
            )
            plan_manifest = _write_frame_manifest(
                plan,
                output / "companyfacts_plan.csv",
                dataset_type="ndx_v11_forward_companyfacts",
                dataset_key="companyfacts_plan",
                observation_date=args.observation_date,
            )
            status = _download_companyfacts(
                plan,
                output_dir=output,
                observation_date=args.observation_date,
                resume=bool(args.resume),
                force=bool(args.force),
                max_companies=max(0, int(args.max_companies)),
            )
            summary = _write_companyfacts_bundle(
                plan,
                status,
                output_dir=output,
                observation_date=args.observation_date,
            )
            manifest = build_bundle(
                spec_path=_resolve(args.spec),
                live_config_path=_resolve(args.config),
                output_dir=output,
                observation_date=args.observation_date,
            )
            print(
                "NDX v11前瞻观察 + SEC Company Facts取证完成 | "
                f"planned_tickers={len(plan)} | unique_cik={plan_audit['unique_cik_count']} | "
                f"fetched={int(status['status'].eq('fetched').sum()) if not status.empty else 0} | "
                f"facts={summary['fact_rows']} | watch_status={manifest['status']}"
            )
            print(f"SEC证据包: {output}")
        else:
            manifest = build_bundle(
                spec_path=_resolve(args.spec),
                live_config_path=_resolve(args.config),
                output_dir=output,
                observation_date=args.observation_date,
            )
            if args.smoke:
                observations = pd.read_csv(output / "forward_observations.csv")
                if len(observations) != 101:
                    raise NdxForwardWatchError(
                        f"smoke expected 101 current NDX securities, observed {len(observations)}"
                    )
                if bool(observations["candidate_admission_allowed"].astype(bool).any()):
                    raise NdxForwardWatchError("smoke unexpectedly admitted a candidate")
            print(
                "NDX v11前瞻观察登记完成 | "
                f"status={manifest['status']} | "
                f"securities={manifest['summary']['current_ndx_securities']} | "
                f"classified={manifest['summary']['accepted_taxonomy_securities']} | "
                f"candidate_admission={manifest['summary']['candidate_admission_allowed']} | "
                "return_data_read=False"
            )
        print(f"输出: {output}")
        print(f"Manifest: {output / 'manifest.json'}")
        return 0
    except (NdxForwardWatchError, OSError, ValueError, yaml.YAMLError, requests.RequestException) as exc:
        print(f"NDX v11前瞻观察失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
