"""Independent binary64 readback of thirteen saved fitted-window scores; no IO/fit."""
from copy import deepcopy
from datetime import date
import math
import numpy as np


def require(ok, message):
    if not ok:
        raise ValueError(message)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'Finite nonboolean number')
    return float(value)


def vector(value, length, returns=False):
    require(type(value) is list and len(value) == length, 'Complete ordered vector')
    result = [number(item) for item in value]
    require(not returns or all(item > -1 for item in result), 'Return exceeds minus one')
    return result


def exact(actual, expected, path='$'):
    """No tolerance; float hex also distinguishes signed zero; bool is never integer."""
    require(type(actual) is type(expected), 'Type mismatch at ' + path)
    if isinstance(expected, dict):
        require(actual.keys() == expected.keys(), 'Keys mismatch at ' + path)
        for key in expected:
            exact(actual[key], expected[key], path + '/' + str(key))
    elif isinstance(expected, list):
        require(len(actual) == len(expected), 'Length mismatch at ' + path)
        for index, item in enumerate(expected):
            exact(actual[index], item, path + '/' + str(index))
    elif isinstance(expected, float):
        require(math.isfinite(actual) and actual.hex() == expected.hex(), 'Binary64 mismatch at ' + path)
    else:
        require(actual == expected, 'Value mismatch at ' + path)


def window_numbers(returns, fee):
    require(len(returns) == 126 and 0 <= fee < 1, '126 returns and valid fee')
    values = np.asarray(returns, dtype=np.float64).copy()
    require(np.isfinite(values).all() and (values > -1).all(), 'Finite window returns')
    # Preserve the original subtract/add round trip on the first return.
    values[0] = (1.0 + values[0]) * (1.0 - fee) - 1.0
    path = np.concatenate((np.asarray([1.0]), np.cumprod(1.0 + values)))
    annual = float(path[-1] ** (252.0 / 126) - 1.0)
    drawdown = float(np.max(1.0 - path / np.maximum.accumulate(path)))
    require(math.isfinite(annual) and math.isfinite(drawdown), 'Finite path metrics')
    return annual, drawdown


def inspect_fitted_scoring_windows(*, cutoff, return_dates, securities,
                                   candidate_returns, incumbent_returns, target_returns,
                                   original_incumbent_weights, fitted_windows, saved_score):
    require(type(return_dates) is list and len(return_dates) == 504
            and return_dates == sorted(set(return_dates)) and return_dates[-1] == cutoff,
            'Exactly 504 ordered return dates')
    for item in return_dates:
        require(type(item) is str and date.fromisoformat(item).isoformat() == item
                and date.fromisoformat(item).weekday() < 5, 'Canonical weekday')
    require(type(securities) is list and bool(securities), 'Securities required')
    for item in securities:
        require(type(item) is dict and set(item) == {'security_id', 'ticker', 'issuer_id', 'risk_chain'},
                'Identity and risk keys')
        require(all(type(value) is str and value and value.strip() == value for value in item.values()),
                'Canonical identity text')
    for key in ('security_id', 'ticker', 'issuer_id'):
        require(len({item[key] for item in securities}) == len(securities), 'Unique coordinate')
    names = [item['ticker'] for item in securities]
    k = len(names)
    require(type(candidate_returns) is list and len(candidate_returns) == 504, 'Complete matrix')
    matrix = [vector(row, k, True) for row in candidate_returns]
    incumbent = vector(incumbent_returns, 504, True)
    target = vector(target_returns, 504, True)
    require(type(original_incumbent_weights) is dict and len(original_incumbent_weights) == 8,
            'Complete original eight')
    require(all(type(key) is str and key and key.strip() == key for key in original_incumbent_weights),
            'Canonical original tickers')
    original = {key: number(value) for key, value in original_incumbent_weights.items()}
    total = sum(original.values())
    require(min(original.values()) >= 0 and math.isfinite(total) and total > 0, 'Original weight mass')
    normalized = {key: value / total for key, value in original.items()}
    require(type(fitted_windows) is list and len(fitted_windows) == 13, 'All thirteen fits')
    require(type(saved_score) is dict and type(saved_score.get('windows')) is list
            and len(saved_score['windows']) == 13, 'All thirteen saved windows')
    previous = None
    rows = []
    for index, fitted in enumerate(fitted_windows):
        start = 126 + index * 21
        require(type(fitted) is dict and type(fitted.get('window_index')) is int
                and fitted['window_index'] == index, 'Fitted index')
        for key, position in (('fit_first_return_end', start - 126), ('fit_last_return_end', start - 1),
                              ('evaluation_first_return_end', start), ('evaluation_last_return_end', start + 125)):
            require(fitted.get(key) == return_dates[position], 'Causal window endpoint')
        require(type(fitted.get('projection_relaxed')) is bool, 'Projection flag')
        weights = vector(fitted['weights'], k)
        require(min(weights) >= 0 and math.isclose(sum(weights), 1., abs_tol=1e-9, rel_tol=0), 'Simplex')
        current = dict(zip(names, weights))
        reference = normalized if previous is None else previous
        order = saved_score['windows'][index].get('fee_summation_order')
        require(type(order) is list and all(type(name) is str for name in order)
                and len(order) == len(set(order)) and set(order) == set(current) | set(reference),
                'Fee order must be exact unique union')
        turnover = .5 * sum(abs(current.get(name, 0.) - reference.get(name, 0.)) for name in order)
        fee = float(turnover * 10. / 10000.)
        daily = []
        for row in matrix[start:start + 126]:
            # DataFrame built from row vectors stores column blocks. Its strided
            # axis-1 finite reduction is ordered addition, not Python sum/np pairwise sum.
            value = 0.0
            for ret, weight in zip(row, weights):
                value = value + ret * weight
            daily.append(value)
        ca, cd = window_numbers(daily, fee)
        ia, idd = window_numbers(incumbent[start:start + 126], 0.)
        ta, td = window_numbers(target[start:start + 126], 0.)
        chains = {}
        for security, weight in zip(securities, weights):
            key = security['risk_chain']
            chains[key] = chains.get(key, 0.) + weight
        ordered = sorted(weights, reverse=True)
        eff = float(1. / np.square(np.asarray(weights, dtype=np.float64)).sum())
        checks = dict(MAX_SINGLE_WEIGHT=ordered[0] <= .45 + 1e-9,
                      MIN_SINGLE_WEIGHT=ordered[-1] >= .05 - 1e-9,
                      SECURITY_TOP3_WEIGHT=sum(ordered[:3]) <= .8 + 1e-9,
                      MINIMUM_EFFECTIVE_N=eff >= k * .7 - 1e-9,
                      RISK_CHAIN_TOP1_WEIGHT=max(chains.values()) <= .55 + 1e-9)
        rows.append(dict(window_index=index, fitted_window_preserved=deepcopy(fitted),
                         fee_reference_weights=deepcopy(reference), fee_summation_order=deepcopy(order),
                         turnover=turnover, entry_cost=fee, candidate_annualized=ca, candidate_drawdown=cd,
                         incumbent_annualized=ia, incumbent_drawdown=idd, target_annualized=ta,
                         target_drawdown=td, effective_n=eff, chain_weights=chains, risk_checks=checks))
        previous = current
    metrics = {}
    for prefix, name in (('', 'candidate'), ('incumbent_', 'incumbent'), ('target_', 'target')):
        for label, field, probability in (('return_p50', 'annualized', .5), ('return_p10', 'annualized', .1),
                                         ('max_drawdown_p50', 'drawdown', .5), ('max_drawdown_p90', 'drawdown', .9)):
            metrics[prefix + label] = float(np.quantile([row[name + '_' + field] for row in rows], probability))
    metrics['target_012922_distance'] = sum(abs(metrics[key] - metrics['target_' + key])
        for key in ('return_p50', 'return_p10', 'max_drawdown_p50', 'max_drawdown_p90'))
    for field, label, probabilities in (('annualized', 'return', (.5, .1)), ('drawdown', 'drawdown_cost', (.5, .9))):
        difference = np.asarray([row['candidate_' + field] for row in rows]) - np.asarray([row['incumbent_' + field] for row in rows])
        for probability in probabilities:
            metrics[f'paired_{label}_p{int(probability * 100)}_vs_incumbent'] = float(np.quantile(difference, probability))
    expected = dict(schema='MULTIDECISION_FITTED_WINDOW_SCORE_REDUCTION_V1', cutoff=cutoff,
                    securities=deepcopy(securities), metrics=metrics, windows=rows,
                    fractional_risk_passed=all(all(row['risk_checks'].values()) for row in rows),
                    risk_gate_semantics='ALL_FIVE_DECLARED_FRACTIONAL_CONSTRAINTS_EVERY_WINDOW',
                    original_incumbent_weights=deepcopy(original_incumbent_weights), normalized_incumbent_weights=normalized,
                    source_bytes_authenticated=False, fit_performed=False, score_computed=True,
                    point_in_time_verified=False, selected_rolling_weights_are_execution_targets=False,
                    whole_lot_gate_evaluated=False, formal_benchmark_passed=False, account_executed=False, promotion_allowed=False)
    exact(saved_score, expected)
    return dict(schema='MULTIDECISION_WINDOW_SCORING_INSPECTION_V1', status='PASS', window_count=13,
                window_return_count=126, metric_count=len(metrics), binary64_comparison='EXACT_HEX_NO_TOLERANCE',
                numpy_version=np.__version__, source_bytes_authenticated=False, fit_performed=False,
                formal_benchmark_passed=False, account_executed=False, promotion_allowed=False)
