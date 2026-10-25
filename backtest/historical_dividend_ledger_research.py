"""Isolated exact research accruals; not integrated into any trading book.

Opening holdings must be the position immediately before the ex-date session.
Payment dates are explicit research inputs, never inferred from ex-dividend data.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction


def _amount(value):
    if isinstance(value, bool):
        raise ValueError('BOOLEAN_AMOUNT')
    result = Fraction(str(value))
    if result < 0:
        raise ValueError('NEGATIVE_AMOUNT')
    return result


def create():
    return dict(schema='HISTORICAL_DIVIDEND_LEDGER_RESEARCH_V1', events={},
                payments={}, paid_cash='0', receivable='0', integrated=False)


def accrue(state, event, *, session_date, opening_quantity):
    """Snapshot pre-trade holdings once; retries must carry identical inputs."""
    required = {'event_id', 'security_id', 'ex_date', 'payment_date',
                'amount_per_share', 'withholding_rate', 'assumption', 'currency'}
    if set(event) != required or not all(isinstance(event[k], str) and event[k]
            for k in ('event_id', 'security_id', 'assumption')):
        raise ValueError('EVENT_SCHEMA')
    ex_day = date.fromisoformat(event['ex_date'])
    if date.fromisoformat(session_date) != ex_day or event['currency'] != 'USD':
        raise ValueError('EX_DATE_OR_CURRENCY')
    if event['payment_date'] is not None and date.fromisoformat(event['payment_date']) < ex_day:
        raise ValueError('PAYMENT_BEFORE_EX_DATE')
    if type(opening_quantity) is not int or opening_quantity < 0:
        raise ValueError('OPENING_QUANTITY')
    rate = _amount(event['withholding_rate'])
    if rate > 1:
        raise ValueError('WITHHOLDING_RATE')
    gross = _amount(event['amount_per_share']) * opening_quantity
    record = dict(event=deepcopy(event), opening_quantity=opening_quantity,
                  gross=str(gross), net=str(gross * (1-rate)))
    result = deepcopy(state)
    prior = result['events'].get(event['event_id'])
    if prior is not None:
        if prior != record:
            raise ValueError('EVENT_CONFLICT')
        return result
    result['events'][event['event_id']] = record
    result['receivable'] = str(_amount(result['receivable']) + _amount(record['net']))
    return result


def pay(state, *, event_id, payment_id, session_date):
    """Post on/after supplied pay date, with explicit caller scheduling.

Unknown pay dates never become cash. This is a research assumption, not proof
    of broker posting. Return cumulative cash: callers must consume deltas only.
    """
    if not isinstance(payment_id, str) or not payment_id:
        raise ValueError('PAYMENT_ID')
    result = deepcopy(state)
    record = result['events'][event_id]
    request = dict(event_id=event_id, payment_id=payment_id, session_date=session_date)
    if payment_id in result['payments']:
        if result['payments'][payment_id] != request:
            raise ValueError('PAYMENT_CONFLICT')
        return result
    if any(p['event_id'] == event_id for p in result['payments'].values()):
        raise ValueError('EVENT_ALREADY_PAID')
    payment_date = record['event']['payment_date']
    if payment_date is None:
        raise ValueError('UNKNOWN_PAYMENT_DATE')
    if date.fromisoformat(session_date) < date.fromisoformat(payment_date):
        raise ValueError('PAYMENT_NOT_DUE')
    net = _amount(record['net'])
    result['payments'][payment_id] = request
    result['paid_cash'] = str(_amount(result['paid_cash']) + net)
    result['receivable'] = str(_amount(result['receivable']) - net)
    return result
