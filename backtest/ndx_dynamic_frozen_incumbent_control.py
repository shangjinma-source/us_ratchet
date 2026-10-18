"""Fixed-weight incumbent control using the candidate's Close-to-Open clock.

The private engine binding uses financial feasibility to control orders, while
every returned risk snapshot is the actual observed risk (never a fake pass).
It does not change the candidate module, caller schedule, or original weights.
"""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
from types import FunctionType, SimpleNamespace

from backtest import ndx_dynamic_frozen_execution_research as candidate

_SOURCE = Path(__file__).resolve()
_LOADED_SHA = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()


def _sources():
    candidate._check_sources()
    if hashlib.sha256(_SOURCE.read_bytes()).hexdigest() != _LOADED_SHA:
        raise ValueError('Loaded incumbent control source drift')


def _financial_snapshot(counts, marks, chains, **constraints):
    if set(counts) != set(marks) or set(counts) != set(chains):
        raise ValueError('Control risk identity mismatch')
    valid = all(type(value) is int and value >= 0 for value in counts.values())
    positive = {key: value for key, value in counts.items() if value > 0}
    observed = (candidate.repair._risk_snapshot(positive,
        {key: marks[key] for key in positive}, {key: chains[key] for key in positive}, **constraints)
        if positive else {'all_passed': False, 'checks': {'ALL_CASH': False}})
    observed.update(target_slot_count=len(counts), positive_holding_count=len(positive),
                    zero_share_security_ids=sorted(key for key, value in counts.items() if value == 0))
    # This object exists only inside the private control binding. Before return,
    # _restore_observations exposes the actual risk and explicit financial checks.
    return dict(all_passed=valid, checks={'NONNEGATIVE_WHOLE_SHARES': valid},
                __control_observed_risk=observed)


def _financial_projection(**arguments):
    """Fee-only share reduction; no risk projection and no weight modification."""
    before = arguments['current_shares']
    marks = arguments['prices']
    cash = arguments['current_cash_usd']
    buffer = arguments['minimum_cash_buffer_usd']
    rate = arguments['transaction_cost_bps'] / 10000.
    investable = cash + sum(before[key] * marks[key] for key in before) - buffer
    wanted = {key: math.floor(investable * arguments['target_weights'][key] / marks[key])
              for key in before}
    if any(value < 0 for value in wanted.values()):
        raise ValueError('Negative control floor shares')
    after_cash, *_ = candidate._cash_projection(cash, before, wanted, marks, rate)
    while after_cash < buffer - 1e-8:
        reducible = [key for key, quantity in wanted.items() if quantity > 0]
        if not reducible:
            return dict(search_complete=True, feasible_projection_found=False,
                        status='NO_FINANCIALLY_FEASIBLE_FLOOR_REDUCTION', projected_shares={})
        wanted[max(reducible, key=lambda key: (marks[key], key))] -= 1
        after_cash, *_ = candidate._cash_projection(cash, before, wanted, marks, rate)
    return dict(search_complete=True, feasible_projection_found=True,
                status='CONTROL_FINANCIAL_FLOOR_FEE_REDUCTION', projected_shares=wanted)


def _restore_observations(value):
    if isinstance(value, list):
        return [_restore_observations(item) for item in value]
    if not isinstance(value, dict):
        return value
    if '__control_observed_risk' in value:
        observed = deepcopy(value['__control_observed_risk'])
        observed['financial_allocation_checks'] = dict(value['checks'])
        observed['risk_is_order_gate'] = False
        return observed
    return {key: _restore_observations(item) for key, item in value.items()}


def _fixed_schedule_without_weight_normalization(rows):
    normalized = candidate.identity._normalise_schedule(rows)
    for raw, item in zip(rows, normalized):
        weights = {key: candidate.repair._finite(target['target_weight'], 'original weight')
                   for key, target in raw['targets'].items()}
        if not math.isclose(sum(weights.values()), 1., rel_tol=0., abs_tol=1e-12):
            raise ValueError('Original incumbent weights must already sum to one')
        for key, weight in weights.items():
            item['targets'][key]['target_weight'] = weight
    return normalized


def simulate_dynamic_frozen_incumbent_control(*, closes, opens, schedule,
        risk_chains_by_decision, corporate_actions, initial_cash_usd,
        minimum_cash_buffer_usd, valuation_end_date, transaction_cost_bps=10.,
        max_single_weight=.45, min_single_weight=.05, top_weight_cap=.8,
        minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55):
    """Accept any fixed disclosed control basket; caller supplies original eight.

    Positive targets that round to zero remain zero-share control slots; their
    absence is observed, not repaired by a candidate risk optimizer. No automatic
    replan, risk projection, renamed identities, or current live mutation.
    """
    _sources()
    rows = deepcopy(list(schedule))
    if not rows or any(row['targets'] != rows[0]['targets'] for row in rows):
        raise ValueError('Incumbent targets and original weights must remain fixed')
    original = candidate.simulate_dynamic_frozen_execution_research
    private_globals = dict(original.__globals__)
    proxy = dict(vars(candidate.repair))
    proxy['_risk_snapshot'] = _financial_snapshot
    identity_proxy = dict(vars(candidate.identity))
    identity_proxy['_normalise_schedule'] = _fixed_schedule_without_weight_normalization
    private_globals.update(repair=SimpleNamespace(**proxy),
        identity=SimpleNamespace(**identity_proxy),
        projector=SimpleNamespace(project_whole_lot_rebalance=_financial_projection),
        _check_sources=_sources)
    bound = FunctionType(original.__code__, private_globals, original.__name__,
                         original.__defaults__, original.__closure__)
    bound.__kwdefaults__ = dict(original.__kwdefaults__ or {})
    result = bound(closes=closes, opens=opens, schedule=rows,
        risk_chains_by_decision=risk_chains_by_decision, corporate_actions=corporate_actions,
        initial_cash_usd=initial_cash_usd, minimum_cash_buffer_usd=minimum_cash_buffer_usd,
        valuation_end_date=valuation_end_date, transaction_cost_bps=transaction_cost_bps,
        max_single_weight=max_single_weight, min_single_weight=min_single_weight,
        top_weight_cap=top_weight_cap, minimum_effective_n_ratio=minimum_effective_n_ratio,
        risk_chain_top1_cap=risk_chain_top1_cap, identity_events=[])
    result = _restore_observations(result)
    result.update(schema='ndx_dynamic_frozen_incumbent_control_v1',
        portfolio_track='fixed_incumbent_execution_control', risk_is_order_gate=False,
        candidate_eligibility_claimed=False, original_target_weights_modified=False,
        zero_share_target_slots_allowed=True)
    result['source_hashes'][str(_SOURCE)] = _LOADED_SHA
    result['summary']['all_cash_session_count'] = sum(
        not any(row['shares'].values()) for row in result['daily'])
    _sources()
    return result
