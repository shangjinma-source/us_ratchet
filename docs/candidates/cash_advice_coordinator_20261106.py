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

    def _advice(self, *, cash_saved):
        state = self.account_service.store.read()
        require(state is not None, 'ACCOUNT_NOT_INITIALIZED')
        try:
            version = self.builder.rebuild()
            advice = self.builder.preview(expected_revision=version['account_revision'],
                target_id=version['target_id'],expected_proposal_id=version['proposal_id'])
        except (ValueError,KeyError,TypeError,OSError):
            current = self.account_service.store.read()
            return dict(cash_saved=cash_saved,advice_ready=False,reason='ADVICE_REFRESH_REQUIRED',
                        account_revision=current['revision'],orders_created=False)
        return dict(cash_saved=cash_saved,advice_ready=True,account_revision=version['account_revision'],
                    advice=advice,orders_created=False)
