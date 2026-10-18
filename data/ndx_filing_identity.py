"""SEC filing-level share identity evidence for point-in-time NDX research."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd
from lxml import etree

from data.ndx_sic_history import normalize_accession


FILING_IDENTITY_POLICY_ID = "ndx_sec_filing_share_identity_v1"
FILING_SHARE_RESOLUTION_POLICY_ID = "ndx_sec_filing_share_resolution_v1"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
EXCLUDED_SHARE_CONCEPT_TOKENS = (
    "weightedaverage",
    "preferred",
    "option",
    "warrant",
    "award",
    "plan",
)
SHARE_STOCK_CONCEPT_PRIORITY = (
    "EntityCommonStockSharesOutstanding",
    "CommonStockSharesOutstanding",
    "NumberOfSharesOutstanding",
    "SharesOutstanding",
    "CommonStockSharesOutstandingNetOfTreasuryStockCommonShares",
)
CLASS_AXES = (
    "StatementClassOfStockAxis",
    "ClassesOfShareCapitalAxis",
)


class NdxFilingIdentityError(ValueError):
    """Raised when filing-level identity evidence cannot be audited safely."""


@dataclass(frozen=True)
class FilingShareResolutionPolicy:
    maximum_domestic_share_age_days: int = 200
    existing_value_tolerance: float = 0.05

    def validate(self) -> None:
        if self.maximum_domestic_share_age_days < 1:
            raise NdxFilingIdentityError("maximum share age must be positive")
        if not 0 < self.existing_value_tolerance < 1:
            raise NdxFilingIdentityError("existing value tolerance must be in (0, 1)")


def _normalized_cik(value: object) -> int:
    raw = str(value or "").strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    if not raw.isdigit() or int(raw) <= 0:
        raise NdxFilingIdentityError(f"invalid CIK: {value!r}")
    return int(raw)


def filing_directory_url(cik: object, accession: str) -> str:
    normalized = normalize_accession(accession)
    return (
        f"{SEC_ARCHIVES_BASE}/{_normalized_cik(cik)}/"
        f"{normalized.replace('-', '')}/index.json"
    )


def filing_document_url(cik: object, accession: str, filename: str) -> str:
    normalized = normalize_accession(accession)
    name = str(filename or "").strip()
    if not name or Path(name).name != name or not re.fullmatch(
        r"[A-Za-z0-9_.-]+", name
    ):
        raise NdxFilingIdentityError(f"unsafe SEC filing filename: {filename!r}")
    return (
        f"{SEC_ARCHIVES_BASE}/{_normalized_cik(cik)}/"
        f"{normalized.replace('-', '')}/{name}"
    )


def select_xbrl_instance(index_payload: Mapping[str, object]) -> dict:
    """Select only an explicit filing XBRL instance; never guess an HTML file."""
    directory = index_payload.get("directory")
    if not isinstance(directory, Mapping):
        raise NdxFilingIdentityError("SEC filing index lacks directory metadata")
    items = directory.get("item")
    if not isinstance(items, list):
        raise NdxFilingIdentityError("SEC filing index lacks file items")
    rows = [item for item in items if isinstance(item, Mapping)]
    exact = [
        item for item in rows
        if str(item.get("name") or "").lower().endswith("_htm.xml")
    ]
    if len(exact) == 1:
        return dict(exact[0]) | {"selection_method": "explicit_inline_xbrl_instance"}
    if len(exact) > 1:
        raise NdxFilingIdentityError("multiple explicit _htm.xml instances found")
    candidates = []
    for item in rows:
        name = str(item.get("name") or "")
        lower = name.lower()
        if not lower.endswith(".xml"):
            continue
        if lower in {"filingsummary.xml", "metalinks.json"}:
            continue
        if re.search(r"_(cal|def|lab|pre)\.xml$", lower):
            continue
        candidates.append(item)
    if len(candidates) == 1:
        return dict(candidates[0]) | {"selection_method": "sole_xbrl_xml_candidate"}
    raise NdxFilingIdentityError(
        f"explicit XBRL instance is ambiguous or missing: {len(candidates)} candidates"
    )


def build_filing_identity_plan(
    valuation_readiness: pd.DataFrame,
    sic_selection: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    readiness_required = {
        "selection_date",
        "ticker",
        "cik",
        "shares_ready",
        "multi_security_issuer",
        "foreign_filer_asof",
    }
    sic_required = {
        "selection_date",
        "ticker",
        "cik",
        "accession_number",
        "form",
        "filed_date",
        "available_date",
        "sic_future_data_guard_passed",
    }
    missing_readiness = sorted(readiness_required - set(valuation_readiness.columns))
    missing_sic = sorted(sic_required - set(sic_selection.columns))
    if missing_readiness or missing_sic:
        raise NdxFilingIdentityError(
            f"filing identity inputs missing: readiness={missing_readiness} "
            f"sic={missing_sic}"
        )
    readiness = valuation_readiness.copy()
    for column in ("shares_ready", "multi_security_issuer", "foreign_filer_asof"):
        readiness[column] = readiness[column].fillna(False).astype(bool)
    mask = (
        ~readiness["shares_ready"]
        | readiness["multi_security_issuer"]
        | readiness["foreign_filer_asof"]
    )
    selected = readiness.loc[mask, sorted(readiness_required)].copy()
    keys = ["selection_date", "ticker", "cik"]
    sic = sic_selection[[
        *keys,
        "accession_number",
        "form",
        "filed_date",
        "available_date",
        "sic_future_data_guard_passed",
    ]].copy()
    mapped = selected.merge(sic, on=keys, how="left", validate="one_to_one")
    if mapped[[
        "accession_number",
        "form",
        "filed_date",
        "available_date",
    ]].isna().any().any():
        raise NdxFilingIdentityError("filing identity plan has unmapped SEC accessions")
    future_guard = (
        mapped["sic_future_data_guard_passed"].fillna(False).astype(bool)
        & (mapped["available_date"].astype(str) <= mapped["selection_date"].astype(str))
    )
    if not bool(future_guard.all()):
        raise NdxFilingIdentityError("filing identity plan uses future SEC evidence")
    mapped["filing_future_data_guard_passed"] = future_guard
    mapped["accession_number"] = mapped["accession_number"].map(normalize_accession)
    mapped["identity_reason"] = [
        ";".join([
            reason
            for condition, reason in (
                (not bool(row.shares_ready), "shares_not_ready"),
                (bool(row.multi_security_issuer), "multi_security_issuer"),
                (bool(row.foreign_filer_asof), "foreign_filer_fx_or_adr"),
            )
            if condition
        ])
        for row in mapped.itertuples(index=False)
    ]
    jobs = mapped.groupby(
        ["cik", "accession_number", "form", "filed_date", "available_date"],
        as_index=False,
    ).agg(
        first_selection_date=("selection_date", "min"),
        last_selection_date=("selection_date", "max"),
        selection_rows=("selection_date", "size"),
        tickers=("ticker", lambda values: ";".join(sorted(set(values)))),
        identity_reasons=(
            "identity_reason",
            lambda values: ";".join(sorted({part for value in values for part in value.split(";")})),
        ),
    )
    jobs["cik"] = jobs["cik"].map(_normalized_cik)
    jobs["index_url"] = [
        filing_directory_url(row.cik, row.accession_number)
        for row in jobs.itertuples(index=False)
    ]
    jobs["job_id"] = [
        hashlib.sha256(
            f"{row.cik}|{row.accession_number}|{row.index_url}".encode("ascii")
        ).hexdigest()[:16]
        for row in jobs.itertuples(index=False)
    ]
    return (
        jobs.sort_values(["cik", "accession_number"], kind="stable").reset_index(
            drop=True
        ),
        mapped.sort_values(["selection_date", "ticker"], kind="stable").reset_index(
            drop=True
        ),
    )


def _local_name(value: object) -> str:
    text = str(value or "")
    return text.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _namespace(value: object) -> str:
    text = str(value or "")
    return text[1:].split("}", 1)[0] if text.startswith("{") else ""


def _attribute(element: etree._Element, name: str) -> str | None:
    target = name.lower()
    for key, value in element.attrib.items():
        if _local_name(key).lower() == target:
            return str(value)
    return None


def _fact_number(element: etree._Element) -> tuple[str, float] | None:
    if str(_attribute(element, "nil") or "").lower() in {"true", "1"}:
        return None
    raw = "".join(element.itertext()).replace("\u00a0", " ").strip()
    compact = re.sub(r"[\s,$]", "", raw)
    if not compact or compact in {"-", "--"}:
        return None
    negative = compact.startswith("(") and compact.endswith(")")
    if negative:
        compact = compact[1:-1]
    try:
        value = float(compact)
    except ValueError:
        return None
    scale_raw = _attribute(element, "scale")
    scale = int(scale_raw) if scale_raw not in (None, "") else 0
    sign = -1.0 if str(_attribute(element, "sign") or "") == "-" else 1.0
    if negative:
        sign *= -1.0
    return raw, sign * value * (10.0 ** scale)


def _share_candidate(concept: str) -> bool:
    normalized = re.sub(r"[^a-z]", "", concept.lower())
    if "sharesoutstanding" not in normalized:
        return False
    return not any(token in normalized for token in EXCLUDED_SHARE_CONCEPT_TOKENS)


def parse_filing_share_facts(
    content: bytes | str,
    *,
    cik: object,
    accession_number: str,
    source_url: str,
) -> pd.DataFrame:
    """Extract dimensional outstanding-share candidates from XBRL or inline XBRL."""
    raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    parser = etree.XMLParser(recover=True, huge_tree=True, resolve_entities=False)
    try:
        root = etree.fromstring(raw, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise NdxFilingIdentityError("filing XBRL cannot be parsed") from exc
    if root is None:
        raise NdxFilingIdentityError("filing XBRL root is missing")
    contexts: dict[str, dict] = {}
    units: dict[str, str] = {}
    for element in root.iter():
        local = _local_name(element.tag).lower()
        if local == "context":
            context_id = str(element.get("id") or "").strip()
            if not context_id:
                continue
            instant = ""
            identifier = ""
            dimensions = []
            for child in element.iter():
                child_local = _local_name(child.tag).lower()
                if child_local == "instant":
                    instant = str(child.text or "").strip()
                elif child_local == "identifier":
                    identifier = str(child.text or "").strip()
                elif child_local in {"explicitmember", "typedmember"}:
                    dimensions.append({
                        "axis": str(_attribute(child, "dimension") or ""),
                        "member": "".join(child.itertext()).strip(),
                    })
            contexts[context_id] = {
                "period_end": instant,
                "entity_identifier": identifier,
                "dimensions": dimensions,
            }
        elif local == "unit":
            unit_id = str(element.get("id") or "").strip()
            measures = [
                str(child.text or "").strip()
                for child in element.iter()
                if _local_name(child.tag).lower() == "measure"
            ]
            if unit_id:
                units[unit_id] = ";".join(value for value in measures if value)
    rows = []
    for element in root.iter():
        local = _local_name(element.tag)
        inline = local.lower() == "nonfraction"
        concept_raw = _attribute(element, "name") if inline else local
        concept = _local_name(concept_raw)
        if not _share_candidate(concept):
            continue
        context_ref = _attribute(element, "contextref")
        unit_ref = _attribute(element, "unitref")
        number = _fact_number(element)
        if not context_ref or number is None:
            continue
        context = contexts.get(context_ref, {})
        dimensions = context.get("dimensions") or []
        value = float(number[1])
        if not np.isfinite(value) or value <= 0:
            continue
        entity_identifier = str(context.get("entity_identifier") or "")
        entity_matches = bool(
            not entity_identifier
            or re.sub(r"\D", "", entity_identifier).lstrip("0")
            == str(_normalized_cik(cik))
        )
        rows.append({
            "cik": _normalized_cik(cik),
            "accession_number": normalize_accession(accession_number),
            "concept_namespace": (
                _namespace(element.tag) if not inline else str(concept_raw).split(":", 1)[0]
            ),
            "concept": concept,
            "context_ref": context_ref,
            "period_end": str(context.get("period_end") or "")[:10],
            "entity_identifier": entity_identifier,
            "entity_identifier_matches_cik": entity_matches,
            "unit_ref": unit_ref or "",
            "unit_measure": units.get(unit_ref or "", ""),
            "raw_value": number[0],
            "value": value,
            "decimals": str(_attribute(element, "decimals") or ""),
            "scale": str(_attribute(element, "scale") or ""),
            "dimensions_count": len(dimensions),
            "dimensions_json": json.dumps(
                dimensions,
                ensure_ascii=False,
                sort_keys=True,
            ),
            "source_url": source_url,
        })
    columns = [
        "cik",
        "accession_number",
        "concept_namespace",
        "concept",
        "context_ref",
        "period_end",
        "entity_identifier",
        "entity_identifier_matches_cik",
        "unit_ref",
        "unit_measure",
        "raw_value",
        "value",
        "decimals",
        "scale",
        "dimensions_count",
        "dimensions_json",
        "source_url",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(rows, columns=columns).drop_duplicates(
        ["cik", "accession_number", "concept", "context_ref", "value"]
    )
    return frame.sort_values(
        ["cik", "accession_number", "period_end", "concept", "context_ref"],
        kind="stable",
    ).reset_index(drop=True)


def _class_dimension_rows(frame: pd.DataFrame) -> tuple[list[float], list[str], str]:
    candidates = []
    for row in frame.itertuples(index=False):
        try:
            dimensions = json.loads(str(row.dimensions_json or "[]"))
        except json.JSONDecodeError:
            return [], [], "invalid_dimensions_json"
        classes = [
            item
            for item in dimensions
            if any(str(item.get("axis") or "").endswith(axis) for axis in CLASS_AXES)
        ]
        if len(classes) != 1:
            continue
        member = str(classes[0].get("member") or "")
        if not member or "preferred" in member.lower():
            continue
        candidates.append({
            "member": member,
            "value": float(row.value),
            "dimension_count": len(dimensions),
        })
    if not candidates:
        return [], [], "common_class_dimension_missing"
    table = pd.DataFrame(candidates)
    values = []
    members = []
    for member, group in table.groupby("member", sort=True):
        minimum_dimensions = int(group["dimension_count"].min())
        preferred = group[group["dimension_count"].eq(minimum_dimensions)]
        unique = sorted(set(preferred["value"].round(6)))
        if len(unique) != 1:
            return [], [], f"ambiguous_class_value:{member}"
        values.append(float(unique[0]))
        members.append(str(member))
    return values, members, "ready"


def resolve_filing_share_rows(
    identity_selection: pd.DataFrame,
    facts: pd.DataFrame,
    jobs: pd.DataFrame,
    valuation_readiness: pd.DataFrame,
    *,
    policy: FilingShareResolutionPolicy | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Resolve issuer shares while keeping foreign/ADR and multi-security gates closed."""
    selected = policy or FilingShareResolutionPolicy()
    selected.validate()
    keys = ["selection_date", "ticker", "cik"]
    identity_required = set(keys)
    readiness_required = {
        *keys,
        "shares_ready",
        "shares_value",
        "foreign_filer_asof",
        "multi_security_issuer",
    }
    fact_required = {
        "cik",
        "accession_number",
        "concept",
        "period_end",
        "unit_measure",
        "value",
        "entity_identifier_matches_cik",
        "dimensions_count",
        "dimensions_json",
        "source_url",
    }
    job_required = {"cik", "accession_number", "available_date", "form"}
    missing = {
        "identity": sorted(identity_required - set(identity_selection.columns)),
        "readiness": sorted(readiness_required - set(valuation_readiness.columns)),
        "facts": sorted(fact_required - set(facts.columns)),
        "jobs": sorted(job_required - set(jobs.columns)),
    }
    if any(missing.values()):
        raise NdxFilingIdentityError(f"filing share inputs missing: {missing}")
    identity = identity_selection[keys].copy()
    readiness = valuation_readiness[sorted(readiness_required)].copy()
    plan = identity.merge(readiness, on=keys, how="left", validate="one_to_one")
    if plan[["shares_ready", "foreign_filer_asof", "multi_security_issuer"]].isna().any().any():
        raise NdxFilingIdentityError("filing share plan does not match valuation readiness")
    candidates = facts[facts["concept"].isin(SHARE_STOCK_CONCEPT_PRIORITY)].copy()
    candidates = candidates[
        candidates["unit_measure"].astype(str).str.lower().eq("shares")
        & candidates["period_end"].notna()
        & candidates["entity_identifier_matches_cik"].fillna(False).astype(bool)
    ].copy()
    candidates["period_end"] = pd.to_datetime(candidates["period_end"], errors="coerce")
    candidates = candidates[candidates["period_end"].notna()].copy()
    job_meta = jobs[["cik", "accession_number", "available_date", "form"]].drop_duplicates()
    job_meta["available_date"] = pd.to_datetime(job_meta["available_date"], errors="coerce")
    if job_meta["available_date"].isna().any():
        raise NdxFilingIdentityError("filing jobs contain invalid available dates")
    candidates = candidates.merge(
        job_meta,
        on=["cik", "accession_number"],
        how="left",
        validate="many_to_one",
    )
    if candidates["available_date"].isna().any():
        raise NdxFilingIdentityError("share facts lack filing availability metadata")
    priority = {
        concept: index for index, concept in enumerate(SHARE_STOCK_CONCEPT_PRIORITY)
    }
    candidates["concept_priority"] = candidates["concept"].map(priority)
    output = []
    failures = []
    for row in plan.itertuples(index=False):
        selection_date = pd.Timestamp(row.selection_date).normalize()
        eligible = candidates[
            candidates["cik"].eq(int(row.cik))
            & candidates["available_date"].le(selection_date)
            & candidates["period_end"].lt(selection_date)
        ].copy()
        resolved_value = np.nan
        accession = ""
        available_date = pd.NaT
        period_end = pd.NaT
        form = ""
        concept = ""
        method = ""
        members: list[str] = []
        status = "qualified_stock_fact_missing"
        if not eligible.empty:
            available_date = eligible["available_date"].max()
            filing = eligible[eligible["available_date"].eq(available_date)].copy()
            minimum_priority = int(filing["concept_priority"].min())
            filing = filing[filing["concept_priority"].eq(minimum_priority)].copy()
            period_end = filing["period_end"].max()
            filing = filing[filing["period_end"].eq(period_end)].copy()
            accession_values = sorted(set(filing["accession_number"].astype(str)))
            if len(accession_values) != 1:
                status = "ambiguous_filing_accession"
            else:
                accession = accession_values[0]
                form = str(filing["form"].iloc[0])
                concept = str(filing["concept"].iloc[0])
                aggregate = filing[filing["dimensions_count"].eq(0)]
                aggregate_values = sorted(set(aggregate["value"].round(6)))
                if len(aggregate_values) == 1:
                    resolved_value = float(aggregate_values[0])
                    method = "dimensionless_issuer_aggregate"
                    status = "ready_candidate"
                elif len(aggregate_values) > 1:
                    status = "ambiguous_dimensionless_aggregate"
                else:
                    values, members, class_status = _class_dimension_rows(filing)
                    if class_status == "ready":
                        resolved_value = float(sum(values))
                        method = "explicit_common_class_sum"
                        status = "ready_candidate"
                    else:
                        status = class_status
        shares_age = (
            int((selection_date - period_end).days)
            if pd.notna(period_end) else np.nan
        )
        existing_ready = bool(row.shares_ready)
        existing_value = (
            float(row.shares_value) if pd.notna(row.shares_value) else np.nan
        )
        relative_difference = (
            abs(resolved_value - existing_value) / existing_value
            if np.isfinite(resolved_value)
            and np.isfinite(existing_value)
            and existing_value > 0
            else np.nan
        )
        comparison_passed = (
            bool(relative_difference <= selected.existing_value_tolerance)
            if existing_ready and np.isfinite(relative_difference) else None
        )
        foreign = bool(row.foreign_filer_asof)
        multi = bool(row.multi_security_issuer)
        age_passed = bool(
            np.isfinite(shares_age)
            and shares_age <= selected.maximum_domestic_share_age_days
        )
        promotion_allowed = bool(
            status == "ready_candidate"
            and not existing_ready
            and not foreign
            and not multi
            and age_passed
        )
        if promotion_allowed:
            promotion_blocker = ""
        elif existing_ready:
            promotion_blocker = "existing_companyfacts_shares_retained"
        elif status != "ready_candidate":
            promotion_blocker = status
        elif foreign:
            promotion_blocker = "foreign_filer_fx_or_adr_pending"
        elif multi:
            promotion_blocker = "multi_security_market_cap_allocation_pending"
        elif not age_passed:
            promotion_blocker = "filing_share_fact_stale"
        else:
            promotion_blocker = "promotion_not_allowed"
        if existing_ready and comparison_passed is False:
            failures.append({
                "scope": "existing_share_crosscheck",
                "selection_date": str(row.selection_date)[:10],
                "ticker": str(row.ticker),
                "reason": f"relative_difference={relative_difference:.6f}",
            })
        output.append({
            "selection_date": str(row.selection_date)[:10],
            "ticker": str(row.ticker).upper(),
            "cik": int(row.cik),
            "existing_shares_ready": existing_ready,
            "existing_shares_value": existing_value,
            "resolved_shares_value": resolved_value,
            "shares_relative_difference": relative_difference,
            "existing_crosscheck_passed": comparison_passed,
            "source_accession_number": accession,
            "source_form": form,
            "source_available_date": (
                available_date.strftime("%Y-%m-%d")
                if pd.notna(available_date) else ""
            ),
            "shares_period_end": (
                period_end.strftime("%Y-%m-%d") if pd.notna(period_end) else ""
            ),
            "shares_age_days": shares_age,
            "shares_age_passed": age_passed,
            "share_concept": concept,
            "share_resolution_method": method,
            "common_class_members": ";".join(members),
            "foreign_filer_asof": foreign,
            "multi_security_issuer": multi,
            "resolution_status": status,
            "promotion_allowed": promotion_allowed,
            "promotion_blocker": promotion_blocker,
            "policy_id": FILING_SHARE_RESOLUTION_POLICY_ID,
        })
    rows = pd.DataFrame(output).sort_values(keys, kind="stable").reset_index(drop=True)
    comparisons = rows[rows["existing_shares_ready"]].copy()
    promotions = rows[rows["promotion_allowed"]].copy()
    failure_frame = pd.DataFrame(
        failures,
        columns=["scope", "selection_date", "ticker", "reason"],
    )
    if rows.duplicated(keys).any():
        raise NdxFilingIdentityError("filing share resolution contains duplicate keys")
    return rows, comparisons, promotions, failure_frame


def file_content_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
