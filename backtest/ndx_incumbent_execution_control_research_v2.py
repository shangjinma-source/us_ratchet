"""Fixed incumbent weights under the same split-aware next-close mechanism.

The private function binding changes allocation eligibility only for this
explicit CONTROL role. The candidate simulator and its globals stay untouched.
Risk is still measured each day but cannot erase the control's economic path.
"""
import hashlib
from pathlib import Path
from types import FunctionType

from backtest import ndx_next_session_execution_research_v2 as execution
from backtest.ndx_incumbent_integer_control_research_v2 import search_incumbent_integer_control_domain_v2

_PATHS = (*execution._PATHS, Path(__file__).resolve(),
          Path(__file__).with_name('ndx_incumbent_integer_control_research_v2.py'),
          Path(__file__).with_name('ndx_exact_pareto_frontier_research.py'))


def _hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in _PATHS}


_LOADED_SOURCES = _hashes()
_GLOBALS = dict(execution.simulate_next_session_execution_research_v2.__globals__)
_GLOBALS.update(_hashes=_hashes, _LOADED_SOURCES=_LOADED_SOURCES,
    search_integer_allocation_domain=search_incumbent_integer_control_domain_v2)
_RUN = FunctionType(execution.simulate_next_session_execution_research_v2.__code__, _GLOBALS)


def simulate_fixed_weight_incumbent_control_v2(*, prices, execution_calendar, decision_dates,
        incumbent_weights, corporate_actions, initial_cash, initial_shares,
        minimum_cash_buffer_usd, transaction_cost_bps, risk_chain_by_ticker,
        constraints, domain_radius, max_evaluations_per_rebalance):
    """Targets are frozen across every declared decision, never reprojected.

    The financial search uses tracking first, never fee-first idle cash as the
    default control. Compare with candidate TRACKING_FIRST, not a different
    execution policy. This does not authenticate risk labels or split sources.
    """
    if not isinstance(decision_dates, (list, tuple)) or not decision_dates:
        raise ValueError('Explicit nonempty control decision dates required')
    if not isinstance(incumbent_weights, dict) or not incumbent_weights:
        raise ValueError('Explicit original incumbent weights required')
    if execution._hashes() != execution._LOADED_SOURCES:
        raise ValueError('Execution dependency changed since original import')
    result = _RUN(prices=prices, execution_calendar=execution_calendar,
        schedule=[(d, dict(incumbent_weights)) for d in decision_dates],
        corporate_actions=corporate_actions, initial_cash=initial_cash, initial_shares=initial_shares,
        minimum_cash_buffer_usd=minimum_cash_buffer_usd, transaction_cost_bps=transaction_cost_bps,
        risk_chain_by_ticker=risk_chain_by_ticker, constraints=constraints, domain_radius=domain_radius,
        max_evaluations_per_rebalance=max_evaluations_per_rebalance, selection_policy='TRACKING_FIRST')
    result.update(schema='ndx_incumbent_execution_control_research_v2', role='INCUMBENT_CONTROL',
        incumbent_target_weights=dict(incumbent_weights), target_weights_projected=False,
        candidate_eligibility=False, allocation_risk_constraints_enforced=False,
        risk_constraint_role='OBSERVATIONAL_ONLY_NOT_CANDIDATE_ADMISSION',
        matched_candidate_execution_policy='TRACKING_FIRST', promotion_allowed=False)
    if execution._hashes() != execution._LOADED_SOURCES or _hashes() != _LOADED_SOURCES:
        raise ValueError('Control sources changed during execution')
    return result


