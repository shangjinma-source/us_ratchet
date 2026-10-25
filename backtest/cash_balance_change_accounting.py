"""Exact external-flow accounting for isolated cash-policy research only."""
from fractions import Fraction


def amount(value):
    if isinstance(value, bool):
        raise ValueError('BOOLEAN_AMOUNT')
    result = Fraction(str(value))
    if result < 0:
        raise ValueError('NEGATIVE_BALANCE_OR_VALUE')
    return result


def replace_available_cash(*, previous_cash, entered_cash, tradable_stock_value,
                           nontradable_value='0'):
    """A confirmed total replaces cash; the difference is an external flow.

    Callers must first reconcile actual fills/reservations. This function cannot
    infer deposits from stale account snapshots or validate broker settlement.
    """
    old, new = amount(previous_cash), amount(entered_cash)
    stock, pending = amount(tradable_stock_value), amount(nontradable_value)
    return dict(cash=str(new), external_flow=str(new-old),
                equity_before=str(old+stock+pending),
                equity_after=str(new+stock+pending),
                selection_equity=str(new+stock),
                nontradable_value=str(pending))


def unitized_performance(*, initial_equity, observations):
    """Each row gives equity immediately before/after its flow and at close.

    Flow executes at the disclosed valuation boundary. Trading costs belong
    after that boundary. Both the pre-flow mark and close enter drawdown.
    """
    previous = amount(initial_equity)
    if not previous:
        raise ValueError('POSITIVE_INITIAL_EQUITY_REQUIRED')
    nav = peak = Fraction(1)
    drawdown = Fraction(0)
    last_date = None
    marks = []
    for row in observations:
        day = row['date']
        if last_date is not None and day <= last_date:
            raise ValueError('ORDERED_UNIQUE_OBSERVATIONS_REQUIRED')
        before, after, close = (amount(row[key]) for key in
                                ('equity_before', 'equity_after', 'close_equity'))
        if isinstance(row['external_flow'], bool):
            raise ValueError('BOOLEAN_FLOW')
        flow = Fraction(str(row['external_flow']))
        if after != before+flow:
            raise ValueError('EXTERNAL_FLOW_RECONCILIATION_FAILED')
        if not previous or not before or not after:
            raise ValueError('ZERO_EQUITY_REQUIRES_SEPARATE_SEGMENT')
        nav *= before/previous
        peak = max(peak, nav)
        drawdown = max(drawdown, 1-nav/peak)
        nav *= close/after
        peak = max(peak, nav)
        drawdown = max(drawdown, 1-nav/peak)
        marks.append(dict(date=day, unit_nav=str(nav)))
        previous, last_date = close, day
    return dict(time_weighted_return=str(nav-1),
                maximum_flow_adjusted_drawdown=str(drawdown), marks=marks)
