"""Reduce thirteen already-fitted historical windows; no fitting or file IO."""
from copy import deepcopy
from datetime import date
import math

import numpy as np
import pandas as pd

from backtest.ndx_cardinality_discovery import _window_metrics


PARAMETERS = dict(max_single_weight=.45, min_single_weight=.05,
                  top_weight_cap=.8, minimum_effective_n_ratio=.7,
                  risk_chain_top1_cap=.55)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite(value):
    require(type(value) in (int, float) and math.isfinite(value),
            'Finite nonboolean number required')
    return float(value)


def vector(values, count, *, returns=False):
    require(type(values) is list and len(values) == count, 'Complete numeric vector')
    result = [finite(value) for value in values]
    if returns:
        require(all(value > -1 for value in result), 'Returns must exceed minus one')
    return result


def reduce_fitted_scoring_windows(*, cutoff, return_dates, securities,
                                  candidate_returns, incumbent_returns,
                                  target_returns, original_incumbent_weights,
                                  fitted_windows):
    """Explicit numeric inputs only; caller must authenticate all sources separately.

    Security order is the fitted panel's column order. The fee summation retains
    the legacy set-union iteration and records that order for independent replay.
    These historical fitted weights are never labeled execution targets.
    """
    require(type(return_dates) is list and len(return_dates) == 504
            and return_dates == sorted(set(return_dates)) and return_dates[-1] == cutoff,
            'Exactly 504 ordered returns ending at cutoff')
    for value in return_dates:
        require(type(value) is str and date.fromisoformat(value).isoformat() == value
                and date.fromisoformat(value).weekday() < 5, 'Canonical return weekday')
    require(type(securities) is list and bool(securities), 'Explicit ordered securities')
    for security in securities:
        require(type(security) is dict and set(security) ==
                {'security_id', 'ticker', 'issuer_id', 'risk_chain'}, 'Identity/risk fields')
        require(all(type(value) is str and value and value == value.strip()
                    for value in security.values()), 'Canonical identity/risk text')
    for key in ('security_id', 'ticker', 'issuer_id'):
        require(len({security[key] for security in securities}) == len(securities),
                'Unique security, ticker and issuer')
    tickers = [security['ticker'] for security in securities]
    count = len(tickers)
    require(type(candidate_returns) is list and len(candidate_returns) == 504,
            'Complete candidate matrix')
    frame = pd.DataFrame([vector(row, count, returns=True) for row in candidate_returns],
                         index=pd.DatetimeIndex(return_dates), columns=tickers)
    incumbent = pd.Series(vector(incumbent_returns, 504, returns=True), index=frame.index)
    target = pd.Series(vector(target_returns, 504, returns=True), index=frame.index)
    require(type(original_incumbent_weights) is dict and len(original_incumbent_weights) == 8,
            'Eight explicit original incumbent weights')
    require(all(type(key) is str and key and key == key.strip()
                for key in original_incumbent_weights), 'Canonical incumbent tickers')
    original = {key: finite(value) for key, value in original_incumbent_weights.items()}
    require(min(original.values()) >= 0 and sum(original.values()) > 0,
            'Nonnegative incumbent with positive mass')
    total = sum(original.values())
    require(math.isfinite(total) and total > 0, 'Finite positive incumbent total mass')
    normalized_original = {key: value / total for key, value in original.items()}
    require(type(fitted_windows) is list and len(fitted_windows) == 13,
            'All thirteen fitted windows required')
    rows = []
    previous = None
    for index, fitted in enumerate(fitted_windows):
        start = index * 21 + 126
        require(type(fitted['window_index']) is int and fitted['window_index'] == index,
                'Ordered fitted window identity')
        require(fitted['fit_first_return_end'] == return_dates[start - 126]
                and fitted['fit_last_return_end'] == return_dates[start - 1]
                and fitted['evaluation_first_return_end'] == return_dates[start]
                and fitted['evaluation_last_return_end'] == return_dates[start + 125],
                'Strict causal 126 fit and 126 evaluation window')
        require(type(fitted['projection_relaxed']) is bool, 'Explicit projection flag')
        values = vector(fitted['weights'], count)
        require(min(values) >= 0 and math.isclose(sum(values), 1., abs_tol=1e-9, rel_tol=0),
                'Fitted nonnegative simplex')
        weights = pd.Series(values, index=tickers, dtype=float)
        candidate = weights.to_dict()
        reference = normalized_original if previous is None else previous
        cost_order = list(set(candidate) | set(reference))
        turnover = 0.5 * sum(abs(candidate.get(ticker, 0.) - reference.get(ticker, 0.))
                             for ticker in cost_order)
        cost = float(turnover * 10. / 10000.)
        forward = frame.iloc[start:start + 126]
        series = forward[tickers].mul(weights, axis=1).sum(axis=1)
        candidate_metric = _window_metrics(series, 126, 126, entry_cost=cost)
        incumbent_metric = _window_metrics(incumbent.iloc[start:start + 126], 126, 126)
        target_metric = _window_metrics(target.iloc[start:start + 126], 126, 126)
        chain_weights = {}
        for security, value in zip(securities, values):
            chain = security['risk_chain']
            chain_weights[chain] = chain_weights.get(chain, 0.) + value
        ordered = sorted(values, reverse=True)
        effective_n = float(1. / np.square(weights.to_numpy()).sum())
        checks = dict(
            MAX_SINGLE_WEIGHT=ordered[0] <= PARAMETERS['max_single_weight'] + 1e-9,
            MIN_SINGLE_WEIGHT=ordered[-1] >= PARAMETERS['min_single_weight'] - 1e-9,
            SECURITY_TOP3_WEIGHT=sum(ordered[:3]) <= PARAMETERS['top_weight_cap'] + 1e-9,
            MINIMUM_EFFECTIVE_N=effective_n >= count * PARAMETERS['minimum_effective_n_ratio'] - 1e-9,
            RISK_CHAIN_TOP1_WEIGHT=max(chain_weights.values()) <= PARAMETERS['risk_chain_top1_cap'] + 1e-9)
        rows.append(dict(window_index=index, fitted_window_preserved=deepcopy(fitted),
                         fee_reference_weights=deepcopy(reference), fee_summation_order=cost_order,
                         turnover=turnover, entry_cost=cost,
                         candidate_annualized=candidate_metric[0][0], candidate_drawdown=candidate_metric[1][0],
                         incumbent_annualized=incumbent_metric[0][0], incumbent_drawdown=incumbent_metric[1][0],
                         target_annualized=target_metric[0][0], target_drawdown=target_metric[1][0],
                         effective_n=effective_n, chain_weights=chain_weights, risk_checks=checks))
        previous = candidate
    def quantile(key, probability):
        return float(np.quantile([row[key] for row in rows], probability))
    metrics = {}
    for prefix, source in (('', 'candidate'), ('incumbent_', 'incumbent'), ('target_', 'target')):
        for label, field, probability in (('return_p50', 'annualized', .5), ('return_p10', 'annualized', .1),
                                         ('max_drawdown_p50', 'drawdown', .5), ('max_drawdown_p90', 'drawdown', .9)):
            metrics[prefix + label] = quantile(source + '_' + field, probability)
    metrics['target_012922_distance'] = sum(abs(metrics[key] - metrics['target_' + key])
        for key in ('return_p50', 'return_p10', 'max_drawdown_p50', 'max_drawdown_p90'))
    for field, label, probabilities in (('annualized', 'return', (.5, .1)), ('drawdown', 'drawdown_cost', (.5, .9))):
        difference = np.asarray([row['candidate_' + field] for row in rows]) - np.asarray([row['incumbent_' + field] for row in rows])
        for probability in probabilities:
            metrics[f'paired_{label}_p{int(probability * 100)}_vs_incumbent'] = float(np.quantile(difference, probability))
    require(all(math.isfinite(value) for value in metrics.values()), 'Finite aggregate metrics')
    return dict(schema='MULTIDECISION_FITTED_WINDOW_SCORE_REDUCTION_V1', cutoff=cutoff,
                securities=deepcopy(securities), metrics=metrics, windows=rows,
                fractional_risk_passed=all(all(row['risk_checks'].values()) for row in rows),
                risk_gate_semantics='ALL_FIVE_DECLARED_FRACTIONAL_CONSTRAINTS_EVERY_WINDOW',
                original_incumbent_weights=deepcopy(original_incumbent_weights),
                normalized_incumbent_weights=normalized_original,
                source_bytes_authenticated=False, fit_performed=False,
                score_computed=True, point_in_time_verified=False,
                selected_rolling_weights_are_execution_targets=False,
                whole_lot_gate_evaluated=False, formal_benchmark_passed=False,
                account_executed=False, promotion_allowed=False)
