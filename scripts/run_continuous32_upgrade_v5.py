"""Explicit reviewed new attempt using V4 transport and blob-backed upgrade V2."""
import argparse
from copy import copy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from core.strategy_account_ledger import canonical, require
from core.strategy_session_target_store_v1 import SessionGuardedTargetStoreV1
from data.strategy_continuous32_upgrade import upgrade_snapshot_provider
from data.strategy_continuous32_upgrade_v2 import Continuous32ResearchUpgradeV2 as Continuous32ResearchUpgrade
from data.strategy_upgrade_recovery_review_v1 import validate_recovery_review
from data.strategy_profiled_server_preparation import build_preparation
from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
from data.strategy_upgrade_action_transport_v4 import PinnedUpgradeActionTransportV4
from scripts import run_continuous32_upgrade as original
from scripts.register_quantity_v2_paper_protocol import safe_path


def run(args):
    recovery_reference=dict(path=args.recovery_path,sha256=args.recovery_sha256)
    root=Path(args.root).resolve()
    package_raw=safe_path(root,args.package_path).read_bytes()
    require(len(package_raw)<=1024*1024 and sha256(package_raw).hexdigest()==args.package_sha256,'UPGRADE_PACKAGE_CHANGED')
    initial_package=json.loads(package_raw)
    from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
    targets=StrategyMonthlyTargetStore(root/'data/strategy_account/monthly_targets.sqlite3')
    def recovery_gate():
        validate_recovery_review(root=root,reference=recovery_reference,package=initial_package,targets=targets)
        for name in ('scripts/run_continuous32_upgrade_v5.py',
                     'data/strategy_upgrade_recovery_review_v1.py',
                     'data/strategy_continuous32_upgrade_v2.py',
                     'data/strategy_upgrade_blob_store_v1.py'):
            expected=initial_package['source_hashes'].get(name)
            require(expected and sha256(safe_path(root,name).read_bytes()).hexdigest()==expected
                    and sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest()==expected,
                    'UPGRADE_V5_IMPLEMENTATION_CHANGED')
    recovery_gate()
    path = getattr(args, 'action_transport_path', None)
    digest = getattr(args, 'action_transport_sha256', None)
    require(bool(path) == bool(digest), 'ACTION_TRANSPORT_REFERENCE_PAIR_REQUIRED')
    require(bool(path), 'ACTION_TRANSPORT_REFERENCE_REQUIRED')
    root = Path(args.root).resolve()
    transport = PinnedUpgradeActionTransportV4(root=root,
        configuration_path=path, configuration_sha256=digest)
    if not args.execute and not args.preflight:
        offline = copy(args)
        offline.action_transport_path = offline.action_transport_sha256 = None
        result = original.run(offline)
        transport.validate()
        recovery_gate()
        return result
    clock = original.regular_session_clock(root)
    clock()
    preparation = build_preparation(root=root, configuration_path=args.configuration_path,
                                    configuration_sha256=args.configuration_sha256)
    package_path = safe_path(root, args.package_path)
    with package_path.open('rb') as stream:
        package_raw = stream.read(1024*1024+1)
    require(len(package_raw) <= 1024*1024 and sha256(package_raw).hexdigest() == args.package_sha256,
            'UPGRADE_PACKAGE_CHANGED')
    package = json.loads(package_raw)
    def gate():
        recovery_gate()
        preparation['validate_code']()
        transport.validate()
        require(package_path.read_bytes() == package_raw, 'UPGRADE_PACKAGE_CHANGED')
        source = 'data/strategy_continuous32_upgrade.py'
        require(sha256(safe_path(root, source).read_bytes()).hexdigest()
                == package['source_hashes'][source], 'UPGRADE_IMPLEMENTATION_CHANGED')
    snapshot = upgrade_snapshot_provider(root=root, package_path=args.package_path,
        package_sha256=args.package_sha256, base_provider=preparation['activation'].snapshot,
        clock=clock, validate_code=gate)
    monthly = ProfiledRollingMonthlyRuntimeRouter(root=root, initial_snapshot=snapshot(),
        snapshot_provider=snapshot, clock=clock, runtime_builder=transport.build_runtime)
    monthly.targets = SessionGuardedTargetStoreV1(monthly.targets.path, root=root,
        calendar_path=original.SESSION_CALENDAR_PATH,
        calendar_sha256=original.SESSION_CALENDAR_SHA256, clock=clock)
    upgrade = Continuous32ResearchUpgrade(monthly=monthly, package_path=args.package_path,
        package_sha256=args.package_sha256, validate_code=gate)
    result = (upgrade.execute if args.execute else upgrade.preflight)(
        event_id=package['upgrade_event_id'])
    gate()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'configuration-path', 'configuration-sha256',
                 'package-path', 'package-sha256', 'receipt-path', 'recovery-path', 'recovery-sha256'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--action-transport-path')
    parser.add_argument('--action-transport-sha256')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if bool(args.action_transport_path) != bool(args.action_transport_sha256):
        parser.error('action transport path and SHA256 must be provided together')
    path = safe_path(Path(args.root).resolve(), args.receipt_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    base = dict(mode='execute' if args.execute else 'preflight' if args.preflight else 'offline',
        entrypoint='CONTINUOUS32_UPGRADE_V5', configuration_sha256=args.configuration_sha256,
        package_sha256=args.package_sha256,
        recovery_review=dict(path=args.recovery_path,sha256=args.recovery_sha256),
        action_transport=dict(path=args.action_transport_path, sha256=args.action_transport_sha256)
        if args.action_transport_path else None)
    with path.open('x', encoding='utf8') as stream:
        stream.write(json.dumps(dict(base, status='STARTED',
            started_at=datetime.now(timezone.utc).isoformat()))+'\n')
        stream.flush()
        try:
            result = run(args)
            terminal = dict(base, status='COMPLETED', result=result)
            code = 0
        except Exception as error:
            message = str(error) if type(error) is ValueError else ''
            terminal = dict(base, status='FAILED_PRESERVED',
                error_type=type(error).__name__,
                error=message if message.replace('_', '').isalnum() and len(message) < 160
                else 'UPGRADE_UNAVAILABLE')
            code = 2
        terminal['finished_at'] = datetime.now(timezone.utc).isoformat()
        stream.write(json.dumps(terminal)+'\n')
        stream.flush()
    print(json.dumps(terminal))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
