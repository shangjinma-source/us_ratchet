"""Replayable isolated dividend journal, separate from the registered trade book.

No IO or spendable-cash mutation. A future versioned integration must explicitly
incorporate this journal into order affordability; adding its totals ad hoc to a
V1 book would break that book's replay and is forbidden.
"""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json

from core.strategy_account_ledger import canonical, require
from backtest.current_strategy_prospective_paper_book_v1 import replay as replay_book
from data.paper_dividend_payment_v1 import prepare_payment
from data.strategy_paper_application_descriptor_v1 import stamp


def digest(value):
    return sha256(canonical(value)).hexdigest()


def create(book):
    identity = {key: book[key] for key in ('account_id', 'descriptor_sha256', 'registration_sha256')}
    return dict(schema='ISOLATED_PAPER_DIVIDEND_JOURNAL_V1', identity=identity,
                entries=[], revision=digest(identity), paid_net='0', spendable_cash_integrated=False)


def _append(journal, request, accepted_at, *, books, authority, admitted_decisions,
            admitted_settlements, admitted_reviews, admitted_entitlements, source_files):
    require(set(request) == {'operation_id', 'expected_revision', 'book_revision',
                            'entitlement_sha256', 'review_sha256'}, 'DIVIDEND_JOURNAL_REQUEST')
    require(type(request['operation_id']) is str and request['operation_id'], 'DIVIDEND_JOURNAL_OPERATION')
    require(request['expected_revision'] == journal['revision'], 'DIVIDEND_JOURNAL_STALE')
    book = books[request['book_revision']]
    require(book['revision'] == request['book_revision'] and
            all(book[key] == value for key, value in journal['identity'].items()), 'DIVIDEND_JOURNAL_BOOK')
    replay_book(book, authority=authority, admitted_decisions=admitted_decisions,
                admitted_settlements=admitted_settlements)
    current = stamp(accepted_at)
    require(stamp(book['last_available_at']) <= current, 'DIVIDEND_JOURNAL_FUTURE_BOOK')
    if journal['entries']:
        require(stamp(journal['entries'][-1]['accepted_at']) <= current, 'DIVIDEND_JOURNAL_CLOCK_REVERSED')
    raw = admitted_reviews[request['review_sha256']]
    right_raw = admitted_entitlements[request['entitlement_sha256']]
    require(sha256(raw).hexdigest() == request['review_sha256'] and
            sha256(right_raw).hexdigest() == request['entitlement_sha256'], 'DIVIDEND_JOURNAL_EVIDENCE_HASH')
    result = prepare_payment(book=book, entitlement=json.loads(right_raw), review_bytes=raw,
        admitted_reviews=admitted_reviews, admitted_entitlements=admitted_entitlements,
        source_files=source_files[request['review_sha256']], clock=lambda:current)
    payment = result['payment']
    require(not any(entry['payment']['event_id'] == payment['event_id'] or
                    entry['payment']['payment_id'] == payment['payment_id'] or
                    entry['request']['operation_id'] == request['operation_id']
                    for entry in journal['entries']), 'DIVIDEND_JOURNAL_DUPLICATE')
    entry = dict(request=deepcopy(request), accepted_at=current.isoformat(), payment=payment,
                 previous_revision=journal['revision'])
    revision = digest(entry)
    journal['entries'].append(dict(entry, revision=revision))
    journal['revision'] = revision
    journal['paid_net'] = str(Fraction(journal['paid_net']) + Fraction(payment['net']))
    return journal


def replay(journal, **evidence):
    # Rebuild even an empty journal, so an altered opening balance cannot pass.
    rebuilt = create(journal['identity'])
    for entry in journal['entries']:
        _append(rebuilt, entry['request'], entry['accepted_at'], **evidence)
        require(rebuilt['entries'][-1] == entry, 'DIVIDEND_JOURNAL_ENTRY_REPLAY')
    require(rebuilt == journal, 'DIVIDEND_JOURNAL_REPLAY')
    return rebuilt


def append(journal, request, *, clock=None, **evidence):
    rebuilt = replay(journal, **evidence)
    for entry in rebuilt['entries']:
        if entry['request']['operation_id'] == request['operation_id']:
            require(entry['request'] == request, 'DIVIDEND_JOURNAL_OPERATION_CONFLICT')
            return rebuilt
    now = stamp((clock or (lambda:datetime.now(timezone.utc)))())
    return _append(rebuilt, request, now.isoformat(), **evidence)
