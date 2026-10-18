"""Point-in-time SEC SIC evidence from historical filing headers."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Mapping

import pandas as pd

from data.ndx_fundamentals import NdxFundamentalError


SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


def normalize_accession(value: str) -> str:
    accession = str(value or "").strip()
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
        raise NdxFundamentalError(f"invalid SEC accession number: {accession!r}")
    return accession


def filing_header_url(cik: int, accession: str) -> str:
    normalized = normalize_accession(accession)
    compact = normalized.replace("-", "")
    return f"{SEC_ARCHIVES_BASE}/{int(cik)}/{compact}/{normalized}.txt"


def sic_division(sic: int | None) -> str | None:
    if sic is None:
        return None
    code = int(sic)
    ranges = (
        (100, 999, "agriculture_forestry_fishing"),
        (1000, 1499, "mining"),
        (1500, 1799, "construction"),
        (2000, 3999, "manufacturing"),
        (4000, 4999, "transportation_communications_utilities"),
        (5000, 5199, "wholesale_trade"),
        (5200, 5999, "retail_trade"),
        (6000, 6799, "finance_insurance_real_estate"),
        (7000, 8999, "services"),
        (9100, 9729, "public_administration"),
        (9900, 9999, "nonclassifiable"),
    )
    for lower, upper, label in ranges:
        if lower <= code <= upper:
            return label
    return "unclassified"


def _header_field(text: str, label: str) -> str | None:
    match = re.search(
        rf"(?im)^\s*{re.escape(label)}:\s*(.*?)\s*$",
        text,
    )
    return match.group(1).strip() if match else None


def parse_sec_filing_header(
    content: bytes | str,
    *,
    expected_cik: int,
    expected_accession: str,
) -> dict:
    text = (
        content.decode("latin-1", errors="strict")
        if isinstance(content, bytes) else str(content)
    )
    if "<SEC-HEADER>" not in text or "</SEC-HEADER>" not in text:
        raise NdxFundamentalError("SEC filing header markers are incomplete")
    expected = normalize_accession(expected_accession)
    observed_accession = _header_field(text, "ACCESSION NUMBER")
    if observed_accession != expected:
        raise NdxFundamentalError(
            f"SEC filing accession mismatch: expected={expected} "
            f"observed={observed_accession}"
        )
    cik_values = {
        int(value)
        for value in re.findall(
            r"(?im)^\s*CENTRAL INDEX KEY:\s*0*(\d+)\s*$",
            text,
        )
    }
    if int(expected_cik) not in cik_values:
        raise NdxFundamentalError(
            f"SEC filing CIK mismatch: expected={expected_cik} "
            f"observed={sorted(cik_values)}"
        )
    sic_match = re.search(
        r"(?im)^\s*STANDARD INDUSTRIAL CLASSIFICATION:\s*(.*?)\s*\[(\d{4})\]\s*$",
        text,
    )
    sic = int(sic_match.group(2)) if sic_match else None
    description = sic_match.group(1).strip() if sic_match else None
    acceptance_match = re.search(r"(?im)^<ACCEPTANCE-DATETIME>(\d{14})\s*$", text)
    filed_raw = _header_field(text, "FILED AS OF DATE")
    filed_date = (
        f"{filed_raw[:4]}-{filed_raw[4:6]}-{filed_raw[6:8]}"
        if filed_raw and re.fullmatch(r"\d{8}", filed_raw) else None
    )
    return {
        "cik": int(expected_cik),
        "accession_number": expected,
        "form": _header_field(text, "CONFORMED SUBMISSION TYPE"),
        "filed_date": filed_date,
        "acceptance_datetime": (
            acceptance_match.group(1) if acceptance_match else None
        ),
        "company_name": _header_field(text, "COMPANY CONFORMED NAME"),
        "sic": sic,
        "sic_description": description,
        "sic_group_2d": f"{sic // 100:02d}" if sic is not None else None,
        "sic_division": sic_division(sic),
        "sic_available": sic is not None,
    }


def build_sic_evidence_plan(
    selection_plan: pd.DataFrame,
    normalization_components: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required_plan = {"selection_date", "ticker", "cik"}
    required_components = {
        "selection_date",
        "cik",
        "metric",
        "component_set",
        "available_date",
        "accession_number",
    }
    missing_plan = sorted(required_plan - set(selection_plan.columns))
    missing_components = sorted(
        required_components - set(normalization_components.columns)
    )
    if missing_plan or missing_components:
        raise NdxFundamentalError(
            f"SIC evidence inputs missing: plan={missing_plan} "
            f"components={missing_components}"
        )
    assets = normalization_components[
        normalization_components["metric"].eq("assets")
        & normalization_components["component_set"].eq("current")
    ].copy()
    if assets.empty:
        raise NdxFundamentalError("current asset components are missing")
    evidence = assets[[
        "selection_date",
        "cik",
        "available_date",
        "accession_number",
    ]].drop_duplicates()
    duplicated = evidence.duplicated(["selection_date", "cik"], keep=False)
    if duplicated.any():
        rows = evidence.loc[duplicated, ["selection_date", "cik"]].drop_duplicates()
        raise NdxFundamentalError(
            f"multiple SIC source accessions for selection/CIK: {len(rows)}"
        )
    mapped = selection_plan.drop_duplicates(
        ["selection_date", "ticker"]
    ).merge(
        evidence,
        on=["selection_date", "cik"],
        how="left",
        validate="many_to_one",
    )
    if mapped["accession_number"].isna().any():
        missing = mapped.loc[
            mapped["accession_number"].isna(), ["selection_date", "ticker", "cik"]
        ]
        raise NdxFundamentalError(
            f"SIC source accession missing for {len(missing)} selection rows"
        )
    mapped["classification_guard_passed"] = (
        mapped["available_date"].astype(str)
        <= mapped["selection_date"].astype(str)
    )
    if not bool(mapped["classification_guard_passed"].all()):
        raise NdxFundamentalError("SIC source filing is not point-in-time")
    jobs = mapped.groupby(["cik", "accession_number"], as_index=False).agg(
        filing_available_date=("available_date", "min"),
        first_selection_date=("selection_date", "min"),
        last_selection_date=("selection_date", "max"),
        selection_rows=("selection_date", "size"),
    )
    jobs["cik"] = jobs["cik"].astype(int)
    jobs["source_url"] = [
        filing_header_url(row.cik, row.accession_number)
        for row in jobs.itertuples(index=False)
    ]
    jobs["job_id"] = [
        hashlib.sha256(
            f"{row.cik}|{row.accession_number}|{row.source_url}".encode("ascii")
        ).hexdigest()[:16]
        for row in jobs.itertuples(index=False)
    ]
    return (
        jobs.sort_values(["cik", "accession_number"]).reset_index(drop=True),
        mapped.sort_values(["selection_date", "ticker"]).reset_index(drop=True),
    )


def sic_header_index(raw_dir: str | Path, jobs: pd.DataFrame) -> pd.DataFrame:
    root = Path(raw_dir)
    rows = []
    for row in jobs.itertuples(index=False):
        path = root / str(int(row.cik)) / f"{row.accession_number}.header.txt"
        if not path.exists():
            continue
        content = path.read_bytes()
        parsed = parse_sec_filing_header(
            content,
            expected_cik=int(row.cik),
            expected_accession=str(row.accession_number),
        )
        rows.append({
            **parsed,
            "path": path.as_posix(),
            "content_bytes": len(content),
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "source_url": row.source_url,
        })
    columns = [
        "cik",
        "accession_number",
        "form",
        "filed_date",
        "acceptance_datetime",
        "company_name",
        "sic",
        "sic_description",
        "sic_group_2d",
        "sic_division",
        "sic_available",
        "path",
        "content_bytes",
        "content_sha256",
        "source_url",
    ]
    return pd.DataFrame(rows, columns=columns)


def raw_sic_bundle_sha256(index: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for row in index.sort_values(["cik", "accession_number"]).itertuples(index=False):
        digest.update(str(int(row.cik)).encode("ascii"))
        digest.update(str(row.accession_number).encode("ascii"))
        digest.update(str(row.content_sha256).encode("ascii"))
    return digest.hexdigest()


def attach_sic_evidence(
    mapped_plan: pd.DataFrame,
    header_index: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "cik",
        "accession_number",
        "form",
        "filed_date",
        "acceptance_datetime",
        "company_name",
        "sic",
        "sic_description",
        "sic_group_2d",
        "sic_division",
        "sic_available",
        "content_sha256",
        "source_url",
    ]
    available = header_index[columns] if not header_index.empty else pd.DataFrame(
        columns=columns
    )
    result = mapped_plan.merge(
        available,
        on=["cik", "accession_number"],
        how="left",
        validate="many_to_one",
    )
    result["header_cached"] = result["content_sha256"].notna()
    result["sic_available"] = result["sic_available"].eq(True)
    result["sic_future_data_guard_passed"] = (
        result["available_date"].astype(str)
        <= result["selection_date"].astype(str)
    )
    return result
