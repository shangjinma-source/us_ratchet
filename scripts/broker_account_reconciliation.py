"""Create a versioned, read-only broker/strategy-book reconciliation bundle."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.broker_account_reconciliation import reconcile_strategy_book
from core.helpers import atomic_write_text, resolve
from core.persist import load_portfolio
from data.versioning import file_sha256


def _artifact(path: Path, rows: int | None = None) -> dict:
    return {"path": path.as_posix(), "rows": rows, "bytes": path.stat().st_size, "sha256": file_sha256(path)}


def _latest_sync_evidence(audit_path: Path) -> dict[str, dict]:
    evidence: dict[str, dict] = {}
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        action, detail = record.get("action"), record.get("detail") or {}
        if action == "sync_trades":
            changed = detail.get("changed") or []
        elif action == "set_position":
            changed = [{
                "ticker": detail.get("ticker"), "shares": detail.get("shares"),
                "avg_price": detail.get("buy_price"), "first_date": detail.get("buy_date"),
            }]
        else:
            continue
        for row in changed:
            ticker = str(row.get("ticker") or "").upper()
            if ticker:
                evidence[ticker] = {
                    "ticker": ticker, "audit_timestamp": record.get("ts"), "audit_action": action,
                    "audited_shares": row.get("shares"), "audited_average_cost": row.get("avg_price"),
                    "audited_event_date": row.get("first_date"),
                }
    return evidence


def build_bundle(args) -> dict:
    source_path, state_path, audit_path = resolve(args.source), resolve(args.state), resolve(args.audit)
    output_dir = resolve(args.output_dir)
    source = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    portfolio = load_portfolio(state_path)
    if portfolio is None:
        raise ValueError("state does not exist")
    state_hash, audit_hash = file_sha256(state_path), file_sha256(audit_path)
    result = reconcile_strategy_book(portfolio, source.get("positions") or [])
    sync_evidence = _latest_sync_evidence(audit_path)
    evidence_rows = []
    for row in result["broker_positions"]:
        evidence = sync_evidence.get(row["ticker"])
        exact = bool(
            evidence
            and abs(float(evidence.get("audited_shares") or 0) - float(row["shares"])) < 1e-9
            and abs(float(evidence.get("audited_average_cost") or 0) - float(row["average_cost"])) < 0.001
        )
        evidence_rows.append({
            "ticker": row["ticker"],
            "broker_whole_shares": row["shares"],
            "broker_average_cost": row["average_cost"],
            **(evidence or {"audit_timestamp": None, "audit_action": None, "audited_shares": None, "audited_average_cost": None, "audited_event_date": None}),
            "latest_audit_exact_match": exact,
            "chronology_status": "AUDIT_EVENT_REPLAYABLE" if exact else "CURRENT_SNAPSHOT_ONLY_EVENT_DATE_UNKNOWN",
        })
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "positions": output_dir / "broker_account_truth.csv",
        "reconciliation": output_dir / "strategy_book_reconciliation.csv",
        "summary": output_dir / "account_summary.json",
        "evidence": output_dir / "broker_sync_evidence.csv",
        "workbook": output_dir / "汇丰实际持仓与策略账分层对账.xlsx",
    }
    pd.DataFrame(result["broker_positions"]).to_csv(paths["positions"], index=False, encoding="utf-8-sig")
    pd.DataFrame(result["reconciliation"]).to_csv(paths["reconciliation"], index=False, encoding="utf-8-sig")
    atomic_write_text(paths["summary"], json.dumps(result["summary"], ensure_ascii=False, indent=2) + "\n")
    pd.DataFrame(evidence_rows).to_csv(paths["evidence"], index=False, encoding="utf-8-sig")
    temporary = paths["workbook"].with_suffix(".tmp.xlsx")
    with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
        pd.DataFrame(result["broker_positions"]).to_excel(writer, sheet_name="券商实际持仓", index=False)
        pd.DataFrame(result["reconciliation"]).to_excel(writer, sheet_name="策略账分层对账", index=False)
        pd.DataFrame(evidence_rows).to_excel(writer, sheet_name="前端同步审计证据", index=False)
        pd.DataFrame([result["summary"]]).to_excel(writer, sheet_name="账户集中度", index=False)
    temporary.replace(paths["workbook"])
    if file_sha256(state_path) != state_hash or file_sha256(audit_path) != audit_hash:
        raise RuntimeError("protected state/audit changed during reconciliation")
    manifest = {
        "schema_version": 1,
        "manifest_type": "broker_account_truth_strategy_book_reconciliation",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "snapshot_as_of": source.get("snapshot_as_of"),
        "snapshot_clock": source.get("snapshot_clock"),
        "source_note": source.get("source_note"),
        "track_contract": {
            "portfolio_optimization": "VARIABLE_CARDINALITY strategy book baseline; broker-only positions excluded",
            "migration_control": "not included in target-cardinality conclusions",
            "broker_account_truth": "used only for account concentration and future execution readiness",
        },
        "source_images": source.get("source_images") or [],
        "inputs": {
            "source": {"path": source_path.as_posix(), "sha256": file_sha256(source_path)},
            "state": {"path": state_path.as_posix(), "sha256": state_hash},
            "audit": {"path": audit_path.as_posix(), "sha256": audit_hash},
        },
        "summary": result["summary"],
        "artifacts": {
            "broker_account_truth": _artifact(paths["positions"], len(result["broker_positions"])),
            "strategy_book_reconciliation": _artifact(paths["reconciliation"], len(result["reconciliation"])),
            "account_summary": _artifact(paths["summary"], 1),
            "broker_sync_evidence": _artifact(paths["evidence"], len(evidence_rows)),
            "workbook": _artifact(paths["workbook"]),
        },
        "guards": {
            "return_data_read": False,
            "fresh_oos_consumed": False,
            "config_changed": False,
            "state_changed": False,
            "today_advice_changed": False,
            "orders_created": False,
            "automatic_state_patch_allowed": False,
        },
    }
    atomic_write_text(output_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="汇丰实际持仓与策略账分层对账（只读）")
    parser.add_argument("--source", default="data/cache/research/broker_account_reconciliation_v1/broker_snapshot_source.yaml")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--audit", default="data/audit.jsonl")
    parser.add_argument("--output-dir", default="data/cache/research/broker_account_reconciliation_v1")
    args = parser.parse_args()
    try:
        manifest = build_bundle(args)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"账户分层对账失败: {exc}", file=sys.stderr)
        return 2
    s = manifest["summary"]
    print(f"账户分层对账完成 | broker={s['broker_position_count']} | strategy_and_broker={s['strategy_and_broker_count']} | broker_only={s['broker_only_count']} | strategy_only={s['strategy_book_only_count']} | state_changed=False")
    print(f"Manifest: {resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
