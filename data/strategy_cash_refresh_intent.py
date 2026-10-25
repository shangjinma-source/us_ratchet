"""Pure proposed cash-save routing; no ledger/UI changes or selection execution.

CASH_CONFIRM is a balance, not a contribution. The current ledger has no external
capital-change event, so cash deltas cannot reliably distinguish deposits, sales,
reservation releases, transfers or corrections. A future server-owned persisted
capital journal is required for explicit contribution-driven recompetition.
"""
from fractions import Fraction
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import replay
from core.strategy_account_difference import require, timestamp, number


def plan_cash_refresh(*, state, target, now, intent='SAVE_BALANCE',
                      capital_change=None, consumed_capital_event_ids=()):
    """Plan after successful balance save, using server snapshots only.

    capital_change, if present, must come from a verified server journal, never a
    browser assertion. This pure planner checks binding, not journal authenticity.
    It does not record/consume the event; target publication must do that atomically.
    """
    require(intent in {'SAVE_BALANCE','APPLY_CAPITAL_CHANGE'}, 'CASH_REFRESH_INTENT_REQUIRED')
    require(replay(state['account_id'], [e['payload'] for e in state['events']]) == state,
            'ACCOUNT_REPLAY_MISMATCH')
    require(state['cash_confirmation_valid'], 'CASH_CONFIRMATION_REQUIRED')
    month=timestamp(now).astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
    require(type(consumed_capital_event_ids) in (list,tuple,set)
            and all(type(e) is str and bool(e) for e in consumed_capital_event_ids),
            'CAPITAL_CONSUMPTION_HISTORY_REQUIRED')
    if target is not None:
        require(target['payload']['account_id']==state['account_id'],'TARGET_ACCOUNT_MISMATCH')
        require(target['payload']['target_month']<=month,'FUTURE_MONTHLY_TARGET')
    base=dict(account_revision=state['revision'], target_id=target['target_id'] if target else None,
              account_mutated=False, selection_executed=False,
              cash_increase_is_capital_inflow=False)
    event_id=None
    if intent=='APPLY_CAPITAL_CHANGE':
        if capital_change is None:
            return dict(base,status='CAPITAL_CHANGE_EVENT_REQUIRED',selection_reason=None,
                        next_action='RECORD_EXPLICIT_CAPITAL_CHANGE',
                        reason='BALANCE_AND_FILL_EVENTS_DO_NOT_IDENTIFY_EXTERNAL_CAPITAL')
        require(type(capital_change) is dict and capital_change.get('schema')==
                'SERVER_EXPLICIT_STRATEGY_CAPITAL_CHANGE_V1','CAPITAL_CHANGE_SCHEMA_REQUIRED')
        event_id=capital_change.get('event_id')
        require(type(event_id) is str and bool(event_id),'CAPITAL_EVENT_ID_REQUIRED')
        require(capital_change.get('account_id')==state['account_id'],
                'CAPITAL_CHANGE_ACCOUNT_BINDING_MISMATCH')
        require(capital_change.get('direction') in {'CONTRIBUTION','WITHDRAWAL'},
                'CAPITAL_CHANGE_DIRECTION_REQUIRED')
        amount=number(capital_change['amount'])
        require(amount>Fraction(0),'NONZERO_CAPITAL_CHANGE_REQUIRED')
        if event_id in consumed_capital_event_ids:
            return dict(base,status='CAPITAL_CHANGE_ALREADY_APPLIED',selection_reason=None,
                        next_action='REFRESH_DAILY_SIGNAL',capital_event_id=event_id)
        require(capital_change.get('cash_confirmation_event_id')==state['last_cash_confirmation_event']
                and type(capital_change.get('account_revision')) is type(state['revision'])
                and capital_change['account_revision']==state['revision'],
                'CAPITAL_CHANGE_ACCOUNT_BINDING_MISMATCH')
        require(capital_change.get('previous_target_id')==(target['target_id'] if target else None),
                'CAPITAL_CHANGE_TARGET_BINDING_MISMATCH')
    else:
        require(capital_change is None,'CAPITAL_CHANGE_REQUIRES_EXPLICIT_INTENT')
    if target is None:
        reason='INITIAL'
    elif target['payload']['target_month']<month:
        reason='MONTHLY_SELECTION'
    elif intent=='APPLY_CAPITAL_CHANGE':
        reason='EXPLICIT_RECONFIGURE'
    else:
        reason=None
    return dict(base,status='SELECTION_REQUIRED' if reason else 'BALANCE_SAVED_REFRESH_ONLY',
                selection_reason=reason,
                next_action='SELECT_THEN_REFRESH_DAILY_SIGNAL' if reason else 'REFRESH_DAILY_SIGNAL',
                capital_event_id=event_id,
                capital_event_consumption='ON_SUCCESSFUL_TARGET_PUBLICATION_ONLY' if event_id else None)
