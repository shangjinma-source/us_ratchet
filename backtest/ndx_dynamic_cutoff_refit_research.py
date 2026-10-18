"""One-decision latest-cutoff refit; never reuse checkpoint last-fit weights."""
from collections.abc import Mapping
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from backtest import ndx_joint_weight_evaluation_v2 as evaluation

_SOURCE = Path(__file__).resolve()
_LOADED_SHA = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()


def _date(value):
    if not isinstance(value, (str, pd.Timestamp)):
        raise ValueError('Canonical session date required')
    date = pd.Timestamp(value)
    if pd.isna(date) or date.tzinfo is not None or date != date.normalize():
        raise ValueError('Canonical session date required')
    if isinstance(value, str) and value != date.date().isoformat():
        raise ValueError('Canonical YYYY-MM-DD required')
    return date


def _number(value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError('Finite numeric value required')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Finite numeric value required')
    return value


def _canonical(value):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError('Canonical identity string required')
    return value


def _sources():
    if (evaluation.source_hashes() != evaluation._LOADED_SOURCES
            or hashlib.sha256(_SOURCE.read_bytes()).hexdigest() != _LOADED_SHA):
        raise ValueError('Cutoff refit source drift')
    return {str(evaluation.ROOT / key): value for key, value in evaluation._LOADED_SOURCES.items()} | {str(_SOURCE): _LOADED_SHA}


def refit_dynamic_cutoff_weights(*, returns, cutoff, selected, weight_spec,
        previous_target_weights=None, fit_days=126, shrinkage_intensity=.35,
        turnover_anchor_strength=.25, max_single_weight=.45, min_single_weight=.05,
        top_weight_cap=.8, minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55):
    """Use the last fit_days rows ending exactly at the declared cutoff.

    Prior targets are a security_id weight mapping. Surviving positive mass is
    renormalized, new entries receive zero. No prior/zero surviving mass disables
    the anchor, rather than triggering the legacy fitter's uniform fallback.
    Returned risk observations describe ORIGINAL declared bounds, including
    true Top-3 for small k; solver envelope relaxation never implies admission.
    """
    sources = _sources()
    if weight_spec not in ('equal_weight', 'constrained_fixed_shrinkage', 'constrained_fixed_shrinkage_turnover_anchor'):
        raise ValueError('Explicit supported weight_spec required')
    cutoff = _date(cutoff)
    if type(fit_days) is not int or fit_days < 20:
        raise ValueError('fit_days must be an integer at least 20')
    if not isinstance(returns, pd.DataFrame) or returns.empty or not returns.columns.is_unique:
        raise ValueError('Unique nonempty returns panel required')
    dates = [_date(value) for value in returns.index]
    if dates != sorted(set(dates)) or dates[-1] != cutoff:
        raise ValueError('Returns must be unique ascending and end exactly at cutoff; future rows forbidden')
    if any(date > cutoff for date in dates):
        raise ValueError('Future returns forbidden')
    if len(dates) < fit_days:
        raise ValueError('Insufficient latest-cutoff fit history')
    for name in returns.columns:
        if _canonical(name) != name.upper():
            raise ValueError('Canonical ticker columns required')
    if not isinstance(selected, Mapping) or not selected:
        raise ValueError('Explicit selected security mapping required')
    securities = sorted(selected)
    tickers, issuers, chains = [], [], {}
    for security in securities:
        _canonical(security)
        item = selected[security]
        if not isinstance(item, Mapping) or set(item) != {'ticker', 'issuer_id', 'risk_chain'}:
            raise ValueError('Exact selected identity/risk schema required')
        ticker, issuer, chain = (_canonical(item[key]) for key in ('ticker', 'issuer_id', 'risk_chain'))
        if ticker != ticker.upper() or ticker not in returns:
            raise ValueError('Selected ticker missing or noncanonical')
        tickers.append(ticker); issuers.append(issuer); chains[ticker] = chain
    if len(set(tickers)) != len(tickers) or len(set(issuers)) != len(issuers):
        raise ValueError('Selected ticker and issuer identities must be unique')
    values = np.array([[_number(value) for value in row] for row in returns.to_numpy()], dtype=float)
    if np.any(values <= -1.):
        raise ValueError('Returns must exceed -100 percent for surviving priced securities')
    frame = pd.DataFrame(values[-fit_days:], index=pd.DatetimeIndex(dates[-fit_days:]), columns=returns.columns)[tickers]
    parameters = dict(shrinkage_intensity=_number(shrinkage_intensity),
        turnover_anchor_strength=_number(turnover_anchor_strength), max_single_weight=_number(max_single_weight),
        min_single_weight=_number(min_single_weight), top_weight_cap=_number(top_weight_cap),
        minimum_effective_n_ratio=_number(minimum_effective_n_ratio), risk_chain_top1_cap=_number(risk_chain_top1_cap))
    if (not all(0 <= value <= 1 for value in parameters.values())
            or parameters['min_single_weight'] > parameters['max_single_weight']
            or parameters['risk_chain_top1_cap'] <= 0):
        raise ValueError('Invalid declared refit envelope')
    previous = {}
    if previous_target_weights is not None:
        if not isinstance(previous_target_weights, Mapping) or not previous_target_weights:
            raise ValueError('Prior targets must be a nonempty mapping or None')
        previous = {_canonical(key): _number(value) for key, value in previous_target_weights.items()}
        if any(value < 0 for value in previous.values()) or not math.isclose(sum(previous.values()), 1., abs_tol=1e-12, rel_tol=0):
            raise ValueError('Prior target weights must be nonnegative and sum to one')
    surviving_mass = sum(previous.get(key, 0.) for key in securities)
    anchor = {key: previous.get(key, 0.) / surviving_mass if surviving_mass > 0 else 0. for key in securities}
    strength = (parameters['turnover_anchor_strength'] if surviving_mass > 0
                and weight_spec == 'constrained_fixed_shrinkage_turnover_anchor' else 0.)
    effective = dict(parameters, turnover_anchor_strength=strength)
    if weight_spec == 'equal_weight':
        fitted = pd.Series(1./len(tickers), index=tickers)
    else:
        fitted = evaluation._SHRINKAGE(frame, tuple(tickers), risk_chain_by_ticker=chains,
            anchor_weights=pd.Series({selected[key]['ticker']: value for key, value in anchor.items()})
                if surviving_mass > 0 else None, **effective)
    weights = {key: float(fitted[selected[key]['ticker']]) for key in securities}
    if any(not math.isfinite(value) or value < 0 for value in weights.values()) or not math.isclose(sum(weights.values()),1.,abs_tol=1e-9,rel_tol=0):
        raise ValueError('Invalid fitted simplex')
    ordered = sorted(weights.values(), reverse=True)
    group = {}
    for key, value in weights.items():
        chain = selected[key]['risk_chain']; group[chain] = group.get(chain,0.) + value
    effective_n = 1. / sum(value * value for value in weights.values())
    checks = dict(MAX_SINGLE_WEIGHT=ordered[0] <= parameters['max_single_weight'] + 1e-9,
        MIN_SINGLE_WEIGHT=ordered[-1] >= parameters['min_single_weight'] - 1e-9,
        SECURITY_TOP3_WEIGHT=sum(ordered[:3]) <= parameters['top_weight_cap'] + 1e-9,
        MINIMUM_EFFECTIVE_N=effective_n >= len(weights)*parameters['minimum_effective_n_ratio']-1e-9,
        RISK_CHAIN_TOP1_WEIGHT=max(group.values()) <= parameters['risk_chain_top1_cap']+1e-9)
    payload = dict(dates=[date.date().isoformat() for date in frame.index], tickers=tickers,
                   returns=frame.to_numpy().tolist())
    _sources()
    return dict(schema='ndx_dynamic_cutoff_refit_research_v1', weight_spec=weight_spec, cutoff=cutoff.date().isoformat(),
        fit_start=payload['dates'][0], fit_end=payload['dates'][-1], fit_row_count=len(frame),
        fit_data_sha256=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
        targets={key: dict(ticker=selected[key]['ticker'], issuer_id=selected[key]['issuer_id'], target_weight=weights[key]) for key in securities},
        risk_chains_by_security={key:selected[key]['risk_chain'] for key in securities},
        previous_target_weights=previous, surviving_anchor_mass=surviving_mass,
        anchor_by_security=anchor, effective_anchor_strength=strength,
        anchor_policy='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED',
        declared_parameters=parameters, declared_constraint_checks=checks, declared_constraints_passed=all(checks.values()),
        risk_chain_projection_relaxed=bool(fitted.attrs.get('risk_chain_projection_relaxed',False)),
        single_name_projection_relaxed=weight_spec!='equal_weight' and parameters['max_single_weight'] < 1./len(weights),
        top3_projection_semantics_relaxed=weight_spec!='equal_weight' and (len(weights)<=3 or parameters['top_weight_cap'] < min(3,len(weights)-1)/len(weights)),
        checkpoint_weights_used=False, point_in_time_verified=False, source_authenticity_verified=False,
        promotion_allowed=False, source_hashes=sources)
