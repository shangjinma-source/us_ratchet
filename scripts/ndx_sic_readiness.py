"""Build resumable point-in-time SEC SIC evidence for NDX selections."""
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
from data.ndx_fundamentals import fundamental_cache_dir
from data.ndx_history import _sec_headers, _sec_user_agent
from data.ndx_sic_history import (
    attach_sic_evidence,
    build_sic_evidence_plan,
    parse_sec_filing_header,
    raw_sic_bundle_sha256,
    sic_header_index,
)
from data.versioning import file_sha256, utc_now_iso, write_dataset_manifest


SIC_EVIDENCE_ID = "sec_filing_header_sic_pit_v1"
MAX_HEADER_BYTES = 2 * 1024 * 1024


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


def _fetch_header_once(
    session: requests.Session,
    url: str,
    *,
    timeout: int,
) -> bytes:
    marker = b"</SEC-HEADER>"
    chunks = []
    size = 0
    with session.get(
        url,
        timeout=timeout,
        stream=True,
        headers={
            "Range": f"bytes=0-{MAX_HEADER_BYTES - 1}",
            "Accept-Encoding": "identity",
        },
    ) as response:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=32 * 1024):
            if not chunk:
                continue
            chunks.append(chunk)
            size += len(chunk)
            combined = b"".join(chunks)
            position = combined.find(marker)
            if position >= 0:
                return combined[:position + len(marker)] + b"\n"
            if size > MAX_HEADER_BYTES:
                break
    raise ValueError(f"SEC header marker not found within {MAX_HEADER_BYTES} bytes: {url}")


def _fetch_header(
    session: requests.Session,
    url: str,
    *,
    timeout: int = 90,
    attempts: int = 4,
) -> bytes:
    for attempt in range(1, attempts + 1):
        try:
            return _fetch_header_once(session, url, timeout=timeout)
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            retryable = (
                isinstance(exc, (requests.ConnectionError, requests.Timeout))
                or status == 429
                or (status is not None and 500 <= int(status) <= 599)
            )
            if not retryable or attempt >= attempts:
                raise
            retry_after = getattr(getattr(exc, "response", None), "headers", {}).get(
                "Retry-After"
            )
            delay = float(retry_after) if str(retry_after or "").isdigit() else 2 ** (attempt - 1)
            time.sleep(min(max(delay, 1.0), 30.0))
    raise RuntimeError("unreachable SEC header retry state")


def _download_headers(
    session: requests.Session,
    raw_dir: Path,
    jobs: pd.DataFrame,
    *,
    force: bool,
    max_filings: int,
) -> pd.DataFrame:
    rows = []
    fetched = 0
    attempted = 0
    failed = 0
    remote_total = sum(
        force
        or not (
            raw_dir / str(int(row.cik))
            / f"{row.accession_number}.header.txt"
        ).exists()
        for row in jobs.itertuples(index=False)
    )
    if max_filings:
        remote_total = min(remote_total, max_filings)
    batch_started = time.monotonic()
    for position, row in enumerate(jobs.itertuples(index=False), start=1):
        attempted_this_row = False
        path = raw_dir / str(int(row.cik)) / f"{row.accession_number}.header.txt"
        status = "cached"
        error = None
        if force or not path.exists():
            if max_filings and attempted >= max_filings:
                rows.append({
                    "job_id": row.job_id,
                    "cik": int(row.cik),
                    "accession_number": row.accession_number,
                    "position": position,
                    "status": "pending_limit",
                    "error": None,
                    "path": path.as_posix(),
                    "source_url": row.source_url,
                })
                continue
            started = time.monotonic()
            attempted += 1
            attempted_this_row = True
            try:
                content = _fetch_header(session, row.source_url)
                parse_sec_filing_header(
                    content,
                    expected_cik=int(row.cik),
                    expected_accession=str(row.accession_number),
                )
                _atomic_bytes(content, path)
                status = "fetched"
                fetched += 1
            except Exception as exc:
                status = "failed"
                error = f"{type(exc).__name__}: {exc}"
                failed += 1
            elapsed = time.monotonic() - started
            if elapsed < 0.15:
                time.sleep(0.15 - elapsed)
        rows.append({
            "job_id": row.job_id,
            "cik": int(row.cik),
            "accession_number": row.accession_number,
            "position": position,
            "status": status,
            "error": error,
            "path": path.as_posix(),
            "source_url": row.source_url,
        })
        if attempted_this_row and (
            attempted % 25 == 0 or attempted == remote_total
        ):
            elapsed = max(time.monotonic() - batch_started, 1e-9)
            remaining = max(remote_total - attempted, 0)
            eta_seconds = remaining * elapsed / attempted
            print(
                f"SIC headers: attempted {attempted}/{remote_total} | "
                f"fetched {fetched} | failed {failed} | "
                f"ETA {eta_seconds / 60:.1f}m"
            )
    return pd.DataFrame(rows)


def _verified_normalization(normalization_dir: Path) -> tuple[dict, Path]:
    manifest_path = normalization_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("normalization_integrity_passed") is not True:
        raise ValueError("fundamental normalization integrity did not pass")
    evidence = (manifest.get("evidence_files") or {}).get(
        "normalization_components"
    ) or {}
    components_path = normalization_dir / str(evidence.get("filename") or "")
    if (
        not components_path.exists()
        or not evidence.get("sha256")
        or file_sha256(components_path) != evidence["sha256"]
    ):
        raise ValueError("normalization component evidence hash mismatch")
    return manifest, components_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Download immutable SEC filing headers and attach historical SIC "
            "evidence to NDX training selections."
        )
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--normalization-dir", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--max-filings",
        type=int,
        default=0,
        help="Limit new header downloads for a smoke run; zero means all.",
    )
    args = parser.parse_args()

    cfg = load_config(_resolve(args.config))
    fundamental_dir = fundamental_cache_dir(cfg)
    normalization_dir = (
        _resolve(args.normalization_dir)
        if args.normalization_dir else fundamental_dir / "normalization_v1"
    )
    output = (
        _resolve(args.output_dir)
        if args.output_dir else fundamental_dir / "sic_history_v1"
    )
    output.mkdir(parents=True, exist_ok=True)
    raw_dir = output / "raw_headers"

    normalization_manifest, components_path = _verified_normalization(
        normalization_dir
    )
    selection_plan_path = fundamental_dir / "plan.csv"
    if file_sha256(selection_plan_path) != normalization_manifest.get("plan_sha256"):
        raise ValueError("selection plan hash differs from fundamental normalization")
    selection_plan = pd.read_csv(selection_plan_path)
    components = pd.read_csv(components_path, low_memory=False)
    jobs, mapped_plan = build_sic_evidence_plan(selection_plan, components)
    plan_path = output / "plan.csv"
    _atomic_csv(jobs, plan_path)

    cached_before = sum(
        (raw_dir / str(int(row.cik)) / f"{row.accession_number}.header.txt").exists()
        for row in jobs.itertuples(index=False)
    )
    print("\nNDX point-in-time SEC SIC readiness")
    print(
        f"Filings: {len(jobs)} | training CIKs: {mapped_plan['cik'].nunique()} | "
        f"selection rows: {len(mapped_plan)} | cached: {cached_before}/{len(jobs)}"
    )
    print(f"Plan: {plan_path}")
    if args.plan_only:
        return 0

    session = None
    if not args.offline:
        explicit_agent = os.environ.get("SEC_USER_AGENT")
        if not explicit_agent:
            raise ValueError(
                "Set SEC_USER_AGENT to an identifying client string with a real contact email."
            )
        session = requests.Session()
        session.headers.update(_sec_headers(_sec_user_agent(explicit_agent)))
    if args.offline:
        download_status = pd.DataFrame([
            {
                "job_id": row.job_id,
                "cik": int(row.cik),
                "accession_number": row.accession_number,
                "position": position,
                "status": (
                    "cached"
                    if (
                        raw_dir / str(int(row.cik))
                        / f"{row.accession_number}.header.txt"
                    ).exists() else "missing_offline"
                ),
                "error": None,
                "path": (
                    raw_dir / str(int(row.cik))
                    / f"{row.accession_number}.header.txt"
                ).as_posix(),
                "source_url": row.source_url,
            }
            for position, row in enumerate(jobs.itertuples(index=False), start=1)
        ])
    else:
        download_status = _download_headers(
            session,
            raw_dir,
            jobs,
            force=bool(args.force),
            max_filings=max(0, int(args.max_filings)),
        )
    _atomic_csv(download_status, output / "download_status.csv")

    header_index = sic_header_index(raw_dir, jobs)
    selection_sic = attach_sic_evidence(mapped_plan, header_index)
    coverage = selection_sic.groupby("selection_date").agg(
        universe_count=("ticker", "size"),
        header_cached_count=("header_cached", "sum"),
        sic_available_count=("sic_available", "sum"),
        header_coverage=("header_cached", "mean"),
        sic_coverage=("sic_available", "mean"),
        unique_sic_codes=("sic", "nunique"),
        unique_sic_groups=("sic_group_2d", "nunique"),
        future_data_guard_passed=("sic_future_data_guard_passed", "all"),
    ).reset_index()
    unresolved = selection_sic[
        ~selection_sic["header_cached"] | ~selection_sic["sic_available"]
    ].drop_duplicates(["cik", "accession_number"])

    output_frames = {
        "raw_header_index": header_index,
        "selection_sic": selection_sic,
        "coverage_summary": coverage,
        "unresolved": unresolved,
    }
    for name, frame in output_frames.items():
        _atomic_csv(frame, output / f"{name}.csv")
    bundle_hash = raw_sic_bundle_sha256(header_index)
    common_extra = {
        "sic_evidence_id": SIC_EVIDENCE_ID,
        "raw_sic_bundle_sha256": bundle_hash,
        "normalization_policy_id": normalization_manifest.get(
            "normalization_policy_id"
        ),
        "normalization_components_sha256": (
            normalization_manifest["evidence_files"]["normalization_components"][
                "sha256"
            ]
        ),
        "point_in_time_policy": "asset-source filing available_date <= selection_date",
        "classification_system": "SEC SIC, not GICS",
        "scoring_allowed": False,
    }
    evidence = {}
    for name, frame in output_frames.items():
        path = output / f"{name}.csv"
        manifest = write_dataset_manifest(
            path,
            dataset_type=f"ndx_{name}",
            dataset_key=SIC_EVIDENCE_ID,
            source="sec_historical_filing_headers",
            source_locator="https://www.sec.gov/Archives/edgar/data/",
            row_count=len(frame),
            data_start=str(mapped_plan["selection_date"].min())[:10],
            data_end=str(mapped_plan["selection_date"].max())[:10],
            extra=common_extra,
        )
        evidence[name] = {
            "filename": path.name,
            "rows": len(frame),
            "sha256": manifest["content_sha256"],
        }

    workbook = output / "ndx_sic_readiness.xlsx"
    temporary = workbook.with_name(workbook.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            coverage.to_excel(writer, sheet_name="coverage_summary", index=False)
            selection_sic.to_excel(writer, sheet_name="selection_sic", index=False)
            header_index.to_excel(writer, sheet_name="filing_sic_history", index=False)
            unresolved.to_excel(writer, sheet_name="unresolved", index=False)
            download_status.to_excel(writer, sheet_name="download_status", index=False)
            jobs.to_excel(writer, sheet_name="plan", index=False)
        os.replace(temporary, workbook)
    finally:
        if temporary.exists():
            temporary.unlink()

    all_headers = len(header_index) == len(jobs)
    sic_complete = bool(all_headers and selection_sic["sic_available"].all())
    future_guard = bool(selection_sic["sic_future_data_guard_passed"].all())
    payload = {
        "generated_at": utc_now_iso(),
        "research_only": True,
        "sic_evidence_id": SIC_EVIDENCE_ID,
        "planned_filings": len(jobs),
        "cached_valid_headers": len(header_index),
        "training_ciks": int(mapped_plan["cik"].nunique()),
        "selection_rows": len(selection_sic),
        "raw_sic_bundle_sha256": bundle_hash,
        "all_headers_cached": all_headers,
        "sic_evidence_complete": sic_complete,
        "future_data_guard_passed": future_guard,
        "minimum_sic_coverage": (
            float(coverage["sic_coverage"].min()) if not coverage.empty else 0.0
        ),
        "classification_system": "SEC SIC, not GICS",
        "scoring_allowed": False,
        "files": {
            **{name: item["filename"] for name, item in evidence.items()},
            "download_status": "download_status.csv",
            "plan": "plan.csv",
            "workbook": workbook.name,
        },
    }
    atomic_write_text(
        output / "sic_readiness.json",
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    atomic_write_text(
        output / "manifest.json",
        json.dumps({
            "schema_version": 1,
            "generated_at": payload["generated_at"],
            "sic_evidence_id": SIC_EVIDENCE_ID,
            "raw_sic_bundle_sha256": bundle_hash,
            "normalization_manifest_sha256": file_sha256(
                normalization_dir / "manifest.json"
            ),
            "evidence_files": evidence,
            "sic_evidence_complete": sic_complete,
            "future_data_guard_passed": future_guard,
            "scoring_allowed": False,
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(
        f"Valid headers: {len(header_index)}/{len(jobs)} | "
        f"SIC selection coverage min: {coverage['sic_coverage'].min() * 100:.2f}% | "
        f"unresolved filings: {len(unresolved)}"
    )
    print("SIC is classification evidence only; scoring remains disabled.")
    print(f"Workbook: {workbook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
