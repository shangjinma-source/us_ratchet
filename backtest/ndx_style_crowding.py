"""Read-only style and crowding diagnostics for the incumbent-first NDX studies.

The module deliberately separates two evidence layers:

* risk-chain labels come only from reviewed, point-in-time first-party evidence;
* beta, correlation, drawdown and marginal-risk-contribution metrics use local
  prices strictly before the selected historical date.

It consumes existing v8g/v10 selection rows and never reruns a return
backtest, ranks a ticker, or promotes a candidate.  Unknown taxonomy evidence
is retained as ``unclassified`` instead of being guessed from a name, price or
recent performance.
"""
from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from core.helpers import atomic_write_text
from data.fetch import get_bars
from data.versioning import file_sha256, manifest_path, utc_now_iso, write_dataset_manifest


STYLE_SCHEMA_VERSION = 1
BENCHMARK_TICKERS = ("QQQ", "SPY", "SMH")
DEFAULT_LOOKBACK_DAYS = (126, 252, 504)
DEFAULT_MIN_OBSERVATIONS = 60
UNCLASSIFIED_CHAIN = "unclassified"

V8G_PROFILE_ROLES = {
    "pool24__q25__top12__source_top3_envelope_baseline": ("baseline", "v8g基线"),
    "pool22__without_tmus_mnst": ("frontier_return_median", "v8g收益中位前沿"),
    "pool22__without_odfl_tmus": ("frontier_return_tail", "v8g收益尾部前沿"),
    "pool22__without_odfl_orly": ("frontier_drawdown_pressure", "v8g回撤压力前沿"),
}
V10_PROFILE_ROLES = {
    "pool24__baseline__guard10": ("component_baseline_guard10", "v10基线过贵惩罚10%"),
    "pool22__without_tmus_mnst__guard10": ("component_return_median_guard10", "v10收益中位组件"),
    "pool22__without_odfl_tmus__guard10": ("component_return_tail_guard10", "v10收益尾部组件"),
    "pool22__without_odfl_orly__guard10": ("component_drawdown_guard10", "v10回撤组件"),
}

PORTFOLIO_COLUMNS = [
    "portfolio_id", "family", "profile_id", "role", "role_cn", "selection_date",
    "safe_weight", "equity_weight", "holding_count", "source_scope",
    "source_manifest_sha256", "source_selection_sha256", "taxonomy_source",
    "selection_lookback_years", "trade_cost_bps", "research_only",
]

TICKER_COLUMNS = [
    "portfolio_id", "family", "profile_id", "role", "selection_date", "ticker",
    "issuer_id", "security_id", "risk_chain", "risk_chain_label", "confidence",
    "classification_status", "classification_reason", "evidence_source",
    "evidence_available_date", "source_scope", "equity_sleeve_weight",
    "portfolio_weight", "classification_available_by_selection", "marginal_risk_pct",
]

RISK_CHAIN_COLUMNS = [
    "portfolio_id", "family", "profile_id", "role", "selection_date", "risk_chain",
    "risk_chain_label", "ticker_count", "portfolio_weight", "equity_sleeve_weight",
    "unclassified_bucket", "confidence_min", "confidence_values",
]

STYLE_COLUMNS = [
    "portfolio_id", "family", "profile_id", "role", "selection_date", "lookback_days",
    "status", "observations", "price_start", "price_end", "strict_asof_passed",
    "portfolio_vol_annualized", "portfolio_max_drawdown", "beta_qqq", "beta_spy",
    "beta_smh", "correlation_qqq", "correlation_spy", "correlation_smh",
    "qqq_minus_spy_beta_proxy", "smh_beta_cycle_proxy", "stress_window_start",
    "stress_window_end", "stress_20d_portfolio_return", "stress_20d_qqq_return",
    "stress_20d_spy_return", "stress_20d_smh_return", "style_proxy_policy",
]

RISK_CONTRIBUTION_COLUMNS = [
    "portfolio_id", "family", "profile_id", "role", "selection_date", "lookback_days",
    "status", "observations", "ticker", "risk_chain", "portfolio_weight",
    "marginal_risk_pct", "annualized_equity_volatility", "strict_asof_passed",
]

UNRESOLVED_COLUMNS = [
    "portfolio_id", "family", "profile_id", "selection_date", "issue_type", "ticker",
    "evidence_status", "details",
]


class NdxStyleCrowdingError(ValueError):
    """Raised when style/crowding inputs fail closed."""


def _json_default(value: Any):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise NdxStyleCrowdingError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise NdxStyleCrowdingError(f"JSON object required: {path}")
    return payload


def _verify_sidecar(path: Path) -> tuple[dict, str]:
    if not path.exists():
        raise NdxStyleCrowdingError(f"input file missing: {path}")
    sidecar = manifest_path(path)
    if not sidecar.exists():
        raise NdxStyleCrowdingError(f"input manifest missing: {sidecar}")
    manifest = _read_json(sidecar)
    digest = file_sha256(path)
    if manifest.get("content_sha256") != digest:
        raise NdxStyleCrowdingError(f"input content hash mismatch: {path}")
    if manifest.get("row_count") is not None:
        observed = len(pd.read_csv(path, keep_default_na=False, low_memory=False))
        if int(manifest["row_count"]) != observed:
            raise NdxStyleCrowdingError(f"input row count mismatch: {path}")
    return manifest, file_sha256(sidecar)


def _verify_lab_selection(root: Path) -> tuple[pd.DataFrame, dict, str, str]:
    manifest_path_value = root / "manifest.json"
    manifest = _read_json(manifest_path_value)
    if manifest.get("research_only") is not True or manifest.get("qqq_role") != "benchmark_only_not_candidate":
        raise NdxStyleCrowdingError(f"lab is not research-only/QQQ benchmark-only: {root}")
    if int(manifest.get("completed_jobs") or 0) != int(manifest.get("planned_jobs") or -1):
        raise NdxStyleCrowdingError(f"lab is incomplete: {root}")
    selection_path = root / "selections.csv"
    expected = (manifest.get("evidence_files") or {}).get("selections") or {}
    if not expected.get("sha256") or file_sha256(selection_path) != expected["sha256"]:
        raise NdxStyleCrowdingError(f"lab selection hash mismatch: {selection_path}")
    try:
        frame = pd.read_csv(selection_path, dtype=str, keep_default_na=False)
    except OSError as exc:
        raise NdxStyleCrowdingError(f"cannot read lab selections: {selection_path}") from exc
    required = {
        "profile_id", "selection_date", "weights", "tickers", "safe_weight",
        "lookback_years", "trade_cost_bps",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise NdxStyleCrowdingError(f"lab selection columns missing: {missing}")
    return frame, manifest, file_sha256(manifest_path_value), expected["sha256"]


def parse_weight_map(value: str | Mapping[str, float], *, reject_benchmarks: bool = True) -> dict[str, float]:
    if isinstance(value, Mapping):
        raw = {str(k).strip().upper(): float(v) for k, v in value.items()}
    else:
        raw = {}
        for item in str(value or "").split(";"):
            item = item.strip()
            if not item:
                continue
            if ":" not in item:
                raise NdxStyleCrowdingError(f"invalid serialized weight: {item!r}")
            ticker, weight = item.rsplit(":", 1)
            ticker = ticker.strip().upper()
            if not ticker or ticker in raw:
                raise NdxStyleCrowdingError(f"duplicate/blank ticker in weights: {ticker!r}")
            raw[ticker] = float(weight)
    if not raw:
        raise NdxStyleCrowdingError("empty portfolio weights")
    if reject_benchmarks and set(raw).intersection({"QQQ", "NDX", "SGOV"}):
        raise NdxStyleCrowdingError("QQQ/NDX/SGOV cannot be stock candidates in this diagnostic")
    if any(not np.isfinite(weight) or weight <= 0 for weight in raw.values()):
        raise NdxStyleCrowdingError("portfolio weights must be positive finite values")
    total = float(sum(raw.values()))
    if not np.isclose(total, 1.0, atol=1e-5):
        raise NdxStyleCrowdingError(f"stock-sleeve weights must sum to one, got {total}")
    return dict(sorted(raw.items()))


def _date_text(value: object) -> str:
    parsed = pd.Timestamp(str(value))
    if pd.isna(parsed):
        raise NdxStyleCrowdingError(f"invalid date: {value!r}")
    return parsed.strftime("%Y-%m-%d")


def _date_in(value: str, start: object, end: object) -> bool:
    return _date_text(start) <= value <= (_date_text(end) if str(end or "").strip() else "9999-12-31")


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(np.nan, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce")


def load_classification_sources(
    taxonomy_path: str | Path,
    overlay_dir: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    taxonomy_file = Path(taxonomy_path)
    taxonomy_manifest, taxonomy_manifest_sha = _verify_sidecar(taxonomy_file)
    taxonomy = pd.read_csv(taxonomy_file, dtype=str, keep_default_na=False)
    required_taxonomy = {
        "ticker", "issuer_id", "security_id", "risk_chain", "risk_chain_label",
        "selection_date_start", "selection_date_end", "evidence_available_date",
        "confidence", "status", "evidence_source",
    }
    missing = sorted(required_taxonomy - set(taxonomy.columns))
    if missing:
        raise NdxStyleCrowdingError(f"taxonomy records missing: {missing}")

    reviewed_dir = Path(overlay_dir) / "reviewed"
    reviewed_manifest_path = reviewed_dir / "manifest.json"
    reviewed_manifest = _read_json(reviewed_manifest_path)
    if reviewed_manifest.get("classification_status") != "accepted_evidence_applied":
        raise NdxStyleCrowdingError("incumbent overlay is not accepted evidence")
    overlay_file = reviewed_dir / "evidence_reviewed.csv"
    expected = (reviewed_manifest.get("artifacts") or {}).get("evidence_reviewed") or {}
    if not expected.get("sha256") or file_sha256(overlay_file) != expected["sha256"]:
        raise NdxStyleCrowdingError("incumbent overlay evidence hash mismatch")
    overlay = pd.read_csv(overlay_file, dtype=str, keep_default_na=False)
    required_overlay = {
        "ticker", "issuer_id", "security_id", "risk_chain", "evidence_available_date",
        "effective_from", "effective_to", "confidence", "status", "evidence_source",
    }
    missing = sorted(required_overlay - set(overlay.columns))
    if missing:
        raise NdxStyleCrowdingError(f"incumbent overlay evidence missing: {missing}")
    versions = {
        "taxonomy_content_sha256": file_sha256(taxonomy_file),
        "taxonomy_manifest_sha256": taxonomy_manifest_sha,
        "taxonomy_version_id": taxonomy_manifest.get("version_id"),
        "overlay_manifest_sha256": file_sha256(reviewed_manifest_path),
        "overlay_evidence_sha256": file_sha256(overlay_file),
        "overlay_decision_registry_sha256": reviewed_manifest.get("decision_registry_sha256"),
    }
    return taxonomy, overlay, versions


def resolve_risk_chain(
    ticker: str,
    selection_date: str,
    *,
    source_scope: str,
    taxonomy: pd.DataFrame,
    overlay: pd.DataFrame,
) -> dict:
    """Resolve only evidence valid at ``selection_date``.

    ``incumbent_overlay`` is intentionally only used for the current eight;
    historical candidate rows use taxonomy records and cannot inherit the
    overlay.  This prevents the current label from being backfilled into the
    historical 163-ticker universe.
    """
    ticker = str(ticker).strip().upper()
    selection_date = _date_text(selection_date)
    source = overlay if source_scope == "incumbent_overlay" else taxonomy
    if source_scope == "incumbent_overlay":
        subset = source[
            source["ticker"].astype(str).str.upper().eq(ticker)
            & source["status"].astype(str).str.lower().eq("accepted")
        ]
        subset = subset[
            subset.apply(
                lambda row: _date_in(selection_date, row["effective_from"], row["effective_to"])
                and _date_text(row["evidence_available_date"]) <= selection_date,
                axis=1,
            )
        ]
    else:
        subset = source[
            source["ticker"].astype(str).str.upper().eq(ticker)
            & source["status"].astype(str).str.lower().eq("accepted")
        ]
        subset = subset[
            subset.apply(
                lambda row: _date_in(selection_date, row["selection_date_start"], row["selection_date_end"])
                and str(row["risk_chain"]).strip().lower() != UNCLASSIFIED_CHAIN
                and bool(str(row["evidence_available_date"]).strip())
                and _date_text(row["evidence_available_date"]) <= selection_date,
                axis=1,
            )
        ]
    if subset.empty:
        return {
            "issuer_id": "", "security_id": "", "risk_chain": UNCLASSIFIED_CHAIN,
            "risk_chain_label": "未分类", "confidence": "", "status": "unclassified",
            "classification_reason": "no_accepted_evidence_at_selection_date",
            "evidence_source": "", "evidence_available_date": "",
            "classification_available_by_selection": False,
        }
    chains = sorted({str(value).strip().lower() for value in subset["risk_chain"] if str(value).strip()})
    if len(chains) != 1:
        return {
            "issuer_id": "", "security_id": "", "risk_chain": UNCLASSIFIED_CHAIN,
            "risk_chain_label": "未分类", "confidence": "", "status": "conflict",
            "classification_reason": "multiple_accepted_risk_chains_at_selection_date",
            "evidence_source": "", "evidence_available_date": "",
            "classification_available_by_selection": False,
        }
    row = subset.iloc[0]
    return {
        "issuer_id": str(row.get("issuer_id") or ""),
        "security_id": str(row.get("security_id") or ""),
        "risk_chain": chains[0],
        "risk_chain_label": str(row.get("risk_chain_label") or chains[0]),
        "confidence": str(row.get("confidence") or ""),
        "status": str(row.get("status") or "accepted"),
        "classification_reason": "accepted_point_in_time_first_party_evidence",
        "evidence_source": str(row.get("evidence_source") or ""),
        "evidence_available_date": str(row.get("evidence_available_date") or ""),
        "classification_available_by_selection": True,
    }


def _select_latest_row(
    frame: pd.DataFrame,
    profile_id: str,
    *,
    lookback_years: float,
    trade_cost_bps: float,
    valuation_weight: float | None = None,
) -> pd.Series:
    subset = frame[frame["profile_id"].eq(profile_id)].copy()
    subset = subset[np.isclose(_numeric(subset, "lookback_years"), lookback_years)]
    subset = subset[np.isclose(_numeric(subset, "trade_cost_bps"), trade_cost_bps)]
    if valuation_weight is not None:
        if "valuation_score_weight" not in subset:
            raise NdxStyleCrowdingError("v10 selections lack valuation_score_weight")
        subset = subset[np.isclose(_numeric(subset, "valuation_score_weight"), valuation_weight)]
    if subset.empty:
        raise NdxStyleCrowdingError(
            f"no selection row for profile={profile_id}, lookback={lookback_years}, cost={trade_cost_bps}, value={valuation_weight}"
        )
    subset["_date"] = pd.to_datetime(subset["selection_date"], errors="coerce")
    if subset["_date"].isna().any():
        raise NdxStyleCrowdingError(f"invalid selection date for profile={profile_id}")
    latest_date = subset["_date"].max()
    latest = subset[subset["_date"].eq(latest_date)]
    if latest[["tickers", "weights"]].drop_duplicates().shape[0] != 1:
        raise NdxStyleCrowdingError(f"ambiguous latest selection state for profile={profile_id}")
    return latest.iloc[0]


def _portfolio_from_selection(
    row: pd.Series,
    *,
    portfolio_id: str,
    family: str,
    role: str,
    role_cn: str,
    manifest_sha256: str,
    selection_sha256: str,
) -> dict:
    weights = parse_weight_map(row["weights"])
    safe_weight = float(row["safe_weight"])
    if not np.isfinite(safe_weight) or not 0 <= safe_weight < 1:
        raise NdxStyleCrowdingError(f"invalid safe_weight for {portfolio_id}")
    return {
        "portfolio_id": portfolio_id,
        "family": family,
        "profile_id": str(row["profile_id"]),
        "role": role,
        "role_cn": role_cn,
        "selection_date": _date_text(row["selection_date"]),
        "safe_weight": safe_weight,
        "equity_weight": 1.0 - safe_weight,
        "holding_count": len(weights),
        "source_scope": "historical_taxonomy",
        "source_manifest_sha256": manifest_sha256,
        "source_selection_sha256": selection_sha256,
        "taxonomy_source": "taxonomy_records_only_no_incumbent_overlay_backfill",
        "selection_lookback_years": float(row["lookback_years"]),
        "trade_cost_bps": float(row["trade_cost_bps"]),
        "research_only": True,
        "weights": weights,
    }


def build_portfolios(
    cfg,
    v8g_dir: str | Path,
    v10_dir: str | Path,
    *,
    lookback_years: float = 3.0,
    trade_cost_bps: float = 10.0,
) -> tuple[list[dict], dict]:
    v8g_frame, v8g_manifest, v8g_manifest_sha, v8g_selection_sha = _verify_lab_selection(Path(v8g_dir))
    v10_frame, v10_manifest, v10_manifest_sha, v10_selection_sha = _verify_lab_selection(Path(v10_dir))
    portfolios: list[dict] = []
    for profile_id, (role, role_cn) in V8G_PROFILE_ROLES.items():
        row = _select_latest_row(
            v8g_frame, profile_id, lookback_years=lookback_years, trade_cost_bps=trade_cost_bps
        )
        portfolios.append(_portfolio_from_selection(
            row, portfolio_id=f"v8g:{profile_id}", family="v8g",
            role=role, role_cn=role_cn, manifest_sha256=v8g_manifest_sha,
            selection_sha256=v8g_selection_sha,
        ))
    for profile_id, (role, role_cn) in V10_PROFILE_ROLES.items():
        row = _select_latest_row(
            v10_frame, profile_id, lookback_years=lookback_years,
            trade_cost_bps=trade_cost_bps, valuation_weight=0.10,
        )
        portfolios.append(_portfolio_from_selection(
            row, portfolio_id=f"v10:{profile_id}", family="v10",
            role=role, role_cn=role_cn, manifest_sha256=v10_manifest_sha,
            selection_sha256=v10_selection_sha,
        ))

    cap = {str(item.ticker).upper(): float(item.cap_total) for item in cfg.symbols}
    if not cap or any(not np.isfinite(value) or value <= 0 for value in cap.values()):
        raise NdxStyleCrowdingError("current config cap_total is invalid")
    total = sum(cap.values())
    safe_weight = float(cfg.safe_leg.target_weight) if cfg.safe_leg else 0.0
    current_date = max(item["selection_date"] for item in portfolios)
    portfolios.insert(0, {
        "portfolio_id": "incumbent:current_eight",
        "family": "incumbent",
        "profile_id": "current_eight",
        "role": "incumbent",
        "role_cn": "当前8只",
        "selection_date": current_date,
        "safe_weight": safe_weight,
        "equity_weight": 1.0 - safe_weight,
        "holding_count": len(cap),
        "source_scope": "incumbent_overlay",
        "source_manifest_sha256": "",
        "source_selection_sha256": file_sha256(Path("config/config.yaml")),
        "taxonomy_source": "accepted_incumbent_overlay_only",
        "selection_lookback_years": "",
        "trade_cost_bps": "",
        "research_only": True,
        "weights": {ticker: value / total for ticker, value in sorted(cap.items())},
    })
    meta = {
        "v8g_manifest_sha256": v8g_manifest_sha,
        "v8g_selection_sha256": v8g_selection_sha,
        "v8g_experiment_id": v8g_manifest.get("experiment_id"),
        "v10_manifest_sha256": v10_manifest_sha,
        "v10_selection_sha256": v10_selection_sha,
        "v10_experiment_id": v10_manifest.get("experiment_id"),
        "lookback_years": lookback_years,
        "trade_cost_bps": trade_cost_bps,
        "selection_date": current_date,
    }
    return portfolios, meta


def _ticker_rows(
    portfolio: dict,
    *,
    taxonomy: pd.DataFrame,
    overlay: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for ticker, sleeve_weight in portfolio["weights"].items():
        classification = resolve_risk_chain(
            ticker, portfolio["selection_date"], source_scope=portfolio["source_scope"],
            taxonomy=taxonomy, overlay=overlay,
        )
        rows.append({
            "portfolio_id": portfolio["portfolio_id"],
            "family": portfolio["family"],
            "profile_id": portfolio["profile_id"],
            "role": portfolio["role"],
            "selection_date": portfolio["selection_date"],
            "ticker": ticker,
            **classification,
            "source_scope": portfolio["source_scope"],
            "equity_sleeve_weight": float(sleeve_weight),
            "portfolio_weight": float(sleeve_weight * portfolio["equity_weight"]),
            "marginal_risk_pct": np.nan,
        })
    return pd.DataFrame(rows, columns=TICKER_COLUMNS)


def _effective_n(weights: Iterable[float]) -> float | None:
    values = np.asarray([float(value) for value in weights if np.isfinite(float(value)) and float(value) > 0])
    total = float(values.sum()) if len(values) else 0.0
    if total <= 0:
        return None
    shares = values / total
    return float(1.0 / np.sum(shares * shares))


def _top_chain_text(group: pd.DataFrame, count: int) -> str:
    totals = group.groupby("risk_chain", dropna=False)["portfolio_weight"].sum().sort_values(ascending=False)
    return ";".join(f"{key}:{float(value):.6f}" for key, value in totals.head(count).items())


def build_risk_chain_exposure(portfolio: dict, ticker_rows: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    if ticker_rows.empty:
        raise NdxStyleCrowdingError(f"empty ticker rows for {portfolio['portfolio_id']}")
    equity_total = float(ticker_rows["portfolio_weight"].sum())
    if not np.isclose(equity_total, portfolio["equity_weight"], atol=1e-5):
        raise NdxStyleCrowdingError(f"portfolio weight sum mismatch: {portfolio['portfolio_id']}")
    grouped = ticker_rows.groupby("risk_chain", dropna=False, sort=True)
    exposure_rows = []
    for chain, group in grouped:
        chain = str(chain or UNCLASSIFIED_CHAIN)
        weight = float(group["portfolio_weight"].sum())
        confidence_values = sorted({str(value) for value in group["confidence"] if str(value).strip()})
        confidence_min = "low" if "low" in confidence_values else ("medium" if "medium" in confidence_values else ("high" if confidence_values else ""))
        exposure_rows.append({
            "portfolio_id": portfolio["portfolio_id"],
            "family": portfolio["family"],
            "profile_id": portfolio["profile_id"],
            "role": portfolio["role"],
            "selection_date": portfolio["selection_date"],
            "risk_chain": chain,
            "risk_chain_label": str(group["risk_chain_label"].iloc[0] or chain),
            "ticker_count": len(group),
            "portfolio_weight": weight,
            "equity_sleeve_weight": weight / equity_total if equity_total else np.nan,
            "unclassified_bucket": chain == UNCLASSIFIED_CHAIN,
            "confidence_min": confidence_min,
            "confidence_values": ";".join(confidence_values),
        })
    exposure = pd.DataFrame(exposure_rows, columns=RISK_CHAIN_COLUMNS)
    classified = ticker_rows[ticker_rows["risk_chain"].ne(UNCLASSIFIED_CHAIN)]
    unknown = ticker_rows[ticker_rows["risk_chain"].eq(UNCLASSIFIED_CHAIN)]
    chain_values = exposure["portfolio_weight"].tolist()
    known_chain_values = classified.groupby("risk_chain")["portfolio_weight"].sum().tolist()
    issuer_bucket = ticker_rows["issuer_id"].where(ticker_rows["issuer_id"].astype(str).str.strip().ne(""), "issuer:unresolved")
    issuer_values = ticker_rows.assign(_issuer=issuer_bucket).groupby("_issuer")["portfolio_weight"].sum().tolist()
    summary = {
        "risk_chain_count": int(len(exposure)),
        "risk_chain_top1": str(exposure.sort_values("portfolio_weight", ascending=False).iloc[0]["risk_chain"]),
        "risk_chain_top1_weight": float(exposure["portfolio_weight"].max()),
        "risk_chain_top3_weight": float(exposure.nlargest(3, "portfolio_weight")["portfolio_weight"].sum()),
        "risk_chain_top1_all_text": _top_chain_text(ticker_rows, 1),
        "risk_chain_top3_all_text": _top_chain_text(ticker_rows, 3),
        "risk_chain_effective_n_all": _effective_n(chain_values),
        "risk_chain_effective_n_classified": _effective_n(known_chain_values),
        "classified_ticker_count": int(len(classified)),
        "unclassified_ticker_count": int(len(unknown)),
        "classified_weight": float(classified["portfolio_weight"].sum()),
        "unclassified_weight": float(unknown["portfolio_weight"].sum()),
        "unclassified_weight_pct_equity": float(unknown["portfolio_weight"].sum() / equity_total) if equity_total else None,
        "issuer_effective_n_conservative": _effective_n(issuer_values),
        "issuer_top1_weight_conservative": float(max(issuer_values)) if issuer_values else None,
        "issuer_unresolved_weight": float(unknown["portfolio_weight"].sum()) if unknown["issuer_id"].astype(str).str.strip().eq("").any() else 0.0,
    }
    return summary, exposure


def _empty_style_row(portfolio: dict, lookback_days: int, status: str, details: str = "") -> dict:
    return {
        "portfolio_id": portfolio["portfolio_id"], "family": portfolio["family"],
        "profile_id": portfolio["profile_id"], "role": portfolio["role"],
        "selection_date": portfolio["selection_date"], "lookback_days": int(lookback_days),
        "status": status, "observations": 0, "price_start": "", "price_end": "",
        "strict_asof_passed": False, "portfolio_vol_annualized": np.nan,
        "portfolio_max_drawdown": np.nan, "beta_qqq": np.nan, "beta_spy": np.nan,
        "beta_smh": np.nan, "correlation_qqq": np.nan, "correlation_spy": np.nan,
        "correlation_smh": np.nan, "qqq_minus_spy_beta_proxy": np.nan,
        "smh_beta_cycle_proxy": np.nan, "stress_window_start": "",
        "stress_window_end": "", "stress_20d_portfolio_return": np.nan,
        "stress_20d_qqq_return": np.nan, "stress_20d_spy_return": np.nan,
        "stress_20d_smh_return": np.nan,
        "style_proxy_policy": details or "QQQ-SPY beta spread and SMH beta are proxies only; no market-cap/style label inferred.",
    }


def style_metrics_before(
    close: pd.DataFrame,
    portfolio: dict,
    *,
    lookback_days: Iterable[int] = DEFAULT_LOOKBACK_DAYS,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
) -> pd.DataFrame:
    names = list(portfolio["weights"]) + list(BENCHMARK_TICKERS)
    missing = sorted(set(names) - set(close.columns))
    rows = []
    for days in sorted({int(value) for value in lookback_days}):
        if missing:
            rows.append(_empty_style_row(portfolio, days, "missing_price_series", f"missing={','.join(missing)}"))
            continue
        asof = pd.Timestamp(portfolio["selection_date"])
        prices = close.loc[close.index < asof, names].sort_index().ffill().dropna(how="any")
        prices = prices.tail(days + 1)
        returns = prices.pct_change(fill_method=None).dropna(how="any")
        if len(returns) < int(min_observations):
            rows.append(_empty_style_row(portfolio, days, "insufficient_observations", f"observations={len(returns)}"))
            continue
        weights = pd.Series(portfolio["weights"], dtype=float)
        weight_tickers = list(weights.index)
        portfolio_returns = returns[weight_tickers].mul(weights, axis=1).sum(axis=1)
        values = (1.0 + portfolio_returns).cumprod()
        drawdown = values / values.cummax() - 1.0
        stress_window = (1.0 + portfolio_returns).rolling(min(20, len(portfolio_returns))).apply(np.prod, raw=True) - 1.0
        stress_end = stress_window.idxmin()
        stress_end_pos = returns.index.get_loc(stress_end)
        stress_start_pos = max(0, stress_end_pos - min(19, len(returns) - 1))
        stress_start = returns.index[stress_start_pos]
        stress = returns.iloc[stress_start_pos:stress_end_pos + 1]
        row = _empty_style_row(portfolio, days, "ok")
        row.update({
            "observations": int(len(returns)),
            "price_start": prices.index[0].strftime("%Y-%m-%d"),
            "price_end": prices.index[-1].strftime("%Y-%m-%d"),
            "strict_asof_passed": bool(prices.index[-1] < asof),
            "portfolio_vol_annualized": float(portfolio_returns.std(ddof=1) * math.sqrt(252)),
            "portfolio_max_drawdown": float(drawdown.min()),
            "stress_window_start": stress_start.strftime("%Y-%m-%d"),
            "stress_window_end": stress_end.strftime("%Y-%m-%d"),
            "stress_20d_portfolio_return": float((1.0 + stress[weight_tickers].mul(weights, axis=1).sum(axis=1)).prod() - 1.0),
            "stress_20d_qqq_return": float((1.0 + stress["QQQ"]).prod() - 1.0),
            "stress_20d_spy_return": float((1.0 + stress["SPY"]).prod() - 1.0),
            "stress_20d_smh_return": float((1.0 + stress["SMH"]).prod() - 1.0),
        })
        for benchmark in BENCHMARK_TICKERS:
            benchmark_returns = returns[benchmark]
            variance = float(benchmark_returns.var(ddof=1))
            covariance = float(np.cov(portfolio_returns, benchmark_returns, ddof=1)[0, 1])
            beta = covariance / variance if variance > 0 else np.nan
            row[f"beta_{benchmark.lower()}"] = beta
            row[f"correlation_{benchmark.lower()}"] = float(portfolio_returns.corr(benchmark_returns))
        row["qqq_minus_spy_beta_proxy"] = row["beta_qqq"] - row["beta_spy"]
        row["smh_beta_cycle_proxy"] = row["beta_smh"]
        rows.append(row)
    return pd.DataFrame(rows, columns=STYLE_COLUMNS)


def marginal_risk_contributions(
    close: pd.DataFrame,
    portfolio: dict,
    *,
    lookback_days: int = 252,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
) -> pd.DataFrame:
    tickers = list(portfolio["weights"])
    missing = sorted(set(tickers) - set(close.columns))
    base = {
        "portfolio_id": portfolio["portfolio_id"], "family": portfolio["family"],
        "profile_id": portfolio["profile_id"], "role": portfolio["role"],
        "selection_date": portfolio["selection_date"], "lookback_days": int(lookback_days),
    }
    if missing:
        return pd.DataFrame([{**base, "status": "missing_price_series", "observations": 0,
                              "ticker": ticker, "risk_chain": UNCLASSIFIED_CHAIN,
                              "portfolio_weight": portfolio["weights"][ticker],
                              "marginal_risk_pct": np.nan, "annualized_equity_volatility": np.nan,
                              "strict_asof_passed": False} for ticker in tickers], columns=RISK_CONTRIBUTION_COLUMNS)
    asof = pd.Timestamp(portfolio["selection_date"])
    prices = close.loc[close.index < asof, tickers].sort_index().ffill().dropna(how="any").tail(lookback_days + 1)
    returns = prices.pct_change(fill_method=None).dropna(how="any")
    if len(returns) < int(min_observations):
        return pd.DataFrame([{**base, "status": "insufficient_observations", "observations": len(returns),
                              "ticker": ticker, "risk_chain": UNCLASSIFIED_CHAIN,
                              "portfolio_weight": portfolio["weights"][ticker],
                              "marginal_risk_pct": np.nan, "annualized_equity_volatility": np.nan,
                              "strict_asof_passed": False} for ticker in tickers], columns=RISK_CONTRIBUTION_COLUMNS)
    weight_vector = np.asarray([portfolio["weights"][ticker] for ticker in tickers], dtype=float)
    covariance = np.atleast_2d(np.cov(returns.to_numpy(dtype=float), rowvar=False, ddof=1))
    variance = float(weight_vector @ covariance @ weight_vector)
    if not np.isfinite(variance) or variance <= 0:
        raise NdxStyleCrowdingError(f"non-positive portfolio variance: {portfolio['portfolio_id']}")
    contribution = weight_vector * (covariance @ weight_vector) / variance
    annualized_volatility = float(math.sqrt(variance * 252.0))
    return pd.DataFrame([
        {**base, "status": "ok", "observations": len(returns), "ticker": ticker,
         "risk_chain": "", "portfolio_weight": float(weight_vector[index]),
         "marginal_risk_pct": float(contribution[index]),
         "annualized_equity_volatility": annualized_volatility,
         "strict_asof_passed": bool(prices.index[-1] < asof)}
        for index, ticker in enumerate(tickers)
    ], columns=RISK_CONTRIBUTION_COLUMNS)


def _load_local_close(cfg, tickers: Iterable[str]) -> tuple[pd.DataFrame, dict[str, dict], dict[str, str]]:
    local_cfg = copy.deepcopy(cfg)
    local_cfg.data.fallback_chain = ["local_cache"]
    series = {}
    metadata = {}
    errors = {}
    for ticker in sorted({str(value).upper().strip() for value in tickers if str(value).strip()}):
        try:
            frame, meta = get_bars(ticker, local_cfg)
            series[ticker] = frame["Close"].astype(float)
            metadata[ticker] = {"source": meta.source, "rows": meta.rows, "start": meta.start, "end": meta.end}
        except Exception as exc:  # fail closed per ticker; summary reports the gap
            errors[ticker] = str(exc)
    close = pd.concat(series, axis=1).sort_index() if series else pd.DataFrame()
    return close, metadata, errors


def run_style_crowding_diagnostic(
    cfg,
    *,
    v8g_dir: str | Path,
    v10_dir: str | Path,
    taxonomy_path: str | Path,
    overlay_dir: str | Path,
    lookback_days: Iterable[int] = DEFAULT_LOOKBACK_DAYS,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    lookback_years: float = 3.0,
    trade_cost_bps: float = 10.0,
) -> tuple[dict[str, pd.DataFrame], dict]:
    portfolios, portfolio_meta = build_portfolios(
        cfg, v8g_dir, v10_dir, lookback_years=lookback_years, trade_cost_bps=trade_cost_bps
    )
    taxonomy, overlay, classification_versions = load_classification_sources(taxonomy_path, overlay_dir)
    ticker_frames = []
    chain_frames = []
    summary_rows = []
    unresolved_rows = []
    for portfolio in portfolios:
        ticker_frame = _ticker_rows(portfolio, taxonomy=taxonomy, overlay=overlay)
        risk_summary, chain_frame = build_risk_chain_exposure(portfolio, ticker_frame)
        ticker_frames.append(ticker_frame)
        chain_frames.append(chain_frame)
        summary_rows.append({
            **{key: portfolio[key] for key in PORTFOLIO_COLUMNS},
            **risk_summary,
        })
        for row in ticker_frame[ticker_frame["classification_available_by_selection"].astype(str).str.lower().ne("true")].to_dict("records"):
            unresolved_rows.append({
                "portfolio_id": portfolio["portfolio_id"], "family": portfolio["family"],
                "profile_id": portfolio["profile_id"], "selection_date": portfolio["selection_date"],
                "issue_type": "risk_chain_unclassified_or_conflict", "ticker": row["ticker"],
                "evidence_status": row["classification_status"],
                "details": row["classification_reason"],
            })

    all_tickers = sorted(set(BENCHMARK_TICKERS).union(*(portfolio["weights"] for portfolio in portfolios)))
    close, price_metadata, price_errors = _load_local_close(cfg, all_tickers)
    for ticker, error in sorted(price_errors.items()):
        unresolved_rows.append({
            "portfolio_id": "", "family": "", "profile_id": "", "selection_date": "",
            "issue_type": "price_series_unavailable", "ticker": ticker,
            "evidence_status": "unresolved", "details": error,
        })

    style_frames = []
    risk_frames = []
    for portfolio, ticker_frame in zip(portfolios, ticker_frames):
        style_frames.append(style_metrics_before(
            close, portfolio, lookback_days=lookback_days, min_observations=min_observations
        ))
        risk_frame = marginal_risk_contributions(
            close, portfolio, lookback_days=252, min_observations=min_observations
        )
        chain_map = ticker_frame.set_index("ticker")["risk_chain"].to_dict()
        if not risk_frame.empty:
            risk_frame["risk_chain"] = risk_frame["ticker"].map(chain_map).fillna(UNCLASSIFIED_CHAIN)
        risk_frames.append(risk_frame)

    ticker_exposure = pd.concat(ticker_frames, ignore_index=True) if ticker_frames else pd.DataFrame(columns=TICKER_COLUMNS)
    risk_chain_exposure = pd.concat(chain_frames, ignore_index=True) if chain_frames else pd.DataFrame(columns=RISK_CHAIN_COLUMNS)
    style_metrics = pd.concat(style_frames, ignore_index=True) if style_frames else pd.DataFrame(columns=STYLE_COLUMNS)
    risk_contributions = pd.concat(risk_frames, ignore_index=True) if risk_frames else pd.DataFrame(columns=RISK_CONTRIBUTION_COLUMNS)
    style_252 = style_metrics[style_metrics["lookback_days"].eq(252)].copy()
    style_252 = style_252.set_index("portfolio_id") if not style_252.empty else pd.DataFrame()
    summaries = []
    for row in summary_rows:
        style_row = style_252.loc[row["portfolio_id"]].to_dict() if not style_252.empty and row["portfolio_id"] in style_252.index else {}
        for key in ["status", "observations", "price_start", "price_end", "strict_asof_passed",
                    "portfolio_vol_annualized", "portfolio_max_drawdown", "beta_qqq", "beta_spy",
                    "beta_smh", "correlation_qqq", "correlation_spy", "correlation_smh",
                    "qqq_minus_spy_beta_proxy", "smh_beta_cycle_proxy", "stress_window_start",
                    "stress_window_end", "stress_20d_portfolio_return", "stress_20d_qqq_return",
                    "stress_20d_spy_return", "stress_20d_smh_return"]:
            row[f"style_252_{key}"] = style_row.get(key, np.nan)
        summaries.append(row)
    portfolio_summary = pd.DataFrame(summaries)
    coverage = pd.DataFrame([
        {"metric": "portfolio_count", "value": len(portfolios)},
        {"metric": "ticker_count_unique", "value": len(set().union(*(portfolio["weights"] for portfolio in portfolios)))},
        {"metric": "taxonomy_classified_ticker_rows", "value": int((ticker_exposure["classification_available_by_selection"].astype(str).str.lower() == "true").sum())},
        {"metric": "taxonomy_unclassified_or_conflict_rows", "value": int((ticker_exposure["classification_available_by_selection"].astype(str).str.lower() != "true").sum())},
        {"metric": "price_series_available_count", "value": len(price_metadata)},
        {"metric": "price_series_error_count", "value": len(price_errors)},
        {"metric": "style_252_ok_count", "value": int((style_metrics["lookback_days"].eq(252) & style_metrics["status"].eq("ok")).sum())},
        {"metric": "risk_contribution_ok_portfolios", "value": int((risk_contributions.groupby("portfolio_id")["status"].first() == "ok").sum()) if not risk_contributions.empty else 0},
        {"metric": "return_data_read_for_style_only", "value": True},
        {"metric": "classification_return_data_used", "value": False},
        {"metric": "backtest_return_results_used", "value": False},
        {"metric": "fresh_oos", "value": False},
        {"metric": "promotion_allowed", "value": False},
    ])
    unresolved = pd.DataFrame(unresolved_rows, columns=UNRESOLVED_COLUMNS)
    frames = {
        "portfolio_summary": portfolio_summary,
        "risk_chain_exposure": risk_chain_exposure,
        "ticker_exposure": ticker_exposure,
        "style_metrics": style_metrics,
        "risk_contributions": risk_contributions,
        "coverage": coverage,
        "unresolved": unresolved,
    }
    summary = {
        "schema_version": STYLE_SCHEMA_VERSION,
        "dataset_type": "ndx_style_crowding_diagnostic",
        "dataset_key": "ndx_incumbent_v8g_v10_style_crowding_v1",
        "research_only": True,
        "historical_diagnostic_only": True,
        "fresh_oos": False,
        "promotion_allowed": False,
        "qqq_is_candidate": False,
        "source_selection_rows_used": True,
        "backtest_return_results_used": False,
        "return_data_read": True,
        "classification_return_data_used": False,
        "price_data_used": True,
        "price_source_policy": "local_cache_only",
        "asof_rule": "price_date < selection_date",
        "risk_chain_policy": "historical candidates use taxonomy records only; current eight uses accepted incumbent overlay; no historical backfill",
        "style_proxy_policy": "QQQ-SPY beta spread is a growth/large-platform proxy only; SMH beta is a semiconductor-cycle proxy only; no market-cap label is inferred",
        "portfolio_count": len(portfolios),
        "portfolio_meta": portfolio_meta,
        "classification_versions": classification_versions,
        "price_series_metadata": price_metadata,
        "price_series_errors": price_errors,
        "lookback_days": sorted({int(value) for value in lookback_days}),
        "min_observations": int(min_observations),
        "unresolved_issue_count": len(unresolved),
    }
    return frames, summary


def plan_style_crowding_diagnostic(
    cfg,
    *,
    v8g_dir: str | Path,
    v10_dir: str | Path,
    taxonomy_path: str | Path,
    overlay_dir: str | Path,
    lookback_years: float = 3.0,
    trade_cost_bps: float = 10.0,
) -> dict:
    portfolios, meta = build_portfolios(
        cfg, v8g_dir, v10_dir, lookback_years=lookback_years, trade_cost_bps=trade_cost_bps
    )
    _, _, versions = load_classification_sources(taxonomy_path, overlay_dir)
    return {
        "schema_version": STYLE_SCHEMA_VERSION,
        "portfolio_count": len(portfolios),
        "portfolio_ids": [item["portfolio_id"] for item in portfolios],
        "selection_date": meta["selection_date"],
        "lookback_years": lookback_years,
        "trade_cost_bps": trade_cost_bps,
        "classification_versions": versions,
        "price_data_read": False,
        "backtest_return_results_used": False,
        "promotion_allowed": False,
    }


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


TRANSLATIONS = {
    "portfolio_id": "组合编号", "family": "研究家族", "profile_id": "配置编号", "role": "角色",
    "role_cn": "角色中文", "selection_date": "选择日期", "safe_weight": "安全仓权重",
    "equity_weight": "股票风险仓权重", "holding_count": "持仓数量", "source_scope": "分类证据范围",
    "source_manifest_sha256": "来源manifest哈希", "source_selection_sha256": "选择文件哈希",
    "taxonomy_source": "taxonomy来源规则", "selection_lookback_years": "选择回看年数",
    "trade_cost_bps": "交易成本bp", "research_only": "仅研究", "ticker": "股票代码",
    "issuer_id": "发行人编号", "security_id": "证券编号", "risk_chain": "风险链编号",
    "risk_chain_label": "风险链", "confidence": "置信度", "classification_status": "分类状态",
    "classification_reason": "分类原因", "evidence_source": "证据来源",
    "evidence_available_date": "证据可用日", "equity_sleeve_weight": "股票袖套权重",
    "portfolio_weight": "组合总权重", "classification_available_by_selection": "选择日分类可用",
    "marginal_risk_pct": "边际风险贡献", "ticker_count": "股票数量", "unclassified_bucket": "未分类桶",
    "confidence_min": "最低置信度", "confidence_values": "置信度集合", "risk_chain_count": "风险链数量",
    "risk_chain_top1": "风险链Top1", "risk_chain_top1_weight": "风险链Top1权重",
    "risk_chain_top3_weight": "风险链Top3权重", "risk_chain_top1_all_text": "风险链Top1明细",
    "risk_chain_top3_all_text": "风险链Top3明细", "risk_chain_effective_n_all": "风险链有效N含未分类",
    "risk_chain_effective_n_classified": "风险链有效N已分类", "classified_ticker_count": "已分类股票数",
    "unclassified_ticker_count": "未分类股票数", "classified_weight": "已分类组合权重",
    "unclassified_weight": "未分类组合权重", "unclassified_weight_pct_equity": "未分类股票袖套占比",
    "issuer_effective_n_conservative": "发行人有效N保守口径", "issuer_top1_weight_conservative": "发行人Top1保守权重",
    "issuer_unresolved_weight": "发行人未解析权重", "lookback_days": "价格回看天数", "status": "状态",
    "observations": "观测数", "price_start": "价格起日", "price_end": "价格止日",
    "strict_asof_passed": "严格点时通过", "portfolio_vol_annualized": "组合年化波动",
    "portfolio_max_drawdown": "组合最大回撤", "beta_qqq": "QQQ Beta", "beta_spy": "SPY Beta",
    "beta_smh": "SMH Beta", "correlation_qqq": "QQQ相关性", "correlation_spy": "SPY相关性",
    "correlation_smh": "SMH相关性", "qqq_minus_spy_beta_proxy": "QQQ-SPY Beta差代理",
    "smh_beta_cycle_proxy": "SMH周期Beta代理", "stress_window_start": "压力窗口起日",
    "stress_window_end": "压力窗口止日", "stress_20d_portfolio_return": "压力20日组合收益",
    "stress_20d_qqq_return": "压力20日QQQ收益", "stress_20d_spy_return": "压力20日SPY收益",
    "stress_20d_smh_return": "压力20日SMH收益", "style_proxy_policy": "风格代理规则",
    "annualized_equity_volatility": "股票袖套年化波动", "metric": "审计指标", "value": "指标值",
    "issue_type": "问题类型", "evidence_status": "证据状态", "details": "详情",
}


def _localize(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns={key: TRANSLATIONS.get(key, f"字段_{key}") for key in frame.columns})


def write_style_crowding_bundle(
    frames: dict[str, pd.DataFrame],
    summary: dict,
    output_dir: str | Path,
    *,
    write_xlsx: bool = True,
) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    evidence = {}
    for name, frame in frames.items():
        path = output / f"{name}.csv"
        _atomic_csv(frame, path)
        manifest = write_dataset_manifest(
            path,
            dataset_type=f"ndx_style_crowding_{name}",
            dataset_key=str(summary.get("dataset_key") or "ndx_incumbent_v8g_v10_style_crowding_v1"),
            source="local_versioned_selection_taxonomy_and_price_cache",
            source_locator=str(summary.get("dataset_key")),
            fetched_at=utc_now_iso(),
            fetched_at_evidence="derived_from_hash_locked_local_sources",
            row_count=len(frame),
            extra={
                "research_only": True,
                "return_data_read": bool(summary.get("return_data_read")),
                "classification_return_data_used": False,
                "backtest_return_results_used": False,
                "price_data_used": bool(summary.get("price_data_used")),
                "fresh_oos": False,
                "promotion_allowed": False,
                "qqq_is_candidate": False,
            },
        )
        evidence[name] = {
            "filename": path.name, "rows": len(frame), "sha256": manifest["content_sha256"],
            "manifest_filename": manifest_path(path).name,
            "manifest_sha256": file_sha256(manifest_path(path)),
        }
        files[name] = path.name

    if write_xlsx:
        workbook = output / "ndx_style_crowding_diagnostic.xlsx"
        temporary = workbook.with_name(workbook.stem + ".tmp.xlsx")
        readme = pd.DataFrame([
            {"metric": key, "value": json.dumps(value, ensure_ascii=False, default=_json_default)}
            for key, value in summary.items()
        ])
        try:
            with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
                _localize(readme).to_excel(writer, sheet_name="说明与版本", index=False)
                for name, frame in frames.items():
                    sheet = {
                        "portfolio_summary": "组合摘要", "risk_chain_exposure": "风险链暴露",
                        "ticker_exposure": "股票分类", "style_metrics": "风格指标",
                        "risk_contributions": "边际风险", "coverage": "覆盖审计",
                        "unresolved": "未解决问题",
                    }.get(name, name)[:31]
                    _localize(frame).to_excel(writer, sheet_name=sheet, index=False)
            os.replace(temporary, workbook)
        finally:
            if temporary.exists():
                temporary.unlink()
        workbook_manifest = write_dataset_manifest(
            workbook,
            dataset_type="ndx_style_crowding_workbook",
            dataset_key=str(summary.get("dataset_key") or "ndx_incumbent_v8g_v10_style_crowding_v1"),
            source="local_versioned_selection_taxonomy_and_price_cache",
            source_locator=str(summary.get("dataset_key")),
            fetched_at=utc_now_iso(),
            fetched_at_evidence="derived_from_hash_locked_local_sources",
            row_count=len(frames["portfolio_summary"]),
            extra={
                "research_only": True, "return_data_read": bool(summary.get("return_data_read")),
                "classification_return_data_used": False, "backtest_return_results_used": False,
                "price_data_used": bool(summary.get("price_data_used")), "fresh_oos": False,
                "promotion_allowed": False, "qqq_is_candidate": False,
            },
        )
        files["workbook"] = workbook.name
        evidence["workbook"] = {
            "filename": workbook.name, "rows": len(frames["portfolio_summary"]),
            "sha256": workbook_manifest["content_sha256"],
            "manifest_filename": manifest_path(workbook).name,
            "manifest_sha256": file_sha256(manifest_path(workbook)),
        }

    payload = {
        **summary,
        "generated_at": utc_now_iso(),
        "files": files,
        "evidence_files": evidence,
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n")
    return payload


def read_verified_style_crowding_bundle(output_dir: str | Path) -> dict:
    """Read the static diagnostic bundle after verifying every derived file.

    This reader is intentionally separate from ``run_style_crowding_diagnostic``:
    an HTTP request may display an existing bundle, but it must never start a
    price load or recompute a backtest.
    """

    root = Path(output_dir)
    parent_manifest_path = root / "manifest.json"
    payload = _read_json(parent_manifest_path)
    if payload.get("dataset_type") != "ndx_style_crowding_diagnostic":
        raise NdxStyleCrowdingError("unexpected style/crowding bundle type")
    if payload.get("research_only") is not True:
        raise NdxStyleCrowdingError("style/crowding bundle is not research-only")
    if payload.get("fresh_oos") is not False or payload.get("promotion_allowed") is not False:
        raise NdxStyleCrowdingError("style/crowding bundle is not locked diagnostic-only")
    if payload.get("qqq_is_candidate") is not False:
        raise NdxStyleCrowdingError("style/crowding bundle promotes QQQ as a candidate")

    names = (
        "portfolio_summary", "risk_chain_exposure", "ticker_exposure",
        "style_metrics", "risk_contributions", "coverage", "unresolved",
    )
    frames = {}
    evidence_files = payload.get("evidence_files") or {}
    for name in names:
        evidence = evidence_files.get(name) or {}
        filename = str(evidence.get("filename") or f"{name}.csv")
        path = root / filename
        if path.resolve().parent != root.resolve():
            raise NdxStyleCrowdingError(f"style/crowding file escapes bundle: {filename}")
        if evidence.get("sha256") != file_sha256(path):
            raise NdxStyleCrowdingError(f"style/crowding content hash mismatch: {path}")
        sidecar = manifest_path(path)
        if evidence.get("manifest_sha256") != file_sha256(sidecar):
            raise NdxStyleCrowdingError(f"style/crowding sidecar hash mismatch: {sidecar}")
        sidecar_manifest, _ = _verify_sidecar(path)
        if sidecar_manifest.get("dataset_key") != payload.get("dataset_key"):
            raise NdxStyleCrowdingError(f"style/crowding dataset key mismatch: {path}")
        frames[name] = pd.read_csv(path, keep_default_na=False, low_memory=False)

    def records(frame: pd.DataFrame) -> list[dict]:
        return frame.where(pd.notna(frame), None).to_dict(orient="records")

    return {
        "available": True,
        "manifest": payload,
        "portfolio_summary": records(frames["portfolio_summary"]),
        "risk_chain_exposure": records(frames["risk_chain_exposure"]),
        "ticker_exposure": records(frames["ticker_exposure"]),
        "style_metrics": records(frames["style_metrics"]),
        "risk_contributions": records(frames["risk_contributions"]),
        "coverage": records(frames["coverage"]),
        "unresolved": records(frames["unresolved"]),
    }


__all__ = [
    "BENCHMARK_TICKERS", "DEFAULT_LOOKBACK_DAYS", "NdxStyleCrowdingError",
    "build_portfolios", "build_risk_chain_exposure", "load_classification_sources",
    "marginal_risk_contributions", "parse_weight_map", "plan_style_crowding_diagnostic",
    "read_verified_style_crowding_bundle", "resolve_risk_chain",
    "run_style_crowding_diagnostic", "style_metrics_before", "write_style_crowding_bundle",
]
