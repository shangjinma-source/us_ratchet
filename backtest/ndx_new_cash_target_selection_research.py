"""Target-distance selection among feasible, explicitly evaluated buy-only plans.

Targets must be supplied from an already frozen decision by the future caller.
This pure API does not establish their provenance and accepts no future-return
input. It cannot rank economic winners or certify a globally optimal portfolio.
"""
from copy import deepcopy
from decimal import Context, localcontext
from fractions import Fraction
from backtest import ndx_conditional_new_cash_fork_research as kernel


SCHEMA = 'NEW_CASH_FEASIBLE_TARGET_L1_SELECTION_V1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rational(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def validate_evaluation(evaluation):
    require(evaluation['schema'] == kernel.SCHEMA, 'Unexpected underlying evaluator schema')
    for flag in ('global_optimality_claimed', 'full_integer_space_infeasibility_claimed',
                 'orders_executed', 'point_in_time_verified', 'promotion_allowed', 'historical_experiment_executed'):
        require(evaluation[flag] is False, 'Underlying evaluator authority changed')
    total = 0
    denominator = 0
    for branch in evaluation['branches']:
        count = branch['evaluated_count']
        require(type(count) is int and type(branch['candidate_count']) is int and type(branch['unevaluated_count']) is int
                and count == len(branch['candidates']) and 0 <= count <= branch['candidate_count']
                and branch['unevaluated_count'] == branch['candidate_count'] - count, 'Underlying coverage mismatch')
        require(branch['status'] == ('EXHAUSTED_SUPPLIED_DOMAIN' if count == branch['candidate_count'] else 'BUDGET_LIMITED'), 'Underlying coverage status mismatch')
        total += count
        denominator += branch['candidate_count']
        for position, row in enumerate(branch['candidates']):
            require(type(row['rank']) is int and row['rank'] == position, 'Underlying prefix rank mismatch')
            checks = row['risk']['checks']
            require(set(checks) == set(kernel.CHECKS) and all(type(value) is bool for value in checks.values()), 'Underlying five-risk gate mismatch')
            require(type(row['risk']['all_passed']) is bool and row['risk']['all_passed'] == all(checks.values()), 'Underlying risk summary mismatch')
            financial = row['financial_checks']
            require(set(financial) == {'NONNEGATIVE_CASH', 'CASH_BUFFER'} and all(type(value) is bool for value in financial.values()), 'Underlying cash gate mismatch')
            require(type(row['issuer_unique']) is bool and row['issuer_unique'] == (not row['issuer_conflicts']), 'Underlying issuer gate mismatch')
            require(type(row['feasible']) is bool and row['feasible'] ==
                    (all(financial.values()) and row['risk']['all_passed'] and row['issuer_unique']), 'Underlying feasible flag inconsistent')
    require(type(evaluation['evaluated_count']) is int and evaluation['evaluated_count'] == total
            and type(evaluation['candidate_count']) is int and evaluation['candidate_count'] == denominator, 'Underlying total coverage mismatch')


def select_target_plans(*, evaluation_inputs, target_weights_by_branch):
    """Call the frozen pure evaluator once; select independently within each branch.

    Objective = sum_sid |positive_stock_weight_sid - normalized_target_sid|.
    Every old/allowed-buy SID participates, absent target entries mean zero.
    Tie order: exact objective, exact fee dollars, original prefix rank.
    Cash is excluded from stock weights, as in the underlying five-risk kernel.
    Candidate caps and global budget remain exactly the caller's explicit domain.
    """
    with localcontext(Context(prec=160)):
        return _select_target_plans(evaluation_inputs=evaluation_inputs,
                                    target_weights_by_branch=target_weights_by_branch)


def _select_target_plans(*, evaluation_inputs, target_weights_by_branch):
    require(type(evaluation_inputs) is dict and type(target_weights_by_branch) is dict, 'Explicit input and target dictionaries required')
    inputs = deepcopy(evaluation_inputs)
    branches = inputs.get('branches')
    require(type(branches) is list and branches, 'Explicit nonempty branch list required')
    require(type(inputs.get('holdings')) is dict, 'Explicit initial holdings required')
    ids = []
    prepared = {}
    for branch in branches:
        require(type(branch) is dict and type(branch.get('branch_id')) is str and type(branch.get('buy_limits')) is dict,
                'Branch ID and buy limits required')
        branch_id = branch['branch_id']
        require(branch_id not in ids, 'Duplicate branch ID')
        ids.append(branch_id)
        require(branch_id in target_weights_by_branch, 'Missing branch target')
        target = target_weights_by_branch[branch_id]
        require(type(target) is dict and target, 'Positive target map required; empty cash controls use the evaluator directly')
        allowed = set(inputs['holdings']) | set(branch['buy_limits'])
        require(set(target) <= allowed, 'Target SID outside this branch old-holdings/buy union')
        parsed = {sid: Fraction(kernel._number(value)) for sid, value in target.items()}
        require(all(value >= 0 for value in parsed.values()), 'Target weights must be nonnegative')
        total = sum(parsed.values(), Fraction(0))
        require(total > 0, 'Target total must be positive')
        normalized = {sid: parsed.get(sid, Fraction(0)) / total for sid in sorted(allowed)}
        prepared[branch_id] = {'original_target_literals': {sid: str(value) for sid, value in target.items()},
                               'original_sum': total, 'normalized': normalized,
                               'absent_target_sids_assigned_zero': sorted(allowed - set(target))}
    require(set(ids) == set(target_weights_by_branch), 'Targets must correspond exactly to branch IDs')
    evaluation = kernel.evaluate_branches(**inputs)
    validate_evaluation(evaluation)
    require([row['branch_id'] for row in evaluation['branches']] == ids, 'Underlying branch order changed')
    prices = {sid: Fraction(kernel._number(value)) for sid, value in inputs['execution_prices'].items()}
    selections = []
    for branch_index, branch in enumerate(evaluation['branches']):
        target = prepared[branch['branch_id']]
        scored = []
        for candidate in branch['candidates']:
            if candidate['feasible'] is not True:
                continue
            holdings = candidate['proposed_holdings']
            require(set(holdings) == set(target['normalized'])
                    and all(type(q) is int and q >= 0 for q in holdings.values()), 'Underlying proposed holding union changed')
            notionals = {sid: quantity * prices[sid] for sid, quantity in holdings.items()}
            invested = sum(notionals.values(), Fraction(0))
            require(invested > 0, 'Feasible candidate unexpectedly has zero stock value')
            weights = {sid: value / invested for sid, value in notionals.items()}
            distance = sum((abs(weights[sid] - target['normalized'][sid]) for sid in weights), Fraction(0))
            fees = Fraction(candidate['fees_usd'])
            require(fees >= 0, 'Underlying negative fee')
            scored.append((distance, fees, candidate['rank'], candidate, weights))
        selected = None
        if scored:
            distance, fees, rank, candidate, weights = min(scored, key=lambda item: item[:3])
            selected = {'candidate_reference': '/evaluation/branches/' + str(branch_index) + '/candidates/' + str(rank),
                        'original_rank': rank, 'buy_shares': deepcopy(candidate['buy_shares']),
                        'holdings': deepcopy(candidate['proposed_holdings']),
                        'positive_holding_count': sum(quantity > 0 for quantity in candidate['proposed_holdings'].values()),
                        'stock_weights': {sid: rational(value) for sid, value in weights.items()},
                        'target_l1_distance': rational(distance), 'fee_usd_exact': rational(fees),
                        'original_candidate': deepcopy(candidate)}
        selections.append({'branch_id': branch['branch_id'], 'status': 'SELECTED_BEST_OF_FEASIBLE_EVALUATED' if selected else 'NO_FEASIBLE_EVALUATED_CANDIDATE',
                           'original_target_literals': target['original_target_literals'],
                           'original_target_sum': rational(target['original_sum']),
                           'normalized_target_weights': {sid: rational(value) for sid, value in target['normalized'].items()},
                           'absent_target_sids_assigned_zero': target['absent_target_sids_assigned_zero'],
                           'candidate_count': branch['candidate_count'], 'evaluated_count': branch['evaluated_count'],
                           'unevaluated_count': branch['unevaluated_count'], 'domain_status': branch['status'],
                           'feasible_evaluated_count': len(scored),
                           'feasible_candidate_scores': [{'original_rank': rank, 'target_l1_distance': rational(distance), 'fee_usd_exact': rational(fees)}
                                                         for distance, fees, rank, _, _ in scored], 'selected': selected})
    return {'schema': SCHEMA, 'evaluation': evaluation, 'selections': selections,
            'objective': 'EXACT_STOCK_WEIGHT_L1_TO_EXPLICIT_NORMALIZED_DECISION_TARGET',
            'tie_break': ['LOWER_EXACT_L1', 'LOWER_EXACT_FEE', 'LOWER_ORIGINAL_RANK'],
            'selection_scope': 'WITHIN_EACH_EVALUATED_BRANCH_NOT_ACROSS_ECONOMIC_STRATEGIES',
            'target_provenance_verified': False, 'targets_required_to_be_frozen_at_decision_by_caller': True,
            'future_return_data_used': False, 'economic_winner_selected': False, 'global_optimality_claimed': False,
            'full_integer_space_infeasibility_claimed': False, 'orders_executed': False,
            'point_in_time_verified': False, 'promotion_allowed': False, 'historical_experiment_executed': False}
