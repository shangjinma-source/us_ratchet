"""Pure V2 display projection; no search, source loading, API mounting or orders."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json

from data.current_quantity_portfolio_research import project
from data.current_research_capital_decision_v2 import VERSION


def project_capital_decision_v2(decision):
    result = decision['search_result']
    binding = decision['binding']
    if (decision.get('method') != VERSION or result.get('method_version') != VERSION
            or binding.get('selection_method') != VERSION
            or binding.get('schema') != 'CAPITAL_DECISION_MECHANIC_V2'):
        raise ValueError('V2 display method binding mismatch')
    complete = result.get('selected') is not None
    allowed = ('BUDGET_STOPPED', 'PER_K_SEARCH_STOPPED_WITH_UNUSED_BUDGET') if complete else (
        'INSUFFICIENT_BUDGET_FOR_MANDATORY_COVERAGE',)
    if result.get('status') not in allowed:
        raise ValueError('V2 display status mismatch')
    identifier = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    if decision.get('decision_id') != identifier or decision.get('research_id') != identifier[:24]:
        raise ValueError('V2 display decision identity mismatch')
    target = result['selected']['quantities'] if complete else None
    supplied_target = decision.get('target_quantities')
    if supplied_target != target or (supplied_target is not None and (
            not isinstance(supplied_target, dict) or any(type(q) is not int for q in supplied_target.values()))):
        raise ValueError('V2 display target mismatch')
    cash = Fraction(binding['available_cash'])
    marks = binding['valuation_quotes']
    holdings = {sid: q * Fraction(marks[sid]['price'])
                for sid, q in binding['shares'].items() if q}
    equity = cash + sum(holdings.values(), Fraction(0))
    if (cash < 0 or equity <= 0 or Fraction(decision['available_cash']) != cash
            or Fraction(decision['investable_equity']) != equity
            or Fraction(binding['investable_equity']) != equity
            or Fraction(binding['search_arguments']['entered_cash']) != equity
            or {sid: Fraction(v) for sid,v in decision['holding_market_values'].items()} != holdings
            or decision['decision_date'] != binding['decision_date']
            or decision['state_revision'] != binding['state_revision']
            or decision.get('execution_blocked') is not True or decision.get('research_only') is not True):
        raise ValueError('V2 display capital snapshot mismatch')
    output = project(result, binding['search_arguments'])
    output.update(research_id=decision['research_id'], method_version=VERSION,
        method_scope='V2_BOUNDED_VARIABLE_CARDINALITY_ACCOUNT_EQUITY_PRICE_SCENARIOS',
        available_cash_exact=decision['available_cash'],
        investable_equity_exact=decision['investable_equity'],
        allocation_basis='CASH_PLUS_MARKED_HOLDINGS_NOT_IMMEDIATELY_SPENDABLE_CASH',
        target_quantities=deepcopy(decision['target_quantities']),
        executable_buy_quantities=None, orders_created=False,
        source_hashes=deepcopy(binding['source_hashes']))
    for name in ('method_version', 'mandatory_evaluations', 'required_evaluation_budget',
                 'all_affordable_single_security_supports_initialized',
                 'single_security_quantity_optimum_established',
                 'single_security_optimization_evaluations', 'local_search_budget_by_k',
                 'training_objective_bound'):
        output['search_coverage'][name] = deepcopy(result.get(name))
    output['notes'].append('配置按现金加持仓市值计算；目标股数不是可立即买入股数，卖出款未到账不能使用。')
    return output
