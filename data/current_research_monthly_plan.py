"""Pure explicit monthly routing to reselection or frozen-target DAY roll."""
from copy import deepcopy

from backtest.return_priority_fresh_cash_quantity_search import search_fresh_cash_quantities
from data.current_research_fill_ledger import review_paper_ledger
from data.current_research_monthly_policy import route_monthly_research_policy
from data.current_research_successor_plan import build_research_successor_plan, roll_research_plan, _capital_method, QUANTITY_METHOD, TOP1_METHOD, decide_top1_for_account, decide_quantity_for_account


def build_monthly_research_plan(state, *, expected_revision, decision_date, active_date,
                                calendar, valuation_quotes, source_hashes, held_unit_continuity,
                                market_session, search_arguments=None,
                                search=search_fresh_cash_quantities, capital_decision=None):
    """No activation or month commit. Requires an already bound target month."""
    reviewed = review_paper_ledger(state)
    if expected_revision != reviewed['revision']:
        raise ValueError('STALE_ACCOUNT_REVISION')
    snapshot = state['plan']['causal_inputs']['research_snapshot']
    saved_method = snapshot.get('selection_method', QUANTITY_METHOD)
    adapters = {QUANTITY_METHOD: decide_quantity_for_account, TOP1_METHOD: decide_top1_for_account}
    if saved_method not in adapters:
        raise ValueError('UNKNOWN_SAVED_SELECTION_METHOD')
    if capital_decision is None:
        capital_decision = adapters[saved_method]
    _, requested_method = _capital_method(capital_decision, search)
    current_month = state['plan']['causal_inputs']['research_snapshot'].get('target_month')
    if current_month is None:
        raise ValueError('BOUND_TARGET_MONTH_REQUIRED_NO_INFERENCE')
    route = route_monthly_research_policy(decision_date=decision_date, active_date=active_date,
        calendar=calendar, current_target_month=current_month)
    parameters = dict(expected_revision=expected_revision, decision_date=decision_date,
        active_date=active_date, calendar=calendar, valuation_quotes=valuation_quotes,
        source_hashes=source_hashes, held_unit_continuity=held_unit_continuity,
        target_month=route['target_month'], market_session=market_session)
    if route['action'] == 'RESELECT':
        if search_arguments is None:
            raise ValueError('RESELECT_ARGUMENTS_REQUIRED')
        result = build_research_successor_plan(state, search_arguments=search_arguments,
                                               search=search, capital_decision=capital_decision, **parameters)
    else:
        saved_method = state['plan']['causal_inputs']['research_snapshot'].get('selection_method', QUANTITY_METHOD)
        if capital_decision is not None and requested_method != saved_method:
            raise ValueError('ROLL_CANNOT_CHANGE_SELECTION_METHOD')
        result = roll_research_plan(state, **parameters)
    return dict(result, route=deepcopy(route), target_month=route['target_month'],
                market_session=deepcopy(market_session), activation_performed=False)
