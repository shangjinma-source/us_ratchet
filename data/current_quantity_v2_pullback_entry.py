"""Research-only causal pullback candidates; not connected to order services.

The caller must authenticate source bytes. This pure kernel validates supplied
declarations and complete minute coverage, not market-data authenticity. Parameters
are explicit research assumptions, not optimized or user-approved defaults.
"""
from datetime import datetime, timedelta
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo


VERSION = 'V2_OBSERVED_SESSION_REBOUND_PULLBACK_RESEARCH_V1'
NY = ZoneInfo('America/New_York')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def number(value):
    require(type(value) in (str, int), 'EXACT_NUMBER_REQUIRED')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError):
        raise ValueError('INVALID_NUMBER') from None


def stamp(value):
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError('INVALID_TIME') from None
    require(result.tzinfo is not None, 'AWARE_TIME_REQUIRED')
    return result


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def build_pullback_candidate(*, reference, now, rebound_fraction, minimum_discount,
                             maximum_age_seconds, previous_cap):
    """Return an unaccepted candidate and cap declaration; never persist or order.

    reference contains verified-source declarations and contiguous completed 1m
    OHLCV bars from the supplied regular-session open. Future/partial, missing,
    duplicate and zero-volume bars fail closed. No forward-filled lows are allowed.
    """
    ratio, discount = number(rebound_fraction), number(minimum_discount)
    require(0 < ratio < 1 and 0 < discount < 1, 'INVALID_POLICY_PARAMETERS')
    require(type(maximum_age_seconds) is int and 0 < maximum_age_seconds <= 120,
            'INVALID_MAXIMUM_AGE')
    policy = dict(version=VERSION, rebound_fraction=str(ratio),
                  minimum_discount=str(discount), maximum_age_seconds=maximum_age_seconds)
    policy_id = digest(policy)
    for name in ('security_id', 'ticker', 'session'):
        require(type(reference.get(name)) is str and bool(reference[name]), 'IDENTITY_REQUIRED')
    require(reference.get('currency') == 'USD'
            and reference.get('price_basis') == 'CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
            'QUOTE_BASIS_REQUIRED')
    require(reference.get('source_bytes_verified') is True, 'SOURCE_VERIFICATION_REQUIRED')
    pins = reference.get('source_hashes')
    require(type(pins) is dict and bool(pins) and all(
        type(path) is str and bool(path) and type(value) is str and len(value) == 64
        and all(c in '0123456789abcdef' for c in value) for path, value in pins.items()),
        'SOURCE_PINS_REQUIRED')
    current = stamp(now)
    opening, closing, captured, checked, last_at = [stamp(reference[name]) for name in
        ('session_open', 'session_close', 'captured_at', 'checked_at', 'last_at')]
    require(opening <= last_at <= captured <= checked <= current < closing,
            'FUTURE_OR_OUTSIDE_SESSION')
    require(opening.second == opening.microsecond == 0
            and closing.second == closing.microsecond == 0, 'MINUTE_SESSION_BOUNDARIES_REQUIRED')
    require(all(t.astimezone(NY).date().isoformat() == reference['session'] for t in
                (opening, closing, captured, checked, current, last_at)), 'SESSION_MISMATCH')
    last = number(reference['last_price'])
    require(last > 0, 'INVALID_LAST_PRICE')
    age = timedelta(seconds=maximum_age_seconds)
    require(current < last_at + age, 'STALE_LAST_PRICE')
    bars = reference.get('bars')
    require(type(bars) is list and 0 < len(bars) <= 1440, 'COMPLETE_MINUTES_REQUIRED')
    complete_through = captured.replace(second=0, microsecond=0)
    expected = opening
    lows = []
    for bar in bars:
        require(all(bar.get(k) == reference[k] for k in ('security_id', 'ticker', 'session')),
                'BAR_IDENTITY_MISMATCH')
        start, end = stamp(bar['start']), stamp(bar['end'])
        require(start == expected and end == start + timedelta(minutes=1)
                and end <= complete_through, 'NONCONTIGUOUS_OR_FUTURE_MINUTE')
        require(bar.get('synthetic') is False, 'SYNTHETIC_STATUS_REQUIRED')
        opened, high, low, close, volume = [number(bar[k]) for k in
                                         ('open', 'high', 'low', 'close', 'volume')]
        require(0 < low <= opened <= high and low <= close <= high, 'INVALID_OHLC')
        require(volume > 0, 'ZERO_VOLUME_MINUTE_UNAVAILABLE')
        lows.append(low)
        expected = end
    require(expected == complete_through, 'INCOMPLETE_SESSION_MINUTES')
    deadline = min(last_at + age, expected + age, closing)
    require(current < deadline, 'REFERENCE_EXPIRED')
    session_low = min(lows)
    # New live trade can undercut the last completed-bar low. Never anchor above it.
    anchor = min(session_low, last)
    rebound_level = anchor + ratio * (last - anchor)
    discount_level = last * (1 - discount)
    candidate = min(rebound_level, discount_level)
    binding = dict(security_id=reference['security_id'], ticker=reference['ticker'],
                   session=reference['session'], currency=reference['currency'],
                   price_basis=reference['price_basis'], policy_id=policy_id)
    if previous_cap is not None:
        require(type(previous_cap) is dict and previous_cap.get('binding') == binding,
                'PRIOR_CAP_BINDING_MISMATCH')
        prior_at = stamp(previous_cap['observed_at'])
        require(opening <= prior_at <= captured, 'PRIOR_CAP_FROM_FUTURE_OR_OTHER_SESSION')
        prior = number(previous_cap['limit_price'])
        require(prior > 0 and (prior * 100).denominator == 1, 'INVALID_PRIOR_CAP')
        candidate = min(candidate, prior)
    limit = Fraction(candidate * 100 // 1, 100)
    require(limit > 0 and limit < last, 'NONPOSITIVE_OR_NONDISCOUNTED_LIMIT')
    return dict(schema=VERSION, policy=policy, policy_id=policy_id,
                binding=binding, observed_session_low=str(session_low),
                last_price=str(last), rebound_level=str(rebound_level),
                discount_level=str(discount_level), limit_price=str(limit),
                reference_valid_until=deadline.isoformat(),
                hypothetical_day_expiry=closing.isoformat(),
                cap_declaration=dict(binding=binding, observed_at=captured.isoformat(),
                                     limit_price=str(limit)),
                input_digest=digest(reference), research_only=True,
                source_authenticated=False, source_verification='CALLER_DECLARATION_ONLY',
                performance_validated=False, orders_created=False)
