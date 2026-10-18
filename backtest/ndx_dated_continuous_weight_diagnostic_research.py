"""Fixed fractional holdings diagnostic, not a cash-conserving account."""
from copy import deepcopy
from datetime import date
from decimal import Context, Decimal, localcontext
from fractions import Fraction
import math

FLAGS=dict.fromkeys(('formal_cohort_verified','point_in_time_verified','promotion_allowed','future_independent_oos','untouched_holdout','accounting_conservation_verified','dividends_included','corporate_actions_complete','weights_refitted','weights_normalized','daily_rebalancing_performed'),False)

def require(ok,message):
    if not ok:raise ValueError(message)
def number(v):
    if type(v) is dict:
        require(set(v)=={'numerator','denominator'},'Exact rational fields')
        for x in v.values():require(type(x) is str and x.lstrip('-').isdigit() and len(x)<180,'Bounded rational integer strings')
        require(int(v['denominator'])>0,'Positive denominator');return Fraction(int(v['numerator']),int(v['denominator']))
    require(type(v) in (str,int,float) and (type(v) is not float or math.isfinite(v)),'Finite original scalar, never bool')
    text=str(v);require(len(text)<180,'Bounded scalar');d=Decimal(text);require(d.is_finite() and abs(d.as_tuple().exponent)<=160,'Finite bounded decimal');return Fraction(d)
def exact(v):return dict(numerator=str(v.numerator),denominator=str(v.denominator))
def display(v):
    with localcontext(Context(prec=80)):return str(Decimal(v.numerator)/Decimal(v.denominator))

def diagnose_continuous_weights(*,calendar,positions,nominal_quotes,split_events,transaction_cost_bps,source_references):
    """Quotes: SID -> 127 {session,nominal_open_exact,nominal_close_exact} rows.

    Positions preserve saved target_weight literals. Split rows carry security_id,
    effective_session, numerator/denominator integer strings, source_reference.
    No implicit weight normalization or residual-cash leg is introduced.
    """
    require(type(calendar) is list and len(calendar)==127 and calendar==sorted(set(calendar)),'Exact127 ordered unique dates')
    for d in calendar:require(type(d) is str and date.fromisoformat(d).isoformat()==d,'Canonical date')
    require(calendar[0]=='2026-03-20' and calendar[1]=='2026-03-23' and calendar[-1]=='2026-09-21','Fixed initial/entry/end dates')
    require(type(positions) is list and 0<len(positions)<=256,'Bounded complete positions')
    sids=[p['security_id'] for p in positions];require(all(type(s) is str and s for s in sids) and len(set(sids))==len(sids),'Unique SID positions')
    require(type(nominal_quotes) is dict and set(nominal_quotes)==set(sids),'Exact quote universe including zero weights')
    weights={p['security_id']:number(p['target_weight']) for p in positions};require(all(w>=0 for w in weights.values()) and sum(weights.values())>0,'Nonnegative saved weights')
    require(number(transaction_cost_bps)==10,'Original same10bps cost contract');cost=Fraction(1,1000)
    require(type(source_references) is dict and source_references,'Explicit source evidence claims')
    quotes={}
    for sid in sids:
        rows=nominal_quotes[sid];require(type(rows) is list and len(rows)==127 and [r['session'] for r in rows]==calendar,'Full unchanged calendar per SID')
        quotes[sid]=[(number(r['nominal_open_exact']),number(r['nominal_close_exact'])) for r in rows]
        require(all(o>0 and c>0 for o,c in quotes[sid]),'Positive nominal prices; adjusted fields not accepted')
    require(type(split_events) is list and len(split_events)<=10000,'Bounded explicit split list')
    events={};seen=set()
    for e in split_events:
        sid=e['security_id'];d=e['effective_session'];require(sid in weights and d in calendar,'Event within bound SID/calendar')
        require((sid,d) not in seen,'No duplicate event per security/session');seen.add((sid,d))
        for k in ('numerator','denominator'):require(type(e[k]) is str and e[k].isdigit() and 0<int(e[k])<10**12,'Positive integer split ratio')
        r=e['source_reference'];require(type(r) is dict and type(r.get('path')) is str and r['path'] and type(r.get('sha256')) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Event source reference')
        events[(sid,d)]=Fraction(int(e['numerator']),int(e['denominator']))
    quantities={sid:Fraction(0) for sid in sids};path=[];values=[Fraction(1)]
    path.append(dict(session=calendar[0],normalized_value=exact(Fraction(1)),normalized_value_display='1',role='INITIAL_REFERENCE_ONE_NOT_INVESTED_ACCOUNT',security_rows=[dict(security_id=sid,fractional_quantity=exact(Fraction(0)),contribution_before_cost=exact(Fraction(0)),contribution_after_cost=exact(Fraction(0))) for sid in sids]))
    for i,d in enumerate(calendar[1:],1):
        per=[]
        for sid in sids:
            ratio=events.get((sid,d),Fraction(1));quantities[sid]*=ratio
            if i==1:quantities[sid]=weights[sid]/quotes[sid][i][0]
            gross=quantities[sid]*quotes[sid][i][1];per.append(dict(security_id=sid,fractional_quantity=exact(quantities[sid]),nominal_close_exact=exact(quotes[sid][i][1]),split_ratio_before_purchase_or_mark=exact(ratio),entry_purchase=i==1,contribution_before_cost=exact(gross),contribution_after_cost=exact(gross*(1-cost))))
        value=sum((number(r['contribution_after_cost']) for r in per),Fraction(0));values.append(value)
        path.append(dict(session=d,normalized_value=exact(value),normalized_value_display=display(value),role='FIXED_FRACTIONAL_HOLDINGS_CLOSE_MARK',security_rows=per))
    peak=values[0];peak_i=0;worst=Fraction(0);pair=(0,0)
    for i,value in enumerate(values):
        if value>peak:peak=value;peak_i=i
        dd=(peak-value)/peak
        if dd>worst:worst=dd;pair=(peak_i,i)
    ret=values[-1]-1;annual=values[-1]**2-1
    return dict(schema='DATED_FIXED_FRACTIONAL_WEIGHT_DIAGNOSTIC_V1',calendar=deepcopy(calendar),positions_preserved=deepcopy(positions),split_events_preserved=deepcopy(split_events),source_references_preserved=deepcopy(source_references),transaction_cost_bps_preserved=transaction_cost_bps,weight_sum_exact=exact(sum(weights.values())),scalar_encoding='FLOAT_TO_STR_THEN_EXACT_DECIMAL_FRACTION;EXACT_RATIONAL_QUOTES',role='frozen_target_weight_daily_return_comparability',cost_policy='ONCE_MULTIPLICATIVE_ONE_MINUS_COST_ON_ALL_POST_ENTRY_VALUES_NOT_DAILY_FEE',path=path,interval_count=126,cumulative_return_exact=exact(ret),annualized_return_exact=exact(annual),annualization_exponent_exact=exact(Fraction(252,126)),max_drawdown_exact=exact(worst),drawdown_peak_index=pair[0],drawdown_trough_index=pair[1],drawdown_peak_session=calendar[pair[0]],drawdown_trough_session=calendar[pair[1]],evaluation_interval_previously_used_for_fitting=True,**FLAGS)
