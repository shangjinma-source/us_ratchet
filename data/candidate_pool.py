"""Versioned current security pools and fail-closed candidate governance.

Current Nasdaq-100 and QQQ snapshots are useful for today's screening and
forward observation.  They are deliberately not historical constituent data:
every manifest and derived registry carries a hard guard that prevents these
files from being presented as point-in-time backtest inputs.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd
import yaml

from core.helpers import atomic_write_text, project_root, proxy_env
from data.versioning import (
    file_sha256,
    manifest_path,
    utc_now_iso,
    write_dataset_manifest,
)


NASDAQ_NDX_COMPANIES_URL = (
    "https://www.nasdaq.com/solutions/global-indexes/nasdaq-100/companies"
)
INVESCO_QQQ_PRODUCT_URL = (
    "https://www.invesco.com/us/en/financial-products/etfs/"
    "invesco-qqq-trust-series-1.html"
)

CURRENT_ONLY_SCOPE = "current_snapshot_only"
MIN_NDX_SECURITIES = 100
MAX_NDX_SECURITIES = 110
MIN_QQQ_EQUITY_HOLDINGS = 90
MAX_QQQ_EQUITY_HOLDINGS = 120
MIN_PRICE_ROWS = 504
MAX_CURRENT_SCREEN_LAG_BUSINESS_DAYS = 3

SNAPSHOT_COLUMNS = [
    "as_of_date",
    "source_type",
    "source_id",
    "ticker",
    "name",
    "weight",
    "sector",
    "source_locator",
]

REQUIRED_TAXONOMY_CATEGORIES = {
    "platform_cloud_apps",
    "ai_accelerators",
    "semiconductor_equipment",
    "eda_ip",
    "foundry",
    "memory",
    "analog_power",
    "optical_network",
    "power_datacenter_chain",
}


class CandidatePoolError(RuntimeError):
    pass


class _JsonLdParser(HTMLParser):
    """Collect JSON-LD scripts without depending on attribute order or quoting."""

    def __init__(self) -> None:
        super().__init__()
        self._capturing = False
        self._parts: list[str] = []
        self.documents: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "script":
            return
        values = {str(key).lower(): str(value or "").lower() for key, value in attrs}
        if values.get("type") == "application/ld+json":
            self._capturing = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capturing:
            self.documents.append("".join(self._parts).strip())
            self._capturing = False
            self._parts = []


@dataclass
class CandidatePoolMeta:
    source_id: str
    source: str
    rows: int
    as_of_date: str
    cached: bool
    stale: bool = False
    manifest: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "source": self.source,
            "rows": int(self.rows),
            "as_of_date": self.as_of_date,
            "cached": bool(self.cached),
            "stale": bool(self.stale),
            "version_id": self.manifest.get("version_id"),
            "fetched_at": self.manifest.get("fetched_at"),
            "source_locator": self.manifest.get("source_locator"),
            "point_in_time_scope": self.manifest.get("point_in_time_scope"),
            "historical_backtest_allowed": bool(
                self.manifest.get("historical_backtest_allowed", False)
            ),
            "errors": dict(self.errors),
        }


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "table" and self._table is None:
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def _cache_dir(cfg) -> Path:
    direct = getattr(cfg, "cache_dir", None)
    if direct is not None:
        return Path(direct)
    data_cfg = getattr(cfg, "data", None)
    if data_cfg is not None and getattr(data_cfg, "cache_dir", None):
        return Path(data_cfg.cache_dir)
    return Path("data/cache")


def _proxy_cfg(cfg):
    data_cfg = getattr(cfg, "data", None)
    return getattr(data_cfg, "proxy", None)


def _pool_dir(cfg) -> Path:
    return _cache_dir(cfg) / "candidate_pools"


def _current_path(cfg, source_id: str) -> Path:
    return _pool_dir(cfg) / f"{source_id}_current.csv"


def _snapshot_dir(cfg, source_id: str) -> Path:
    return _pool_dir(cfg) / "snapshots" / source_id


def _registry_path(cfg) -> Path:
    return _pool_dir(cfg) / "security_candidate_registry_current.json"


def _normalize_date(value: str) -> str:
    raw = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise CandidatePoolError(f"invalid as_of_date: {value!r}") from exc


def _valid_ticker(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", str(value or "")))


def _normalize_snapshot(
    frame: pd.DataFrame,
    *,
    source_id: str,
    source_type: str,
) -> pd.DataFrame:
    missing = set(SNAPSHOT_COLUMNS) - set(frame.columns)
    if missing:
        raise CandidatePoolError(f"{source_id}: snapshot missing columns {sorted(missing)}")
    out = frame[SNAPSHOT_COLUMNS].copy()
    out["ticker"] = out["ticker"].fillna("").astype(str).str.upper().str.strip()
    out["name"] = out["name"].fillna("").astype(str).str.strip()
    out["sector"] = out["sector"].fillna("").astype(str).str.strip()
    out["source_locator"] = out["source_locator"].fillna("").astype(str).str.strip()
    out["source_id"] = out["source_id"].fillna("").astype(str).str.strip()
    out["source_type"] = out["source_type"].fillna("").astype(str).str.strip()
    out["as_of_date"] = out["as_of_date"].map(_normalize_date)
    out["weight"] = pd.to_numeric(out["weight"], errors="coerce")

    if out.empty:
        raise CandidatePoolError(f"{source_id}: snapshot is empty")
    if out["as_of_date"].nunique() != 1:
        raise CandidatePoolError(f"{source_id}: snapshot contains multiple as_of dates")
    if set(out["source_id"]) != {source_id}:
        raise CandidatePoolError(f"{source_id}: source_id mismatch")
    if set(out["source_type"]) != {source_type}:
        raise CandidatePoolError(f"{source_id}: source_type mismatch")
    invalid = sorted(t for t in out["ticker"] if not _valid_ticker(t))
    if invalid:
        raise CandidatePoolError(f"{source_id}: invalid tickers {invalid[:8]}")
    duplicates = sorted(out.loc[out["ticker"].duplicated(False), "ticker"].unique())
    if duplicates:
        raise CandidatePoolError(f"{source_id}: duplicate tickers {duplicates}")
    if (out["name"] == "").any():
        raise CandidatePoolError(f"{source_id}: blank company names")
    weights = out["weight"].dropna()
    if ((weights < 0) | (weights > 1)).any():
        raise CandidatePoolError(f"{source_id}: weights outside [0, 1]")
    return out.sort_values("ticker", kind="stable").reset_index(drop=True)


def parse_nasdaq_ndx_companies(
    html_text: str,
    *,
    as_of_date: str,
    known_name_to_ticker: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Parse the official Nasdaq-100 companies table with completeness checks."""
    if not re.search(r"nasdaq\s*[-–]\s*100", html_text or "", re.IGNORECASE):
        raise CandidatePoolError("nasdaq_100: response does not identify Nasdaq-100")
    parser = _TableParser()
    parser.feed(html_text)
    selected: list[list[str]] | None = None
    for table in parser.tables:
        if not table:
            continue
        header = [re.sub(r"\s+", " ", cell).strip().lower() for cell in table[0]]
        if len(header) >= 2 and header[0] == "symbol" and header[1] == "company name":
            selected = table
            break
    raw_rows: list[tuple[str, str]] = []
    ticker_name_fallbacks: list[dict[str, str]] = []
    if selected is not None:
        for cells in selected[1:]:
            if len(cells) < 2:
                continue
            ticker = str(cells[0]).upper().strip()
            name = str(cells[1]).strip()
            if ticker or name:
                raw_rows.append((ticker, name))
    else:
        json_ld = _JsonLdParser()
        json_ld.feed(html_text)

        def walk(value):
            if isinstance(value, dict):
                yield value
                for child in value.values():
                    yield from walk(child)
            elif isinstance(value, list):
                for child in value:
                    yield from walk(child)

        candidates: list[list[tuple[str, str]]] = []
        for document in json_ld.documents:
            try:
                payload = json.loads(document)
            except (TypeError, ValueError):
                continue
            for node in walk(payload):
                node_type = node.get("@type")
                types = (
                    {str(item) for item in node_type}
                    if isinstance(node_type, list)
                    else {str(node_type)}
                )
                if "ItemList" not in types:
                    continue
                identity = " ".join(
                    str(node.get(key) or "") for key in ("@id", "name", "description")
                ).lower()
                if "nasdaq-100" not in identity and "nasdaq 100" not in identity:
                    continue
                parsed: list[tuple[str, str]] = []
                for item in node.get("itemListElement") or []:
                    if not isinstance(item, dict):
                        continue
                    ticker = str(item.get("description") or "").upper().strip()
                    name = str(item.get("name") or "").strip()
                    if not ticker and known_name_to_ticker:
                        normalized_name = re.sub(r"\s+", " ", name).strip().upper()
                        fallback = str(known_name_to_ticker.get(normalized_name) or "").upper().strip()
                        if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", fallback):
                            ticker = fallback
                            ticker_name_fallbacks.append({"name": name, "ticker": ticker})
                    if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", ticker) and name:
                        parsed.append((ticker, name))
                if parsed:
                    candidates.append(parsed)
        complete = [
            value for value in candidates
            if MIN_NDX_SECURITIES <= len(value) <= MAX_NDX_SECURITIES
        ]
        if complete:
            raw_rows = max(complete, key=len)

    if not raw_rows:
        raise CandidatePoolError(
            "nasdaq_100: official constituent table or JSON-LD ItemList not found"
        )

    rows = []
    for ticker, name in raw_rows:
        rows.append({
            "as_of_date": _normalize_date(as_of_date),
            "source_type": "index_constituent",
            "source_id": "nasdaq_100",
            "ticker": ticker,
            "name": name,
            "weight": None,
            "sector": "",
            "source_locator": NASDAQ_NDX_COMPANIES_URL,
        })
    frame = _normalize_snapshot(
        pd.DataFrame(rows), source_id="nasdaq_100", source_type="index_constituent"
    )
    if not MIN_NDX_SECURITIES <= len(frame) <= MAX_NDX_SECURITIES:
        raise CandidatePoolError(
            "nasdaq_100: incomplete or implausible constituent security count; "
            f"expected={MIN_NDX_SECURITIES}..{MAX_NDX_SECURITIES}, parsed={len(frame)}"
        )
    frame.attrs["ticker_name_fallbacks"] = ticker_name_fallbacks
    return frame


def _snapshot_guard_extra(
    *,
    as_of_date: str,
    as_of_date_evidence: str,
    source_effective_date_known: bool,
) -> dict:
    return {
        "as_of_date": as_of_date,
        "as_of_date_evidence": as_of_date_evidence,
        "source_effective_date_known": bool(source_effective_date_known),
        "publication_time_known": False,
        "point_in_time_scope": CURRENT_ONLY_SCOPE,
        "historical_backtest_allowed": False,
        "allowed_uses": [
            "current_candidate_screen",
            "current_control_group",
            "forward_observation",
        ],
        "prohibited_uses": [
            "historical_constituent_backtest",
            "historical_membership_inference",
            "backfill_before_as_of_date",
        ],
    }


def _strict_manifest(path: Path, *, source_id: str) -> dict:
    target = manifest_path(path)
    if not target.exists():
        raise CandidatePoolError(f"{source_id}: manifest missing: {target}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise CandidatePoolError(f"{source_id}: invalid manifest: {target}") from exc
    if payload.get("content_sha256") != file_sha256(path):
        raise CandidatePoolError(f"{source_id}: cache hash does not match manifest")
    if (
        payload.get("dataset_type") != "security_pool_current"
        or payload.get("dataset_key") != source_id
    ):
        raise CandidatePoolError(f"{source_id}: manifest identity mismatch")
    if payload.get("point_in_time_scope") != CURRENT_ONLY_SCOPE:
        raise CandidatePoolError(f"{source_id}: current-only guard missing")
    if payload.get("historical_backtest_allowed") is not False:
        raise CandidatePoolError(f"{source_id}: historical backtest guard is not fail-closed")
    return payload


def _load_snapshot(
    cfg,
    *,
    source_id: str,
    source_type: str,
) -> tuple[pd.DataFrame, CandidatePoolMeta]:
    path = _current_path(cfg, source_id)
    if not path.exists():
        raise CandidatePoolError(f"{source_id}: current snapshot missing: {path}")
    manifest = _strict_manifest(path, source_id=source_id)
    frame = _normalize_snapshot(
        pd.read_csv(path), source_id=source_id, source_type=source_type
    )
    if int(manifest.get("row_count") or -1) != len(frame):
        raise CandidatePoolError(f"{source_id}: row count does not match manifest")
    as_of = str(frame["as_of_date"].iloc[0])
    if manifest.get("as_of_date") != as_of:
        raise CandidatePoolError(f"{source_id}: as-of date does not match manifest")
    return frame, CandidatePoolMeta(
        source_id=source_id,
        source=str(manifest.get("source") or "candidate_pool_cache"),
        rows=len(frame),
        as_of_date=as_of,
        cached=True,
        manifest=manifest,
    )


def _write_snapshot(
    cfg,
    frame: pd.DataFrame,
    *,
    source_id: str,
    source_type: str,
    source: str,
    source_locator: str,
    fetched_at: str,
    completeness: str,
    as_of_date_evidence: str,
    source_effective_date_known: bool,
    extra: dict | None = None,
) -> tuple[pd.DataFrame, CandidatePoolMeta]:
    normalized = _normalize_snapshot(
        frame, source_id=source_id, source_type=source_type
    )
    as_of = str(normalized["as_of_date"].iloc[0])
    previous_tickers: set[str] | None = None
    previous_version = None
    try:
        previous, previous_meta = _load_snapshot(
            cfg, source_id=source_id, source_type=source_type
        )
        previous_tickers = set(previous["ticker"])
        previous_version = previous_meta.manifest.get("version_id")
    except CandidatePoolError:
        pass

    current_tickers = set(normalized["ticker"])
    observed_added = sorted(current_tickers - previous_tickers) if previous_tickers is not None else []
    observed_removed = sorted(previous_tickers - current_tickers) if previous_tickers is not None else []
    csv_text = normalized.to_csv(index=False, lineterminator="\n")
    content_hash = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    guard = _snapshot_guard_extra(
        as_of_date=as_of,
        as_of_date_evidence=as_of_date_evidence,
        source_effective_date_known=source_effective_date_known,
    )
    manifest_extra = {
        **guard,
        "completeness": completeness,
        "source_record_count": len(normalized),
        "source_confidence": "official_source_runtime_or_export",
        "previous_version_id": previous_version,
        "observed_added": observed_added,
        "observed_removed": observed_removed,
        "observed_change_date_kind": "local_snapshot_comparison_not_official_effective_date",
        **(extra or {}),
    }

    archive = _snapshot_dir(cfg, source_id) / f"{as_of}_{content_hash[:12]}.csv"
    if not archive.exists():
        atomic_write_text(archive, csv_text)
        write_dataset_manifest(
            archive,
            dataset_type="security_pool_snapshot",
            dataset_key=f"{source_id}:{as_of}:{content_hash[:12]}",
            source=source,
            source_locator=source_locator,
            fetched_at=fetched_at,
            row_count=len(normalized),
            data_start=as_of,
            data_end=as_of,
            extra={**manifest_extra, "immutable_snapshot": True},
        )

    current = _current_path(cfg, source_id)
    atomic_write_text(current, csv_text)
    manifest = write_dataset_manifest(
        current,
        dataset_type="security_pool_current",
        dataset_key=source_id,
        source=source,
        source_locator=source_locator,
        fetched_at=fetched_at,
        row_count=len(normalized),
        data_start=as_of,
        data_end=as_of,
        extra={
            **manifest_extra,
            "immutable_snapshot": False,
            "archive_path": archive.as_posix(),
        },
    )
    return normalized, CandidatePoolMeta(
        source_id=source_id,
        source=source,
        rows=len(normalized),
        as_of_date=as_of,
        cached=False,
        manifest=manifest,
    )


def _fetch_nasdaq_html(cfg) -> tuple[str, str]:
    import requests

    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    }
    with proxy_env(_proxy_cfg(cfg)):
        response = requests.get(
            NASDAQ_NDX_COMPANIES_URL, headers=headers, timeout=30
        )
    if response.status_code != 200:
        raise CandidatePoolError(f"nasdaq_100: HTTP {response.status_code}")
    if not response.text.strip():
        raise CandidatePoolError("nasdaq_100: empty response")
    return response.text, utc_now_iso()


def refresh_nasdaq_100_snapshot(cfg) -> tuple[pd.DataFrame, CandidatePoolMeta]:
    """Refresh the complete current list; incomplete responses never overwrite cache."""
    try:
        html_text, fetched_at = _fetch_nasdaq_html(cfg)
        fetch_day = datetime.fromisoformat(fetched_at).astimezone(timezone.utc).date().isoformat()
        known_name_to_ticker: dict[str, str] = {}
        try:
            previous, _ = _load_snapshot(
                cfg, source_id="nasdaq_100", source_type="index_constituent"
            )
            normalized_names = previous["name"].astype(str).map(
                lambda value: re.sub(r"\s+", " ", value).strip().upper()
            )
            counts = normalized_names.value_counts()
            known_name_to_ticker = {
                name: str(ticker).upper().strip()
                for name, ticker in zip(normalized_names, previous["ticker"].astype(str))
                if counts.get(name, 0) == 1
            }
        except Exception:
            known_name_to_ticker = {}
        frame = parse_nasdaq_ndx_companies(
            html_text,
            as_of_date=fetch_day,
            known_name_to_ticker=known_name_to_ticker,
        )
        ticker_name_fallbacks = list(frame.attrs.get("ticker_name_fallbacks") or [])
        return _write_snapshot(
            cfg,
            frame,
            source_id="nasdaq_100",
            source_type="index_constituent",
            source="nasdaq_ndx_official_companies_page",
            source_locator=NASDAQ_NDX_COMPANIES_URL,
            fetched_at=fetched_at,
            completeness="validated_unique_security_count_100_to_110",
            as_of_date_evidence="runtime_fetch_date_not_source_effective_date",
            source_effective_date_known=False,
            extra={
                "index_id": "NDX",
                "source_company_count_claim": 100,
                "observed_security_count": len(frame),
                "weights_available": False,
                "sector_available": False,
                "ticker_name_fallback_count": len(ticker_name_fallbacks),
                "ticker_name_fallbacks": ticker_name_fallbacks,
                "ticker_name_fallback_rule": "exact_unique_company_name_from_last_complete_official_snapshot",
            },
        )
    except Exception as exc:
        try:
            frame, meta = _load_snapshot(
                cfg, source_id="nasdaq_100", source_type="index_constituent"
            )
        except Exception as cache_exc:
            raise CandidatePoolError(
                "nasdaq_100: refresh failed and no complete cache is available; "
                f"refresh={exc!r}; cache={cache_exc!r}"
            ) from cache_exc
        meta.stale = True
        meta.source = "nasdaq_100_cache_stale"
        meta.errors = {"refresh": str(exc)}
        return frame, meta


def get_nasdaq_100_snapshot(
    cfg, *, refresh: bool = False
) -> tuple[pd.DataFrame, CandidatePoolMeta]:
    if refresh:
        return refresh_nasdaq_100_snapshot(cfg)
    return _load_snapshot(cfg, source_id="nasdaq_100", source_type="index_constituent")


def _decode_export(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "ticker" in text.lower() or "% tna" in text.lower():
            return text
    raise CandidatePoolError("qqq: export encoding or headers are not recognized")


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _parse_weight(value: str) -> float | None:
    raw = str(value or "").replace(",", "").strip()
    if not raw or raw in {"-", "--"}:
        return None
    is_percent = "%" in raw
    try:
        number = float(raw.replace("%", ""))
    except ValueError:
        return None
    if is_percent or number > 1:
        number /= 100.0
    return number


def _source_reported_date(text: str) -> str | None:
    match = re.search(
        r"as\s+of\s+(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text, re.IGNORECASE
    )
    if not match:
        return None
    month, day_value, year = (int(value) for value in match.groups())
    return date(year, month, day_value).isoformat()


def parse_invesco_qqq_export(
    raw: bytes,
    *,
    as_of_date: str | None = None,
) -> pd.DataFrame:
    """Parse an official Invesco holdings export and verify equity coverage."""
    text = _decode_export(raw)
    reported_date = _source_reported_date(text)
    supplied_date = _normalize_date(as_of_date) if as_of_date else None
    if reported_date and supplied_date and reported_date != supplied_date:
        raise CandidatePoolError(
            f"qqq: supplied as_of_date {supplied_date} != source date {reported_date}"
        )
    effective_date = reported_date or supplied_date
    if not effective_date:
        raise CandidatePoolError(
            "qqq: export does not expose an as-of date; pass the date displayed by Invesco"
        )

    parsed_rows = list(csv.reader(io.StringIO(text)))
    header_index = None
    indices: dict[str, int] = {}
    for row_index, row in enumerate(parsed_rows):
        keys = [_header_key(cell) for cell in row]
        ticker_candidates = [i for i, key in enumerate(keys) if key == "ticker"]
        name_candidates = [
            i for i, key in enumerate(keys)
            if key in {"company", "companyname", "securityname", "name"}
        ]
        weight_candidates = [
            i for i, key in enumerate(keys)
            if key in {"tna", "weight", "weightpct", "percenttna", "percentofnetassets"}
            or key.endswith("tna")
        ]
        if ticker_candidates and name_candidates and weight_candidates:
            header_index = row_index
            indices = {
                "ticker": ticker_candidates[0],
                "name": name_candidates[0],
                "weight": weight_candidates[0],
            }
            break
    if header_index is None:
        raise CandidatePoolError("qqq: holdings header not found in official export")

    rows = []
    excluded = {"USD", "CASH", "N/A", "NA"}
    max_index = max(indices.values())
    for source_row in parsed_rows[header_index + 1:]:
        if len(source_row) <= max_index:
            continue
        ticker = str(source_row[indices["ticker"]]).upper().strip()
        name = str(source_row[indices["name"]]).strip()
        weight = _parse_weight(source_row[indices["weight"]])
        if ticker in excluded or not _valid_ticker(ticker) or not name or weight is None:
            continue
        rows.append({
            "as_of_date": effective_date,
            "source_type": "etf_holding",
            "source_id": "qqq",
            "ticker": ticker,
            "name": name,
            "weight": weight,
            "sector": "",
            "source_locator": INVESCO_QQQ_PRODUCT_URL,
        })
    frame = _normalize_snapshot(
        pd.DataFrame(rows), source_id="qqq", source_type="etf_holding"
    )
    if not MIN_QQQ_EQUITY_HOLDINGS <= len(frame) <= MAX_QQQ_EQUITY_HOLDINGS:
        raise CandidatePoolError(
            "qqq: incomplete or implausible equity holding count; "
            f"expected={MIN_QQQ_EQUITY_HOLDINGS}..{MAX_QQQ_EQUITY_HOLDINGS}, "
            f"parsed={len(frame)}"
        )
    total_weight = float(frame["weight"].sum())
    if not 0.85 <= total_weight <= 1.05:
        raise CandidatePoolError(
            f"qqq: parsed equity weight sum is implausible: {total_weight:.6f}"
        )
    return frame


def import_invesco_qqq_export(
    cfg,
    export_path: str | Path,
    *,
    as_of_date: str | None = None,
) -> tuple[pd.DataFrame, CandidatePoolMeta]:
    path = Path(export_path)
    if not path.exists():
        raise CandidatePoolError(f"qqq: export file missing: {path}")
    frame = parse_invesco_qqq_export(path.read_bytes(), as_of_date=as_of_date)
    effective_date = str(frame["as_of_date"].iloc[0])
    return _write_snapshot(
        cfg,
        frame,
        source_id="qqq",
        source_type="etf_holding",
        source="invesco_qqq_official_holdings_export",
        source_locator=INVESCO_QQQ_PRODUCT_URL,
        fetched_at=utc_now_iso(),
        completeness="validated_equity_count_and_weight_sum",
        as_of_date_evidence="source_reported_or_explicit_official_page_date",
        source_effective_date_known=True,
        extra={
            "fund_ticker": "QQQ",
            "observed_equity_holding_count": len(frame),
            "equity_weight_sum": float(frame["weight"].sum()),
            "import_file_sha256": file_sha256(path),
            "import_file_name": path.name,
            "weights_available": True,
            "sector_available": False,
            "as_of_date": effective_date,
        },
    )


def get_qqq_snapshot(cfg) -> tuple[pd.DataFrame, CandidatePoolMeta]:
    return _load_snapshot(cfg, source_id="qqq", source_type="etf_holding")


def assert_historical_backtest_allowed(manifest: dict) -> None:
    if manifest.get("historical_backtest_allowed") is not True:
        raise CandidatePoolError(
            "current NDX/QQQ snapshots cannot be used for historical backtests; "
            "a versioned point-in-time constituent event table is required"
        )


def load_candidate_taxonomy(path: str | Path | None = None) -> dict:
    target = Path(path) if path else project_root() / "config" / "candidate_taxonomy.yaml"
    if not target.exists():
        raise CandidatePoolError(f"candidate taxonomy missing: {target}")
    try:
        payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise CandidatePoolError(f"invalid candidate taxonomy: {target}") from exc
    if int(payload.get("schema_version") or 0) != 1:
        raise CandidatePoolError("candidate taxonomy schema_version must be 1")
    categories = payload.get("categories") or {}
    missing = REQUIRED_TAXONOMY_CATEGORIES - set(categories)
    if missing:
        raise CandidatePoolError(f"candidate taxonomy missing categories: {sorted(missing)}")
    securities = payload.get("securities") or {}
    for ticker, entry in securities.items():
        if not _valid_ticker(str(ticker).upper()):
            raise CandidatePoolError(f"candidate taxonomy has invalid ticker: {ticker}")
        assigned = [entry.get("primary"), *(entry.get("secondary") or [])]
        unknown = {value for value in assigned if value and value not in categories}
        if unknown:
            raise CandidatePoolError(
                f"candidate taxonomy {ticker} uses unknown categories: {sorted(unknown)}"
            )
        if not entry.get("primary") or not str(entry.get("rationale") or "").strip():
            raise CandidatePoolError(f"candidate taxonomy {ticker} lacks primary/rationale")
    payload["path"] = target.as_posix()
    payload["content_sha256"] = file_sha256(target)
    payload["version_id"] = (
        f"candidate_taxonomy:{payload.get('taxonomy_id')}:{payload['content_sha256'][:16]}"
    )
    return payload


def _raw_price_history_status(cfg, ticker: str) -> dict:
    candidates = [
        _cache_dir(cfg) / f"{ticker}.csv",
        _cache_dir(cfg) / f"{ticker.replace('.', '-')}.csv",
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        return {
            "status": "missing",
            "ready": False,
            "history_ready": False,
            "rows": 0,
            "start": None,
            "end": None,
            "cache_path": None,
            "reason": "price_cache_missing",
        }
    try:
        frame = pd.read_csv(path, usecols=lambda column: column in {"Date", "Close"})
        if set(frame.columns) != {"Date", "Close"}:
            raise ValueError("Date/Close columns missing")
        dates = pd.to_datetime(frame["Date"], errors="coerce")
        close = pd.to_numeric(frame["Close"], errors="coerce")
        valid = dates.notna() & close.notna() & (close > 0)
        rows = int(valid.sum())
        start = dates[valid].min().strftime("%Y-%m-%d") if rows else None
        end = dates[valid].max().strftime("%Y-%m-%d") if rows else None
        ready = rows >= MIN_PRICE_ROWS
        return {
            "status": "history_ready" if ready else "insufficient_history",
            "ready": ready,
            "history_ready": ready,
            "rows": rows,
            "start": start,
            "end": end,
            "cache_path": path.as_posix(),
            "reason": None if ready else f"price_rows_below_{MIN_PRICE_ROWS}",
        }
    except Exception as exc:
        return {
            "status": "invalid",
            "ready": False,
            "history_ready": False,
            "rows": 0,
            "start": None,
            "end": None,
            "cache_path": path.as_posix(),
            "reason": f"invalid_price_cache: {exc}",
        }


def _market_reference_date(cfg) -> str | None:
    ends = []
    for ticker in ("QQQ", "SPY"):
        status = _raw_price_history_status(cfg, ticker)
        if status.get("end"):
            ends.append(str(status["end"]))
    return max(ends) if ends else None


def _price_history_status(
    cfg,
    ticker: str,
    *,
    market_reference_date: str | None,
) -> dict:
    status = _raw_price_history_status(cfg, ticker)
    history_ready = bool(status.get("history_ready"))
    end = status.get("end")
    lag = None
    if end and market_reference_date:
        end_day = pd.Timestamp(end)
        reference_day = pd.Timestamp(market_reference_date)
        if end_day >= reference_day:
            lag = 0
        else:
            lag = len(pd.bdate_range(end_day + pd.offsets.BDay(1), reference_day))
    fresh = (
        history_ready
        and lag is not None
        and lag <= MAX_CURRENT_SCREEN_LAG_BUSINESS_DAYS
    )
    if history_ready and market_reference_date is None:
        reason = "market_reference_date_missing"
        display_status = "reference_missing"
    elif history_ready and not fresh:
        reason = (
            f"price_cache_lags_market_by_{lag}_business_days"
            if lag is not None else "price_freshness_unknown"
        )
        display_status = "stale"
    else:
        reason = status.get("reason")
        display_status = "ready" if fresh else status.get("status")
    status.update({
        "status": display_status,
        "ready": fresh,
        "fresh": fresh,
        "market_reference_date": market_reference_date,
        "lag_business_days": lag,
        "max_current_screen_lag_business_days": MAX_CURRENT_SCREEN_LAG_BUSINESS_DAYS,
        "reason": None if fresh else reason,
    })
    return status


def _meta_version(meta: CandidatePoolMeta | None) -> str | None:
    return meta.manifest.get("version_id") if meta else None


def build_security_candidate_registry(
    cfg,
    ndx_frame: pd.DataFrame,
    ndx_meta: CandidatePoolMeta,
    *,
    qqq_frame: pd.DataFrame | None = None,
    qqq_meta: CandidatePoolMeta | None = None,
    taxonomy: dict | None = None,
    source_errors: dict | None = None,
) -> dict:
    """Build all-NDX control and target research layers without live eligibility."""
    ndx = _normalize_snapshot(
        ndx_frame, source_id="nasdaq_100", source_type="index_constituent"
    )
    qqq = None
    if qqq_frame is not None:
        qqq = _normalize_snapshot(
            qqq_frame, source_id="qqq", source_type="etf_holding"
        )
    taxonomy = taxonomy or load_candidate_taxonomy()
    category_defs = taxonomy["categories"]
    mappings = {str(k).upper(): v for k, v in taxonomy["securities"].items()}

    ndx_rows = {str(row.ticker): row for row in ndx.itertuples(index=False)}
    qqq_rows = (
        {str(row.ticker): row for row in qqq.itertuples(index=False)} if qqq is not None else {}
    )
    incumbents = {
        str(symbol.ticker).upper(): symbol for symbol in (getattr(cfg, "symbols", []) or [])
    }
    tickers = sorted(set(ndx_rows) | set(qqq_rows) | set(incumbents))
    market_reference_date = _market_reference_date(cfg)
    observed_added = set(ndx_meta.manifest.get("observed_added") or [])
    observed_removed = set(ndx_meta.manifest.get("observed_removed") or [])
    rows = []

    for ticker in tickers:
        ndx_row = ndx_rows.get(ticker)
        qqq_row = qqq_rows.get(ticker)
        incumbent = ticker in incumbents
        mapping = mappings.get(ticker) or {}
        primary = mapping.get("primary")
        secondary = list(mapping.get("secondary") or [])
        categories = [value for value in [primary, *secondary] if value]
        target_mapped = bool(categories)
        price = _price_history_status(
            cfg, ticker, market_reference_date=market_reference_date
        )
        ndx_current = ndx_row is not None
        qqq_current = qqq_row is not None
        removed_incumbent = incumbent and ticker in observed_removed

        if removed_incumbent:
            stage = "frozen_review"
            new_capital_policy = "freeze_new_capital_pending_review"
        elif incumbent:
            stage = "incumbent"
            new_capital_policy = "current_config_unchanged"
        elif target_mapped and (ndx_current or qqq_current):
            stage = "watch"
            new_capital_policy = "research_only_no_new_capital"
        else:
            stage = "screening_pending"
            new_capital_policy = "research_only_no_new_capital"

        current_screen_blockers = []
        if not target_mapped and not incumbent:
            current_screen_blockers.append("industry_mapping_not_curated")
        if not price["ready"]:
            current_screen_blockers.append(price["reason"] or "price_history_not_ready")
        current_screen_ready = (target_mapped or incumbent) and price["ready"]

        scopes = []
        if ndx_current:
            scopes.append("all_ndx_control")
        if target_mapped or incumbent:
            scopes.append("strategy_target_pool")
        sources = []
        if ndx_current:
            sources.append("nasdaq_100_current")
        if qqq_current:
            sources.append("qqq_current")
        if incumbent:
            sources.append("current_config_incumbent")

        membership_change = "unchanged_or_first_observation"
        if ticker in observed_added:
            membership_change = "observed_added_to_ndx"
        elif ticker in observed_removed:
            membership_change = "observed_removed_from_ndx"

        qqq_weight = None
        if qqq_row is not None and pd.notna(qqq_row.weight):
            qqq_weight = float(qqq_row.weight)
        name = (
            str(ndx_row.name) if ndx_row is not None
            else str(qqq_row.name) if qqq_row is not None
            else ticker
        )
        cap_total = float(incumbents[ticker].cap_total) if incumbent else None
        rows.append({
            "ticker": ticker,
            "name": name,
            "stage": stage,
            "scopes": scopes,
            "sources": sources,
            "ndx_current": ndx_current,
            "qqq_current": qqq_current,
            "qqq_weight": qqq_weight,
            "incumbent": incumbent,
            "incumbent_cap_total": cap_total,
            "membership_change": membership_change,
            "taxonomy": {
                "primary": primary,
                "primary_label": (category_defs.get(primary) or {}).get("label") if primary else None,
                "secondary": secondary,
                "rationale": mapping.get("rationale"),
                "evidence": "curated_strategy_taxonomy_not_pure_play_classification"
                if mapping else "unclassified_no_inference",
            },
            "price_history": price,
            "liquidity": {
                "status": "index_membership_proxy_only" if ndx_current else "unverified",
                "verified": False,
                "note": "NDX membership is not a substitute for order-size and spread checks.",
            },
            "broker_tradability": {
                "venue": str(getattr(getattr(cfg, "execution", None), "venue", "HSBC")),
                "status": "configured_symbol_not_broker_verified" if incumbent else "unverified",
                "verified": False,
            },
            "current_screen": {
                "eligible": current_screen_ready,
                "blockers": current_screen_blockers,
                "allowed_use": "today_current_cross_section_only",
            },
            "historical_backtest": {
                "eligible": False,
                "blockers": [
                    "current_snapshot_only",
                    "historical_point_in_time_constituents_missing",
                ],
            },
            "live": {
                "eligible": False,
                "blockers": [
                    "historical_point_in_time_constituents_missing",
                    "hsbc_tradability_unverified",
                    "research_admission_not_run",
                    "today_diff_not_available",
                    "user_confirmation_missing",
                ],
            },
            "new_capital_policy": new_capital_policy,
            "sell_policy": "no_automatic_sell",
            "today_advice_impact": "none",
        })

    stage_counts: dict[str, int] = {}
    taxonomy_counts = {key: 0 for key in category_defs}
    for row in rows:
        stage_counts[row["stage"]] = stage_counts.get(row["stage"], 0) + 1
        primary = row["taxonomy"]["primary"]
        if primary:
            taxonomy_counts[primary] = taxonomy_counts.get(primary, 0) + 1

    component_versions = [value for value in [_meta_version(ndx_meta), _meta_version(qqq_meta)] if value]
    identity = {
        "component_versions": component_versions,
        "taxonomy_version": taxonomy["version_id"],
        "incumbents": sorted(incumbents),
        "candidate_state": [
            {
                "ticker": row["ticker"],
                "stage": row["stage"],
                "primary": row["taxonomy"]["primary"],
                "price_status": row["price_history"]["status"],
                "price_end": row["price_history"]["end"],
            }
            for row in rows
        ],
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    target_rows = [row for row in rows if "strategy_target_pool" in row["scopes"]]
    current_ready = [row for row in target_rows if row["current_screen"]["eligible"]]
    payload = {
        "schema_version": 1,
        "registry_id": f"security_candidate_registry:{digest[:16]}",
        "generated_at": utc_now_iso(),
        "research_only": True,
        "today_advice_impact": "none",
        "historical_backtest_allowed": False,
        "point_in_time_scope": CURRENT_ONLY_SCOPE,
        "summary": {
            "registry_securities": len(rows),
            "ndx_current_securities": len(ndx_rows),
            "qqq_current_equities": len(qqq_rows),
            "incumbents": len(incumbents),
            "strategy_target_pool": len(target_rows),
            "current_screen_ready": len(current_ready),
            "market_reference_date": market_reference_date,
            "max_price_lag_business_days": MAX_CURRENT_SCREEN_LAG_BUSINESS_DAYS,
            "screening_pending": stage_counts.get("screening_pending", 0),
            "historical_backtest_ready": 0,
            "live_ready": 0,
            "stage_counts": stage_counts,
            "taxonomy_counts": taxonomy_counts,
            "full_ndx_control_tickers": sorted(ndx_rows),
            "current_screen_tickers": [row["ticker"] for row in current_ready],
            "guardrail": (
                "全部当前 NDX 证券保留在对照竞争池；只有产业映射明确且价格新鲜的标的"
                "进入今日横截面筛选。当前快照仍禁止回填历史；历史竞争只允许读取独立的"
                "SEC 点时成分数据集。"
            ),
        },
        "sources": {
            "nasdaq_100": ndx_meta.to_dict(),
            "qqq": qqq_meta.to_dict() if qqq_meta else {
                "source_id": "qqq",
                "status": "missing_or_unavailable",
                "historical_backtest_allowed": False,
            },
            "taxonomy": {
                "version_id": taxonomy["version_id"],
                "path": taxonomy["path"],
                "research_only": bool(taxonomy.get("research_only", True)),
            },
        },
        "source_errors": dict(source_errors or {}),
        "candidates": rows,
    }
    return payload


def build_current_candidate_registry(cfg) -> dict:
    ndx, ndx_meta = get_nasdaq_100_snapshot(cfg)
    source_errors = {}
    qqq = None
    qqq_meta = None
    try:
        qqq, qqq_meta = get_qqq_snapshot(cfg)
    except CandidatePoolError as exc:
        source_errors["qqq"] = str(exc)
    return build_security_candidate_registry(
        cfg,
        ndx,
        ndx_meta,
        qqq_frame=qqq,
        qqq_meta=qqq_meta,
        source_errors=source_errors,
    )


def save_security_candidate_registry(cfg, payload: dict) -> dict:
    path = _registry_path(cfg)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, text)
    source_versions = [
        source.get("version_id")
        for source in (payload.get("sources") or {}).values()
        if isinstance(source, dict) and source.get("version_id")
    ]
    return write_dataset_manifest(
        path,
        dataset_type="security_candidate_registry",
        dataset_key="us_growth_current",
        source="derived_from_versioned_current_security_pools",
        source_locator=None,
        row_count=len(payload.get("candidates") or []),
        data_start=None,
        data_end=None,
        extra={
            "registry_id": payload.get("registry_id"),
            "component_versions": sorted(source_versions),
            "point_in_time_scope": CURRENT_ONLY_SCOPE,
            "historical_backtest_allowed": False,
            "research_only": True,
            "today_advice_impact": "none",
        },
    )


def refresh_candidate_price_caches(cfg, tickers: Iterable[str]) -> dict:
    """Refresh target prices through the configured provider chain.

    A provider failure may fall back to an existing cache, but the registry's
    freshness check remains authoritative and will still mark that ticker stale.
    """
    from data.fetch import get_bars

    results = {}
    errors = {}
    for ticker in sorted({str(value).upper().strip() for value in tickers if str(value).strip()}):
        try:
            _, meta = get_bars(ticker, cfg)
            results[ticker] = {
                "source": meta.source,
                "cached": bool(meta.cached),
                "rows": int(meta.rows),
                "start": meta.start,
                "end": meta.end,
                "provider_errors": dict(meta.errors),
            }
        except Exception as exc:
            errors[ticker] = str(exc)
    return {"results": results, "errors": errors}
