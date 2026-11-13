"""Pure uSMART personal-standard base-fee estimates; no account writes.

Tariff supplied by user 2026-11-10. Excludes settlement/regulatory fees.
One call represents one order, not each partial fill. No promotions assumed.
"""
from fractions import Fraction


def _amount(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
        raise ValueError('EXACT_AMOUNT_REQUIRED')
    result = Fraction(value)
    if result < 0:
        raise ValueError('NONNEGATIVE_AMOUNT_REQUIRED')
    return result


def estimate_base_fee(*, quantity, price_usd):
    quantity, price = _amount(quantity), _amount(price_usd)
    if quantity <= 0 or price <= 0:
        raise ValueError('POSITIVE_QUANTITY_AND_PRICE_REQUIRED')
    if quantity < 1:
        fee = Fraction('0.99')
    else:
        fee = max(Fraction('1.88'), min(quantity * Fraction('0.009'), quantity * price / 100))
    # Conservative cent reserve; actual broker rounding is not established.
    reserve = Fraction(-(-fee.numerator * 100 // fee.denominator), 100)
    return dict(commission_usd='0', platform_fee_exact_usd=str(fee),
                platform_fee_reserve_usd=str(reserve), total_cost_known=False,
                plan='USMART_PERSONAL_STANDARD_NO_PROMOTION')


def affordable_integer_buy(*, cash_usd, target_quantity, limit_price_usd,
                           other_fee_reserve_usd):
    """Bound a BUY by confirmed spendable cash, never future sell proceeds.

    Caller must separately supply other-fee reserve and account reservations.
    Return is an estimate, not an executable order or full-cost guarantee.
    """
    cash, price = _amount(cash_usd), _amount(limit_price_usd)
    other = _amount(other_fee_reserve_usd)
    if type(target_quantity) is not int or target_quantity < 0 or price <= 0:
        raise ValueError('VALID_TARGET_AND_PRICE_REQUIRED')
    low, high = 0, min(target_quantity, int(cash // price))
    while low < high:
        middle = (low + high + 1) // 2
        fee = Fraction(estimate_base_fee(quantity=middle, price_usd=price)['platform_fee_reserve_usd'])
        if middle * price + fee + other <= cash:
            low = middle
        else:
            high = middle - 1
    fee = Fraction(estimate_base_fee(quantity=low, price_usd=price)['platform_fee_reserve_usd']) if low else Fraction(0)
    cost = low * price + fee + (other if low else 0)
    return dict(quantity=low, estimated_cash_required=str(cost),
                remaining_cash=str(cash-cost), executable=False,
                total_cost_known=False)
