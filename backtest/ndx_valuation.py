"""Research-only point-in-time NDX valuation score evidence."""
from __future__ import annotations

import json

import pandas as pd

from data.ndx_fundamentals import NdxFundamentalError, fundamental_cache_dir
from data.ndx_valuation_score import (
    SUPPORTED_VALUATION_SCORE_POLICY_IDS,
    VALUATION_OVERPAY_GUARD_POLICY_ID,
    VALUATION_SCORE_POLICY_ID,
)
from data.versioning import file_sha256, manifest_path


VALUATION_POLICY_DIRECTORIES = {
    VALUATION_SCORE_POLICY_ID: "valuation_score_contract_v2",
    VALUATION_OVERPAY_GUARD_POLICY_ID: "valuation_score_overpay_guard_v1",
}


def load_valuation_score_evidence(
    cfg,
    policy_id: str = VALUATION_SCORE_POLICY_ID,
) -> tuple[pd.DataFrame, dict]:
    if policy_id not in SUPPORTED_VALUATION_SCORE_POLICY_IDS:
        raise NdxFundamentalError(f"unsupported valuation score policy: {policy_id}")
    directory = fundamental_cache_dir(cfg) / VALUATION_POLICY_DIRECTORIES[policy_id]
    root_path = directory / "manifest.json"
    if not root_path.exists():
        raise NdxFundamentalError(
            f"valuation score contract is missing: {root_path}"
        )
    root = json.loads(root_path.read_text(encoding="utf-8"))
    checks = {
        "policy_id": root.get("policy_id") == policy_id,
        "integrity_passed": bool(root.get("integrity_passed")),
        "return_data_read": root.get("return_data_read") is False,
        "training_allowed": bool(root.get("training_spec_generation_allowed")),
        "live_closed": root.get("live_scoring_allowed") is False,
    }
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise NdxFundamentalError(
            f"valuation score contract failed checks: {failed}"
        )
    evidence = (root.get("evidence_files") or {}).get("scores") or {}
    path = directory / str(evidence.get("filename") or "")
    sidecar = manifest_path(path)
    if not path.exists() or not sidecar.exists():
        raise NdxFundamentalError("valuation score evidence is missing")
    manifest = json.loads(sidecar.read_text(encoding="utf-8"))
    expected = str(evidence.get("sha256") or "")
    if file_sha256(path) != expected or manifest.get("content_sha256") != expected:
        raise NdxFundamentalError("valuation score evidence hash changed")
    frame = pd.read_csv(path, low_memory=False)
    required = {
        "selection_date",
        "ticker",
        "cik",
        "valuation_score",
        "valuation_factor_active",
        "valuation_factor_coverage",
        "valuation_missing_neutral_applied",
        "valuation_missing_neutral_score",
        "valuation_policy_id",
        "return_data_read",
        "training_spec_generation_allowed",
        "live_scoring_allowed",
    }
    missing = sorted(required - set(frame.columns))
    if missing or frame.empty:
        raise NdxFundamentalError(
            f"valuation score evidence is empty or incomplete: {missing}"
        )
    if frame.duplicated(["selection_date", "ticker"]).any():
        raise NdxFundamentalError("valuation score evidence has duplicate keys")
    scores = pd.to_numeric(frame["valuation_score"], errors="coerce")
    if scores.isna().any() or not scores.between(0, 100, inclusive="both").all():
        raise NdxFundamentalError("valuation scores escape [0, 100]")
    if not frame["valuation_policy_id"].eq(policy_id).all():
        raise NdxFundamentalError("valuation score row policy changed")
    missing_rows = frame["valuation_missing_neutral_applied"].astype(bool)
    neutral = pd.to_numeric(
        frame["valuation_missing_neutral_score"], errors="coerce"
    )
    if not scores[missing_rows].eq(neutral[missing_rows]).all():
        raise NdxFundamentalError("missing valuation rows are not exactly neutral")
    if frame["return_data_read"].astype(bool).any():
        raise NdxFundamentalError("valuation score evidence read return data")
    if not frame["training_spec_generation_allowed"].astype(bool).all():
        raise NdxFundamentalError("valuation score rows are not training-ready")
    if frame["live_scoring_allowed"].astype(bool).any():
        raise NdxFundamentalError("valuation score evidence enables live scoring")
    return frame, {
        "version_id": manifest.get("version_id"),
        "content_sha256": manifest.get("content_sha256"),
        "source": manifest.get("source"),
        "data_start": manifest.get("data_start"),
        "data_end": manifest.get("data_end"),
        "row_count": manifest.get("row_count"),
        "valuation_policy_id": policy_id,
        "manifest_path": sidecar.as_posix(),
        "cache_path": path.as_posix(),
        "future_data_guard": "valuation selection_date equals rebalance date",
        "missing_policy": "exact_neutral_cross_section_median",
        "live_scoring_allowed": False,
    }


def valuation_snapshot(
    scores: pd.DataFrame,
    asof: pd.Timestamp,
    policy_id: str = VALUATION_SCORE_POLICY_ID,
) -> pd.DataFrame:
    date_label = pd.Timestamp(asof).strftime("%Y-%m-%d")
    snapshot = scores[scores["selection_date"].astype(str).eq(date_label)].copy()
    if snapshot.empty:
        raise NdxFundamentalError(
            f"valuation score snapshot is unavailable for {date_label}"
        )
    if snapshot["valuation_policy_id"].nunique() != 1 or (
        snapshot["valuation_policy_id"].iloc[0] != policy_id
    ):
        raise NdxFundamentalError("valuation policy identity changed")
    if not snapshot["valuation_factor_active"].astype(bool).all():
        raise NdxFundamentalError("valuation factor is inactive for this date")
    return snapshot.set_index(snapshot["ticker"].astype(str).str.upper())
