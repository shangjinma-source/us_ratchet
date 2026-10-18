"""Exact diagnostics of saved decimal quantities; never an account/order gate."""
from datetime import date
from fractions import Fraction
import math


def require(condition, message):
    if not condition:
        raise ValueError(message)


def session_date(value):
    require(type(value) is str, 'Session must be an ISO date')
    require(date.fromisoformat(value).isoformat() == value, 'Canonical ISO date')
    return value


def saved_number(value):
    require(type(value) in (int, float), 'Original finite JSON number, not bool/string')
    require(type(value) is int or math.isfinite(value), 'Finite original number')
    # repr is the round-trip decimal representation of the saved JSON float.
    # This is not a claim about pre-serialization binary arithmetic precision.
    return Fraction(str(value))


def rational(value):
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def latest_labels(*, session, security_ids, observations):
    """Last observation per SID at/before Close; never backward-fill a new SID."""
    session_date(session)
    require(type(security_ids) is list and len(set(security_ids)) == len(security_ids),
            'Explicit unique SID list')
    require(all(type(sid) is str and sid for sid in security_ids), 'Nonempty SID')
    require(type(observations) is dict, 'Date-indexed original observations')
    labels = {}
    for observed in sorted(observations):
        session_date(observed)
        entries = observations[observed]
        require(type(entries) is dict, 'SID-indexed observed labels')
        for sid, label in entries.items():
            require(type(sid) is str and sid and type(label) is str and label,
                    'Nonempty original SID and label')
            if observed <= session and sid in security_ids:
                labels[sid] = dict(label=label, observation_session=observed)
    require(set(labels) == set(security_ids), 'Missing as-of label; no future backfill')
    return labels


def derive_daily_diagnostic(*, session, shares, close_prices, labels):
    """Stock-only concentration from saved quantities/prices and dated labels.

    Caller authenticates source files and joins SID/Close columns. No cash is
    included in the denominator; all-cash days have undefined concentration.
    """
    session_date(session)
    require(all(type(value) is dict for value in (shares, close_prices, labels)),
            'Explicit original mappings')
    require(set(shares) == set(close_prices) == set(labels), 'Exact SID sets')
    amounts = {}
    for sid, quantity in shares.items():
        require(type(sid) is str and sid, 'Nonempty SID')
        quantity, price = saved_number(quantity), saved_number(close_prices[sid])
        require(quantity > 0 and price > 0, 'Positive saved holding and Close')
        label = labels[sid]
        require(type(label) is dict and set(label) == {'label', 'observation_session'},
                'Original label with observation date')
        require(type(label['label']) is str and label['label'], 'Nonempty risk label')
        require(session_date(label['observation_session']) <= session, 'No future label')
        amounts[sid] = quantity * price
    total = sum(amounts.values(), Fraction(0))
    weights = {sid: amount / total for sid, amount in amounts.items()}
    chains = {}
    for sid, weight in weights.items():
        chain = labels[sid]['label']
        chains[chain] = chains.get(chain, Fraction(0)) + weight
    ordered = sorted(weights.values(), reverse=True)
    hhi = sum((weight * weight for weight in ordered), Fraction(0))
    metrics = None if not weights else dict(
        hhi=rational(hhi), effective_n=rational(1 / hhi),
        top1_weight=rational(ordered[0]), minimum_single_weight=rational(ordered[-1]),
        top3_weight=rational(sum(ordered[:3], Fraction(0))),
        risk_chain_top1_weight=rational(max(chains.values())))
    return dict(schema='SAVED_DECIMAL_HOLDINGS_RISK_DIAGNOSTIC_V1', session=session,
                status='DERIVED_SAVED_DECIMAL_DIAGNOSTIC' if weights else 'ALL_CASH_CONCENTRATION_UNDEFINED',
                numeric_basis='EXACT_RATIONAL_OF_SAVED_JSON_DECIMAL_VALUES_NOT_ORIGINAL_FLOAT_RISK',
                denominator='INVESTED_SECURITIES_ONLY_EXCLUDES_CASH',
                invested_value=rational(total), metrics=metrics,
                security_weights={sid: rational(value) for sid, value in sorted(weights.items())},
                chain_weights={chain: rational(value) for chain, value in sorted(chains.items())},
                label_observations={sid: dict(labels[sid]) for sid in sorted(labels)},
                source_bytes_authenticated=False, original_saved_risk=False,
                order_gate_evaluated=False, account_executed=False,
                historical_label_validity_verified=False, point_in_time_verified=False,
                promotion_allowed=False)
