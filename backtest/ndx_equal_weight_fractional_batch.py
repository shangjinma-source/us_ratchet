"""Batched equal-weight fractional statistics, explicitly no whole-lot results.

Matches the legacy independent-window fractional arithmetic: daily constant
weights, first window incumbent-distance entry cost only, NAV=1 drawdown anchor.
It does not reproduce actual buy-and-hold or next-session execution returns.
"""
from collections import Counter
from collections.abc import Mapping
import hashlib
import math
from pathlib import Path
import numpy as np
import pandas as pd
from backtest import ndx_joint_weight_evaluation as validation

_SOURCES={str(Path(path).resolve()):hashlib.sha256(Path(path).read_bytes()).hexdigest()
          for path in (__file__,validation.__file__)}


def _check_sources():
    if any(hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest for path,digest in _SOURCES.items()):
        raise ValueError('Fractional batch source drift')


def _require(condition,message):
    if not condition:raise ValueError(message)


def _window(values,cost):
    gross=1.+values.copy()
    gross[0]*=1.-cost
    nav=np.concatenate([np.ones((1,values.shape[1])),np.cumprod(gross,axis=0)],axis=0)
    _require(np.isfinite(nav).all() and (nav>0).all(),'Nonfinite/nonpositive fractional NAV')
    annual=nav[-1]**(252./len(values))-1.
    drawdown=np.max(1.-nav/np.maximum.accumulate(nav,axis=0),axis=0)
    _require(np.isfinite(annual).all(),'Nonfinite annualized return')
    return annual,drawdown


def evaluate_equal_weight_fractional_batch(*,combinations,universe,returns,target_returns,
        incumbent_weights,contract,batch_size=256):
    _check_sources()
    _require(type(batch_size) is int and batch_size>0,'Positive integer batch size required')
    _require(isinstance(contract,Mapping) and set(contract)==validation.CONTRACT_FIELDS,'Exact evaluation contract required')
    for key,value in contract.items():
        _require(type(value) in (int,float) and math.isfinite(value),'Invalid contract number '+key)
    for key in ('fit_days','window_days','step_days'):
        _require(type(contract[key]) is int and contract[key]>0,'Invalid window integer')
    _require(contract['transaction_cost_bps']>=0 and contract['minimum_median_dollar_volume_usd']>0,'Invalid cost/liquidity')
    for key in ('shrinkage_intensity','turnover_anchor_strength','max_single_weight','min_single_weight',
                'top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap'):
        _require(0<=contract[key]<=1,'Invalid fraction')
    _require(0<contract['risk_chain_top1_cap'] and contract['min_single_weight']<=contract['max_single_weight']
        and 0<=contract['minimum_cash_buffer_usd']<contract['portfolio_cash_usd'],'Invalid risk/cash contract')
    _require(isinstance(returns,pd.DataFrame) and not returns.empty and returns.columns.is_unique,'Invalid returns')
    calendar=returns.index
    _require(isinstance(calendar,pd.DatetimeIndex) and calendar.tz is None and not calendar.hasnans
        and calendar.is_unique and calendar.is_monotonic_increasing and calendar.equals(calendar.normalize()),'Invalid calendar')
    _require(all(type(t) is str and t and t==t.strip().upper() for t in returns.columns),'Invalid ticker columns')
    _require(isinstance(target_returns,pd.Series) and target_returns.index.equals(calendar),'Target calendar mismatch')
    values=validation._numeric_values(returns,'returns');target=validation._numeric_values(target_returns,'target')
    _require((values>-1).all() and (target>-1).all(),'Returns must exceed -100 percent')
    required={'ticker','security_id','issuer_id','risk_chain','median_dollar_volume_usd'}
    _require(isinstance(universe,pd.DataFrame) and not universe.empty and universe.columns.is_unique and required<=set(universe),'Incomplete universe')
    for key in ('ticker','security_id','issuer_id','risk_chain'):
        _require(universe[key].map(lambda value:type(value) is str and bool(value) and value==value.strip()).all(),'Invalid identity')
    _require(universe.ticker.is_unique and universe.security_id.is_unique,'Ambiguous identity')
    liquidity=validation._numeric_values(universe[['median_dollar_volume_usd']],'liquidity')
    _require((liquidity>0).all(),'Invalid liquidity')
    _require(isinstance(incumbent_weights,Mapping) and bool(incumbent_weights),'Explicit incumbent weights required')
    _require(all(type(t) is str and t==t.strip().upper() and t in returns and type(w) in (int,float)
        and math.isfinite(w) and w>=0 for t,w in incumbent_weights.items()),'Invalid incumbent weights')
    total=sum(incumbent_weights.values())
    _require(abs(total-1.)<=1e-10,'Incumbent weights must be normalized')
    incumbent={ticker:weight/total for ticker,weight in incumbent_weights.items()}
    combos=list(combinations)
    _require(bool(combos),'Explicit nonempty combinations required')
    info=universe.set_index('ticker').to_dict('index');seen=set()
    for combo in combos:
        _require(type(combo) in (tuple,list) and bool(combo),'Nonempty ticker sequence required')
        _require(all(type(t) is str and t==t.strip().upper() and t in info and t in returns for t in combo),'Ticker outside supplied universe')
        _require(list(combo)==sorted(set(combo)) and tuple(combo) not in seen,'Duplicate/noncanonical combination')
        _require(len({info[t]['issuer_id'] for t in combo})==len(combo),'Duplicate issuer combination')
        seen.add(tuple(combo))
    starts=list(range(contract['fit_days'],len(returns)-contract['window_days']+1,contract['step_days']))
    _require(bool(starts),'No evaluation windows')
    # Sorted incumbent columns match evaluate_joint_weight_task's explicit order.
    incumbent_series=returns[sorted(incumbent)].mul(pd.Series(incumbent),axis=1).sum(axis=1).to_numpy()
    ir=[];idd=[];tr=[];tdd=[]
    for start in starts:
        end=start+contract['window_days']
        a,b=_window(incumbent_series[start:end,None],np.zeros(1));ir.append(a[0]);idd.append(b[0])
        a,b=_window(target[start:end,None],np.zeros(1));tr.append(a[0]);tdd.append(b[0])
    ir=np.asarray(ir);idd=np.asarray(idd);tr=np.asarray(tr);tdd=np.asarray(tdd)
    q=lambda data,p:float(np.quantile(data,p))
    records=[]
    for offset in range(0,len(combos),batch_size):
        group=combos[offset:offset+batch_size]
        # Sum each ordered combination in the same element order as pandas;
        # only windows and candidates are vectorized, avoiding BLAS-dependent sums.
        candidate=np.column_stack([(returns[list(combo)]*(1./len(combo))).sum(axis=1).to_numpy() for combo in group])
        turnover=np.array([.5*sum(abs((1./len(combo) if ticker in combo else 0.)-incumbent.get(ticker,0.))
            for ticker in sorted(set(combo)|set(incumbent))) for combo in group])
        cost=turnover*contract['transaction_cost_bps']/10000.
        _require((cost<1).all(),'Invalid entry cost')
        cr=[];cd=[]
        for window,start in enumerate(starts):
            a,b=_window(candidate[start:start+contract['window_days']],cost if window==0 else np.zeros(len(group)))
            cr.append(a);cd.append(b)
        cr=np.asarray(cr);cd=np.asarray(cd)
        for column,combo in enumerate(group):
            r=cr[:,column];d=cd[:,column]
            metrics=dict(return_p50=q(r,.5),return_p10=q(r,.1),max_drawdown_p50=q(d,.5),max_drawdown_p90=q(d,.9),
                paired_return_p50_vs_incumbent=q(r-ir,.5),paired_return_p10_vs_incumbent=q(r-ir,.1),
                paired_drawdown_cost_p50_vs_incumbent=q(d-idd,.5),paired_drawdown_cost_p90_vs_incumbent=q(d-idd,.9),
                return_p50_vs_012922=q(r,.5)-q(tr,.5),return_p10_vs_012922=q(r,.1)-q(tr,.1),
                max_drawdown_p50_vs_012922=q(d,.5)-q(tdd,.5),max_drawdown_p90_vs_012922=q(d,.9)-q(tdd,.9))
            metrics['target_012922_distance']=sum(abs(metrics[field]) for field in ('return_p50_vs_012922','return_p10_vs_012922','max_drawdown_p50_vs_012922','max_drawdown_p90_vs_012922'))
            weights=[1./len(combo)]*len(combo); chains={}
            for ticker,weight in zip(combo,weights):
                chain=info[ticker]['risk_chain'];chains[chain]=chains.get(chain,0.)+weight
            chain_values=sorted(chains.values(),reverse=True)
            effective=float(1./np.square(np.asarray(weights)).sum());top3=sum(weights[:3]);minimum_liquidity=min(info[t]['median_dollar_volume_usd'] for t in combo)
            risk=dict(risk_chain_top1=chain_values[0],risk_chain_top3=sum(chain_values[:3]),issuer_top1=weights[0],
                weight_top3_max=top3,effective_n_min=effective,portfolio_min_median_dollar_volume_usd=float(minimum_liquidity),
                declared_max_single_passed=weights[0]<=contract['max_single_weight']+1e-9,
                declared_security_top3_weight_passed=top3<=contract['top_weight_cap']+1e-9,
                declared_risk_chain_top1_weight_passed=chain_values[0]<=contract['risk_chain_top1_cap']+1e-9,
                declared_effective_n_passed=effective>=contract['minimum_effective_n_ratio']*len(combo)-1e-9,
                liquidity_constraint_passed=minimum_liquidity>=contract['minimum_median_dollar_volume_usd'],
                minimum_single_weight_observed=weights[0])
            turns=np.zeros(len(starts));turns[0]=turnover[column]
            metrics.update(initial_turnover=float(turnover[column]),initial_transaction_cost=float(cost[column]),
                turnover=q(turns,.5),turnover_p90=q(turns,.9),turnover_max=float(turnover[column]),
                ongoing_rebalance_turnover_p50=0.,transaction_cost=q(turns*contract['transaction_cost_bps']/10000.,.5))
            records.append(dict(tickers=';'.join(combo),holding_count=len(combo),weight_spec='equal_weight',
                fractional_metrics=metrics,risk_liquidity_metrics=risk,rolling_fit_window_count=len(starts),
                whole_lot_status='NOT_EVALUATED',promotion_allowed=False))
    _check_sources()
    return dict(schema='ndx_equal_weight_fractional_batch_v1',records=records,source_hashes=dict(_SOURCES),
        window_starts=[str(returns.index[start].date()) for start in starts],window_days=contract['window_days'],
        count=len(records),input_calendar_start=str(calendar[0].date()),input_calendar_end=str(calendar[-1].date()),
        execution_model='CONSTANT_DAILY_FRACTIONAL_WEIGHTS_INDEPENDENT_OVERLAPPING_WINDOWS',
        cost_model='FIRST_WINDOW_INCUMBENT_DISTANCE_ONLY_THEN_ZERO_EQUAL_WEIGHT_TURNOVER',
        whole_lot_status='NOT_EVALUATED',full_legacy_result_compatible=False,source_authenticity_verified=False,promotion_allowed=False)
