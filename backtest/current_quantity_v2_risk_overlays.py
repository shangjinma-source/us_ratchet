"""Fixed research overlays. No IO, selector, execution or performance claims.

Caller must supply reviewed histories normalized to one decision share unit.
References are required provenance, not authenticated by this pure module.
Raw split-adjusted/nominal mixtures are not accepted as normalized input.
"""
from copy import deepcopy
from datetime import date, datetime
from fractions import Fraction
from math import isqrt
from zoneinfo import ZoneInfo

UNIT_SCHEMA='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1'


def _stamp(value):
    t=datetime.fromisoformat(value)
    if t.tzinfo is None or t.utcoffset() is None:raise ValueError('AWARE_TIME_REQUIRED')
    return t


def _validated(*,base_target,signal_date,observed_at,session_dates,session_close_times,histories,count):
    if date.fromisoformat(signal_date).isoformat()!=signal_date:raise ValueError('INVALID_SIGNAL_DATE')
    cutoff=_stamp(observed_at)
    if cutoff.astimezone(ZoneInfo('America/New_York')).date().isoformat()!=signal_date:
        raise ValueError('OBSERVATION_MUST_BE_DECISION_SESSION_DATE')
    if session_dates!=sorted(set(session_dates)) or signal_date not in session_dates:
        raise ValueError('EXPLICIT_SESSION_CALENDAR_REQUIRED')
    for day in session_dates:date.fromisoformat(day)
    monthly=base_target.get('monthly_decision_date')
    if not isinstance(monthly,str) or date.fromisoformat(monthly).isoformat()!=monthly or monthly not in session_dates or monthly>signal_date:
        raise ValueError('INVALID_OR_FUTURE_MONTHLY_TARGET_DATE')
    close_times=session_close_times['closes']
    if not session_close_times.get('review_reference'):raise ValueError('REVIEWED_SESSION_CLOSES_REQUIRED')
    signal_close=_stamp(close_times[signal_date])
    if signal_close.astimezone(ZoneInfo('America/New_York')).date().isoformat()!=signal_date or signal_close>cutoff:
        raise ValueError('SIGNAL_SESSION_NOT_COMPLETED')
    quantities=base_target['quantities'];units=base_target['price_units']
    if not base_target.get('origin_reference') or not isinstance(quantities,dict):raise ValueError('FROZEN_TARGET_REFERENCE_REQUIRED')
    if any(type(q) is not int or q<0 for q in quantities.values()):raise ValueError('WHOLE_NONNEGATIVE_TARGET_REQUIRED')
    positive={sid:q for sid,q in quantities.items() if q}
    if set(positive)!=set(histories) or set(positive)!=set(units):raise ValueError('EXACT_POSITIVE_TARGET_DOMAIN_REQUIRED')
    if not positive:return positive,{}
    index=session_dates.index(signal_date)
    if index+1<count:raise ValueError('INSUFFICIENT_COMPLETED_HISTORY')
    expected=session_dates[index-count+1:index+1]
    series={}
    for sid in positive:
        source=histories[sid];unit=source['units']
        if (unit.get('schema')!=UNIT_SCHEMA or unit.get('unit_asof')!=signal_date
            or unit.get('currency')!='USD' or not unit.get('basis_id')
            or not unit.get('review_reference') or not source.get('source_reference')):
            raise ValueError('REVIEWED_CONSTANT_SHARE_UNITS_REQUIRED')
        if units[sid]!=unit['basis_id']:raise ValueError('TARGET_HISTORY_UNIT_MISMATCH')
        rows=source['closes']
        if [row['date'] for row in rows]!=expected:raise ValueError('EXACT_COMPLETED_WINDOW_REQUIRED')
        values=[];previous=None
        for row in rows:
            completed=_stamp(row['completed_at'])
            scheduled_close=_stamp(close_times[row['date']])
            if scheduled_close.astimezone(ZoneInfo('America/New_York')).date().isoformat()!=row['date']:
                raise ValueError('MISDATED_SESSION_CLOSE')
            if completed<scheduled_close or completed>cutoff or completed.astimezone(ZoneInfo('America/New_York')).date().isoformat()!=row['date']:
                raise ValueError('FUTURE_OR_MISDATED_COMPLETED_CLOSE')
            if previous is not None and completed<=previous:raise ValueError('NONMONOTONIC_COMPLETION')
            previous=completed
            if isinstance(row['close'],bool):raise ValueError('BOOLEAN_PRICE')
            value=Fraction(str(row['close']))
            if value<=0:raise ValueError('POSITIVE_CLOSE_REQUIRED')
            values.append(value)
        series[sid]=values
    return positive,series


def _result(policy,base_target,target,signal_date,observed_at,diagnostics):
    return dict(policy=policy,parameter_authority='FIXED_RESEARCH_HYPOTHESIS_NOT_USER_NUMERICAL_PREFERENCE',
        base_target=deepcopy(base_target),target_quantities=target,
        signal_date=signal_date,observed_at=observed_at,diagnostics=diagnostics,
        execution='NEXT_SESSION_OPEN_ONLY_BY_SEPARATE_RUNNER',
        sources_authenticated=False,performance_validated=False,production_adopted=False)


def volatility20_target20(*,base_target,signal_date,observed_at,session_dates,session_close_times,histories):
    """Monthly-only: 20 simple returns, sample variance,252 annualization,.20 vol.

    Integer quantities use exact rational squared exposure and integer square
    root, avoiding floating point drift at a whole-share floor boundary.
    """
    if base_target.get('monthly_decision_date')!=signal_date:raise ValueError('R1_MONTHLY_DECISION_ONLY')
    q,prices=_validated(base_target=base_target,signal_date=signal_date,observed_at=observed_at,
        session_dates=session_dates,session_close_times=session_close_times,histories=histories,count=21)
    if not q:return _result('VOL20_TARGET20',base_target,{},signal_date,observed_at,dict(reason='EMPTY_TARGET'))
    total=sum((q[s]*prices[s][-1] for s in q),Fraction(0))
    weights={s:q[s]*prices[s][-1]/total for s in q}
    returns=[sum((weights[s]*(prices[s][i]/prices[s][i-1]-1) for s in q),Fraction(0)) for i in range(1,21)]
    mean=sum(returns,Fraction(0))/20
    variance=sum(((r-mean)**2 for r in returns),Fraction(0))/19
    annual_variance=variance*252
    ratio=Fraction(1) if annual_variance==0 else min(Fraction(1),Fraction(1,25)/annual_variance)
    target={s:isqrt((q[s]*q[s]*ratio.numerator)//ratio.denominator) for s in q}
    return _result('VOL20_TARGET20',base_target,target,signal_date,observed_at,
        dict(lookback_returns=20,sample_variance=str(variance),annual_variance=str(annual_variance),
             annualization_sessions=252,target_annual_volatility='1/5',exposure_multiplier_squared=str(ratio),
             risky_weights={s:str(w) for s,w in weights.items()},mean_daily_return=str(mean),
             freeze='SCALED_TARGETS_FIXED_UNTIL_NEXT_MONTHLY_SELECTION_OR_EXPLICIT_UNIT_MIGRATION'))


def sma20_target(*,base_target,signal_date,observed_at,session_dates,session_close_times,histories):
    """Daily: exact close>SMA20 ON; equality OFF. Never mutate monthly ceiling."""
    q,prices=_validated(base_target=base_target,signal_date=signal_date,observed_at=observed_at,
        session_dates=session_dates,session_close_times=session_close_times,histories=histories,count=20)
    target={};diagnostics={}
    for sid,ceiling in q.items():
        average=sum(prices[sid],Fraction(0))/20
        on=prices[sid][-1]>average
        target[sid]=ceiling if on else 0
        diagnostics[sid]=dict(close=str(prices[sid][-1]),sma20=str(average),on=on,monthly_ceiling=ceiling)
    return _result('SMA20_RECHECK',base_target,target,signal_date,observed_at,diagnostics)
