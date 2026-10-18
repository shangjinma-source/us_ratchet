"""Strict all-or-nothing refit schedule for an externally chosen research path.

The previous anchor is a strategic decision target, never actual fills or
holdings. Selection, price identity authentication and execution are external.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

import pandas as pd

from backtest import ndx_dynamic_cutoff_refit_v2_research as fitter

_SOURCE = Path(__file__).resolve()
_LOADED_SHA = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()
_RISK_PARAMETERS = ('max_single_weight', 'min_single_weight', 'top_weight_cap',
                    'minimum_effective_n_ratio', 'risk_chain_top1_cap')
_PARAMETERS = ('fit_days', 'shrinkage_intensity', 'turnover_anchor_strength', *_RISK_PARAMETERS)
_CHECKS = ('MAX_SINGLE_WEIGHT', 'MIN_SINGLE_WEIGHT', 'SECURITY_TOP3_WEIGHT',
           'MINIMUM_EFFECTIVE_N', 'RISK_CHAIN_TOP1_WEIGHT')
_PERIOD_KEYS = ('decision_date', 'execution_date', 'cutoff', 'returns', 'selected',
                'weight_spec', 'parameters', 'source_hashes')
_ANCHOR_POLICY = 'PREVIOUS_SUCCESSFUL_SCHEDULE_TARGET_BY_SID_REGARDLESS_OF_LATER_EXECUTION_STATUS'


class RefitScheduleError(ValueError):
    """Failure audit only: no partial schedule or replacement candidate."""
    def __init__(self, decision_date, stage, detail):
        self.audit = dict(decision_date=decision_date, stage=stage, detail=detail,
                          entire_schedule_rejected=True, partial_schedule_returned=False,
                          implicit_hold_or_cash_policy_applied=False, promotion_allowed=False)
        super().__init__(f'Refit schedule rejected at {decision_date}: {stage}: {detail}')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _day(value):
    if type(value) is not str or re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is None:
        raise ValueError('Canonical explicit session date required')
    return fitter.previous._date(value).date().isoformat()


def _validate_sources(sources):
    if type(sources) is not dict or not sources:
        raise ValueError('Explicit nonempty source closure required')
    for path, expected in sources.items():
        if (type(path) is not str or not Path(path).is_absolute()
                or type(expected) is not str or re.fullmatch('[0-9a-f]{64}', expected) is None):
            raise ValueError('Absolute source path and canonical SHA256 required')


def _verify(sources):
    _validate_sources(sources)
    for path, expected in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Schedule source drift: ' + path)


def _merge(*mappings):
    merged = {}
    for mapping in mappings:
        for path, digest in mapping.items():
            canonical = str(Path(path).resolve())
            if canonical in merged and merged[canonical] != digest:
                raise ValueError('Conflicting schedule source bindings')
            merged[canonical] = digest
    return merged


def _input_payload(period, calendar):
    frame = period['returns']
    if (not isinstance(frame, pd.DataFrame) or frame.empty or not frame.columns.is_unique
            or not isinstance(frame.index, pd.DatetimeIndex) or frame.index.hasnans
            or frame.index.tz is not None or not frame.index.is_unique or not frame.index.is_monotonic_increasing
            or not frame.index.equals(frame.index.normalize())):
        raise ValueError('Canonical ordered full returns panel required')
    return dict(decision_date=period['decision_date'], execution_date=period['execution_date'],
        cutoff=period['cutoff'], weight_spec=period['weight_spec'], selected=period['selected'],
        parameters=period['parameters'], source_hashes=period['source_hashes'],
        calendar_scope='EXPLICIT_EXECUTION_CALENDAR_NOT_VERIFIED_EXCHANGE_CALENDAR', calendar=calendar,
        returns=dict(dates=[day.date().isoformat() for day in frame.index], columns=list(frame.columns),
            values=[[fitter.previous._number(value) for value in row] for row in frame.to_numpy()]))


def _validate_refit(fitted, period, previous, numerical_sources):
    selected, parameters = period['selected'], period['parameters']
    expected_parameters = {key: fitter.previous._number(value) for key, value in parameters.items() if key != 'fit_days'}
    mass = sum((previous or {}).get(sid, 0.) for sid in sorted(selected))
    anchor = {sid: (previous or {}).get(sid, 0.) / mass if mass > 0 else 0. for sid in selected}
    strength = parameters['turnover_anchor_strength'] if mass > 0 and period['weight_spec'] == 'constrained_fixed_shrinkage_turnover_anchor' else 0.
    if (fitted['source_hashes'] != numerical_sources or fitted['cutoff'] != period['cutoff']
            or fitted['fit_end'] != period['cutoff'] or fitted['fit_row_count'] != parameters['fit_days']
            or fitted['fit_start'] != period['returns'].index[-parameters['fit_days']].date().isoformat()
            or fitted['declared_parameters'] != expected_parameters or fitted['weight_spec'] != period['weight_spec']
            or fitted['checkpoint_weights_used'] is not False or fitted['previous_target_weights'] != (previous or {})
            or fitted['risk_chains_by_security'] != {sid: value['risk_chain'] for sid, value in selected.items()}
            or fitted['surviving_anchor_mass'] != mass or fitted['effective_anchor_strength'] != strength
            or fitted['anchor_by_security'] != anchor or set(fitted['targets']) != set(selected)):
        raise ValueError('Cutoff, parameters, source, identity or strategic-target anchor differs')
    weights, chains = {}, {}
    for sid, target in fitted['targets'].items():
        if (type(target) is not dict or set(target) != {'ticker', 'issuer_id', 'target_weight'}
                or any(target[key] != selected[sid][key] for key in ('ticker', 'issuer_id'))):
            raise ValueError('Refit target identity differs')
        weight = fitter.previous._number(target['target_weight'])
        if weight <= 0:
            raise ValueError('Strictly positive schedule target required')
        weights[sid] = weight
        chain = selected[sid]['risk_chain']
        chains[chain] = chains.get(chain, 0.) + weight
    if not math.isclose(sum(weights.values()), 1., rel_tol=0., abs_tol=1e-9):
        raise ValueError('Refit target simplex differs')
    ordered = sorted(weights.values(), reverse=True)
    checks = dict(MAX_SINGLE_WEIGHT=ordered[0] <= parameters['max_single_weight'] + 1e-9,
        MIN_SINGLE_WEIGHT=ordered[-1] >= parameters['min_single_weight'] - 1e-9,
        SECURITY_TOP3_WEIGHT=sum(ordered[:3]) <= parameters['top_weight_cap'] + 1e-9,
        MINIMUM_EFFECTIVE_N=1. / sum(value * value for value in weights.values())
                            >= len(weights) * parameters['minimum_effective_n_ratio'] - 1e-9,
        RISK_CHAIN_TOP1_WEIGHT=max(chains.values()) <= parameters['risk_chain_top1_cap'] + 1e-9)
    if (fitted['declared_constraint_checks'] != checks
            or any(type(value) is not bool for value in fitted['declared_constraint_checks'].values())
            or type(fitted['declared_constraints_passed']) is not bool
            or fitted['declared_constraints_passed'] != all(checks.values())):
        raise ValueError('Refit five-risk checks disagree with independently measured target weights')
    return checks


def build_refit_schedule_research(*, calendar, decisions):
    """Refit every explicit decision or reject the entire schedule.

    Each decision has exactly _PERIOD_KEYS. Five risk parameters must agree
    across periods for the old executor's fixed risk contract. Fit length and
    shrinkage/anchor parameters are always explicit and may change by period.
    Cutoff may equal decision Close; execution must be the next supplied session.
    The supplied calendar and identity declarations are not authenticated here.
    """
    if type(calendar) is not list or not calendar or [_day(day) for day in calendar] != sorted(set(calendar)):
        raise ValueError('Explicit unique ascending calendar required')
    if type(decisions) not in (list, tuple) or not decisions:
        raise ValueError('Explicit nonempty ordered decision path required')
    calendar = deepcopy(calendar)
    periods = deepcopy(decisions)
    numerical_sources = fitter._sources()
    sources = _merge(numerical_sources, {str(_SOURCE): _LOADED_SHA})
    _verify(sources)
    positions = {day: index for index, day in enumerate(calendar)}
    input_digests, issuer_by_security = [], {}
    fixed_risk = None
    previous_execution = None
    previous_decision = None
    for period in periods:
        if type(period) is not dict or set(period) != set(_PERIOD_KEYS):
            raise ValueError('Exact per-decision schema required; no injected prior targets')
        day, execution, cutoff = (_day(period[key]) for key in ('decision_date', 'execution_date', 'cutoff'))
        if (day not in positions or execution not in positions or positions[execution] != positions[day] + 1
                or cutoff > day or (previous_decision is not None and day <= previous_decision)
                or (previous_execution is not None and day < previous_execution)):
            raise RefitScheduleError(day, 'INPUT_INVALID', 'Future cutoff, unordered decisions, overlap or non-next execution')
        previous_decision, previous_execution = day, execution
        parameters = period['parameters']
        if type(parameters) is not dict or set(parameters) != set(_PARAMETERS):
            raise RefitScheduleError(day, 'INPUT_INVALID', 'Eight original fit/risk parameters required')
        risk = {key: fitter.previous._number(parameters[key]) for key in _RISK_PARAMETERS}
        if fixed_risk is not None and risk != fixed_risk:
            raise RefitScheduleError(day, 'INPUT_INVALID', 'Risk contract changed across execution path')
        fixed_risk = risk
        selected = period['selected']
        if type(selected) is not dict or not selected:
            raise RefitScheduleError(day, 'INPUT_INVALID', 'Explicit selected SID identity mapping required')
        for security, item in selected.items():
            fitter.previous._canonical(security)
            if type(item) is not dict or set(item) != {'ticker', 'issuer_id', 'risk_chain'}:
                raise RefitScheduleError(day, 'INPUT_INVALID', 'Exact selected identity/risk schema required')
            for value in item.values():
                fitter.previous._canonical(value)
            if security in issuer_by_security and issuer_by_security[security] != item['issuer_id']:
                raise RefitScheduleError(day, 'INPUT_INVALID', 'Permanent SID issuer identity changed')
            issuer_by_security[security] = item['issuer_id']
        _validate_sources(period['source_hashes'])
        sources = _merge(sources, period['source_hashes'])
        input_digests.append(_digest(_input_payload(period, calendar)))
    _verify(sources)
    previous = None
    schedule, risk_chains, refits = [], {}, []
    for period, input_digest in zip(periods, input_digests):
        day = period['decision_date']
        before = deepcopy(previous)
        try:
            fitted = fitter.refit_dynamic_cutoff_weights(returns=period['returns'], cutoff=period['cutoff'],
                selected=period['selected'], weight_spec=period['weight_spec'], previous_target_weights=before,
                **period['parameters'])
        except (ValueError, ArithmeticError, RuntimeError) as error:
            _verify(sources)
            raise RefitScheduleError(day, 'REFIT_ERROR_NOT_ECONOMIC_INFEASIBILITY', str(error)) from error
        finally:
            _verify(_merge(numerical_sources, {str(_SOURCE): _LOADED_SHA}))
            if fitter._sources() != numerical_sources:
                raise ValueError('Numerical source closure changed')
        try:
            checks = _validate_refit(fitted, period, before, numerical_sources)
        except (ValueError, KeyError, TypeError, IndexError) as error:
            _verify(sources)
            raise RefitScheduleError(day, 'INVALID_REFIT_RESULT', str(error)) from error
        if not all(checks.values()):
            _verify(sources)
            raise RefitScheduleError(day, 'ORIGINAL_FIVE_RISKS_FAILED', [key for key, passed in checks.items() if not passed])
        previous = {sid: target['target_weight'] for sid, target in fitted['targets'].items()}
        schedule.append(dict(decision_date=day, execution_date=period['execution_date'], targets=deepcopy(fitted['targets'])))
        risk_chains[day] = deepcopy(fitted['risk_chains_by_security'])
        refits.append(dict(decision_date=day, execution_date=period['execution_date'], input_sha256=input_digest,
            source_set_sha256=_digest(_merge(numerical_sources, {str(_SOURCE): _LOADED_SHA}, period['source_hashes'])),
            previous_schedule_target_by_security=before,
            result={key: value for key, value in fitted.items() if key != 'source_hashes'}))
    _verify(sources)
    return dict(schema='ndx_dynamic_refit_schedule_research_v1', schedule=schedule,
        risk_chains_by_decision=risk_chains, refits=refits, source_hashes=sources,
        decision_count=len(periods), submitted_decision_count=len(decisions),
        submitted_decision_path_complete=True, external_expected_decision_denominator_verified=False,
        fixed_risk_parameters=fixed_risk,
        calendar=calendar, calendar_sha256=_digest(calendar),
        calendar_scope='EXPLICIT_EXECUTION_CALENDAR_NOT_VERIFIED_EXCHANGE_CALENDAR',
        schedule_input_sha256=_digest(input_digests), target_anchor_policy=_ANCHOR_POLICY,
        anchor_uses_actual_fills_or_holdings=False, later_execution_failure_resets_target_anchor=False,
        failure_policy='ANY_INVALID_INPUT_REFIT_ERROR_OR_FIVE_RISK_FAILURE_REJECTS_ENTIRE_SCHEDULE',
        partial_schedule_allowed=False, implicit_hold_or_cash_policy_applied=False,
        externally_supplied_selection_path=True, selector_execution_performed=False, unique_selection_performed=False,
        decision_ticker_authenticity_verified=False, downstream_price_identity_bridge_required=True,
        technology_scope_verified=False, point_in_time_verified=False, source_authenticity_verified=False,
        execution_performed=False, order_generation_allowed=False, whole_lot_status='NOT_EVALUATED',
        promotion_allowed=False, portfolio_track='portfolio_optimization')
