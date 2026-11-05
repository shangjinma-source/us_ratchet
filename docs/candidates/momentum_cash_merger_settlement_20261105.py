"""Frozen-book isolated closing settlement hooks; D0/D1/D5 are assumptions."""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path

SOURCE_SHA256 = 'a570e4333fd0be8a2879f1b3a4f8b54a415b1e5a9e6fddf703e3226385b16039'


class Settlement:
    def __init__(self, days, events, delay):
        if type(delay) is not int or delay not in (0, 1, 5) or days != sorted(set(days)):
            raise ValueError('FIXED_DELAY_AND_EXPLICIT_CALENDAR_REQUIRED')
        self.events = {}
        self.claims = {}
        self.paid = set()
        self.log = []
        for event in events:
            if event['type'] != 'merger':
                continue
            identifier = event.get('event_id')
            if not identifier or identifier in self.events or not event.get('source_references'):
                raise ValueError('UNIQUE_CASH_MERGER_EVIDENCE_REQUIRED')
            index = days.index(event['date']) + delay
            self.events[identifier] = dict(event=deepcopy(event), due=days[index] if index < len(days) else None)

    def accrue(self, event, shares):
        identifier = event.get('event_id')
        if event.get('type') != 'merger' or identifier not in self.events or event != self.events[identifier]['event']:
            raise ValueError('CASH_MERGER_EVENT_BINDING_REQUIRED')
        if type(shares) is not int or shares <= 0 or F(event['share_cash']) <= 0:
            raise ValueError('POSITIVE_ENTITLED_SHARES_REQUIRED')
        if identifier in self.claims:
            raise ValueError('DUPLICATE_ENTITLEMENT')
        self.claims[identifier] = shares * F(event['share_cash'])

    def release(self, identifier, day, cash, receivable):
        if identifier not in self.claims:
            raise ValueError('NO_ENTITLED_CASH_MERGER_CLAIM')
        if identifier in self.paid:
            raise ValueError('DUPLICATE_SETTLEMENT')
        if self.events[identifier]['due'] != day:
            raise ValueError('SETTLEMENT_DATE_MISMATCH')
        amount = self.claims[identifier]
        if receivable < amount:
            raise ValueError('INSUFFICIENT_MERGER_RECEIVABLE')
        next_cash, next_receivable = cash + amount, receivable - amount
        assert next_cash + next_receivable == cash + receivable
        self.paid.add(identifier)
        self.log.append(dict(event_id=identifier,date=day,amount=str(amount),phase='AFTER_CLOSE_ORDERS_NEXT_SESSION_ONLY'))
        return next_cash, next_receivable

    def close(self, day, cash, receivable):
        for identifier in self.claims:
            if identifier not in self.paid and self.events[identifier]['due'] == day:
                cash, receivable = self.release(identifier, day, cash, receivable)
        return cash, receivable


def run_book(*, settlement_delay, **kwargs):
    """Private namespace, two exact hooks; never patch imported/frozen engine."""
    path = Path(__file__).resolve().parents[2] / 'backtest/historical_dividend_next_open_book_research.py'
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('FROZEN_BOOK_CHANGED')
    settlement = Settlement(kwargs['session_dates'], kwargs.get('events', ()), settlement_delay)
    source = raw.decode('utf8')
    first = "            elif kind == 'merger':\n                receivable += shares.get(sid, 0) * number(event['share_cash'])"
    source = source.replace('\r\n', '\n')
    second = "        ledger.append(dict(date=day, cash=str(cash), shares=dict(shares), receivable=str(receivable),"
    if source.count(first) != 1 or source.count(second) != 1:
        raise ValueError('EXACT_SETTLEMENT_HOOKS_REQUIRED')
    source = source.replace(first, "            elif kind == 'merger':\n                if shares.get(sid, 0):\n                    _settlement.accrue(event, shares[sid])\n                receivable += shares.get(sid, 0) * number(event['share_cash'])")
    source = source.replace(second, "        cash, receivable = _settlement.close(day, cash, receivable)\n" + second)
    namespace = {'__name__': '_isolated_cash_merger_book', '_settlement': settlement}
    exec(compile(source, str(path) + ':isolated_settlement', 'exec'), namespace)
    result = namespace['run_next_open_book'](**kwargs)
    result['cash_merger_settlement'] = dict(delay_sessions=settlement_delay, assumption_not_broker_fact=True,
                                          releases=settlement.log, pending_ids=sorted(set(settlement.claims)-settlement.paid),
                                          frozen_book_sha256=SOURCE_SHA256)
    return result
