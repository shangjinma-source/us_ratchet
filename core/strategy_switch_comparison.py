"""Compare hold versus candidate on common mature scenarios, ignoring commission.

Pure research arithmetic, not an order or a dynamic switching policy. Candidate
cash assumes completed sales. Callers must review units, source availability,
issuer exposure and execution constraints before using the comparison.
"""
from datetime import date
from fractions import Fraction
from math import prod


def compare_switch(*, cash, holdings, candidate, prices, scenarios,
                   scenario_dates, decision_date, slippage_bps):
    def amount(value):
        if type(value) not in (str, int, Fraction):
            raise ValueError('EXACT_AMOUNT_REQUIRED')
        value = Fraction(value)
        if value < 0:
            raise ValueError('NEGATIVE_AMOUNT')
        return value

    date.fromisoformat(decision_date)
    if not scenarios or len(scenarios) != len(scenario_dates):
        raise ValueError('COMMON_SCENARIOS_REQUIRED')
    if scenario_dates != sorted(set(scenario_dates)) or any(date.fromisoformat(day) > date.fromisoformat(decision_date) for day in scenario_dates):
        raise ValueError('MATURE_UNIQUE_SCENARIOS_REQUIRED')
    for portfolio in (holdings, candidate):
        if not isinstance(portfolio, dict) or any(type(q) is not int or q < 0 for q in portfolio.values()):
            raise ValueError('INTEGER_LONG_POSITIONS_REQUIRED')
    domain = {sid for portfolio in (holdings, candidate) for sid, q in portfolio.items() if q}
    if not domain <= prices.keys() or any(not domain <= row.keys() for row in scenarios):
        raise ValueError('COMMON_VALUATION_DOMAIN_REQUIRED')
    marks = {sid: amount(prices[sid]) for sid in domain}
    if any(value <= 0 for value in marks.values()):
        raise ValueError('POSITIVE_MARKS_REQUIRED')
    gross = [{sid: amount(row[sid]) for sid in domain} for row in scenarios]
    if any(value <= 0 for row in gross for value in row.values()):
        raise ValueError('POSITIVE_GROSS_REQUIRED')
    balance = amount(cash)
    equity = balance + sum((holdings.get(sid, 0) * marks[sid] for sid in domain), Fraction(0))
    slip = amount(slippage_bps) / 10000
    if equity <= 0 or slip >= 1:
        raise ValueError('INVALID_EQUITY_OR_SLIPPAGE')
    buy = sum((max(candidate.get(sid, 0) - holdings.get(sid, 0), 0) * marks[sid] for sid in domain), Fraction(0))
    sell = sum((max(holdings.get(sid, 0) - candidate.get(sid, 0), 0) * marks[sid] for sid in domain), Fraction(0))
    residual = balance + sell * (1 - slip) - buy * (1 + slip)

    def evaluate(portfolio, cash_value):
        growth = [(cash_value + sum((portfolio.get(sid, 0) * marks[sid] * row[sid] for sid in domain), Fraction(0))) / equity for row in gross]
        return dict(growth=[str(value) for value in growth], product=str(prod(growth)),
                    maximum_security_weight=str(max((portfolio.get(sid, 0) * marks[sid] / equity for sid in domain), default=Fraction(0))))

    result = dict(equity=str(equity), buy_notional=str(buy), sell_notional=str(sell),
                  commission_assumption='IGNORED_BY_USER_REQUEST', slippage_bps=str(Fraction(slippage_bps)),
                  slippage_cost=str((buy + sell) * slip), candidate_cash=str(residual),
                  hold=evaluate(holdings, balance), candidate=None, ranking='UNAFFORDABLE',
                  orders_created=False, trigger_defined=False)
    if residual >= 0:
        result['candidate'] = evaluate(candidate, residual)
        left, right = Fraction(result['candidate']['product']), Fraction(result['hold']['product'])
        result['ranking'] = 'CANDIDATE_HIGHER' if left > right else 'HOLD_HIGHER' if left < right else 'TIE'
    return result
