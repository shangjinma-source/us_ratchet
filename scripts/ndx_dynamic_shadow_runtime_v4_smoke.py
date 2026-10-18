"""Read-only artifact smoke, not proof that a Windows Scheduled Task executed.

The future installer must establish task execution independently. Empty runs
before the contract's first decision cannot certify economic execution.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_daily_v3 import verify_daily_run_manifest
from backtest.ndx_dynamic_shadow_daily_economic_replay import verify_daily_economic_replay
from backtest.ndx_dynamic_shadow_daily import load_daily_contract
from scripts import ndx_dynamic_shadow_fresh_search_v4 as acceptance

LATEST = Path("data/cache/research/ndx_dynamic_shadow_daily_v1/latest_run.json")
CONTRACT = Path("config/ndx_dynamic_shadow_daily_v1.yaml")
PROTECTED = ("config/config.yaml", "data/state.json", "data/broker_positions.json")
SNAPSHOT_FIELDS = {"schema_version", "captured_at_utc", "latest_run_path", "latest_run_sha256", "protected_live_sha256"}
PENDING_PHASES = {"WAIT_FOR_NEXT_OBSERVED_SESSION"}


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _pairs(items):
    output = {}
    for key, value in items:
        if key in output:
            raise ValueError("duplicate JSON field")
        output[key] = value
    return output


def _read_json(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def _time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone aware")
    return parsed.astimezone(timezone.utc)


def _date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("date must be canonical ISO date")
    return date.fromisoformat(value)


def _protected(root):
    return {name: _hash((root / name).read_bytes()) for name in PROTECTED}


def _protected_schema(value):
    if not isinstance(value, dict) or set(value) != set(PROTECTED) or any(
            not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for digest in value.values()):
        raise ValueError("protected live hash inventory invalid")


def snapshot(root):
    root = Path(root).resolve()
    path = (root / LATEST).resolve()
    before = _protected(root)
    raw = path.read_bytes() if path.is_file() else None
    captured = datetime.now(timezone.utc).isoformat()
    repeated = path.read_bytes() if path.is_file() else None
    if repeated != raw or _protected(root) != before:
        raise ValueError("snapshot inputs changed while reading")
    return {"schema_version": 1, "captured_at_utc": captured,
            "latest_run_path": path.as_posix(), "latest_run_sha256": _hash(raw) if raw is not None else None,
            "protected_live_sha256": before}


def _level(manifest, root):
    contract_path = root / CONTRACT
    contract_raw = contract_path.read_bytes()
    contract = load_daily_contract(contract_path)
    first = _date(str(contract["schedule_contract"]["first_decision_not_before"]))
    latest = _date(manifest["latest_observed_session"])
    for key in ("independent_lane_count", "realized_decision_batches", "benchmark_control_count"):
        if type(manifest[key]) is not int or manifest[key] < 0:
            raise ValueError("run economic counts must be nonnegative integers")
    phases = manifest["decision_phases"]
    if not isinstance(phases, list):
        raise ValueError("decision phases must be a list")
    for phase in phases:
        if not isinstance(phase, dict) or set(phase) != {"decision_date", "phase"}:
            raise ValueError("decision phase schema invalid")
        if not first <= _date(phase["decision_date"]) <= latest or not isinstance(phase["phase"], str):
            raise ValueError("decision phase coordinate invalid")
    if len({phase["decision_date"] for phase in phases}) != len(phases):
        raise ValueError("duplicate decision phase")
    batches, lanes, controls = (manifest[key] for key in ("realized_decision_batches", "independent_lane_count", "benchmark_control_count"))
    economic = None
    if batches:
        if lanes != 10 or controls != 2 or not phases:
            raise ValueError("economic run lacks complete lanes and controls")
        economic = verify_daily_economic_replay(manifest, repository_root=root)
        if (economic.get("economic_replay_verified") is not True
                or type(economic.get("economic_lane_count")) is not int
                or economic["economic_lane_count"] != 11
                or type(economic.get("verified_rows")) is not int or economic["verified_rows"] < 11):
            raise ValueError("eleven economic lanes were not independently rebuilt")
        level = "ECONOMIC_PATHS_VERIFIED"
    elif lanes or controls:
        raise ValueError("economic paths without a realized decision")
    elif not phases and latest < first and _time(manifest["generated_at"]).date() < first:
        level = "PRE_DECISION_OPERATIONAL_ONLY"
    elif phases and all(phase["phase"] in PENDING_PHASES for phase in phases):
        for phase in phases:
            decision = phase["decision_date"]
            if _date(decision) != latest:
                raise ValueError("pending decision already has a later observed session")
            receipt_path = root / acceptance.ACCEPTANCE / decision / "receipt.json"
            receipt_raw = receipt_path.read_bytes()
            receipt = acceptance.verify_acceptance(receipt_path)
            final = (root / acceptance.SEARCH / "final" / decision / "manifest.json").resolve()
            if (receipt.get("decision_date") != decision
                    or Path(receipt["final_binding"]["path"]).resolve() != final
                    or receipt["final_binding"]["sha256"] != _hash(final.read_bytes())
                    or receipt_path.read_bytes() != receipt_raw):
                raise ValueError("pending decision receipt binding changed")
        level = "DECISION_PENDING_EXECUTION"
    else:
        raise ValueError("run does not prove a valid pre-decision or pending stage")
    if contract_path.read_bytes() != contract_raw:
        raise ValueError("daily contract changed during stage verification")
    return level, first.isoformat(), economic


def verify(root, before=None, expected=None):
    if (before is None) == (expected is None):
        raise ValueError("exactly one before snapshot or expected proof is required")
    root = Path(root).resolve()
    path = (root / LATEST).resolve()
    protected = _protected(root)
    raw = path.read_bytes()
    digest = _hash(raw)
    parsed = _read_json(raw)
    if not isinstance(parsed, dict):
        raise ValueError("daily manifest must be an object")
    generated = _time(parsed["generated_at"])
    now = datetime.now(timezone.utc)
    if generated > now:
        raise ValueError("daily run timestamp is in the future")
    if before is not None:
        if (not isinstance(before, dict) or set(before) != SNAPSHOT_FIELDS
                or type(before["schema_version"]) is not int or before["schema_version"] != 1
                or before["latest_run_path"] != path.as_posix()):
            raise ValueError("before snapshot schema or canonical path invalid")
        prior = before["latest_run_sha256"]
        if prior is not None and (not isinstance(prior, str) or re.fullmatch(r"[0-9a-f]{64}", prior) is None):
            raise ValueError("before snapshot run digest invalid")
        captured = _time(before["captured_at_utc"])
        if captured > now or generated < captured or prior == digest:
            raise ValueError("no fresh canonical daily run from this smoke")
        _protected_schema(before["protected_live_sha256"])
        if _json(before["protected_live_sha256"]) != _json(protected):
            raise ValueError("protected live files changed since snapshot")
    elif not isinstance(expected, dict):
        raise ValueError("expected proof must be an object")
    verified = verify_daily_run_manifest(path, repository_root=root)
    if _json(verified) != _json(parsed):
        raise ValueError("daily verifier returned a different manifest")
    level, first, economic = _level(parsed, root)
    if _json(verify_daily_run_manifest(path, repository_root=root)) != _json(parsed):
        raise ValueError("daily sources changed after stage verification")
    if path.read_bytes() != raw or _protected(root) != protected:
        raise ValueError("daily or protected live bytes changed during verification")
    proof = {"schema_version": 1, "latest_run_path": path.as_posix(), "latest_run_sha256": digest,
             "run_generated_at": parsed["generated_at"], "run_manifest_sha256": parsed["run_manifest_sha256"],
             "status": parsed["status"], "latest_observed_session": parsed["latest_observed_session"],
             "independent_lane_count": parsed["independent_lane_count"],
             "realized_decision_batches": parsed["realized_decision_batches"],
             "evidence_level": level, "first_decision_not_before": first,
             "protected_live_sha256": protected, "economic_replay": economic,
             "full_daily_v3_verifier_replayed": True, "task_execution_verified_by_this_tool": False,
             "promotion_allowed": False, "live_mutation_allowed": False,
             "orders_allowed": False, "artifact_only": True}
    if expected is not None and _json(expected) != _json(proof):
        raise ValueError("expected smoke proof changed or was superseded")
    return proof


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--snapshot", action="store_true")
    mode.add_argument("--verify", action="store_true")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--before-path", type=Path)
    source.add_argument("--expected-path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.snapshot:
            if args.before_path or args.expected_path:
                raise ValueError("snapshot accepts no proof input")
            result = snapshot(ROOT)
        elif args.before_path:
            result = verify(ROOT, before=_read_json(args.before_path.read_text(encoding="utf-8-sig")))
        elif args.expected_path:
            result = verify(ROOT, expected=_read_json(args.expected_path.read_text(encoding="utf-8-sig")))
        else:
            raise ValueError("verify requires --before-path or --expected-path")
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"runtime-v4 artifact smoke failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
