"""Recover fractional statistics from complete saved window weights, without fitting."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import platform
import numpy as np
import pandas as pd
import scipy
from backtest import ndx_candidate_input_equivalence_v2_research as equivalence

SOURCE = Path(__file__).resolve()
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
TOLERANCE = 1e-12


def recover(*, arguments, saved):
    arguments, saved = deepcopy((arguments, saved))
    if arguments['engine'] != 'non_equal_fractional_v1':
        raise ValueError('Only saved non-equal fractional windows supported')
    proof = equivalence.candidate_numerical_input_fingerprint(**arguments)
    actual = dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__)
    if arguments['runtime'] != actual:
        raise ValueError('Original numerical runtime required')
    if saved['schema'] != 'ndx_non_equal_fractional_research_v1':
        raise ValueError('Saved fractional result required')
    if any(saved['result'].get(k) != arguments['task'][k] for k in ('tickers','holding_count','weight_spec')):
        raise ValueError('Saved result/task differs')
    if saved.get('promotion_allowed') is not False or saved.get('point_in_time_verified') is not False:
        raise ValueError('Research-only saved result required')
    equivalence.previous._verify(saved['source_hashes'])
    if saved['source_hashes'] != equivalence.previous.fractional._sources():
        raise ValueError('Saved numerical closure differs')
    inputs = arguments['inputs']; task = arguments['task']; contract = inputs['contract']
    combo = task['tickers'].split(';')
    returns = inputs['returns']; target = inputs['target_returns']
    fit, window, step = (contract[k] for k in ('fit_days', 'window_days', 'step_days'))
    starts = list(range(fit, len(returns)-window+1, step))
    windows = saved['historical_window_weights']
    if len(windows) != len(starts) or saved['result']['rolling_fit_window_count'] != len(starts):
        raise ValueError('Complete window denominator required')
    incumbent = dict(inputs['incumbent_weights'])
    total = sum(incumbent.values()); incumbent = {k:v/total for k,v in incumbent.items()}
    prior = None; rows = []
    anchored = task['weight_spec'] == 'constrained_fixed_shrinkage_turnover_anchor'
    def metric(series, cost=0.):
        values = series.astype(float).copy()
        values.iloc[0] = (1.+values.iloc[0])*(1.-cost)-1.
        nav = pd.Series(np.concatenate(([1.], (1.+values).cumprod().to_numpy(dtype=float))))
        return float(nav.iloc[-1] ** (252./len(values))-1.), float((1.-nav/nav.cummax()).max())
    for start, record in zip(starts, windows):
        if (record['fit_start'] != str(returns.index[start-fit].date()) or
            record['fit_end'] != str(returns.index[start-1].date()) or
            type(record['fit_row_count']) is not int or record['fit_row_count'] != fit or record['tickers'] != combo):
            raise ValueError('Window identity/order/boundary differs')
        weights = record['weights']
        if set(weights) != set(combo) or any(type(v) not in (int,float) or not math.isfinite(v) or v <= 0 for v in weights.values()):
            raise ValueError('Complete positive finite weights required')
        if abs(sum(weights.values())-1.) > TOLERANCE:
            raise ValueError('Saved weights must sum to one')
        if record['anchor_weights'] != (prior if anchored else None):
            raise ValueError('Previous fitted target anchor differs')
        strength = record['turnover_anchor_strength']
        if type(strength) not in (int,float) or strength != (contract['turnover_anchor_strength'] if anchored else 0.):
            raise ValueError('Anchor parameter differs')
        reference = incumbent if prior is None else prior
        turnover = .5 * sum(abs(weights.get(t,0.)-reference.get(t,0.)) for t in set(weights)|set(reference))
        cost = float(turnover*contract['transaction_cost_bps']/10000.)
        forward = returns.iloc[start:start+window]
        candidate = forward[combo].mul(pd.Series(weights),axis=1).sum(axis=1)
        benchmark = forward[list(incumbent)].mul(pd.Series(incumbent),axis=1).sum(axis=1)
        cr,cd = metric(candidate,cost); ir,idd = metric(benchmark); tr,td = metric(target.iloc[start:start+window])
        rows.append(dict(start=str(forward.index[0].date()),end=str(forward.index[-1].date()),
            candidate_return=cr,candidate_drawdown=cd,incumbent_return=ir,incumbent_drawdown=idd,
            target_return=tr,target_drawdown=td,turnover=float(turnover),cost=cost))
        prior = weights
    def values(key): return np.asarray([row[key] for row in rows])
    def q(key,p): return float(np.quantile(values(key),p))
    metrics = dict(return_p50=q('candidate_return',.5),return_p10=q('candidate_return',.1),
        max_drawdown_p50=q('candidate_drawdown',.5),max_drawdown_p90=q('candidate_drawdown',.9))
    for stem,key,ps in [('return','return',[.5,.1]),('drawdown_cost','drawdown',[.5,.9])]:
        for p in ps:
            metrics[f'paired_{stem}_p{int(p*100)}_vs_incumbent'] = float(np.quantile(values('candidate_'+key)-values('incumbent_'+key),p))
    for name,key,p in [('return_p50','return',.5),('return_p10','return',.1),('max_drawdown_p50','drawdown',.5),('max_drawdown_p90','drawdown',.9)]:
        metrics[name+'_vs_012922'] = metrics[name]-q('target_'+key,p)
    metrics['target_012922_distance'] = sum(abs(metrics[k+'_vs_012922']) for k in ('return_p50','return_p10','max_drawdown_p50','max_drawdown_p90'))
    metrics.update(turnover=q('turnover',.5),initial_turnover=rows[0]['turnover'],initial_transaction_cost=rows[0]['cost'],
        ongoing_rebalance_turnover_p50=float(np.quantile(values('turnover')[1:],.5)) if len(rows)>1 else 0.,
        turnover_p90=q('turnover',.9),turnover_max=float(max(values('turnover'))),transaction_cost=q('cost',.5))
    closure = proof['source_hashes'] | {str(SOURCE):LOADED}
    equivalence.previous._verify(closure)
    return dict(metrics=metrics,windows=rows,input_fingerprint=proof['numerical_input_sha256'],
        source_hashes=closure, fitted=False, promotion_allowed=False)


def verify_original(*, arguments, saved):
    result = recover(arguments=arguments,saved=saved)
    for key,value in result['metrics'].items():
        original = saved['result'][key]
        if type(original) not in (int,float) or not math.isfinite(original) or abs(value-original)>TOLERANCE:
            raise ValueError('Original metric reconstruction differs: '+key)
    return result
