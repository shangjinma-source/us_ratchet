"""Isolated cash-to-research-advice orchestration; no production mounting."""
from core.strategy_account_difference import require
from api.strategy_account import WriteOutcomeUncertain


class CashAdviceCoordinator:
    def __init__(self, *, account_service, builder):
        self.account_service = account_service
        self.builder = builder

    def save_cash(self, body):
        require(type(body) is dict and set(body) == {'expected_revision','event'}, 'BODY_FIELDS')
        require(type(body['event']) is dict and body['event'].get('kind') == 'CASH_CONFIRM', 'CASH_CONFIRM_REQUIRED')
        try:
            self.account_service.append(body)
        except WriteOutcomeUncertain:
            # Never assume an uncertain write failed or blindly retry it.
            state = None
            try:
                state = self.account_service.store.read()
                matches = [r['payload'] for r in state['events'] if r['payload']['event_id'] == body['event'].get('event_id')] if state else []
            except Exception:
                # A read failure cannot establish that the preceding write
                # failed. Do not leak exception details or repeat append.
                state = None
                matches = []
            if matches != [body['event']]:
                return dict(cash_saved=None,advice_ready=False,reason='CASH_WRITE_REQUIRES_RECONCILIATION',
                            account_revision=state['revision'] if state else None,orders_created=False)
        try:
            return self._advice(cash_saved=True)
        except Exception:
            # append (or exact journal reconciliation) already established
            # durability. A later read/projection failure cannot undo that.
            revision = None
            try:
                state = self.account_service.store.read()
                revision = state['revision'] if state else None
            except Exception:
                pass
            return dict(cash_saved=True,advice_ready=False,reason='ADVICE_REFRESH_REQUIRED',
                        account_revision=revision,orders_created=False)

    def retry_advice(self):
        # Explicitly no append call; preserve previously committed cash.
        state = self.account_service.store.read()
        require(state is not None and state['cash_confirmation_valid'], 'CASH_RECONFIRMATION_REQUIRED')
        return self._advice(cash_saved=True)

    def cash_status(self, body):
        """Read-only reconciliation; absence does not prove an in-flight failure."""
        require(type(body) is dict and set(body) == {'expected_revision','event'}, 'BODY_FIELDS')
        event = body['event']
        require(type(event) is dict and event.get('kind') == 'CASH_CONFIRM', 'CASH_CONFIRM_REQUIRED')
        state = self.account_service.store.read()
        require(state is not None, 'ACCOUNT_NOT_INITIALIZED')
        matches = [row['payload'] for row in state['events'] if row['payload']['event_id'] == event.get('event_id')]
        require(not matches or matches == [event], 'CASH_EVENT_CONFLICT')
        # With no matching event, an advanced revision proves that this exact
        # optimistic write can no longer commit, including a delayed request.
        # Absence at the same revision is still an unknown in-flight outcome.
        superseded = not matches and state['revision'] != body['expected_revision']
        return dict(cash_saved=True if matches else False if superseded else None,advice_ready=False,
                    reason='CASH_RECORDED' if matches else 'CASH_NOT_SAVED_ACCOUNT_CHANGED' if superseded else 'CASH_NOT_YET_OBSERVED',
                    account_revision=state['revision'],orders_created=False)

    def _advice(self, *, cash_saved):
        state = self.account_service.store.read()
        require(state is not None, 'ACCOUNT_NOT_INITIALIZED')
        try:
            version = self.builder.rebuild()
            advice = self.builder.preview(expected_revision=version['account_revision'],
                target_id=version['target_id'],expected_proposal_id=version['proposal_id'])
            # Return one coherent UI snapshot, not a second independent account
            # fetch that can mix a new fill with an older target or advice.
            current = self.account_service.store.read()
            require(current is not None and current['revision'] == version['account_revision'],
                    'ACCOUNT_CHANGED_DURING_ADVICE')
            account = self.account_service.project(current)['account']
            require(self.account_service.store.read() == current, 'ACCOUNT_CHANGED_DURING_ADVICE')
        except (ValueError,KeyError,TypeError,OSError):
            current = self.account_service.store.read()
            return dict(cash_saved=cash_saved,advice_ready=False,reason='ADVICE_REFRESH_REQUIRED',
                        account_revision=current['revision'],orders_created=False)
        return dict(cash_saved=cash_saved,advice_ready=True,account_revision=version['account_revision'],
                    account=account,advice=advice,orders_created=False)
