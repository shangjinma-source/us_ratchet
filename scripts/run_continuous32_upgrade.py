"""Explicit research-version upgrade; defaults to offline binding checks.

Source preflight and one-shot selection require separate explicit switches.
No clock override, cash event, broker order or automatic retry is provided.
"""
import argparse
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, require
from core.strategy_session_target_store_v1 import SessionGuardedTargetStoreV1
from data.strategy_continuous32_upgrade import (
    Continuous32ResearchUpgrade, upgrade_snapshot_provider,
)
from data.strategy_profiled_server_preparation import build_preparation
from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
from data.strategy_profiled_runtime_archive import require_archived_configuration
from data.strategy_continuous32_target_decision import PROFILE_ID
from scripts.register_quantity_v2_paper_protocol import safe_path

SESSION_CALENDAR_PATH = "research_contracts/daily_calendar_2026_extension_v1/calendar.candidate.json"
SESSION_CALENDAR_SHA256 = "1440d82ecc956baab15df4b49da444e4878459e353cf7c280dd5d3dcf2a109af"


def regular_session_clock(root, clock=None):
    """Server-fixed calendar; injection is for tests, never a CLI option."""
    source = clock or (lambda: datetime.now(timezone.utc))
    previous = None
    def checked():
        nonlocal previous
        path = safe_path(Path(root), SESSION_CALENDAR_PATH)
        with path.open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024
                and sha256(raw).hexdigest() == SESSION_CALENDAR_SHA256,
                "UPGRADE_SESSION_CALENDAR_CHANGED")
        calendar = json.loads(raw)
        require(calendar["schema"] == "FIXED_EXCHANGE_SESSIONS_V1"
                and calendar["exchange"] == "NASDAQ", "UPGRADE_SESSION_CALENDAR_SCHEMA")
        now = source()
        require(isinstance(now, datetime) and now.utcoffset() is not None,
                "AWARE_SERVER_CLOCK_REQUIRED")
        require(previous is None or now >= previous, "UPGRADE_SERVER_CLOCK_ROLLBACK")
        day = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        rows = [row for row in calendar["sessions"] if row["date"] == day]
        require(len(rows) == 1, "UPGRADE_NO_REGULAR_SESSION")
        opening, closing = (datetime.fromisoformat(rows[0][key]) for key in ("open", "close"))
        require(opening <= now < closing, "UPGRADE_OUTSIDE_REGULAR_SESSION")
        previous = now
        return now
    return checked


def run(args):
    root = Path(args.root).resolve()
    clock = (regular_session_clock(root) if args.execute or args.preflight
             else lambda: datetime.now(timezone.utc))
    # Refuse before constructing the source provider or making HTTP requests.
    clock()
    transport_path=getattr(args,'action_transport_path',None)
    transport_sha=getattr(args,'action_transport_sha256',None)
    require(bool(transport_path)==bool(transport_sha),'ACTION_TRANSPORT_REFERENCE_PAIR_REQUIRED')
    transport=None
    if transport_path:
        from data.strategy_upgrade_action_transport_v2 import PinnedUpgradeActionTransportV2
        transport=PinnedUpgradeActionTransportV2(root=root,configuration_path=transport_path,configuration_sha256=transport_sha)
    preparation = build_preparation(
        root=root, configuration_path=args.configuration_path,
        configuration_sha256=args.configuration_sha256,
    )
    package_path = safe_path(root, args.package_path)
    package_raw = package_path.read_bytes()
    require(len(package_raw) <= 1024 * 1024
            and sha256(package_raw).hexdigest() == args.package_sha256,
            "UPGRADE_PACKAGE_CHANGED")
    package = json.loads(package_raw)

    def gate():
        preparation["validate_code"]()
        if transport is not None: transport.validate()
        require(package_path.read_bytes() == package_raw, "UPGRADE_PACKAGE_CHANGED")
        source = "data/strategy_continuous32_upgrade.py"
        require(sha256(safe_path(root, source).read_bytes()).hexdigest()
                == package["source_hashes"][source], "UPGRADE_IMPLEMENTATION_CHANGED")

    snapshot = upgrade_snapshot_provider(
        root=root, package_path=args.package_path,
        package_sha256=args.package_sha256,
        base_provider=preparation["activation"].snapshot,
        clock=clock, validate_code=gate,
    )
    monthly = ProfiledRollingMonthlyRuntimeRouter(
        root=root, initial_snapshot=snapshot(),
        snapshot_provider=snapshot, clock=clock,
        **({"runtime_builder":transport.build_runtime} if transport is not None else {}),
    )
    monthly.targets = SessionGuardedTargetStoreV1(
        monthly.targets.path, root=root, calendar_path=SESSION_CALENDAR_PATH,
        calendar_sha256=SESSION_CALENDAR_SHA256, clock=clock,
    )
    upgrade = Continuous32ResearchUpgrade(
        monthly=monthly, package_path=args.package_path,
        package_sha256=args.package_sha256, validate_code=gate,
    )
    if args.execute or args.preflight:
        result=(upgrade.execute if args.execute else upgrade.preflight)(event_id=package["upgrade_event_id"])
        gate()
        return result

    # Offline check never invokes a market provider, selector or ledger append.
    with monthly.snapshot_operation():
        upgrade._package()
        account = monthly.accounts.read()
        target = monthly.current()
        require(account and account["revision"] == package["account_revision"],
                "UPGRADE_STALE_ACCOUNT")
        require(target and target["target_id"] == package["previous_target_id"],
                "UPGRADE_STALE_TARGET")
        _, configuration = monthly._for_target(target)
        require(sha256(canonical(configuration)).hexdigest()
                == package["original_configuration_sha256"],
                "UPGRADE_ORIGINAL_CONFIGURATION_CHANGED")
        reference = package["upgraded_configuration"]
        with safe_path(root, reference["path"]).open("rb") as source:
            upgraded_raw = source.read(1024 * 1024 + 1)
        require(len(upgraded_raw) <= 1024 * 1024
                and sha256(upgraded_raw).hexdigest() == reference["sha256"],
                "UPGRADE_CONFIGURATION_CHANGED")
        upgraded = json.loads(upgraded_raw)
        require(upgraded["schema"] == "REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1"
                and upgraded["selector_profile"] == PROFILE_ID,
                "UPGRADE_PROFILE_REQUIRED")
        for key in ("target_month", "training_manifest", "training_sha256",
                    "training_closed_at", "identity_manifest", "identity_sha256"):
            require(upgraded[key] == configuration[key], "UPGRADE_SAVED_DATA_CHANGED")
        require_archived_configuration(
            root=root, archive_path=monthly.archive_path,
            archive_sha256=monthly.archive_sha256, configuration=upgraded,
        )
        monthly._runtime(upgraded).selection._pins()
        gate()
        return {
            "status": "OFFLINE_BINDINGS_MATCH_NOT_SOURCE_PREFLIGHT",
            "account_revision": account["revision"],
            "previous_target_id": target["target_id"],
            "selection_started": False,
            "market_capture_requested": False,
            "target_write_requested": False,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "configuration-path", "configuration-sha256",
                 "package-path", "package-sha256", "receipt-path"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--action-transport-path")
    parser.add_argument("--action-transport-sha256")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if bool(args.action_transport_path)!=bool(args.action_transport_sha256):
        parser.error("--action-transport-path and --action-transport-sha256 must be supplied together")
    receipt_path = safe_path(Path(args.root).resolve(), args.receipt_path)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    # Reserve a new receipt before any operation; never overwrite an earlier run.
    with receipt_path.open("x", encoding="utf-8") as stream:
        receipt = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "mode": "execute" if args.execute else "preflight" if args.preflight else "offline",
            "configuration_sha256": args.configuration_sha256,
            "package_sha256": args.package_sha256,
            "action_transport": ({"path":args.action_transport_path,"sha256":args.action_transport_sha256}
                                 if args.action_transport_path else None),
        }
        stream.write(json.dumps(dict(receipt, status="STARTED")) + "\n")
        stream.flush()
        exit_code = 0
        try:
            receipt["result"] = run(args)
            receipt["status"] = "COMPLETED"
        except Exception as error:
            receipt.update(status="FAILED_PRESERVED", error_type=type(error).__name__,
                           error=str(error))
            exit_code = 1
        receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
        stream.write(json.dumps(receipt, ensure_ascii=False) + "\n")
        stream.flush()
    print(json.dumps({key: receipt[key] for key in
                      ("status", "mode", "finished_at")}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
