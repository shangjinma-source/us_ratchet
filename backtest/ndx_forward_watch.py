"""Register a point-in-time NDX forward observation without scoring or backtesting.

The forward-watch boundary is deliberately separate from the historical NDX
proxy.  This module audits current constituents, issuer/security identity,
reviewed risk-chain evidence, current evidence freshness, and local price
cache metadata.  It never reads portfolio returns and never promotes a row to
an investable candidate.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_marginal_allocation import load_plan
from data.versioning import file_sha256, manifest_path, utc_now_iso, write_dataset_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORWARD_WATCH_SCHEMA_VERSION = 1
UNCLASSIFIED_CHAIN = "unclassified"
MIN_PRICE_ROWS = 504
DEFAULT_MAX_LAG_BUSINESS_DAYS = 3
OFFICIAL_NASDAQ_COMPANIES_URL = (
    "https://www.nasdaq.com/solutions/global-indexes/nasdaq-100/companies"
)


class NdxForwardWatchError(ValueError):
    """Raised when a forward-watch input cannot be audited safely."""


OBSERVATION_COLUMNS = [
    "observation_date",
    "ticker",
    "name",
    "issuer_id",
    "security_id",
    "identity_status",
    "cik",
    "ndx_as_of_date",
    "ndx_membership_status",
    "risk_chain",
    "risk_chain_label",
    "taxonomy_confidence",
    "taxonomy_status",
    "taxonomy_source",
    "taxonomy_effective_from",
    "taxonomy_effective_to",
    "taxonomy_evidence_available_date",
    "price_status",
    "price_end",
    "price_cache_raw_end",
    "price_future_rows",
    "price_rows",
    "quality_evidence_status",
    "valuation_evidence_status",
    "component_watch_ready",
    "candidate_admission_allowed",
    "blockers",
    "reason",
]

OBSERVATION_LABELS = {
    "observation_date": "观察日期",
    "ticker": "股票代码",
    "name": "证券名称",
    "issuer_id": "发行人编号",
    "security_id": "证券编号",
    "identity_status": "身份状态",
    "cik": "SEC CIK",
    "ndx_as_of_date": "NDX快照日期",
    "ndx_membership_status": "NDX成员状态",
    "risk_chain": "风险链编号",
    "risk_chain_label": "风险链名称",
    "taxonomy_confidence": "风险链置信度",
    "taxonomy_status": "风险链证据状态",
    "taxonomy_source": "风险链证据来源",
    "taxonomy_effective_from": "风险链生效起日",
    "taxonomy_effective_to": "风险链生效止日",
    "taxonomy_evidence_available_date": "风险链证据可用日",
    "price_status": "价格缓存状态",
    "price_end": "价格缓存末日",
    "price_cache_raw_end": "价格缓存原始末日",
    "price_future_rows": "观察日及以后价格行数",
    "price_rows": "价格有效行数",
    "quality_evidence_status": "质量证据状态",
    "valuation_evidence_status": "估值证据状态",
    "component_watch_ready": "组件观察就绪",
    "candidate_admission_allowed": "候选准入允许",
    "blockers": "阻塞原因",
    "reason": "未晋级说明",
}

PREREQUISITE_LABELS = {
    "id": "前置项",
    "available": "是否满足",
    "required_for_registration": "登记是否必需",
    "path": "证据路径",
    "version_id": "版本编号",
    "content_sha256": "内容哈希",
    "observed_value": "观测值",
    "reason": "审计说明",
}

SUMMARY_LABELS = {
    "item": "项目",
    "value": "内容",
}


def _resolve(path: str | Path, *, root: Path = PROJECT_ROOT) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


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


def _iso_date(value: Any, *, field: str) -> str:
    raw = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise NdxForwardWatchError(f"{field} must be YYYY-MM-DD: {value!r}") from exc


def _optional_date(value: Any) -> str:
    raw = str(value or "").strip()[:10]
    if not raw or raw.lower() in {"nan", "nat", "none"}:
        return ""
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return ""


def _bool_text(value: bool) -> str:
    return "是" if bool(value) else "否"


def _json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise NdxForwardWatchError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise NdxForwardWatchError(f"JSON root must be an object: {path}")
    return payload


def _read_yaml(path: Path) -> dict:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise NdxForwardWatchError(f"invalid YAML: {path}") from exc
    if not isinstance(payload, dict):
        raise NdxForwardWatchError(f"YAML root must be a mapping: {path}")
    return payload


def _read_sidecar(path: Path) -> tuple[dict | None, dict]:
    sidecar = manifest_path(path)
    if not path.exists():
        return None, {
            "available": False,
            "path": path.as_posix(),
            "content_sha256": None,
            "version_id": None,
            "reason": "file_missing",
        }
    if not sidecar.exists():
        return None, {
            "available": False,
            "path": path.as_posix(),
            "content_sha256": file_sha256(path),
            "version_id": None,
            "reason": "manifest_missing",
        }
    try:
        payload = _read_json(sidecar)
    except NdxForwardWatchError as exc:
        return None, {
            "available": False,
            "path": path.as_posix(),
            "content_sha256": file_sha256(path),
            "version_id": None,
            "reason": str(exc),
        }
    digest = file_sha256(path)
    expected = str(payload.get("content_sha256") or "")
    if expected != digest:
        return payload, {
            "available": False,
            "path": path.as_posix(),
            "content_sha256": digest,
            "version_id": payload.get("version_id"),
            "reason": "content_hash_mismatch",
            "manifest_content_sha256": expected,
        }
    row_count = payload.get("row_count")
    return payload, {
        "available": True,
        "path": path.as_posix(),
        "content_sha256": digest,
        "version_id": payload.get("version_id"),
        "manifest_sha256": file_sha256(sidecar),
        "row_count": row_count,
        "reason": "verified",
    }


def _versioned_frame(path: Path) -> tuple[pd.DataFrame | None, dict]:
    payload, audit = _read_sidecar(path)
    if not audit["available"]:
        return None, audit
    try:
        frame = pd.read_csv(path, low_memory=False, keep_default_na=False)
    except Exception as exc:
        audit = {**audit, "available": False, "reason": f"csv_read_failed: {exc}"}
        return None, audit
    row_count = audit.get("row_count")
    if row_count is not None and int(row_count) != len(frame):
        audit = {
            **audit,
            "available": False,
            "reason": f"row_count_mismatch: manifest={row_count} observed={len(frame)}",
        }
        return None, audit
    return frame, audit


def _verified_bundle_manifest(path: Path) -> tuple[dict | None, dict]:
    payload, audit = _read_sidecar(path)
    if payload is None or not audit["available"]:
        return payload, audit
    try:
        bundle = _read_json(path)
    except NdxForwardWatchError as exc:
        return None, {**audit, "available": False, "reason": str(exc)}
    return bundle, audit


def load_forward_watch_spec(path: str | Path) -> dict:
    target = Path(path)
    payload = _read_yaml(target)
    if int(payload.get("schema_version") or 0) != FORWARD_WATCH_SCHEMA_VERSION:
        raise NdxForwardWatchError("forward-watch schema_version is unsupported")
    if payload.get("research_only") is not True:
        raise NdxForwardWatchError("forward-watch must be research_only")
    if _iso_date(payload.get("fresh_oos_start"), field="fresh_oos_start") != "2026-07-13":
        raise NdxForwardWatchError("fresh_oos_start must remain the registered 2026-07-13 boundary")
    candidate_policy = payload.get("candidate_policy") or {}
    if candidate_policy.get("qqq_candidate_allowed") is not False:
        raise NdxForwardWatchError("QQQ must remain outside the candidate universe")
    if candidate_policy.get("unclassified_policy") != "reject_and_report":
        raise NdxForwardWatchError("unclassified policy must be reject_and_report")
    if candidate_policy.get("conflict_policy") != "reject_and_report":
        raise NdxForwardWatchError("conflict policy must be reject_and_report")
    if candidate_policy.get("live_config_mutation_allowed") is not False:
        raise NdxForwardWatchError("live config mutation must remain disabled")
    if candidate_policy.get("today_advice_impact") != "none":
        raise NdxForwardWatchError("today advice impact must remain none")
    lock = payload.get("rule_lock") or {}
    for key in (
        "v11_plan_path",
        "v10_spec_path",
        "v10_spec_sha256",
        "component_family",
        "valuation_policy_id",
        "valuation_score_version_id",
    ):
        if not str(lock.get(key) or "").strip():
            raise NdxForwardWatchError(f"rule_lock.{key} is required")
    profiles = lock.get("frozen_profile_ids")
    if not isinstance(profiles, list) or not profiles:
        raise NdxForwardWatchError("rule_lock.frozen_profile_ids must be non-empty")
    payload["path"] = target.resolve().as_posix()
    payload["content_sha256"] = file_sha256(target)
    payload["version_id"] = (
        f"ndx_v11_forward_watch:{payload['experiment_id']}:{payload['content_sha256'][:16]}"
    )
    return payload


def _audit_local_file(path: Path, *, role: str, required: bool = True) -> tuple[dict, dict | None]:
    if not path.exists():
        return {
            "id": role,
            "available": False,
            "path": path.as_posix(),
            "version_id": None,
            "content_sha256": None,
            "reason": "file_missing",
        }, None
    digest = file_sha256(path)
    return {
        "id": role,
        "available": True,
        "path": path.as_posix(),
        "version_id": f"local:{role}:{digest[:16]}",
        "content_sha256": digest,
        "reason": "verified_local_file",
    }, None


def _business_day_lag(start: str, end: str) -> int | None:
    start_day = pd.Timestamp(start)
    end_day = pd.Timestamp(end)
    if end_day < start_day:
        return None
    return int(len(pd.bdate_range(start_day + pd.offsets.BDay(1), end_day)))


def _lag_to_reference(observed_end: str, reference_date: str) -> int:
    observed = pd.Timestamp(observed_end)
    reference = pd.Timestamp(reference_date)
    if observed >= reference:
        return 0
    return int(len(pd.bdate_range(observed + pd.offsets.BDay(1), reference)))


def _audit_ndx_snapshot(path: Path, observation_date: str) -> tuple[pd.DataFrame, dict]:
    frame, version = _versioned_frame(path)
    audit = {
        "id": "ndx_current_snapshot",
        "required_for_registration": True,
        "path": path.as_posix(),
        "available": bool(version.get("available") and frame is not None),
        "version_id": version.get("version_id"),
        "content_sha256": version.get("content_sha256"),
        "reason": version.get("reason"),
    }
    if frame is None:
        return pd.DataFrame(columns=["ticker", "name"]), audit
    required = {"as_of_date", "source_id", "ticker", "name", "source_locator"}
    missing = sorted(required - set(frame.columns))
    if missing:
        audit.update({"available": False, "reason": f"missing_columns: {missing}"})
        return pd.DataFrame(columns=frame.columns), audit
    frame = frame.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    frame["as_of_date"] = frame["as_of_date"].map(_optional_date)
    as_of = sorted(set(frame["as_of_date"]))
    ticker_count = int(frame["ticker"].nunique())
    source_ok = bool(
        frame["source_id"].astype(str).eq("nasdaq_100").all()
        and frame["source_locator"].astype(str).eq(OFFICIAL_NASDAQ_COMPANIES_URL).all()
    )
    qqq_present = "QQQ" in set(frame["ticker"])
    if len(as_of) != 1 or not as_of[0]:
        audit.update({"available": False, "reason": "snapshot_as_of_date_not_unique"})
        return frame, audit
    snapshot_date = as_of[0]
    lag = _business_day_lag(snapshot_date, observation_date)
    max_lag = DEFAULT_MAX_LAG_BUSINESS_DAYS
    valid = (
        ticker_count >= 100
        and not qqq_present
        and source_ok
        and snapshot_date <= observation_date
        and lag is not None
        and lag <= max_lag
    )
    reasons = []
    if ticker_count < 100:
        reasons.append(f"ticker_count_below_100:{ticker_count}")
    if qqq_present:
        reasons.append("qqq_present")
    if not source_ok:
        reasons.append("non_official_nasdaq_source")
    if snapshot_date > observation_date:
        reasons.append("snapshot_after_observation_date")
    if lag is None or lag > max_lag:
        reasons.append(f"snapshot_lag_business_days:{lag}")
    audit.update({
        "available": bool(valid),
        "observed_value": f"{ticker_count} securities as_of {snapshot_date}",
        "snapshot_date": snapshot_date,
        "ticker_count": ticker_count,
        "lag_business_days": lag,
        "reason": "verified_official_current_snapshot" if valid else ";".join(reasons),
    })
    return frame, audit


def _load_sec_crosswalk(path: Path) -> tuple[dict[str, dict], dict]:
    payload, audit = _read_sidecar(path)
    result: dict[str, dict] = {}
    if payload is None or not audit.get("available"):
        return result, {
            "id": "sec_current_identity_crosswalk",
            "required_for_registration": True,
            "path": path.as_posix(),
            "available": False,
            "version_id": audit.get("version_id"),
            "content_sha256": audit.get("content_sha256"),
            "reason": audit.get("reason"),
        }
    try:
        raw = _read_json(path)
        fields = raw.get("fields") or []
        rows = raw.get("data") or []
        if fields != ["cik", "name", "ticker", "exchange"]:
            raise ValueError("SEC ticker crosswalk schema changed")
        grouped: dict[str, list[dict]] = {}
        for values in rows:
            if not isinstance(values, list) or len(values) != len(fields):
                continue
            item = dict(zip(fields, values))
            ticker = str(item.get("ticker") or "").upper().strip()
            cik = str(item.get("cik") or "").strip()
            if ticker and cik.isdigit() and int(cik) > 0:
                grouped.setdefault(ticker, []).append({
                    "ticker": ticker,
                    "cik": f"{int(cik):010d}",
                    "name": str(item.get("name") or "").strip(),
                    "exchange": str(item.get("exchange") or "").strip(),
                })
        for ticker, candidates in grouped.items():
            if len(candidates) == 1:
                result[ticker] = candidates[0]
        fetched_at = _optional_date(payload.get("fetched_at"))
        audit = {
            "id": "sec_current_identity_crosswalk",
            "required_for_registration": True,
            "path": path.as_posix(),
            "available": bool(result),
            "version_id": audit.get("version_id"),
            "content_sha256": audit.get("content_sha256"),
            "fetched_at": fetched_at,
            "unique_ticker_count": len(result),
            "reason": "verified_official_sec_crosswalk" if result else "no_unique_ticker_rows",
        }
        return result, audit
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return result, {
            "id": "sec_current_identity_crosswalk",
            "required_for_registration": True,
            "path": path.as_posix(),
            "available": False,
            "version_id": audit.get("version_id"),
            "content_sha256": audit.get("content_sha256"),
            "reason": f"crosswalk_parse_failed: {exc}",
        }


def _date_list(value: Any) -> list[str]:
    result = []
    for raw in str(value or "").split(";"):
        parsed = _optional_date(raw)
        if parsed:
            result.append(parsed)
    return sorted(set(result))


def _classification_from_frame(
    ticker: str,
    observation_date: str,
    records: pd.DataFrame | None,
    overlay: pd.DataFrame | None,
) -> dict:
    candidates: list[dict] = []
    conflicts = []
    for frame, source in ((overlay, "incumbent_overlay_reviewed"), (records, "taxonomy_v2_historical_records")):
        if frame is None or frame.empty or "ticker" not in frame:
            continue
        subset = frame[
            frame["ticker"].astype(str).str.upper().eq(ticker)
            & frame.get("status", pd.Series(index=frame.index, dtype=str)).astype(str).str.lower().eq("accepted")
        ].copy()
        for row in subset.to_dict(orient="records"):
            start = _optional_date(row.get("effective_from")) or _optional_date(
                row.get("selection_date_start")
            )
            end = _optional_date(row.get("effective_to")) or _optional_date(
                row.get("selection_date_end")
            )
            available_dates = _date_list(
                row.get("evidence_available_date")
            )
            in_effect = bool(
                start
                and start <= observation_date
                and (not end or observation_date <= end)
                and available_dates
                and max(available_dates) <= observation_date
            )
            if not in_effect:
                continue
            candidates.append({
                "source": source,
                "security_id": str(row.get("security_id") or ""),
                "issuer_id": str(row.get("issuer_id") or ""),
                "risk_chain": str(row.get("risk_chain") or UNCLASSIFIED_CHAIN),
                "confidence": str(row.get("confidence") or ""),
                "effective_from": start,
                "effective_to": end,
                "evidence_available_date": ";".join(available_dates),
                "evidence_locator": str(
                    row.get("evidence_locator") or row.get("evidence_source") or ""
                ),
            })
    if not candidates:
        return {
            "security_id": "",
            "issuer_id": "",
            "risk_chain": UNCLASSIFIED_CHAIN,
            "confidence": "",
            "status": "unclassified",
            "source": "",
            "effective_from": "",
            "effective_to": "",
            "evidence_available_date": "",
            "evidence_locator": "",
            "reason": "no_accepted_taxonomy_evidence_covering_observation_date",
        }
    chains = {item["risk_chain"] for item in candidates}
    securities = {item["security_id"] for item in candidates if item["security_id"]}
    if len(chains) != 1 or len(securities) > 1:
        conflicts = sorted(chains)
        return {
            "security_id": "",
            "issuer_id": "",
            "risk_chain": UNCLASSIFIED_CHAIN,
            "confidence": "",
            "status": "conflict",
            "source": ";".join(sorted({item["source"] for item in candidates})),
            "effective_from": "",
            "effective_to": "",
            "evidence_available_date": "",
            "evidence_locator": "",
            "reason": "multiple_accepted_security_or_risk_chain_records:" + ",".join(conflicts),
        }
    selected = candidates[0]
    return {
        **selected,
        "status": "accepted",
        "reason": "accepted_point_in_time_first_party_taxonomy_evidence",
    }


def _load_taxonomy_inputs(paths: Mapping[str, Path], observation_date: str) -> tuple[pd.DataFrame | None, pd.DataFrame | None, dict, dict]:
    taxonomy_manifest_path = paths["taxonomy_manifest"]
    taxonomy_manifest, taxonomy_audit = _verified_bundle_manifest(taxonomy_manifest_path)
    taxonomy_records, records_audit = _versioned_frame(paths["taxonomy_records"])
    overlay_manifest, overlay_manifest_audit = _verified_bundle_manifest(paths["overlay_manifest"])
    overlay, overlay_audit = _versioned_frame(paths["overlay_evidence"])
    taxonomy_ok = bool(
        taxonomy_manifest is not None
        and taxonomy_audit.get("available")
        and taxonomy_manifest.get("historical_backfill_allowed") is False
        and (taxonomy_manifest.get("future_data_guard") or {}).get("passed") is True
        and records_audit.get("available")
    )
    overlay_ok = bool(
        overlay_manifest is not None
        and overlay_manifest_audit.get("available")
        and overlay_manifest.get("classification_status") == "accepted_evidence_applied"
        and overlay_audit.get("available")
        and int((overlay_manifest.get("summary") or {}).get("pending_manual_review") or 0) == 0
    )
    taxonomy_audit_row = {
        "id": "taxonomy_v2_current_evidence",
        "required_for_registration": True,
        "path": taxonomy_manifest_path.as_posix(),
        "available": taxonomy_ok,
        "version_id": (taxonomy_manifest or {}).get("taxonomy_version"),
        "content_sha256": taxonomy_audit.get("content_sha256"),
        "reason": "taxonomy bundle and records verified" if taxonomy_ok else "taxonomy bundle or records failed audit",
        "historical_classified_rows_not_backfilled": True,
    }
    overlay_audit_row = {
        "id": "incumbent_overlay_current_evidence",
        "required_for_registration": True,
        "path": paths["overlay_manifest"].as_posix(),
        "available": overlay_ok,
        "version_id": overlay_manifest_audit.get("version_id"),
        "content_sha256": overlay_manifest_audit.get("content_sha256"),
        "reason": "accepted incumbent overlay verified" if overlay_ok else "incumbent overlay failed audit",
    }
    if not taxonomy_ok:
        taxonomy_records = None
    if not overlay_ok:
        overlay = None
    return taxonomy_records, overlay, taxonomy_audit_row, overlay_audit_row


def _audit_score_evidence(
    *,
    root: Path,
    score_path: Path,
    expected_policy: str,
    current_tickers: set[str],
    observation_date: str,
    evidence_id: str,
) -> tuple[dict, pd.DataFrame | None]:
    frame, score_audit = _versioned_frame(score_path)
    root_manifest_path = root / "manifest.json"
    root_payload = _read_json(root_manifest_path) if root_manifest_path.exists() else {}
    root_digest = file_sha256(root_manifest_path) if root_manifest_path.exists() else None
    readiness_path = root / "quality_readiness.json"
    summary_path = root / "summary.json"
    metadata = {}
    if readiness_path.exists():
        metadata = _read_json(readiness_path)
    elif summary_path.exists():
        metadata = _read_json(summary_path)
    audit = {
        "id": evidence_id,
        # Registration is allowed to document a fresh observation even when
        # the current factor evidence is stale; stale evidence blocks every
        # candidate row below and is therefore reported as a candidate gate,
        # not hidden as a missing registration artifact.
        "required_for_registration": False,
        "path": score_path.as_posix(),
        "available": False,
        "version_id": score_audit.get("version_id"),
        "content_sha256": score_audit.get("content_sha256"),
        "root_manifest_sha256": root_digest,
        "latest_selection_date": None,
        "latest_current_ticker_coverage": 0.0,
        "policy_id": expected_policy,
        "reason": score_audit.get("reason"),
    }
    if frame is None:
        return audit, frame
    required = {"selection_date", "ticker"}
    missing = sorted(required - set(frame.columns))
    if missing:
        audit["reason"] = f"score_file_missing_columns: {missing}"
        return audit, frame
    dates = frame["selection_date"].map(_optional_date)
    tickers = frame["ticker"].astype(str).str.upper().str.strip()
    valid_dates = sorted({value for value in dates if value})
    if not valid_dates:
        audit["reason"] = "score_file_has_no_selection_dates"
        return audit, frame
    latest = valid_dates[-1]
    latest_rows = tickers[dates.eq(latest)]
    coverage = (
        len(set(latest_rows) & current_tickers) / len(current_tickers)
        if current_tickers else 0.0
    )
    policy_columns = [column for column in frame.columns if column.endswith("policy_id")]
    policy_values = set()
    for column in policy_columns:
        policy_values.update(
            value for value in frame[column].astype(str).str.strip().unique()
            if value and value.lower() not in {"nan", "none"}
        )
    future_rows = sum(value > observation_date for value in dates if value)
    root_expected = None
    evidence_name = "quality_scores" if evidence_id == "quality_current_evidence" else "scores"
    evidence_files = root_payload.get("evidence_files") or {}
    if evidence_name in evidence_files:
        root_expected = evidence_files[evidence_name].get("sha256")
    root_hash_ok = root_expected in {None, score_audit.get("content_sha256")}
    metadata_ready = bool(
        metadata.get("research_ranking_ready", metadata.get("integrity_passed", False))
    )
    policy_ok = not policy_values or expected_policy in policy_values
    ready = bool(
        score_audit.get("available")
        and root_hash_ok
        and metadata_ready
        and policy_ok
        and latest >= observation_date
        and coverage >= 1.0
        and future_rows == 0
    )
    reasons = []
    if not score_audit.get("available"):
        reasons.append(str(score_audit.get("reason")))
    if not root_hash_ok:
        reasons.append("root_manifest_score_hash_mismatch")
    if not metadata_ready:
        reasons.append("root_readiness_not_ready")
    if not policy_ok:
        reasons.append("policy_id_mismatch")
    if latest < observation_date:
        reasons.append(f"latest_selection_date_before_observation:{latest}")
    if coverage < 1.0:
        reasons.append(f"latest_current_ticker_coverage:{coverage:.4f}")
    if future_rows:
        reasons.append(f"future_selection_rows:{future_rows}")
    audit.update({
        "available": ready,
        "latest_selection_date": latest,
        "latest_current_ticker_coverage": coverage,
        "policy_values": sorted(policy_values),
        "future_selection_rows": int(future_rows),
        "reason": "current point-in-time evidence verified" if ready else ";".join(reasons),
    })
    return audit, frame


def _price_status(
    price_dir: Path,
    ticker: str,
    market_reference_date: str | None,
    observation_date: str,
) -> dict:
    candidates = [price_dir / f"{ticker}.csv", price_dir / f"{ticker.replace('.', '-')}.csv"]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        return {"status": "missing", "rows": 0, "end": "", "reason": "price_cache_missing"}
    try:
        frame = pd.read_csv(path, usecols=lambda column: column in {"Date", "Close"})
        if not {"Date", "Close"}.issubset(frame.columns):
            raise ValueError("Date/Close columns missing")
        dates = pd.to_datetime(frame["Date"], errors="coerce")
        close = pd.to_numeric(frame["Close"], errors="coerce")
        valid = dates.notna() & close.notna() & np.isfinite(close) & (close > 0)
        raw_rows = int(valid.sum())
        raw_end = dates[valid].max().strftime("%Y-%m-%d") if raw_rows else ""
        usable = valid & dates.lt(pd.Timestamp(observation_date))
        rows = int(usable.sum())
        end = dates[usable].max().strftime("%Y-%m-%d") if rows else ""
        future_rows = int((valid & dates.ge(pd.Timestamp(observation_date))).sum())
        lag = _lag_to_reference(end, market_reference_date) if end and market_reference_date else None
        price_before_observation = bool(end and end < observation_date)
        ready = bool(
            rows >= MIN_PRICE_ROWS
            and lag is not None
            and lag <= DEFAULT_MAX_LAG_BUSINESS_DAYS
            and price_before_observation
        )
        reason = None
        if rows < MIN_PRICE_ROWS:
            reason = f"price_rows_below_{MIN_PRICE_ROWS}"
        elif not price_before_observation:
            reason = "no_valid_price_strictly_before_observation_date"
        elif not market_reference_date:
            reason = "market_reference_date_missing"
        elif lag is None or lag > DEFAULT_MAX_LAG_BUSINESS_DAYS:
            reason = f"price_cache_lag_business_days:{lag}"
        return {
            "status": "ready" if ready else "stale",
            "rows": rows,
            "end": end,
            "raw_end": raw_end,
            "future_rows": future_rows,
            "lag_business_days": lag,
            "cache_path": path.as_posix(),
            "reason": reason,
        }
    except Exception as exc:
        return {"status": "invalid", "rows": 0, "end": "", "cache_path": path.as_posix(), "reason": str(exc)}


def _taxonomy_labels(path: Path) -> dict[str, str]:
    if not path.exists():
        return {UNCLASSIFIED_CHAIN: "未分类"}
    payload = _read_yaml(path)
    chains = payload.get("risk_chains") or {}
    return {str(key): str((value or {}).get("label") or key) for key, value in chains.items()}


def _empty_observations() -> pd.DataFrame:
    return pd.DataFrame(columns=OBSERVATION_COLUMNS)


def build_observations(
    *,
    snapshot: pd.DataFrame,
    snapshot_audit: Mapping[str, Any],
    crosswalk: Mapping[str, Mapping[str, Any]],
    crosswalk_audit: Mapping[str, Any],
    taxonomy_records: pd.DataFrame | None,
    overlay: pd.DataFrame | None,
    quality_audit: Mapping[str, Any],
    valuation_audit: Mapping[str, Any],
    price_cache_dir: Path,
    observation_date: str,
    taxonomy_labels: Mapping[str, str],
) -> pd.DataFrame:
    if snapshot.empty or "ticker" not in snapshot.columns:
        return _empty_observations()
    market_reference_date = None
    market_statuses = [
        _price_status(price_cache_dir, ticker, None, observation_date)
        for ticker in ("QQQ", "SPY")
    ]
    market_dates = [
        status.get("end")
        for status in market_statuses
        if status.get("end") and str(status.get("end")) < observation_date
    ]
    if market_dates:
        market_reference_date = max(market_dates)
    rows = []
    for item in snapshot.sort_values("ticker", kind="stable").to_dict(orient="records"):
        ticker = str(item.get("ticker") or "").upper().strip()
        identity = crosswalk.get(ticker) or {}
        cik = str(identity.get("cik") or "")
        issuer_id = f"issuer:{cik}" if cik else ""
        classification = _classification_from_frame(
            ticker, observation_date, taxonomy_records, overlay
        )
        security_id = str(classification.get("security_id") or "")
        identity_status = "resolved_by_accepted_taxonomy_evidence" if security_id else (
            "resolved_issuer_only_current_security_unresolved" if cik else "unresolved_current_cik"
        )
        if not security_id and cik:
            security_id = f"security:{cik}:current_ticker:{ticker}"
        price = _price_status(
            price_cache_dir, ticker, market_reference_date, observation_date
        )
        blockers = []
        if ticker == "QQQ":
            blockers.append("qqq_is_never_a_candidate")
        if not bool(snapshot_audit.get("available")):
            blockers.append("ndx_current_snapshot_not_verified")
        fetched_at = _optional_date(crosswalk_audit.get("fetched_at"))
        if not cik:
            blockers.append("sec_current_cik_unresolved")
        elif fetched_at and fetched_at > observation_date:
            blockers.append("sec_identity_crosswalk_after_observation_date")
        if classification.get("status") != "accepted":
            blockers.append(
                "taxonomy_conflict" if classification.get("status") == "conflict"
                else "taxonomy_v2_current_evidence_missing_or_unclassified"
            )
        if not bool(quality_audit.get("available")):
            blockers.append("quality_current_evidence_stale_or_incomplete")
        if not bool(valuation_audit.get("available")):
            blockers.append("valuation_current_evidence_stale_or_incomplete")
        if price.get("status") != "ready":
            blockers.append(price.get("reason") or "price_cache_not_ready")
        blockers.append("fresh_oos_backtest_not_run")
        component_ready = not blockers or blockers == ["fresh_oos_backtest_not_run"]
        rows.append({
            "observation_date": observation_date,
            "ticker": ticker,
            "name": str(item.get("name") or ""),
            "issuer_id": classification.get("issuer_id") or issuer_id,
            "security_id": security_id,
            "identity_status": identity_status,
            "cik": cik,
            "ndx_as_of_date": str(item.get("as_of_date") or ""),
            "ndx_membership_status": "current_official_snapshot" if snapshot_audit.get("available") else "snapshot_audit_failed",
            "risk_chain": classification.get("risk_chain") or UNCLASSIFIED_CHAIN,
            "risk_chain_label": taxonomy_labels.get(classification.get("risk_chain") or UNCLASSIFIED_CHAIN, "未分类"),
            "taxonomy_confidence": classification.get("confidence") or "",
            "taxonomy_status": classification.get("status") or "unclassified",
            "taxonomy_source": classification.get("source") or "",
            "taxonomy_effective_from": classification.get("effective_from") or "",
            "taxonomy_effective_to": classification.get("effective_to") or "",
            "taxonomy_evidence_available_date": classification.get("evidence_available_date") or "",
            "price_status": price.get("status"),
            "price_end": price.get("end") or "",
            "price_cache_raw_end": price.get("raw_end") or "",
            "price_future_rows": int(price.get("future_rows") or 0),
            "price_rows": int(price.get("rows") or 0),
            "quality_evidence_status": "ready" if quality_audit.get("available") else "stale_or_incomplete",
            "valuation_evidence_status": "ready" if valuation_audit.get("available") else "stale_or_incomplete",
            "component_watch_ready": bool(component_ready),
            "candidate_admission_allowed": False,
            "blockers": ";".join(blockers),
            "reason": ";".join(blockers) if blockers else "component watch ready; portfolio admission still requires fresh OOS",
        })
    return pd.DataFrame(rows, columns=OBSERVATION_COLUMNS)


def _write_artifact(frame: pd.DataFrame, path: Path, *, dataset_type: str, dataset_key: str, extra: dict | None = None) -> dict:
    _atomic_csv(frame, path)
    manifest = write_dataset_manifest(
        path,
        dataset_type=dataset_type,
        dataset_key=dataset_key,
        source="derived_from_hash_locked_forward_watch_inputs",
        fetched_at_evidence="derived_runtime_utc",
        row_count=len(frame),
        extra={
            "research_only": True,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
            "live_config_mutation_allowed": False,
            "today_advice_impact": "none",
            **(extra or {}),
        },
    )
    return {
        "filename": path.name,
        "manifest_filename": manifest_path(path).name,
        "rows": len(frame),
        "sha256": manifest["content_sha256"],
        "version_id": manifest["version_id"],
    }


def _write_workbook(path: Path, frames: Mapping[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.stem + ".tmp.xlsx")
    with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
        frames["observations"].rename(columns=OBSERVATION_LABELS).to_excel(
            writer, sheet_name="证券观察", index=False
        )
        frames["summary"].rename(columns=SUMMARY_LABELS).to_excel(
            writer, sheet_name="登记摘要", index=False
        )
        frames["prerequisites"].rename(columns=PREREQUISITE_LABELS).to_excel(
            writer, sheet_name="前置审计", index=False
        )
        frames["rule_lock"].to_excel(writer, sheet_name="规则锁定", index=False)
        frames["sources"].to_excel(writer, sheet_name="来源版本", index=False)
    temporary.replace(path)


def _load_paths(spec: Mapping[str, Any], *, root: Path) -> dict[str, Path]:
    raw = spec.get("paths") or {}
    required = {
        "taxonomy_definition",
        "taxonomy_manifest",
        "taxonomy_records",
        "taxonomy_identity",
        "overlay_manifest",
        "overlay_evidence",
        "ndx_snapshot",
        "sec_crosswalk",
        "exact_event_manifest",
        "event_gap_manifest",
        "v11_plan_manifest",
        "quality_root",
        "quality_scores",
        "valuation_root",
        "valuation_scores",
        "price_cache_dir",
    }
    missing = sorted(required - set(raw))
    if missing:
        raise NdxForwardWatchError(f"forward-watch paths missing: {missing}")
    return {key: _resolve(value, root=root) for key, value in raw.items()}


def build_bundle(
    *,
    spec_path: str | Path,
    live_config_path: str | Path,
    output_dir: str | Path,
    observation_date: str,
    root: Path = PROJECT_ROOT,
) -> dict:
    spec = load_forward_watch_spec(_resolve(spec_path, root=root))
    observed = _iso_date(observation_date, field="observation_date")
    today = datetime.now(timezone.utc).date().isoformat()
    if observed > today:
        raise NdxForwardWatchError("observation_date cannot be in the future")
    if observed < spec["fresh_oos_start"]:
        raise NdxForwardWatchError("observation_date cannot precede the registered fresh OOS boundary")
    paths = _load_paths(spec, root=root)
    output = _resolve(output_dir, root=root)
    output.mkdir(parents=True, exist_ok=True)

    live_config_path = _resolve(live_config_path, root=root)
    live_config = _read_yaml(live_config_path)
    v11_plan_path = _resolve(spec["rule_lock"]["v11_plan_path"], root=root)
    v10_spec_path = _resolve(spec["rule_lock"]["v10_spec_path"], root=root)
    v11_plan_manifest = _read_json(paths["v11_plan_manifest"]) if paths["v11_plan_manifest"].exists() else {}
    rule_lock_rows = []
    v11_plan_ok = False
    v11_plan_error = ""
    try:
        v11_plan = load_plan(v11_plan_path, config=live_config)
        v11_plan_ok = bool(v11_plan.get("_audit", {}).get("passed"))
        v11_plan_error = "verified current v11 pre-registration" if v11_plan_ok else "v11 plan audit failed"
        v11_spec_hash = v11_plan.get("_spec_sha256")
    except Exception as exc:
        v11_plan = {}
        v11_spec_hash = None
        v11_plan_error = f"v11 plan audit failed: {exc}"
    v10_hash = file_sha256(v10_spec_path) if v10_spec_path.exists() else None
    v10_payload = _read_yaml(v10_spec_path) if v10_spec_path.exists() else {}
    v10_profiles = {
        str(profile.get("id")): profile
        for phase in (v10_payload.get("phases") or [])
        for profile in (phase.get("construction_profiles") or [])
        if isinstance(profile, Mapping)
    }
    locked_profiles = spec["rule_lock"]["frozen_profile_ids"]
    profile_ok = all(profile_id in v10_profiles for profile_id in locked_profiles)
    v10_ok = bool(
        v10_hash == spec["rule_lock"]["v10_spec_sha256"]
        and v10_payload.get("analysis_contract", {}).get("component_family") == spec["rule_lock"]["component_family"]
        and profile_ok
    )
    rule_lock_rows.extend([
        {"rule": "v11_plan", "value": v11_plan_path.as_posix(), "version": v11_spec_hash or "", "passed": v11_plan_ok, "reason": v11_plan_error},
        {"rule": "v10_spec_sha256", "value": v10_spec_path.as_posix(), "version": v10_hash or "", "passed": v10_ok, "reason": "v10 hash/component/profile lock verified" if v10_ok else "v10 rule lock mismatch"},
        {"rule": "fresh_oos_start", "value": spec["fresh_oos_start"], "version": spec["version_id"], "passed": True, "reason": "observation is after registered fresh OOS boundary"},
        {"rule": "qqq_candidate_policy", "value": "QQQ excluded", "version": "candidate_policy_v1", "passed": True, "reason": "QQQ never enters candidate rows"},
        {"rule": "old_holding_policy", "value": "freeze_existing_and_redirect_future_money", "version": "v11_stage1", "passed": True, "reason": "existing holdings are not sold by this research tool"},
    ])

    snapshot, snapshot_audit = _audit_ndx_snapshot(paths["ndx_snapshot"], observed)
    crosswalk, crosswalk_audit = _load_sec_crosswalk(paths["sec_crosswalk"])
    taxonomy_records, overlay, taxonomy_audit, overlay_audit = _load_taxonomy_inputs(paths, observed)
    current_tickers = set(snapshot["ticker"].astype(str).str.upper()) if "ticker" in snapshot else set()
    quality_audit, _ = _audit_score_evidence(
        root=paths["quality_root"],
        score_path=paths["quality_scores"],
        expected_policy="ndx_sec_quality_three_sleeve_v1",
        current_tickers=current_tickers,
        observation_date=observed,
        evidence_id="quality_current_evidence",
    )
    valuation_audit, _ = _audit_score_evidence(
        root=paths["valuation_root"],
        score_path=paths["valuation_scores"],
        expected_policy=spec["rule_lock"]["valuation_policy_id"],
        current_tickers=current_tickers,
        observation_date=observed,
        evidence_id="valuation_current_evidence",
    )

    event_manifest = _read_json(paths["exact_event_manifest"]) if paths["exact_event_manifest"].exists() else {}
    gap_manifest = _read_json(paths["event_gap_manifest"]) if paths["event_gap_manifest"].exists() else {}
    event_hash = file_sha256(paths["exact_event_manifest"]) if paths["exact_event_manifest"].exists() else None
    gap_hash_match = bool(event_hash and gap_manifest.get("exact_event_manifest_sha256") == event_hash)
    exact_audit = {
        "id": "exact_ndx_event_timing_audit",
        "required_for_registration": False,
        "path": paths["exact_event_manifest"].as_posix(),
        "available": bool(event_manifest.get("exact_index_event_timing") is True),
        "version_id": event_manifest.get("dataset_key"),
        "content_sha256": event_hash,
        "reason": "exact event sources verified; historical backtest remains blocked" if event_manifest.get("exact_index_event_timing") is True else "exact event timing audit unavailable",
        "historical_backtest_allowed": bool(event_manifest.get("historical_backtest_allowed") is True),
    }
    gap_audit = {
        "id": "event_gap_scope_lock",
        "required_for_registration": True,
        "path": paths["event_gap_manifest"].as_posix(),
        "available": bool(
            gap_manifest.get("dataset_key") == "ndx_event_gap_disposition_v1"
            and gap_manifest.get("scope_lock_complete") is True
            and gap_manifest.get("v11_plan_registration_allowed") is True
            and gap_manifest.get("v11_execution_allowed") is False
            and gap_hash_match
        ),
        "version_id": gap_manifest.get("dataset_key"),
        "content_sha256": file_sha256(paths["event_gap_manifest"]) if paths["event_gap_manifest"].exists() else None,
        "reason": "event gap scope hash-locked; execution remains blocked" if gap_hash_match else "event gap scope or exact-event hash audit failed",
        "exact_event_manifest_hash_matches": gap_hash_match,
    }

    price_dir = paths["price_cache_dir"]
    observations = build_observations(
        snapshot=snapshot,
        snapshot_audit=snapshot_audit,
        crosswalk=crosswalk,
        crosswalk_audit=crosswalk_audit,
        taxonomy_records=taxonomy_records,
        overlay=overlay,
        quality_audit=quality_audit,
        valuation_audit=valuation_audit,
        price_cache_dir=price_dir,
        observation_date=observed,
        taxonomy_labels=_taxonomy_labels(paths["taxonomy_definition"]),
    )
    prerequisites = pd.DataFrame([
        {"id": "v11_plan", "required_for_registration": True, "path": v11_plan_path.as_posix(), "available": v11_plan_ok, "version_id": v11_spec_hash, "content_sha256": file_sha256(v11_plan_path) if v11_plan_path.exists() else None, "observed_value": v11_plan_manifest.get("status"), "reason": v11_plan_error},
        {"id": "v10_rule_lock", "required_for_registration": True, "path": v10_spec_path.as_posix(), "available": v10_ok, "version_id": v10_hash, "content_sha256": v10_hash, "observed_value": v10_payload.get("analysis_contract", {}).get("component_family"), "reason": "hash/component/profile lock verified" if v10_ok else "hash/component/profile lock failed"},
        snapshot_audit,
        crosswalk_audit,
        taxonomy_audit,
        overlay_audit,
        quality_audit,
        valuation_audit,
        exact_audit,
        gap_audit,
    ])
    registration_blockers = []
    for row in prerequisites.to_dict(orient="records"):
        if row.get("required_for_registration") and not bool(row.get("available")):
            registration_blockers.append(str(row.get("id")))
    current_evidence_stale = not quality_audit.get("available") or not valuation_audit.get("available")
    if registration_blockers:
        status = "FORWARD_WATCH_REGISTRATION_BLOCKED_PREREQUISITE"
    elif current_evidence_stale:
        status = "FORWARD_WATCH_REGISTERED_BLOCKED_CURRENT_EVIDENCE_STALE"
    elif observations.empty or not bool(observations["component_watch_ready"].any()):
        status = "FORWARD_WATCH_REGISTERED_BLOCKED_SECURITY_OR_PRICE_EVIDENCE"
    else:
        status = "FORWARD_WATCH_COMPONENT_READY_WAITING_FOR_FRESH_OOS"
    summary_rows = [
        {"item": "研究状态", "value": status},
        {"item": "观察日期", "value": observed},
        {"item": "新鲜OOS起日", "value": spec["fresh_oos_start"]},
        {"item": "当前NDX证券数", "value": len(observations)},
        {"item": "已接受风险链证券数", "value": int(observations["taxonomy_status"].eq("accepted").sum()) if not observations.empty else 0},
        {"item": "未分类或冲突证券数", "value": int((~observations["taxonomy_status"].eq("accepted")).sum()) if not observations.empty else 0},
        {"item": "组件观察就绪数", "value": int(observations["component_watch_ready"].sum()) if not observations.empty else 0},
        {"item": "候选准入数", "value": int(observations["candidate_admission_allowed"].sum()) if not observations.empty else 0},
        {"item": "当前质量证据最后重选日", "value": quality_audit.get("latest_selection_date")},
        {"item": "当前估值证据最后重选日", "value": valuation_audit.get("latest_selection_date")},
        {"item": "收益数据读取", "value": False},
        {"item": "回测结果使用", "value": False},
        {"item": "实盘配置改变", "value": False},
        {"item": "今日建议改变", "value": False},
        {"item": "旧持仓卖出允许", "value": False},
        {"item": "注册阻塞项", "value": ";".join(registration_blockers)},
    ]
    summary = pd.DataFrame(summary_rows)
    sources = pd.DataFrame([
        {"source_role": "forward_watch_spec", "path": str(spec["path"]), "version_id": spec["version_id"], "content_sha256": spec["content_sha256"], "available": True},
        {"source_role": "live_config_snapshot_read_only", "path": live_config_path.as_posix(), "version_id": f"local:config:{file_sha256(live_config_path)[:16]}", "content_sha256": file_sha256(live_config_path), "available": True},
        {"source_role": "v11_plan_manifest", "path": paths["v11_plan_manifest"].as_posix(), "version_id": v11_plan_manifest.get("status"), "content_sha256": file_sha256(paths["v11_plan_manifest"]) if paths["v11_plan_manifest"].exists() else None, "available": paths["v11_plan_manifest"].exists()},
        {"source_role": "ndx_current_snapshot", "path": paths["ndx_snapshot"].as_posix(), "version_id": snapshot_audit.get("version_id"), "content_sha256": snapshot_audit.get("content_sha256"), "available": snapshot_audit.get("available")},
        {"source_role": "taxonomy_v2_bundle", "path": paths["taxonomy_manifest"].as_posix(), "version_id": taxonomy_audit.get("version_id"), "content_sha256": taxonomy_audit.get("content_sha256"), "available": taxonomy_audit.get("available")},
        {"source_role": "incumbent_overlay", "path": paths["overlay_manifest"].as_posix(), "version_id": overlay_audit.get("version_id"), "content_sha256": overlay_audit.get("content_sha256"), "available": overlay_audit.get("available")},
        {"source_role": "quality_scores", "path": paths["quality_scores"].as_posix(), "version_id": quality_audit.get("version_id"), "content_sha256": quality_audit.get("content_sha256"), "available": quality_audit.get("available")},
        {"source_role": "valuation_scores", "path": paths["valuation_scores"].as_posix(), "version_id": valuation_audit.get("version_id"), "content_sha256": valuation_audit.get("content_sha256"), "available": valuation_audit.get("available")},
        {"source_role": "exact_ndx_events", "path": paths["exact_event_manifest"].as_posix(), "version_id": exact_audit.get("version_id"), "content_sha256": exact_audit.get("content_sha256"), "available": exact_audit.get("available")},
        {"source_role": "event_gap_disposition", "path": paths["event_gap_manifest"].as_posix(), "version_id": gap_audit.get("version_id"), "content_sha256": gap_audit.get("content_sha256"), "available": gap_audit.get("available")},
    ])
    rule_lock = pd.DataFrame(rule_lock_rows)
    artifacts = {}
    artifacts["observations"] = _write_artifact(
        observations, output / "forward_observations.csv",
        dataset_type="ndx_v11_forward_watch", dataset_key="observations",
        extra={"observation_date": observed, "status": status},
    )
    artifacts["summary"] = _write_artifact(
        summary, output / "summary.csv",
        dataset_type="ndx_v11_forward_watch", dataset_key="summary",
        extra={"observation_date": observed, "status": status},
    )
    artifacts["prerequisites"] = _write_artifact(
        prerequisites, output / "prerequisites.csv",
        dataset_type="ndx_v11_forward_watch", dataset_key="prerequisites",
        extra={"observation_date": observed, "status": status},
    )
    artifacts["sources"] = _write_artifact(
        sources, output / "source_versions.csv",
        dataset_type="ndx_v11_forward_watch", dataset_key="source_versions",
        extra={"observation_date": observed, "status": status},
    )
    artifacts["rule_lock"] = _write_artifact(
        rule_lock, output / "rule_lock.csv",
        dataset_type="ndx_v11_forward_watch", dataset_key="rule_lock",
        extra={"observation_date": observed, "status": status},
    )
    workbook = output / "ndx_v11_forward_watch.xlsx"
    _write_workbook(workbook, {
        "observations": observations,
        "summary": summary,
        "prerequisites": prerequisites,
        "rule_lock": rule_lock,
        "sources": sources,
    })
    workbook_manifest = write_dataset_manifest(
        workbook,
        dataset_type="ndx_v11_forward_watch_workbook",
        dataset_key="forward_watch",
        source="derived_from_hash_locked_forward_watch_inputs",
        fetched_at_evidence="derived_runtime_utc",
        row_count=len(observations),
        extra={
            "research_only": True,
            "observation_date": observed,
            "status": status,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
        },
    )
    artifacts["workbook"] = {
        "filename": workbook.name,
        "manifest_filename": manifest_path(workbook).name,
        "rows": len(observations),
        "sha256": workbook_manifest["content_sha256"],
        "version_id": workbook_manifest["version_id"],
    }
    payload = {
        "schema_version": FORWARD_WATCH_SCHEMA_VERSION,
        "manifest_type": "ndx_v11_forward_watch_bundle",
        "generated_at": utc_now_iso(),
        "experiment_id": spec["experiment_id"],
        "forward_watch_version": spec["version_id"],
        "observation_date": observed,
        "fresh_oos_start": spec["fresh_oos_start"],
        "status": status,
        "research_only": True,
        "return_data_read": False,
        "price_data_used": False,
        "price_metadata_audited": True,
        "backtest_results_used": False,
        "live_config_changed": False,
        "today_advice_changed": False,
        "old_holding_sale_allowed": False,
        "qqq_candidate_allowed": False,
        "candidate_admission_allowed": False,
        "registration_blockers": registration_blockers,
        "input_versions": sources.to_dict(orient="records"),
        "artifacts": artifacts,
        "summary": {
            "current_ndx_securities": len(observations),
            "accepted_taxonomy_securities": int(observations["taxonomy_status"].eq("accepted").sum()) if not observations.empty else 0,
            "unclassified_or_conflict_securities": int((~observations["taxonomy_status"].eq("accepted")).sum()) if not observations.empty else 0,
            "component_watch_ready": int(observations["component_watch_ready"].sum()) if not observations.empty else 0,
            "candidate_admission_allowed": 0,
            "current_quality_latest_selection_date": quality_audit.get("latest_selection_date"),
            "current_valuation_latest_selection_date": valuation_audit.get("latest_selection_date"),
        },
        "policy": {
            "taxonomy_role": "risk_construction_evidence_only",
            "historical_label_backfill": False,
            "same_issuer_multiple_security_policy": "one_issuer_one_slot",
            "candidate_share_of_new_money": [0.0, 0.05, 0.10, 0.15],
            "frozen_v10_profiles": locked_profiles,
        },
    }
    manifest_path_main = output / "manifest.json"
    _atomic_text(manifest_path_main, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    bundle_manifest = write_dataset_manifest(
        manifest_path_main,
        dataset_type="ndx_v11_forward_watch_bundle_manifest",
        dataset_key=spec["experiment_id"],
        source="derived_from_hash_locked_forward_watch_inputs",
        fetched_at_evidence="derived_runtime_utc",
        row_count=1,
        extra={
            "research_only": True,
            "observation_date": observed,
            "status": status,
            "return_data_read": False,
            "price_data_used": False,
            "backtest_results_used": False,
            "manifest_self_sidecar": True,
        },
    )
    return payload


def build_sec_companyfacts_plan(
    *,
    spec_path: str | Path,
    output_dir: str | Path,
    observation_date: str,
    root: Path = PROJECT_ROOT,
) -> tuple[pd.DataFrame, dict]:
    """Build a current CIK download plan without making HTTP requests."""

    spec = load_forward_watch_spec(_resolve(spec_path, root=root))
    observed = _iso_date(observation_date, field="observation_date")
    paths = _load_paths(spec, root=root)
    snapshot, snapshot_audit = _audit_ndx_snapshot(paths["ndx_snapshot"], observed)
    crosswalk, crosswalk_audit = _load_sec_crosswalk(paths["sec_crosswalk"])
    rows = []
    for item in snapshot.to_dict(orient="records"):
        ticker = str(item.get("ticker") or "").upper().strip()
        identity = crosswalk.get(ticker) or {}
        cik = str(identity.get("cik") or "")
        rows.append({
            "observation_date": observed,
            "ticker": ticker,
            "name": str(item.get("name") or ""),
            "cik": cik,
            "status": "planned" if cik else "unresolved_cik",
            "raw_path": (Path(output_dir) / "raw_companyfacts" / f"CIK{cik}.json").as_posix() if cik else "",
            "reason": "SEC Company Facts download only; no scoring or backtest" if cik else "SEC ticker crosswalk has no unique CIK",
        })
    plan = pd.DataFrame(rows, columns=[
        "observation_date", "ticker", "name", "cik", "status", "raw_path", "reason"
    ])
    return plan, {
        "snapshot_audit": snapshot_audit,
        "crosswalk_audit": crosswalk_audit,
        "unique_cik_count": int(plan.loc[plan["cik"].ne(""), "cik"].nunique()) if not plan.empty else 0,
        "ticker_count": len(plan),
        "spec_version": spec["version_id"],
    }


__all__ = [
    "NdxForwardWatchError",
    "build_bundle",
    "build_sec_companyfacts_plan",
    "load_forward_watch_spec",
]
