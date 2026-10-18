r"""Audit frozen local challengers under $5k whole-share and risk-chain rules."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cardinality_discovery import load_discovery_spec, validate_discovery_spec
from backtest.ndx_incumbent_pit_attribution import INCUMBENT_TICKERS
from backtest.ndx_local_action_execution import evaluate_local_action_execution
from core.helpers import atomic_write_text
from data.versioning import file_sha256
from scripts.ndx_cardinality_frontier_attribution import parse_weight_string
from scripts.ndx_challenger_master_table import build_local_master_rows


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


def _verified_artifact(manifest: dict, key: str) -> tuple[Path, pd.DataFrame]:
    artifact = (manifest.get("artifacts") or {}).get(key) or {}
    path = Path(str(artifact.get("path") or ""))
    if not path.is_absolute() or not path.is_file() or file_sha256(path) != artifact.get("sha256"):
        raise ValueError(f"artifact mismatch: {key}")
    frame = pd.read_csv(path, low_memory=False)
    if len(frame) != int(artifact.get("rows") or -1):
        raise ValueError(f"artifact row count changed: {key}")
    return path, frame


def _prior_close(path: Path, selection_date: date) -> tuple[str, float]:
    """Read only rows before selection; stop at the first later-or-equal row."""
    latest_date = ""
    latest_close = 0.0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            row_date = date.fromisoformat(str(row.get("Date") or "")[:10])
            if row_date >= selection_date:
                break
            close = float(row.get("Close") or 0.0)
            if close <= 0:
                raise ValueError(f"non-positive prior close: {path}")
            latest_date = row_date.isoformat()
            latest_close = close
    if not latest_date:
        raise ValueError(f"selection prior close missing: {path}")
    return latest_date, latest_close


def run(args: argparse.Namespace) -> dict:
    local_stability_manifest_path = _resolve(args.local_stability_manifest)
    local, _, local_stability_path, local_inputs = build_local_master_rows(
        local_stability_manifest_path,
    )
    if local.empty:
        raise ValueError("local stability bundle has no selected actions")

    pit_manifest_path = _resolve(args.incumbent_pit_manifest)
    pit_manifest = json.loads(pit_manifest_path.read_text(encoding="utf-8"))
    if pit_manifest.get("manifest_type") != "ndx_incumbent_pit_execution_attribution":
        raise ValueError("unexpected incumbent PIT attribution manifest")
    if pit_manifest.get("historical_backfill_created") is not False:
        raise ValueError("incumbent PIT input created taxonomy backfill")
    pit_path, pit = _verified_artifact(pit_manifest, "projection")

    discovery_manifest_path = _resolve(args.discovery_manifest)
    discovery_manifest = json.loads(discovery_manifest_path.read_text(encoding="utf-8"))
    members_path, members = _verified_artifact(discovery_manifest, "eligible_securities")
    selection_text = str(args.selection_date)
    selection = date.fromisoformat(selection_text)
    track = str(args.universe_track)
    member_rows = members.loc[
        members["selection_date"].astype(str).eq(selection_text)
        & members["universe_track"].astype(str).eq(track)
    ].copy()
    member_rows = member_rows.drop_duplicates("ticker")
    if member_rows["ticker"].duplicated().any():
        raise ValueError("candidate PIT metadata is ambiguous")
    metadata = member_rows.set_index("ticker")[["security_id", "issuer_id", "risk_chain", "evidence_available_date"]].to_dict("index")
    incumbent_rows = pit.loc[pit["selection_date"].astype(str).eq(selection_text)].copy()
    if set(incumbent_rows["ticker"]) != set(INCUMBENT_TICKERS) or len(incumbent_rows) != 8:
        raise ValueError("incumbent PIT metadata is incomplete")
    for row in incumbent_rows.to_dict("records"):
        metadata[row["ticker"]] = {
            "security_id": row["security_id"], "issuer_id": row["issuer_id"],
            "risk_chain": row["risk_chain"], "evidence_available_date": row["evidence_available_date"],
        }

    spec_path = _resolve(args.spec)
    spec = load_discovery_spec(spec_path)
    validate_discovery_spec(spec)
    contract = spec["synthetic_smoke_contract"]
    cash = float(contract["portfolio_cash_usd"])
    buffer = float(contract["minimum_cash_buffer_usd"])
    parameters = {
        "cash": cash,
        "minimum_cash_buffer": buffer,
        # The frozen local-action search declared top-1/top-3 constraints only.
        # Do not retrofit the variable-cardinality minimum-weight/effective-N
        # admission rules onto already-selected local actions.
        "min_single_weight": 0.0,
        "max_single_weight": float(contract["max_single_weight"]),
        "top3_cap": float(contract["top_weight_cap"]),
        "minimum_effective_n_ratio": 0.0,
        "risk_chain_top1_cap": float(contract["risk_chain_top1_cap"]),
    }

    price_root = _resolve(args.price_root)
    price_cache: dict[str, tuple[str, float, Path, str]] = {}
    summaries = []
    positions = []
    for candidate in local.to_dict("records"):
        weights = parse_weight_string(candidate["candidate_weights"])
        prices = {}
        chains = {}
        for ticker in weights:
            if ticker not in metadata:
                raise ValueError(f"PIT metadata missing for local action: {ticker}")
            if str(metadata[ticker]["evidence_available_date"]) > selection_text:
                raise ValueError(f"future candidate evidence: {ticker}")
            if ticker not in price_cache:
                price_path = price_root / f"{ticker}.csv"
                digest = file_sha256(price_path)
                prior_date, prior_close = _prior_close(price_path, selection)
                price_cache[ticker] = (prior_date, prior_close, price_path, digest)
            prices[ticker] = price_cache[ticker][1]
            chains[ticker] = str(metadata[ticker]["risk_chain"])
        result = evaluate_local_action_execution(weights, prices, chains, **parameters)
        key = f"{candidate['candidate_id']}|{candidate['selection_role']}"
        shares_text = ";".join(f"{ticker}:{result['shares'][ticker]}" for ticker in sorted(weights))
        status = "WHOLE_LOT_REPLAY_COMPLIANT" if result["constraints_passed"] else "WHOLE_LOT_REPLAY_NONCOMPLIANT"
        summaries.append({
            "execution_key": key,
            "candidate_id": candidate["candidate_id"],
            "selection_role": candidate["selection_role"],
            "action_scope": candidate["action_scope"],
            "selection_date": selection_text,
            "candidate_tickers": candidate["candidate_tickers"],
            "candidate_weights": candidate["candidate_weights"],
            "execution_status": status,
            "execution_constraints_passed": result["constraints_passed"],
            "execution_constraint_failures": result["constraint_failures"],
            "whole_lot_shares": shares_text,
            "execution_invested_usd": result["invested_usd"],
            "execution_residual_cash_usd": result["residual_cash_usd"],
            "execution_deployment_ratio": result["deployment_ratio"],
            "execution_risky_weight_l1_drift": result["risky_weight_l1_drift"],
            "execution_risky_weight_max_abs_drift": result["risky_weight_max_abs_drift"],
            "execution_actual_top1_weight": result["actual_top1_weight"],
            "execution_actual_top3_weight": result["actual_top3_weight"],
            "execution_actual_effective_n": result["actual_effective_n"],
            "execution_actual_risk_chain_top1_weight": result["actual_risk_chain_top1_weight"],
            "risk_chain_weights": ";".join(f"{chain}:{weight:.10f}" for chain, weight in sorted(result["risk_chain_weights"].items())),
        })
        for ticker in sorted(weights):
            prior_date, prior_close, _, _ = price_cache[ticker]
            positions.append({
                "execution_key": key, "candidate_id": candidate["candidate_id"],
                "selection_role": candidate["selection_role"], "ticker": ticker,
                "security_id": metadata[ticker]["security_id"], "issuer_id": metadata[ticker]["issuer_id"],
                "risk_chain": chains[ticker], "target_weight": weights[ticker],
                "prior_close_date": prior_date, "prior_close": prior_close,
                "whole_shares": result["shares"][ticker],
                "whole_lot_notional_usd": result["notionals"][ticker],
                "actual_risky_weight": result["actual_risky_weights"][ticker],
            })

    summary = pd.DataFrame(summaries)
    position = pd.DataFrame(positions)
    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary_path = output / "local_action_execution_audit.csv"
    position_path = output / "local_action_execution_positions.csv"
    _atomic_csv(summary, summary_path)
    _atomic_csv(position, position_path)
    price_inputs = [{"ticker": ticker, "path": item[2].as_posix(), "sha256": item[3]} for ticker, item in sorted(price_cache.items())]
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_local_action_whole_lot_execution_audit",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "POST_SELECTION_EXECUTION_ATTRIBUTION_ONLY_NOT_RESELECTION_OR_ADMISSION",
        "selection_date": selection_text,
        "universe_track": track,
        "candidate_count": len(summary),
        "compliant_count": int(summary["execution_constraints_passed"].sum()),
        "noncompliant_count": int((~summary["execution_constraints_passed"]).sum()),
        "portfolio_cash_usd": cash,
        "minimum_cash_buffer_usd": buffer,
        "constraint_contract": "LOCAL_DECLARED_TOP1_TOP3_PLUS_WHOLE_LOT_CASH_BUFFER_AND_RISK_CHAIN",
        "variable_cardinality_min_single_weight_applied": False,
        "variable_cardinality_effective_n_ratio_applied": False,
        "candidate_selection_changed": False,
        "selection_date_or_later_price_values_used": False,
        "historical_taxonomy_backfill_used": False,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "inputs": {
            "local_stability_manifest": {"path": local_stability_manifest_path.as_posix(), "sha256": file_sha256(local_stability_manifest_path)},
            "local_stability": {"path": local_stability_path.as_posix(), "sha256": file_sha256(local_stability_path)},
            "local_candidates": local_inputs,
            "incumbent_pit_manifest": {"path": pit_manifest_path.as_posix(), "sha256": file_sha256(pit_manifest_path)},
            "incumbent_pit": {"path": pit_path.as_posix(), "sha256": file_sha256(pit_path)},
            "discovery_manifest": {"path": discovery_manifest_path.as_posix(), "sha256": file_sha256(discovery_manifest_path)},
            "members": {"path": members_path.as_posix(), "sha256": file_sha256(members_path)},
            "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
            "prices": price_inputs,
        },
        "artifacts": {
            "summary": {"path": summary_path.as_posix(), "rows": len(summary), "sha256": file_sha256(summary_path)},
            "positions": {"path": position_path.as_posix(), "rows": len(position), "sha256": file_sha256(position_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="局部候选的整股与风险链执行回放")
    parser.add_argument("--local-stability-manifest", default="data/cache/research/ndx_local_challenger_stability_v1/manifest.json")
    parser.add_argument("--incumbent-pit-manifest", default="data/cache/research/ndx_incumbent_pit_attribution_v1/manifest.json")
    parser.add_argument("--discovery-manifest", default="data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json")
    parser.add_argument("--spec", default="config/ndx_cardinality_discovery_v1.yaml")
    parser.add_argument("--selection-date", default="2024-06-03")
    parser.add_argument("--universe-track", default="strict_technology")
    parser.add_argument("--price-root", default="data/cache")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_local_action_execution_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"局部候选执行回放失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"局部候选执行回放完成 | candidates={payload['candidate_count']} | "
        f"compliant={payload['compliant_count']} | promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
