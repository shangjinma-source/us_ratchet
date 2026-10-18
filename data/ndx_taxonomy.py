"""Point-in-time Nasdaq-100 risk-chain taxonomy evidence.

This module is intentionally independent from the return engine.  It builds a
stable security/issuer identity universe from the historical QQQ N-PORT proxy,
then applies only explicitly reviewed first-party evidence.  Missing or
conflicting evidence is represented as ``unclassified`` and never inferred
from a ticker name, price, return, market-cap rank, or legacy taxonomy.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import parse_qs, unquote, urlparse

import pandas as pd
import yaml

from data.ndx_filing_identity import filing_directory_url
from data.ndx_security_identity import SecurityLifecycle
from data.versioning import file_sha256, manifest_path


TAXONOMY_SCHEMA_VERSION = 2
TAXONOMY_CONFIG_ID = "us_growth_risk_chain_taxonomy_v2"
HISTORY_MANIFEST_TYPE = "ndx_point_in_time_constituents"
HISTORY_MANIFEST_KEY = "qqq_nport_public_filings"
EVIDENCE_SOURCE_TYPES = {
    "sec_filing_business_description",
    "issuer_official_material",
    "nasdaq_official_material",
}
EVIDENCE_STATUSES = {"accepted", "unclassified", "pending_review", "rejected"}
EVIDENCE_CONFIDENCES = {"high", "medium", "low", ""}
UNCLASSIFIED_CHAIN = "unclassified"

EVIDENCE_COLUMNS = [
    "evidence_id",
    "security_id",
    "issuer_id",
    "ticker",
    "risk_chain",
    "effective_from",
    "effective_to",
    "evidence_source_type",
    "evidence_source",
    "evidence_locator",
    "evidence_available_date",
    "accession_number",
    "evidence_excerpt",
    "confidence",
    "status",
    "notes",
]

IDENTITY_COLUMNS = [
    "security_id",
    "issuer_id",
    "ticker",
    "cik",
    "cusip",
    "observation_from",
    "observation_to",
    "available_from",
    "available_to",
    "observed_reports",
    "ticker_count",
    "ticker_set",
    "identity_status",
    "identity_issue",
]

OBSERVATION_COLUMNS = [
    "selection_date",
    "report_date",
    "filed_date",
    "available_date",
    "accession_number",
    "ticker",
    "price_ticker",
    "name",
    "cusip",
    "security_id",
    "issuer_id",
    "cik",
    "identity_status",
    "ticker_lifecycle_rule_id",
    "ticker_lifecycle_status",
]

RECORD_COLUMNS = [
    "security_id",
    "issuer_id",
    "ticker",
    "cik",
    "cusip",
    "effective_from",
    "effective_to",
    "selection_date_start",
    "selection_date_end",
    "selection_dates",
    "observations_count",
    "risk_chain",
    "risk_chain_label",
    "evidence_source",
    "evidence_source_type",
    "evidence_locator",
    "evidence_available_date",
    "evidence_ids",
    "confidence",
    "status",
    "reason",
]


class NdxTaxonomyError(ValueError):
    """Raised when taxonomy input cannot be audited safely."""


@dataclass(frozen=True)
class InputVersion:
    name: str
    path: str
    version_id: str | None
    content_sha256: str
    manifest_sha256: str | None
    row_count: int
    verified: bool
    used_for: str

    def to_dict(self) -> dict:
        return {
            "source_name": self.name,
            "path": self.path,
            "version_id": self.version_id,
            "content_sha256": self.content_sha256,
            "manifest_sha256": self.manifest_sha256,
            "row_count": int(self.row_count),
            "manifest_verified": bool(self.verified),
            "used_for": self.used_for,
        }


@dataclass(frozen=True)
class SecurityUniverse:
    identities: pd.DataFrame
    observations: pd.DataFrame
    lifecycle_aliases: pd.DataFrame
    issues: pd.DataFrame


def empty_evidence_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=EVIDENCE_COLUMNS)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def normalize_cik(value: object) -> str | None:
    if _is_missing(value):
        return None
    raw = str(value).strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    if not raw or not raw.isdigit() or int(raw) <= 0:
        return None
    return f"{int(raw):010d}"


def normalize_ticker(value: object) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip().upper()


def normalize_cusip(value: object) -> str:
    if _is_missing(value):
        return ""
    raw = str(value).strip().upper()
    if raw in {"", "NAN", "NA", "N/A", "NONE", "NULL", "<NA>"}:
        return ""
    return re.sub(r"\s+", "", raw)


def normalize_date(value: object, *, field: str, allow_blank: bool = True) -> str | None:
    if _is_missing(value) or not str(value).strip():
        if allow_blank:
            return None
        raise NdxTaxonomyError(f"{field} is required")
    parsed = pd.Timestamp(str(value).strip())
    if pd.isna(parsed):
        raise NdxTaxonomyError(f"invalid {field}: {value!r}")
    return parsed.normalize().strftime("%Y-%m-%d")


def _read_manifest(path: Path) -> tuple[dict, str]:
    sidecar = manifest_path(path)
    if not sidecar.exists():
        raise NdxTaxonomyError(f"manifest missing for {path}")
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise NdxTaxonomyError(f"invalid manifest for {path}") from exc
    digest = file_sha256(path)
    if payload.get("content_sha256") != digest:
        raise NdxTaxonomyError(f"content hash mismatch for {path}")
    if payload.get("row_count") is not None:
        try:
            observed = len(pd.read_csv(path, low_memory=False, keep_default_na=False))
        except Exception as exc:
            raise NdxTaxonomyError(f"cannot read manifested CSV {path}") from exc
        if int(payload.get("row_count")) != observed:
            raise NdxTaxonomyError(
                f"row count mismatch for {path}: manifest={payload.get('row_count')} observed={observed}"
            )
    return payload, file_sha256(sidecar)


def read_versioned_csv(path: str | Path, *, name: str, used_for: str) -> tuple[pd.DataFrame, InputVersion]:
    target = Path(path)
    if not target.exists():
        raise NdxTaxonomyError(f"input CSV missing: {target}")
    manifest, manifest_digest = _read_manifest(target)
    frame = pd.read_csv(
        target, low_memory=False, keep_default_na=False,
        dtype={"cusip": str, "cusips": str, "cik": str},
    )
    return frame, InputVersion(
        name=name,
        path=target.as_posix(),
        version_id=str(manifest.get("version_id") or "") or None,
        content_sha256=file_sha256(target),
        manifest_sha256=manifest_digest,
        row_count=len(frame),
        verified=True,
        used_for=used_for,
    )


def load_taxonomy_definition(path: str | Path) -> dict:
    target = Path(path)
    if not target.exists():
        raise NdxTaxonomyError(f"taxonomy definition missing: {target}")
    try:
        payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise NdxTaxonomyError(f"invalid taxonomy definition: {target}") from exc
    if int(payload.get("schema_version") or 0) != TAXONOMY_SCHEMA_VERSION:
        raise NdxTaxonomyError("taxonomy v2 schema_version is not supported")
    if str(payload.get("taxonomy_id") or "") != TAXONOMY_CONFIG_ID:
        raise NdxTaxonomyError("taxonomy v2 taxonomy_id is not supported")
    categories = payload.get("risk_chains")
    if not isinstance(categories, Mapping) or UNCLASSIFIED_CHAIN not in categories:
        raise NdxTaxonomyError("taxonomy v2 risk_chains must include unclassified")
    for key, value in categories.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]+", str(key)) or not isinstance(value, Mapping):
            raise NdxTaxonomyError(f"invalid taxonomy risk chain: {key!r}")
        if not str(value.get("label") or "").strip():
            raise NdxTaxonomyError(f"risk chain {key!r} lacks a label")
    policy = payload.get("classification_policy") or {}
    if policy.get("historical_backfill_allowed") is not False:
        raise NdxTaxonomyError("taxonomy v2 must explicitly prohibit historical backfill")
    allowed = set(policy.get("allowed_source_types") or [])
    if allowed != EVIDENCE_SOURCE_TYPES:
        raise NdxTaxonomyError("taxonomy v2 source policy is incomplete")
    payload["path"] = target.as_posix()
    payload["content_sha256"] = file_sha256(target)
    payload["version_id"] = f"{TAXONOMY_CONFIG_ID}:{payload['content_sha256'][:16]}"
    return payload


def _security_id(cik: str | None, cusip: str, ticker: str) -> str:
    if cik and cusip:
        return f"security:{cik}:{cusip}"
    if cik:
        return f"security:{cik}:unresolved_cusip:{ticker}"
    return f"security:unresolved:{ticker}"


def _issuer_id(cik: str | None, ticker: str) -> str:
    return f"issuer:{cik}" if cik else f"issuer:unresolved:{ticker}"


def _crosswalk_cusips(value: object) -> set[str]:
    if _is_missing(value):
        return set()
    return {
        normalize_cusip(item)
        for item in str(value).split(";")
        if normalize_cusip(item)
    }


def _lifecycle_price_ticker(
    lifecycle: SecurityLifecycle | None,
    cik: str | None,
    ticker: str,
    report_date: str,
) -> tuple[str, str, str]:
    if lifecycle is None or cik is None:
        return ticker, "", "not_declared"
    rule = lifecycle.rules_by_cik.get(cik)
    if rule is None:
        return ticker, "", "not_declared_same_ticker"
    if ticker not in rule.recognized_tickers:
        return ticker, rule.rule_id, "ticker_not_recognized_by_lifecycle"
    try:
        resolved = rule.resolve(pd.Timestamp(report_date))
    except Exception:
        return ticker, rule.rule_id, "lifecycle_resolution_failed"
    return resolved, rule.rule_id, "resolved_from_versioned_lifecycle"


def _lifecycle_alias_frame(lifecycle: SecurityLifecycle | None) -> pd.DataFrame:
    columns = [
        "issuer_id",
        "security_id",
        "cik",
        "cusip",
        "rule_id",
        "recognized_ticker",
        "price_ticker",
        "effective_from",
        "effective_to",
        "evidence_urls",
    ]
    if lifecycle is None:
        return pd.DataFrame(columns=columns)
    rows = []
    for cik, rule in sorted(lifecycle.rules_by_cik.items()):
        for interval in rule.intervals:
            for ticker in sorted(rule.recognized_tickers):
                rows.append({
                    "issuer_id": f"issuer:{cik}",
                    "security_id": _security_id(cik, normalize_cusip(rule.cusip), ticker),
                    "cik": cik,
                    "cusip": normalize_cusip(rule.cusip),
                    "rule_id": rule.rule_id,
                    "recognized_ticker": ticker,
                    "price_ticker": interval.price_ticker,
                    "effective_from": (
                        interval.effective_from.strftime("%Y-%m-%d")
                        if interval.effective_from is not None else ""
                    ),
                    "effective_to": (
                        interval.effective_to.strftime("%Y-%m-%d")
                        if interval.effective_to is not None else ""
                    ),
                    "evidence_urls": " | ".join(rule.evidence_urls),
                })
    return pd.DataFrame(rows, columns=columns)


def build_security_universe(
    history: pd.DataFrame,
    crosswalk: pd.DataFrame,
    *,
    lifecycle: SecurityLifecycle | None = None,
) -> SecurityUniverse:
    required_history = {
        "report_date", "filed_date", "available_date", "accession_number",
        "ticker", "name", "cusip", "weight", "source_locator",
    }
    required_crosswalk = {"ticker", "cik", "mapping_status", "cusips"}
    missing_history = sorted(required_history - set(history.columns))
    missing_crosswalk = sorted(required_crosswalk - set(crosswalk.columns))
    if missing_history or missing_crosswalk:
        raise NdxTaxonomyError(
            f"identity inputs missing: history={missing_history} crosswalk={missing_crosswalk}"
        )

    hist = history.copy()
    for column in ("report_date", "filed_date", "available_date"):
        hist[column] = [
            normalize_date(value, field=column, allow_blank=False)
            for value in hist[column]
        ]
    for column in ("ticker", "name", "accession_number", "source_locator"):
        hist[column] = hist[column].map(lambda value: "" if _is_missing(value) else str(value).strip())
    hist["ticker"] = hist["ticker"].map(normalize_ticker)
    hist["cusip"] = hist["cusip"].map(normalize_cusip)
    if hist["ticker"].eq("").any():
        raise NdxTaxonomyError("NDX history contains a blank ticker")
    if hist["ticker"].eq("QQQ").any():
        raise NdxTaxonomyError("QQQ cannot enter the taxonomy security universe")

    cw = crosswalk.copy()
    cw["ticker"] = cw["ticker"].map(normalize_ticker)
    cw["cik"] = cw["cik"].map(normalize_cik)
    cw["mapping_status"] = cw["mapping_status"].astype(str).str.strip().str.lower()
    cw["cusips"] = cw["cusips"].map(_crosswalk_cusips)
    if cw["ticker"].duplicated().any():
        raise NdxTaxonomyError("CIK crosswalk contains duplicate tickers")
    if cw["mapping_status"].ne("mapped").any():
        raise NdxTaxonomyError("CIK crosswalk contains unresolved historical tickers")

    merged = hist.merge(
        cw[["ticker", "cik", "cusips"]],
        on="ticker",
        how="left",
        validate="many_to_one",
        indicator="crosswalk_match",
    )
    issues = []
    observations = []
    for row in merged.itertuples(index=False):
        ticker = normalize_ticker(row.ticker)
        cik = normalize_cik(row.cik)
        cusip = normalize_cusip(row.cusip)
        crosswalk_cusips = set(row.cusips) if isinstance(row.cusips, set) else set()
        issue_parts = []
        if row.crosswalk_match != "both" or cik is None:
            issue_parts.append("cik_crosswalk_missing")
        if not cusip:
            issue_parts.append("historical_cusip_missing")
        elif crosswalk_cusips and cusip not in crosswalk_cusips:
            issue_parts.append("historical_cusip_not_in_crosswalk")
        security = _security_id(cik, cusip, ticker)
        issuer = _issuer_id(cik, ticker)
        price_ticker, rule_id, lifecycle_status = _lifecycle_price_ticker(
            lifecycle, cik, ticker, str(row.report_date)
        )
        if lifecycle_status in {"ticker_not_recognized_by_lifecycle", "lifecycle_resolution_failed"}:
            issue_parts.append(lifecycle_status)
        identity_status = "resolved" if cik and cusip else "unresolved_identity"
        if issue_parts:
            issues.append({
                "issue_type": "identity",
                "security_id": security,
                "issuer_id": issuer,
                "ticker": ticker,
                "cik": cik or "",
                "cusip": cusip,
                "report_date": row.report_date,
                "detail": ";".join(issue_parts),
            })
        observations.append({
            "selection_date": row.available_date,
            "report_date": row.report_date,
            "filed_date": row.filed_date,
            "available_date": row.available_date,
            "accession_number": str(row.accession_number),
            "ticker": ticker,
            "price_ticker": price_ticker,
            "name": str(row.name),
            "cusip": cusip,
            "security_id": security,
            "issuer_id": issuer,
            "cik": cik or "",
            "identity_status": identity_status,
            "ticker_lifecycle_rule_id": rule_id,
            "ticker_lifecycle_status": lifecycle_status,
        })
    obs = pd.DataFrame(observations, columns=OBSERVATION_COLUMNS)
    if obs.empty:
        raise NdxTaxonomyError("historical NDX identity universe is empty")
    identity_rows = []
    for security_id, group in obs.groupby("security_id", sort=True):
        issuers = sorted(set(group["issuer_id"]))
        ciks = sorted({value for value in group["cik"] if value})
        cusips = sorted({value for value in group["cusip"] if value})
        tickers = sorted(set(group["ticker"]))
        matching_issues = sorted(
            set(
                issue["detail"]
                for issue in issues
                if issue["security_id"] == security_id
            )
        )
        identity_rows.append({
            "security_id": security_id,
            "issuer_id": issuers[0] if len(issuers) == 1 else "",
            "ticker": tickers[0] if len(tickers) == 1 else ";".join(tickers),
            "cik": ciks[0] if len(ciks) == 1 else ";".join(ciks),
            "cusip": cusips[0] if len(cusips) == 1 else ";".join(cusips),
            "observation_from": group["report_date"].min(),
            "observation_to": group["report_date"].max(),
            "available_from": group["available_date"].min(),
            "available_to": group["available_date"].max(),
            "observed_reports": int(group["report_date"].nunique()),
            "ticker_count": int(group["ticker"].nunique()),
            "ticker_set": ";".join(tickers),
            "identity_status": "resolved" if len(issuers) == 1 and ciks and cusips else "unresolved_identity",
            "identity_issue": ";".join(matching_issues),
        })
    identities = pd.DataFrame(identity_rows, columns=IDENTITY_COLUMNS)
    return SecurityUniverse(
        identities=identities.sort_values("security_id").reset_index(drop=True),
        observations=obs.sort_values(["selection_date", "ticker", "security_id"]).reset_index(drop=True),
        lifecycle_aliases=_lifecycle_alias_frame(lifecycle),
        issues=pd.DataFrame(issues, columns=[
            "issue_type", "security_id", "issuer_id", "ticker", "cik", "cusip", "report_date", "detail"
        ]),
    )


def build_evidence_plan(
    universe: SecurityUniverse,
    *,
    sic_selection: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Create one review/fetch plan row per historical security identity.

    Existing SIC headers are used only to locate a possible first-party annual
    filing. SIC itself is never converted into a risk-chain label. Quarterly
    filings are intentionally not selected because they do not provide the
    standardized business sections required by the review contract.
    """
    sic = None
    if sic_selection is not None and not sic_selection.empty:
        required = {"ticker", "cik", "available_date", "accession_number", "source_url"}
        missing = sorted(required - set(sic_selection.columns))
        if missing:
            raise NdxTaxonomyError(f"SIC plan missing columns: {missing}")
        sic = sic_selection.copy()
        sic["ticker"] = sic["ticker"].map(normalize_ticker)
        sic["cik"] = sic["cik"].map(normalize_cik)
        sic["available_date"] = [
            normalize_date(value, field="sic.available_date", allow_blank=False)
            for value in sic["available_date"]
        ]
        sic["accession_number"] = sic["accession_number"].astype(str).str.strip()
        if "form" not in sic.columns:
            sic["form"] = ""
        sic["form"] = sic["form"].astype(str).str.strip().str.upper()
        sic = sic.sort_values(["available_date", "ticker", "accession_number"])

    rows = []
    for identity in universe.identities.itertuples(index=False):
        candidates = pd.DataFrame()
        if sic is not None:
            candidates = sic[
                (sic["cik"] == str(identity.cik))
                | (sic["ticker"].isin(str(identity.ticker).split(";")))
            ].copy()
        start = str(identity.observation_from)
        if candidates.empty:
            candidate = None
            point_in_time = False
        else:
            annual = candidates[
                candidates["form"].isin({"10-K", "20-F", "40-F"})
            ]
            annual_amendments = candidates[
                candidates["form"].isin({"10-K/A", "20-F/A", "40-F/A"})
            ]
            eligible = annual[annual["available_date"] <= start]
            eligible_amendments = annual_amendments[
                annual_amendments["available_date"] <= start
            ]
            point_in_time = not eligible.empty or not eligible_amendments.empty
            if not eligible.empty:
                candidate = eligible.iloc[-1]
            elif not eligible_amendments.empty:
                candidate = eligible_amendments.iloc[-1]
            elif not annual.empty:
                candidate = annual.iloc[0]
            elif not annual_amendments.empty:
                candidate = annual_amendments.iloc[0]
            else:
                candidate = None
        accession = str(candidate["accession_number"]) if candidate is not None else ""
        source_url = str(candidate["source_url"]) if candidate is not None else ""
        filing_available = str(candidate["available_date"]) if candidate is not None else ""
        form = str(candidate.get("form") or "") if candidate is not None else ""
        index_url = ""
        if accession and normalize_cik(identity.cik):
            try:
                index_url = filing_directory_url(int(str(identity.cik)), accession)
            except Exception:
                index_url = ""
        if identity.identity_status != "resolved":
            plan_status = "identity_unresolved"
        elif candidate is None:
            plan_status = "needs_annual_sec_filing_plan"
        elif point_in_time:
            plan_status = "ready_for_point_in_time_review"
        else:
            plan_status = "source_after_observation_start"
        job_key = "|".join([str(identity.issuer_id), accession, index_url or source_url])
        job_id = hashlib.sha256(job_key.encode("utf-8")).hexdigest()[:16]
        rows.append({
            "job_id": job_id,
            "security_id": identity.security_id,
            "issuer_id": identity.issuer_id,
            "ticker": identity.ticker,
            "cik": identity.cik,
            "cusip": identity.cusip,
            "observation_from": identity.observation_from,
            "observation_to": identity.observation_to,
            "evidence_required_from": start,
            "accession_number": accession,
            "form": form,
            "source_available_date": filing_available,
            "source_url": source_url,
            "sec_index_url": index_url,
            "source_role": "candidate_sec_filing_business_description",
            "classification_allowed": False,
            "point_in_time_for_observation_start": point_in_time,
            "plan_status": plan_status,
            "review_note": (
                "SIC/header is locator evidence only; manual business-description review is required."
            ),
        })
    columns = [
        "job_id", "security_id", "issuer_id", "ticker", "cik", "cusip",
        "observation_from", "observation_to", "evidence_required_from",
        "accession_number", "form", "source_available_date", "source_url",
        "sec_index_url", "source_role", "classification_allowed",
        "point_in_time_for_observation_start", "plan_status", "review_note",
    ]
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["plan_status", "issuer_id", "security_id"], kind="stable"
    ).reset_index(drop=True)


def _column_aliases() -> dict[str, str]:
    return {
        "security": "security_id",
        "证券编号": "security_id",
        "issuer": "issuer_id",
        "发行人编号": "issuer_id",
        "股票代码": "ticker",
        "source_type": "evidence_source_type",
        "证据类型": "evidence_source_type",
        "source": "evidence_source",
        "证据来源": "evidence_source",
        "source_url": "evidence_locator",
        "来源地址": "evidence_locator",
        "available_date": "evidence_available_date",
        "证据可用日": "evidence_available_date",
        "risk_chain_id": "risk_chain",
        "风险链": "risk_chain",
        "start_date": "effective_from",
        "起始日": "effective_from",
        "end_date": "effective_to",
        "结束日": "effective_to",
        "excerpt": "evidence_excerpt",
        "证据摘录": "evidence_excerpt",
        "状态": "status",
        "置信度": "confidence",
        "备注": "notes",
    }


def load_evidence_csv(path: str | Path | None) -> pd.DataFrame:
    if path is None or not str(path).strip():
        return empty_evidence_frame()
    target = Path(path)
    if not target.exists():
        raise NdxTaxonomyError(f"evidence CSV missing: {target}")
    frame = pd.read_csv(target, low_memory=False, keep_default_na=False)
    aliases = _column_aliases()
    frame = frame.rename(columns={column: aliases.get(str(column), str(column)) for column in frame.columns})
    if frame.empty:
        return empty_evidence_frame()
    for column in EVIDENCE_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[EVIDENCE_COLUMNS].copy()


def _official_locator_valid(source_type: str, locator: str) -> bool:
    if not locator.startswith("https://"):
        return False
    lower = locator.lower()
    if source_type == "sec_filing_business_description":
        return "sec.gov/" in lower or lower.endswith("sec.gov")
    if source_type == "nasdaq_official_material":
        return "nasdaq.com/" in lower or lower.endswith("nasdaq.com")
    return True


def _evidence_id(row: Mapping[str, object], index: int) -> str:
    supplied = str(row.get("evidence_id") or "").strip()
    if supplied:
        return supplied
    payload = {
        key: str(row.get(key) or "").strip()
        for key in EVIDENCE_COLUMNS
        if key not in {"evidence_id", "notes"}
    }
    return f"evidence:{hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()[:16]}:{index}"


def normalize_and_expand_evidence(
    evidence: pd.DataFrame,
    universe: SecurityUniverse,
    taxonomy: Mapping[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize evidence and expand issuer-scoped rows to security rows.

    Invalid rows are retained in the issue table and are never allowed to
    classify an observation.  This makes manual review auditable instead of
    silently dropping bad evidence.
    """
    if evidence is None or evidence.empty:
        columns = [*EVIDENCE_COLUMNS, "validation_status", "validation_reason", "scope"]
        return pd.DataFrame(columns=columns), pd.DataFrame(columns=[
            "evidence_id", "security_id", "issuer_id", "ticker", "reason", "status"
        ])
    categories = set((taxonomy.get("risk_chains") or {}).keys())
    identity_by_security = universe.identities.set_index("security_id", drop=False)
    security_by_issuer = universe.identities.groupby("issuer_id")["security_id"].apply(list).to_dict()
    security_by_ticker: dict[str, list[str]] = {}
    for row in universe.identities.itertuples(index=False):
        for ticker in str(row.ticker).split(";"):
            security_by_ticker.setdefault(normalize_ticker(ticker), []).append(row.security_id)
    for row in universe.lifecycle_aliases.itertuples(index=False):
        security_by_ticker.setdefault(normalize_ticker(row.recognized_ticker), []).append(row.security_id)
    security_by_ticker = {
        key: sorted(set(value)) for key, value in security_by_ticker.items()
    }
    output = []
    issues = []
    for index, raw in enumerate(evidence.to_dict(orient="records")):
        base = {column: str(raw.get(column) or "").strip() for column in EVIDENCE_COLUMNS}
        base["evidence_id"] = _evidence_id(base, index)
        base["ticker"] = normalize_ticker(base["ticker"])
        base["risk_chain"] = str(base["risk_chain"] or "").strip().lower()
        base["evidence_source_type"] = str(base["evidence_source_type"] or "").strip().lower()
        base["confidence"] = str(base["confidence"] or "").strip().lower()
        base["status"] = str(base["status"] or "pending_review").strip().lower()
        base["effective_from"] = normalize_date(base["effective_from"], field="effective_from") or ""
        base["effective_to"] = normalize_date(base["effective_to"], field="effective_to") or ""
        base["evidence_available_date"] = normalize_date(
            base["evidence_available_date"], field="evidence_available_date"
        ) or ""
        targets: list[str] = []
        scope = "security"
        supplied_security = str(base["security_id"] or "").strip()
        supplied_issuer = str(base["issuer_id"] or "").strip()
        if supplied_security:
            targets = [supplied_security]
        elif supplied_issuer:
            targets = list(security_by_issuer.get(supplied_issuer, []))
            scope = "issuer"
        elif base["ticker"]:
            targets = list(security_by_ticker.get(base["ticker"], []))
            scope = "ticker_or_lifecycle_alias"
        if not targets:
            issues.append({
                "evidence_id": base["evidence_id"],
                "security_id": supplied_security,
                "issuer_id": supplied_issuer,
                "ticker": base["ticker"],
                "reason": "evidence_target_not_in_historical_identity_universe",
                "status": "rejected",
            })
            continue
        for security_id in sorted(set(targets)):
            row = dict(base)
            row["security_id"] = security_id
            identity = (
                identity_by_security.loc[security_id]
                if security_id in identity_by_security.index
                else None
            )
            reason_parts = []
            if identity is None:
                reason_parts.append("security_id_not_in_identity_universe")
            else:
                expected_issuer = str(identity.issuer_id)
                if supplied_issuer and supplied_issuer != expected_issuer:
                    reason_parts.append("issuer_id_security_id_mismatch")
                row["issuer_id"] = expected_issuer
                if not row["ticker"]:
                    row["ticker"] = str(identity.ticker)
            if row["status"] == "accepted" and row["risk_chain"] not in categories:
                reason_parts.append("unknown_risk_chain")
            elif row["status"] in {"unclassified", "pending_review", "rejected"}:
                if row["risk_chain"] not in {"", UNCLASSIFIED_CHAIN}:
                    reason_parts.append("non_unclassified_pending_chain")
            if row["evidence_source_type"] not in EVIDENCE_SOURCE_TYPES:
                reason_parts.append("unsupported_evidence_source_type")
            if row["status"] not in EVIDENCE_STATUSES:
                reason_parts.append("unsupported_status")
            if row["confidence"] not in EVIDENCE_CONFIDENCES:
                reason_parts.append("unsupported_confidence")
            if row["status"] == "accepted":
                if row["risk_chain"] in {"", UNCLASSIFIED_CHAIN}:
                    reason_parts.append("accepted_row_must_have_classification")
                if row["confidence"] not in {"high", "medium"}:
                    reason_parts.append("accepted_row_requires_high_or_medium_confidence")
                if not row["evidence_excerpt"]:
                    reason_parts.append("accepted_row_requires_evidence_excerpt")
                if not row["evidence_available_date"]:
                    reason_parts.append("accepted_row_requires_evidence_available_date")
                if not row["effective_from"]:
                    reason_parts.append("accepted_row_requires_effective_from")
                if row["evidence_available_date"] and row["effective_from"]:
                    if row["evidence_available_date"] > row["effective_from"]:
                        reason_parts.append("evidence_available_after_effective_from")
                if not _official_locator_valid(
                    row["evidence_source_type"], row["evidence_locator"]
                ):
                    reason_parts.append("evidence_locator_not_first_party_https")
            elif row["status"] == "unclassified":
                if row["risk_chain"] not in {"", UNCLASSIFIED_CHAIN}:
                    reason_parts.append("unclassified_row_has_non_unclassified_chain")
                row["risk_chain"] = UNCLASSIFIED_CHAIN
            elif row["status"] in {"pending_review", "rejected"}:
                row["risk_chain"] = UNCLASSIFIED_CHAIN
            if row["effective_from"] and row["effective_to"] and row["effective_from"] > row["effective_to"]:
                reason_parts.append("effective_interval_reversed")
            if reason_parts:
                row["validation_status"] = "rejected"
            elif row["status"] == "pending_review":
                row["validation_status"] = "pending"
            elif row["status"] == "rejected":
                row["validation_status"] = "rejected"
            else:
                row["validation_status"] = "valid"
            row["validation_reason"] = ";".join(reason_parts)
            row["scope"] = scope
            output.append(row)
            if reason_parts:
                issues.append({
                    "evidence_id": row["evidence_id"],
                    "security_id": row["security_id"],
                    "issuer_id": row["issuer_id"],
                    "ticker": row["ticker"],
                    "reason": ";".join(reason_parts),
                    "status": "rejected",
                })
    columns = [*EVIDENCE_COLUMNS, "validation_status", "validation_reason", "scope"]
    issue_columns = ["evidence_id", "security_id", "issuer_id", "ticker", "reason", "status"]
    return pd.DataFrame(output, columns=columns), pd.DataFrame(issues, columns=issue_columns)


def _date_in_interval(value: str, start: str, end: str) -> bool:
    return bool(
        (not start or value >= start)
        and (not end or value <= end)
    )


def _join_nonempty(values: Iterable[object]) -> str:
    return ";".join(sorted({str(value).strip() for value in values if str(value or "").strip()}))


def _state_for_observation(
    security_id: str,
    selection_date: str,
    identity: Mapping[str, object],
    valid_evidence: pd.DataFrame,
) -> dict:
    if str(identity.get("identity_status")) != "resolved":
        return {
            "risk_chain": UNCLASSIFIED_CHAIN,
            "status": "unclassified",
            "reason": "identity_unresolved",
            "evidence": pd.DataFrame(),
        }
    candidates = valid_evidence[
        valid_evidence["security_id"].eq(security_id)
        & valid_evidence["status"].eq("accepted")
    ].copy()
    if candidates.empty:
        return {
            "risk_chain": UNCLASSIFIED_CHAIN,
            "status": "unclassified",
            "reason": "no_reliable_evidence",
            "evidence": candidates,
        }
    applicable = candidates[
        candidates.apply(
            lambda row: _date_in_interval(
                selection_date,
                str(row.effective_from or ""),
                str(row.effective_to or ""),
            )
            and str(row.evidence_available_date or "") <= selection_date,
            axis=1,
        )
    ].copy()
    chains = sorted(set(applicable["risk_chain"]))
    if len(chains) == 1:
        return {
            "risk_chain": chains[0],
            "status": "accepted",
            "reason": "point_in_time_first_party_evidence",
            "evidence": applicable,
        }
    if len(chains) > 1:
        return {
            "risk_chain": UNCLASSIFIED_CHAIN,
            "status": "conflict",
            "reason": "conflicting_accepted_evidence",
            "evidence": applicable,
        }
    return {
        "risk_chain": UNCLASSIFIED_CHAIN,
        "status": "unclassified",
        "reason": "evidence_not_available_by_selection_date",
        "evidence": applicable,
    }


def _group_states(states: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    for state in states:
        key = (
            state["risk_chain"], state["status"], state["reason"],
            state.get("evidence_ids", ""), state.get("evidence_available_date", ""),
        )
        if groups and groups[-1][0].get("_key") == key:
            groups[-1].append(state)
        else:
            state = dict(state)
            state["_key"] = key
            groups.append([state])
    return groups


def build_taxonomy_records(
    universe: SecurityUniverse,
    taxonomy: Mapping[str, object],
    evidence: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Resolve reviewed evidence on historical observations without backfill."""
    valid = evidence[
        evidence.get("validation_status", pd.Series(dtype=str)).eq("valid")
    ].copy() if not evidence.empty else evidence.copy()
    records = []
    conflicts = []
    future_audit = []
    labels = {
        key: str(value.get("label") or "")
        for key, value in (taxonomy.get("risk_chains") or {}).items()
    }
    identity_index = universe.identities.set_index("security_id", drop=False)
    for security_id, group in universe.observations.groupby("security_id", sort=True):
        identity = identity_index.loc[security_id].to_dict()
        observation_dates = sorted(set(group["selection_date"].astype(str)))
        states = []
        for selection_date in observation_dates:
            state = _state_for_observation(
                security_id, selection_date, identity, valid
            )
            selected_evidence = state.pop("evidence")
            evidence_ids = _join_nonempty(selected_evidence["evidence_id"]) if not selected_evidence.empty else ""
            evidence_available = _join_nonempty(selected_evidence["evidence_available_date"]) if not selected_evidence.empty else ""
            state.update({
                "selection_date": selection_date,
                "evidence_ids": evidence_ids,
                "evidence_available_date": evidence_available,
            })
            if state["status"] == "conflict":
                chains = sorted(set(selected_evidence["risk_chain"]))
                conflicts.append({
                    "security_id": security_id,
                    "issuer_id": identity.get("issuer_id"),
                    "ticker": identity.get("ticker"),
                    "selection_date": selection_date,
                    "risk_chains": ";".join(chains),
                    "evidence_ids": evidence_ids,
                    "reason": "conflicting_accepted_evidence",
                })
            for ev in selected_evidence.to_dict(orient="records"):
                available = str(ev.get("evidence_available_date") or "")
                passed = bool(available and available <= selection_date)
                future_audit.append({
                    "security_id": security_id,
                    "issuer_id": identity.get("issuer_id"),
                    "ticker": identity.get("ticker"),
                    "selection_date": selection_date,
                    "evidence_id": ev.get("evidence_id"),
                    "evidence_available_date": available,
                    "effective_from": ev.get("effective_from"),
                    "effective_to": ev.get("effective_to"),
                    "future_data_guard_passed": passed,
                    "guard_rule": "evidence_available_date <= selection_date",
                })
            states.append(state)
        for state_group in _group_states(states):
            first = state_group[0]
            last = state_group[-1]
            evidence_ids = _join_nonempty(item.get("evidence_ids") for item in state_group)
            evidence_dates = _join_nonempty(
                date for item in state_group for date in str(item.get("evidence_available_date") or "").split(";")
            )
            ev_rows = valid[valid["evidence_id"].isin(evidence_ids.split(";") if evidence_ids else [])]
            records.append({
                "security_id": security_id,
                "issuer_id": identity.get("issuer_id"),
                "ticker": identity.get("ticker"),
                "cik": identity.get("cik"),
                "cusip": identity.get("cusip"),
                "effective_from": first["selection_date"],
                "effective_to": last["selection_date"],
                "selection_date_start": first["selection_date"],
                "selection_date_end": last["selection_date"],
                "selection_dates": ";".join(item["selection_date"] for item in state_group),
                "observations_count": len(state_group),
                "risk_chain": first["risk_chain"],
                "risk_chain_label": labels.get(first["risk_chain"], labels.get(UNCLASSIFIED_CHAIN, "未分类")),
                "evidence_source": _join_nonempty(ev_rows["evidence_source"]) if not ev_rows.empty else "",
                "evidence_source_type": _join_nonempty(ev_rows["evidence_source_type"]) if not ev_rows.empty else "",
                "evidence_locator": _join_nonempty(ev_rows["evidence_locator"]) if not ev_rows.empty else "",
                "evidence_available_date": evidence_dates,
                "evidence_ids": evidence_ids,
                "confidence": _join_nonempty(ev_rows["confidence"]) if not ev_rows.empty else "",
                "status": first["status"],
                "reason": first["reason"],
            })
    return (
        pd.DataFrame(records, columns=RECORD_COLUMNS).sort_values(
            ["security_id", "effective_from"], kind="stable"
        ).reset_index(drop=True),
        pd.DataFrame(conflicts),
        pd.DataFrame(future_audit),
    )


def build_coverage_report(
    universe: SecurityUniverse,
    records: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for identity in universe.identities.itertuples(index=False):
        subset = records[records["security_id"].eq(identity.security_id)]
        classified = subset[subset["status"].eq("accepted")]
        conflicts = subset[subset["status"].eq("conflict")]
        observed = int(universe.observations["security_id"].eq(identity.security_id).sum())
        classified_observations = int(classified["observations_count"].sum()) if not classified.empty else 0
        conflict_observations = int(conflicts["observations_count"].sum()) if not conflicts.empty else 0
        rows.append({
            "security_id": identity.security_id,
            "issuer_id": identity.issuer_id,
            "ticker": identity.ticker,
            "cik": identity.cik,
            "cusip": identity.cusip,
            "observations": observed,
            "classified_observations": classified_observations,
            "conflict_observations": conflict_observations,
            "unclassified_observations": max(0, observed - classified_observations),
            "classification_coverage": classified_observations / observed if observed else 0.0,
            "identity_status": identity.identity_status,
        })
    detail = pd.DataFrame(rows)
    summary = pd.DataFrame([
        {
            "scope": "historical_ndx_union",
            "historical_ticker_count": int(universe.observations["ticker"].nunique()),
            "security_count": int(universe.identities["security_id"].nunique()),
            "issuer_count": int(universe.identities["issuer_id"].nunique()),
            "classified_ticker_count": int(detail.loc[detail.classified_observations.gt(0), "ticker"].nunique()),
            "classified_security_count": int(detail.loc[detail.classified_observations.gt(0), "security_id"].nunique()),
            "unclassified_security_count": int(detail.loc[detail.classified_observations.eq(0), "security_id"].nunique()),
            "conflict_security_count": int(detail.loc[detail.conflict_observations.gt(0), "security_id"].nunique()),
            "observation_count": int(detail.observations.sum()),
            "classified_observation_count": int(detail.classified_observations.sum()),
            "future_data_guard_passed": True,
            "return_data_read": False,
        }
    ])
    return summary, detail


def taxonomy_digest(
    taxonomy: Mapping[str, object],
    universe: SecurityUniverse,
    evidence: pd.DataFrame,
) -> str:
    payload = {
        "taxonomy_version": taxonomy.get("version_id"),
        "identity_sha256": hashlib.sha256(
            universe.identities.to_csv(index=False).encode("utf-8")
        ).hexdigest(),
        "evidence_sha256": hashlib.sha256(
            evidence.to_csv(index=False).encode("utf-8")
        ).hexdigest(),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def empty_fetch_attempts() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "job_id", "issuer_id", "cik", "accession_number", "status",
        "index_url", "document_url", "raw_path", "content_bytes",
        "content_sha256", "attempted_at", "error",
    ])


def select_business_document(index_payload: Mapping[str, object], form: str = "") -> dict:
    """Choose a primary HTML filing document only when the SEC index is clear."""
    directory = index_payload.get("directory")
    if not isinstance(directory, Mapping):
        raise NdxTaxonomyError("SEC filing index lacks directory metadata")
    items = directory.get("item")
    if not isinstance(items, list):
        raise NdxTaxonomyError("SEC filing index lacks item list")
    candidates = []
    wanted = str(form or "").upper().replace("/A", "")
    for item in items:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        lower = name.lower()
        item_type = str(item.get("type") or "").upper()
        description = str(item.get("description") or "").upper()
        if not lower.endswith((".htm", ".html")):
            continue
        if wanted and wanted not in {item_type.replace("/A", ""), description.replace("/A", "")}:
            if wanted not in description and wanted not in item_type:
                continue
        if any(token in lower for token in ("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml")):
            continue
        candidates.append(dict(item))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise NdxTaxonomyError("SEC filing index has no unambiguous primary HTML document")
    candidates.sort(key=lambda item: int(item.get("size") or 0), reverse=True)
    if len(candidates) >= 2 and int(candidates[0].get("size") or 0) == int(candidates[1].get("size") or 0):
        raise NdxTaxonomyError("SEC filing index has tied primary HTML documents")
    return candidates[0]


class _SecIndexHtmlParser(HTMLParser):
    """Extract document rows from the SEC filing index HTML table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, str]]] = []
        self._row: list[dict[str, str]] | None = None
        self._cell_text: list[str] | None = None
        self._cell_href = ""
        self._in_anchor = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
            self._cell_text = None
            self._cell_href = ""
            self._in_anchor = False
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_text = []
            self._cell_href = ""
            self._in_anchor = False
        elif tag == "a" and self._cell_text is not None:
            self._in_anchor = True
            self._cell_href = next(
                (str(value or "") for key, value in attrs if key.lower() == "href"),
                "",
            )

    def handle_data(self, data: str) -> None:
        if self._cell_text is not None:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "a":
            self._in_anchor = False
        elif tag in {"td", "th"} and self._row is not None and self._cell_text is not None:
            self._row.append({
                "text": unescape(" ".join("".join(self._cell_text).split())),
                "href": self._cell_href,
            })
            self._cell_text = None
            self._cell_href = ""
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell_text = None
            self._cell_href = ""
            self._in_anchor = False


def select_business_document_from_index_html(html_content: str | bytes, form: str = "") -> dict:
    """Select a primary document from the SEC archive's official index HTML.

    Some older SEC ``index.json`` files expose every directory item as
    ``text.gif`` and omit the filing form.  The companion official index HTML
    still carries the form, document name, and size in its document table.
    This parser is used only as a fallback and remains fail-closed on ties or
    missing form matches.
    """
    if isinstance(html_content, bytes):
        html_content = html_content.decode("utf-8", errors="replace")
    parser = _SecIndexHtmlParser()
    parser.feed(str(html_content))
    wanted = str(form or "").upper().replace("/A", "")
    candidates = []
    for row in parser.rows:
        if len(row) < 4:
            continue
        description = row[1]["text"].upper().replace("/A", "")
        document_cell = row[2]
        document_type = row[3]["text"].upper().replace("/A", "")
        if wanted and wanted not in {description, document_type}:
            continue
        href = document_cell.get("href", "")
        query_doc = parse_qs(urlparse(href).query).get("doc", [""])[0]
        document_path = query_doc or href
        name = Path(unquote(document_path.split("?", 1)[0])).name
        if not name.lower().endswith((".htm", ".html")):
            continue
        lower = name.lower()
        if any(token in lower for token in ("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml")):
            continue
        size_match = re.search(r"[0-9][0-9,]*", row[4]["text"] if len(row) >= 5 else "")
        size = int(size_match.group(0).replace(",", "")) if size_match else 0
        candidates.append({
            "name": name,
            "type": document_type,
            "description": description,
            "size": size,
            "source": "sec_index_html",
        })
    if not candidates:
        raise NdxTaxonomyError("SEC filing index HTML has no matching primary HTML document")
    if len(candidates) == 1:
        return candidates[0]
    candidates.sort(key=lambda item: int(item.get("size") or 0), reverse=True)
    if int(candidates[0].get("size") or 0) == int(candidates[1].get("size") or 0):
        raise NdxTaxonomyError("SEC filing index HTML has tied primary HTML documents")
    return candidates[0]
