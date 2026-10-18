"""Fail-closed approval contract for one exact state daily-update transition."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from core.broker_account import load_broker_account
from core.persist import audit_log, load_portfolio, save_portfolio
from data.versioning import file_sha256


class StateDailyUpdateApprovalError(ValueError):
    """Raised when a preview cannot be bound to one user-approved state write."""


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False, default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _aware_utc(value: Any, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise StateDailyUpdateApprovalError(f"invalid {label}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise StateDailyUpdateApprovalError(f"{label} must be timezone-aware")
    return result.astimezone(timezone.utc)


def _canonical(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise StateDailyUpdateApprovalError(f"path escapes repository: {relative}") from exc
    return candidate


def _artifact_path(descriptor: Mapping[str, Any], expected: Path) -> Path:
    if set(descriptor) != {"path", "rows", "bytes", "sha256"}:
        raise StateDailyUpdateApprovalError("preview artifact descriptor schema changed")
    path = Path(str(descriptor.get("path") or "")).resolve()
    if (
        path != expected.resolve() or not path.is_file()
        or path.stat().st_size != int(descriptor.get("bytes", -1))
        or file_sha256(path) != descriptor.get("sha256")
    ):
        raise StateDailyUpdateApprovalError(f"preview artifact changed: {expected.name}")
    return path


def verify_daily_update_preview(
    manifest_path: str | Path, *, repository_root: str | Path,
) -> dict[str, Any]:
    """Recompute the state transition plus broker/session confirmation binding."""
    root = Path(repository_root).resolve()
    expected_manifest = _canonical(
        root, "data/cache/research/state_daily_update_preview_v1/manifest.json",
    )
    path = Path(manifest_path).resolve()
    if path != expected_manifest:
        raise StateDailyUpdateApprovalError("daily-update preview path is not canonical")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateDailyUpdateApprovalError("daily-update preview is missing/invalid") from exc
    if (
        set(manifest) != {
            "schema_version", "manifest_type", "generated_at", "status",
            "latest_completed_session", "state_freshness", "impact",
            "approval_boundary", "inputs", "artifacts",
        }
        or manifest.get("schema_version") != 1
        or manifest.get("manifest_type") != "state_daily_update_preview"
        or manifest.get("status") != "USER_APPROVAL_REQUIRED_NOT_APPLIED"
    ):
        raise StateDailyUpdateApprovalError("preview is not an approval-ready exact transition")
    preview_root = path.parent
    inputs = manifest.get("inputs") or {}
    if set(inputs) != {"state", "config", "broker"}:
        raise StateDailyUpdateApprovalError("preview must bind state, config, and broker inputs")
    expected_inputs = {
        "state": _canonical(root, "data/state.json"),
        "config": _canonical(root, "config/config.yaml"),
        "broker": _canonical(root, "data/broker_positions.json"),
    }
    for name, expected in expected_inputs.items():
        descriptor = inputs.get(name) or {}
        if set(descriptor) != {"path", "sha256"}:
            raise StateDailyUpdateApprovalError(f"preview {name} input schema changed")
        if (
            Path(str(descriptor.get("path") or "")).resolve() != expected
            or not expected.is_file() or file_sha256(expected) != descriptor.get("sha256")
        ):
            raise StateDailyUpdateApprovalError(f"live {name} hash drifted after preview")
    artifacts = manifest.get("artifacts") or {}
    expected_artifacts = {
        "rollback": preview_root / "state_before_rollback_snapshot.json",
        "proposed": preview_root / "state_after_daily_update_proposed_not_live.json",
        "diff": preview_root / "today_state_diff.json",
        "ledger": preview_root / "session_catchup_ledger.json",
        "reconciliation_template": preview_root / "state_reconciliation_input_template.yaml",
    }
    if set(artifacts) != set(expected_artifacts):
        raise StateDailyUpdateApprovalError("preview artifact registry is incomplete")
    paths = {
        name: _artifact_path(artifacts[name], expected)
        for name, expected in expected_artifacts.items()
    }
    if file_sha256(paths["rollback"]) != inputs["state"]["sha256"]:
        raise StateDailyUpdateApprovalError("rollback snapshot is not the exact live state input")
    before, proposed = load_portfolio(paths["rollback"]), load_portfolio(paths["proposed"])
    if before is None or proposed is None:
        raise StateDailyUpdateApprovalError("preview state artifact cannot be loaded")
    try:
        diff = json.loads(paths["diff"].read_text(encoding="utf-8"))
        ledger = json.loads(paths["ledger"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateDailyUpdateApprovalError("preview diff/ledger is invalid") from exc
    catchup = (manifest.get("state_freshness") or {}).get("session_catchup") or {}
    dates = [str(row.get("session_date") or "") for row in ledger]
    latest = str(manifest.get("latest_completed_session") or "")
    if (
        not isinstance(ledger, list)
        or dates != sorted(dates) or len(dates) != len(set(dates))
        or len(ledger) != int(catchup.get("session_count", -1))
        or (dates[0] if dates else None) != catchup.get("first_session")
        or (dates[-1] if dates else None) != catchup.get("last_session")
        or (dates[-1] if dates else before.last_run_date) != latest
        or proposed.last_run_date != latest
        or before.last_run_date != (manifest.get("state_freshness") or {}).get("before")
        or proposed.last_run_date != (manifest.get("state_freshness") or {}).get("after_if_approved")
        or proposed.day_index - before.day_index != len(ledger)
        or any(row.get("immediate_buys") for row in ledger)
        or diff.get("status") != "USER_APPROVAL_REQUIRED_NOT_APPLIED"
        or diff.get("live_state_written") is not False
        or diff.get("orders_created") is not False
        or int(diff.get("immediate_buy_count", -1)) != 0
        or (manifest.get("impact") or {}).get("protected_hashes_unchanged") is not True
        or (manifest.get("impact") or {}).get("state_changed") is not False
        or (manifest.get("impact") or {}).get("orders_created") is not False
        or (manifest.get("approval_boundary") or {}).get("automatic_apply_allowed") is not False
    ):
        raise StateDailyUpdateApprovalError("preview clock/diff/rollback boundary changed")
    broker = load_broker_account(expected_inputs["broker"])
    if broker is None or str(broker.get("positions_confirmed_session_date") or "") != latest:
        raise StateDailyUpdateApprovalError(
            "broker positions are not explicitly confirmed for the preview session"
        )
    return {
        "manifest": manifest, "manifest_path": path,
        "manifest_sha256": file_sha256(path), "before": before,
        "proposed": proposed, "broker": broker, "paths": paths,
        "expected_inputs": expected_inputs, "session": latest,
    }


APPROVAL_PLAN_KEYS = {
    "schema_version", "manifest_type", "status", "request_id", "created_at_utc",
    "expires_at_utc", "session_date", "approval_token_sha256",
    "approval_token_artifact", "preview_manifest", "expected_live_inputs",
    "today_diff", "rollback", "proposed_state", "broker_confirmation",
    "one_time_use", "apply_default", "orders_created", "promotion_allowed",
    "manifest_sha256",
}


def _descriptor(path: Path) -> dict[str, str]:
    return {"path": path.resolve().as_posix(), "sha256": file_sha256(path)}


def build_approval_plan(
    preview_manifest_path: str | Path, *, repository_root: str | Path,
    output_dir: str | Path, now_utc: Any | None = None,
) -> tuple[dict[str, Any], str]:
    """Seal one expiring token request; this never writes live state."""
    root = Path(repository_root).resolve()
    output = Path(output_dir).resolve()
    expected_output = _canonical(root, "data/cache/research/state_daily_update_approval_v1")
    if output != expected_output:
        raise StateDailyUpdateApprovalError("approval output directory is not canonical")
    verified = verify_daily_update_preview(
        preview_manifest_path, repository_root=root,
    )
    created = (
        _aware_utc(now_utc, "plan creation time")
        if now_utc is not None else datetime.now(timezone.utc)
    )
    token = secrets.token_urlsafe(24)
    token_sha = hashlib.sha256(token.encode("utf-8")).hexdigest()
    request_id = canonical_sha256({
        "preview_manifest_sha256": verified["manifest_sha256"],
        "session_date": verified["session"],
        "state_sha256": file_sha256(verified["expected_inputs"]["state"]),
        "broker_sha256": file_sha256(verified["expected_inputs"]["broker"]),
        "approval_token_sha256": token_sha,
    })[:24]
    output.mkdir(parents=True, exist_ok=True)
    plan_path = output / "approval_plan.json"
    token_path = output / "approval_token.txt"
    if plan_path.exists() or token_path.exists():
        raise StateDailyUpdateApprovalError("approval plan already exists; refusing overwrite")
    token_content = (
        f"request_id={request_id}\nsession_date={verified['session']}\n"
        f"approval_token={token}\n"
    )
    token_temporary = token_path.with_suffix(".txt.tmp")
    token_temporary.write_text(token_content, encoding="utf-8", newline="\n")
    os.replace(token_temporary, token_path)
    manifest = verified["manifest"]
    plan = {
        "schema_version": 1,
        "manifest_type": "state_daily_update_one_time_approval_plan",
        "status": "AWAITING_EXPLICIT_USER_APPROVAL_NOT_APPLIED",
        "request_id": request_id,
        "created_at_utc": created.isoformat(),
        "expires_at_utc": (created + timedelta(hours=24)).isoformat(),
        "session_date": verified["session"],
        "approval_token_sha256": token_sha,
        "approval_token_artifact": _descriptor(token_path),
        "preview_manifest": {
            "path": verified["manifest_path"].as_posix(),
            "sha256": verified["manifest_sha256"],
        },
        "expected_live_inputs": {
            name: _descriptor(path) for name, path in verified["expected_inputs"].items()
        },
        "today_diff": _descriptor(verified["paths"]["diff"]),
        "rollback": _descriptor(verified["paths"]["rollback"]),
        "proposed_state": _descriptor(verified["paths"]["proposed"]),
        "broker_confirmation": {
            "positions_confirmed_session_date": verified["broker"]["positions_confirmed_session_date"],
            "snapshot_as_of": verified["broker"]["snapshot_as_of"],
            "broker_sha256": manifest["inputs"]["broker"]["sha256"],
        },
        "one_time_use": {
            "required": True,
            "consumed_marker": (
                output / "consumed" / f"{request_id}.json"
            ).resolve().as_posix(),
        },
        "apply_default": False,
        "orders_created": False,
        "promotion_allowed": False,
    }
    plan["manifest_sha256"] = canonical_sha256(plan)
    content = json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    plan_temporary = plan_path.with_suffix(".json.tmp")
    plan_temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(plan_temporary, plan_path)
    return plan, token


def verify_approval_plan(
    plan_path: str | Path, *, repository_root: str | Path,
    now_utc: Any | None = None,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    path = Path(plan_path).resolve()
    output = _canonical(root, "data/cache/research/state_daily_update_approval_v1")
    if path != output / "approval_plan.json":
        raise StateDailyUpdateApprovalError("approval plan path is not canonical")
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateDailyUpdateApprovalError("approval plan is missing/invalid") from exc
    unsigned = dict(plan)
    declared = str(unsigned.pop("manifest_sha256", ""))
    if (
        set(plan) != APPROVAL_PLAN_KEYS
        or canonical_sha256(unsigned) != declared
        or plan.get("schema_version") != 1
        or plan.get("manifest_type") != "state_daily_update_one_time_approval_plan"
        or plan.get("status") != "AWAITING_EXPLICIT_USER_APPROVAL_NOT_APPLIED"
        or plan.get("apply_default") is not False
        or plan.get("orders_created") is not False
        or plan.get("promotion_allowed") is not False
    ):
        raise StateDailyUpdateApprovalError("approval plan boundary changed")
    current = (
        _aware_utc(now_utc, "plan verification time")
        if now_utc is not None else datetime.now(timezone.utc)
    )
    if current > _aware_utc(plan.get("expires_at_utc"), "plan expiry"):
        raise StateDailyUpdateApprovalError("approval plan expired")
    preview_descriptor = plan.get("preview_manifest") or {}
    if set(preview_descriptor) != {"path", "sha256"}:
        raise StateDailyUpdateApprovalError("approval preview binding changed")
    preview = verify_daily_update_preview(
        preview_descriptor.get("path"), repository_root=root,
    )
    if preview["manifest_sha256"] != preview_descriptor.get("sha256"):
        raise StateDailyUpdateApprovalError("approval preview hash changed")
    expected_inputs = plan.get("expected_live_inputs") or {}
    if set(expected_inputs) != {"state", "config", "broker"}:
        raise StateDailyUpdateApprovalError("approval live input registry changed")
    for name, expected_path in preview["expected_inputs"].items():
        descriptor = expected_inputs.get(name) or {}
        if (
            set(descriptor) != {"path", "sha256"}
            or Path(str(descriptor.get("path") or "")).resolve() != expected_path
            or file_sha256(expected_path) != descriptor.get("sha256")
        ):
            raise StateDailyUpdateApprovalError(f"approval {name} binding changed")
    bindings = {
        "today_diff": preview["paths"]["diff"],
        "rollback": preview["paths"]["rollback"],
        "proposed_state": preview["paths"]["proposed"],
    }
    for name, expected_path in bindings.items():
        descriptor = plan.get(name) or {}
        if (
            set(descriptor) != {"path", "sha256"}
            or Path(str(descriptor.get("path") or "")).resolve() != expected_path
            or file_sha256(expected_path) != descriptor.get("sha256")
        ):
            raise StateDailyUpdateApprovalError(f"approval {name} binding changed")
    token_artifact = plan.get("approval_token_artifact") or {}
    token_path = output / "approval_token.txt"
    if (
        set(token_artifact) != {"path", "sha256"}
        or Path(str(token_artifact.get("path") or "")).resolve() != token_path
        or not token_path.is_file()
        or file_sha256(token_path) != token_artifact.get("sha256")
    ):
        raise StateDailyUpdateApprovalError("approval token artifact changed")
    token_lines = dict(
        line.split("=", 1) for line in token_path.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    token = token_lines.get("approval_token", "")
    if (
        token_lines.get("request_id") != plan.get("request_id")
        or token_lines.get("session_date") != plan.get("session_date")
        or hashlib.sha256(token.encode("utf-8")).hexdigest()
        != plan.get("approval_token_sha256")
        or plan.get("session_date") != preview["session"]
    ):
        raise StateDailyUpdateApprovalError("approval token/session binding changed")
    broker = plan.get("broker_confirmation") or {}
    if (
        set(broker) != {"positions_confirmed_session_date", "snapshot_as_of", "broker_sha256"}
        or broker.get("positions_confirmed_session_date") != preview["session"]
        or broker.get("positions_confirmed_session_date")
        != preview["broker"].get("positions_confirmed_session_date")
        or broker.get("snapshot_as_of") != preview["broker"].get("snapshot_as_of")
        or broker.get("broker_sha256") != expected_inputs["broker"]["sha256"]
    ):
        raise StateDailyUpdateApprovalError("approval broker confirmation changed")
    one_time = plan.get("one_time_use") or {}
    consumed = output / "consumed" / f"{plan['request_id']}.json"
    if (
        set(one_time) != {"required", "consumed_marker"}
        or one_time.get("required") is not True
        or Path(str(one_time.get("consumed_marker") or "")).resolve() != consumed
        or consumed.exists()
    ):
        raise StateDailyUpdateApprovalError("approval token already consumed or marker changed")
    return {"plan": plan, "preview": preview, "token": token, "consumed_marker": consumed}


def refresh_approval_plan(
    preview_manifest_path: str | Path, *, repository_root: str | Path,
    output_dir: str | Path, now_utc: Any | None = None,
) -> tuple[dict[str, Any], str]:
    """Archive the old immutable request and transactionally publish a new pointer."""
    root, output = Path(repository_root).resolve(), Path(output_dir).resolve()
    plan_path, token_path = output / "approval_plan.json", output / "approval_token.txt"
    if not plan_path.is_file() or not token_path.is_file():
        return build_approval_plan(
            preview_manifest_path, repository_root=root, output_dir=output,
            now_utc=now_utc,
        )
    old_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    unsigned = dict(old_plan)
    declared = str(unsigned.pop("manifest_sha256", ""))
    if set(old_plan) != APPROVAL_PLAN_KEYS or canonical_sha256(unsigned) != declared:
        raise StateDailyUpdateApprovalError("old approval plan cannot be safely archived")
    verify_daily_update_preview(preview_manifest_path, repository_root=root)
    archive = output / "archive" / str(old_plan["request_id"])
    archive.mkdir(parents=True, exist_ok=True)
    archived_plan, archived_token = archive / plan_path.name, archive / token_path.name
    for source, destination in ((plan_path, archived_plan), (token_path, archived_token)):
        if destination.exists() and destination.read_bytes() != source.read_bytes():
            raise StateDailyUpdateApprovalError("immutable approval archive collision")
        if not destination.exists():
            shutil.copy2(source, destination)
    held_plan, held_token = output / ".approval_plan.superseded", output / ".approval_token.superseded"
    os.replace(plan_path, held_plan)
    os.replace(token_path, held_token)
    try:
        result = build_approval_plan(
            preview_manifest_path, repository_root=root, output_dir=output,
            now_utc=now_utc,
        )
    except Exception:
        if plan_path.exists():
            plan_path.unlink()
        if token_path.exists():
            token_path.unlink()
        os.replace(held_plan, plan_path)
        os.replace(held_token, token_path)
        raise
    held_plan.unlink()
    held_token.unlink()
    return result


def apply_approved_plan(
    plan_path: str | Path, *, repository_root: str | Path,
    approval_token: str, apply: bool = False, now_utc: Any | None = None,
) -> dict[str, Any]:
    """Plan by default; one exact state write only with --apply and matching token."""
    verified = verify_approval_plan(
        plan_path, repository_root=repository_root, now_utc=now_utc,
    )
    plan, preview = verified["plan"], verified["preview"]
    result = {
        "schema_version": 1,
        "manifest_type": "state_daily_update_approval_application",
        "status": "PLAN_VERIFIED_NOT_APPLIED",
        "request_id": plan["request_id"],
        "session_date": plan["session_date"],
        "approval_token_matched": bool(
            approval_token
            and hashlib.sha256(approval_token.encode("utf-8")).hexdigest()
            == plan["approval_token_sha256"]
        ),
        "apply_requested": bool(apply),
        "state_written": False,
        "broker_written": False,
        "config_written": False,
        "orders_created": False,
    }
    if not apply:
        return result
    if not result["approval_token_matched"]:
        raise StateDailyUpdateApprovalError("explicit one-time approval token mismatch")
    state_path = preview["expected_inputs"]["state"]
    config_path = preview["expected_inputs"]["config"]
    broker_path = preview["expected_inputs"]["broker"]
    expected_hashes = {
        name: str(plan["expected_live_inputs"][name]["sha256"])
        for name in ("state", "config", "broker")
    }
    if any(
        file_sha256(preview["expected_inputs"][name]) != expected_hashes[name]
        for name in ("state", "config", "broker")
    ):
        raise StateDailyUpdateApprovalError("live input drifted immediately before state write")
    consumed = verified["consumed_marker"]
    consumption = {
        "schema_version": 1,
        "manifest_type": "state_daily_update_approval_consumption",
        "request_id": plan["request_id"],
        "session_date": plan["session_date"],
        "consumed_at_utc": (
            _aware_utc(now_utc, "approval consumption time").isoformat()
            if now_utc is not None else datetime.now(timezone.utc).isoformat()
        ),
        "state_before_sha256": expected_hashes["state"],
        "state_after_sha256": file_sha256(state_path),
        "broker_sha256": expected_hashes["broker"],
        "config_sha256": expected_hashes["config"],
        "orders_created": False,
    }
    consumption["record_sha256"] = canonical_sha256(consumption)
    try:
        save_portfolio(preview["proposed"], state_path)
        if file_sha256(state_path) != file_sha256(preview["paths"]["proposed"]):
            raise StateDailyUpdateApprovalError("applied state differs from approved proposed state")
        if (
            file_sha256(config_path) != expected_hashes["config"]
            or file_sha256(broker_path) != expected_hashes["broker"]
        ):
            raise StateDailyUpdateApprovalError("config/broker changed during approved state write")
        consumed.parent.mkdir(parents=True, exist_ok=True)
        with consumed.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(consumption, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception as exc:
        if consumed.exists():
            consumed.unlink()
        rollback_bytes = preview["paths"]["rollback"].read_bytes()
        temporary = state_path.with_suffix(state_path.suffix + ".approved-rollback.tmp")
        with temporary.open("wb") as handle:
            handle.write(rollback_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, state_path)
        if file_sha256(state_path) != expected_hashes["state"]:
            raise StateDailyUpdateApprovalError(
                f"post-write failure and rollback verification failed: {exc}"
            ) from exc
        raise StateDailyUpdateApprovalError(
            f"post-write failure; approved rollback restored: {exc}"
        ) from exc
    audit_log(
        "approved_state_daily_update",
        {
            "request_id": plan["request_id"],
            "session_date": plan["session_date"],
            "state_before_sha256": expected_hashes["state"],
            "state_after_sha256": file_sha256(state_path),
            "broker_confirmation_sha256": expected_hashes["broker"],
            "orders_created": False,
        },
        "一次性显式批准：仅推进已审阅策略时钟，不创建订单",
    )
    result.update({
        "status": "APPLIED_EXACT_USER_APPROVED_STATE_TRANSITION",
        "state_written": True,
    })
    return result


__all__ = [
    "StateDailyUpdateApprovalError", "apply_approved_plan",
    "build_approval_plan", "canonical_sha256", "refresh_approval_plan",
    "verify_approval_plan",
    "verify_daily_update_preview",
]
