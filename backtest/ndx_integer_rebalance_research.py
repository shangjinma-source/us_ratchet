"""Self-financing finite-domain integer rebalancing research, not a live engine.

The fixed ticker set is an execution subproblem, not a portfolio cardinality
answer. Supplied schedules are execution targets; their historical fit/signal
provenance must be verified by the caller. Only current marks influence actions.
"""
import math
from collections.abc import Mapping

import numpy as np
import pandas as pd

from backtest.ndx_integer_allocation_research import search_integer_allocation_domain, RISK_FIELDS
from backtest.ndx_whole_lot_rebalance import _constraint_snapshot


def _require(condition,message):
    if not condition:
        raise ValueError(message)


def simulate_integer_rebalance_research(*,prices,schedule,initial_cash,initial_shares,
        minimum_cash_buffer_usd,transaction_cost_bps,risk_chain_by_ticker,constraints,
        domain_radius,max_evaluations_per_rebalance,selection_policy):
    _require(selection_policy in ('TRACKING_FIRST','FEES_FIRST'),'Explicit selection policy required')
    _require(type(domain_radius) is int and domain_radius>=0,'Invalid domain radius')
    _require(type(max_evaluations_per_rebalance) is int and max_evaluations_per_rebalance>0,'Invalid search budget')
    _require(isinstance(prices,pd.DataFrame) and not prices.empty and prices.columns.is_unique,'Invalid price panel')
    _require(all(isinstance(t,str) and t and t==t.strip() for t in prices),'Invalid ticker')
    names=sorted(prices)
    _require(isinstance(prices.index,pd.DatetimeIndex) and prices.index.tz is None
        and prices.index.is_unique and prices.index.is_monotonic_increasing and not prices.index.hasnans
        and prices.index.equals(prices.index.normalize()),'Invalid price dates')
    _require(all(type(v) in (int,float) or isinstance(v,(np.integer,np.floating))
        for v in prices.to_numpy().flat) and not any(isinstance(v,(bool,np.bool_)) for v in prices.to_numpy().flat),
        'Non-numeric price values')
    _require(np.isfinite(prices.to_numpy(dtype=float)).all() and (prices.to_numpy(dtype=float)>0).all(),'Invalid price values')
    _require(isinstance(initial_shares,Mapping) and set(initial_shares)==set(names)
        and all(type(v) is int and v>=0 for v in initial_shares.values()),'Invalid initial shares')
    _require(isinstance(risk_chain_by_ticker,Mapping) and set(risk_chain_by_ticker)==set(names),'Risk label coverage differs')
    _require(isinstance(constraints,Mapping) and set(constraints)==RISK_FIELDS,'Complete risk contract required')
    for value in (initial_cash,minimum_cash_buffer_usd,transaction_cost_bps):
        _require(type(value) in (int,float) and math.isfinite(value) and value>=0,'Invalid cash/fee contract')
    _require(isinstance(schedule,(list,tuple)) and schedule,'Nonempty explicit schedule required')
    items=[]
    for date,weights in schedule:
        _require(isinstance(date,(str,pd.Timestamp)),'Invalid schedule date type')
        date=pd.Timestamp(date)
        _require(not pd.isna(date) and date.tzinfo is None and date==date.normalize() and date in prices.index,'Schedule date absent/invalid')
        _require(isinstance(weights,Mapping) and set(weights)==set(names),'Fixed ticker schedule required')
        _require(all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in weights.values())
            and abs(sum(weights.values())-1)<=1e-10,'Invalid explicit target weights')
        items.append((date,dict(weights)))
    _require([d for d,_ in items]==sorted({d for d,_ in items}),'Schedule dates must be unique and sorted')
    targets=dict(items);path=prices.loc[items[0][0]:,names]
    shares=dict(initial_shares);cash=float(initial_cash)
    initial_equity=cash+sum(shares[t]*float(path.iloc[0][t]) for t in names)
    _require(math.isfinite(initial_equity) and initial_equity>0,'Invalid initial equity')
    daily=[];rebalances=[];fees_total=0.;partial=False;unresolved=False
    for date,marks_row in path.iterrows():
        marks={t:float(marks_row[t]) for t in names}
        if date in targets:
            pretrade=cash+sum(shares[t]*marks[t] for t in names)
            investable=max(0.,pretrade-minimum_cash_buffer_usd)
            floors={t:math.floor(investable*targets[date][t]/marks[t]) for t in names}
            domains={t:sorted(set(range(max(0,floors[t]-domain_radius),floors[t]+domain_radius+1))|{shares[t]}) for t in names}
            search=search_integer_allocation_domain(prices=marks,target_weights=targets[date],
                current_shares=shares,current_cash=cash,transaction_cost_bps=transaction_cost_bps,
                minimum_cash_buffer_usd=minimum_cash_buffer_usd,risk_chain_by_ticker=risk_chain_by_ticker,
                constraints=constraints,share_domains=domains,max_evaluations=max_evaluations_per_rebalance)
            partial |= not search['pareto_complete_within_explicit_domain']
            before_shares=dict(shares);before_cash=cash;choice=None
            if search['pareto']:
                fields=('total_tracking_error_including_cash','fees_usd') if selection_policy=='TRACKING_FIRST' else ('fees_usd','total_tracking_error_including_cash')
                choice=min(search['pareto'],key=lambda row:(row[fields[0]],row[fields[1]],tuple(row['shares'][t] for t in names)))
                shares=dict(choice['shares']);cash=choice['posttrade_cash_usd'];fees_total+=choice['fees_usd']
                status='FINITE_DOMAIN_SELECTION' if search['pareto_complete_within_explicit_domain'] else 'BEST_OBSERVED_PARTIAL_DOMAIN'
            else:
                unresolved=True;status='UNRESOLVED_NO_FEASIBLE_OBSERVED_CARRY'
            rebalances.append(dict(date=str(date.date()),status=status,target_weights=targets[date],
                pretrade_equity_usd=pretrade,pretrade_cash_usd=before_cash,previous_shares=before_shares,
                selected_shares=dict(shares),posttrade_cash_usd=cash,
                fees_usd=choice['fees_usd'] if choice else 0.,
                finite_domain_size=search['finite_domain_size'],evaluated=search['evaluated'],
                feasible_evaluated=search['feasible_evaluated'],unexamined=search['unexamined'],
                finite_domain_complete=search['pareto_complete_within_explicit_domain'],
                selected_tracking_error_including_cash=choice['total_tracking_error_including_cash'] if choice else None))
        notionals={t:shares[t]*marks[t] for t in names}
        snapshot=_constraint_snapshot(notionals,risk_chain_by_ticker=risk_chain_by_ticker,**constraints)
        invested=sum(notionals.values());equity=cash+invested
        cash_pass=cash>=minimum_cash_buffer_usd-1e-9
        passed=bool(snapshot['constraints_passed'] and min(shares.values())>=1 and cash_pass)
        daily.append(dict(date=str(date.date()),is_rebalance=date in targets,shares=dict(shares),cash_usd=cash,
            invested_usd=invested,equity_usd=equity,security_weights={t:notionals[t]/invested if invested>0 else 0. for t in names},
            cash_buffer_passed=cash_pass,minimum_one_share_passed=min(shares.values())>=1,
            risk_snapshot=snapshot,all_constraints_passed=passed))
        if date in targets:
            rebalances[-1]['posttrade_constraints_passed']=passed
    values=[initial_equity]+[r['equity_usd'] for r in daily]
    peak=values[0];drawdown=0.
    for value in values:
        peak=max(peak,value);drawdown=max(drawdown,1-value/peak)
    return dict(schema='ndx_integer_rebalance_research_v1',
        scope='FIXED_TICKER_EXECUTION_SUBPROBLEM_NOT_CARDINALITY_DECISION',
        selection_policy=selection_policy,domain_radius=domain_radius,zero_shares_retained_in_domain=True,
        status='UNRESOLVED' if unresolved else ('PARTIAL_SEARCH_PATH' if partial else 'FINITE_DOMAIN_PATH_COMPLETED'),
        any_partial_search=partial,any_unresolved_rebalance=unresolved,
        all_days_constraints_passed=all(r['all_constraints_passed'] for r in daily),
        all_rebalance_days_constraints_passed=all(r['posttrade_constraints_passed'] for r in rebalances),
        initial_equity_usd=initial_equity,terminal_equity_usd=daily[-1]['equity_usd'],
        terminal_cash_usd=cash,terminal_shares=shares,total_fees_usd=fees_total,
        path_return_net=daily[-1]['equity_usd']/initial_equity-1.,path_max_drawdown=drawdown,
        drawdown_initial_peak='PRETRADE_INITIAL_MARKED_EQUITY_INCLUDING_INITIAL_SHARES',
        daily=daily,rebalances=rebalances,signal_provenance_verified=False,signal_timing_verified=False,
        schedule_source='CALLER_SUPPLIED_EXECUTION_TARGETS',
        global_allocation_optimality_claim_allowed=False,promotion_allowed=False,order_generation_allowed=False)
