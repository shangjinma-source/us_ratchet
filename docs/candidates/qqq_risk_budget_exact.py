"""Fixed 63-day research sizing. No account access, price fetching or execution."""
from datetime import date
from fractions import Fraction
from math import isqrt, sqrt


WINDOW = 63


def _number(value):
    if isinstance(value, bool):
        raise ValueError('BOOLEAN_FINANCIAL_VALUE')
    try:
        return Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError) as error:
        raise ValueError('INVALID_FINANCIAL_VALUE') from error


def _day(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError('CANONICAL_DATE_REQUIRED')
    return value


def _variance(values):
    mean = sum(values, Fraction(0)) / WINDOW
    return sum(((value - mean) ** 2 for value in values), Fraction(0)) / (WINDOW - 1)


def scale_targets_to_qqq_risk(*, decision_date, target_quantities, decision_prices,
                             tradable_equity, stock_gross_returns, qqq_gross_returns):
    """Map SID -> date -> gross return; all 63 dates must match QQQ exactly.

    Caller authenticates complete exchange sessions and company-action-consistent
    return coordinates. Prices are decision-close executable nominal units;
    gross returns are unitless. No annualization is needed in the variance ratio.
    Nontradable rights are excluded from tradable_equity by the owning caller.
    """
    _day(decision_date)
    if not all(isinstance(x, dict) for x in (target_quantities, decision_prices,
                                           stock_gross_returns, qqq_gross_returns)):
        raise ValueError('EXPLICIT_MAPPING_REQUIRED')
    securities = set(target_quantities)
    if securities != set(decision_prices) or securities != set(stock_gross_returns):
        raise ValueError('SECURITY_DOMAIN_MISMATCH')
    if any(type(s) is not str or not s for s in securities):
        raise ValueError('SECURITY_ID_REQUIRED')
    if any(type(q) is not int or q < 0 for q in target_quantities.values()):
        raise ValueError('NONNEGATIVE_INTEGER_TARGET_REQUIRED')
    equity = _number(tradable_equity)
    prices = {s: _number(p) for s, p in decision_prices.items()}
    if equity <= 0 or any(p <= 0 for p in prices.values()):
        raise ValueError('POSITIVE_PRICE_AND_EQUITY_REQUIRED')
    dates = sorted(_day(d) for d in qqq_gross_returns)
    if len(dates) != WINDOW or dates[-1] != decision_date:
        raise ValueError('CURRENT_COMPLETE_63_DAY_WINDOW_REQUIRED')
    def returns(series):
        if not isinstance(series, dict) or set(series) != set(dates):
            raise ValueError('SAME_63_DATES_REQUIRED')
        gross = [_number(series[d]) for d in dates]
        if any(g <= 0 for g in gross):
            raise ValueError('POSITIVE_GROSS_RETURN_REQUIRED')
        return [g - 1 for g in gross]
    benchmark = returns(qqq_gross_returns)
    stocks = {s: returns(stock_gross_returns[s]) for s in securities}
    weights = {s: target_quantities[s] * prices[s] / equity for s in securities}
    invested = sum(weights.values(), Fraction(0))
    if invested > 1:
        raise ValueError('TARGET_EXCEEDS_TRADABLE_EQUITY')
    portfolio = [sum((weights[s] * stocks[s][i] for s in securities), Fraction(0))
                 for i in range(WINDOW)]
    portfolio_variance, qqq_variance = _variance(portfolio), _variance(benchmark)
    ratio = min(Fraction(1), qqq_variance / portfolio_variance) if portfolio_variance else Fraction(1)
    # floor(q * sqrt(ratio)) exactly, even arbitrarily close to an integer.
    scaled = {s: isqrt(q * q * ratio.numerator // ratio.denominator)
              for s, q in target_quantities.items()}
    invested_after = sum((scaled[s] * prices[s] for s in securities), Fraction(0))
    return dict(target_quantities=scaled, original_target_quantities=dict(target_quantities),
                decision_date=decision_date, dates=dates, observations=WINDOW,
                portfolio_variance=str(portfolio_variance), qqq_variance=str(qqq_variance),
                scale_squared_exact=str(ratio), scale_display=sqrt(float(ratio)),
                original_weights={s: str(w) for s, w in sorted(weights.items())},
                original_cash_weight=str(1-invested),
                target_value_after=str(invested_after), cash_after_at_decision_prices=str(equity-invested_after),
                reason='ZERO_PORTFOLIO_VARIANCE_KEEP_TARGET' if not portfolio_variance else
                       'QQQ_RISK_BUDGET_SCALED' if ratio < 1 else 'WITHIN_QQQ_RISK_BUDGET',
                research_only=True)
