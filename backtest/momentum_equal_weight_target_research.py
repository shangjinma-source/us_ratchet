"""Research-only target sizing for the fixed 252/21 momentum experiment.

Consumes a caller-authenticated static roster and tradable equity. It neither
admits corporate actions nor values unpaid rights, and never executes trades.
"""
from fractions import Fraction


def build_target(*, roster, decision_date, investable_equity, nominal_prices):
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    require(roster['decision_date'] == decision_date, 'ROSTER_DATE_MISMATCH')
    selected = roster['selected']
    require(len(selected) == 10, 'EXACTLY_TEN_REQUIRED')
    securities = [row['security_id'] for row in selected]
    issuers = [row['issuer_id'] for row in selected]
    require(all(securities) and len(set(securities)) == 10, 'DUPLICATE_SECURITY')
    require(all(issuers) and len(set(issuers)) == 10, 'DUPLICATE_ISSUER')
    require(type(roster['gate']['risk_on']) is bool, 'BOOLEAN_MARKET_GATE_REQUIRED')
    require(not isinstance(investable_equity, bool), 'INVALID_EQUITY')
    equity = Fraction(str(investable_equity))
    require(equity > 0, 'POSITIVE_TRADABLE_EQUITY_REQUIRED')
    prices = {}
    for security in securities:
        require(security in nominal_prices, 'MISSING_SELECTED_PRICE')
        value = nominal_prices[security]
        require(not isinstance(value, bool), 'INVALID_PRICE')
        prices[security] = Fraction(str(value))
        require(prices[security] > 0, 'POSITIVE_NOMINAL_PRICE_REQUIRED')
    quantities = ({security: int((equity / 10) // prices[security])
                   for security in securities} if roster['gate']['risk_on'] else {})
    target_value = sum((prices[s] * q for s, q in quantities.items()), Fraction(0))
    return dict(decision_date=decision_date, target_quantities=quantities,
                investable_equity=str(equity), target_value=str(target_value),
                unallocated_equity=str(equity - target_value),
                method='FIXED_252_21_TOP10_EQUAL_WEIGHT_MONTHLY_MARKET_GATE',
                research_only=True, execution_authorized=False)
