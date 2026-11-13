"""Confirmed broker split of existing aggregate cash; never a second cash ledger."""
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
import sqlite3
from contextlib import closing


def validate_broker_cash(document, *, account, transfers, now):
    required = {'account_id', 'account_revision', 'transfer_revision', 'balances'}
    if type(document) is not dict or set(document) != required:
        raise ValueError('BROKER_CASH_FIELDS')
    if document['account_id'] != account['account_id'] or transfers['account_id'] != account['account_id']:
        raise ValueError('BROKER_CASH_ACCOUNT_MISMATCH')
    if document['account_revision'] != account['revision'] or document['transfer_revision'] != transfers['revision']:
        raise ValueError('STALE_BROKER_CASH_BINDING')
    if not account['cash_confirmation_valid']:
        raise ValueError('AGGREGATE_CASH_CONFIRMATION_REQUIRED')
    if now.utcoffset() is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    balances = document['balances']
    if type(balances) is not dict or set(balances) != {'HSBC', 'USMART'}:
        raise ValueError('BOTH_BROKER_BALANCES_REQUIRED')
    totals = {'available_cash': Fraction(0), 'reserved_cash': Fraction(0)}
    latest_transfer = max((datetime.fromisoformat(event['occurred_at'])
                           for event in transfers['events']), default=None)
    for row in balances.values():
        if type(row) is not dict or set(row) != {'available_cash', 'reserved_cash', 'observed_at'}:
            raise ValueError('BROKER_BALANCE_FIELDS')
        at = datetime.fromisoformat(row['observed_at'])
        if at.utcoffset() is None or at > now or (latest_transfer is not None and at < latest_transfer):
            raise ValueError('BROKER_BALANCE_TIME_INVALID')
        for field in totals:
            if type(row[field]) not in (str, int):
                raise ValueError('EXACT_CASH_REQUIRED')
            value = Fraction(row[field])
            if value < 0 or (value * 100).denominator != 1:
                raise ValueError('NONNEGATIVE_CENT_CASH_REQUIRED')
            totals[field] += value
    if any(totals[field] != Fraction(account[field]) for field in totals):
        raise ValueError('BROKER_SUM_DIFFERS_FROM_CONFIRMED_ACCOUNT')
    return dict(available_cash=str(totals['available_cash']),
                total_uninvested_cash=str(sum(totals.values())),
                in_transit_included=False, account_written=False)


class BrokerCashAllocationStore:
    """Append-only allocation facts; caller holds account/transfer snapshot locks.

    Reading revalidates both revisions. After a fill, cash edit or transfer,
    the old split cannot be reused to size orders. No inferred default broker.
    """
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path)) as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS broker_cash_allocations (
                sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL,
                account_id TEXT NOT NULL, payload TEXT NOT NULL,
                recorded_at TEXT NOT NULL, digest TEXT NOT NULL)''')
            connection.commit()

    def save(self, event_id, document, *, account, transfers, now):
        if type(event_id) is not str or not event_id.strip() or len(event_id) > 128:
            raise ValueError('EVENT_ID_REQUIRED')
        payload = json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False)
        digest = sha256(payload.encode()).hexdigest()
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('BEGIN IMMEDIATE')
            old = connection.execute('SELECT payload FROM broker_cash_allocations WHERE event_id=?', (event_id,)).fetchone()
            if old and old[0] != payload:
                raise ValueError('EVENT_ID_CONFLICT')
            validate_broker_cash(document, account=account, transfers=transfers, now=now)
            if not old:
                connection.execute('INSERT INTO broker_cash_allocations (event_id,account_id,payload,recorded_at,digest) VALUES (?,?,?,?,?)',
                    (event_id, account['account_id'], payload, now.isoformat(), digest))
            connection.commit()
        return dict(saved=True, already_recorded=bool(old), digest=digest, account_written=False)

    def read(self, *, account, transfers, now):
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute('SELECT payload,digest FROM broker_cash_allocations WHERE account_id=? ORDER BY sequence DESC LIMIT 1',
                                     (account['account_id'],)).fetchone()
        if row is None:
            return dict(status='BROKER_CASH_CONFIRMATION_REQUIRED', balances=None)
        if sha256(row[0].encode()).hexdigest() != row[1]:
            raise ValueError('BROKER_CASH_ALLOCATION_INTEGRITY')
        document = json.loads(row[0])
        try:
            validate_broker_cash(document, account=account, transfers=transfers, now=now)
        except ValueError as error:
            return dict(status='BROKER_CASH_CONFIRMATION_REQUIRED', reason=str(error), balances=None)
        return dict(status='CONFIRMED_BROKER_CASH_SPLIT', document=document, digest=row[1], account_written=False)
