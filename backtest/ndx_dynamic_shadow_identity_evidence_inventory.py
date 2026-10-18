"""Read-only inventory of prospective dynamic-shadow identity evidence.

The inventory deliberately does not turn ticker joins, historical N-PORT
observations, SEC's current ticker file, or a declared rename rule into an
execution-valid security identity.  It records exactly what each frozen source
proves and keeps admission, promotion, and live mutation disabled.
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from backtest.ndx_dynamic_shadow_candidate_snapshot import verify_snapshot_bundle


class NdxDynamicShadowIdentityEvidenceError(ValueError):
    """Raised when an existing identity-evidence artifact fails verification."""


_CANDIDATE_ROOT = Path("data/cache/research/ndx_dynamic_shadow_candidate_generator_v1")
_OFFICIAL_ROOT = Path("data/cache/candidate_pools/snapshots/nasdaq_100")
_TAXONOMY_ROOT = Path("data/cache/candidate_pools/ndx_taxonomy_v2")
_SEC_PATH = Path("data/cache/candidate_pools/ndx_history/sec_company_tickers_exchange.json")
_LIFECYCLE_PATH = Path("config/ndx_security_lifecycle.yaml")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _iso_date(value: Any, label: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise NdxDynamicShadowIdentityEvidenceError(f"invalid {label}") from exc
    if parsed.isoformat() != text:
        raise NdxDynamicShadowIdentityEvidenceError(f"non-canonical {label}")
    return text


def _optional_date(value: Any, label: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    return date.fromisoformat(_iso_date(text, label))


def _selection_dates(value: Any, label: str) -> list[date]:
    parts = [part.strip() for part in str(value or "").split(";") if part.strip()]
    return [date.fromisoformat(_iso_date(part, label)) for part in parts]


def _timestamp(value: Any, label: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NdxDynamicShadowIdentityEvidenceError(f"invalid {label}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NdxDynamicShadowIdentityEvidenceError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _capture_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowIdentityEvidenceError(f"cannot read {label}") from exc
    if not isinstance(value, dict):
        raise NdxDynamicShadowIdentityEvidenceError(f"{label} must be an object")
    return value, raw


def _capture_csv(path: Path, label: str) -> tuple[pd.DataFrame, bytes]:
    try:
        raw = path.read_bytes()
        frame = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise NdxDynamicShadowIdentityEvidenceError(f"cannot read {label}") from exc
    return frame, raw


def _dataset_manifest(
    data_path: Path,
    manifest_path: Path,
    *,
    dataset_type: str,
) -> tuple[dict[str, Any], bytes, bytes]:
    manifest, manifest_raw = _capture_json(manifest_path, f"{dataset_type} manifest")
    try:
        data_raw = data_path.read_bytes()
    except OSError as exc:
        raise NdxDynamicShadowIdentityEvidenceError(f"missing {dataset_type} data") from exc
    if (
        manifest.get("dataset_type") != dataset_type
        or Path(str(manifest.get("cache_path") or "")).resolve() != data_path.resolve()
        or Path(str(manifest.get("manifest_path") or "")).resolve() != manifest_path.resolve()
        or manifest.get("content_sha256") != _sha256(data_raw)
        or int(manifest.get("content_bytes", -1)) != len(data_raw)
    ):
        raise NdxDynamicShadowIdentityEvidenceError(
            f"{dataset_type} path/content binding changed"
        )
    return manifest, data_raw, manifest_raw


def _load_latest_official_archive(
    root: Path,
) -> tuple[Path | None, dict[str, Any] | None, pd.DataFrame, str | None]:
    archive_root = (root / _OFFICIAL_ROOT).resolve()
    if not archive_root.is_dir():
        return None, None, pd.DataFrame(), None
    captures: list[tuple[datetime, Path, dict[str, Any], pd.DataFrame, str]] = []
    for manifest_path in sorted(archive_root.glob("*.csv.manifest.json")):
        data_path = Path(str(manifest_path)[: -len(".manifest.json")]).resolve()
        if data_path.parent != archive_root:
            raise NdxDynamicShadowIdentityEvidenceError("official archive escaped canonical root")
        manifest, data_raw, manifest_raw = _dataset_manifest(
            data_path, manifest_path.resolve(), dataset_type="security_pool_snapshot",
        )
        frame = pd.read_csv(io.BytesIO(data_raw), dtype=str, keep_default_na=False)
        required = {"as_of_date", "source_type", "source_id", "ticker", "name", "source_locator"}
        if (
            not required.issubset(frame.columns)
            or len(frame) != int(manifest.get("row_count", -1))
            or frame["ticker"].str.strip().eq("").any()
            or frame["ticker"].str.upper().duplicated().any()
            or set(frame["source_type"]) != {"index_constituent"}
            or set(frame["source_id"]) != {"nasdaq_100"}
            or manifest.get("immutable_snapshot") is not True
            or manifest.get("historical_backtest_allowed") is not False
            or manifest.get("source_effective_date_known") is not False
        ):
            raise NdxDynamicShadowIdentityEvidenceError("official archive semantics changed")
        frame = frame.copy()
        frame["ticker"] = frame["ticker"].str.upper().str.strip()
        captures.append((
            _timestamp(manifest.get("fetched_at"), "official fetched_at"),
            data_path, manifest, frame, _sha256(manifest_raw),
        ))
    if not captures:
        return None, None, pd.DataFrame(), None
    _, path, manifest, frame, manifest_digest = max(captures, key=lambda item: item[0])
    return path, manifest, frame, manifest_digest


def _taxonomy_bundle(root: Path) -> tuple[dict[str, Any], dict[str, pd.DataFrame], dict[str, Any]]:
    taxonomy_root = (root / _TAXONOMY_ROOT).resolve()
    manifest_path = taxonomy_root / "manifest.json"
    if not manifest_path.is_file():
        return {}, {}, {"present": False, "path": manifest_path.as_posix()}
    manifest, manifest_raw = _capture_json(manifest_path, "taxonomy manifest")
    if manifest.get("manifest_type") != "ndx_taxonomy_v2_bundle":
        raise NdxDynamicShadowIdentityEvidenceError("taxonomy manifest identity changed")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise NdxDynamicShadowIdentityEvidenceError("taxonomy artifact registry is missing")
    expected = {
        "identities": "security_identity.csv",
        "records": "taxonomy_records.csv",
        "identity_issues": "identity_issues.csv",
    }
    frames: dict[str, pd.DataFrame] = {}
    descriptors: dict[str, Any] = {}
    for key, filename in expected.items():
        descriptor = artifacts.get(key)
        if not isinstance(descriptor, Mapping) or descriptor.get("filename") != filename:
            raise NdxDynamicShadowIdentityEvidenceError(f"taxonomy descriptor changed: {key}")
        artifact_path = (taxonomy_root / filename).resolve()
        if artifact_path.parent != taxonomy_root:
            raise NdxDynamicShadowIdentityEvidenceError("taxonomy artifact escaped canonical root")
        frame, raw = _capture_csv(artifact_path, f"taxonomy {key}")
        if descriptor.get("sha256") != _sha256(raw) or int(descriptor.get("rows", -1)) != len(frame):
            raise NdxDynamicShadowIdentityEvidenceError(f"taxonomy artifact hash changed: {key}")
        frames[key] = frame
        descriptors[key] = {
            "path": artifact_path.as_posix(), "sha256": _sha256(raw), "rows": len(frame),
        }
    required_identity = {
        "security_id", "issuer_id", "ticker", "cik", "cusip",
        "observation_from", "observation_to", "available_from", "available_to",
        "identity_status",
    }
    required_records = {
        "security_id", "issuer_id", "ticker", "selection_dates", "risk_chain",
        "evidence_available_date", "status",
    }
    if not required_identity.issubset(frames["identities"].columns):
        raise NdxDynamicShadowIdentityEvidenceError("taxonomy identity schema changed")
    if not required_records.issubset(frames["records"].columns):
        raise NdxDynamicShadowIdentityEvidenceError("taxonomy record schema changed")
    if frames["identities"]["security_id"].duplicated().any():
        raise NdxDynamicShadowIdentityEvidenceError("taxonomy security_id is not unique")
    return manifest, frames, {
        "present": True,
        "path": manifest_path.as_posix(),
        "sha256": _sha256(manifest_raw),
        "artifacts": descriptors,
    }


def _sec_crosswalk(root: Path) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    data_path = (root / _SEC_PATH).resolve()
    manifest_path = Path(str(data_path) + ".manifest.json")
    if not data_path.is_file() or not manifest_path.is_file():
        return {}, {"present": False, "path": data_path.as_posix()}
    manifest, data_raw, manifest_raw = _dataset_manifest(
        data_path, manifest_path, dataset_type="sec_company_ticker_crosswalk",
    )
    try:
        payload = json.loads(data_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowIdentityEvidenceError("SEC ticker crosswalk is invalid") from exc
    if not isinstance(payload, dict) or payload.get("fields") != ["cik", "name", "ticker", "exchange"]:
        raise NdxDynamicShadowIdentityEvidenceError("SEC ticker crosswalk schema changed")
    by_ticker: dict[str, list[dict[str, str]]] = {}
    for values in payload.get("data") or []:
        if not isinstance(values, list) or len(values) != 4:
            raise NdxDynamicShadowIdentityEvidenceError("SEC ticker crosswalk row is invalid")
        cik, name, ticker, exchange = values
        symbol = str(ticker or "").upper().strip()
        if not symbol:
            continue
        cik_text = str(cik or "").strip()
        if not cik_text.isdigit() or int(cik_text) <= 0:
            raise NdxDynamicShadowIdentityEvidenceError("SEC ticker crosswalk CIK is invalid")
        by_ticker.setdefault(symbol, []).append({
            "cik": f"{int(cik_text):010d}", "name": str(name or "").strip(),
            "ticker": symbol, "exchange": str(exchange or "").strip(),
        })
    duplicate = sorted(key for key, rows in by_ticker.items() if len(rows) != 1)
    if duplicate:
        raise NdxDynamicShadowIdentityEvidenceError(
            f"SEC ticker crosswalk is not unique: {duplicate[:5]}"
        )
    return {key: rows[0] for key, rows in by_ticker.items()}, {
        "present": True,
        "path": data_path.as_posix(),
        "sha256": _sha256(data_raw),
        "manifest_path": manifest_path.as_posix(),
        "manifest_sha256": _sha256(manifest_raw),
        "fetched_at": manifest.get("fetched_at"),
        "publication_time_known": manifest.get("publication_time_known") is True,
        "provides_cusip": False,
    }


def _lifecycle_inventory(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    path = (root / _LIFECYCLE_PATH).resolve()
    if not path.is_file():
        return {}, {"present": False, "path": path.as_posix()}
    try:
        raw = path.read_bytes()
        payload = yaml.safe_load(raw.decode("utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise NdxDynamicShadowIdentityEvidenceError("security lifecycle is invalid") from exc
    if not isinstance(payload, Mapping) or int(payload.get("schema_version", 0)) != 1:
        raise NdxDynamicShadowIdentityEvidenceError("security lifecycle schema changed")
    rows = payload.get("rules")
    if not isinstance(rows, list) or not rows:
        raise NdxDynamicShadowIdentityEvidenceError("security lifecycle rules are missing")
    by_cik: dict[str, dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, Mapping):
            raise NdxDynamicShadowIdentityEvidenceError("security lifecycle rule is invalid")
        cik_raw = str(item.get("cik") or "").strip()
        if not cik_raw.isdigit() or int(cik_raw) <= 0:
            raise NdxDynamicShadowIdentityEvidenceError("security lifecycle CIK is invalid")
        cik = f"{int(cik_raw):010d}"
        if cik in by_cik:
            raise NdxDynamicShadowIdentityEvidenceError("security lifecycle CIK is duplicated")
        recognized = [str(value or "").upper().strip() for value in item.get("recognized_tickers") or []]
        intervals = item.get("intervals")
        evidence = item.get("evidence")
        if (
            not str(item.get("rule_id") or "").strip()
            or len(str(item.get("cusip") or "").strip()) != 9
            or not recognized
            or not isinstance(intervals, list) or not intervals
            or not isinstance(evidence, list) or not evidence
            or any(not isinstance(ev, Mapping) for ev in evidence)
            or any(not str(ev.get("url") or "").startswith("https://") for ev in evidence)
        ):
            raise NdxDynamicShadowIdentityEvidenceError("security lifecycle rule is incomplete")
        by_cik[cik] = {
            "rule_id": str(item["rule_id"]),
            "cusip": str(item["cusip"]).upper(),
            "recognized_tickers": recognized,
            "intervals": [dict(value) for value in intervals],
        }
    return by_cik, {
        "present": True, "path": path.as_posix(), "sha256": _sha256(raw),
        "mapping_id": str(payload.get("mapping_id") or ""), "declared_rule_count": len(by_cik),
    }


def _candidate_snapshot(
    root: Path, decision_date: str,
) -> tuple[dict[str, Any] | None, pd.DataFrame, dict[str, Any]]:
    candidate_root = (root / _CANDIDATE_ROOT).resolve()
    manifest_path = (candidate_root / decision_date / "manifest.json").resolve()
    if not manifest_path.is_file():
        return None, pd.DataFrame(), {
            "present": False, "path": manifest_path.as_posix(), "seal_record_verified": False,
        }
    raw = manifest_path.read_bytes()
    digest = _sha256(raw)
    try:
        captured = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowIdentityEvidenceError("candidate manifest is invalid") from exc
    verified = verify_snapshot_bundle(manifest_path)
    if manifest_path.read_bytes() != raw or verified != captured or verified.get("decision_date") != decision_date:
        raise NdxDynamicShadowIdentityEvidenceError("candidate manifest changed during verification")
    descriptor = (verified.get("artifacts") or {}).get("eligible_securities") or {}
    eligible_path = (manifest_path.parent / str(descriptor.get("filename") or "")).resolve()
    if eligible_path.parent != manifest_path.parent:
        raise NdxDynamicShadowIdentityEvidenceError("candidate eligible artifact escaped snapshot")
    eligible, eligible_raw = _capture_csv(eligible_path, "candidate eligible securities")
    if descriptor.get("sha256") != _sha256(eligible_raw) or int(descriptor.get("rows", -1)) != len(eligible):
        raise NdxDynamicShadowIdentityEvidenceError("candidate eligible artifact changed")
    seal_verified = False
    seal_digest = None
    ledger_path = candidate_root / "decision_seals.jsonl"
    if ledger_path.is_file():
        from scripts.ndx_dynamic_shadow_candidate_generator import _load_and_validate_seal_ledger

        records = _load_and_validate_seal_ledger(ledger_path, expected_root=candidate_root)
        matching = [row for row in records if row.get("decision_date") == decision_date]
        if len(matching) != 1:
            raise NdxDynamicShadowIdentityEvidenceError("candidate decision seal is not unique")
        record = matching[0]
        if (
            record.get("snapshot_manifest_sha256") != digest
            or record.get("snapshot_fingerprint") != verified.get("snapshot_fingerprint")
        ):
            raise NdxDynamicShadowIdentityEvidenceError("candidate decision seal disagrees")
        seal_verified = True
        seal_digest = record.get("record_sha256")
    return verified, eligible, {
        "present": True, "path": manifest_path.as_posix(), "sha256": digest,
        "snapshot_bundle_verified": True, "seal_record_verified": seal_verified,
        "seal_record_sha256": seal_digest,
    }


def _select_taxonomy_record(
    records: pd.DataFrame, security_id: str, decision_date: str,
) -> dict[str, Any] | None:
    matches = records.loc[records["security_id"].eq(security_id)].copy()
    if matches.empty:
        return None
    decision = date.fromisoformat(decision_date)
    matches["_selection_dates_parsed"] = matches["selection_dates"].map(
        lambda value: _selection_dates(value, "taxonomy selection date")
    )
    matches["_last"] = matches["_selection_dates_parsed"].map(
        lambda values: max(values, default=None)
    )
    matches["_evidence_available"] = matches["evidence_available_date"].map(
        lambda value: _optional_date(value, "taxonomy evidence_available_date")
    )
    matches = matches.loc[
        matches["_last"].notna()
        & matches["_last"].le(decision)
        & matches["_evidence_available"].notna()
        & matches["_evidence_available"].le(decision)
    ]
    if matches.empty:
        return None
    matches = matches.loc[matches["_last"].eq(matches["_last"].max())]
    matches = matches.loc[
        matches["_evidence_available"].eq(matches["_evidence_available"].max())
    ]
    if len(matches) != 1:
        raise NdxDynamicShadowIdentityEvidenceError(
            "latest taxonomy record is ambiguous for security_id"
        )
    return matches.iloc[0].to_dict()


def _ticker_aliases(value: Any) -> set[str]:
    return {part.strip().upper() for part in str(value or "").split(";") if part.strip()}


def _select_historical_identity_for_ticker(
    identities: pd.DataFrame, *, ticker: str, decision_date: str,
) -> tuple[dict[str, Any] | None, str]:
    """Select only a fully available latest historical row, never infer validity."""

    if identities.empty:
        return None, "HISTORICAL_IDENTITY_SOURCE_MISSING"
    matches = identities.loc[
        identities["ticker"].map(lambda value: ticker in _ticker_aliases(value))
    ].copy()
    if matches.empty:
        return None, "HISTORICAL_TICKER_OR_ALIAS_MISSING"
    decision = date.fromisoformat(decision_date)
    matches["_available_to"] = matches["available_to"].map(
        lambda value: _optional_date(value, "historical identity available_to")
    )
    matches = matches.loc[
        matches["_available_to"].notna() & matches["_available_to"].le(decision)
    ].copy()
    if matches.empty:
        return None, "HISTORICAL_IDENTITY_NOT_FULLY_AVAILABLE_BY_DECISION"
    latest = matches["_available_to"].max()
    selected = matches.loc[matches["_available_to"].eq(latest)]
    if len(selected) != 1:
        return None, "HISTORICAL_IDENTITY_LATEST_AVAILABLE_ROW_AMBIGUOUS"
    return selected.iloc[0].to_dict(), "LATEST_FULLY_AVAILABLE_HISTORICAL_ROW_NOT_CURRENT_PROOF"


def _lifecycle_state(
    rule: Mapping[str, Any] | None, *, cik: str, cusip: str, ticker: str,
    valid_on_date: str,
) -> tuple[str, str, list[str]]:
    if rule is None:
        return "NOT_DECLARED_SAME_TICKER_NOT_PROOF", ticker, [
            "NO_DECLARED_RENAME_RULE_GENERAL_IDENTITY_NOT_PROVED"
        ]
    if ticker not in set(rule["recognized_tickers"]):
        raise NdxDynamicShadowIdentityEvidenceError("candidate ticker conflicts with lifecycle rule")
    if cusip and cusip != rule["cusip"]:
        raise NdxDynamicShadowIdentityEvidenceError("candidate CUSIP conflicts with lifecycle rule")
    matches = []
    for interval in rule["intervals"]:
        begin = str(interval.get("effective_from") or "")
        end = str(interval.get("effective_to") or "")
        if (not begin or valid_on_date >= begin) and (not end or valid_on_date <= end):
            matches.append(str(interval.get("price_ticker") or "").upper().strip())
    if len(matches) != 1 or not matches[0]:
        raise NdxDynamicShadowIdentityEvidenceError("lifecycle interval is ambiguous")
    return "DECLARED_ALIAS_INTERVAL_NOT_FULL_IDENTITY_PROOF", matches[0], [
        "DECLARED_RENAME_RULE_DOES_NOT_PROVE_GENERAL_VALID_ON_DATE_IDENTITY"
    ]


def build_identity_evidence_inventory(
    repository_root: str | Path,
    *,
    decision_date: str,
    valid_on_date: str | None = None,
) -> dict[str, Any]:
    """Rebuild an evidence inventory without granting selection authority."""

    root = Path(repository_root).resolve()
    decision = _iso_date(decision_date, "decision_date")
    valid_date = _iso_date(valid_on_date or decision, "valid_on_date")
    if valid_date < decision:
        raise NdxDynamicShadowIdentityEvidenceError("valid_on_date precedes decision_date")

    candidate, eligible, candidate_source = _candidate_snapshot(root, decision)
    taxonomy_manifest, taxonomy_frames, taxonomy_source = _taxonomy_bundle(root)
    sec, sec_source = _sec_crosswalk(root)
    lifecycle, lifecycle_source = _lifecycle_inventory(root)

    official_path: Path | None = None
    official_manifest: dict[str, Any] | None = None
    official_manifest_digest: str | None = None
    official = pd.DataFrame()
    if candidate is not None:
        paths = candidate.get("source_paths") or {}
        versions = candidate.get("source_versions") or {}
        official_path = Path(str(paths.get("official_snapshot_sha256") or "")).resolve()
        expected_root = (root / _OFFICIAL_ROOT).resolve()
        official_manifest_path = Path(str(paths.get("official_snapshot_manifest_sha256") or "")).resolve()
        if (
            official_path.parent != expected_root
            or official_manifest_path != Path(str(official_path) + ".manifest.json")
            or paths.get("taxonomy_manifest_sha256") != (root / _TAXONOMY_ROOT / "manifest.json").resolve().as_posix()
            or paths.get("security_lifecycle_sha256") != (root / _LIFECYCLE_PATH).resolve().as_posix()
        ):
            raise NdxDynamicShadowIdentityEvidenceError("candidate source path registry changed")
        official_manifest, official_raw, official_manifest_raw = _dataset_manifest(
            official_path, official_manifest_path, dataset_type="security_pool_snapshot",
        )
        official_manifest_digest = _sha256(official_manifest_raw)
        if (
            versions.get("official_snapshot_sha256") != _sha256(official_raw)
            or versions.get("official_snapshot_manifest_sha256") != official_manifest_digest
            or versions.get("taxonomy_manifest_sha256") != taxonomy_source.get("sha256")
            or versions.get("security_lifecycle_sha256") != lifecycle_source.get("sha256")
        ):
            raise NdxDynamicShadowIdentityEvidenceError("candidate source hash registry changed")
        official = pd.read_csv(io.BytesIO(official_raw), dtype=str, keep_default_na=False)
        official["ticker"] = official["ticker"].str.upper().str.strip()
    else:
        official_path, official_manifest, official, official_manifest_digest = (
            _load_latest_official_archive(root)
        )

    official_by_ticker = (
        official.set_index("ticker", drop=False).to_dict("index") if not official.empty else {}
    )
    identities = taxonomy_frames.get("identities", pd.DataFrame())
    records = taxonomy_frames.get("records", pd.DataFrame())
    identity_by_security = (
        identities.set_index("security_id", drop=False).to_dict("index")
        if not identities.empty else {}
    )
    if not eligible.empty:
        source_rows = eligible.to_dict("records")
        universe_basis = "SEALED_CANDIDATE_ELIGIBLE_ROWS"
    else:
        source_rows = [{"ticker": ticker, "universe_track": "UNSEALED_LATEST_OFFICIAL_DIAGNOSTIC"}
                       for ticker in sorted(official_by_ticker)]
        universe_basis = "LATEST_OFFICIAL_OBSERVATION_DIAGNOSTIC_NOT_DECISION_POOL"

    rows = []
    for source_row in source_rows:
        ticker = str(source_row.get("ticker") or "").upper().strip()
        security_id = str(source_row.get("security_id") or "").strip()
        if security_id:
            identity = identity_by_security.get(security_id)
            identity_resolution_status = (
                "CANDIDATE_SECURITY_ID_EXACT_HISTORICAL_ROW"
                if identity is not None else "CANDIDATE_SECURITY_ID_NOT_IN_HISTORICAL_IDENTITY"
            )
        else:
            identity, identity_resolution_status = _select_historical_identity_for_ticker(
                identities, ticker=ticker, decision_date=decision,
            )
        identity = dict(identity or {})
        if not security_id:
            security_id = str(identity.get("security_id") or "")
        issuer_id = str(source_row.get("issuer_id") or identity.get("issuer_id") or "")
        cik_raw = str(identity.get("cik") or "").strip()
        cik = f"{int(cik_raw):010d}" if cik_raw.isdigit() and int(cik_raw) > 0 else ""
        cusip = str(identity.get("cusip") or "").upper().strip()
        official_row = official_by_ticker.get(ticker)
        sec_row = sec.get(ticker)
        taxonomy_record = _select_taxonomy_record(records, security_id, decision) if security_id and not records.empty else None
        if candidate is not None and identity:
            if (
                str(identity.get("issuer_id") or "") != issuer_id
                or ticker not in _ticker_aliases(identity.get("ticker"))
            ):
                raise NdxDynamicShadowIdentityEvidenceError(
                    "candidate identity disagrees with historical identity artifact"
                )
        if candidate is not None and taxonomy_record is not None:
            if (
                str(taxonomy_record.get("issuer_id") or "") != issuer_id
                or ticker not in _ticker_aliases(taxonomy_record.get("ticker"))
                or str(taxonomy_record.get("risk_chain") or "")
                != str(source_row.get("risk_chain") or "")
            ):
                raise NdxDynamicShadowIdentityEvidenceError(
                    "candidate taxonomy identity disagrees with historical artifact"
                )
        historical_date_values = _selection_dates(
            (taxonomy_record or {}).get("selection_dates"), "taxonomy selection date",
        )
        historical_dates = [value.isoformat() for value in historical_date_values]
        historical_last = max(
            historical_dates,
            default=(
                _optional_date(identity.get("available_to"), "historical identity available_to").isoformat()
                if identity and _optional_date(
                    identity.get("available_to"), "historical identity available_to",
                ) is not None
                else ""
            ),
        )
        sec_comparable = bool(sec_row and cik and issuer_id)
        sec_match = bool(
            sec_row and cik and sec_row["cik"] == cik
            and (not issuer_id or issuer_id == f"issuer:{cik}")
        )
        lifecycle_status, price_ticker, lifecycle_gaps = _lifecycle_state(
            lifecycle.get(cik), cik=cik, cusip=cusip, ticker=ticker,
            valid_on_date=valid_date,
        )
        gaps = []
        if candidate is None:
            gaps.append("CANDIDATE_DECISION_SNAPSHOT_NOT_SEALED")
        elif not candidate_source["seal_record_verified"]:
            gaps.append("CANDIDATE_DECISION_SEAL_RECORD_MISSING")
        if official_row is None:
            gaps.append("TICKER_NOT_IN_BOUND_OFFICIAL_MEMBERSHIP_OBSERVATION")
        else:
            gaps.extend([
                "OFFICIAL_MEMBERSHIP_EFFECTIVE_DATE_UNKNOWN",
                "OFFICIAL_MEMBERSHIP_HAS_NO_CIK_OR_CUSIP",
            ])
            if str((official_row or {}).get("as_of_date") or "") != decision:
                gaps.append("OFFICIAL_MEMBERSHIP_NOT_OBSERVED_ON_DECISION_DATE")
        if not identity:
            gaps.append("HISTORICAL_SECURITY_IDENTITY_MISSING")
        elif str(identity.get("identity_status")) != "resolved":
            gaps.append("HISTORICAL_SECURITY_IDENTITY_UNRESOLVED")
        if decision not in historical_dates:
            gaps.append("HISTORICAL_IDENTITY_NOT_OBSERVED_ON_DECISION_DATE")
        if taxonomy_record is None or str(taxonomy_record.get("status")) != "accepted":
            gaps.append("ACCEPTED_RISK_CHAIN_EVIDENCE_MISSING")
        if sec_row is None:
            gaps.append("SEC_CURRENT_TICKER_CROSSCHECK_MISSING")
        else:
            if not sec_comparable:
                gaps.append("SEC_ISSUER_CIK_CROSSCHECK_NOT_POSSIBLE")
            elif not sec_match:
                gaps.append("SEC_ISSUER_CIK_CROSSCHECK_MISMATCH")
            gaps.append("SEC_CURRENT_TICKER_CROSSCHECK_HAS_NO_CUSIP")
            if str(sec_source.get("fetched_at") or "")[:10] != decision:
                gaps.append("SEC_CURRENT_TICKER_CROSSCHECK_NOT_CAPTURED_ON_DECISION_DATE")
        gaps.extend(lifecycle_gaps)
        gaps.append("EXECUTION_VALID_ON_DATE_SECURITY_IDENTITY_NOT_PROVED")
        rows.append({
            "universe_track": str(source_row.get("universe_track") or ""),
            "ticker": ticker,
            "security_id": security_id,
            "issuer_id": issuer_id,
            "cik": cik,
            "cusip": cusip,
            "official_name": str((official_row or {}).get("name") or ""),
            "official_source_as_of_label_equals_decision_date": bool(
                official_row is not None and str((official_row or {}).get("as_of_date") or "") == decision
            ),
            "official_fetch_timestamp_date_equals_decision_date": bool(
                official_manifest is not None
                and str(official_manifest.get("fetched_at") or "")[:10] == decision
            ),
            "official_membership_observed_on_decision_date": bool(
                official_row is not None
                and str((official_row or {}).get("as_of_date") or "") == decision
                and str((official_manifest or {}).get("fetched_at") or "")[:10] == decision
            ),
            "official_membership_effective_date_known": False,
            "historical_identity_resolution_status": identity_resolution_status,
            "historical_identity_status": str(identity.get("identity_status") or "missing"),
            "historical_last_observation_date": historical_last,
            "historical_taxonomy_selection_coordinate_equals_decision_date": decision in historical_dates,
            "historical_identity_observed_on_decision_date": decision in historical_dates,
            "risk_chain": str(source_row.get("risk_chain") or (taxonomy_record or {}).get("risk_chain") or ""),
            "risk_chain_evidence_status": str((taxonomy_record or {}).get("status") or "missing"),
            "sec_crosscheck_cik": str((sec_row or {}).get("cik") or ""),
            "sec_crosscheck_name": str((sec_row or {}).get("name") or ""),
            "sec_issuer_cik_matches": sec_match,
            "sec_crosscheck_provides_cusip": False,
            "lifecycle_status": lifecycle_status,
            "lifecycle_rule_id": str((lifecycle.get(cik) or {}).get("rule_id") or ""),
            "price_ticker_on_requested_valid_date": price_ticker,
            "decision_identity_mapping_hash_bound": candidate is not None and candidate_source["seal_record_verified"],
            "execution_valid_on_date_proved": False,
            "identity_gap_codes": sorted(set(gaps)),
        })

    all_gaps = {gap for row in rows for gap in row["identity_gap_codes"]}
    if candidate is None:
        all_gaps.add("CANDIDATE_DECISION_SNAPSHOT_NOT_SEALED")
    elif not candidate_source["seal_record_verified"]:
        all_gaps.add("CANDIDATE_DECISION_SEAL_RECORD_MISSING")
    if official_manifest is None:
        all_gaps.add("OFFICIAL_MEMBERSHIP_SOURCE_MISSING")
    if not taxonomy_source.get("present"):
        all_gaps.add("HISTORICAL_IDENTITY_TAXONOMY_SOURCE_MISSING")
    if not sec_source.get("present"):
        all_gaps.add("SEC_CURRENT_TICKER_CROSSCHECK_SOURCE_MISSING")
    if not lifecycle_source.get("present"):
        all_gaps.add("DECLARED_TICKER_LIFECYCLE_SOURCE_MISSING")
    all_gaps.add("EXECUTION_VALID_ON_DATE_SECURITY_IDENTITY_NOT_PROVED")
    official_source = {
        "present": official_manifest is not None,
        "path": official_path.as_posix() if official_path else None,
        "sha256": official_manifest.get("content_sha256") if official_manifest else None,
        "manifest_sha256": official_manifest_digest,
        "as_of_date": official_manifest.get("as_of_date") if official_manifest else None,
        "fetched_at": official_manifest.get("fetched_at") if official_manifest else None,
        "source_effective_date_known": False,
        "provides_cik": False,
        "provides_cusip": False,
    }
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_identity_evidence_inventory",
        "status": (
            "BLOCKED_CANDIDATE_DECISION_NOT_SEALED"
            if candidate is None else "BLOCKED_EXECUTION_VALID_ON_DATE_IDENTITY_NOT_PROVED"
        ),
        "research_track": "portfolio_optimization",
        "decision_date": decision,
        "requested_valid_on_date": valid_date,
        "universe_basis": universe_basis,
        "security_row_count": len(rows),
        "source_inventory": {
            "candidate_snapshot": candidate_source,
            "official_membership_observation": official_source,
            "historical_identity_and_taxonomy": taxonomy_source,
            "sec_current_ticker_crosscheck": sec_source,
            "declared_ticker_lifecycle": lifecycle_source,
        },
        "gap_codes": sorted(all_gaps),
        "security_evidence": rows,
        "decision_identity_mapping_is_execution_identity_proof": False,
        "execution_valid_on_date_proved": False,
        "admission_authority": False,
        "candidate_admission_allowed": False,
        "policy_admission_performed": False,
        "promotion_allowed": False,
        "live_mutation": False,
        "broker_data_read": False,
        "external_data_fetched": False,
        "orders_created": False,
    }


__all__ = [
    "NdxDynamicShadowIdentityEvidenceError",
    "build_identity_evidence_inventory",
]
