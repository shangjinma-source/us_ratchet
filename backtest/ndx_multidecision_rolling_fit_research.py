"""Thirteen causal inner fits through the unchanged certified V3 closure."""
from copy import deepcopy
from datetime import date
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from backtest import ndx_joint_weight_evaluation_v2 as binding
from backtest import ndx_joint_weight_evaluation_v3 as v3
from backtest import ndx_multidecision_window_scoring_research as numeric


SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
NUMERIC_LOADED_SHA = hashlib.sha256(Path(numeric.__file__).read_bytes()).hexdigest()
SPECS = ('equal_weight', 'constrained_fixed_shrinkage', 'constrained_fixed_shrinkage_turnover_anchor')
PARAMETERS = dict(shrinkage_intensity=.35, max_single_weight=.45, min_single_weight=.05,
                  top_weight_cap=.8, minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55)


def source_hashes():
    v3._validate_loaded_sources()
    numeric_path = Path(numeric.__file__).resolve()
    result = {str(v3.ROOT / name): value for name, value in v3._LOADED_SOURCES.items()}
    result.update({str(SOURCE): hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                   str(numeric_path): hashlib.sha256(numeric_path.read_bytes()).hexdigest()})
    numeric.require(result[str(SOURCE)] == LOADED_SHA, 'Rolling fitter source drift')
    numeric.require(result[str(numeric_path)] == NUMERIC_LOADED_SHA, 'Loaded numeric helper drift')
    return result


def prepare_panel(cutoff, return_dates, securities, candidate_returns, weight_spec):
    numeric.require(weight_spec in SPECS, 'Registered weight specification')
    numeric.require(type(return_dates) is list and len(return_dates) == 504
                    and return_dates == sorted(set(return_dates)) and return_dates[-1] == cutoff,
                    'Exactly 504 ordered returns ending at cutoff')
    for value in return_dates:
        numeric.require(type(value) is str and date.fromisoformat(value).isoformat() == value
                        and date.fromisoformat(value).weekday() < 5, 'Canonical weekday')
    numeric.require(type(securities) is list and bool(securities), 'Explicit securities')
    for security in securities:
        numeric.require(type(security) is dict and set(security) ==
                        {'security_id', 'ticker', 'issuer_id', 'risk_chain'}, 'Exact identity/risk fields')
        numeric.require(all(type(value) is str and value and value == value.strip()
                            for value in security.values()), 'Canonical identity/risk text')
    for key in ('security_id', 'ticker', 'issuer_id'):
        numeric.require(len({security[key] for security in securities}) == len(securities),
                        'Unique security, ticker and issuer')
    numeric.require(type(candidate_returns) is list and len(candidate_returns) == 504,
                    'Complete candidate matrix')
    return pd.DataFrame([numeric.vector(row, len(securities), returns=True) for row in candidate_returns],
                        index=pd.DatetimeIndex(return_dates), columns=[s['ticker'] for s in securities])


def fit_windows_with_fitter(frame, securities, weight_spec, fitter):
    """Internal worker: preserve the legacy inner prior, including first anchor."""
    tickers = tuple(s['ticker'] for s in securities)
    chains = {s['ticker']: s['risk_chain'] for s in securities}
    rows = []
    previous = None
    for index in range(13):
        start = index * 21 + 126
        history = frame.iloc[start - 126:start]
        anchored = weight_spec == 'constrained_fixed_shrinkage_turnover_anchor'
        if weight_spec == 'equal_weight':
            weights = pd.Series(1. / len(tickers), index=list(tickers), dtype=float)
        else:
            # None with strength .25 deliberately invokes the old equal anchor.
            weights = fitter(history, tickers, **PARAMETERS, risk_chain_by_ticker=chains,
                             anchor_weights=previous if anchored else None,
                             turnover_anchor_strength=.25 if anchored else 0.)
        numeric.require(isinstance(weights, pd.Series) and list(weights.index) == list(tickers),
                        'Exact fitted column order')
        values = numeric.vector(weights.tolist(), len(tickers))
        numeric.require(min(values) >= 0 and math.isclose(sum(values), 1., abs_tol=1e-9, rel_tol=0),
                        'Valid fitted simplex')
        payload = dict(dates=[value.date().isoformat() for value in history.index],
                       tickers=list(tickers), returns=history.to_numpy().tolist())
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        rows.append(dict(window_index=index, fit_first_return_end=payload['dates'][0],
                         fit_last_return_end=payload['dates'][-1],
                         evaluation_first_return_end=frame.index[start].date().isoformat(),
                         evaluation_last_return_end=frame.index[start + 125].date().isoformat(),
                         fit_data_sha256=hashlib.sha256(encoded).hexdigest(),
                         weights=values, projection_relaxed=bool(weights.attrs.get('risk_chain_projection_relaxed', False)),
                         requested_inner_prior=None if previous is None else previous.to_dict(),
                         fitter_anchor_used=None if not anchored or previous is None else previous.to_dict(),
                         fitter_anchor_strength=.25 if anchored else 0.))
        previous = weights
    return rows


def fit_causal_scoring_windows(*, cutoff, return_dates, securities, candidate_returns, weight_spec):
    """Numerical research operation; external registered executor authenticates data."""
    sources = source_hashes()
    frame = prepare_panel(cutoff, return_dates, securities, candidate_returns, weight_spec)
    captured, calls = [], []
    def private_bind(function, **dependencies):
        if function is binding._PORTFOLIO:
            captured.append(dependencies['constrained_fixed_shrinkage_weights'])
        elif function is binding._EVALUATE:
            numeric.require(len(captured) == 1, 'Exactly one private certified fitter')
            def evaluate(unused_task, **unused_inputs):
                numeric.require(unused_task is None and not unused_inputs, 'No legacy task execution')
                calls.append(True)
                return fit_windows_with_fitter(frame, securities, weight_spec, captured[0])
            return evaluate
        return binding._bind(function, **dependencies)
    proxy = SimpleNamespace(**dict(vars(binding), _bind=private_bind))
    reconstructed = binding._bind(v3.probe.evaluate_reconstructed, evaluator=proxy)
    try:
        result = reconstructed(None, {})
        numeric.require(len(calls) == len(captured) == 1, 'One private rolling operation')
        return dict(schema='MULTIDECISION_CAUSAL_ROLLING_FITS_V1', cutoff=cutoff,
                    securities=deepcopy(securities), weight_spec=weight_spec,
                    windows=result['result'], reconstruction_attempts=result['reconstruction_attempts'],
                    numerical_projection='V3_CERTIFIED_RECOVERY_ORIGINAL_PROBE_CLOSURE',
                    inner_prior_policy='FIRST_NONE_THEN_SAME_CANDIDATE_PREVIOUS_TARGET',
                    source_hashes=sources, source_bytes_authenticated=False,
                    outer_lane_prior_applied=False, fit_performed=weight_spec != 'equal_weight',
                    score_computed=False, point_in_time_verified=False,
                    account_executed=False, promotion_allowed=False)
    finally:
        numeric.require(source_hashes() == sources, 'Source drift during rolling fitting')
