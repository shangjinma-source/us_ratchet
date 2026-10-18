"""Pure gross dividend accrual sensitivity; never payment or total-return proof.

The caller supplies provider-event dates and explicitly assumes compatible
share units. No source IO, trading, cash credit, reinvestment or annualization.
"""
from datetime import date
from fractions import Fraction
import math


PRICE_BASIS = 'PROVIDER_QUOTE_CLOSE_NOT_DIVIDEND_ADJUSTED_ASSUMPTION'


class DividendDiagnosticInputError(ValueError):
    """The supplied book/events cannot support this limited diagnostic."""


def _require(condition, message):
    if not condition:
        raise DividendDiagnosticInputError(message)


def _number(value):
    _require(type(value) in (str, int, float), 'Explicit rational number; bool denied')
    _require(type(value) is not float or math.isfinite(value), 'Finite number required')
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise DividendDiagnosticInputError('Invalid rational number') from error
    _require(result >= 0, 'Nonnegative number required')
    return result


def _day(value):
    _require(type(value) is str, 'ISO session date required')
    try:
        valid = date.fromisoformat(value).isoformat() == value
    except ValueError:
        valid = False
    _require(valid, 'Canonical ISO date required')
    return value


def _shares(value):
    _require(type(value) is dict and all(type(key) is str and key and type(quantity) is int and quantity >= 0
                                       for key, quantity in value.items()), 'Nonnegative whole shares by explicit security ID required')
    return dict(value)


def diagnose_dividend_accrual(*, book, events, initial_shares, initial_equity,
                             price_basis, same_share_unit_basis):
    """Derive equity including cumulative gross entitlements from a complete book.

    Previous-session closing shares qualify, including shares sold on event day;
    same-day purchases do not. First-day eligibility uses explicit initial_shares.
    initial_equity is the pre-window equity, not the first closing observation.
    Events inside the date window must map to an actual session; never roll dates.
    Empty events do not establish that no dividends occurred.
    """
    _require(price_basis == PRICE_BASIS and same_share_unit_basis is True,
             'Explicit unadjusted-for-dividend Close and same-share-unit assumptions required')
    _require(type(book) is dict and book.get('status') == 'COMPLETE_CONDITIONAL_PAPER_BOOK', 'Complete conditional book required')
    rows = book.get('daily_rows')
    _require(type(rows) is list and rows, 'Nonempty daily rows required')
    previous_shares = _shares(initial_shares)
    baseline = _number(initial_equity)
    _require(baseline > 0, 'Positive pre-window initial equity required')
    sessions, equities, holdings = [], [], []
    for row in rows:
        _require(type(row) is dict and {'session', 'shares', 'close_equity', 'external_cash_flow'} <= set(row), 'Explicit daily book fields required')
        sessions.append(_day(row['session']))
        equities.append(_number(row['close_equity']))
        holdings.append(_shares(row['shares']))
        _require(equities[-1] > 0 and _number(row['external_cash_flow']) == 0, 'Positive equity and zero external flows required')
    _require(sessions == sorted(set(sessions)), 'Unique increasing sessions required')
    _require(type(events) is list, 'Explicit event list required')
    by_session, identifiers, security_dates = {}, set(), set()
    outside_count = 0
    for event in events:
        _require(type(event) is dict and set(event) == {'id', 'security_id', 'event_date', 'amount_per_share'}, 'Explicit closed event fields required')
        identifier, security = event['id'], event['security_id']
        _require(type(identifier) is str and identifier and type(security) is str and security, 'Nonempty event/security IDs required')
        event_day, amount = _day(event['event_date']), _number(event['amount_per_share'])
        _require(identifier not in identifiers and (security, event_day) not in security_dates, 'Duplicate event ID or security/date denied')
        identifiers.add(identifier)
        security_dates.add((security, event_day))
        if event_day < sessions[0] or event_day > sessions[-1]:
            outside_count += 1
            continue
        _require(event_day in sessions, 'In-window event must have an explicit book session')
        by_session.setdefault(event_day, []).append((identifier, security, amount))
    accrued, peak, previous_equity, max_drawdown = Fraction(0), baseline, baseline, Fraction(0)
    daily, accrual_events = [], []
    for session, close_equity, shares in zip(sessions, equities, holdings):
        entitlement = Fraction(0)
        for identifier, security, amount in sorted(by_session.get(session, [])):
            eligible = previous_shares.get(security, 0)
            gross = eligible * amount
            entitlement += gross
            accrual_events.append(dict(id=identifier, security_id=security, event_date=session,
                                       amount_per_share=str(amount), eligible_shares=eligible,
                                       gross_entitlement=str(gross), payment_date=None, payment_verified=False))
        accrued += entitlement
        equity = close_equity + accrued
        peak = max(peak, equity)
        drawdown = equity / peak - 1
        max_drawdown = min(max_drawdown, drawdown)
        daily.append(dict(session=session, original_close_equity=str(close_equity),
                          gross_entitlement=str(entitlement), cumulative_gross_entitlement=str(accrued),
                          derived_close_equity=str(equity), daily_net_return=str(equity / previous_equity - 1),
                          cumulative_net_return=str(equity / baseline - 1), drawdown=str(drawdown)))
        previous_shares, previous_equity = shares, equity
    return dict(schema='GROSS_DIVIDEND_ACCRUAL_DIAGNOSTIC_V1', status='COMPLETE_CONDITIONAL_DIAGNOSTIC',
                price_basis=price_basis, same_share_unit_basis_assumed=True,
                initial_equity=str(baseline), gross_accrual_events=accrual_events, daily_rows=daily,
                input_event_count=len(events), in_window_event_count=len(accrual_events),
                ignored_outside_window_event_count=outside_count,
                cumulative_gross_entitlement=str(accrued), derived_final_equity=str(previous_equity),
                derived_net_return=str(previous_equity / baseline - 1), derived_max_drawdown=str(max_drawdown),
                conditional_diagnostic_only=True, event_coverage_complete_verified=False,
                event_date_is_ex_dividend_date_assumed=True, share_unit_basis_verified=False,
                payment_verified=False, taxes_and_withholding_included=False,
                original_book_modified=False, cash_credited=False, trades_changed=False, reinvestment_performed=False,
                total_return_certified=False, annualization_performed=False, cagr=None)
