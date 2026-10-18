"""Adopt a reviewed monthly data package using a fixed deployment descriptor.

This command changes only the release pointer, never holdings, cash, targets,
or orders. Production time comes from the system; no clock override is exposed.
"""
from pathlib import Path

from core.strategy_account_ledger import require
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate
from data.strategy_account_release_activation import MonthlyReleaseActivation, SNAPSHOT_FIELDS
from scripts.prepare_real_monthly_release import _read


SCRIPT_PATH = 'scripts/activate_real_monthly_release.py'


def activate(*, root, descriptor_path, descriptor_sha256, receipt_path,
             receipt_sha256, expected_release_revision):
    # Import only the declared scope. Importing the factory does not mount it.
    from api.strategy_rolling_composition import ROLLING_SOURCE_PATHS
    root = Path(root).absolute()
    descriptor = _read(root, descriptor_path, descriptor_sha256)
    pins = descriptor['source_pins']
    require(type(pins) is dict and ROLLING_SOURCE_PATHS | {SCRIPT_PATH} <= set(pins),
            'ACTIVATION_DEPLOYMENT_SOURCE_SCOPE_REQUIRED')
    gate = bind_dynamic_source_gate(root=root, source_pins=pins)
    service = MonthlyReleaseActivation(root=root,
        initial_snapshot={key:descriptor[key] for key in SNAPSHOT_FIELDS}, validate_code=gate)
    result = service.adopt(receipt_path=receipt_path, receipt_sha256=receipt_sha256,
        expected_release_revision=expected_release_revision)
    return dict(status='MONTHLY_DATA_RELEASE_ADOPTED', release_revision=result['revision'],
        target_month=result['payload']['target_month'], account_writes=False,
        target_created=False, orders_created=False)


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root','descriptor-path','descriptor-sha256','receipt-path','receipt-sha256'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--expected-release-revision', required=True, type=int)
    arguments = vars(parser.parse_args(argv))
    try:
        result = activate(**arguments)
    except Exception:
        # An interrupted response is not proof that the pointer was unchanged.
        # The next invocation must read the current release before retrying.
        print(json.dumps(dict(status='BLOCKED', reason='MONTHLY_ACTIVATION_REJECTED',
            reconcile_release_before_retry=True, account_writes=False, orders_created=False)))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
