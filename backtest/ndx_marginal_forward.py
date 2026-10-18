"""Append-only forward cohorts and maturity evaluation for NDX v11 stage 1."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_marginal_stage1 import ALLOWED_SHARES, INCUMBENTS
from data.versioning import file_sha256


FORWARD_SCHEMA_VERSION = 1


class NdxMarginalForwardError(ValueError):
    pass


def load_forward_spec(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if int(payload.get("schema_version") or 0) != FORWARD_SCHEMA_VERSION:
        raise NdxMarginalForwardError("unsupported marginal-forward schema")
    if payload.get("research_only") is not True:
        raise NdxMarginalForwardError("marginal forward watch must be research_only")
    if payload.get("live_config_mutation_allowed") is not False:
        raise NdxMarginalForwardError("live mutation must remain disabled")
    selection = payload.get("selection_contract") or {}
    evaluation = payload.get("evaluation_contract") or {}
    if tuple(float(x) for x in selection.get("candidate_share_of_new_money") or []) != ALLOWED_SHARES:
        raise NdxMarginalForwardError("candidate share contract changed")
    if tuple(selection.get("incumbent_tickers") or []) != INCUMBENTS:
        raise NdxMarginalForwardError("incumbent identity changed")
    if int(selection.get("max_new_candidate_slots") or 0) != 1:
        raise NdxMarginalForwardError("stage 1 must retain one candidate slot")
    if evaluation.get("entry") != "first_common_session_open_on_or_after_observation_date":
        raise NdxMarginalForwardError("entry convention changed")
    if evaluation.get("exit") != "horizon_session_close":
        raise NdxMarginalForwardError("exit convention changed")
    if int(evaluation.get("minimum_paired_primary_windows") or 0) < 12:
        raise NdxMarginalForwardError("primary paired-window minimum cannot fall below 12")
    if list(evaluation.get("contribution_start_offsets_months") or []) != [0, 1, 2, 3, 4, 5]:
        raise NdxMarginalForwardError("six-month monthly contribution starts changed")
    payload["path"] = path.resolve().as_posix()
    payload["sha256"] = file_sha256(path)
    return payload


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "nat", "none"} else text


def _load_sidecar(path: Path, *, expected_return_data_read: bool) -> dict[str, Any]:
    sidecar = path.with_name(path.name + ".manifest.json")
    if not path.exists() or not sidecar.exists():
        raise NdxMarginalForwardError(f"missing versioned input: {path}")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    digest = file_sha256(path)
    if payload.get("content_sha256") != digest:
        raise NdxMarginalForwardError(f"input hash mismatch: {path}")
    if payload.get("return_data_read") is not expected_return_data_read:
        raise NdxMarginalForwardError(f"return-data identity mismatch: {path}")
    return {
        "path": path.resolve().as_posix(),
        "sha256": digest,
        "version_id": payload.get("version_id"),
        "rows": payload.get("row_count"),
        "return_data_read": expected_return_data_read,
    }


def build_cohort(
    *,
    observation_date: str,
    shortlist_path: Path,
    actions_path: Path,
    config_path: Path,
    spec_path: Path,
    imported_seed: bool,
    registered_date: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    observed = date.fromisoformat(str(observation_date)).isoformat()
    registered = date.fromisoformat(registered_date or date.today().isoformat()).isoformat()
    if observed > registered:
        raise NdxMarginalForwardError("future observation registration is forbidden")
    if observed < registered and not imported_seed:
        raise NdxMarginalForwardError("past observation requires explicit imported_seed")
    spec = load_forward_spec(spec_path)
    shortlist_version = _load_sidecar(shortlist_path, expected_return_data_read=True)
    action_version = _load_sidecar(actions_path, expected_return_data_read=False)
    shortlist = pd.read_csv(shortlist_path, low_memory=False)
    actions = pd.read_csv(actions_path, low_memory=False)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    selection_dates = sorted(set(shortlist["selection_date"].astype(str)))
    if selection_dates != [observed]:
        raise NdxMarginalForwardError(
            f"shortlist selection date must equal observation date: {selection_dates}"
        )
    shortlist_tickers = {_text(value) for value in shortlist["ticker"] if _text(value)}
    action_tickers = {_text(value) for value in actions["ticker"] if _text(value)}
    if shortlist_tickers != action_tickers:
        raise NdxMarginalForwardError("shortlist and action ticker sets differ")
    if set(pd.to_numeric(actions["target_candidate_share"], errors="coerce").dropna()) != set(ALLOWED_SHARES):
        raise NdxMarginalForwardError("action share grid differs from frozen contract")
    if not actions.loc[actions["ticker"].notna() & actions["ticker"].ne(""), "status"].eq(
        "FORWARD_WATCH_ONLY_NOT_SELECTED"
    ).all():
        raise NdxMarginalForwardError("unexpected candidate action status")
    symbols = config.get("symbols") or []
    cap_by_ticker = {str(row.get("ticker")): float(row.get("cap_total")) for row in symbols}
    if tuple(cap_by_ticker) != INCUMBENTS:
        raise NdxMarginalForwardError("live config incumbent order or identity changed")
    total_cap = sum(cap_by_ticker.values())
    incumbent_weights = {ticker: value / total_cap for ticker, value in cap_by_ticker.items()}
    rows = []
    for row in actions.to_dict("records"):
        ticker = _text(row.get("ticker"))
        share = float(row.get("target_candidate_share") or 0.0)
        action_id = str(row.get("action_id") or "")
        rows.append({
            "observation_date": observed,
            "registered_date": registered,
            "cohort_fresh_oos_eligible": bool(not imported_seed and observed == registered),
            "cohort_origin": "imported_seed" if imported_seed else "same_day_registration",
            "action_id": action_id,
            "ticker": ticker,
            "risk_chain": _text(row.get("risk_chain")),
            "target_candidate_share": share,
            "incumbent_share": 1.0 - share,
            "new_money": row.get("new_money"),
            "whole_lot_shares": row.get("whole_lot_shares"),
            "execution_claim_allowed": bool(pd.notna(row.get("new_money")) and pd.notna(row.get("whole_lot_shares"))),
            "research_status": (
                "PREEXISTING_SEED_NOT_FRESH_EVALUATION"
                if imported_seed else "FRESH_COHORT_REGISTERED_WAITING_FOR_MATURITY"
            ),
            "incumbent_weights_json": json.dumps(incumbent_weights, sort_keys=True, separators=(",", ":")),
        })
    cohort = pd.DataFrame(rows)
    manifest = {
        "schema_version": FORWARD_SCHEMA_VERSION,
        "manifest_type": "ndx_marginal_forward_cohort",
        "observation_date": observed,
        "registered_date": registered,
        "registered_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "cohort_origin": "imported_seed" if imported_seed else "same_day_registration",
        "fresh_oos_eligible": bool(not imported_seed and observed == registered),
        "candidate_admission_allowed": False,
        "stage_2_unlocked": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "spec": {"path": spec["path"], "sha256": spec["sha256"]},
        "inputs": {
            "shortlist": shortlist_version,
            "actions": action_version,
            "config": {"path": config_path.resolve().as_posix(), "sha256": file_sha256(config_path)},
        },
        "action_count": len(cohort),
        "candidate_count": int(cohort["ticker"].ne("").sum() / 3),
        "incumbent_weights": incumbent_weights,
    }
    manifest["cohort_content_sha256"] = _canonical_hash(cohort.fillna("").to_dict("records"))
    return cohort, manifest


def append_cohort_index(index_path: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    """Append one immutable cohort record with a previous-record hash chain."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_cohort_index(index_path)
    observed = str(record.get("observation_date") or "")
    matches = [row for row in existing if row.get("observation_date") == observed]
    if matches:
        comparable = {key: value for key, value in record.items() if key not in {"previous_record_sha256", "record_sha256"}}
        prior = {key: value for key, value in matches[0].items() if key not in {"previous_record_sha256", "record_sha256"}}
        if comparable != prior:
            raise NdxMarginalForwardError("observation date already registered with different evidence")
        return matches[0]
    unsigned = dict(record)
    unsigned["previous_record_sha256"] = existing[-1]["record_sha256"] if existing else None
    signed = {**unsigned, "record_sha256": _canonical_hash(unsigned)}
    with index_path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(signed, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return signed


def read_cohort_index(index_path: Path) -> list[dict[str, Any]]:
    """Read and verify every append-only index row and chain link."""
    existing: list[dict[str, Any]] = []
    if not index_path.exists():
        return existing
    with index_path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise NdxMarginalForwardError(f"invalid index JSONL row {line_number}") from exc
            expected = row.get("record_sha256")
            unsigned = {key: value for key, value in row.items() if key != "record_sha256"}
            if expected != _canonical_hash(unsigned):
                raise NdxMarginalForwardError(f"index hash mismatch at row {line_number}")
            if existing and row.get("previous_record_sha256") != existing[-1]["record_sha256"]:
                raise NdxMarginalForwardError(f"index chain mismatch at row {line_number}")
            if not existing and row.get("previous_record_sha256") is not None:
                raise NdxMarginalForwardError("first index row has a previous hash")
            existing.append(row)
    return existing


def read_price_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise NdxMarginalForwardError(f"price cache missing: {path}")
    frame = pd.read_csv(path)
    required = {"Date", "Open", "Close"}
    if not required.issubset(frame.columns):
        raise NdxMarginalForwardError(f"price cache columns missing: {path}")
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    for column in ("Open", "Close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["Date", "Open", "Close"]).drop_duplicates("Date").sort_values("Date").set_index("Date")


def _max_drawdown(values: np.ndarray) -> float:
    peak = np.maximum.accumulate(values)
    return float(np.max(np.where(peak > 0, (peak - values) / peak, 0.0)))


def _window_metrics(
    dates: pd.DatetimeIndex,
    *,
    prices: Mapping[str, pd.DataFrame],
    weights: Mapping[str, float],
    candidate: str,
    candidate_share: float,
    cost: float,
    target_nav: pd.DataFrame | None,
) -> dict[str, Any]:
    size = len(dates)
    incumbent_curve = np.zeros(size, dtype=float)
    for ticker, weight in weights.items():
        frame = prices[ticker]
        entry_open = float(frame.loc[dates[0], "Open"])
        incumbent_curve += float(weight) * frame.loc[dates, "Close"].to_numpy(dtype=float) / entry_open
    strategy_curve = incumbent_curve.copy()
    if candidate:
        frame = prices[candidate]
        candidate_curve = frame.loc[dates, "Close"].to_numpy(dtype=float) / float(frame.loc[dates[0], "Open"])
        strategy_curve = (1.0 - candidate_share) * incumbent_curve + candidate_share * candidate_curve
    incumbent_nav = np.concatenate(([1.0], (1.0 - cost) * incumbent_curve))
    strategy_nav = np.concatenate(([1.0], (1.0 - cost) * strategy_curve))
    incumbent_return = float(incumbent_nav[-1] - 1.0)
    strategy_return = float(strategy_nav[-1] - 1.0)
    incumbent_dd = _max_drawdown(incumbent_nav)
    strategy_dd = _max_drawdown(strategy_nav)
    target_return = None
    target_dd = None
    target_mature = False
    target_entry_date = None
    target_exit_date = None
    target_exit_lag = None
    if target_nav is not None and not target_nav.empty:
        target_window = target_nav.loc[
            (target_nav.index >= dates[0]) & (target_nav.index <= dates[-1]), "Close"
        ].dropna()
        if len(target_window) >= 2:
            target_entry_date = target_window.index[0].strftime("%Y-%m-%d")
            target_exit_date = target_window.index[-1].strftime("%Y-%m-%d")
            target_exit_lag = int(np.busday_count(target_window.index[-1].date(), dates[-1].date()))
        if len(target_window) >= 2 and target_exit_lag is not None and target_exit_lag <= 3:
            target_values = target_window.to_numpy(dtype=float)
            target_return = float(target_values[-1] / target_values[0] - 1.0)
            target_dd = _max_drawdown(target_values / target_values[0])
            target_mature = True
    return {
        "exit_date": dates[-1].strftime("%Y-%m-%d"),
        "strategy_return": strategy_return,
        "incumbent_return": incumbent_return,
        "return_delta_vs_incumbent": strategy_return - incumbent_return,
        "strategy_max_drawdown": strategy_dd,
        "incumbent_max_drawdown": incumbent_dd,
        "dd_cost_vs_incumbent": strategy_dd - incumbent_dd,
        "target_return": target_return,
        "return_delta_vs_target": strategy_return - target_return if target_return is not None else None,
        "target_max_drawdown": target_dd,
        "dd_cost_vs_target": strategy_dd - target_dd if target_dd is not None else None,
        "target_mature": target_mature,
        "target_entry_date": target_entry_date,
        "target_exit_date": target_exit_date,
        "target_exit_lag_business_days": target_exit_lag,
    }


def build_cohort_curve_points(
    cohort: pd.DataFrame,
    *,
    price_cache_dir: Path,
    transaction_cost_bps: float,
    target_nav: pd.DataFrame | None = None,
    start_offset_months: int = 0,
    primary_horizon: int = 126,
) -> pd.DataFrame:
    """Build display curves from a frozen cohort without creating admission evidence."""
    columns = [
        "observation_date", "action_id", "ticker", "risk_chain",
        "target_candidate_share", "window_start_offset_months", "date",
        "curve_session", "strategy_nav", "incumbent_nav", "target_012922_nav",
        "strategy_drawdown", "incumbent_drawdown", "target_012922_drawdown",
        "return_delta_vs_incumbent", "fresh_oos_eligible", "mature_primary",
        "evidence_role",
    ]
    if cohort.empty:
        return pd.DataFrame(columns=columns)
    observed = pd.Timestamp(str(cohort.iloc[0]["observation_date"]))
    not_before = observed + pd.DateOffset(months=int(start_offset_months))
    weights = json.loads(str(cohort.iloc[0]["incumbent_weights_json"]))
    tickers = sorted(
        set(weights).union(set(cohort.loc[cohort["ticker"].ne(""), "ticker"]))
    )
    prices = {
        ticker: read_price_cache(price_cache_dir / f"{ticker}.csv")
        for ticker in tickers
    }
    cost = max(0.0, float(transaction_cost_bps)) / 10_000.0
    rows: list[dict[str, Any]] = []
    for action in cohort.to_dict("records"):
        candidate = str(action.get("ticker") or "")
        share = float(action.get("target_candidate_share") or 0.0)
        action_tickers = list(weights) + ([candidate] if candidate else [])
        common: pd.DatetimeIndex | None = None
        for ticker in action_tickers:
            dates = prices[ticker].index[prices[ticker].index >= not_before]
            common = dates if common is None else common.intersection(dates)
        dates = (
            pd.DatetimeIndex([])
            if common is None
            else pd.DatetimeIndex(common).sort_values()
        )
        if dates.empty:
            continue
        incumbent_curve = np.zeros(len(dates), dtype=float)
        for ticker, weight in weights.items():
            entry_open = float(prices[ticker].loc[dates[0], "Open"])
            incumbent_curve += (
                float(weight)
                * prices[ticker].loc[dates, "Close"].to_numpy(dtype=float)
                / entry_open
            )
        strategy_curve = incumbent_curve.copy()
        if candidate:
            candidate_curve = (
                prices[candidate].loc[dates, "Close"].to_numpy(dtype=float)
                / float(prices[candidate].loc[dates[0], "Open"])
            )
            strategy_curve = (
                (1.0 - share) * incumbent_curve + share * candidate_curve
            )
        incumbent_curve = (1.0 - cost) * incumbent_curve
        strategy_curve = (1.0 - cost) * strategy_curve
        incumbent_dd = incumbent_curve / np.maximum.accumulate(incumbent_curve) - 1.0
        strategy_dd = strategy_curve / np.maximum.accumulate(strategy_curve) - 1.0
        target_values = pd.Series(np.nan, index=dates, dtype=float)
        if target_nav is not None and not target_nav.empty:
            target_close = target_nav["Close"].reindex(dates).dropna()
            if not target_close.empty:
                target_values.loc[target_close.index] = (
                    target_close / float(target_close.iloc[0])
                )
        target_array = target_values.to_numpy(dtype=float)
        target_dd = np.full(len(dates), np.nan, dtype=float)
        finite_target = np.isfinite(target_array)
        if finite_target.any():
            observed_target = target_array[finite_target]
            target_dd[finite_target] = (
                observed_target / np.maximum.accumulate(observed_target) - 1.0
            )
        mature_primary = bool(len(dates) >= int(primary_horizon))
        for index, curve_date in enumerate(dates):
            rows.append({
                "observation_date": action["observation_date"],
                "action_id": action["action_id"],
                "ticker": candidate,
                "risk_chain": action.get("risk_chain"),
                "target_candidate_share": share,
                "window_start_offset_months": int(start_offset_months),
                "date": curve_date.strftime("%Y-%m-%d"),
                "curve_session": index + 1,
                "strategy_nav": float(strategy_curve[index]),
                "incumbent_nav": float(incumbent_curve[index]),
                "target_012922_nav": (
                    float(target_array[index]) if np.isfinite(target_array[index]) else None
                ),
                "strategy_drawdown": float(strategy_dd[index]),
                "incumbent_drawdown": float(incumbent_dd[index]),
                "target_012922_drawdown": (
                    float(target_dd[index]) if np.isfinite(target_dd[index]) else None
                ),
                "return_delta_vs_incumbent": float(
                    strategy_curve[index] - incumbent_curve[index]
                ),
                "fresh_oos_eligible": bool(action["cohort_fresh_oos_eligible"]),
                "mature_primary": mature_primary,
                "evidence_role": "FORWARD_CURVE_MONITORING_ONLY_NOT_ADMISSION_EVIDENCE",
            })
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["observation_date", "action_id", "curve_session"], kind="stable"
    ).reset_index(drop=True)


def evaluate_cohort(
    cohort: pd.DataFrame,
    *,
    price_cache_dir: Path,
    horizons: list[int],
    transaction_cost_bps: float,
    target_nav: pd.DataFrame | None = None,
    start_offsets_months: list[int] | None = None,
) -> pd.DataFrame:
    if cohort.empty:
        return pd.DataFrame()
    observed = pd.Timestamp(str(cohort.iloc[0]["observation_date"]))
    offsets = sorted(set(int(value) for value in (start_offsets_months or [0])))
    weights = json.loads(str(cohort.iloc[0]["incumbent_weights_json"]))
    tickers = sorted(set(weights).union(set(cohort.loc[cohort["ticker"].ne(""), "ticker"])))
    prices = {ticker: read_price_cache(price_cache_dir / f"{ticker}.csv") for ticker in tickers}
    cost = max(0.0, float(transaction_cost_bps)) / 10_000.0
    rows = []
    for action in cohort.to_dict("records"):
        candidate = str(action.get("ticker") or "")
        share = float(action.get("target_candidate_share") or 0.0)
        action_tickers = list(weights) + ([candidate] if candidate else [])
        for offset in offsets:
            window_not_before = observed + pd.DateOffset(months=offset)
            common = None
            for ticker in action_tickers:
                dates = prices[ticker].index[prices[ticker].index >= window_not_before]
                common = dates if common is None else common.intersection(dates)
            common = pd.DatetimeIndex([]) if common is None else pd.DatetimeIndex(common).sort_values()
            for horizon in sorted(set(int(value) for value in horizons)):
                mature = len(common) >= horizon
                base = {
                "observation_date": action["observation_date"],
                "action_id": action["action_id"],
                "ticker": candidate,
                "risk_chain": action.get("risk_chain"),
                "target_candidate_share": share,
                "window_start_offset_months": offset,
                "window_not_before": window_not_before.strftime("%Y-%m-%d"),
                "horizon_trading_days": horizon,
                "fresh_oos_eligible": bool(action["cohort_fresh_oos_eligible"]),
                "entry_date": common[0].strftime("%Y-%m-%d") if len(common) else None,
                "available_common_sessions": len(common),
                "mature": mature,
                "execution_claim_allowed": bool(action["execution_claim_allowed"]),
            }
                if not mature:
                    interim = (
                        _window_metrics(
                            common,
                            prices=prices,
                            weights=weights,
                            candidate=candidate,
                            candidate_share=share,
                            cost=cost,
                            target_nav=target_nav,
                        )
                        if len(common) else {}
                    )
                    rows.append({
                    **base,
                    "exit_date": None,
                    "strategy_return": None,
                    "incumbent_return": None,
                    "return_delta_vs_incumbent": None,
                    "strategy_max_drawdown": None,
                    "incumbent_max_drawdown": None,
                    "dd_cost_vs_incumbent": None,
                    "target_return": None,
                    "return_delta_vs_target": None,
                    "target_max_drawdown": None,
                    "dd_cost_vs_target": None,
                    "target_mature": False,
                    "target_entry_date": None,
                    "target_exit_date": None,
                    "target_exit_lag_business_days": None,
                    "interim_exit_date": interim.get("exit_date"),
                    "interim_strategy_return": interim.get("strategy_return"),
                    "interim_incumbent_return": interim.get("incumbent_return"),
                    "interim_return_delta_vs_incumbent": interim.get("return_delta_vs_incumbent"),
                    "interim_strategy_max_drawdown": interim.get("strategy_max_drawdown"),
                    "interim_incumbent_max_drawdown": interim.get("incumbent_max_drawdown"),
                    "interim_dd_cost_vs_incumbent": interim.get("dd_cost_vs_incumbent"),
                    "interim_target_return": interim.get("target_return"),
                    "interim_return_delta_vs_target": interim.get("return_delta_vs_target"),
                    "interim_is_admission_evidence": False,
                    "status": "WAITING_FOR_MATURITY" if len(common) else "WAITING_FOR_ENTRY_PRICE",
                    })
                    continue
                dates = common[:horizon]
                metrics = _window_metrics(
                    dates,
                    prices=prices,
                    weights=weights,
                    candidate=candidate,
                    candidate_share=share,
                    cost=cost,
                    target_nav=target_nav,
                )
                rows.append({
                **base,
                **metrics,
                "interim_exit_date": None,
                "interim_strategy_return": None,
                "interim_incumbent_return": None,
                "interim_return_delta_vs_incumbent": None,
                "interim_strategy_max_drawdown": None,
                "interim_incumbent_max_drawdown": None,
                "interim_dd_cost_vs_incumbent": None,
                "interim_target_return": None,
                "interim_return_delta_vs_target": None,
                "interim_is_admission_evidence": False,
                "status": "MATURE_IMPORTED_SEED_NOT_FRESH" if not base["fresh_oos_eligible"] else "MATURE_FRESH_FORWARD",
                })
    return pd.DataFrame(rows)


def build_maturity_summary(
    evaluations: pd.DataFrame,
    *,
    primary_horizon: int,
    minimum_windows: int,
) -> pd.DataFrame:
    if evaluations.empty:
        return pd.DataFrame(columns=["action_id", "primary_mature_fresh_cohorts", "admission_status"])
    primary = evaluations.loc[
        evaluations["horizon_trading_days"].eq(int(primary_horizon))
        & evaluations["mature"]
        & evaluations["fresh_oos_eligible"]
    ].copy()
    rows = []
    for action_id in sorted(set(evaluations["action_id"])):
        group = primary.loc[primary["action_id"].eq(action_id)]
        returns = pd.to_numeric(group["return_delta_vs_incumbent"], errors="coerce").dropna()
        dd_costs = pd.to_numeric(group["dd_cost_vs_incumbent"], errors="coerce").dropna()
        target_returns = pd.to_numeric(
            group["return_delta_vs_target"] if "return_delta_vs_target" in group else pd.Series(dtype=float),
            errors="coerce",
        ).dropna()
        target_dd_costs = pd.to_numeric(
            group["dd_cost_vs_target"] if "dd_cost_vs_target" in group else pd.Series(dtype=float),
            errors="coerce",
        ).dropna()
        enough = len(group) >= int(minimum_windows)
        target_enough = enough and len(target_returns) == len(group) and len(target_dd_costs) == len(group)
        rows.append({
            "action_id": action_id,
            "primary_mature_fresh_windows": len(group),
            "return_delta_p50": returns.quantile(0.50) if enough else None,
            "return_delta_p10": returns.quantile(0.10) if enough else None,
            "dd_cost_p50": dd_costs.quantile(0.50) if enough else None,
            "dd_cost_p90": dd_costs.quantile(0.90) if enough else None,
            "target_return_delta_p50": target_returns.quantile(0.50) if target_enough else None,
            "target_return_delta_p10": target_returns.quantile(0.10) if target_enough else None,
            "target_dd_cost_p50": target_dd_costs.quantile(0.50) if target_enough else None,
            "target_dd_cost_p90": target_dd_costs.quantile(0.90) if target_enough else None,
            "incumbent_gate_evaluated": enough,
            "target_012922_gate_evaluated": target_enough,
            "admission_status": (
                "BLOCKED_TARGET_012922_POLICY_GATE_NOT_APPLIED"
                if target_enough else (
                    "BLOCKED_TARGET_012922_EVIDENCE_INCOMPLETE"
                    if enough else "INSUFFICIENT_FRESH_PRIMARY_COHORTS"
                )
            ),
            "stage_2_unlocked": False,
        })
    return pd.DataFrame(rows)


__all__ = [
    "NdxMarginalForwardError",
    "append_cohort_index",
    "build_cohort",
    "build_maturity_summary",
    "evaluate_cohort",
    "load_forward_spec",
    "read_cohort_index",
]
