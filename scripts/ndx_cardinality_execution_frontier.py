r"""Re-select cross-k training frontiers after fixed-cash whole-lot constraints."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cardinality_discovery import load_discovery_spec, validate_discovery_spec
from core.helpers import atomic_write_text
from data.versioning import file_sha256
from scripts.ndx_cardinality_frontier_attribution import (
    concentration_metrics,
    parse_weight_string,
    repair_whole_lot_allocation,
    whole_lot_weight_drift,
)
from scripts.ndx_cardinality_real_smoke import _load_bars


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
    frontier_manifest_path = _resolve(args.frontier_manifest)
    discovery_manifest_path = _resolve(args.discovery_manifest)
    spec_path = _resolve(args.spec)
    frontier_manifest = json.loads(frontier_manifest_path.read_text(encoding="utf-8"))
    if frontier_manifest.get("manifest_type") != "ndx_cross_cardinality_real_training_frontiers":
        raise ValueError("unexpected cross-cardinality manifest")
    artifact_key = str(args.candidate_artifact)
    artifact = (frontier_manifest.get("artifacts") or {}).get(artifact_key) or {}
    frontier_path = Path(str(artifact.get("path") or ""))
    if not frontier_path.is_absolute() or file_sha256(frontier_path) != artifact.get("sha256"):
        raise ValueError(f"cardinality frontier artifact mismatch: {artifact_key}")
    frontiers = pd.read_csv(frontier_path, low_memory=False)
    if len(frontiers) != int(artifact.get("rows") or -1):
        raise ValueError("cardinality frontier row count changed")

    discovery = json.loads(discovery_manifest_path.read_text(encoding="utf-8"))
    members_artifact = (discovery.get("artifacts") or {}).get("eligible_securities") or {}
    members_path = Path(str(members_artifact.get("path") or ""))
    if not members_path.is_absolute() or file_sha256(members_path) != members_artifact.get("sha256"):
        raise ValueError("point-in-time membership artifact mismatch")
    members = pd.read_csv(members_path, low_memory=False)
    identity = frontier_manifest["comparison_identity"]
    selection = pd.Timestamp(identity["selection_date"]).normalize()
    metadata = members.loc[
        members["universe_track"].eq(identity["universe_track"])
        & members["selection_date"].eq(selection.date().isoformat())
    ][["ticker", "issuer_id", "risk_chain"]].drop_duplicates("ticker").set_index("ticker")
    if metadata.index.duplicated().any():
        raise ValueError("point-in-time metadata is ambiguous")

    spec = load_discovery_spec(spec_path)
    validate_discovery_spec(spec)
    contract = spec["synthetic_smoke_contract"]
    cash = float(contract["portfolio_cash_usd"])
    buffer = float(contract["minimum_cash_buffer_usd"])
    min_weight = float(contract["min_single_weight"])
    max_weight = float(contract["max_single_weight"])
    top3_cap = float(contract["top_weight_cap"])
    effective_ratio = float(contract["minimum_effective_n_ratio"])
    chain_cap = float(contract["risk_chain_top1_cap"])

    inventories = {}
    source_inputs = []
    for source_value in sorted(frontiers["source_manifest"].astype(str).unique()):
        source_path = Path(source_value)
        source = json.loads(source_path.read_text(encoding="utf-8"))
        inventory_artifact = (source.get("artifacts") or {}).get("price_inventory") or {}
        inventory_path = Path(str(inventory_artifact.get("path") or ""))
        if not inventory_path.is_absolute() or file_sha256(inventory_path) != inventory_artifact.get("sha256"):
            raise ValueError(f"price inventory mismatch: {source_path}")
        inventory = pd.read_csv(inventory_path, low_memory=False)
        if len(inventory) != int(inventory_artifact.get("rows") or -1):
            raise ValueError(f"price inventory rows changed: {source_path}")
        inventories[source_value] = inventory.set_index("ticker")
        source_inputs.append({"path": source_path.as_posix(), "sha256": file_sha256(source_path)})

    price_cache = {}
    rows = []
    for frontier in frontiers.to_dict("records"):
        weights = parse_weight_string(frontier["weights"])
        inventory = inventories[str(frontier["source_manifest"])]
        prices = {}
        chains = {}
        for ticker in weights:
            if ticker not in metadata.index or ticker not in inventory.index:
                raise ValueError(f"execution metadata missing: {ticker}")
            price_path = Path(str(inventory.loc[ticker, "path"]))
            expected_hash = str(inventory.loc[ticker, "sha256"])
            cache_key = (price_path.as_posix(), expected_hash)
            if cache_key not in price_cache:
                if file_sha256(price_path) != expected_hash:
                    raise ValueError(f"price file hash changed: {ticker}")
                prior = _load_bars(price_path).loc[lambda frame: frame.index < selection]
                if prior.empty:
                    raise ValueError(f"selection prior close missing: {ticker}")
                price_cache[cache_key] = float(prior["Close"].iloc[-1])
            prices[ticker] = price_cache[cache_key]
            chains[ticker] = str(metadata.loc[ticker, "risk_chain"])
        shares = repair_whole_lot_allocation(
            weights, prices, chains, cash=cash, minimum_cash_buffer=buffer,
            risk_chain_top1_cap=chain_cap, min_single_weight=min_weight,
            max_single_weight=max_weight, top3_cap=top3_cap,
            minimum_effective_n_ratio=effective_ratio,
        )
        notionals = {ticker: shares[ticker] * prices[ticker] for ticker in weights}
        drift = whole_lot_weight_drift(weights, notionals, cash)
        concentration = concentration_metrics(drift["actual_risky_weights"])
        chain_weights = {}
        for ticker, weight in drift["actual_risky_weights"].items():
            chain_weights[chains[ticker]] = chain_weights.get(chains[ticker], 0.0) + weight
        checks = {
            "whole_lot": all(value >= 1 for value in shares.values()),
            "min_single": min(drift["actual_risky_weights"].values()) >= min_weight - 1e-12,
            "max_single": concentration["top1_weight"] <= max_weight + 1e-12,
            "top3": concentration["top3_weight"] <= top3_cap + 1e-12,
            "effective_n": concentration["effective_n"] >= len(weights) * effective_ratio - 1e-12,
            "risk_chain_top1": max(chain_weights.values()) <= chain_cap + 1e-12,
            "cash_buffer": cash - sum(notionals.values()) >= buffer - 1e-9,
        }
        rows.append({
            **frontier,
            "execution_issuer_ids": ";".join(sorted(str(metadata.loc[ticker, "issuer_id"]) for ticker in weights)),
            "execution_constraints_passed": all(checks.values()),
            "execution_constraint_failures": ";".join(key for key, passed in checks.items() if not passed),
            "execution_whole_shares": ";".join(f"{ticker}:{shares[ticker]}" for ticker in sorted(shares)),
            "execution_invested_usd": sum(notionals.values()),
            "execution_residual_cash_usd": cash - sum(notionals.values()),
            "execution_deployment_ratio": drift["deployment_ratio"],
            "execution_risky_weight_l1_drift": drift["risky_weight_l1_drift"],
            "execution_risky_weight_max_abs_drift": drift["risky_weight_max_abs_drift"],
            "execution_actual_top1_weight": concentration["top1_weight"],
            "execution_actual_top3_weight": concentration["top3_weight"],
            "execution_actual_effective_n": concentration["effective_n"],
            "execution_actual_risk_chain_top1_weight": max(chain_weights.values()),
        })
    audit = pd.DataFrame(rows)
    compliant = audit.loc[audit["execution_constraints_passed"].astype(bool)].copy()
    if compliant.empty:
        raise ValueError("no whole-lot compliant cardinality frontier remains")
    selectors = {
        "RETURN": ("return_p50", False), "BAD_TAIL": ("return_p10", False),
        "DRAWDOWN": ("max_drawdown_p90", True),
        "012922_DISTANCE": ("target_012922_distance", True),
    }
    selected_rows = []
    for role, (column, ascending) in selectors.items():
        row = compliant.sort_values(
            [column, "tickers", "weight_spec"], ascending=[ascending, True, True], kind="stable"
        ).iloc[0].copy()
        row["execution_frontier_role"] = role
        selected_rows.append(row)
    selected = pd.DataFrame(selected_rows)

    output = _resolve(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    audit_path = output / "execution_frontier_audit.csv"
    selected_path = output / "execution_aware_frontiers.csv"
    workbook_path = output / "ndx_cardinality_execution_frontiers.xlsx"
    _atomic_csv(audit, audit_path)
    _atomic_csv(selected, selected_path)
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            selected.to_excel(writer, sheet_name="整股可执行前沿", index=False)
            audit.to_excel(writer, sheet_name="逐候选执行审计", index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_execution_aware_frontiers",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "TRAINING_EXECUTION_RESELECTION_ONLY_NOT_ADMISSION",
        "candidate_frontier_count": len(audit),
        "candidate_artifact_key": artifact_key,
        "execution_compliant_count": len(compliant),
        "selected_frontier_count": len(selected),
        "portfolio_cash_usd": cash, "minimum_cash_buffer_usd": buffer,
        "strategy_baseline": "ORIGINAL_8_CAP_TOTAL_NORMALIZED",
        "personal_off_strategy_positions_included": False,
        "fresh_oos_consumed": False, "promotion_allowed": False,
        "inputs": {
            "frontier_manifest": {"path": frontier_manifest_path.as_posix(), "sha256": file_sha256(frontier_manifest_path)},
            "frontiers": {"path": frontier_path.as_posix(), "sha256": file_sha256(frontier_path)},
            "discovery_manifest": {"path": discovery_manifest_path.as_posix(), "sha256": file_sha256(discovery_manifest_path)},
            "members": {"path": members_path.as_posix(), "sha256": file_sha256(members_path)},
            "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
            "sources": source_inputs,
        },
        "artifacts": {
            "audit": {"path": audit_path.as_posix(), "rows": len(audit), "sha256": file_sha256(audit_path)},
            "selected": {"path": selected_path.as_posix(), "rows": len(selected), "sha256": file_sha256(selected_path)},
            "workbook": {"path": workbook_path.as_posix(), "sha256": file_sha256(workbook_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="跨持仓数前沿整股约束重选")
    parser.add_argument("--frontier-manifest", default="data/cache/research/ndx_cross_cardinality_frontiers_v2/manifest.json")
    parser.add_argument("--discovery-manifest", default="data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json")
    parser.add_argument("--spec", default="config/ndx_cardinality_discovery_v1.yaml")
    parser.add_argument(
        "--candidate-artifact", choices=["frontiers", "cross_cardinality_pareto"],
        default="cross_cardinality_pareto",
    )
    parser.add_argument("--output-dir", default="data/cache/research/ndx_cardinality_execution_frontiers_v1")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"整股执行前沿重选失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"整股执行前沿重选完成 | compliant={payload['execution_compliant_count']}/"
        f"{payload['candidate_frontier_count']} | promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
