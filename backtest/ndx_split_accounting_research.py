"""Exact whole-share split transition; caller evidence is not authenticated here.

Apply before marking the first post-split session. Pending baskets are cancelled,
not silently scaled or reoptimized: actual broker order adjustment is unproven.
Fractional entitlements require a separate cash-in-lieu model and fail closed.
"""
from copy import deepcopy
from fractions import Fraction
import math
import re
from datetime import date
from urllib.parse import urlsplit


def apply_split_session(*, session, shares, cash_usd, pending_plan, events):
    """Return a new account snapshot without modifying any caller object.

    Events must be the explicit events for this session, with a source locator
    and digest of the reviewed evidence. Neither existence nor completeness of
    those sources is proven by this arithmetic primitive.
    This is not idempotent: invoke once on the PRE-SPLIT account snapshot.
    A persistent ledger must separately track previously applied event identity.
    """
    if type(session) is not str or date.fromisoformat(session).isoformat() != session:
        raise ValueError('Canonical session date required')
    if not isinstance(shares, dict) or not shares or any(
            type(t) is not str or not t or t.strip() != t or type(n) is not int or n < 0
            for t, n in shares.items()):
        raise ValueError('Nonnegative whole-share account required')
    if type(cash_usd) not in (int, float) or not math.isfinite(cash_usd) or cash_usd < 0:
        raise ValueError('Invalid cash')
    if pending_plan is not None and not isinstance(pending_plan, dict):
        raise ValueError('Invalid pending plan')
    if type(events) not in (list, tuple):
        raise ValueError('Explicit session events required')
    updated = dict(shares)
    seen, applied = set(), []
    for event in events:
        required = {'ticker', 'session', 'new_shares', 'old_shares', 'source_url', 'evidence_sha256'}
        if not isinstance(event, dict) or set(event) != required:
            raise ValueError('Exact event schema required')
        ticker = event['ticker']
        if type(ticker) is not str or ticker not in shares or ticker in seen or event['session'] != session:
            raise ValueError('Unknown, duplicate or wrong-session split')
        numerator, denominator = event['new_shares'], event['old_shares']
        if any(type(v) is not int or v <= 0 for v in (numerator, denominator)) or numerator == denominator:
            raise ValueError('Explicit positive nontrivial integer split ratio required')
        locator = event['source_url']
        if type(locator) is not str or any(c.isspace() for c in locator):
            raise ValueError('Invalid source locator')
        parsed = urlsplit(locator)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or type(event['evidence_sha256']) is not str
                or re.fullmatch('[0-9a-f]{64}', event['evidence_sha256']) is None):
            raise ValueError('Source locator and evidence digest required')
        entitlement = Fraction(shares[ticker] * numerator, denominator)
        if entitlement.denominator != 1:
            raise ValueError('UNRESOLVED_FRACTIONAL_SPLIT_ENTITLEMENT')
        updated[ticker] = entitlement.numerator
        seen.add(ticker)
        applied.append(dict(event=deepcopy(event), pre_shares=shares[ticker], post_shares=updated[ticker]))
    cancelled = deepcopy(pending_plan) if events and pending_plan is not None else None
    return dict(session=session, shares=updated, cash_usd=cash_usd,
        pending_plan=None if cancelled is not None else deepcopy(pending_plan),
        cancelled_plan=cancelled,
        pending_plan_status='CANCELLED_SPLIT_REQUIRES_NEW_SCHEDULED_DECISION' if cancelled is not None else 'UNCHANGED',
        applied_events=applied, split_cash_flow_usd=0., split_fees_usd=0.,
        evidence_authenticated=False, corporate_action_coverage_verified=False,
        broker_order_adjustment_modelled=False, promotion_allowed=False)
