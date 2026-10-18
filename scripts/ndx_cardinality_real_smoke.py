r"""Run one point-in-time, real-data cardinality training smoke.

This is training discovery only. It uses data strictly before selection_date,
does not consume forward returns, and cannot promote a portfolio.

PowerShell/PyCharm:
    python -B scripts\ndx_cardinality_real_smoke.py --track strict_technology --selection-date 2024-06-03 --holding-count 2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cardinality_discovery import (
    _frontier_tags,
    evaluate_synthetic_portfolio,
    load_discovery_spec,
    search_synthetic_cardinality,
    search_two_stage_cardinality,
    validate_discovery_spec,
)
from backtest.ndx_cardinality_input_readiness import load_price_series
from backtest.ndx_whole_lot_rebalance import (
    load_point_in_time_security_bars,
)
from core.helpers import atomic_write_text
from data.ndx_execution_price import load_verified_execution_cache
from data.ndx_security_identity import load_security_lifecycle
from data.versioning import file_sha256


class NdxCardinalityRealSmokeError(ValueError):
    pass


INCUMBENT = ["NVDA", "TXN", "ASML", "CDNS", "TSM", "MU", "MSFT", "GOOG"]


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _verified_csv(manifest: dict, key: str) -> tuple[pd.DataFrame, Path]:
    artifact = (manifest.get("artifacts") or {}).get(key) or {}
    path = Path(str(artifact.get("path") or ""))
    if not path.is_absolute() or file_sha256(path) != str(artifact.get("sha256") or ""):
        raise NdxCardinalityRealSmokeError(f"input readiness artifact mismatch: {key}")
    frame = pd.read_csv(path, low_memory=False)
    if len(frame) != int(artifact.get("rows") or -1):
        raise NdxCardinalityRealSmokeError(f"input readiness artifact row count changed: {key}")
    return frame, path


def _load_bars(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, usecols=["Date", "Close", "Volume"])
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    frame["Volume"] = pd.to_numeric(frame["Volume"], errors="coerce")
    if frame.isna().any().any() or frame["Date"].duplicated().any():
        raise NdxCardinalityRealSmokeError(f"invalid price bars: {path}")
    if not frame["Date"].is_monotonic_increasing:
        raise NdxCardinalityRealSmokeError(f"unsorted price bars: {path}")
    if (frame[["Close", "Volume"]] < 0).any().any() or (frame["Close"] == 0).any():
        raise NdxCardinalityRealSmokeError(f"non-positive price bars: {path}")
    return frame.set_index("Date")


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _assign_replay_frontiers(frame: pd.DataFrame) -> pd.DataFrame:
    """Tag locked replay results both within k and across all replayed k.

    The within-cardinality tags preserve the original coordinate audit.  The
    cross-cardinality tags are the portfolio-optimization comparison and must
    not be omitted when one replay job evaluates several holding counts.
    """
    required = {"holding_count", "declared_constraints_passed"}
    if frame.empty or not required.issubset(frame.columns):
        raise NdxCardinalityRealSmokeError("candidate replay frontier input is incomplete")
    tagged = frame.copy()
    tagged["frontier_tags"] = ""
    tagged["constrained_frontier_tags"] = ""
    for _, indexes in tagged.groupby("holding_count", sort=True).groups.items():
        group = tagged.loc[indexes]
        tagged.loc[indexes, "frontier_tags"] = _frontier_tags(group)
        compliant = group["declared_constraints_passed"].astype(bool)
        if bool(compliant.any()):
            compliant_indexes = group.index[compliant]
            tagged.loc[compliant_indexes, "constrained_frontier_tags"] = _frontier_tags(
                group.loc[compliant_indexes]
            )
    tagged["cross_cardinality_frontier_tags"] = _frontier_tags(tagged)
    tagged["cross_cardinality_constrained_frontier_tags"] = ""
    compliant = tagged["declared_constraints_passed"].astype(bool)
    if bool(compliant.any()):
        compliant_indexes = tagged.index[compliant]
        tagged.loc[
            compliant_indexes, "cross_cardinality_constrained_frontier_tags"
        ] = _frontier_tags(tagged.loc[compliant_indexes])
    return tagged


def _attach_point_in_time_identity_columns(
    frame: pd.DataFrame, search_universe: pd.DataFrame,
) -> pd.DataFrame:
    """Bind each ticker list to its decision-date security/issuer identities."""
    required = {"ticker", "security_id", "issuer_id", "risk_chain"}
    if frame.empty or "tickers" not in frame or not required.issubset(search_universe.columns):
        raise NdxCardinalityRealSmokeError("candidate identity input is incomplete")
    if search_universe["ticker"].astype(str).duplicated().any():
        raise NdxCardinalityRealSmokeError("point-in-time ticker identity is ambiguous")
    lookup = search_universe.set_index(search_universe["ticker"].astype(str))
    security_values: list[str] = []
    issuer_values: list[str] = []
    chain_values: list[str] = []
    for value in frame["tickers"].astype(str):
        tickers = [item for item in value.split(";") if item]
        if not tickers or any(ticker not in lookup.index for ticker in tickers):
            raise NdxCardinalityRealSmokeError("candidate ticker identity cannot be resolved")
        rows = lookup.loc[tickers]
        security_ids = rows["security_id"].astype(str).tolist()
        issuer_ids = rows["issuer_id"].astype(str).tolist()
        risk_chains = rows["risk_chain"].astype(str).tolist()
        if len(set(security_ids)) != len(security_ids) or len(set(issuer_ids)) != len(issuer_ids):
            raise NdxCardinalityRealSmokeError("candidate violates security/issuer uniqueness")
        security_values.append(";".join(security_ids))
        issuer_values.append(";".join(issuer_ids))
        chain_values.append(";".join(risk_chains))
    result = frame.copy()
    result["security_ids"] = security_values
    result["issuer_ids"] = issuer_values
    result["risk_chains"] = chain_values
    return result


def run(args) -> dict:
    spec_path = _resolve(args.spec)
    readiness_manifest_path = _resolve(args.input_readiness_manifest)
    discovery_manifest_path = _resolve(args.discovery_manifest)
    lifecycle_path = _resolve(args.security_lifecycle)
    execution_price_manifest_path = _resolve(args.execution_price_manifest)
    price_root = _resolve(args.return_cache_dir)
    target_path = _resolve(args.target_nav)
    state_path = _resolve(args.state)
    config_path = _resolve(args.config)
    output = _resolve(args.output_dir)
    protected_before = {"config": file_sha256(config_path), "state": file_sha256(state_path)}

    spec = load_discovery_spec(spec_path)
    validate_discovery_spec(spec)
    readiness = json.loads(readiness_manifest_path.read_text(encoding="utf-8"))
    if readiness.get("manifest_type") != "ndx_cardinality_real_input_readiness":
        raise NdxCardinalityRealSmokeError("unexpected input readiness manifest")
    if readiness.get("promotion_allowed") is not False:
        raise NdxCardinalityRealSmokeError("input readiness unexpectedly allows promotion")
    membership_audit, membership_audit_path = _verified_csv(readiness, "membership_readiness")
    job_audit, job_audit_path = _verified_csv(readiness, "job_readiness")
    identity_audit, identity_audit_path = _verified_csv(readiness, "identity")
    failed_lifecycle_issuers: set[str] = set()
    if not identity_audit.empty:
        failed_identity = identity_audit.loc[
            ~identity_audit["identity_status"].astype(str).eq("IDENTITY_MATCH")
        ]
        for value in failed_identity["issuer_ids"].fillna("").astype(str):
            failed_lifecycle_issuers.update(item for item in value.split(";") if item)

    discovery = json.loads(discovery_manifest_path.read_text(encoding="utf-8"))
    locked_lifecycle = ((discovery.get("inputs") or {}).get("ticker_lifecycle") or {}).get("sha256")
    if file_sha256(lifecycle_path) != locked_lifecycle:
        raise NdxCardinalityRealSmokeError("security lifecycle hash is stale")
    lifecycle = load_security_lifecycle(lifecycle_path)
    execution_bundle = json.loads(execution_price_manifest_path.read_text(encoding="utf-8"))
    bundle_selection = pd.Timestamp(execution_bundle.get("selection_date")).normalize()
    single_coordinate_matches = bool(
        execution_bundle.get("coordinate_scope") in {None, "SINGLE_COORDINATE"}
        and execution_bundle.get("universe_track") == args.track
        and bundle_selection == pd.Timestamp(args.selection_date).normalize()
    )
    all_coordinate_covers = bool(
        execution_bundle.get("coordinate_scope") == "ALL_DEGRADED_READY_COORDINATES"
        and execution_bundle.get("universe_track") == "ALL"
        and bundle_selection >= pd.Timestamp(args.selection_date).normalize()
    )
    if (
        execution_bundle.get("manifest_type") != "ndx_cardinality_whole_lot_execution_price_bundle"
        or execution_bundle.get("status") != "READY"
        or execution_bundle.get("research_track") != "portfolio_optimization"
        or execution_bundle.get("migration_control_included") is not False
        or execution_bundle.get("whole_lot_execution_use_only") is not True
        or not (single_coordinate_matches or all_coordinate_covers)
    ):
        raise NdxCardinalityRealSmokeError("whole-lot execution price bundle contract mismatch")
    execution_inventory_artifact = execution_bundle["artifacts"]["inventory"]
    execution_inventory_path = Path(execution_inventory_artifact["path"])
    if file_sha256(execution_inventory_path) != execution_inventory_artifact["sha256"]:
        raise NdxCardinalityRealSmokeError("whole-lot execution inventory hash mismatch")
    execution_inventory = pd.read_csv(execution_inventory_path, low_memory=False)
    if len(execution_inventory) != int(execution_inventory_artifact["rows"]):
        raise NdxCardinalityRealSmokeError("whole-lot execution inventory row count changed")
    execution_inventory_by_ticker = execution_inventory.set_index("ticker")
    execution_cache_root = execution_price_manifest_path.parent
    execution_raw_dir = execution_cache_root / "raw"
    requested_execution_end = str(execution_bundle["requested_end"])

    def verified_execution_bars(ticker: str) -> pd.DataFrame:
        if ticker not in execution_inventory_by_ticker.index:
            raise NdxCardinalityRealSmokeError(f"execution inventory missing {ticker}")
        inventory_row = execution_inventory_by_ticker.loc[ticker]
        if str(inventory_row["status"]) != "FETCHED":
            raise NdxCardinalityRealSmokeError(f"execution price not fetched for {ticker}")
        frame, manifest = load_verified_execution_cache(
            execution_cache_root, ticker, requested_end=requested_execution_end,
        )
        path = Path(str(inventory_row["path"]))
        sidecar_path = Path(str(inventory_row["sidecar_path"]))
        if (
            file_sha256(path) != str(inventory_row["sha256"])
            or file_sha256(sidecar_path) != str(inventory_row["sidecar_sha256"])
            or manifest.get("content_sha256") != str(inventory_row["sha256"])
        ):
            raise NdxCardinalityRealSmokeError(f"execution inventory artifact mismatch: {ticker}")
        return frame
    members_artifact = (discovery.get("artifacts") or {}).get("eligible_securities") or {}
    members_path = Path(str(members_artifact.get("path") or ""))
    if not members_path.is_absolute() or file_sha256(members_path) != members_artifact.get("sha256"):
        raise NdxCardinalityRealSmokeError("point-in-time membership artifact mismatch")
    members = pd.read_csv(members_path, low_memory=False)

    selection = pd.Timestamp(args.selection_date).normalize()
    track = str(args.track)
    holding_count = int(args.holding_count)
    replay_source_frame = None
    requested_holding_counts = [holding_count]
    if args.candidate_sets_file:
        replay_source_frame = pd.read_csv(_resolve(args.candidate_sets_file), low_memory=False)
        required_replay_columns = {
            "universe_track", "selection_date", "holding_count", "tickers", "weight_spec",
        }
        if not required_replay_columns.issubset(replay_source_frame.columns):
            raise NdxCardinalityRealSmokeError("candidate replay source columns are incomplete")
        if args.source_batch:
            if "source_batch" not in replay_source_frame.columns:
                raise NdxCardinalityRealSmokeError("candidate replay source_batch column is missing")
            replay_source_frame = replay_source_frame.loc[
                replay_source_frame["source_batch"].astype(str).eq(str(args.source_batch))
            ].copy()
        coordinate_scope = replay_source_frame.loc[
            replay_source_frame["universe_track"].astype(str).eq(track)
            & replay_source_frame["selection_date"].astype(str).eq(selection.date().isoformat())
        ].copy()
        if holding_count > 0:
            coordinate_scope = coordinate_scope.loc[
                pd.to_numeric(coordinate_scope["holding_count"], errors="coerce").eq(holding_count)
            ]
        requested_holding_counts = sorted(
            pd.to_numeric(coordinate_scope["holding_count"], errors="raise").astype(int).unique().tolist()
        )
        if not requested_holding_counts or any(value <= 0 for value in requested_holding_counts):
            raise NdxCardinalityRealSmokeError("candidate replay source has no valid requested holding counts")
    elif holding_count <= 0:
        raise NdxCardinalityRealSmokeError("holding_count must be positive outside candidate replay mode")
    jobs = job_audit.loc[
        job_audit["universe_track"].eq(track)
        & job_audit["selection_date"].eq(selection.date().isoformat())
        & job_audit["holding_count"].isin(requested_holding_counts)
    ]
    if (
        len(jobs) != len(requested_holding_counts)
        or not jobs["degraded_research_job_ready"].astype(bool).all()
    ):
        raise NdxCardinalityRealSmokeError("requested degraded training job is not ready")
    audit_rows = membership_audit.loc[
        membership_audit["universe_track"].eq(track)
        & membership_audit["selection_date"].eq(selection.date().isoformat())
    ][["security_id", "input_ready", "identity_status", "readiness_reason"]]
    coordinate_members = members.loc[
        members["universe_track"].eq(track)
        & members["selection_date"].eq(selection.date().isoformat())
        & members["membership_window_eligible"].astype(bool)
    ].copy()
    universe = coordinate_members.merge(
        audit_rows.loc[audit_rows["input_ready"].astype(bool), ["security_id", "input_ready"]],
        on="security_id", how="inner", validate="one_to_one",
    )
    if universe.empty:
        raise NdxCardinalityRealSmokeError("degraded point-in-time universe is empty")

    lifecycle_rows = []
    for rule in lifecycle.rules_by_cik.values():
        prefix = f"security:{rule.cik}:"
        present = coordinate_members.loc[
            coordinate_members["security_id"].astype(str).str.startswith(prefix)
        ]
        eligible = universe.loc[universe["security_id"].astype(str).str.startswith(prefix)]
        row = {
            "lifecycle_rule_id": rule.rule_id,
            "recognized_tickers": ";".join(sorted(rule.recognized_tickers)),
            "coordinate_security_count": len(present),
            "eligible_security_count": len(eligible),
            "portfolio_track": "portfolio_optimization",
            "candidate_returns_used": False,
            "status": "",
        }
        if len(eligible):
            row["status"] = "ELIGIBLE_COORDINATE_STITCHED_BY_SECURITY_ID"
            row["candidate_returns_used"] = True
        elif len(present):
            blocked = audit_rows.loc[
                audit_rows["security_id"].isin(present["security_id"])
            ]
            row["status"] = "BLOCKED_COORDINATE_NOT_STITCHED"
            row["block_reason"] = ";".join(sorted(blocked["readiness_reason"].astype(str).unique()))
        elif f"issuer:{rule.cik}" in failed_lifecycle_issuers:
            row["status"] = "GLOBAL_IDENTITY_BLOCKED_NOT_STITCHED"
            row["block_reason"] = "ISSUER_LIFECYCLE_IDENTITY_CHAIN_INCOMPLETE"
        else:
            logical_ticker = rule.resolve(selection)
            security_id = f"security:{rule.cik}:{rule.cusip}"
            for interval in rule.intervals:
                if interval.effective_from is None or interval.effective_from < selection:
                    verified_execution_bars(interval.price_ticker)
            _, control = load_point_in_time_security_bars(
                ticker=logical_ticker,
                security_id=security_id,
                return_cache_dir=execution_raw_dir,
                lifecycle=lifecycle,
                end_exclusive=selection,
            )
            row.update(control)
            row["status"] = "NOMINAL_CACHE_STITCHABLE_CONTROL_NOT_ELIGIBLE_COORDINATE"
        lifecycle_rows.append(row)
    lifecycle_coverage = pd.DataFrame(lifecycle_rows)

    bars: dict[str, pd.DataFrame] = {}
    inventory_rows = []
    universe_by_ticker = universe.drop_duplicates("ticker").set_index("ticker")
    all_tickers = sorted(set(universe["ticker"].astype(str)) | set(INCUMBENT))
    for ticker in all_tickers:
        if ticker in universe_by_ticker.index:
            security_id = str(universe_by_ticker.loc[ticker, "security_id"])
            frame, source = load_point_in_time_security_bars(
                ticker=ticker,
                security_id=security_id,
                return_cache_dir=price_root,
                lifecycle=lifecycle,
                end_exclusive=selection,
            )
        else:
            path = price_root / f"{ticker}.csv"
            frame = _load_bars(path).loc[lambda value: value.index < selection].copy()
            source = {
                "lifecycle_rule_id": "", "source_tickers": ticker,
                "source_files": path.as_posix(), "source_sha256": file_sha256(path),
                "segment_count": 1, "cross_ticker_stitched": False,
            }
        bars[ticker] = frame
        before = frame.loc[frame.index < selection]
        inventory_rows.append({
            "ticker": ticker,
            "path": source["source_files"],
            "sha256": source["source_sha256"],
            "rows": len(frame),
            "rows_before_selection": len(before),
            "data_start": frame.index.min().date().isoformat(),
            "data_end": frame.index.max().date().isoformat(),
            "lifecycle_rule_id": source["lifecycle_rule_id"],
            "source_tickers": source["source_tickers"],
            "segment_count": source["segment_count"],
            "cross_ticker_stitched": source["cross_ticker_stitched"],
        })
    inventory = pd.DataFrame(inventory_rows)
    minimum_rows = int(args.minimum_price_rows_before_selection)
    eligible_tickers = set(
        inventory.loc[
            inventory["ticker"].isin(universe["ticker"])
            & inventory["rows_before_selection"].ge(minimum_rows),
            "ticker",
        ]
    )
    excluded_for_history = sorted(set(universe["ticker"].astype(str)) - eligible_tickers)
    universe = universe.loc[universe["ticker"].isin(eligible_tickers)].copy()
    if universe["issuer_id"].nunique() < max(requested_holding_counts):
        raise NdxCardinalityRealSmokeError("history coverage leaves too few issuers")

    price_columns = {
        ticker: bars[ticker].loc[bars[ticker].index < selection, "Close"].rename(ticker)
        for ticker in sorted(set(universe["ticker"].astype(str)) | set(INCUMBENT))
    }
    prices = pd.concat(price_columns.values(), axis=1, join="inner").dropna()
    prices = prices.tail(int(args.training_lookback_days) + 1)
    nominal_columns = {}
    for ticker in sorted(universe["ticker"].astype(str).unique()):
        security_id = str(universe_by_ticker.loc[ticker, "security_id"])
        rule = lifecycle.rules_by_cik.get(security_id.split(":")[1])
        if rule is not None:
            for interval in rule.intervals:
                if interval.effective_from is None or interval.effective_from < selection:
                    verified_execution_bars(interval.price_ticker)
            nominal, _ = load_point_in_time_security_bars(
                ticker=ticker, security_id=security_id,
                return_cache_dir=execution_raw_dir, lifecycle=lifecycle,
                end_exclusive=selection,
            )
        else:
            nominal = verified_execution_bars(ticker)
            nominal = nominal.loc[nominal.index < selection]
        nominal_columns[ticker] = nominal["Close"].rename(ticker)
    nominal_prices = pd.concat(nominal_columns.values(), axis=1, join="outer").reindex(prices.index)
    if nominal_prices.isna().any().any():
        missing = nominal_prices.columns[nominal_prices.isna().any()].tolist()
        raise NdxCardinalityRealSmokeError(f"nominal execution price coverage missing: {missing}")
    target_frame = pd.read_csv(target_path, usecols=["Date", "Close"])
    target_frame["Date"] = pd.to_datetime(target_frame["Date"], errors="coerce").dt.normalize()
    target_frame["Close"] = pd.to_numeric(target_frame["Close"], errors="coerce")
    target_prices = target_frame.set_index("Date")["Close"].sort_index().reindex(prices.index).ffill()
    valid = target_prices.notna()
    prices = prices.loc[valid]
    target_prices = target_prices.loc[valid]
    returns = prices.pct_change(fill_method=None).dropna()
    target_returns = target_prices.pct_change(fill_method=None).reindex(returns.index)
    if target_returns.isna().any() or len(returns) < int(args.fit_days) + int(args.window_days):
        raise NdxCardinalityRealSmokeError("aligned training history is too short")

    prior_prices = {}
    liquidity = {}
    for ticker in universe["ticker"].astype(str):
        prior = bars[ticker].loc[bars[ticker].index < selection]
        prior_prices[ticker] = float(prior["Close"].iloc[-1])
        liquidity[ticker] = float((prior["Close"] * prior["Volume"]).tail(63).median())
    search_universe = universe[["ticker", "security_id", "issuer_id", "risk_chain"]].drop_duplicates("ticker").copy()
    search_universe["synthetic_price"] = search_universe["ticker"].map(prior_prices)
    search_universe["median_dollar_volume_usd"] = search_universe["ticker"].map(liquidity)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    caps = {ticker: float(state["symbols"][ticker]["cap_total"]) for ticker in INCUMBENT}
    cap_total = sum(caps.values())
    incumbent_weights = {ticker: value / cap_total for ticker, value in caps.items()}
    smoke = spec["synthetic_smoke_contract"]
    effective_portfolio_cash = (
        float(args.portfolio_cash_usd)
        if args.portfolio_cash_usd is not None else float(smoke["portfolio_cash_usd"])
    )
    search_kwargs = dict(
        holding_count=holding_count,
        exact_limit=int(spec["search_contract"]["exact_enumeration_max_feasible_combinations"]),
        beam_width=int(args.beam_width), window_days=int(args.window_days),
        step_days=int(args.step_days), transaction_cost_bps=float(args.transaction_cost_bps),
        fit_days=int(args.fit_days), shrinkage_intensity=float(smoke["fixed_shrinkage_intensity"]),
        max_single_weight=float(smoke["max_single_weight"]),
        min_single_weight=float(smoke["min_single_weight"]),
        top_weight_cap=float(smoke["top_weight_cap"]),
        minimum_effective_n_ratio=float(smoke["minimum_effective_n_ratio"]),
        risk_chain_top1_cap=float(smoke["risk_chain_top1_cap"]),
        turnover_anchor_strength=float(smoke["turnover_anchor_strength"]),
        portfolio_cash_usd=effective_portfolio_cash,
        minimum_cash_buffer_usd=float(smoke["minimum_cash_buffer_usd"]),
        minimum_median_dollar_volume_usd=float(smoke["minimum_median_dollar_volume_usd"]),
        incumbent_weights=incumbent_weights,
        execution_prices=nominal_prices,
    )
    second_stage_shortlist = pd.DataFrame()
    candidate_replay_source = None
    if args.candidate_sets_file:
        candidate_sets_path = _resolve(args.candidate_sets_file)
        assert replay_source_frame is not None
        replay_rows = replay_source_frame.loc[
            replay_source_frame["universe_track"].astype(str).eq(track)
            & replay_source_frame["selection_date"].astype(str).eq(selection.date().isoformat())
            & pd.to_numeric(replay_source_frame["holding_count"], errors="coerce").isin(requested_holding_counts)
        ].copy()
        replay_rows = replay_rows.drop_duplicates(["tickers", "weight_spec"], keep="first")
        if replay_rows.empty:
            raise NdxCardinalityRealSmokeError("candidate replay source has no requested coordinate rows")
        available = set(search_universe["ticker"].astype(str))
        evaluated = []
        for replay_row in replay_rows.to_dict("records"):
            combo = tuple(sorted(item for item in str(replay_row["tickers"]).split(";") if item))
            row_holding_count = int(replay_row["holding_count"])
            if len(combo) != row_holding_count or not set(combo).issubset(available):
                raise NdxCardinalityRealSmokeError(
                    f"candidate replay ticker set is invalid for coordinate: {combo}"
                )
            evaluated.append(evaluate_synthetic_portfolio(
                combo, search_universe, returns, target_returns, INCUMBENT,
                window_days=int(args.window_days), step_days=int(args.step_days),
                transaction_cost_bps=float(args.transaction_cost_bps),
                weight_spec=str(replay_row["weight_spec"]), fit_days=int(args.fit_days),
                shrinkage_intensity=float(smoke["fixed_shrinkage_intensity"]),
                max_single_weight=float(smoke["max_single_weight"]),
                min_single_weight=float(smoke["min_single_weight"]),
                top_weight_cap=float(smoke["top_weight_cap"]),
                minimum_effective_n_ratio=float(smoke["minimum_effective_n_ratio"]),
                risk_chain_top1_cap=float(smoke["risk_chain_top1_cap"]),
                turnover_anchor_strength=float(smoke["turnover_anchor_strength"]),
                portfolio_cash_usd=effective_portfolio_cash,
                minimum_cash_buffer_usd=float(smoke["minimum_cash_buffer_usd"]),
                minimum_median_dollar_volume_usd=float(smoke["minimum_median_dollar_volume_usd"]),
                incumbent_weights=incumbent_weights,
                execution_prices=nominal_prices,
            ))
        candidates = pd.DataFrame(evaluated).sort_values("portfolio_id", kind="stable").reset_index(drop=True)
        candidates = _assign_replay_frontiers(candidates)
        candidates["search_mode"] = "LOCKED_CANDIDATE_CAPITAL_REPLAY"
        candidates["search_exhaustive"] = False
        search_audit = {
            "holding_count": holding_count if holding_count > 0 else "VARIABLE",
            "holding_counts": requested_holding_counts,
            "theoretical_feasible_portfolios": None,
            "liquidity_feasible_portfolios": None,
            "liquidity_pruned_portfolios": None,
            "expanded_nodes": 0,
            "pruned_nodes": 0,
            "fully_evaluated_portfolios": len(candidates),
            "evaluated_security_sets": int(candidates["tickers"].nunique()),
            "weight_specification_count": int(candidates["weight_spec"].nunique()),
            "evaluation_rows": len(candidates),
            "unevaluated_feasible_portfolios": None,
            "search_mode": "LOCKED_CANDIDATE_CAPITAL_REPLAY",
            "search_exhaustive": False,
            "optimality_claim_allowed": False,
            "result_label": "REAL_TRAINING_CAPITAL_REPLAY_SHORTLIST",
        }
        candidate_replay_source = {
            "path": candidate_sets_path.as_posix(),
            "sha256": file_sha256(candidate_sets_path),
            "coordinate_source_rows": len(replay_rows),
            "target_portfolio_cash_usd": effective_portfolio_cash,
            "source_batches": sorted(replay_rows["source_batch"].astype(str).unique().tolist())
            if "source_batch" in replay_rows else [],
        }
    elif args.search_method == "two_stage":
        real_search = spec["real_training_search_contract"]
        candidates, second_stage_shortlist, search_audit = search_two_stage_cardinality(
            search_universe, returns, target_returns, INCUMBENT,
            second_stage_per_frontier=int(real_search["second_stage_per_frontier_security_sets"]),
            second_stage_weight_specs=tuple(real_search["second_stage_weight_specifications"]),
            **search_kwargs,
        )
    else:
        candidates, search_audit = search_synthetic_cardinality(
            search_universe, returns, target_returns, INCUMBENT,
            weight_specs=tuple(smoke["weight_specifications"]), **search_kwargs,
        )
    candidates = _attach_point_in_time_identity_columns(candidates, search_universe)
    candidates.insert(0, "universe_track", track)
    candidates.insert(1, "selection_date", selection.date().isoformat())
    candidates.insert(2, "decision_data_end", returns.index.max().date().isoformat())
    candidates["result_role"] = "REAL_POINT_IN_TIME_TRAINING_DISCOVERY_ONLY"
    candidates["promotion_allowed"] = False
    execution_modes = sorted(candidates["whole_lot_execution_mode"].astype(str).unique())
    if execution_modes != ["CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_REAL_CLOSES"]:
        raise NdxCardinalityRealSmokeError("continuous whole-lot execution audit is missing")
    if not candidate_replay_source:
        search_audit["result_label"] = (
            "REAL_TRAINING_EXACT_FRONTIER"
            if bool(search_audit["search_exhaustive"])
            else "REAL_TRAINING_CURRENT_SEARCHED_FRONTIER"
        )
    frontier_columns = ["frontier_tags", "constrained_frontier_tags"]
    if candidate_replay_source:
        frontier_columns.extend([
            "cross_cardinality_frontier_tags",
            "cross_cardinality_constrained_frontier_tags",
        ])
    frontier_mask = candidates[frontier_columns].ne("").any(axis=1)
    frontiers = candidates.loc[frontier_mask].sort_values(
        ["declared_constraints_passed", "target_012922_distance", "return_p10"],
        ascending=[False, True, False],
    )

    output.mkdir(parents=True, exist_ok=True)
    candidate_path = output / "training_candidates.csv"
    frontier_path = output / "training_frontiers.csv"
    inventory_path = output / "price_input_inventory.csv"
    shortlist_path = output / "second_stage_shortlist.csv"
    lifecycle_coverage_path = output / "lifecycle_coverage.csv"
    workbook_path = output / "ndx_cardinality_real_training_smoke.xlsx"
    _atomic_csv(candidates, candidate_path)
    _atomic_csv(frontiers, frontier_path)
    _atomic_csv(inventory, inventory_path)
    _atomic_csv(lifecycle_coverage, lifecycle_coverage_path)
    if not second_stage_shortlist.empty:
        _atomic_csv(second_stage_shortlist, shortlist_path)
    scope_summary = pd.DataFrame([
        {"项目": "组合计算范围", "值": "汇丰100%美股股票风险仓"},
        {"项目": "比较基线", "值": "原八只股票按state.cap_total归一化"},
        {"项目": "SGOV处理", "值": "排除出目标函数、候选权重和绩效比较"},
        {"项目": "外部指数底仓", "值": "约占全资产一半，仅作架构背景，不并入回测"},
        {"项目": "策略外个人AVGO", "值": "不并入比较基线"},
    ])
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            scope_summary.to_excel(writer, sheet_name="口径摘要", index=False)
            frontiers.to_excel(writer, sheet_name="真实训练前沿", index=False)
            candidates.to_excel(writer, sheet_name="全部训练候选", index=False)
            search_universe.to_excel(writer, sheet_name="点时退化候选池", index=False)
            inventory.to_excel(writer, sheet_name="价格输入", index=False)
            lifecycle_coverage.to_excel(writer, sheet_name="生命周期覆盖", index=False)
            if not second_stage_shortlist.empty:
                second_stage_shortlist.to_excel(writer, sheet_name="二阶段结构短名单", index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()

    protected_after = {"config": file_sha256(config_path), "state": file_sha256(state_path)}
    if protected_after != protected_before:
        raise NdxCardinalityRealSmokeError("protected config/state hash changed")
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_real_training_smoke",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "TRAINING_DISCOVERY_ONLY_NOT_ADMISSION",
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "universe_mode": "degraded_research",
        "universe_track": track,
        "selection_date": selection.date().isoformat(),
        "holding_count": holding_count,
        "holding_counts": requested_holding_counts,
        "search_method": args.search_method,
        "candidate_replay_mode": bool(candidate_replay_source),
        "candidate_replay_source": candidate_replay_source,
        "frontier_comparison_scope": (
            "WITHIN_CARDINALITY_AND_CROSS_CARDINALITY"
            if candidate_replay_source else "WITHIN_REQUESTED_CARDINALITY"
        ),
        "portfolio_cash_usd": effective_portfolio_cash,
        "excluded_for_history": excluded_for_history,
        "candidate_security_count": len(search_universe),
        "candidate_issuer_count": int(search_universe["issuer_id"].nunique()),
        "training_return_rows": len(returns),
        "training_end": returns.index.max().date().isoformat(),
        "fit_strictly_before_selection": bool(returns.index.max() < selection),
        "portfolio_scope": spec["result_contract"]["portfolio_scope"],
        "safe_leg_role": spec["result_contract"]["safe_leg_role"],
        "external_index_context": spec["result_contract"]["external_index_context"],
        "incumbent_role": spec["result_contract"]["incumbent_role"],
        "personal_off_strategy_positions_included": False,
        "return_data_read": True,
        "selection_date_or_later_returns_read": False,
        "portfolio_returns_calculated": True,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "protected_hashes_unchanged": True,
        "incumbent_weights_source": "state.symbols.cap_total_normalized",
        "incumbent_weights": incumbent_weights,
        "whole_lot_execution_mode": execution_modes[0],
        "whole_lot_execution_price_basis": "unadjusted_nominal_trade_price",
        "adjusted_return_prices_used_for_whole_lot_shares": False,
        "selection_date_or_later_execution_prices_used": False,
        "whole_lot_shares_and_cash_carried_between_rebalances": True,
        "whole_lot_transaction_costs_deducted_from_cash": True,
        "whole_lot_constraints_checked_daily": True,
        "eligible_cross_ticker_lifecycle_security_count": int(inventory["cross_ticker_stitched"].astype(bool).sum()),
        "stitchable_noneligible_lifecycle_control_count": int(
            lifecycle_coverage["status"].eq("NOMINAL_CACHE_STITCHABLE_CONTROL_NOT_ELIGIBLE_COORDINATE").sum()
        ),
        "search_audit": search_audit,
        "inputs": {
            "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
            "input_readiness_manifest": {"path": readiness_manifest_path.as_posix(), "sha256": file_sha256(readiness_manifest_path)},
            "security_lifecycle": {"path": lifecycle_path.as_posix(), "sha256": file_sha256(lifecycle_path)},
            "execution_price_manifest": {"path": execution_price_manifest_path.as_posix(), "sha256": file_sha256(execution_price_manifest_path)},
            "execution_price_inventory": {"path": execution_inventory_path.as_posix(), "sha256": file_sha256(execution_inventory_path)},
            "membership_audit": {"path": membership_audit_path.as_posix(), "sha256": file_sha256(membership_audit_path)},
            "identity_audit": {"path": identity_audit_path.as_posix(), "sha256": file_sha256(identity_audit_path)},
            "job_audit": {"path": job_audit_path.as_posix(), "sha256": file_sha256(job_audit_path)},
            "target_nav": {"path": target_path.as_posix(), "sha256": file_sha256(target_path)},
            "state": {"path": state_path.as_posix(), "sha256": protected_before["state"]},
            "config": {"path": config_path.as_posix(), "sha256": protected_before["config"]},
        },
        "artifacts": {
            "candidates": {"path": candidate_path.as_posix(), "rows": len(candidates), "sha256": file_sha256(candidate_path)},
            "frontiers": {"path": frontier_path.as_posix(), "rows": len(frontiers), "sha256": file_sha256(frontier_path)},
            "price_inventory": {"path": inventory_path.as_posix(), "rows": len(inventory), "sha256": file_sha256(inventory_path)},
            "lifecycle_coverage": {"path": lifecycle_coverage_path.as_posix(), "rows": len(lifecycle_coverage), "sha256": file_sha256(lifecycle_coverage_path)},
            "workbook": {"path": workbook_path.as_posix(), "rows": None, "sha256": file_sha256(workbook_path)},
        },
    }
    if not second_stage_shortlist.empty:
        payload["artifacts"]["second_stage_shortlist"] = {
            "path": shortlist_path.as_posix(), "rows": len(second_stage_shortlist),
            "sha256": file_sha256(shortlist_path),
        }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="不固定持仓数真实点时训练 smoke")
    parser.add_argument("--track", choices=["strict_technology", "technology_plus_adjacent"], default="strict_technology")
    parser.add_argument("--selection-date", default="2024-06-03")
    parser.add_argument("--holding-count", type=int, default=2)
    parser.add_argument("--candidate-sets-file", default="")
    parser.add_argument("--source-batch", default="")
    parser.add_argument("--portfolio-cash-usd", type=float)
    parser.add_argument("--spec", default="config/ndx_cardinality_discovery_v1.yaml")
    parser.add_argument("--input-readiness-manifest", default="data/cache/research/ndx_variable_cardinality_input_readiness_v2/manifest.json")
    parser.add_argument("--discovery-manifest", default="data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json")
    parser.add_argument("--security-lifecycle", default="config/ndx_security_lifecycle.yaml")
    parser.add_argument("--execution-price-manifest", default="data/cache/research/ndx_cardinality_execution_prices_all_ready_v1/manifest.json")
    parser.add_argument("--return-cache-dir", default="data/cache")
    parser.add_argument("--target-nav", default="data/cache/funds/012922.csv")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_variable_cardinality_real_smoke_v1")
    parser.add_argument("--minimum-price-rows-before-selection", type=int, default=252)
    parser.add_argument("--training-lookback-days", type=int, default=504)
    parser.add_argument("--fit-days", type=int, default=126)
    parser.add_argument("--window-days", type=int, default=126)
    parser.add_argument("--step-days", type=int, default=21)
    parser.add_argument("--beam-width", type=int, default=64)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--search-method", choices=["two_stage", "full"], default="two_stage")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = run(args)
    except Exception as exc:
        print(f"真实点时训练 smoke 失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    audit = payload["search_audit"]
    print(
        "真实点时训练 smoke 完成 | "
        f"track={payload['universe_track']} | date={payload['selection_date']} | "
        f"k={payload['holding_count']} | evaluated={audit['evaluation_rows']} | "
        "promotion_allowed=False"
    )
    print(f"Manifest: {_resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
