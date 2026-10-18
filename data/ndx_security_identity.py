"""Versioned point-in-time security identity for NDX research.

Ticker aliases are intentionally narrow: a rule may bridge a symbol change
for the same CIK and CUSIP, but it must never bridge an acquisition, merger,
or delisting into a different security.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Mapping

import pandas as pd
import yaml


SECURITY_LIFECYCLE_SCHEMA_VERSION = 1


class NdxSecurityIdentityError(ValueError):
    """Raised when point-in-time security identity evidence is ambiguous."""


def _cik(value: object) -> str:
    raw = str(value or "").strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    if not raw.isdigit() or int(raw) <= 0:
        raise NdxSecurityIdentityError(f"invalid CIK: {value!r}")
    return f"{int(raw):010d}"


def _ticker(value: object) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol or not symbol.replace("-", "").replace(".", "").isalnum():
        raise NdxSecurityIdentityError(f"invalid ticker: {value!r}")
    return symbol


def _date(value: object, *, field: str) -> pd.Timestamp | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    parsed = pd.Timestamp(value)
    if pd.isna(parsed):
        raise NdxSecurityIdentityError(f"invalid {field}: {value!r}")
    return parsed.normalize()


@dataclass(frozen=True)
class TickerInterval:
    effective_from: pd.Timestamp | None
    effective_to: pd.Timestamp | None
    price_ticker: str

    def contains(self, value: pd.Timestamp) -> bool:
        return bool(
            (self.effective_from is None or value >= self.effective_from)
            and (self.effective_to is None or value <= self.effective_to)
        )


@dataclass(frozen=True)
class SecurityLifecycleRule:
    rule_id: str
    cik: str
    cusip: str
    issuer_name: str
    recognized_tickers: frozenset[str]
    intervals: tuple[TickerInterval, ...]
    evidence_urls: tuple[str, ...]

    def resolve(self, selection_date: pd.Timestamp) -> str:
        matches = [
            interval.price_ticker
            for interval in self.intervals
            if interval.contains(selection_date)
        ]
        if len(matches) != 1:
            raise NdxSecurityIdentityError(
                f"{self.rule_id}: expected one ticker on "
                f"{selection_date:%Y-%m-%d}, found {matches}"
            )
        return matches[0]


@dataclass(frozen=True)
class SecurityLifecycle:
    mapping_id: str
    last_reviewed: str
    rules_by_cik: Mapping[str, SecurityLifecycleRule]


def _validated_intervals(rule_id: str, rows: object) -> tuple[TickerInterval, ...]:
    if not isinstance(rows, list) or not rows:
        raise NdxSecurityIdentityError(f"{rule_id}: intervals must be nonempty")
    intervals = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise NdxSecurityIdentityError(f"{rule_id}: interval {index} is invalid")
        begin = _date(raw.get("effective_from"), field="effective_from")
        end = _date(raw.get("effective_to"), field="effective_to")
        if begin is not None and end is not None and begin > end:
            raise NdxSecurityIdentityError(
                f"{rule_id}: interval {index} begins after it ends"
            )
        intervals.append(TickerInterval(begin, end, _ticker(raw.get("price_ticker"))))
    if intervals[0].effective_from is not None:
        raise NdxSecurityIdentityError(f"{rule_id}: first interval must be open-start")
    if intervals[-1].effective_to is not None:
        raise NdxSecurityIdentityError(f"{rule_id}: last interval must be open-end")
    for previous, current in zip(intervals, intervals[1:]):
        if previous.effective_to is None or current.effective_from is None:
            raise NdxSecurityIdentityError(
                f"{rule_id}: only boundary intervals may be open-ended"
            )
        expected = previous.effective_to + timedelta(days=1)
        if current.effective_from != expected:
            raise NdxSecurityIdentityError(
                f"{rule_id}: ticker intervals contain a gap or overlap at "
                f"{current.effective_from:%Y-%m-%d}"
            )
    return tuple(intervals)


def load_security_lifecycle(path: str | Path) -> SecurityLifecycle:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)
    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise NdxSecurityIdentityError("security lifecycle root must be a mapping")
    if int(payload.get("schema_version") or 0) != SECURITY_LIFECYCLE_SCHEMA_VERSION:
        raise NdxSecurityIdentityError("unsupported security lifecycle schema_version")
    mapping_id = str(payload.get("mapping_id") or "").strip()
    if not mapping_id:
        raise NdxSecurityIdentityError("security lifecycle mapping_id is required")
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise NdxSecurityIdentityError("security lifecycle rules must be nonempty")
    rules: dict[str, SecurityLifecycleRule] = {}
    rule_ids: set[str] = set()
    for raw in raw_rules:
        if not isinstance(raw, Mapping):
            raise NdxSecurityIdentityError("security lifecycle rule is invalid")
        rule_id = str(raw.get("rule_id") or "").strip()
        if not rule_id or rule_id in rule_ids:
            raise NdxSecurityIdentityError(f"invalid or duplicate rule_id: {rule_id!r}")
        cik = _cik(raw.get("cik"))
        if cik in rules:
            raise NdxSecurityIdentityError(f"duplicate lifecycle CIK: {cik}")
        cusip = str(raw.get("cusip") or "").strip().upper()
        if len(cusip) != 9 or not cusip.isalnum():
            raise NdxSecurityIdentityError(f"{rule_id}: invalid CUSIP {cusip!r}")
        recognized = raw.get("recognized_tickers")
        if not isinstance(recognized, list) or not recognized:
            raise NdxSecurityIdentityError(
                f"{rule_id}: recognized_tickers must be nonempty"
            )
        tickers = frozenset(_ticker(value) for value in recognized)
        intervals = _validated_intervals(rule_id, raw.get("intervals"))
        interval_tickers = {item.price_ticker for item in intervals}
        if not interval_tickers.issubset(tickers):
            raise NdxSecurityIdentityError(
                f"{rule_id}: interval ticker is not recognized"
            )
        evidence = raw.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise NdxSecurityIdentityError(f"{rule_id}: official evidence is required")
        urls = []
        for item in evidence:
            if not isinstance(item, Mapping):
                raise NdxSecurityIdentityError(f"{rule_id}: evidence row is invalid")
            url = str(item.get("url") or "").strip()
            if not url.startswith("https://"):
                raise NdxSecurityIdentityError(
                    f"{rule_id}: evidence URL must use https"
                )
            _date(item.get("effective_date"), field="evidence effective_date")
            urls.append(url)
        rules[cik] = SecurityLifecycleRule(
            rule_id=rule_id,
            cik=cik,
            cusip=cusip,
            issuer_name=str(raw.get("issuer_name") or "").strip(),
            recognized_tickers=tickers,
            intervals=intervals,
            evidence_urls=tuple(urls),
        )
        rule_ids.add(rule_id)
    return SecurityLifecycle(
        mapping_id=mapping_id,
        last_reviewed=str(payload.get("last_reviewed") or ""),
        rules_by_cik=rules,
    )


def apply_security_lifecycle(
    plan: pd.DataFrame,
    lifecycle: SecurityLifecycle,
) -> pd.DataFrame:
    """Attach a strict point-in-time price ticker while preserving plan identity."""
    required = {"selection_date", "ticker", "cik"}
    if not required.issubset(plan.columns):
        raise NdxSecurityIdentityError(
            f"security plan lacks {sorted(required - set(plan.columns))}"
        )
    output = plan.copy()
    output["selection_date"] = output["selection_date"].astype(str).str[:10]
    output["ticker"] = output["ticker"].map(_ticker)
    price_tickers = []
    rule_ids = []
    statuses = []
    cusips = []
    evidence_urls = []
    aliases = []
    for row in output[["selection_date", "ticker", "cik"]].itertuples(index=False):
        selection_date = _date(row.selection_date, field="selection_date")
        cik = _cik(row.cik)
        logical_ticker = _ticker(row.ticker)
        rule = lifecycle.rules_by_cik.get(cik)
        if rule is None:
            price_ticker = logical_ticker
            rule_id = ""
            status = "not_declared_same_ticker"
            cusip = ""
            evidence_url = ""
        else:
            if logical_ticker not in rule.recognized_tickers:
                raise NdxSecurityIdentityError(
                    f"{rule.rule_id}: plan ticker {logical_ticker} is not recognized"
                )
            assert selection_date is not None
            price_ticker = rule.resolve(selection_date)
            rule_id = rule.rule_id
            status = "resolved_from_versioned_lifecycle"
            cusip = rule.cusip
            evidence_url = " | ".join(rule.evidence_urls)
        price_tickers.append(price_ticker)
        rule_ids.append(rule_id)
        statuses.append(status)
        cusips.append(cusip)
        evidence_urls.append(evidence_url)
        aliases.append(price_ticker != logical_ticker)
    output["price_ticker"] = price_tickers
    output["ticker_alias_applied"] = aliases
    output["ticker_lifecycle_rule_id"] = rule_ids
    output["ticker_lifecycle_status"] = statuses
    output["security_cusip"] = cusips
    output["ticker_lifecycle_evidence_url"] = evidence_urls
    if output.duplicated(["selection_date", "ticker"]).any():
        raise NdxSecurityIdentityError("security lifecycle output contains duplicate keys")
    return output
