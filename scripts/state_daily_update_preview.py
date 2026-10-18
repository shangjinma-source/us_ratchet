r"""Build an exact, read-only preview of ``POST /api/daily_update``.

This script writes a rollback snapshot and proposed state only under a research
output directory.  It never writes ``data/state.json`` and never calls an order
endpoint.

PowerShell:
    python -B scripts\state_daily_update_preview.py
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import server
from core.helpers import atomic_write_text, resolve
from core.persist import load_portfolio, save_portfolio
from core.broker_account import load_broker_account
from core.state_readiness import state_clock_readiness
from data.versioning import file_sha256
from backtest.state_catchup import build_reconciliation_template
import yaml


TRACKED_SYMBOL_FIELDS = (
    "shares", "reserve_cash", "reserve_budget", "H", "tier_armed",
    "cost_basis", "pending_ladder", "pending_core_cash", "frozen",
)


def _artifact(path: Path, rows: int | None = None) -> dict:
    return {"path": path.as_posix(), "rows": rows, "bytes": path.stat().st_size, "sha256": file_sha256(path)}


def portfolio_diff(before, after, signals) -> list[dict]:
    """Return field-level changes plus any engine-generated immediate buys."""
    signal_map = {signal.ticker: signal for signal in signals}
    rows: list[dict] = []
    for ticker in sorted(before.symbols):
        old, new = before.symbols[ticker], after.symbols[ticker]
        changes = {
            field: {"before": getattr(old, field), "after": getattr(new, field)}
            for field in TRACKED_SYMBOL_FIELDS
            if getattr(old, field) != getattr(new, field)
        }
        signal = signal_map.get(ticker)
        immediate = [
            {"amount": float(amount), "price": float(price), "reason": str(reason)}
            for amount, price, reason in (signal.immediate_buys if signal is not None else [])
        ]
        rows.append({
            "ticker": ticker, "field_changes": changes,
            "field_change_count": len(changes), "immediate_buys": immediate,
            "immediate_buy_count": len(immediate),
        })
    return rows


def build_bundle(args) -> dict:
    state_path, config_path = resolve(args.state), resolve(args.config)
    broker_path, output_dir = resolve(args.broker), resolve(args.output_dir)
    state_hash_before, config_hash_before = file_sha256(state_path), file_sha256(config_path)
    broker_hash_before = file_sha256(broker_path)
    before = load_portfolio(state_path)
    if before is None:
        raise ValueError("state does not exist")
    cfg = server._cfg_for_portfolio(before)
    latest_closed = server._latest_closed_session_date(cfg)
    if latest_closed is None:
        raise ValueError("no completed common risk-leg session")
    latest_closed_iso = latest_closed.isoformat()
    clock_readiness = state_clock_readiness(before, latest_closed_iso)

    proposed, catchup_ledger, catchup = server._state_session_catchup(
        before, cfg, latest_closed_iso
    )
    diff_rows = portfolio_diff(before, proposed, [])
    historical_actions = [row for row in catchup_ledger if row.get("immediate_buys")]
    broker = load_broker_account(broker_path)
    broker_session_confirmed = bool(
        broker and broker.get("positions_confirmed_session_date") == latest_closed_iso
    )
    entry_dates_after_state = sorted(
        row["ticker"] for row in clock_readiness["blockers"]
        if row["code"] == "POSITION_EVENT_AFTER_STATE_CLOCK"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "rollback": output_dir / "state_before_rollback_snapshot.json",
        "proposed": output_dir / "state_after_daily_update_proposed_not_live.json",
        "diff": output_dir / "today_state_diff.json",
        "ledger": output_dir / "session_catchup_ledger.json",
        "reconciliation_template": output_dir / "state_reconciliation_input_template.yaml",
    }
    shutil.copy2(state_path, paths["rollback"])
    save_portfolio(proposed, paths["proposed"])
    diff_payload = {
        "status": (
            "BLOCKED_USER_RECONCILIATION_REQUIRED"
            if not clock_readiness["safe_to_apply_daily_update"]
            or historical_actions or not broker_session_confirmed else
            "USER_APPROVAL_REQUIRED_NOT_APPLIED"
        ),
        "operation": "exact cross-ticker session-by-session catch-up preview",
        "state_clock_readiness": clock_readiness,
        "state_last_run_date_before": before.last_run_date,
        "state_last_run_date_after": proposed.last_run_date,
        "day_index_before": before.day_index, "day_index_after": proposed.day_index,
        "entry_dates_after_state_last_run_date": entry_dates_after_state,
        "symbols_with_changes": [row["ticker"] for row in diff_rows if row["field_change_count"]],
        "symbols_with_immediate_buys": sorted({
            ticker for row in historical_actions for ticker in row["immediate_buys"]
        }),
        "immediate_buy_count": catchup["immediate_buy_count"],
        "session_catchup": catchup,
        "historical_action_sessions": historical_actions,
        "symbol_diffs": diff_rows,
        "live_state_written": False, "orders_created": False,
        "broker_positions_confirmed_for_latest_session": broker_session_confirmed,
    }
    atomic_write_text(paths["diff"], json.dumps(diff_payload, ensure_ascii=False, indent=2) + "\n")
    atomic_write_text(paths["ledger"], json.dumps(catchup_ledger, ensure_ascii=False, indent=2) + "\n")
    atomic_write_text(
        paths["reconciliation_template"],
        yaml.safe_dump(build_reconciliation_template(before), allow_unicode=True, sort_keys=False),
    )
    if (file_sha256(state_path) != state_hash_before
            or file_sha256(config_path) != config_hash_before
            or file_sha256(broker_path) != broker_hash_before):
        raise RuntimeError("protected config/state/broker changed during daily-update preview")
    manifest = {
        "schema_version": 1, "manifest_type": "state_daily_update_preview",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": diff_payload["status"],
        "latest_completed_session": latest_closed_iso,
        "state_freshness": {
            "before": before.last_run_date, "after_if_approved": proposed.last_run_date,
            "calendar_age_days_before": (latest_closed - datetime.fromisoformat(before.last_run_date).date()).days if before.last_run_date else None,
            "entry_dates_after_state_last_run_date": entry_dates_after_state,
            "clock_readiness": clock_readiness,
            "session_catchup": catchup,
        },
        "impact": {
            "symbols_with_changes": len(diff_payload["symbols_with_changes"]),
            "immediate_buy_count": diff_payload["immediate_buy_count"],
            "config_changed": False, "state_changed": False, "today_advice_changed": False,
            "orders_created": False, "protected_hashes_unchanged": True,
        },
        "approval_boundary": {
            "safe_next_action_if_approved": (
                "reconcile the listed position dates first; POST /api/daily_update remains blocked"
                if not clock_readiness["safe_to_apply_daily_update"] else
                "reconcile historical action sessions before any state write"
                if historical_actions else
                "confirm broker positions for the exact latest completed session"
                if not broker_session_confirmed else
                "review this exact diff and rollback snapshot, then explicitly approve one daily-update write"
            ),
            "rollback_source": paths["rollback"].as_posix(),
            "automatic_apply_allowed": False,
        },
        "inputs": {
            "state": {"path": state_path.as_posix(), "sha256": state_hash_before},
            "config": {"path": config_path.as_posix(), "sha256": config_hash_before},
            "broker": {"path": broker_path.as_posix(), "sha256": broker_hash_before},
        },
        "artifacts": {
            "rollback": _artifact(paths["rollback"]), "proposed": _artifact(paths["proposed"]),
            "diff": _artifact(paths["diff"], len(diff_rows)),
            "ledger": _artifact(paths["ledger"], len(catchup_ledger)),
            "reconciliation_template": _artifact(paths["reconciliation_template"], len(before.symbols)),
        },
    }
    atomic_write_text(output_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="每日状态推进 today diff 与回滚快照（只读）")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--broker", default="data/broker_positions.json")
    parser.add_argument("--output-dir", default="data/cache/research/state_daily_update_preview_v1")
    args = parser.parse_args()
    try:
        manifest = build_bundle(args)
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"每日状态推进预览失败: {exc}", file=sys.stderr)
        return 2
    impact = manifest["impact"]
    print(
        "每日状态推进预览完成 | "
        f"before={manifest['state_freshness']['before']} | after={manifest['state_freshness']['after_if_approved']} | "
        f"changed_symbols={impact['symbols_with_changes']} | immediate_buys={impact['immediate_buy_count']} | "
        "live_changed=False"
    )
    print(f"Manifest: {resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
