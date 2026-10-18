"""Independent saved-quantity/Close/as-of risk arithmetic, no producer imports."""
from datetime import date
from decimal import Decimal
from fractions import Fraction
import json
import math


def require(value,message):
    if not value:raise ValueError(message)


def exact(a,b):
    encode=lambda value:json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
    require(encode(a)==encode(b),'Exact independent daily risk/locator evidence')


def number(value):
    require(type(value)in(int,float),'Original number without bool or string')
    if type(value)is int:return Fraction(value)
    require(math.isfinite(value),'Finite saved price/quantity')
    return Fraction(Decimal(repr(value)))


def day(value):
    require(type(value)is str and date.fromisoformat(value).isoformat()==value,'Canonical original session')
    return value


def ratio(value):return dict(numerator=str(value.numerator),denominator=str(value.denominator))


def expected_projection(stateful_input,daily):
    calendar=stateful_input['calendar'];close=stateful_input['closes'];aliases=stateful_input['internal_columns_by_security'];observations=stateful_input['risk_chains_by_decision']
    require(type(calendar)is list and len(calendar)==120 and calendar==sorted(set(calendar)),'Complete 120 original days')
    for value in calendar:day(value)
    require(type(daily)is list and [x['session']for x in daily]==calendar,'Complete original saved daily order')
    exact(close['index'],calendar)
    columns=close['columns'];matrix=close['data']
    require(type(columns)is list and len(set(columns))==len(columns),'Unique source Close columns')
    require(type(matrix)is list and len(matrix)==120 and all(type(row)is list and len(row)==len(columns)for row in matrix),'Original complete Close shape')
    require(type(aliases)is dict and len(set(aliases.values()))==len(aliases)and set(aliases.values())==set(columns),'Exact SID/Close alias coverage')
    require(type(observations)is dict,'Original dated risk labels')
    for session,entries in observations.items():
        day(session);require(type(entries)is dict,'Original observation mapping')
        for sid,label in entries.items():require(type(sid)is str and sid and type(label)is str and label,'Original nonempty labels')
    rows=[]
    for offset,original in enumerate(daily):
        require('risk'not in original,'Do not overwrite saved original risk')
        holdings=original['holdings'];session=calendar[offset]
        require(type(holdings)is dict and set(holdings)<=set(aliases),'Exact saved holdings resolve')
        amounts={};labels={};locators={}
        for sid,holding in holdings.items():
            require(type(sid)is str and sid and holding['ticker']==aliases[sid],'Original SID/internal ticker binding')
            column=columns.index(aliases[sid]);quantity=number(holding['shares']);price=number(matrix[offset][column])
            require(quantity>0 and price>0,'Positive saved quantities and Close')
            eligible=[observed for observed,entries in observations.items()if observed<=session and sid in entries]
            require(eligible,'No future/backfilled label')
            observed=max(eligible);labels[sid]=dict(label=observations[observed][sid],observation_session=observed)
            amounts[sid]=quantity*price
            locators[sid]=dict(quantity_tokens=['daily',offset,'holdings',sid,'shares'],price_tokens=['closes','data',offset,column],label_tokens=['risk_chains_by_decision',observed,sid])
        total=sum(amounts.values(),Fraction());weights={sid:value/total for sid,value in amounts.items()};chains={}
        for sid,weight in weights.items():chains[labels[sid]['label']]=chains.get(labels[sid]['label'],Fraction())+weight
        ordered=sorted(weights.values(),reverse=True);hhi=sum((w**2 for w in weights.values()),Fraction())
        metrics=None
        if ordered:metrics=dict(hhi=ratio(hhi),effective_n=ratio(Fraction(1)/hhi),top1_weight=ratio(max(ordered)),minimum_single_weight=ratio(min(ordered)),top3_weight=ratio(sum(ordered[:3],Fraction())),risk_chain_top1_weight=ratio(max(chains.values())))
        diagnostic=dict(schema='SAVED_DECIMAL_HOLDINGS_RISK_DIAGNOSTIC_V1',session=session,
            status='DERIVED_SAVED_DECIMAL_DIAGNOSTIC'if ordered else'ALL_CASH_CONCENTRATION_UNDEFINED',
            numeric_basis='EXACT_RATIONAL_OF_SAVED_JSON_DECIMAL_VALUES_NOT_ORIGINAL_FLOAT_RISK',denominator='INVESTED_SECURITIES_ONLY_EXCLUDES_CASH',
            invested_value=ratio(total),metrics=metrics,security_weights={sid:ratio(weights[sid])for sid in sorted(weights)},
            chain_weights={key:ratio(chains[key])for key in sorted(chains)},label_observations={sid:labels[sid]for sid in sorted(labels)},
            source_bytes_authenticated=False,original_saved_risk=False,order_gate_evaluated=False,account_executed=False,historical_label_validity_verified=False,point_in_time_verified=False,promotion_allowed=False)
        rows.append(dict(diagnostic=diagnostic,source_locator_tokens=locators,daily_index=offset))
    return dict(schema='CANDIDATE_CONTINUOUS_SAVED_DAILY_RISK_PROJECTION_V1',rows=rows,path_day_count=120,
                source_bytes_authenticated=False,account_executed=False,original_saved_risk=False,order_gate_evaluated=False,point_in_time_verified=False,promotion_allowed=False)


def inspect(paths,published):
    require([x['track_index']for x in paths]==[8,10,12,14],'Exact four candidate continuous positions')
    require(type(published)is list and len(published)==4,'Complete four saved projections')
    numeric=0;undefined=0
    for original,saved in zip(paths,published):
        expected={key:value for key,value in original.items()if key not in ('stateful_input','daily')}
        expected['projection']=expected_projection(original['stateful_input'],original['daily'])
        exact(saved,expected)
        for row in expected['projection']['rows']:
            if row['diagnostic']['metrics']is None:undefined+=1
            else:numeric+=1
    require(numeric+undefined==480,'Complete 480 positions, including all-cash nulls')
    return dict(schema='CANDIDATE_SAVED_DAILY_RISK_INDEPENDENT_INSPECTION_V1',status='PASS',path_count=4,path_day_count=480,
                numeric_day_count=numeric,undefined_all_cash_day_count=undefined,producer_projection_called=False,
                original_saved_risk=False,order_gate_evaluated=False,account_executed=False,point_in_time_verified=False,promotion_allowed=False)
