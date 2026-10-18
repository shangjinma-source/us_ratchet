"""Exact cash-flow boundary accounting for explicit hypothetical buy-only paths.

No selection, risk gate, cash-buffer policy, execution, source certification or
calendar discovery. Zero-capital inception is explicitly unsupported: a positive
prior-close valuation and positive pre/post-flow Open valuations are required.
Input dates denote observed successive marks, not certified adjacent sessions.
"""
from datetime import date
from decimal import Context, Decimal, localcontext
from fractions import Fraction


SCHEMA = 'BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1'
MAX_SESSIONS = 512
MAX_SECURITIES = 256
MAX_SHARES = 10**12
MAX_RATIO_BITS = 12000  # Output/resource bound, not an investment constraint.


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    require(type(value) in (Decimal, str, int), 'Use decimal literals/Decimal/int, not float or bool')
    if type(value) is str:
        require(0 < len(value) <= 80 and value.strip() == value, 'Bounded decimal literal required')
    if type(value) is int:
        require(abs(value) <= 10**40, 'Numeric resource bound exceeded')
    try:
        with localcontext(Context(prec=160)):
            parsed = Decimal(value)
    except Exception as error:
        raise ValueError('Invalid decimal') from error
    require(parsed.is_finite() and len(parsed.as_tuple().digits) <= 40
            and abs(parsed.as_tuple().exponent) <= 40, 'Finite bounded decimal required')
    result = Fraction(parsed)
    require(0 <= result <= 10**40, 'Nonnegative bounded value required')
    return result


def day(value):
    require(type(value) is str and date.fromisoformat(value).isoformat() == value, 'Canonical YYYY-MM-DD required')
    return value


def shares(value):
    require(type(value) is dict and len(value) <= MAX_SECURITIES, 'Bounded explicit SID-to-share map required')
    for sid, quantity in value.items():
        require(type(sid) is str and sid and sid.strip() == sid, 'Nonblank SID required')
        require(type(quantity) is int and 0 <= quantity <= MAX_SHARES, 'Whole nonnegative shares required; no sells')
    return dict(sorted(value.items()))


def prices(value, required):
    require(type(value) is dict and set(value) == set(required), 'Exact full old-and-bought SID price union required')
    result = {sid: number(value[sid]) for sid in sorted(required)}
    require(all(value > 0 for value in result.values()), 'Prices must be positive')
    return result


def money(value):
    """Exact finite decimal, without division under a caller Decimal context."""
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    require(denominator == 1, 'Money unexpectedly has nonterminating decimal representation')
    places = max(twos, fives)
    integer = value.numerator * 2**(places - twos) * 5**(places - fives)
    sign = '-' if integer < 0 else ''
    digits = str(abs(integer)).zfill(places + 1)
    if not places:
        return sign + digits
    return sign + (digits[:-places] + '.' + digits[-places:]).rstrip('0').rstrip('.')


def ratio(value):
    require(max(abs(value.numerator).bit_length(), value.denominator.bit_length()) <= MAX_RATIO_BITS,
            'Exact cumulative ratio exceeds explicit output resource bound')
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def mark(cash, holdings, marks):
    return cash + sum((quantity * marks[sid] for sid, quantity in holdings.items()), Fraction(0))


def account_path(*, initial, sessions, transaction_cost_bps):
    """Reconcile explicit buys, with injection AFTER pre-flow Open valuation.

    Each session requires session, open_prices, close_prices,
    cash_injection_usd (including explicit zero), buy_shares (including {}).
    r_overnight = V_open_minus / V_previous_close - 1
    r_after_flow = V_close / (V_open_minus + injection) - 1
    chained TWR = product((1+r_overnight)*(1+r_after_flow)) - 1.
    The post-flow denominator is BEFORE fees, so transaction fees reduce return.
    No withdrawals, dividends, cash interest, FX, splits or automatic class swaps.
    """
    require(type(initial) is dict and set(initial) == {'session', 'cash_usd', 'holdings', 'close_prices'}, 'Exact initial contract required')
    require(type(sessions) is list and 1 <= len(sessions) <= MAX_SESSIONS, 'Nonempty bounded explicit sessions required')
    previous_day = day(initial['session'])
    cash = number(initial['cash_usd'])
    holdings = shares(initial['holdings'])
    initial_marks = prices(initial['close_prices'], holdings)
    initial_value = previous_value = mark(cash, holdings, initial_marks)
    require(initial_value > 0, 'UNSUPPORTED_ZERO_CAPITAL_INCEPTION: prior Close must have positive equity')
    fee_bps = number(transaction_cost_bps)
    require(fee_bps <= 10000, 'Fee exceeds 10000 bps')
    rate = fee_bps / 10000
    cumulative, total_flow, total_fees = Fraction(1), Fraction(0), Fraction(0)
    rows = []
    for session in sessions:
        require(type(session) is dict and set(session) == {'session', 'open_prices', 'close_prices', 'cash_injection_usd', 'buy_shares'}, 'Exact session contract required')
        current_day = day(session['session'])
        require(current_day > previous_day, 'Sessions must be strictly increasing, no duplicate/reorder')
        buys = shares(session['buy_shares'])
        union = set(holdings) | set(buys)
        require(len(union) <= MAX_SECURITIES, 'SID union resource bound exceeded')
        opens, closes = prices(session['open_prices'], union), prices(session['close_prices'], union)
        injection = number(session['cash_injection_usd'])
        before_flow = mark(cash, holdings, opens)
        after_flow = before_flow + injection
        require(previous_value > 0 and before_flow > 0 and after_flow > 0, 'Undefined zero-equity cash-flow boundary; no epsilon substitution')
        gross = sum((quantity * opens[sid] for sid, quantity in buys.items()), Fraction(0))
        fees = gross * rate
        new_cash = cash + injection - gross - fees
        require(new_cash >= 0, 'Insufficient cash for explicit buys and fees')
        new_holdings = {sid: holdings.get(sid, 0) + buys.get(sid, 0) for sid in sorted(union)}
        require(all(quantity <= MAX_SHARES for quantity in new_holdings.values()), 'Final share resource bound exceeded')
        after_trades = mark(new_cash, new_holdings, opens)
        closing = mark(new_cash, new_holdings, closes)
        require(after_trades == after_flow - fees, 'Open conservation mismatch')
        overnight_factor, after_flow_factor = before_flow / previous_value, closing / after_flow
        factor = overnight_factor * after_flow_factor
        cumulative *= factor
        total_flow += injection
        total_fees += fees
        rows.append({'previous_close_session': previous_day, 'session': current_day,
                     'previous_close_equity_usd': money(previous_value), 'pre_flow_open_equity_usd': money(before_flow),
                     'cash_injection_usd': money(injection), 'post_flow_pre_fee_open_equity_usd': money(after_flow),
                     'post_trade_open_equity_usd': money(after_trades), 'close_equity_usd': money(closing),
                     'gross_buy_usd': money(gross), 'fees_usd': money(fees), 'cash_after_usd': money(new_cash),
                     'holdings_before': dict(holdings), 'buy_shares': buys, 'holdings_after': dict(new_holdings),
                     'overnight_pnl_usd': money(before_flow - previous_value),
                     'intraday_mark_pnl_before_fees_usd': money(closing - after_trades),
                     'after_flow_pnl_net_fees_usd': money(closing - after_flow),
                     'cash_flow_adjusted_pnl_usd': money(closing - previous_value - injection),
                     'overnight_return': ratio(overnight_factor - 1), 'after_flow_return': ratio(after_flow_factor - 1),
                     'session_twr': ratio(factor - 1), 'cumulative_twr': ratio(cumulative - 1)})
        previous_day, previous_value, cash, holdings = current_day, closing, new_cash, new_holdings
    return {'schema': SCHEMA, 'rows': rows, 'initial_equity_usd': money(initial_value),
            'terminal_equity_usd': money(previous_value), 'total_cash_injection_usd': money(total_flow),
            'total_fees_usd': money(total_fees), 'net_dollar_pnl_excluding_injections_usd': money(previous_value - initial_value - total_flow),
            'chained_twr': ratio(cumulative - 1), 'transaction_cost_bps': money(fee_bps),
            'cash_event_timing': 'AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES',
            'arithmetic': 'EXACT_RATIONAL_VALUES_FINITE_DECIMAL_MONEY_NO_FLOAT_INPUT',
            'zero_capital_inception_supported': False, 'cash_buffer_and_risk_gates_evaluated': False,
            'dividends_modelled': False, 'corporate_actions_modelled': False, 'cash_interest_modelled': False,
            'withdrawals_supported': False, 'exchange_session_adjacency_verified': False,
            'historical_experiment_executed': False, 'orders_executed': False,
            'point_in_time_verified': False, 'promotion_allowed': False,
            'parameter_authority': 'CALLER_SUPPLIED_SYNTHETIC_OR_EXPLICIT_SCENARIO_NOT_SOURCE_BOUND',
            'engineering_resource_limits_not_investment_policy': {'sessions': MAX_SESSIONS, 'security_ids': MAX_SECURITIES, 'ratio_bits': MAX_RATIO_BITS}}
