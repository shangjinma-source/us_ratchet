r"""Enumerate real point-in-time local changes around the incumbent portfolio.

PowerShell/PyCharm:
    python -B scripts\ndx_local_challenger_search.py
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_local_challenger import evaluate_fixed_weight_challenger, normalize_weights, tag_local_frontiers
from core.helpers import atomic_write_text
from data.versioning import file_sha256
from scripts.ndx_cardinality_real_smoke import INCUMBENT, _load_bars, _verified_csv


class NdxLocalChallengerSearchError(ValueError):
    pass


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run(args: argparse.Namespace) -> dict:
    selection = pd.Timestamp(args.selection_date).normalize()
    readiness_path = _resolve(args.input_readiness_manifest)
    discovery_path = _resolve(args.discovery_manifest)
    target_path = _resolve(args.target_nav)
    state_path = _resolve(args.state)
    config_path = _resolve(args.config)
    price_root = _resolve(args.return_cache_dir)
    output = _resolve(args.output_dir)
    protected_before = {"config": file_sha256(config_path), "state": file_sha256(state_path)}

    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    if readiness.get("manifest_type") != "ndx_cardinality_real_input_readiness":
        raise NdxLocalChallengerSearchError("unexpected input readiness manifest")
    membership_audit, membership_path = _verified_csv(readiness, "membership_readiness")
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    artifact = (discovery.get("artifacts") or {}).get("eligible_securities") or {}
    members_path = Path(str(artifact.get("path") or ""))
    if not members_path.is_absolute() or file_sha256(members_path) != artifact.get("sha256"):
        raise NdxLocalChallengerSearchError("point-in-time membership artifact mismatch")
    members = pd.read_csv(members_path, low_memory=False)
    date_text = selection.date().isoformat()
    ready_ids = membership_audit.loc[
        membership_audit["universe_track"].eq(args.track)
        & membership_audit["selection_date"].eq(date_text)
        & membership_audit["input_ready"].astype(bool),
        "security_id",
    ]
    universe = members.loc[
        members["universe_track"].eq(args.track)
        & members["selection_date"].eq(date_text)
        & members["membership_window_eligible"].astype(bool)
        & members["security_id"].isin(set(ready_ids.astype(str)))
    ][["ticker", "issuer_id"]].drop_duplicates("ticker")
    if universe.empty:
        raise NdxLocalChallengerSearchError("point-in-time local candidate universe is empty")

    all_tickers = sorted(set(universe["ticker"].astype(str)) | set(INCUMBENT))
    bars = {ticker: _load_bars(price_root / f"{ticker}.csv") for ticker in all_tickers}
    minimum_rows = int(args.minimum_price_rows_before_selection)
    candidate_tickers = sorted(
        ticker for ticker in universe["ticker"].astype(str)
        if len(bars[ticker].loc[bars[ticker].index < selection]) >= minimum_rows
    )
    price_series = {
        ticker: bars[ticker].loc[bars[ticker].index < selection, "Close"].rename(ticker)
        for ticker in sorted(set(candidate_tickers) | set(INCUMBENT))
    }
    prices = pd.concat(price_series.values(), axis=1, join="inner").dropna().tail(
        int(args.training_lookback_days) + 1
    )
    target_frame = pd.read_csv(target_path, usecols=["Date", "Close"])
    target_frame["Date"] = pd.to_datetime(target_frame["Date"], errors="coerce").dt.normalize()
    target_frame["Close"] = pd.to_numeric(target_frame["Close"], errors="coerce")
    target_prices = target_frame.set_index("Date")["Close"].sort_index().reindex(prices.index).ffill()
    valid = target_prices.notna()
    prices = prices.loc[valid]
    target_prices = target_prices.loc[valid]
    returns = prices.pct_change(fill_method=None).dropna()
    target_returns = target_prices.pct_change(fill_method=None).reindex(returns.index)
    if target_returns.isna().any() or returns.index.max() >= selection:
        raise NdxLocalChallengerSearchError("training alignment is invalid or future-contaminated")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    incumbent_weights = normalize_weights({
        ticker: float(state["symbols"][ticker]["cap_total"]) for ticker in INCUMBENT
    })
    issuer_by_ticker = universe.set_index("ticker")["issuer_id"].astype(str).to_dict()
    for ticker in INCUMBENT:
        issuer_by_ticker.setdefault(ticker, f"INCUMBENT:{ticker}")
    # GOOG and GOOGL are two securities of the same issuer.
    if "GOOG" in issuer_by_ticker and "GOOGL" in issuer_by_ticker:
        issuer_by_ticker["GOOGL"] = issuer_by_ticker["GOOG"]

    operations: list[tuple[str, tuple[str, ...], tuple[str, ...], dict[str, float]]] = []
    incumbent_issuers = {issuer_by_ticker[ticker] for ticker in INCUMBENT}
    additions = [
        ticker for ticker in candidate_tickers
        if ticker not in incumbent_weights and issuer_by_ticker[ticker] not in incumbent_issuers
    ]
    for ticker in additions:
        for sleeve in args.add_sleeve:
            weights = {name: weight * (1.0 - sleeve) for name, weight in incumbent_weights.items()}
            weights[ticker] = sleeve
            operations.append((f"ADD_{sleeve:.3f}", tuple(), (ticker,), weights))
    for removed in INCUMBENT:
        retained = {ticker: weight for ticker, weight in incumbent_weights.items() if ticker != removed}
        retained_issuers = {issuer_by_ticker[ticker] for ticker in retained}
        for added in additions:
            if issuer_by_ticker[added] in retained_issuers:
                continue
            weights = dict(retained)
            weights[added] = incumbent_weights[removed]
            operations.append(("SINGLE_REPLACE", (removed,), (added,), weights))
    for removed_pair in itertools.combinations(INCUMBENT, 2):
        retained = {ticker: weight for ticker, weight in incumbent_weights.items() if ticker not in removed_pair}
        retained_issuers = {issuer_by_ticker[ticker] for ticker in retained}
        feasible_additions = [ticker for ticker in additions if issuer_by_ticker[ticker] not in retained_issuers]
        for added_pair in itertools.combinations(feasible_additions, 2):
            if issuer_by_ticker[added_pair[0]] == issuer_by_ticker[added_pair[1]]:
                continue
            for assignment in (added_pair, tuple(reversed(added_pair))):
                weights = dict(retained)
                for removed, added in zip(removed_pair, assignment):
                    weights[added] = incumbent_weights[removed]
                operations.append(("DOUBLE_REPLACE", tuple(removed_pair), tuple(assignment), weights))
    for count in (1, 2):
        for removed in itertools.combinations(INCUMBENT, count):
            weights = {ticker: weight for ticker, weight in incumbent_weights.items() if ticker not in removed}
            operations.append((f"DROP_{count}", tuple(removed), tuple(), weights))

    rows = [evaluate_fixed_weight_challenger(
        operation=operation, removed=removed, added=added, weights=weights,
        returns=returns, target=target_returns, incumbent_weights=incumbent_weights,
        fit_days=int(args.fit_days), window_days=int(args.window_days), step_days=int(args.step_days),
        transaction_cost_bps=float(args.transaction_cost_bps),
    ) for operation, removed, added, weights in operations]
    candidates = tag_local_frontiers(pd.DataFrame(rows))
    candidates.insert(0, "universe_track", args.track)
    candidates.insert(1, "selection_date", date_text)
    frontiers = candidates.loc[candidates["frontier_tags"].ne("")].sort_values(
        ["operation", "target_012922_distance", "return_p10"], ascending=[True, True, False]
    )
    output.mkdir(parents=True, exist_ok=True)
    candidates_path = output / "local_challengers.csv"
    frontiers_path = output / "local_frontiers.csv"
    workbook_path = output / "ndx_local_challengers.xlsx"
    _atomic_csv(candidates, candidates_path)
    _atomic_csv(frontiers, frontiers_path)
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            frontiers.to_excel(writer, sheet_name="local_frontiers", index=False)
            candidates.to_excel(writer, sheet_name="all_local_challengers", index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    if {"config": file_sha256(config_path), "state": file_sha256(state_path)} != protected_before:
        raise NdxLocalChallengerSearchError("protected config/state hash changed")
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_local_challenger_training_search",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "TRAINING_DISCOVERY_ONLY_NOT_ADMISSION",
        "selection_date": date_text,
        "universe_track": args.track,
        "candidate_tickers": candidate_tickers,
        "new_candidate_tickers": additions,
        "operation_rows": candidates["operation"].value_counts().sort_index().to_dict(),
        "evaluation_rows": len(candidates),
        "training_return_rows": len(returns),
        "training_end": returns.index.max().date().isoformat(),
        "selection_date_or_later_returns_read": False,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "protected_hashes_unchanged": True,
        "inputs": {
            "input_readiness_manifest": {"path": readiness_path.as_posix(), "sha256": file_sha256(readiness_path)},
            "membership_readiness": {"path": membership_path.as_posix(), "sha256": file_sha256(membership_path)},
            "discovery_manifest": {"path": discovery_path.as_posix(), "sha256": file_sha256(discovery_path)},
            "target_nav": {"path": target_path.as_posix(), "sha256": file_sha256(target_path)},
            "state": {"path": state_path.as_posix(), "sha256": protected_before["state"]},
            "config": {"path": config_path.as_posix(), "sha256": protected_before["config"]},
        },
        "artifacts": {
            "candidates": {"path": candidates_path.as_posix(), "rows": len(candidates), "sha256": file_sha256(candidates_path)},
            "frontiers": {"path": frontiers_path.as_posix(), "rows": len(frontiers), "sha256": file_sha256(frontiers_path)},
            "workbook": {"path": workbook_path.as_posix(), "sha256": file_sha256(workbook_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="真实点时局部组合 challenger 穷举")
    parser.add_argument("--track", default="strict_technology", choices=["strict_technology", "technology_plus_adjacent"])
    parser.add_argument("--selection-date", default="2024-06-03")
    parser.add_argument("--input-readiness-manifest", default="data/cache/research/ndx_variable_cardinality_input_readiness_v1/manifest.json")
    parser.add_argument("--discovery-manifest", default="data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json")
    parser.add_argument("--return-cache-dir", default="data/cache")
    parser.add_argument("--target-nav", default="data/cache/funds/012922.csv")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_local_challenger_training_v1")
    parser.add_argument("--minimum-price-rows-before-selection", type=int, default=252)
    parser.add_argument("--training-lookback-days", type=int, default=504)
    parser.add_argument("--fit-days", type=int, default=126)
    parser.add_argument("--window-days", type=int, default=126)
    parser.add_argument("--step-days", type=int, default=21)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--add-sleeve", type=float, action="append", default=None)
    args = parser.parse_args()
    args.add_sleeve = args.add_sleeve or [0.025, 0.05, 0.10]
    if any(not 0 < sleeve < 1 for sleeve in args.add_sleeve):
        parser.error("--add-sleeve must be in (0,1)")
    return args


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"局部 challenger 搜索失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"局部 challenger 搜索完成 | rows={payload['evaluation_rows']} | "
        f"operations={payload['operation_rows']} | promotion_allowed=False"
    )
    print(f"Manifest: {payload['artifacts']['candidates']['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
