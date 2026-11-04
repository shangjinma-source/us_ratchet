"""Read current account, target and advice in one verified snapshot operation.

No account/target writes or implicit target generation. Explicit composition
only; the bound preview retains its final source, identity and expiry checks.
"""
from copy import deepcopy

from api.strategy_frontier_monthly_target_v1 import compact
from core.strategy_account_ledger import require


class CurrentPreviewV1:
    def __init__(self, *, bound_preview):
        self.bound = bound_preview
        self.monthly = bound_preview.monthly

    def read(self, *, expected_revision=None):
        with self.monthly.snapshot_operation():
            self.bound.validate_sources()
            state = deepcopy(self.monthly.accounts.read())
            target = deepcopy(self.monthly.current())
            month = self.monthly._month()
            require(state is not None, 'ACCOUNT_NOT_INITIALIZED')
            require(expected_revision is None or state['revision'] == expected_revision,
                    'STALE_REVISION')
            # Never compute an old-month proposal or silently create a new one.
            if target is not None and target['payload']['target_month'] == month:
                daily = self.bound.preview(expected_revision=state['revision'],
                    target_id=target['target_id'], expected_proposal_id=target['proposal_id'])
                snapshot = daily['verified_snapshot']
                return dict(schema='CURRENT_ADVICE_READ_V1',
                    account=deepcopy(snapshot['account']), target=deepcopy(snapshot['target']),
                    daily=deepcopy(daily), orders_created=False, account_mutated=False)

            projected = self.bound.project_account(deepcopy(state))
            require(projected.get('status') == 'READY' and
                    projected['account']['revision'] == state['revision'],
                    'SNAPSHOT_ACCOUNT_PROJECTION_MISMATCH')
            display = compact(target)
            prior = target['payload']['target_month'] if target else None
            display.update(server_month=month, configuration_reason=(
                'INITIAL' if prior is None else 'MONTHLY_SELECTION' if prior < month else None))
            self.bound.validate_sources()
            require(self.monthly.accounts.read() == state and self.monthly.current() == target
                    and self.monthly._month() == month, 'SNAPSHOT_CHANGED_DURING_PREVIEW')
            return dict(schema='CURRENT_ADVICE_READ_V1', account=deepcopy(projected['account']),
                target=display, daily=None, orders_created=False, account_mutated=False)
