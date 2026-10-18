"""Apply the explicitly approved broker/state split with hash-locked rollback."""
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

from core.broker_account import load_broker_account, save_broker_account
from core.helpers import atomic_write_text, resolve
from core.persist import audit_log, load_portfolio, save_portfolio
from data.versioning import file_sha256


APPROVAL_TOKEN = "批准分层持仓并推进策略时钟"


def _artifact(path: Path) -> dict:
    return {"path": path.as_posix(), "bytes": path.stat().st_size, "sha256": file_sha256(path)}


def build_or_apply(args) -> dict:
    live_state, live_config, live_broker = resolve(args.state), resolve(args.config), resolve(args.broker)
    preview_dir, output_dir = resolve(args.preview_dir), resolve(args.output_dir)
    preview_manifest_path = preview_dir / "manifest.json"
    preview = json.loads(preview_manifest_path.read_text(encoding="utf-8"))
    expected_state = preview["inputs"]["state"]["sha256"]
    expected_config = preview["inputs"]["config"]["sha256"]
    if file_sha256(live_state) != expected_state:
        raise RuntimeError("live state hash drifted after approval")
    if file_sha256(live_config) != expected_config:
        raise RuntimeError("live config hash drifted after approval")
    if preview.get("status") != "USER_APPROVAL_REQUIRED_NOT_APPLIED":
        raise RuntimeError("preview is not approval-gated")
    proposed_state_path = Path(preview["artifacts"]["proposed_strategy_state"]["path"])
    proposed_broker_path = Path(preview["artifacts"]["proposed_broker_account"]["path"])
    if file_sha256(proposed_state_path) != preview["artifacts"]["proposed_strategy_state"]["sha256"]:
        raise RuntimeError("proposed state hash mismatch")
    if file_sha256(proposed_broker_path) != preview["artifacts"]["proposed_broker_account"]["sha256"]:
        raise RuntimeError("proposed broker account hash mismatch")
    before = load_portfolio(live_state)
    after = load_portfolio(proposed_state_path)
    broker_after = load_broker_account(proposed_broker_path)
    state_changes = []
    for ticker in sorted(before.symbols):
        fields = {}
        for field in ("H", "tier_armed", "pending_ladder", "pending_core_cash", "shares", "cost_basis"):
            old, new = getattr(before.symbols[ticker], field), getattr(after.symbols[ticker], field)
            if old != new:
                fields[field] = {"before": old, "after": new}
        if fields:
            state_changes.append({"ticker": ticker, "fields": fields})
    transition = {
        "approval_token_required": APPROVAL_TOKEN,
        "approval_token_matched": args.approval_token == APPROVAL_TOKEN,
        "apply_requested": bool(args.apply),
        "state_clock": {"before": before.last_run_date, "after": after.last_run_date},
        "state_symbol_changes": state_changes,
        "broker_positions_after": broker_after["positions"],
        "broker_position_count_after": len(broker_after["positions"]),
        "config_changed": False,
        "today_advice_recompute_required": True,
        "orders_created": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(output_dir / "approved_transition_diff.json", json.dumps(transition, ensure_ascii=False, indent=2) + "\n")
    if not args.apply:
        transition["status"] = "PLAN_ONLY_NOT_APPLIED"
        return transition
    if args.approval_token != APPROVAL_TOKEN:
        raise RuntimeError("explicit approval token mismatch")
    rollback_dir = output_dir / "rollback"
    rollback_dir.mkdir(parents=True, exist_ok=True)
    rollback_state = rollback_dir / "state_before_approved_transition.json"
    shutil.copy2(live_state, rollback_state)
    rollback_broker = None
    if live_broker.exists():
        rollback_broker = rollback_dir / "broker_positions_before_approved_transition.json"
        shutil.copy2(live_broker, rollback_broker)
    save_broker_account(broker_after, live_broker)
    save_portfolio(after, live_state)
    audit_log(
        "apply_approved_broker_state_transition",
        {
            "approval_token": APPROVAL_TOKEN,
            "state_before_sha256": expected_state,
            "state_after_sha256": file_sha256(live_state),
            "broker_after_sha256": file_sha256(live_broker),
            "state_clock_before": before.last_run_date,
            "state_clock_after": after.last_run_date,
            "broker_position_count": len(broker_after["positions"]),
            "rollback_state": rollback_state.as_posix(),
            "rollback_broker": rollback_broker.as_posix() if rollback_broker else None,
        },
        "用户明确批准分层持仓并推进策略时钟；未创建订单",
    )
    if file_sha256(live_config) != expected_config:
        raise RuntimeError("config changed during approved transition")
    manifest = {
        "schema_version": 1,
        "manifest_type": "approved_broker_state_transition",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "APPLIED_USER_APPROVED",
        "approval_token": APPROVAL_TOKEN,
        "inputs": {
            "preview_manifest": _artifact(preview_manifest_path),
            "state_before": {"sha256": expected_state},
            "config": {"path": live_config.as_posix(), "sha256": expected_config},
        },
        "outputs": {
            "state": _artifact(live_state),
            "broker_account": _artifact(live_broker),
            "transition_diff": _artifact(output_dir / "approved_transition_diff.json"),
        },
        "rollback": {
            "state": _artifact(rollback_state),
            "broker_account": _artifact(rollback_broker) if rollback_broker else None,
        },
        "impact": {
            "state_clock_before": before.last_run_date,
            "state_clock_after": after.last_run_date,
            "state_symbols_changed": len(state_changes),
            "broker_position_count": len(broker_after["positions"]),
            "config_changed": False,
            "today_advice_recomputed_by_running_service": False,
            "orders_created": False,
        },
    }
    atomic_write_text(output_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="应用已批准的券商持仓分层与策略时钟推进")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--broker", default="data/broker_positions.json")
    parser.add_argument("--preview-dir", default="data/cache/research/state_catchup_reconciled_preview_v1")
    parser.add_argument("--output-dir", default="data/cache/research/approved_broker_state_transition_20260801")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approval-token", default="")
    args = parser.parse_args()
    try:
        result = build_or_apply(args)
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"批准迁移失败: {exc}", file=sys.stderr)
        return 2
    print(f"批准迁移 | status={result['status']} | orders_created=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
