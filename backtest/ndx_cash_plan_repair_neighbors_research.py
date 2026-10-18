"""Bounded local neighbors of additional-buy quantities; no holdings or risk API."""
from itertools import combinations, product


SCHEMA = 'ADDITIONAL_BUY_LOCAL_REPAIR_NEIGHBORS_V1'
ORDER_VERSION = 'SEED_ORDER_SORTED_SID_SINGLE_MINUS_PLUS_THEN_PAIR_LEX_SIGNS_V1'
MAX_MOVE_ATTEMPTS = 10000
MAX_INPUT_PLANS = 10000
MAX_SECURITIES = 256
MAX_SHARES = 10**12


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, maximum):
    require(type(value) is int and 0 <= value <= maximum, 'Bounded nonnegative integer required, not bool/float')
    return value


def validate_plans(plans, sids, limits, label):
    require(type(plans) is list and len(plans) <= MAX_INPUT_PLANS, label + ': bounded ordered list required')
    result, seen = [], set()
    for plan in plans:
        require(type(plan) is dict and set(plan) == set(sids), label + ': exact buy-limit SID keys required')
        values = tuple(integer(plan[sid], limits[sid]) for sid in sids)
        require(values not in seen, label + ': duplicate input plan')
        seen.add(values)
        result.append(values)
    return result


def generate_repair_neighbors(*, buy_limits, seed_plans, excluded_plans, max_generated_plans):
    """Enumerate the COMPLETE bounded requested local domain before prefix capping.

    For each seed: sorted SID singles -1,+1; then pairs i<j in sorted SID
    order with deltas (-1,-1),(-1,+1),(+1,-1),(+1,+1). First seen wins.
    Counts partition all attempted moves into out-of-bounds, duplicate valid
    coordinates, unique excluded coordinates, and distinct remaining plans.
    An excluded coordinate is counted once as excluded; later visits count as
    duplicates. Only additional buys are modified, never actual old holdings.
    """
    require(type(buy_limits) is dict and len(buy_limits) <= MAX_SECURITIES, 'Bounded buy-limit SID map required')
    for sid, cap in buy_limits.items():
        require(type(sid) is str and sid and sid.strip() == sid, 'Canonical nonblank SID required')
        integer(cap, MAX_SHARES)
    sids = sorted(buy_limits)
    limit = integer(max_generated_plans, MAX_MOVE_ATTEMPTS)
    require(type(seed_plans) is list and len(seed_plans) <= MAX_INPUT_PLANS, 'Bounded seed list required')
    move_count_per_seed = 2 * len(sids) ** 2
    attempts = len(seed_plans) * move_count_per_seed
    require(attempts <= MAX_MOVE_ATTEMPTS, 'Requested full local domain exceeds move-attempt engineering cap')
    seeds = validate_plans(seed_plans, sids, buy_limits, 'seeds')
    exclusions = set(validate_plans(excluded_plans, sids, buy_limits, 'excluded'))
    moves = [((index, delta),) for index in range(len(sids)) for delta in (-1, 1)]
    moves += [((first, delta1), (second, delta2))
              for first, second in combinations(range(len(sids)), 2)
              for delta1, delta2 in product((-1, 1), repeat=2)]
    require(len(moves) == move_count_per_seed, 'Internal move count mismatch')
    seen, distinct = set(), []
    out_of_bounds = duplicate_count = excluded_count = 0
    for seed_index, seed in enumerate(seeds):
        for move_index, move in enumerate(moves):
            candidate = list(seed)
            for index, delta in move:
                candidate[index] += delta
            coordinate = tuple(candidate)
            if any(value < 0 or value > buy_limits[sid] for sid, value in zip(sids, coordinate)):
                out_of_bounds += 1
                continue
            if coordinate in seen:
                duplicate_count += 1
                continue
            seen.add(coordinate)
            if coordinate in exclusions:
                excluded_count += 1
                continue
            distinct.append({'buy_shares': dict(zip(sids, coordinate)),
                             'first_seed_index': seed_index, 'first_seed_buy_shares': dict(zip(sids, seed)),
                             'first_move_index': move_index, 'first_move_kind': 'SINGLE' if len(move) == 1 else 'PAIR',
                             'first_move_deltas': {sids[index]: delta for index, delta in move}})
    require(attempts == out_of_bounds + duplicate_count + excluded_count + len(distinct), 'Internal count partition mismatch')
    generated = distinct[:limit]
    return {'schema': SCHEMA, 'order_version': ORDER_VERSION,
            'buy_limits': {sid: buy_limits[sid] for sid in sids},
            'seed_plans': [dict(zip(sids, seed)) for seed in seeds],
            'excluded_plans': [dict(zip(sids, values)) for values in validate_plans(excluded_plans, sids, buy_limits, 'excluded')],
            'seed_count': len(seeds), 'excluded_input_count': len(exclusions),
            'moves_per_seed': move_count_per_seed, 'total_move_attempts': attempts,
            'out_of_bounds_attempt_count': out_of_bounds, 'duplicate_valid_coordinate_attempt_count': duplicate_count,
            'unique_excluded_coordinate_count': excluded_count, 'distinct_remaining_plan_count': len(distinct),
            'generated_plan_count': len(generated), 'ungenerated_plan_count': len(distinct) - len(generated),
            'max_generated_plans': limit, 'generated_plans': generated,
            'status': 'ALL_REQUESTED_LOCAL_NEIGHBORS_GENERATED' if len(generated) == len(distinct) else 'LOCAL_GENERATION_BUDGET_PREFIX',
            'requested_local_domain_fully_enumerated': True,
            'global_integer_domain_enumerated': False, 'global_optimality_claimed': False,
            'full_integer_space_infeasibility_claimed': False, 'candidate_feasibility_evaluated': False,
            'risk_evaluated': False, 'price_data_used': False, 'old_holdings_modified': False,
            'orders_executed': False, 'point_in_time_verified': False, 'promotion_allowed': False,
            'engineering_limits_not_k_or_eligible_pool_policy': {'move_attempts': MAX_MOVE_ATTEMPTS,
                                                               'input_plans': MAX_INPUT_PLANS, 'security_ids': MAX_SECURITIES}}
