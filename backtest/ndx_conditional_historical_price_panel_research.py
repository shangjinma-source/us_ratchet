"""Conditional 253-price/252 split-only-return assembly. No I/O or optimizer."""
import copy
import math
from datetime import date
from decimal import Decimal, localcontext
import pandas as pd

FALSE=('source_bytes_authenticated','security_identity_verified','historical_identity_interval_verified',
    'complete_corporate_actions_verified','exchange_calendar_completeness_verified','cash_dividends_included',
    'point_in_time_verified','legal_training_input_admitted','execution_authorized','fit_performed',
    'oos_evaluation_performed','promotion_allowed')


def day(value):
    if type(value) is not str or date.fromisoformat(value).isoformat()!=value:raise ValueError('Canonical session date required')
    return value


def positive(value):
    if type(value) not in (str,int,float) or type(value) is bool:raise ValueError('Explicit finite positive numeric input required')
    try:value=Decimal(str(value))
    except Exception as exc:raise ValueError('Invalid numeric input') from exc
    if not value.is_finite() or value<=0:raise ValueError('Finite positive numeric input required')
    return value


def finite_float(value):
    result=float(value)
    if not math.isfinite(result):raise ValueError('Float64 overflow refused')
    return result


def names(values,count):
    if type(values) is not list or len(values)!=count or len(set(values))!=count or any(type(v) is not str or not v or v!=v.strip() or v!=v.upper() for v in values):raise ValueError('Explicit unique role ticker list required')
    return set(values)


def assemble_historical_prices(*,calendar,channels,candidate_tickers,incumbent_tickers,minimum_identity_dates,exclude_on_or_after):
    """Nominal Close × effective-day share ratio / prior nominal Close − 1.

    Caller supplies authenticated nominal-price and ordinary-share split evidence.
    This function verifies the arithmetic/declared denominators only. A split in
    the evaluation interval is rejected: this minimal interface does not grant
    the frozen whole-lot executor corporate-action accounting capabilities.
    """
    if type(calendar) is not list or len(calendar)!=253 or [day(v) for v in calendar]!=sorted(set(calendar)):
        raise ValueError('Complete explicit 253 ascending reference sessions required')
    excluded=day(exclude_on_or_after)
    if calendar[-1]>=excluded:raise ValueError('Unfinalized receipt-day price excluded')
    candidate=names(candidate_tickers,14);incumbent=names(incumbent_tickers,8);tickers=sorted(candidate|incumbent)
    if len(tickers)!=20 or len(candidate&incumbent)!=2 or set(channels)!=set(tickers) or set(minimum_identity_dates)!=set(tickers):raise ValueError('Exact 14 plus original 8 union of 20 required')
    if minimum_identity_dates.get('LRCX')!='2024-10-03':raise ValueError('Explicit post-transition LRCX coordinate floor required')
    opens={};closes={};returns={};ratios={};events={};used={};role_rows=[]
    with localcontext() as context:
        context.prec=50
        for ticker in tickers:
            floor=minimum_identity_dates[ticker]
            if floor is not None and calendar[0]<day(floor):raise ValueError('Reference calendar predates declared identity floor')
            channel=channels[ticker]
            if set(channel)!={'nominal_rows','split_events'} or type(channel['nominal_rows']) is not list or type(channel['split_events']) is not list:raise ValueError('Explicit nominal rows and complete submitted split events required')
            price={};order=[]
            for row in channel['nominal_rows']:
                if set(row)!={'session','open','close'}:raise ValueError('Exact nominal Open/Close row required')
                session=day(row['session'])
                if session in price or session>=excluded:raise ValueError('Duplicate or unfinished price session')
                price[session]=(positive(row['open']),positive(row['close']));order.append(session)
            if order!=sorted(order) or any(d not in price for d in calendar):raise ValueError('Missing reference session cannot be compressed or filled')
            start=order.index(calendar[0])
            if order[start:start+253]!=calendar:raise ValueError('Declared return predecessors must be adjacent submitted price sessions')
            split={};submitted=[]
            for event in channel['split_events']:
                if not {'session','new_shares','old_shares','event_kind'}<=set(event):raise ValueError('Explicit effective-day split ratio and action class required')
                session=day(event['session'])
                if event['event_kind']=='IDENTITY_TRANSITION_SHARE_SPLIT':
                    if floor is None or session!=floor or calendar[0]<floor:raise ValueError('Identity-transition split requires bounded post-action coordinate')
                elif event['event_kind']!='ORDINARY_SHARE_SPLIT':raise ValueError('Complex or unknown action cannot be modeled as simple split')
                if session in split or session>=excluded:raise ValueError('Duplicate or future split event')
                numerator=positive(event['new_shares']);denominator=positive(event['old_shares']);ratio=numerator/denominator
                split[session]=ratio;submitted.append(session)
                if calendar[0]<session<=calendar[-1] and session not in calendar:raise ValueError('In-window split missing from declared reference calendar')
            if submitted!=sorted(submitted):raise ValueError('Ascending full submitted split-event denominator required')
            if any(d in split for d in calendar[127:]):raise ValueError('Known split in evaluation interval requires separate action-aware execution')
            op=[price[d][0] for d in calendar];cl=[price[d][1] for d in calendar]
            daily=[];factor=[];used_rows=[]
            for previous,current,prior_close,current_close in zip(calendar[:-1],calendar[1:],cl[:-1],cl[1:]):
                ratio=split.get(current,Decimal(1));value=current_close*ratio/prior_close-1
                converted=finite_float(value)
                if converted<=-1:raise ValueError('Return cannot underflow to total loss for positive surviving prices')
                daily.append(converted);factor.append(str(ratio))
                if current in split:used_rows.append(dict(previous_session=previous,session=current,share_ratio=str(ratio),split_neutral_price_return=str(value)))
            opens[ticker]=[finite_float(v) for v in op];closes[ticker]=[finite_float(v) for v in cl];returns[ticker]=daily;ratios[ticker]=factor
            if any(v<=0 for v in opens[ticker]+closes[ticker]):raise ValueError('Positive nominal prices cannot underflow in float64')
            events[ticker]=copy.deepcopy(channel['split_events']);used[ticker]=used_rows
            role_rows.append(dict(ticker=ticker,candidate=ticker in candidate,original_incumbent=ticker in incumbent,minimum_identity_date=floor,
                role_is_not_security_identity_authentication=True,security_id=None))
    index=pd.DatetimeIndex(calendar)
    return dict(schema='CONDITIONAL_HISTORICAL_253_PRICE_252_RETURN_PANEL_V1',
        nominal_open=pd.DataFrame(opens,index=index,dtype='float64'),nominal_close=pd.DataFrame(closes,index=index,dtype='float64'),
        returns=pd.DataFrame(returns,index=index[1:],dtype='float64'),effective_day_share_ratios=ratios,
        submitted_full_split_events=events,applied_fit_split_events=used,roles=role_rows,
        price_basis='CONDITIONAL_NOMINAL_OPEN_CLOSE',return_basis='SPLIT_ONLY_PRICE_RETURN_EXCLUDES_CASH_DIVIDENDS',
        calendar=list(calendar),exclude_on_or_after=excluded,fit_return_dates=list(calendar[1:127]),evaluation_return_dates=list(calendar[127:]),
        price_row_count=253,return_row_count=252,fit_days=126,evaluation_days=126,rolling_step_days=21,available_original_rolling_windows=1,
        known_evaluation_split_events=[],submitted_event_denominator_preserved=True,
        historical_risk_labels_are_separate_research_assumptions=True,**dict.fromkeys(FALSE,False))
