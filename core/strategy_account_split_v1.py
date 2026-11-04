"""Unmounted integer forward-split reducer; server must authenticate evidence.

No broker IO, persistence, source approval, or automatic account migration.
Old ledger readers cannot replay SPLIT_CONFIRMED: deployment needs a versioned
store and coordinated target/risk migration before this reducer may be used.
"""
from copy import deepcopy
from datetime import datetime
from core import strategy_account_ledger as ledger


def moment(value):
    ledger.require(type(value) is str, 'SPLIT_TIME_REQUIRED')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    ledger.require(result.utcoffset() is not None, 'SPLIT_AWARE_TIME_REQUIRED')
    return result


def apply_event(state, event, *, expected_revision):
    ledger.require(state.get('schema') == 'REAL_STRATEGY_SCOPED_LEDGER_V1'
                   and state.get('revision') == ledger._revision(state), 'STATE_INTEGRITY')
    ledger.require(type(event) is dict and type(event.get('event_id')) is str
                   and bool(event['event_id'].strip()), 'EVENT_ID_REQUIRED')
    for previous in state['events']:
        if previous['payload']['event_id'] == event['event_id']:
            ledger.require(previous['payload'] == event, 'EVENT_ID_CONFLICT')
            return deepcopy(state), deepcopy(previous['effect'])
    ledger.require(expected_revision == state['revision'], 'STALE_REVISION')
    prior_splits = [item['payload'] for item in state['events']
                    if item['payload']['kind'] == 'SPLIT_CONFIRMED']
    if event.get('kind') != 'SPLIT_CONFIRMED':
        if event.get('kind') in ('FILL', 'DIRECT_FILL'):
            sid = event.get('security_id') if event['kind'] == 'DIRECT_FILL' else state['orders'].get(event.get('order_id'), {}).get('security_id')
            for split in prior_splits:
                if split['security_id'] == sid:
                    ledger.require(moment(event['executed_at']) >= moment(split['effective_at']),
                                   'PRE_SPLIT_LATE_FILL_REQUIRES_RECONCILIATION')
        return ledger.apply_event(state, event, expected_revision=expected_revision)

    fields = {'event_id', 'kind', 'action_id', 'security_id', 'ratio', 'effective_at',
              'broker_confirmed_at', 'old_unit_id', 'new_unit_id', 'evidence_sha256'}
    ledger.require(set(event) == fields, 'SPLIT_EVENT_FIELDS')
    for key in ('action_id', 'security_id', 'old_unit_id', 'new_unit_id'):
        ledger.require(type(event[key]) is str and bool(event[key].strip()), 'SPLIT_IDENTITY_REQUIRED')
    ledger.require(event['old_unit_id'] != event['new_unit_id'], 'SPLIT_UNIT_CHANGE_REQUIRED')
    ratio = event['ratio']
    ledger.require(type(ratio) is int and ratio > 1, 'INTEGER_FORWARD_SPLIT_REQUIRED')
    digest = event['evidence_sha256']
    ledger.require(type(digest) is str and len(digest) == 64
                   and all(c in '0123456789abcdef' for c in digest), 'SPLIT_EVIDENCE_REQUIRED')
    effective = moment(event['effective_at'])
    ledger.require(moment(event['broker_confirmed_at']) >= effective, 'SPLIT_BROKER_CONFIRMATION_TOO_EARLY')
    sid = event['security_id']
    for split in prior_splits:
        ledger.require(split['action_id'] != event['action_id'], 'SPLIT_ACTION_ALREADY_APPLIED')
        if split['security_id'] == sid:
            ledger.require(moment(split['effective_at']) < effective, 'SPLIT_CLOCK_NOT_FORWARD')
    same_security = [split for split in prior_splits if split['security_id'] == sid]
    if same_security:
        ledger.require(same_security[-1]['new_unit_id'] == event['old_unit_id'], 'SPLIT_UNIT_CHAIN_MISMATCH')
        used_units = {split[key] for split in same_security for key in ('old_unit_id', 'new_unit_id')}
        ledger.require(event['new_unit_id'] not in used_units, 'SPLIT_UNIT_ID_REUSED')
    ledger.require(not any(order['security_id'] == sid and order['status'] == 'OPEN'
                           for order in state['orders'].values()), 'SPLIT_OPEN_ORDERS_REQUIRE_RECONCILIATION')
    for item in state['events']:
        payload = item['payload']
        if payload['kind'] not in ('FILL', 'DIRECT_FILL'):
            continue
        fill_sid = payload.get('security_id') if payload['kind'] == 'DIRECT_FILL' else state['orders'][payload['order_id']]['security_id']
        if fill_sid == sid:
            ledger.require(moment(payload['executed_at']) < effective, 'POST_SPLIT_FILL_REQUIRES_RECONCILIATION')
    held = state['shares'].get(sid, 0)
    updated = deepcopy(state)
    updated['shares'][sid] = held * ratio
    updated['holdings_revision'] += 1
    updated['cash_confirmation_valid'] = False
    effect = dict(event_id=event['event_id'], kind=event['kind'], action_id=event['action_id'],
                  security_id=sid, quantity_before=held, quantity_after=held*ratio,
                  cash_delta='0', manual_cash_changed=False, cash_confirmation_valid=False)
    ledger._project(updated)
    updated['events'].append(dict(payload=deepcopy(event), effect=deepcopy(effect)))
    updated['revision'] = ledger._revision(updated)
    return updated, effect


def replay(account_id, events):
    state = ledger.create_account(account_id)
    for event in events:
        state, _ = apply_event(state, event, expected_revision=state['revision'])
    return state
