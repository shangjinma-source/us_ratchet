"""User-confirmed USD transfer facts; no broker IO or account cash mutation."""
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json


def _revision(account_id, events):
    return sha256(json.dumps([account_id, events], sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def create_transfers(account_id):
    if not isinstance(account_id, str) or not account_id.strip():
        raise ValueError('ACCOUNT_ID_REQUIRED')
    return dict(account_id=account_id, events=[], revision=_revision(account_id, []))


def _amount(value):
    if type(value) not in (str, int) or len(str(value)) > 64:
        raise ValueError('EXACT_AMOUNT_REQUIRED')
    amount = Fraction(value)
    if amount < 0 or (amount * 100).denominator != 1:
        raise ValueError('NONNEGATIVE_CENT_AMOUNT_REQUIRED')
    return amount


def project_transfers(state):
    if state['revision'] != _revision(state['account_id'], state['events']):
        raise ValueError('TRANSFER_STATE_INTEGRITY')
    transfers = {}
    for event in state['events']:
        transfer_id = event['transfer_id']
        if event['kind'] == 'SENT':
            transfers[transfer_id] = dict(source=event['source'], destination=event['destination'],
                principal=event['principal'], fee=event['fee'], received='0', sent_at=event['occurred_at'])
        else:
            row = transfers[transfer_id]
            row['received'] = str(Fraction(row['received']) + Fraction(event['amount']))
    for row in transfers.values():
        row['in_transit'] = str(Fraction(row['principal']) - Fraction(row['received']))
        row['status'] = 'RECEIVED' if Fraction(row['in_transit']) == 0 else 'IN_TRANSIT'
    return dict(transfers=transfers,
        in_transit_usd=str(sum((Fraction(r['in_transit']) for r in transfers.values()), Fraction(0))),
        confirmed_fees_usd=str(sum((Fraction(r['fee']) for r in transfers.values()), Fraction(0))),
        external_capital_flow_usd='0', account_cash_mutated=False,
        in_transit_is_buying_power=False)


def apply_transfer_event(state, event, *, expected_revision, now):
    projection = project_transfers(state)
    if type(event) is not dict or type(event.get('event_id')) is not str or not event['event_id'].strip():
        raise ValueError('EVENT_ID_REQUIRED')
    for previous in state['events']:
        if previous['event_id'] == event['event_id']:
            if previous != event:
                raise ValueError('EVENT_ID_CONFLICT')
            return deepcopy(state)
    if expected_revision != state['revision']:
        raise ValueError('STALE_REVISION')
    common = {'event_id', 'transfer_id', 'kind', 'occurred_at'}
    extra = {'source', 'destination', 'principal', 'fee'} if event.get('kind') == 'SENT' else {'amount'}
    if event.get('kind') not in ('SENT', 'RECEIVED') or set(event) != common | extra:
        raise ValueError('TRANSFER_EVENT_FIELDS')
    if type(event['transfer_id']) is not str or not event['transfer_id'].strip():
        raise ValueError('TRANSFER_ID_REQUIRED')
    occurred = datetime.fromisoformat(event['occurred_at'])
    if occurred.utcoffset() is None or now.utcoffset() is None or occurred > now:
        raise ValueError('VALID_OCCURRED_TIME_REQUIRED')
    row = projection['transfers'].get(event['transfer_id'])
    if event['kind'] == 'SENT':
        if row is not None:
            raise ValueError('TRANSFER_ALREADY_RECORDED')
        if {event['source'], event['destination']} != {'HSBC', 'USMART'}:
            raise ValueError('DISTINCT_SUPPORTED_BROKERS_REQUIRED')
        if _amount(event['principal']) <= 0:
            raise ValueError('POSITIVE_PRINCIPAL_REQUIRED')
        _amount(event['fee'])
    else:
        if row is None:
            raise ValueError('UNKNOWN_TRANSFER')
        amount = _amount(event['amount'])
        if amount <= 0 or amount > Fraction(row['in_transit']):
            raise ValueError('RECEIPT_EXCEEDS_PENDING_PRINCIPAL')
        if occurred < datetime.fromisoformat(row['sent_at']):
            raise ValueError('RECEIPT_BEFORE_TRANSFER')
    updated = deepcopy(state)
    updated['events'].append(deepcopy(event))
    updated['revision'] = _revision(updated['account_id'], updated['events'])
    return updated
