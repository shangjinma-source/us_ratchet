"""Exact explicit-window diagnostics for four distinct cash-fork/reference roles."""
from datetime import date
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction

SCHEMA = 'CASH_FORK_FOUR_ROLE_EXACT_REFERENCE_WINDOW_V1'
TIMING = 'AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES'


def require(ok,message):
    if not ok: raise ValueError(message)


def day(value):
    require(type(value) is str and date.fromisoformat(value).isoformat()==value,'Canonical date required')
    return value


def number(value):
    require(type(value) in (str,int,Decimal),'Decimal literal required, not float/bool')
    if type(value) is str: require(0<len(value)<=80 and value.strip()==value,'Bounded decimal literal required')
    if type(value) is int: require(abs(value)<=10**40,'Numeric bound exceeded')
    parsed=Decimal(value)
    require(parsed.is_finite() and len(parsed.as_tuple().digits)<=40 and abs(parsed.as_tuple().exponent)<=40,'Finite bounded decimal required')
    return Fraction(parsed)


def ratio(value):
    return {'numerator':str(value.numerator),'denominator':str(value.denominator)}


def from_ratio(value):
    require(type(value) is dict and set(value)=={'numerator','denominator'}
        and all(type(v) is str and len(v)<=4000 for v in value.values()),'Explicit exact ratio required')
    numerator,denominator=int(value['numerator']),int(value['denominator'])
    require(denominator>0,'Positive ratio denominator required')
    return Fraction(numerator,denominator)


def metrics(calendar,wealth):
    require(len(calendar)==len(wealth)>=2 and wealth[0]==1 and all(value>0 for value in wealth),'Positive wealth including initial one required')
    peak,worst=Fraction(1),Fraction(0)
    for value in wealth:
        peak=max(peak,value); worst=max(worst,1-value/peak)
    intervals=len(calendar)-1
    with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)) as context:
        terminal=Decimal(wealth[-1].numerator)/Decimal(wealth[-1].denominator)
        exponent=Decimal(252)/Decimal(intervals)
        annualized=context.power(terminal,exponent)-Decimal(1)
    return {'observation_count':len(calendar),'interval_count':len(calendar)-1,
        'cumulative_return':ratio(wealth[-1]-1),'maximum_drawdown':ratio(worst),
        'wealth':[{'session':session,'normalized_wealth':ratio(value)} for session,value in zip(calendar,wealth)],
        'initial_one_in_drawdown':True,'annualized_return_calculated':True,
        'annualized_return_diagnostic_decimal':str(annualized),
        'annualization':{'formula':'terminal_normalized_wealth ** (252 / interval_count) - 1',
            'sessions_per_year':252,'interval_count':intervals,'decimal_precision':80,'rounding':'ROUND_HALF_EVEN',
            'arithmetic':'DECIMAL80_POWER_FROM_EXACT_TERMINAL_FRACTION_NOT_EXACT_RATIONAL_ANNUALIZATION',
            'annualization_is_historical_diagnostic':True,'short_window_below_252_intervals':intervals<252,
            'short_window_limitation':'SHORT_WINDOW_COMPOUNDING_CAN_MAGNIFY_SMALL_MOVES_NOT_LONG_TERM_EVIDENCE',
            'formal_admission_allowed':False}}


def compare_reference_window(*,initial_session,observed_sessions,candidate_cumulative_twr,control_cumulative_twr,
        incumbent_rows,nav_rows,candidate_flow_events,control_flow_events,
        candidate_currency,control_currency,incumbent_currency,nav_currency):
    require(type(observed_sessions) is list and 1<=len(observed_sessions)<=512,'Explicit positive-length bounded window required')
    calendar=[day(initial_session)]+[day(value) for value in observed_sessions]
    require(calendar==sorted(set(calendar)),'Strict complete ordered observation calendar required')
    require(candidate_currency==control_currency=='USD' and incumbent_currency=='USD' and nav_currency=='CNY','Explicit role currency labels required')
    for flows in (candidate_flow_events,control_flow_events):
        require(type(flows) is list and len(flows)<=len(observed_sessions),'Bounded explicit flow list required')
        dates=[]
        for event in flows:
            require(type(event) is dict and set(event)=={'session','amount_usd','timing'},'Exact flow event fields required')
            require(day(event['session']) in observed_sessions and event['timing']==TIMING
                    and number(event['amount_usd'])>=0,'Flow date/timing/amount mismatch')
            dates.append(event['session'])
        require(dates==sorted(set(dates)),'Unique ordered flow dates required')
    require(candidate_flow_events==control_flow_events,'Same-flow control must have identical explicit flows')
    values={}
    for role,rows in [('candidate',candidate_cumulative_twr),('same_flow_zero_trade_control',control_cumulative_twr)]:
        require(type(rows) is list and [row['session'] for row in rows]==observed_sessions,'Exact TWR daily calendar required')
        values[role]=[Fraction(1)]+[1+from_ratio(row['cumulative_twr']) for row in rows]
    lags=[]
    for role,rows in [('saved_incumbent_different_flow_reference',incumbent_rows),('fund_012922_cny_nav_reference',nav_rows)]:
        require(type(rows) is list and [row['session'] for row in rows]==calendar,'Exact reference calendar required; no intersection/drop/fill')
        raw=[number(row['value']) for row in rows]
        require(all(value>0 for value in raw),'Positive reference values required')
        values[role]=[value/raw[0] for value in raw]
        if role=='fund_012922_cny_nav_reference':
            previous=None
            dated_values={}
            for row,value in zip(rows,raw):
                nav_date=day(row['nav_date']); session=day(row['session'])
                require(nav_date<=session and (previous is None or nav_date>=previous),'Future or backwards NAV date prohibited')
                require(nav_date not in dated_values or dated_values[nav_date]==value,'One NAV date cannot have conflicting values')
                dated_values[nav_date]=value
                lags.append({'session':session,'nav_date':nav_date,'calendar_day_lag':(date.fromisoformat(session)-date.fromisoformat(nav_date)).days,
                    'publication_time':None,'publication_time_verified':False,'tradable_at_us_open_verified':False})
                previous=nav_date
    roles={role:metrics(calendar,wealth) for role,wealth in values.items()}
    for role in roles:
        roles[role].update(currency_label=nav_currency if role=='fund_012922_cny_nav_reference' else 'USD',
            uses_saved_chained_twr=role in ('candidate','same_flow_zero_trade_control'),
            flow_equivalent_to_candidate=role=='same_flow_zero_trade_control',formal_admission_allowed=False)
    comparisons={}
    for role in values:
        if role=='candidate': continue
        comparisons[role]={'candidate_minus_reference_return':ratio(from_ratio(roles['candidate']['cumulative_return'])-from_ratio(roles[role]['cumulative_return'])),
            'candidate_minus_reference_drawdown':ratio(from_ratio(roles['candidate']['maximum_drawdown'])-from_ratio(roles[role]['maximum_drawdown'])),
            'scope':'SAME_FLOW_LOCAL_ZERO_TRADE_CONTROL' if role=='same_flow_zero_trade_control' else 'RETROSPECTIVE_REFERENCE_DIFFERENT_FLOW_OR_CURRENCY',
            'formal_benchmark_gate':False}
    return {'schema':SCHEMA,'calendar':calendar,'roles':roles,'comparisons':comparisons,
        'candidate_flow_events':[dict(event) for event in candidate_flow_events],
        'control_flow_events':[dict(event) for event in control_flow_events],'nav_observation_lags':lags,
        'nav_max_calendar_day_lag':max(item['calendar_day_lag'] for item in lags),
        'missing_observation_count':0,'missing_policy':'REJECT_NO_INTERSECTION_DROP_OR_FUTURE_FILL',
        'annualized_return_calculated':True,'incumbent_same_injection_response_modelled':False,
        'nav_dataset_currency_binding_certified':False,'currency_fx_equivalence_verified':False,
        'nav_publication_time_verified':False,'subscription_execution_equivalence_verified':False,
        'formal_dual_benchmark_admission':False,'point_in_time_verified':False,'promotion_allowed':False,
        'orders_executed':False,'economic_winner_selected':False,'cross_window_ranking_performed':False,
        'parameter_authority':'CALLER_SUPPLIED_EXPLICIT_REFERENCE_WINDOW_NOT_SOURCE_CERTIFICATION'}
