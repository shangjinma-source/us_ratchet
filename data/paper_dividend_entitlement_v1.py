"""Bind a server-admitted paper dividend review to replayed historical shares.

The caller supplies the trusted admission map, never a browser request. Source
review and legal/settlement eligibility are upstream responsibilities. No IO.
"""
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
from core.strategy_account_ledger import canonical, require
from data.strategy_paper_application_descriptor_v1 import stamp
from data.paper_pre_event_holdings_v1 import holdings_before_session
from backtest.paper_cash_dividend_projection_v1 import project


def prepare_entitlement(*, book, authority, admitted_decisions, review_bytes,
                        admitted_reviews, source_files, admitted_settlements=None, clock=None):
    now = stamp((clock or (lambda: datetime.now(timezone.utc)))())
    require(type(review_bytes) is bytes, 'PAPER_DIVIDEND_REVIEW_BYTES')
    review_hash = sha256(review_bytes).hexdigest()
    require(admitted_reviews.get(review_hash) == review_bytes, 'PAPER_DIVIDEND_REVIEW_NOT_ADMITTED')
    review = json.loads(review_bytes)
    require(review['schema'] == 'PAPER_ORDINARY_DIVIDEND_REVIEW_V1'
            and review['scope'] == 'ISOLATED_PAPER_DIVIDEND_ONLY'
            and review['status'] == 'REVIEWED_EVENT_AND_CONSTANT_SHARE_UNITS', 'PAPER_DIVIDEND_REVIEW_SCOPE')
    require(review['account_id'] == book['account_id']
            and review['book_revision'] == book['revision']
            and review['descriptor_sha256'] == book['descriptor_sha256']
            and review['registration_sha256'] == book['registration_sha256'], 'PAPER_DIVIDEND_BOOK_BINDING')
    require(review['eligibility_rule'] == 'REVIEWED_PRE_EX_SESSION_OPEN_PAPER_HOLDINGS'
            and review['kind'] == 'ORDINARY_CASH_DIVIDEND' and review['currency'] == 'USD'
            and review['unresolved_actions'] == [] and review['special_entitlement_conditions'] == [],
            'PAPER_DIVIDEND_ELIGIBILITY_UNRESOLVED')
    require(type(review['event_id']) is str and bool(review['event_id'])
            and type(review['security_id']) is str and bool(review['security_id']), 'PAPER_DIVIDEND_IDENTITY')
    require(type(review['amount_per_share']) is str and Fraction(review['amount_per_share']) > 0,
            'PAPER_DIVIDEND_AMOUNT')
    require(stamp(review['available_at']) <= now, 'PAPER_DIVIDEND_FUTURE_REVIEW')
    hashes = review['source_sha256']
    require(type(hashes) is dict and hashes and set(hashes) == set(source_files)
            and all(type(raw) is bytes and sha256(raw).hexdigest() == hashes[name]
                    for name, raw in source_files.items()), 'PAPER_DIVIDEND_SOURCE_CLOSURE')
    snapshot = holdings_before_session(book=book, authority=authority, admitted_decisions=admitted_decisions,
        admitted_settlements=admitted_settlements, session_date=review['ex_session_date'], clock=lambda: now)
    if snapshot['status'] == 'WAIT_PRIOR_ORDER_SETTLEMENT':
        return snapshot
    require(stamp(review['entitlement_at']) == stamp(snapshot['boundary'])
            and stamp(review['entitlement_at']) <= stamp(review['payable_at']), 'PAPER_DIVIDEND_EVENT_BOUNDARY')
    proof = dict(review_sha256=review_hash, snapshot=snapshot)
    entitlement = dict(event_id=review['event_id'], kind=review['kind'], currency=review['currency'],
        eligible_shares=snapshot['shares'].get(review['security_id'], 0),
        amount_per_share=review['amount_per_share'], entitlement_evidence_sha256=sha256(canonical(proof)).hexdigest(),
        entitlement_at=review['entitlement_at'], payable_at=review['payable_at'], available_at=now.isoformat())
    projection = project([entitlement], [], observed_at=now.isoformat())
    return dict(status='PAPER_ENTITLEMENT_PREPARED_NOT_POSTED', entitlement=entitlement,
                proof=proof, projection=projection, account_mutated=False,
                source_admission_performed=False, payment_verified=False)
