"""Build the immutable original-eight research control for dynamic shadow paths."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


class NdxOriginal8ControlError(ValueError):
    """Raised when the original-eight control cannot be reproduced exactly."""


EXPECTED_TICKERS = ("NVDA", "TXN", "ASML", "CDNS", "TSM", "MU", "MSFT", "GOOG")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise NdxOriginal8ControlError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise NdxOriginal8ControlError(f"expected JSON object: {path}")
    return value


def _verify_artifact(root: Path, artifact: Mapping[str, Any], name: str) -> Path:
    raw_path = str(artifact.get("path") or "")
    expected_hash = str(artifact.get("sha256") or "")
    if not raw_path or len(expected_hash) != 64:
        raise NdxOriginal8ControlError(f"{name} artifact contract is incomplete")
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_file() or file_sha256(path) != expected_hash:
        raise NdxOriginal8ControlError(f"{name} artifact hash mismatch")
    return path


def build_original8_control(
    root: Path,
    *,
    dynamic_manifest_path: Path,
    identity_manifest_path: Path,
) -> dict[str, Any]:
    """Freeze identities and consensus weights without consulting mutable state."""
    root = root.resolve()
    dynamic_path = dynamic_manifest_path.resolve()
    identity_path = identity_manifest_path.resolve()
    dynamic = _read_json(dynamic_path)
    identity = _read_json(identity_path)

    if dynamic.get("manifest_type") != "ndx_dynamic_cardinality_historical_walkforward":
        raise NdxOriginal8ControlError("unexpected dynamic walkforward manifest type")
    coverage = dynamic.get("capital_replay_source_coverage") or {}
    if coverage.get("original_8_weight_source") != "CAPITAL_REPLAY_CHILD_MANIFEST_CONSENSUS":
        raise NdxOriginal8ControlError("original-eight weights are not child-manifest consensus")
    weights_raw = coverage.get("original_8_incumbent_weights") or {}
    if set(weights_raw) != set(EXPECTED_TICKERS):
        raise NdxOriginal8ControlError("original-eight weight ticker set changed")
    weights = {ticker: float(weights_raw[ticker]) for ticker in EXPECTED_TICKERS}
    if any(not math.isfinite(value) or value <= 0 for value in weights.values()):
        raise NdxOriginal8ControlError("original-eight weights must be finite and positive")
    if not math.isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise NdxOriginal8ControlError("original-eight weights do not sum to one")

    dynamic_identity_input = (dynamic.get("inputs") or {}).get("incumbent_identity_manifest") or {}
    if Path(str(dynamic_identity_input.get("path") or "")).resolve() != identity_path:
        raise NdxOriginal8ControlError("dynamic manifest points to a different identity manifest")
    if file_sha256(identity_path) != str(dynamic_identity_input.get("sha256") or ""):
        raise NdxOriginal8ControlError("identity manifest hash changed since walkforward")
    if identity.get("manifest_type") != "ndx_incumbent_pit_execution_attribution":
        raise NdxOriginal8ControlError("unexpected incumbent identity manifest type")
    projection_path = _verify_artifact(root, (identity.get("artifacts") or {}).get("projection") or {}, "identity projection")

    projection = pd.read_csv(projection_path, dtype=str).fillna("")
    required_columns = {"selection_date", "ticker", "security_id", "issuer_id", "risk_chain"}
    if not required_columns.issubset(projection.columns):
        raise NdxOriginal8ControlError("identity projection columns are incomplete")
    latest_date = str(projection["selection_date"].max())
    latest = projection.loc[projection["selection_date"].eq(latest_date)].copy()
    if len(latest) != len(EXPECTED_TICKERS) or set(latest["ticker"]) != set(EXPECTED_TICKERS):
        raise NdxOriginal8ControlError("latest identity projection is not the complete original eight")
    if latest[["security_id", "issuer_id"]].eq("").any().any():
        raise NdxOriginal8ControlError("original-eight identity is incomplete")
    if latest["security_id"].duplicated().any() or latest["issuer_id"].duplicated().any():
        raise NdxOriginal8ControlError("original-eight identities are not unique")

    by_ticker = latest.set_index("ticker", drop=False)
    securities = [
        {
            "ticker": ticker,
            "security_id": str(by_ticker.at[ticker, "security_id"]),
            "issuer_id": str(by_ticker.at[ticker, "issuer_id"]),
            "risk_chain": str(by_ticker.at[ticker, "risk_chain"]),
            "target_weight": weights[ticker],
        }
        for ticker in EXPECTED_TICKERS
    ]
    definition = {
        "control_id": "ndx_original_8_incumbent_v0",
        "securities": securities,
        "starting_capital_usd": 25000.0,
        "minimum_cash_buffer_usd": 100.0,
        "transaction_cost_bps": 10.0,
    }
    return {
        "schema_version": 1,
        "manifest_type": "ndx_original_8_frozen_research_control",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "FROZEN_RESEARCH_CONTROL_NOT_CURRENT_BROKER_OVERLAY",
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "broker_current_overlay_included": False,
        "definition": definition,
        "definition_sha256": canonical_sha256(definition),
        "identity_projection_date": latest_date,
        "weight_source": "CAPITAL_REPLAY_CHILD_MANIFEST_CONSENSUS",
        "source_state_sha256": coverage.get("original_8_source_state_sha256"),
        "inputs": {
            "dynamic_walkforward_manifest": {
                "path": dynamic_path.as_posix(),
                "sha256": file_sha256(dynamic_path),
            },
            "identity_manifest": {
                "path": identity_path.as_posix(),
                "sha256": file_sha256(identity_path),
            },
            "identity_projection": {
                "path": projection_path.as_posix(),
                "sha256": file_sha256(projection_path),
                "rows": int(len(projection)),
            },
        },
        "same_calendar_execution_control_required": True,
        "promotion_allowed": False,
        "live_mutation": {
            "config": False,
            "state": False,
            "broker": False,
            "today_advice": False,
            "orders": False,
        },
    }


__all__ = [
    "EXPECTED_TICKERS",
    "NdxOriginal8ControlError",
    "build_original8_control",
    "canonical_sha256",
    "file_sha256",
]
