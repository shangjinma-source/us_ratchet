"""Fetch and audit first-party annual SEC evidence for the live incumbents.

Examples for a PyCharm terminal:
    python -B scripts\\ndx_incumbent_overlay.py --plan-only
    $env:SEC_USER_AGENT="us_ratchet/1.0 real-contact@example.com"
    python -B scripts\\ndx_incumbent_overlay.py --fetch-sec --resume --max-jobs 8
    python -B scripts\\ndx_incumbent_overlay.py --review-pack

The command never assigns a risk chain and never reads prices, returns, or
backtest results.  It creates a separate overlay because TSM is not part of
the historical 163-ticker NDX identity universe.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import atomic_write_text  # noqa: E402
from data.ndx_history import _sec_headers, _sec_user_agent  # noqa: E402
from data.ndx_incumbent_overlay import (  # noqa: E402
    ATTEMPT_COLUMNS,
    NdxIncumbentOverlayError,
    OVERLAY_PLAN_COLUMNS,
    REVIEW_DOCUMENT_COLUMNS,
    REVIEW_TEMPLATE_COLUMNS,
    build_identity_rows,
    build_overlay_plan,
    build_review_pack,
    load_identity_overrides,
    load_incumbent_tickers,
    parse_submission_filings,
    resolve_sec_company_tickers,
)
from data.versioning import file_sha256, manifest_path, utc_now_iso, write_dataset_manifest  # noqa: E402


SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_SUBMISSIONS_FILE_URL = "https://data.sec.gov/submissions/{filename}"
OVERLAY_OUTPUT_SCHEMA_VERSION = 1


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _load_config(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise NdxIncumbentOverlayError("config root must be a mapping")
    return payload


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_json(path: Path, payload: dict) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _write_workbook(path: Path, plan: pd.DataFrame, documents: pd.DataFrame, template: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp.xlsx")
    with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
        plan.to_excel(writer, sheet_name="证据计划", index=False)
        documents.to_excel(writer, sheet_name="SEC原文审计", index=False)
        template.to_excel(writer, sheet_name="分类复核模板", index=False)
    temporary.replace(path)


def _load_attempts(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=ATTEMPT_COLUMNS)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    for column in ATTEMPT_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[ATTEMPT_COLUMNS].drop_duplicates("overlay_id", keep="last")


def _upsert_attempt(frame: pd.DataFrame, row: dict) -> pd.DataFrame:
    remaining = frame[~frame["overlay_id"].eq(str(row["overlay_id"]))].copy()
    return pd.concat([remaining, pd.DataFrame([row])], ignore_index=True)[ATTEMPT_COLUMNS].sort_values(
        ["ticker", "overlay_id"], kind="stable"
    ).reset_index(drop=True)


def _fetch_json(session: requests.Session, url: str, *, timeout: float) -> dict:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise NdxIncumbentOverlayError(f"SEC JSON response is not an object: {url}")
    return payload


def _submission_filings_with_history(
    session: requests.Session,
    submission: dict,
    *,
    cik: str,
    overlay_id: str,
    ticker: str,
    output: Path,
    timeout: float,
    refresh: bool,
) -> list[dict]:
    """Parse recent SEC filings and the official historical submissions files."""

    filings = parse_submission_filings(submission, cik=cik)
    files = ((submission.get("filings") or {}).get("files") or [])
    if not isinstance(files, list):
        raise NdxIncumbentOverlayError("SEC submissions historical files schema changed")
    for item in files:
        if not isinstance(item, dict):
            continue
        filename = Path(str(item.get("name") or "")).name
        if not filename or not filename.startswith(f"CIK{cik}-submissions-"):
            raise NdxIncumbentOverlayError(
                f"unexpected SEC historical submissions filename: {filename!r}"
            )
        url = SEC_SUBMISSIONS_FILE_URL.format(filename=filename)
        path = output / "raw_sec" / "submissions" / filename
        if refresh or not _valid_raw(path):
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            _write_raw(
                path,
                response.content,
                dataset_type="ndx_incumbent_overlay_sec_submissions_history",
                dataset_key=f"{overlay_id}:{filename}",
                source_locator=url,
                extra={
                    "overlay_id": overlay_id,
                    "ticker": ticker,
                    "cik": cik,
                    "submission_file": filename,
                },
            )
        try:
            historical = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise NdxIncumbentOverlayError(
                f"SEC historical submissions JSON is invalid: {path}"
            ) from exc
        filings.extend(parse_submission_filings(historical, cik=cik))
    unique = {}
    for filing in filings:
        accession = str(filing.get("accession_number") or "")
        if accession:
            unique[accession] = filing
    return sorted(
        unique.values(),
        key=lambda row: (str(row.get("filed_date") or ""), str(row.get("accession_number") or "")),
    )


def _write_raw(path: Path, content: bytes, *, dataset_type: str, dataset_key: str, source_locator: str, extra: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return write_dataset_manifest(
        path,
        dataset_type=dataset_type,
        dataset_key=dataset_key,
        source="sec_edgar_incumbent_overlay",
        source_locator=source_locator,
        fetched_at=utc_now_iso(),
        fetched_at_evidence="sec_public_archive_http_200",
        row_count=1,
        extra={
            "research_only": True,
            "classification_automatic": False,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
            **extra,
        },
    )


def _valid_raw(path: Path) -> bool:
    sidecar = manifest_path(path)
    if not path.exists() or not sidecar.exists():
        return False
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    return payload.get("content_sha256") == file_sha256(path)


def _company_ticker_payload(session: requests.Session, *, timeout: float, output: Path, refresh: bool) -> dict:
    target = output / "sec_company_tickers_exchange.json"
    if target.exists() and not refresh and _valid_raw(target):
        return json.loads(target.read_text(encoding="utf-8"))
    response = session.get(SEC_COMPANY_TICKERS_URL, timeout=timeout)
    response.raise_for_status()
    _write_raw(
        target,
        response.content,
        dataset_type="ndx_incumbent_overlay_sec_company_tickers",
        dataset_key="sec_company_tickers_exchange",
        source_locator=SEC_COMPANY_TICKERS_URL,
        extra={"used_for": "TSM overlay identity resolution"},
    )
    return response.json()


def _fetch_overlay(
    plan: pd.DataFrame,
    *,
    output: Path,
    user_agent: str,
    timeout: float,
    request_delay: float,
    max_jobs: int,
    resume: bool,
    refresh: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    headers = _sec_headers(_sec_user_agent(user_agent))
    session = requests.Session()
    session.headers.update(headers)
    attempts = _load_attempts(output / "fetch_attempts.csv")
    updated_plan = plan.copy()
    if "raw_path" not in updated_plan.columns:
        updated_plan["raw_path"] = ""
    processed = 0
    for row in updated_plan.to_dict(orient="records"):
        if max_jobs and processed >= max_jobs:
            break
        overlay_id = str(row["overlay_id"])
        previous = attempts[attempts["overlay_id"].eq(overlay_id)]
        if resume and not refresh and not previous.empty and previous.iloc[-1]["status"] == "fetched":
            continue
        processed += 1
        attempt = {
            "overlay_id": overlay_id,
            "ticker": row["ticker"],
            "cik": row["cik"],
            "status": "failed",
            "attempted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "submission_url": "",
            "accession_number": "",
            "document_url": "",
            "raw_path": "",
            "content_sha256": "",
            "error": "",
        }
        try:
            if not row["cik"]:
                raise NdxIncumbentOverlayError("identity requires SEC company ticker resolution")
            cik = str(row["cik"])
            submission_url = SEC_SUBMISSIONS_URL.format(cik=cik)
            attempt["submission_url"] = submission_url
            submission = _fetch_json(session, submission_url, timeout=timeout)
            submissions_dir = output / "raw_sec" / "submissions"
            submission_path = submissions_dir / f"CIK{cik}.json"
            if refresh or not _valid_raw(submission_path):
                _write_raw(
                    submission_path,
                    json.dumps(submission, ensure_ascii=False, sort_keys=True).encode("utf-8"),
                    dataset_type="ndx_incumbent_overlay_sec_submissions",
                    dataset_key=f"{overlay_id}:submissions",
                    source_locator=submission_url,
                    extra={"overlay_id": overlay_id, "ticker": row["ticker"], "cik": cik},
                )
            filings = _submission_filings_with_history(
                session,
                submission,
                cik=cik,
                overlay_id=overlay_id,
                ticker=str(row["ticker"]),
                output=output,
                timeout=timeout,
                refresh=refresh,
            )
            chosen = build_overlay_plan(
                pd.DataFrame([row]),
                selection_start=row["selection_date_start"],
                selection_end=row["selection_date_end"],
                submissions_by_cik={cik: filings},
            ).iloc[0].to_dict()
            if not chosen["document_url"]:
                raise NdxIncumbentOverlayError("no annual 10-K/20-F/40-F filing found")
            document_url = str(chosen["document_url"])
            attempt["accession_number"] = chosen["accession_number"]
            attempt["document_url"] = document_url
            response = session.get(document_url, timeout=timeout)
            response.raise_for_status()
            raw_path = output / "raw_sec" / "filings" / row["ticker"] / (
                f"{chosen['accession_number'].replace('-', '')}_{Path(document_url).name}"
            )
            _write_raw(
                raw_path,
                response.content,
                dataset_type="ndx_incumbent_overlay_sec_annual_filing",
                dataset_key=f"{overlay_id}:{chosen['accession_number']}",
                source_locator=document_url,
                extra={
                    "overlay_id": overlay_id,
                    "ticker": row["ticker"],
                    "cik": cik,
                    "form": chosen["form"],
                    "report_date": chosen["report_date"],
                    "filed_date": chosen["filed_date"],
                    "evidence_available_date": chosen["evidence_available_date"],
                },
            )
            row.update(chosen)
            row["raw_path"] = raw_path.as_posix()
            row["status"] = "fetched_pending_business_review"
            mask = updated_plan["overlay_id"].eq(overlay_id)
            for key, value in row.items():
                if key not in updated_plan.columns:
                    updated_plan[key] = ""
                updated_plan.loc[mask, key] = value
            attempt["status"] = "fetched"
            attempt["raw_path"] = raw_path.as_posix()
            attempt["content_sha256"] = file_sha256(raw_path)
        except Exception as exc:
            attempt["error"] = f"{type(exc).__name__}: {exc}"
        attempts = _upsert_attempt(attempts, attempt)
        _atomic_csv(attempts, output / "fetch_attempts.csv")
        if request_delay:
            time.sleep(request_delay)
    return updated_plan, attempts


def _write_artifact(frame: pd.DataFrame, path: Path, *, name: str) -> dict:
    _atomic_csv(frame, path)
    manifest = write_dataset_manifest(
        path,
        dataset_type="ndx_incumbent_overlay_artifact",
        dataset_key=name,
        source="derived_from_hash_locked_sec_overlay_inputs",
        fetched_at_evidence="derived_runtime_utc",
        row_count=len(frame),
        extra={
            "research_only": True,
            "classification_automatic": False,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
        },
    )
    return {"filename": path.name, "rows": len(frame), "sha256": manifest["content_sha256"]}


def build_bundle(args) -> dict:
    config_path = _resolve(args.config)
    identity_path = _resolve(args.identity)
    output = _resolve(args.output_dir)
    identity_override_path = _resolve(args.identity_overrides)
    config = _load_config(config_path)
    tickers = load_incumbent_tickers(config)
    identity_overrides = load_identity_overrides(identity_override_path, tickers)
    company_payload = None
    if args.fetch_sec:
        headers = _sec_headers(_sec_user_agent(args.sec_user_agent))
        session = requests.Session()
        session.headers.update(headers)
        company_payload = _company_ticker_payload(
            session, timeout=args.timeout, output=output, refresh=args.refresh
        )
    sec_crosswalk = (
        resolve_sec_company_tickers(company_payload, tickers, allow_missing=True)
        if company_payload
        else {}
    )
    for ticker, override in identity_overrides.items():
        sec_crosswalk.setdefault(ticker, override)
    identities = build_identity_rows(
        config,
        identity_path=identity_path,
        sec_company_tickers=sec_crosswalk,
    )
    output.mkdir(parents=True, exist_ok=True)
    existing_plan_path = output / "overlay_plan.csv"
    existing_plan = None
    if existing_plan_path.exists() and (args.review_pack or (args.fetch_sec and args.resume)):
        existing_plan = pd.read_csv(existing_plan_path, dtype=str, keep_default_na=False)
        if not set(OVERLAY_PLAN_COLUMNS).issubset(existing_plan.columns):
            existing_plan = None
    submissions = {}
    if args.submissions_json:
        raw = json.loads(_resolve(args.submissions_json).read_text(encoding="utf-8"))
        submissions = {str(key): parse_submission_filings(value) for key, value in raw.items()}
    plan = existing_plan if existing_plan is not None else build_overlay_plan(
        identities,
        selection_start=args.selection_start,
        selection_end=args.selection_end,
        submissions_by_cik=submissions,
    )
    if existing_plan is not None:
        identity_by_ticker = identities.set_index("ticker").to_dict(orient="index")
        for index, row in plan.iterrows():
            identity = identity_by_ticker.get(str(row.get("ticker") or "").upper())
            if not identity:
                continue
            for field in ("security_id", "issuer_id", "cik", "cusip", "identity_status"):
                plan.loc[index, field] = identity.get(field, "")
    attempts = _load_attempts(output / "fetch_attempts.csv")
    if args.fetch_sec:
        plan, attempts = _fetch_overlay(
            plan,
            output=output,
            user_agent=args.sec_user_agent,
            timeout=args.timeout,
            request_delay=args.request_delay,
            max_jobs=args.max_jobs,
            resume=args.resume,
            refresh=args.refresh,
        )
    else:
        if (output / "fetch_attempts.csv").exists():
            attempts = _load_attempts(output / "fetch_attempts.csv")
        if not plan.empty and not attempts.empty:
            raw_by_id = attempts.set_index("overlay_id").to_dict(orient="index")
            for index, row in plan.iterrows():
                raw = raw_by_id.get(row["overlay_id"], {})
                for key in ("accession_number", "document_url", "raw_path"):
                    if raw.get(key):
                        plan.loc[index, key] = raw[key]
                if raw.get("status") == "fetched":
                    plan.loc[index, "status"] = "fetched_pending_business_review"
    documents, template = build_review_pack(
        plan,
        raw_root=output / "raw_sec",
    )
    plan_path = output / "overlay_plan.csv"
    documents_path = output / "review_documents.csv"
    template_path = output / "evidence_review_template.csv"
    attempts_path = output / "fetch_attempts.csv"
    artifacts = {
        "plan": _write_artifact(plan, plan_path, name="overlay_plan"),
        "documents": _write_artifact(documents, documents_path, name="review_documents"),
        "template": _write_artifact(template, template_path, name="evidence_review_template"),
        "attempts": _write_artifact(attempts, attempts_path, name="fetch_attempts"),
    }
    workbook = output / "ndx_incumbent_overlay_review.xlsx"
    _write_workbook(workbook, plan, documents, template)
    workbook_manifest = write_dataset_manifest(
        workbook,
        dataset_type="ndx_incumbent_overlay_artifact",
        dataset_key="review_workbook",
        source="derived_from_hash_locked_sec_overlay_inputs",
        fetched_at_evidence="derived_runtime_utc",
        row_count=len(plan),
        extra={
            "research_only": True,
            "classification_automatic": False,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
        },
    )
    artifacts["workbook"] = {"filename": workbook.name, "rows": len(plan), "sha256": workbook_manifest["content_sha256"]}
    manifest = {
        "schema_version": OVERLAY_OUTPUT_SCHEMA_VERSION,
        "manifest_type": "ndx_incumbent_taxonomy_overlay",
        "generated_at": utc_now_iso(),
        "research_only": True,
        "classification_automatic": False,
        "classification_status": "pending_codex_review_from_sec_business_text",
        "selection_date_start": args.selection_start,
        "selection_date_end": args.selection_end,
        "return_data_read": False,
        "price_data_used": False,
        "backtest_results_used": False,
        "historical_backfill_allowed": False,
        "future_data_guard": "evidence_available_date <= selection_date",
        "incumbent_tickers": tickers,
        "ndx_identity_file_sha256": file_sha256(identity_path),
        "identity_override_file": identity_override_path.as_posix(),
        "identity_override_file_sha256": (
            file_sha256(identity_override_path)
            if identity_override_path.exists()
            else None
        ),
        "config_sha256": file_sha256(config_path),
        "artifacts": artifacts,
        "summary": {
            "incumbent_count": len(tickers),
            "identity_resolved_count": int(identities["cik"].astype(str).ne("").sum()),
            "filing_selected_count": int(plan["accession_number"].astype(str).ne("").sum()),
            "raw_fetched_count": int(attempts["status"].astype(str).eq("fetched").sum()),
            "review_document_count": len(documents),
            "classification_decisions": 0,
            "pending_manual_review": len(template),
        },
    }
    manifest_path_out = output / "manifest.json"
    _write_json(manifest_path_out, manifest)
    write_dataset_manifest(
        manifest_path_out,
        dataset_type="ndx_incumbent_overlay_manifest",
        dataset_key="incumbent_overlay",
        source="derived_from_hash_locked_sec_overlay_inputs",
        fetched_at_evidence="derived_runtime_utc",
        row_count=1,
        extra={"research_only": True, "classification_automatic": False},
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the NDX live-incumbent SEC taxonomy overlay")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--identity", default="data/cache/candidate_pools/ndx_taxonomy_v2/security_identity.csv")
    parser.add_argument(
        "--identity-overrides",
        default="config/ndx_incumbent_overlay_identity.yaml",
    )
    parser.add_argument("--output-dir", default="data/cache/candidate_pools/ndx_taxonomy_v2/incumbent_overlay")
    parser.add_argument("--selection-start", default="2019-09-30")
    parser.add_argument("--selection-end", default="2026-03-31")
    parser.add_argument("--submissions-json", default="")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--fetch-sec", action="store_true")
    parser.add_argument("--review-pack", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--max-jobs", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--request-delay", type=float, default=0.15)
    parser.add_argument("--sec-user-agent", default="")
    args = parser.parse_args()
    if args.refresh and not args.fetch_sec:
        parser.error("--refresh requires --fetch-sec")
    if sum(bool(value) for value in (args.plan_only, args.fetch_sec, args.review_pack)) != 1:
        parser.error("choose exactly one of --plan-only, --fetch-sec, or --review-pack")
    try:
        manifest = build_bundle(args)
    except (NdxIncumbentOverlayError, OSError, ValueError, requests.RequestException, yaml.YAMLError) as exc:
        print(f"NDX incumbent overlay failed closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "NDX incumbent SEC overlay complete | "
        f"selected={manifest['summary']['filing_selected_count']} | "
        f"fetched={manifest['summary']['raw_fetched_count']} | "
        f"pending_review={manifest['summary']['pending_manual_review']} | "
        "classification_decisions=0"
    )
    print(f"Output: {_resolve(args.output_dir)}")
    print(f"Manifest: {_resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
