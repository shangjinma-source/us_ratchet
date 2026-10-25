"""Recover a prior regular-close decision snapshot after reviewed distributions."""
from copy import deepcopy
from fractions import Fraction
from backtest.return_priority_distribution_entitlements import apply_distribution


def decision_snapshot(state, *, decision_date, reviewed_events):
    ledger = state.get('daily_ledger', [])
    if not ledger or ledger[-1]['date'] != decision_date:
        raise ValueError('POST_CLOSE_REGULAR_LEDGER_REQUIRED')
    close = ledger[-1]
    if close.get('valuation_phase') != 'REGULAR_CLOSE_BEFORE_AFTER_HOURS_ACTION':
        raise ValueError('POST_CLOSE_LEDGER_PHASE_REQUIRED')
    events = [event for event in reviewed_events
              if event['effective_date'] == decision_date and event['timing'] == 'AFTER_CLOSE']
    applied = [row['action_details'] for row in state.get('order_log', [])
               if row.get('event') == 'DISTRIBUTION_APPLIED' and row['date'] == decision_date
               and row['timing'] == 'AFTER_CLOSE']
    if not events or len(applied) != len(events):
        raise ValueError('REVIEWED_POST_CLOSE_EVENTS_REQUIRED')
    replay = dict(cash=close['cash'], shares=deepcopy(close['shares']),
                  distribution_rights=deepcopy(close['distribution_rights']), applied_distribution_ids=[])
    for event, actual in zip(events, applied):
        if event['parent_sid'] != event['post_parent_sid'] or Fraction(event['parent_ratio']) != 1:
            raise ValueError('POST_CLOSE_DELIVERED_UNITS_CHANGED')
        expected = dict(event, eligible_parent_quantity=replay['shares'].get(event['parent_sid'], 0))
        if actual != expected:
            raise ValueError('POST_CLOSE_EVENT_OR_ELIGIBILITY_MISMATCH')
        replay = apply_distribution(state=replay, event=expected, as_of=decision_date)
    if any(replay[key] != state[key] for key in ('cash', 'shares', 'distribution_rights')):
        raise ValueError('POST_CLOSE_ACCOUNT_REPLAY_MISMATCH')
    for key in ('receivable', 'merger_entitlements'):
        if close[key] != state[key]:
            raise ValueError('POST_CLOSE_OTHER_CAPITAL_CHANGED')
    snapshot = deepcopy(state)
    for key in ('cash', 'shares', 'distribution_rights', 'receivable', 'merger_entitlements'):
        snapshot[key] = deepcopy(close[key])
    snapshot['pending_post_close_coordinates'] = False
    return snapshot, [event['event_id'] for event in events]
