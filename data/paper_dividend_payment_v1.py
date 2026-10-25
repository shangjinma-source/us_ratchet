"""Prepare an explicitly reviewed paper payment; never infer payment from a date.

Admission maps are server-owned evidence, not request fields. This pure adapter
does not post cash, authenticate external sources, or change the paper book.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

from core.strategy_account_ledger import canonical, require
from data.strategy_paper_application_descriptor_v1 import stamp
from backtest.paper_cash_dividend_projection_v1 import project


def prepare_payment(*, book, entitlement, review_bytes, admitted_reviews,
                    admitted_entitlements, source_files, clock=None):
    now = stamp((clock or (lambda: datetime.now(timezone.utc)))())
    entitlement_bytes = canonical(entitlement)
    entitlement_hash = sha256(entitlement_bytes).hexdigest()
    require(admitted_entitlements.get(entitlement_hash) == entitlement_bytes,
            'PAPER_PAYMENT_ENTITLEMENT_NOT_ADMITTED')
    require(type(review_bytes) is bytes, 'PAPER_PAYMENT_REVIEW_BYTES')
    review_hash = sha256(review_bytes).hexdigest()
    require(admitted_reviews.get(review_hash) == review_bytes, 'PAPER_PAYMENT_REVIEW_NOT_ADMITTED')
    review = json.loads(review_bytes)
    require(review['schema'] == 'PAPER_CASH_PAYMENT_REVIEW_V1'
            and review['scope'] == 'ISOLATED_PAPER_DIVIDEND_ONLY'
            and review['status'] == 'REVIEWED_PAPER_PAYMENT'
            and review['unresolved_items'] == [], 'PAPER_PAYMENT_REVIEW_SCOPE')
    require(all(review[key] == book[key] for key in
                ('account_id', 'descriptor_sha256', 'registration_sha256'))
            and review['book_revision'] == book['revision'], 'PAPER_PAYMENT_BOOK_BINDING')
    require(review['entitlement_sha256'] == entitlement_hash
            and review['event_id'] == entitlement['event_id'], 'PAPER_PAYMENT_ENTITLEMENT_BINDING')
    hashes = review['source_sha256']
    require(type(hashes) is dict and hashes and set(hashes) == set(source_files)
            and all(type(raw) is bytes and sha256(raw).hexdigest() == hashes[name]
                    for name, raw in source_files.items()), 'PAPER_PAYMENT_SOURCE_CLOSURE')
    require(stamp(review['paid_at']) <= stamp(review['available_at']) <= now,
            'PAPER_PAYMENT_FUTURE_REVIEW')
    payment = {key: deepcopy(review[key]) for key in
               ('payment_id', 'event_id', 'currency', 'gross', 'withholding', 'fees', 'net', 'paid_at')}
    payment.update(available_at=review['available_at'], payment_evidence_sha256=review_hash)
    projection = project([entitlement], [payment], observed_at=now.isoformat())
    return dict(status='PAPER_PAYMENT_PREPARED_NOT_POSTED', payment=payment,
                entitlement_sha256=entitlement_hash, review_sha256=review_hash,
                projection=projection, account_mutated=False, source_admission_performed=False)
