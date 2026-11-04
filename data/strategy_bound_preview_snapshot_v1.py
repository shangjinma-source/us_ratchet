"""Return advice and its final verified UI snapshot in one operation.

Explicit composition only; existing routes are unchanged until wired in a release.
The supplied projector must be the account API's pure projection, never a fetch.
"""
from copy import deepcopy

from api.strategy_frontier_monthly_target_v1 import compact
from core.strategy_account_difference import require, timestamp


class BoundPreviewSnapshotV1:
    def __init__(self, *, observed, project_account, validate_sources=None):
        self.observed = observed
        self.monthly = observed.monthly
        self.project_account = project_account
        self.validate_sources = validate_sources or observed.validate_sources

    def preview(self, *, expected_revision, target_id, expected_proposal_id):
        with self.monthly.snapshot_operation():
            self.validate_sources()
            state = deepcopy(self.monthly.accounts.read())
            target = deepcopy(self.monthly.current())
            require(state is not None and state['revision'] == expected_revision,
                    'STALE_REVISION')
            require(target is not None and target['target_id'] == target_id and
                    target['proposal_id'] == expected_proposal_id, 'STALE_TARGET')
            month = self.monthly._month()
            response = deepcopy(self.observed.preview(expected_revision=expected_revision,
                target_id=target_id, expected_proposal_id=expected_proposal_id))
            generated = self.observed.clock()
            require(response.get('account_revision') == expected_revision and
                    response.get('target_id') == target_id and
                    response.get('proposal_id') == expected_proposal_id,
                    'FRONTIER_RESPONSE_BINDING_MISMATCH')
            projected = self.project_account(deepcopy(state))
            require(projected.get('status') == 'READY' and
                    projected['account']['revision'] == expected_revision,
                    'SNAPSHOT_ACCOUNT_PROJECTION_MISMATCH')
            display = compact(target)
            prior = display['target_month']
            display.update(server_month=month, configuration_reason=(
                'MONTHLY_SELECTION' if prior < month else
                'EXPLICIT_RECONFIGURE' if prior == month else None))
            # Projection may take time or allow concurrent database writers.
            # Recheck after projection and journal work, not just before preview.
            self.validate_sources()
            require(self.monthly.accounts.read() == state and
                    self.monthly.current() == target and self.monthly._month() == month,
                    'SNAPSHOT_CHANGED_DURING_PREVIEW')
            checked = self.observed.clock()
            require(checked.utcoffset() is not None, 'AWARE_SERVER_CLOCK_REQUIRED')
            require(checked >= generated, 'CLOCK_MOVED_BACKWARDS')
            status = response.get('status')
            require(status in {'READY', 'HOLD', 'WAIT'}, 'ADVICE_STATUS_INVALID')
            if status != 'WAIT':
                require(prior == month, 'FRONTIER_TARGET_MONTH')
                signal = response.get('risk_projection', {}).get('signal', {})
                valid_from = response.get('risk_valid_from', signal.get('valid_from'))
                valid_until = response.get('risk_valid_until', signal.get('valid_until'))
                require(valid_from is not None and valid_until is not None and
                        timestamp(valid_from) <= checked < timestamp(valid_until),
                        'RISK_ADVICE_EXPIRED')
            if status != 'READY':
                require(not response.get('new_orders') and not response.get('reference_quotes')
                        and not response.get('difference', {}).get('new_orders'),
                        'NONREADY_EXECUTION_FIELDS_FORBIDDEN')
            for quote in response.get('reference_quotes', {}).values():
                require(timestamp(quote['observed_at']) <= checked <
                        timestamp(quote['reference_valid_until']), 'ADVICE_EXPIRED')
            for order in response.get('new_orders', []):
                require(order['security_id'] in response.get('reference_quotes', {}),
                        'ADVICE_QUOTE_REQUIRED')
                if 'reference_valid_until' in order:
                    require(checked < timestamp(order['reference_valid_until']), 'ADVICE_EXPIRED')
            response['verified_snapshot'] = dict(schema='BOUND_PREVIEW_SNAPSHOT_V1',
                account=deepcopy(projected['account']), target=display,
                checked_at=checked.isoformat())
            return response
