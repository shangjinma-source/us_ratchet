"""Evaluate a bounded ordered set of explicit buy plans without Cartesian search."""
from copy import deepcopy
from decimal import Context, Decimal, localcontext
from fractions import Fraction
from backtest import ndx_conditional_new_cash_fork_research as kernel


SCHEMA = 'EXPLICIT_BUY_ONLY_CASH_PLAN_EVALUATION_V1'
MAX_SUPPLIED_PLANS = 10000  # Engineering cap, not a feasible-pool/cardinality limit.


def require(condition, message):
    if not condition:
        raise ValueError(message)


def evaluate_explicit_plans(*, evaluation_inputs, plans_by_branch):
    """Validate every supplied plan, then evaluate only the global ordered prefix.

    Each plan must contain exactly all SID keys in its branch buy_limits,
    including explicit zero quantities. Duplicate plans within a branch fail.
    The same quantities in different named branches remain distinct scenarios.
    No target choice, ranking, optimization, source certification or execution.
    """
    with localcontext(Context(prec=160)):
        return _evaluate(evaluation_inputs=evaluation_inputs, plans_by_branch=plans_by_branch)


def _evaluate(*, evaluation_inputs, plans_by_branch):
    require(type(evaluation_inputs) is dict and type(plans_by_branch) is dict, 'Explicit input and branch plan dictionaries required')
    inputs = deepcopy(evaluation_inputs)
    budget = kernel._integer(inputs['max_evaluations'], kernel.MAX_EVALUATIONS)
    zero_inputs = deepcopy(inputs)
    zero_inputs['max_evaluations'] = 0
    validation = kernel.evaluate_branches(**zero_inputs)
    require(validation['schema'] == kernel.SCHEMA and type(validation['evaluated_count']) is int
            and validation['evaluated_count'] == 0
            and all(branch['evaluated_count'] == 0 and not branch['candidates'] for branch in validation['branches']),
            'Underlying zero-search validator unexpectedly evaluated plans')
    for flag in ('orders_executed', 'point_in_time_verified', 'promotion_allowed', 'global_optimality_claimed'):
        require(validation[flag] is False, 'Underlying authority changed')
    branch_ids = [branch['branch_id'] for branch in inputs['branches']]
    require(set(plans_by_branch) == set(branch_ids), 'Plans must match exact branch IDs')
    prepared, supplied_total = [], 0
    for branch in inputs['branches']:
        branch_id, limits = branch['branch_id'], branch['buy_limits']
        supplied = plans_by_branch[branch_id]
        require(type(supplied) is list, 'Each branch needs an ordered explicit plan list, possibly empty')
        supplied_total += len(supplied)
        require(supplied_total <= MAX_SUPPLIED_PLANS, 'Supplied plan resource bound exceeded')
        plans, seen = [], set()
        sids = sorted(limits)
        for plan in supplied:
            require(type(plan) is dict and set(plan) == set(limits), 'Plan keys must exactly equal branch buy-limit SID keys')
            counts = tuple(kernel._integer(plan[sid], limits[sid]) for sid in sids)
            require(counts not in seen, 'Duplicate explicit plan within branch')
            seen.add(counts)
            cartesian_rank = 0
            for sid, quantity in zip(sids, counts):
                cartesian_rank = cartesian_rank * (limits[sid] + 1) + quantity
            plans.append({'buy_shares': dict(zip(sids, counts)), 'cartesian_rank': cartesian_rank})
        prepared.append(plans)
    # Every plan, including the unevaluated suffix, has passed validation above.
    cash = kernel._number(inputs['starting_cash_usd'])
    amount = kernel._number(inputs['cash_event']['amount_usd'])
    buffer = kernel._number(inputs['minimum_cash_buffer_usd'])
    fee_bps = kernel._number(inputs['transaction_cost_bps'])
    marks = {sid: kernel._number(value) for sid, value in inputs['execution_prices'].items()}
    parameters = {key: Fraction(kernel._number(value)) for key, value in inputs['risk_parameters'].items()}
    base, securities = inputs['holdings'], inputs['securities']
    initial = cash + sum((marks[sid] * quantity for sid, quantity in base.items()), Decimal(0))
    results, evaluated_total = [], 0
    for branch_index, branch in enumerate(inputs['branches']):
        plans = prepared[branch_index]
        count = min(len(plans), budget - evaluated_total)
        evaluated = []
        for index, plan in enumerate(plans[:count]):
            buys = plan['buy_shares']
            after = dict(base)
            for sid, quantity in buys.items():
                after[sid] = after.get(sid, 0) + quantity
            gross = sum((marks[sid] * quantity for sid, quantity in buys.items()), Decimal(0))
            fees = gross * fee_bps / Decimal(10000)
            remaining = cash + amount - gross - fees
            risk = kernel._risk(after, marks, securities, parameters)
            conflicts = kernel._issuer_conflicts(after, securities)
            financial = {'NONNEGATIVE_CASH': remaining >= 0, 'CASH_BUFFER': remaining >= buffer}
            equity = remaining + sum((marks[sid] * quantity for sid, quantity in after.items()), Decimal(0))
            evaluated.append({'supplied_plan_index': index, 'original_cartesian_rank': plan['cartesian_rank'],
                'buy_shares': dict(buys), 'proposed_holdings': dict(sorted(after.items())),
                'gross_buy_usd': str(gross), 'fees_usd': str(fees), 'cash_after_usd': str(remaining),
                'equity_after_usd': str(equity), 'cash_flow_adjusted_pnl_usd': str(equity - initial - amount),
                'financial_checks': financial, 'risk': risk, 'issuer_conflicts': conflicts,
                'issuer_unique': not conflicts, 'feasible': all(financial.values()) and risk['all_passed'] and not conflicts})
        evaluated_total += count
        cartesian_count = validation['branches'][branch_index]['candidate_count']
        results.append({'branch_id': branch['branch_id'], 'buy_limits': deepcopy(branch['buy_limits']),
            'cartesian_candidate_count': cartesian_count, 'supplied_plan_count': len(plans),
            'evaluated_count': count, 'unevaluated_supplied_plan_count': len(plans) - count,
            'unsupplied_cartesian_candidate_count': cartesian_count - len(plans),
            'status': 'ALL_SUPPLIED_PLANS_EVALUATED' if count == len(plans) else 'SUPPLIED_PLAN_BUDGET_LIMITED',
            'supplied_plans': deepcopy(plans), 'evaluated_plans': evaluated,
            'feasible_evaluated_count': sum(row['feasible'] for row in evaluated)})
    return {'schema': SCHEMA, 'contract_validation_without_search': validation,
            'cash_event': deepcopy(validation['cash_event']), 'starting_holdings': deepcopy(validation['starting_holdings']),
            'starting_cash_usd': validation['starting_cash_usd'], 'initial_equity_usd': str(initial),
            'risk_parameters': deepcopy(validation['risk_parameters']), 'transaction_cost_bps': str(fee_bps),
            'minimum_cash_buffer_usd': str(buffer), 'max_evaluations': budget,
            'cartesian_candidate_count': validation['candidate_count'], 'supplied_plan_count': supplied_total,
            'evaluated_count': evaluated_total, 'unevaluated_supplied_plan_count': supplied_total - evaluated_total,
            'branches': results, 'evaluation_order': 'CALLER_BRANCH_ORDER_THEN_CALLER_PLAN_ORDER_V1',
            'kernel_validation_call_count': 1, 'kernel_cartesian_search_evaluation_count': 0,
            'engineering_max_supplied_plans': MAX_SUPPLIED_PLANS, 'supplied_plans_are_full_space_claim': False,
            'global_optimality_claimed': False, 'full_integer_space_infeasibility_claimed': False,
            'economic_winner_selected': False, 'orders_executed': False, 'point_in_time_verified': False,
            'promotion_allowed': False, 'historical_experiment_executed': False, 'time_series_return_evaluated': False,
            'parameter_authority': 'CALLER_SUPPLIED_NOT_SOURCE_BOUND'}
