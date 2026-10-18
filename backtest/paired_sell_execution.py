"""Two predeclared SELL execution models; pure mechanism, not a strategy result."""
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from backtest.current_quantity_v2_minute_day_fill import MODEL,evaluate,exact,stamp

BASELINE='CEIL_FRESH_LAST_BASELINE_V1'
PREMIUM='HALF_RECENT_MEDIAN_MINUTE_TR_PREMIUM_V1'


def require(condition,reason):
    if not condition:raise ValueError(reason)


def ceil_cent(value):
    scaled=value*100
    return Fraction(-(-scaled.numerator//scaled.denominator),100)


def construct(*,signal):
    """Caller supplies original causal evidence; presence is not authentication."""
    s=deepcopy(signal)
    require(s['trigger'] in ('MONTHLY_TARGET_REDUCTION','SAME_MONTH_RESIDUAL_SELL'),'UNSUPPORTED_EXIT_TRIGGER')
    for key in ('decision_id','security_id','ticker','source_reference','expected_revision'):
        require(type(s[key])is str and bool(s[key].strip()),'EXPLICIT_IDENTITY_REQUIRED')
    held,target,quantity=(s[k] for k in ('held_shares','target_shares','sell_quantity'))
    require(all(type(v)is int for v in (held,target,quantity)) and held>target>=0 and quantity==held-target,'EXISTING_TARGET_REDUCTION_REQUIRED')
    at,accepted,opened,closed,last_at=map(stamp,(s['signal_at'],s['accepted_at'],s['session_open'],s['session_close'],s['last_trade_at']))
    local=at.astimezone(ZoneInfo('America/New_York'))
    require(at.second==at.microsecond==0,'WHOLE_MINUTE_SIGNAL_REQUIRED')
    cutoff=at
    require(s['session']==local.date().isoformat()==opened.astimezone(ZoneInfo('America/New_York')).date().isoformat()==closed.astimezone(ZoneInfo('America/New_York')).date().isoformat() and opened<=at<=accepted<closed,'SESSION_ACCEPTANCE_BOUNDARY')
    require(opened<=last_at<=at and accepted-last_at<=timedelta(seconds=120),'FRESH_CAUSAL_LAST_REQUIRED')
    require(s['last_price_kind']=='OBSERVED_TRADE','OBSERVED_TRADE_REQUIRED')
    last=exact(s['last_price']);require(last>0,'POSITIVE_LAST_REQUIRED')
    bars=s['recent_minutes'];require(type(bars)is list and len(bars)==6,'SIX_COMPLETED_MINUTES_REQUIRED')
    previous=None;ranges=[]
    for i,bar in enumerate(bars):
        require(bar['security_id']==s['security_id'] and bar['ticker']==s['ticker'],'MINUTE_IDENTITY_MISMATCH')
        start,end=stamp(bar['start']),stamp(bar['end'])
        require(start==cutoff-timedelta(minutes=6-i) and end==start+timedelta(minutes=1) and start>=opened,'CONTIGUOUS_CAUSAL_MINUTES_REQUIRED')
        o,h,l,c=(exact(bar[k]) for k in ('open','high','low','close'))
        require(0<l<=min(o,c)<=max(o,c)<=h,'INVALID_OHLC')
        if previous is not None:ranges.append(max(h-l,abs(h-previous),abs(l-previous)))
        previous=c
    require(accepted-cutoff<=timedelta(seconds=120),'MINUTE_REFERENCE_EXPIRED')
    premium=sorted(ranges)[2]/2
    common=dict(side='SELL',quantity=quantity,filled_quantity=0,closed=None,
                accepted_at=s['accepted_at'],session_close=s['session_close'])
    return dict(status='READY_CONDITIONAL',signal=s,median_true_range=str(premium*2),
        orders={name:dict(common,order_id=sha256(json.dumps([s['decision_id'],s['security_id'],s['session'],s['signal_at'],s['accepted_at'],s['expected_revision'],name],separators=(',',':')).encode()).hexdigest(),limit_price=str(ceil_cent(price)))
                for name,price in ((BASELINE,last),(PREMIUM,last+premium))},
        source_authenticated=False,production_policy_changed=False)


def paired_evaluate(*,signal,minutes,observed_through,evaluated_at,fees,available_cash,available_shares):
    """No BUY leg, resource reuse, automatic fill or economic winner assertion."""
    boundary=dict(research_only=True,real_fill=False,account_mutated=False,
                  downstream_buy_outcome='NOT_EVALUATED',economic_winner=None,
                  cash_scope='AVAILABLE_CASH_EXCLUDING_OTHER_RESERVATIONS_NOT_TOTAL_ACCOUNT_NAV')
    try:
        prepared=construct(signal=signal)
        cash=exact(available_cash);fee=exact(fees)
        require(cash>=0 and fee>=0,'EXPLICIT_NONNEGATIVE_RESOURCES_REQUIRED')
        require(type(available_shares)is int and signal['sell_quantity']<=available_shares<=signal['held_shares'],'EXPLICIT_AVAILABLE_SHARES_REQUIRED')
        require(type(minutes)is list and len(minutes)<=1440,'BOUNDED_MINUTE_LIST_REQUIRED')
        require(all(bar['security_id']==signal['security_id'] and bar['ticker']==signal['ticker'] for bar in minutes),'MINUTE_IDENTITY_MISMATCH')
        branches={}
        for name,order in prepared['orders'].items():
            result=evaluate(model=MODEL,order=deepcopy(order),minutes=deepcopy(minutes),
                observed_through=observed_through,evaluated_at=evaluated_at,fees=str(fee),
                available_cash=str(cash),available_shares=available_shares,
                event_id=order['order_id']+':fill',expected_revision=signal['expected_revision'])
            resources=None
            if result['status']=='SIMULATED_FILL':
                resources=dict(cash=str(cash+exact(result['cash_change'])),shares=signal['held_shares']-signal['sell_quantity'],
                               available_at=result['evidence_available_at'])
            elif result['status']=='EXPIRE':
                resources=dict(cash=str(cash),shares=signal['held_shares'],available_at=signal['session_close'])
            branches[name]=dict(order=order,fill=result,initial_resources=dict(cash=str(cash),shares=signal['held_shares'],available_shares=available_shares),
                                resulting_resources=resources)
        return dict(boundary,status='UNKNOWN' if any(b['fill']['status']=='UNKNOWN' for b in branches.values()) else 'PAIRED_CONDITIONAL_OUTCOMES',
                    branches=branches,construction=prepared)
    except (ValueError,KeyError,TypeError,IndexError,ArithmeticError) as error:
        return dict(boundary,status='UNKNOWN',branches={},reason=str(error) if isinstance(error,ValueError) else type(error).__name__)


def terminal_values(*,paired,close_bar,evaluated_at):
    """Compare both branches including unsold inventory; never report account NAV.

    The explicit final minute close is a mark proxy, not an official close or
    executable sale. Caller remains responsible for authenticating its source.
    """
    boundary=dict(research_only=True,account_mutated=False,economic_winner=None,
                  downstream_buy_outcome='NOT_EVALUATED',source_authenticated=False,
                  value_scope='AVAILABLE_CASH_PLUS_THIS_SECURITY_NOT_ACCOUNT_NAV',
                  mark_kind='FINAL_MINUTE_CLOSE_PROXY_NOT_EXECUTABLE_CASH')
    try:
        require(paired['status']=='PAIRED_CONDITIONAL_OUTCOMES','COMPLETE_PAIR_REQUIRED')
        signal=paired['construction']['signal']
        closed=stamp(signal['session_close'])
        require(stamp(evaluated_at)>=closed,'SESSION_NOT_CLOSED')
        require(close_bar['security_id']==signal['security_id'] and close_bar['ticker']==signal['ticker'],'CLOSE_IDENTITY_MISMATCH')
        require(type(close_bar['source_reference']) is str and bool(close_bar['source_reference'].strip()),'CLOSE_SOURCE_REQUIRED')
        require(stamp(close_bar['start'])==closed-timedelta(minutes=1) and stamp(close_bar['end'])==closed,'FINAL_MINUTE_MARK_REQUIRED')
        require(closed<=stamp(close_bar['observed_at'])<=stamp(evaluated_at),'CLOSE_MARK_NOT_YET_OBSERVED')
        opened,high,low,mark=(exact(close_bar[key]) for key in ('open','high','low','close'))
        require(0<low<=min(opened,mark)<=max(opened,mark)<=high,'INVALID_CLOSE_OHLC')
        values={}
        for name in (BASELINE,PREMIUM):
            branch=paired['branches'][name]
            require(branch['fill']['status'] in ('SIMULATED_FILL','EXPIRE'),'COMPLETE_BRANCH_REQUIRED')
            resources=branch['resulting_resources']
            cash=exact(resources['cash']);shares=resources['shares']
            require(cash>=0 and type(shares)is int and shares>=0,'INVALID_TERMINAL_RESOURCES')
            require(stamp(resources['available_at'])<=closed,'TERMINAL_RESOURCES_NOT_AVAILABLE')
            inventory=shares*mark
            values[name]=dict(cash=str(cash),shares=shares,inventory_mark=str(inventory),
                              cash_plus_inventory=str(cash+inventory),fill_status=branch['fill']['status'])
        difference=exact(values[PREMIUM]['cash_plus_inventory'])-exact(values[BASELINE]['cash_plus_inventory'])
        return dict(boundary,status='PAIRED_TERMINAL_VALUES',branches=values,
                    premium_minus_baseline=str(difference),close_bar=deepcopy(close_bar))
    except (ValueError,KeyError,TypeError,IndexError,ArithmeticError) as error:
        return dict(boundary,status='UNKNOWN',branches={},reason=str(error) if isinstance(error,ValueError) else type(error).__name__)
