"""Public identifier crosscheck, not an execution-identity authority.

OpenFIGI mapping is observed when queried; it supplies no historical effective
interval or SEC issuer proof.  This module never edits existing identity data.
"""
from __future__ import annotations

import hashlib
from io import StringIO
import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd


ENDPOINT = "https://api.openfigi.com/v3/mapping"


class IdentityMappingProbeError(ValueError):
    pass


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise IdentityMappingProbeError(f"mapping response contains duplicate JSON key: {key}")
        value[key] = item
    return value


def build_mapping_jobs(identity_csv_bytes: bytes, tickers: list[str]) -> tuple[list[dict], list[dict]]:
    """Read each requested historical identity from one captured byte buffer."""
    names = [value.strip().upper() for value in tickers]
    if not names or len(names) > 5 or len(set(names)) != len(names):
        raise IdentityMappingProbeError("one transport batch requires 1..5 unique tickers")
    frame = pd.read_csv(StringIO(identity_csv_bytes.decode("utf-8-sig")), dtype=str).fillna("")
    required = {"security_id", "issuer_id", "ticker", "cik", "cusip", "observation_from", "observation_to"}
    if not required.issubset(frame.columns):
        raise IdentityMappingProbeError("historical identity source schema is incomplete")
    identities = []
    for ticker in names:
        rows = frame.loc[frame["ticker"].eq(ticker)]
        if len(rows) != 1:
            raise IdentityMappingProbeError(f"historical identity is missing or ambiguous: {ticker}")
        row = {key: str(rows.iloc[0][key]) for key in sorted(required)}
        if any(not row[key] for key in ("security_id", "issuer_id", "cik", "cusip")):
            raise IdentityMappingProbeError(f"historical identity lacks identifiers: {ticker}")
        if len(row["cusip"]) != 9 or not row["cusip"].isalnum():
            raise IdentityMappingProbeError("CUSIP format is invalid")
        identities.append(row)
    if len({row["cusip"] for row in identities}) != len(identities):
        raise IdentityMappingProbeError("transport inputs contain duplicate CUSIPs")
    jobs = [{"idType": "ID_CUSIP", "idValue": row["cusip"], "exchCode": "US"} for row in identities]
    return jobs, identities


def build_mapping_observation(
    *, identity_csv_bytes: bytes, tickers: list[str], response_bytes: bytes,
    observed_at_utc: str, http_status: int,
) -> dict[str, Any]:
    jobs, identities = build_mapping_jobs(identity_csv_bytes, tickers)
    observed = datetime.fromisoformat(observed_at_utc.replace("Z", "+00:00"))
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise IdentityMappingProbeError("observation requires a timezone-aware timestamp")
    if http_status != 200:
        raise IdentityMappingProbeError(f"mapping request did not succeed: HTTP {http_status}")
    try:
        responses = json.loads(response_bytes.decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityMappingProbeError("mapping response is not UTF-8 JSON") from exc
    if not isinstance(responses, list) or len(responses) != len(jobs):
        raise IdentityMappingProbeError("mapping response does not preserve request cardinality")
    results = []
    for identity, response in zip(identities, responses, strict=True):
        if not isinstance(response, dict):
            raise IdentityMappingProbeError("mapping job response must be an object")
        matches = response.get("data")
        if "error" in response or "warning" in response:
            status = "UNRESOLVED_PROVIDER_ERROR_OR_WARNING"
        elif not isinstance(matches, list) or not matches:
            status = "UNRESOLVED_NO_MAPPING"
        elif len(matches) != 1:
            status = "UNRESOLVED_AMBIGUOUS_MAPPING"
        else:
            match = matches[0]
            if not isinstance(match, dict) or any(not isinstance(match.get(key), str) or not match[key]
                                                for key in ("ticker", "figi", "compositeFIGI", "shareClassFIGI")):
                status = "UNRESOLVED_INCOMPLETE_SHARE_CLASS_MAPPING"
            elif match.get("exchCode") != "US" or match.get("marketSector") != "Equity":
                status = "UNRESOLVED_MARKET_OR_EXCHANGE_MISMATCH"
            elif match["ticker"] != identity["ticker"]:
                status = "OBSERVED_TICKER_DIFFERS_REQUIRES_LIFECYCLE_REVIEW"
            else:
                status = "OBSERVED_CUSIP_TICKER_SHARE_CLASS_MATCH"
        results.append({
            "historical_identity": identity, "status": status,
            "provider_result": response,
            "execution_valid_on_date_proved": False,
            "automatic_alias_created": False,
        })
    provider_identifiers: dict[tuple[str, str], set[int]] = {}
    for index, result in enumerate(results):
        matches = result["provider_result"].get("data")
        if not isinstance(matches, list) or len(matches) != 1 or not isinstance(matches[0], dict):
            continue
        for field in ("figi", "compositeFIGI", "shareClassFIGI"):
            identifier = matches[0].get(field)
            if isinstance(identifier, str) and identifier:
                provider_identifiers.setdefault((field, identifier), set()).add(index)
    conflicted = set().union(*(indexes for indexes in provider_identifiers.values() if len(indexes) > 1))
    for index in conflicted:
        results[index]["status"] = "UNRESOLVED_CROSS_JOB_PROVIDER_IDENTITY_COLLISION"
    payload = {
        "schema_version": 1, "manifest_type": "ndx_public_identity_mapping_observation",
        "endpoint": ENDPOINT,
        "observed_at_utc": observed.astimezone(timezone.utc).isoformat(),
        "http_status": http_status, "request_jobs": jobs,
        "historical_identity_source_sha256": hashlib.sha256(identity_csv_bytes).hexdigest(),
        "response_bytes_sha256": hashlib.sha256(response_bytes).hexdigest(),
        "response_body_utf8": response_bytes.decode("utf-8"),
        "results": results,
        "matched_count": sum(row["status"] == "OBSERVED_CUSIP_TICKER_SHARE_CLASS_MATCH" for row in results),
        "requested_count": len(jobs),
        "observation_is_historical_effective_date": False,
        "historical_asof_mapping_claimed": False,
        "sec_issuer_crosscheck_performed": False,
        "execution_valid_on_date_proved": False,
        "admission_authority": False, "promotion_allowed": False,
        "live_mutation": False, "orders_created": False,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    payload["observation_sha256"] = hashlib.sha256(serialized).hexdigest()
    return payload


def verify_mapping_observation(observation_bytes: bytes, *, identity_csv_bytes: bytes) -> dict[str, Any]:
    """Rebuild a saved diagnostic observation, never authenticate the provider."""
    try:
        observation = json.loads(observation_bytes.decode("utf-8"), object_pairs_hook=_unique_json_object)
        if not isinstance(observation, dict):
            raise IdentityMappingProbeError("saved observation must be an object")
        tickers = [row["historical_identity"]["ticker"] for row in observation["results"]]
        rebuilt = build_mapping_observation(
            identity_csv_bytes=identity_csv_bytes, tickers=tickers,
            response_bytes=observation["response_body_utf8"].encode("utf-8"),
            observed_at_utc=observation["observed_at_utc"], http_status=observation["http_status"],
        )
    except (KeyError, TypeError, AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityMappingProbeError("saved observation schema is malformed") from exc
    if observation != rebuilt:
        raise IdentityMappingProbeError("saved observation differs from its captured inputs")
    return rebuilt
