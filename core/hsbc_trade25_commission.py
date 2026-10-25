"""Trade25 US brokerage quote for one confirmed broker charging unit.

Not total transaction cost. Partial fills must not be treated as separate
charging units without broker evidence. No default FX or account turnover.
Sources and remaining uncertainties: research_contracts/hsbc_trade25_20261024.json.
"""
from datetime import datetime, timedelta, timezone
from fractions import Fraction


def _amount(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError('EXACT_AMOUNT_REQUIRED')
    result = Fraction(value)
    if result < 0:
        raise ValueError('NEGATIVE_AMOUNT')
    return result


def quote_commission(*, executed_at, turnover_month, prior_turnover_hkd,
                     gross_usd, quantity, execution_hkd_per_usd,
                     charging_unit_confirmed):
    """Caller supplies complete pre-trade turnover for the execution HK month."""
    instant = datetime.fromisoformat(executed_at.replace('Z', '+00:00'))
    if instant.utcoffset() is None:
        raise ValueError('AWARE_EXECUTION_TIME_REQUIRED')
    month = instant.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m')
    if turnover_month != month:
        raise ValueError('EXECUTION_MONTH_TURNOVER_REQUIRED')
    if type(quantity) is not int or quantity <= 0:
        raise ValueError('POSITIVE_INTEGER_QUANTITY_REQUIRED')
    if type(charging_unit_confirmed) is not bool:
        raise ValueError('CHARGING_UNIT_FLAG_REQUIRED')
    prior = _amount(prior_turnover_hkd)
    gross = _amount(gross_usd)
    rate = _amount(execution_hkd_per_usd)
    if not gross or not rate:
        raise ValueError('POSITIVE_GROSS_AND_FX_REQUIRED')
    result = dict(month=month, prior_turnover_hkd=str(prior),
                  after_turnover_hkd=str(prior + gross * rate),
                  commission_usd=None, total_cost_known=False)
    if not charging_unit_confirmed:
        result['status'] = 'CHARGING_UNIT_UNCONFIRMED'
    elif prior == 250000:
        # Summary tables say >= while detailed waiver text says exceeds.
        # Do not silently choose a rule for this exact starting boundary.
        result['status'] = 'EXACT_THRESHOLD_REQUIRES_CONFIRMATION'
    elif prior < 250000:
        result.update(status='WAIVED_INCLUDING_FIRST_CROSSING', commission_usd='0')
    else:
        fee = Fraction(18) + max(0, quantity - 1000) * Fraction('0.015')
        result.update(status='STANDARD_BROKERAGE', commission_usd=str(fee))
    return result
