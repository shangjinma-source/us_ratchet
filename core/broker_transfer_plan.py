"""Read-only funding plan after HSBC monthly waiver is exhausted.

Inputs are already-selected integer BUY orders, not new strategy signals.
Transfer and other fees are explicit budget assumptions, never broker facts.
"""
from fractions import Fraction

from core.usmart_standard_fees import _amount, estimate_base_fee


def fit_integer_buys(*, buys, available_cash, other_fee_reserve):
    """Scale an unfunded BUY basket, then allocate at most one rounding share.

    Does not change the strategy target. Result is a budget preview only.
    Fees are recomputed for every nonempty order; quantities never exceed input.
    """
    budget, other = _amount(available_cash), _amount(other_fee_reserve)
    def cost(rows):
        active = [row for row in rows if row['quantity']]
        return sum((_amount(row['limit_price']) * row['quantity'] +
                    Fraction(estimate_base_fee(quantity=row['quantity'],
                        price_usd=row['limit_price'])['platform_fee_reserve_usd'])
                    for row in active), Fraction(0)) + (other if active else 0)
    if cost(buys) <= budget:
        return [dict(row) for row in buys]
    gross = sum((_amount(row['limit_price'])*row['quantity'] for row in buys), Fraction(0))
    fees = cost(buys)-gross-(other if buys else 0)
    ratio = min(Fraction(1), max(Fraction(0), budget-other-fees)/gross) if gross else Fraction(0)
    result = [dict(row, quantity=int(row['quantity']*ratio)) for row in buys]
    # Stable largest-remainder allocation; a single bounded pass, no optimization sweep.
    ranking = sorted(range(len(buys)), key=lambda i: (-(buys[i]['quantity']*ratio-result[i]['quantity']), buys[i]['symbol']))
    for index in ranking:
        if result[index]['quantity'] >= buys[index]['quantity']:
            continue
        result[index]['quantity'] += 1
        if cost(result) > budget:
            result[index]['quantity'] -= 1
    assert cost(result) <= budget
    return [row for row in result if row['quantity']]


def plan_usmart_funding(*, hsbc_cash, usmart_cash, buys,
                       other_fee_reserve, transfer_fee_reserve,
                       hsbc_waiver_exhausted, hsbc_minimum_cash='0'):
    if hsbc_waiver_exhausted is not True:
        raise ValueError('HSBC_WAIVER_PRIORITY_REQUIRES_SEPARATE_ALLOCATION')
    hsbc, usmart = _amount(hsbc_cash), _amount(usmart_cash)
    other, transfer_fee = _amount(other_fee_reserve), _amount(transfer_fee_reserve)
    minimum = _amount(hsbc_minimum_cash)
    gross = platform = Fraction(0)
    seen = set()
    for order in buys:
        symbol, quantity = order['symbol'], order['quantity']
        price = _amount(order['limit_price'])
        if not isinstance(symbol, str) or not symbol.strip() or symbol in seen:
            raise ValueError('UNIQUE_SYMBOL_REQUIRED')
        if type(quantity) is not int or quantity <= 0 or price <= 0:
            raise ValueError('POSITIVE_INTEGER_BUY_REQUIRED')
        seen.add(symbol)
        gross += quantity * price
        platform += Fraction(estimate_base_fee(
            quantity=quantity, price_usd=price)['platform_fee_reserve_usd'])
    required = gross + platform + (other if seen else 0)
    # Round the proposed credited transfer up to a cent.
    shortfall = max(Fraction(0), required - usmart)
    transfer = Fraction(-(-shortfall.numerator * 100 // shortfall.denominator), 100)
    debit = transfer + (transfer_fee if transfer else 0)
    transferable = max(Fraction(0), hsbc - minimum)
    shortage = max(Fraction(0), debit - transferable)
    return {
        'status': 'INSUFFICIENT_TOTAL_CASH' if shortage else 'FUNDING_PLAN_ONLY',
        'gross_buy_usd': str(gross), 'platform_fee_reserve_usd': str(platform),
        'usmart_required_usd': str(required),
        'proposed_transfer_credit_usd': str(transfer),
        'hsbc_debit_budget_usd': str(debit),
        'hsbc_remaining_if_funded_usd': str(hsbc-debit) if not shortage else None,
        'funding_shortage_usd': str(shortage),
        'hsbc_minimum_cash_usd': str(minimum),
        'maximum_transfer_credit_usd': str(max(Fraction(0), transferable-transfer_fee)),
        'confirmed_usmart_cash_usd': str(usmart),
        'total_confirmed_cash_usd': str(hsbc+usmart),
        'executable': False, 'total_cost_known': False,
    }
