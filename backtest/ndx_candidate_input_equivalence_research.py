"""Conservative per-candidate input equality; never authorize checkpoint reuse.

Whole input legality is checked before ignoring unrelated finite columns. No
fitter, projection, metric evaluator, or historical checkpoint is executed.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

import pandas as pd

from backtest import ndx_dynamic_training_semantics as semantics
from backtest import ndx_equal_weight_fractional_batch as equal
from backtest import ndx_joint_weight_evaluation as validation
from backtest import ndx_joint_weight_evaluation_v3 as joint
from backtest import ndx_non_equal_fractional_research as fractional

SOURCE = Path(__file__).resolve()
LOADED = {str(Path(p).resolve()): hashlib.sha256(Path(p).read_bytes()).hexdigest()
          for p in (SOURCE, semantics.__file__)}
ENGINES = {'equal_weight_fractional_v1', 'non_equal_fractional_v1', 'joint_weight_v3'}
IDENTITY_FIELDS = ('ticker', 'security_id', 'issuer_id', 'risk_chain',
                   'synthetic_price', 'median_dollar_volume_usd')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def _verify(sources):
    if type(sources) is not dict or not sources:
        raise ValueError('Nonempty absolute source bindings required')
    for path, digest in sources.items():
        if (type(path) is not str or not Path(path).is_absolute()
                or type(digest) is not str or re.fullmatch('[0-9a-f]{64}', digest) is None
                or hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest):
            raise ValueError('Candidate equivalence source drift or invalid binding: ' + str(path))


def numerical_source_hashes(engine):
    if engine not in ENGINES:
        raise ValueError('Explicit supported numerical engine required')
    if engine == 'equal_weight_fractional_v1':
        equal._check_sources()
        result = dict(equal._SOURCES)
    else:
        joint._validate_loaded_sources()
        result = {str(joint.ROOT / name): digest for name, digest in joint._LOADED_SOURCES.items()}
        if engine == 'non_equal_fractional_v1':
            result.update(fractional._sources())
    _verify(result)
    return result


def _validate_without_evaluation(task, inputs):
    # Independent validation only. Do not invoke or replace an evaluator edge.
    if type(task['tickers']) is not str:
        raise ValueError('Explicit ticker sequence required')
    tickers = task['tickers'].split(';')
    if (not all(tickers) or tickers != sorted(set(tickers))
            or type(task['holding_count']) is not int or task['holding_count'] != len(tickers)
            or task['weight_spec'] not in set(validation.WEIGHT_SPECS) | {'equal_weight'}):
        raise ValueError('Invalid task specification')
    if pd.Timestamp(task['decision_data_end']) >= pd.Timestamp(task['selection_date']):
        raise ValueError('Cutoff must precede selection')
    contract = inputs['contract']
    if type(contract) is not dict or set(contract) != validation.CONTRACT_FIELDS:
        raise ValueError('All fourteen contract parameters required')
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in contract.values()):
        raise ValueError('Finite nonboolean contract numbers required')
    if any(type(contract[key]) is not int or contract[key] <= 0 for key in ('fit_days', 'window_days', 'step_days')):
        raise ValueError('Positive integer windows required')
    if any(not 0 <= contract[key] <= 1 for key in ('shrinkage_intensity', 'turnover_anchor_strength')):
        raise ValueError('Invalid shrinkage/anchor fraction')
    if any(not 0 < contract[key] <= 1 for key in ('max_single_weight', 'min_single_weight',
            'top_weight_cap', 'minimum_effective_n_ratio', 'risk_chain_top1_cap')):
        raise ValueError('Invalid original risk bounds')
    if (contract['min_single_weight'] > contract['max_single_weight']
            or contract['transaction_cost_bps'] < 0 or contract['minimum_median_dollar_volume_usd'] <= 0
            or not 0 <= contract['minimum_cash_buffer_usd'] < contract['portfolio_cash_usd']):
        raise ValueError('Invalid risk/cost/cash/liquidity contract')
    universe = inputs['universe']
    if not set(IDENTITY_FIELDS) <= set(universe):
        raise ValueError('Complete identity/risk/price/liquidity universe required')
    for key in IDENTITY_FIELDS[:4]:
        if not universe[key].map(lambda x: type(x) is str and bool(x) and x == x.strip()).all():
            raise ValueError('Canonical nonempty universe identity required')
    if universe.security_id.duplicated().any():
        raise ValueError('Duplicate universe SID')
    values = validation._numeric_values(universe[['synthetic_price', 'median_dollar_volume_usd']], 'universe')
    if (values <= 0).any() or not set(tickers) <= set(universe.ticker):
        raise ValueError('Invalid price/liquidity or candidate outside universe')
    incumbent = inputs['incumbent_weights']
    if (type(incumbent) is not dict or not incumbent
            or any(type(t) is not str or not t or t != t.strip().upper()
                   or type(w) not in (int, float) or not math.isfinite(w) or w < 0 for t, w in incumbent.items())
            or abs(sum(incumbent.values()) - 1.) > 1e-10):
        raise ValueError('Explicit normalized incumbent required')
    if (not isinstance(inputs['target_returns'], pd.Series)
            or not set(tickers) | set(incumbent) <= set(inputs['returns'])
            or not set(tickers) <= set(inputs['nominal_prices'])
            or (inputs['nominal_prices'].to_numpy() <= 0).any()):
        raise ValueError('Missing numeric columns or invalid nominal prices')


def _panel(frame, columns=None):
    if isinstance(frame, pd.Series):
        frame = frame.to_frame('value')
    elif columns is not None:
        frame = frame.loc[:, columns]
    return dict(dates=[str(day.date()) for day in frame.index], columns=list(frame.columns),
                dtypes=[str(value) for value in frame.dtypes],
                values=[[float(value).hex() for value in row] for row in frame.to_numpy()])


def candidate_numerical_input_fingerprint(*, task, inputs, engine, source_hashes, runtime):
    """Bind a sufficient dependency projection, conservatively including prices.

    Runtime records are compared, not authenticated. Input-to-file provenance and
    old result validity need separate verified readback; this function hashes the
    actual supplied typed inputs and never declares those external gates passed.
    """
    task, inputs, source_hashes, runtime = deepcopy((task, inputs, source_hashes, runtime))
    _verify(LOADED)
    _verify(source_hashes)
    numerical = numerical_source_hashes(engine)
    if any(source_hashes.get(path) != digest for path, digest in numerical.items()):
        raise ValueError('Original numerical source closure must be explicitly bound')
    if (type(runtime) is not dict or set(runtime) != {'python', 'numpy', 'pandas', 'scipy'}
            or any(type(value) is not str or not value or value != value.strip() for value in runtime.values())):
        raise ValueError('Explicit original four-library runtime record required')
    keys = {'tickers', 'holding_count', 'weight_spec', 'selection_date', 'decision_data_end',
            'source_batch', 'universe_track'}
    if type(task) is not dict or not keys <= set(task):
        raise ValueError('Explicit complete candidate coordinate required')
    if (engine == 'equal_weight_fractional_v1') != (task['weight_spec'] == 'equal_weight'):
        raise ValueError('Weight specification and engine differ')
    full = semantics.training_semantics(inputs=inputs, decision_data_end=task['decision_data_end'],
        source_batch=task['source_batch'], universe_track=task['universe_track'])
    _validate_without_evaluation(task, inputs)
    tickers = task['tickers'].split(';')
    for field in ('selection_date', 'decision_data_end'):
        if type(task[field]) is not str or str(pd.Timestamp(task[field]).date()) != task[field]:
            raise ValueError('Canonical candidate dates required')
    for panel in ('returns', 'nominal_prices'):
        if any(type(t) is not str or not t or t != t.strip().upper() for t in inputs[panel].columns):
            raise ValueError('Canonical panel ticker columns required')
    if any(t != t.strip().upper() for t in tickers):
        raise ValueError('Canonical selected tickers required')
    if (inputs['returns'].to_numpy() <= -1).any() or (inputs['target_returns'].to_numpy() <= -1).any():
        raise ValueError('Return input must exceed minus one')
    universe = inputs['universe'].set_index('ticker', drop=False)
    selected = universe.loc[tickers, list(IDENTITY_FIELDS)]
    if selected.issuer_id.duplicated().any():
        raise ValueError('Candidate contains repeated issuer')
    starts = list(range(inputs['contract']['fit_days'],
        len(inputs['returns']) - inputs['contract']['window_days'] + 1, inputs['contract']['step_days']))
    if not starts:
        raise ValueError('No evaluation windows')
    if engine != 'equal_weight_fractional_v1' and inputs['contract']['fit_days'] < max(20, 3 * len(tickers)):
        raise ValueError('Insufficient non-equal fitting history')
    used = sorted(set(tickers) | set(inputs['incumbent_weights']))
    payload = dict(schema='ndx_candidate_numerical_input_projection_v1', engine=engine,
        coordinate={key: task[key] for key in ('tickers', 'holding_count', 'weight_spec',
                                               'selection_date', 'decision_data_end')},
        selected_identity_risk_liquidity_price=selected.to_dict('records'),
        contract=inputs['contract'], runtime=runtime, numerical_sources=numerical,
        # Preserve order: Python normalization sums can depend on insertion order.
        incumbent_weights=list(inputs['incumbent_weights'].items()),
        returns=_panel(inputs['returns'], used), target_returns=_panel(inputs['target_returns']),
        nominal_prices=_panel(inputs['nominal_prices'], tickers), window_offsets=starts)
    _verify(source_hashes)
    _verify(LOADED)
    return dict(schema='ndx_candidate_numerical_input_fingerprint_research_v1',
        numerical_input_sha256=_digest(payload), payload=payload,
        full_training_semantics=full, source_hashes=source_hashes | LOADED,
        dependency_projection='SUFFICIENT_CONSERVATIVE_NOT_MINIMAL_NECESSARY',
        entire_supplied_input_validation_passed=True,
        omitted_unselected_return_columns=sorted(set(inputs['returns']) - set(used)),
        retained_prices_reason='CONSERVATIVE_VALIDATION_AND_DISCARDED_FLOOR_DIAGNOSTICS_DEPENDENCY',
        runtime_record_authenticated=False, source_to_typed_input_linkage_verified=False,
        historical_result_verified=False, candidate_membership_verified=False,
        price_identity_authenticated=False, point_in_time_verified=False,
        result_reuse_authorized=False, execution_performed=False, promotion_allowed=False)


def compare_candidate_numerical_inputs(*, left, right):
    """Rebuild both fingerprints from complete inputs, never trust claimed hashes."""
    before = candidate_numerical_input_fingerprint(**left)
    after = candidate_numerical_input_fingerprint(**right)
    _verify(before['source_hashes'])
    _verify(after['source_hashes'])
    changed = sorted(key for key in before['payload'] if before['payload'][key] != after['payload'][key])
    return dict(schema='ndx_candidate_numerical_input_equivalence_research_v1',
        numerical_input_equivalent=not changed, changed_dependency_fields=changed,
        left=before, right=after,
        full_training_semantics_equal=before['full_training_semantics'] == after['full_training_semantics'],
        prior_results_reused=False, result_reuse_authorized=False, point_in_time_verified=False,
        global_search_completeness_verified=False, whole_lot_result_reuse_allowed=False,
        new_scope_membership_verified=False, execution_performed=False, promotion_allowed=False)
