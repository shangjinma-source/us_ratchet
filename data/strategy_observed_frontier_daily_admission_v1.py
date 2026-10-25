"""Proposal-bound generation audit with final post-journal admission checks."""
from copy import deepcopy
from hashlib import sha256
import sqlite3
from uuid import uuid4

from core.strategy_account_difference import require, timestamp
from data.strategy_daily_advice_journal_v1 import encoded


class ObservedFrontierDailyAdmission:
    def __init__(self, *, service, monthly, journal, clock, validate_sources, policy_references):
        self.service, self.monthly, self.journal, self.clock = service, monthly, journal, clock
        self.validate_sources = validate_sources
        self.policy_references = deepcopy(policy_references)

    def preview(self, *, expected_revision, target_id, expected_proposal_id):
        with self.monthly.snapshot_operation():
            return self._preview(expected_revision=expected_revision, target_id=target_id,
                                 expected_proposal_id=expected_proposal_id)

    def _preview(self, *, expected_revision, target_id, expected_proposal_id):
        started = self.clock()
        self.validate_sources()
        state = deepcopy(self.monthly.accounts.read())
        target = deepcopy(self.monthly.current())
        require(state is not None and target is not None
                and state['revision'] == expected_revision and target['target_id'] == target_id
                and target.get('proposal_id') == expected_proposal_id, 'STALE_SNAPSHOT')
        response = deepcopy(self.service.preview(expected_revision=expected_revision,
            target_id=target_id, expected_proposal_id=expected_proposal_id))
        generated = self.clock()
        require(started <= generated, 'CLOCK_MOVED_BACKWARDS')
        require(response.get('status') in {'READY', 'HOLD', 'WAIT'}, 'ADVICE_STATUS_INVALID')
        require(response.get('account_revision') == expected_revision
                and response.get('target_id') == target_id
                and response.get('proposal_id') == expected_proposal_id, 'ADVICE_BINDING_MISMATCH')
        event = dict(schema='DAILY_GENERATED_ADVICE_V1', event_id=uuid4().hex,
            account_id=state['account_id'], account_revision=expected_revision, target_id=target_id,
            target_month=target['payload'].get('target_month'), started_at=started.isoformat(),
            generated_at=generated.isoformat(), response=response,
            response_sha256=sha256(encoded(response)).hexdigest(),
            policy_references=deepcopy(self.policy_references), displayed=False,
            evidence_complete=False, followup_status='NOT_ADMITTED')

        def checked_result():
            result = deepcopy(response)
            try:
                self.validate_sources()
                require(self.monthly.accounts.read() == state and self.monthly.current() == target,
                        'SNAPSHOT_CHANGED')
                now = self.clock()
                require(now >= generated, 'CLOCK_MOVED_BACKWARDS')
                if result['status'] != 'READY':
                    require(not result.get('new_orders') and not result.get('reference_quotes')
                            and not result.get('difference', {}).get('new_orders'),
                            'NONREADY_EXECUTION_FIELDS_FORBIDDEN')
                if result['status'] != 'WAIT':
                    signal = result.get('risk_projection', {}).get('signal', {})
                    valid_from = result.get('risk_valid_from', signal.get('valid_from'))
                    valid_until = result.get('risk_valid_until', signal.get('valid_until'))
                    require(valid_from is not None and valid_until is not None, 'RISK_VALIDITY_REQUIRED')
                    require(timestamp(valid_from) <= generated <= now < timestamp(valid_until),
                            'RISK_ADVICE_EXPIRED')
                for order in result.get('new_orders', []):
                    require(result['status'] == 'READY', 'WAIT_CANNOT_CONTAIN_ORDERS')
                    quote = result.get('reference_quotes', {})[order['security_id']]
                    require(timestamp(quote['observed_at']) <= generated, 'FUTURE_QUOTE')
                    require(now < timestamp(quote['reference_valid_until']), 'ADVICE_EXPIRED')
            except (ValueError, KeyError, TypeError, OSError, RuntimeError, sqlite3.Error):
                result.update(status='WAIT', detail_status='UNAVAILABLE',
                              reason='ADVICE_INVALIDATED_AFTER_GENERATION',
                              new_orders=[], reference_quotes={})
                # Some services also expose executable suggestions nested here.
                if isinstance(result.get('difference'), dict):
                    result['difference']['new_orders'] = []
            return result

        saved = False
        try:
            self.journal.append(event, now=generated)
            saved = True
        except (ValueError, OSError, RuntimeError, sqlite3.Error):
            pass
        result = checked_result()
        if saved:
            try:
                self.journal.record_return(event['event_id'],
                    dict(status=result['status'], checked_at=self.clock().isoformat()))
            except (ValueError, OSError, RuntimeError, sqlite3.Error):
                saved = False
        # No journal IO may follow this final check: even record_return can
        # consume the remaining quote/signal lifetime or observe changed state.
        result = checked_result()
        result['observation_record'] = dict(status='SAVED' if saved else 'UNAVAILABLE',
            event_id=event['event_id'] if saved else None, displayed=False, evidence_complete=False)
        return result
