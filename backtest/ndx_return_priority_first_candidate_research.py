"""Finite return-first conditional target search; no IO or account authority.

Root must bind actual inputs and authorize an outer run separately. The dated
research target never substitutes for full PIT or actual old-book/new-cash work.
"""
from collections import defaultdict
from datetime import date
import math
import random


class BudgetExhausted(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValueError(message)


class Budget:
    def __init__(self, objective_limit, integer_limit):
        require(type(objective_limit) is int and objective_limit >= 0, 'Finite objective budget')
        require(type(integer_limit) is int and integer_limit >= 0, 'Finite integer budget')
        self.objective_limit = objective_limit
        self.integer_limit = integer_limit
        self.objective_calls = 0
        self.integer_proposals = 0
        self.risk_calls = 0

    def objective(self):
        if self.objective_calls >= self.objective_limit:
            raise BudgetExhausted('Objective budget exhausted before calculation')
        self.objective_calls += 1

    def integer(self):
        if self.integer_proposals >= self.integer_limit:
            raise BudgetExhausted('Integer proposal budget exhausted before proposal')
        self.integer_proposals += 1


def validate_inputs(securities, initial_prices, returns, return_dates, cutoff):
    require(type(securities) is list and securities, 'Nonempty explicit security domain')
    required = {'security_id', 'issuer_id', 'ticker', 'risk_chain'}
    require(all(type(row) is dict and set(row) == required
                and all(type(value) is str and value for value in row.values()) for row in securities), 'Closed identities')
    ids = [row['security_id'] for row in securities]
    require(len(set(ids)) == len(ids) and len({row['ticker'] for row in securities}) == len(ids), 'Unique security/ticker domain')
    require(set(initial_prices) == set(returns) == set(ids), 'Full declared domain prices/returns')
    require(type(return_dates) is list and return_dates == sorted(set(return_dates)) and len(return_dates) >= 2, 'Common explicit sessions')
    require(date.fromisoformat(cutoff).isoformat() == cutoff and return_dates[-1] <= cutoff, 'No post-cutoff returns')
    require(all(date.fromisoformat(day).isoformat() == day for day in return_dates), 'Canonical ISO sessions')
    for sid in ids:
        require(type(initial_prices[sid]) in (int, float) and math.isfinite(initial_prices[sid]) and initial_prices[sid] > 0, 'Positive initial close reference')
        require(type(returns[sid]) is list and len(returns[sid]) == len(return_dates)
                and all(type(value) in (int, float) and math.isfinite(value) and value > -1 for value in returns[sid]), 'Complete finite split-only returns')
    return {row['security_id']: row for row in securities}


def risk_checks(notionals, metadata, policy, budget=None):
    if budget is not None:
        budget.risk_calls += 1
    require(set(policy) == {'max_single_weight', 'min_single_weight', 'top_three_cap', 'min_neff_ratio', 'chain_cap'}, 'Five explicit risk parameters')
    require(all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in policy.values()), 'Risk parameter range')
    require(notionals and set(notionals) <= set(metadata) and all(math.isfinite(v) and v > 0 for v in notionals.values()), 'Positive finite full support')
    sids = sorted(notionals)
    require(len({metadata[sid]['issuer_id'] for sid in sids}) == len(sids), 'One security per issuer')
    total = sum(notionals[sid] for sid in sids)
    require(math.isfinite(total) and total > 0, 'Finite invested capital')
    weights = {sid: notionals[sid] / total for sid in sids}
    ordered = sorted(weights.values(), reverse=True)
    chains = defaultdict(float)
    for sid in sids:
        chains[metadata[sid]['risk_chain']] += weights[sid]
    neff = 1 / sum(value * value for value in ordered)
    checks = dict(max_single_weight=ordered[0] <= policy['max_single_weight'] + 1e-9,
                  min_single_weight=ordered[-1] >= policy['min_single_weight'] - 1e-9,
                  top_three_cap=sum(ordered[:3]) <= policy['top_three_cap'] + 1e-9,
                  min_neff_ratio=neff >= policy['min_neff_ratio'] * len(sids) - 1e-9,
                  chain_cap=max(chains.values()) <= policy['chain_cap'] + 1e-9)
    return dict(checks=checks, all_passed=all(checks.values()), weights=weights, effective_n=neff)


def analytic_k_status(k, policy):
    require(type(k) is int and k >= 1, 'Positive k')
    reasons = []
    if k * policy['max_single_weight'] < 1 - 1e-9:
        reasons.append('K_TIMES_MAX_WEIGHT_BELOW_ONE')
    if k * policy['min_single_weight'] > 1 + 1e-9:
        reasons.append('K_TIMES_MIN_WEIGHT_ABOVE_ONE')
    if min(3, k) / k > policy['top_three_cap'] + 1e-9:
        reasons.append('MINIMUM_POSSIBLE_TOP_THREE_WEIGHT_EXCEEDS_CAP')
    return reasons


def wealth_metrics(path, periods, annualization=252):
    require(type(periods) is int and periods > 0 and len(path) == periods + 2, 'Initial capital, post-fee initial and each return close required')
    require(all(math.isfinite(v) and v > 0 for v in path), 'Positive finite net wealth path')
    peak = path[0]
    dd = 0.0
    for value in path:
        peak = max(peak, value)
        dd = max(dd, 1 - value / peak)
    return dict(cagr=(path[-1] / path[0]) ** (annualization / periods) - 1,
                maximum_drawdown=dd, ending_wealth=path[-1])


def evaluate_allocation(*, quantities, initial_prices, returns, metadata, policy,
                        cash, fee_bps, buffer, budget, enforce_risk, risk_scope):
    require(risk_scope == 'INITIAL_DEPLOYMENT_DAILY_DIAGNOSTICS_ONLY', 'Root registered initial gate with daily diagnostics')
    require(type(cash) in (int, float) and cash > 0 and 0 <= buffer < cash and 0 <= fee_bps <= 10000, 'Cash/cost convention')
    require(quantities and set(quantities) <= set(initial_prices) and all(math.isfinite(q) and q > 0 for q in quantities.values()), 'Positive quantities')
    n = len(next(iter(returns.values())))
    notionals = {sid: quantities[sid] * initial_prices[sid] for sid in quantities}
    invested = sum(notionals.values())
    fees = invested * fee_bps / 10000
    remaining = cash - invested - fees
    if remaining < buffer - 1e-8:
        return None
    initial_risk = risk_checks(notionals, metadata, policy, budget) if enforce_risk else None
    if initial_risk is not None and not initial_risk['all_passed']:
        return None
    budget.objective()  # Every actual CAGR calculation, including integer candidates.
    path = [float(cash), remaining + invested]
    values = dict(notionals)
    daily_failed = []
    for i in range(n):
        for sid in values:
            values[sid] *= 1 + returns[sid][i]
        require(all(math.isfinite(v) and v > 0 for v in values.values()), 'Finite split-aware economic position values')
        path.append(remaining + sum(values.values()))
        if enforce_risk:
            risk = risk_checks(values, metadata, policy, budget)
            if not risk['all_passed']:
                daily_failed.append(i)
    metrics = wealth_metrics(path, n)
    return dict(quantities=dict(quantities), actual_weights={sid: notionals[sid] / invested for sid in sorted(notionals)},
                invested_notional=invested, fees=fees, research_buffer=buffer,
                unallocated_cash_above_buffer=remaining - buffer, remaining_cash=remaining,
                reconciliation_total=invested + fees + buffer + (remaining - buffer),
                net_wealth_path=path, training_metrics=metrics, initial_risk=initial_risk,
                daily_risk_failed_indices=daily_failed, feasible=True,
                hypothetical_historical_fractional_economic_units=True,
                historical_integer_split_share_evolution_verified=False,
                price_scope='DATED_TARGET_CLOSE_NOTIONALS_BACKCAST_AS_INITIAL_TRAINING_ECONOMIC_UNITS_SPLIT_ONLY_RETURNS',
                split_events_verified=False, execution_open_status='BLOCKED_NOT_SUPPLIED',
                actual_execution_authorized=False)


def supports_for_k(securities, k, limit, rng):
    groups = defaultdict(list)
    for row in securities:
        groups[row['issuer_id']].append(row['security_id'])
    issuers = sorted(groups)
    require(1 <= k <= len(issuers), 'k within full conditional issuer domain')
    seen = set()
    # Deterministic rotating coverage plus random issuer/class proposals. No sector filter.
    for attempt in range(limit * 4):
        offset = attempt * len(issuers) // max(1, limit // 2)
        chosen = [issuers[(i + offset) % len(issuers)] for i in range(k)] if attempt < limit // 2 else rng.sample(issuers, k)
        support = tuple(sorted(rng.choice(sorted(groups[issuer])) for issuer in chosen))
        if support not in seen:
            seen.add(support)
            yield support
            if len(seen) >= limit:
                return


def run_bounded_search(*, securities, initial_prices, target_prices, returns, return_dates, cutoff,
                       policy, cash, fee_bps, buffer, risk_scope, support_limit,
                       per_support_objectives, per_support_integers, global_objectives,
                       global_integers, seed=20261013):
    metadata = validate_inputs(securities, initial_prices, returns, return_dates, cutoff)
    require(set(target_prices) == set(initial_prices) and all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in target_prices.values()), 'Full positive dated target close prices')
    for value in (support_limit, per_support_objectives, per_support_integers):
        require(type(value) is int and value > 0, 'Positive finite local budgets')
    budget = Budget(global_objectives, global_integers)
    rng = random.Random(seed)
    issuer_count = len({row['issuer_id'] for row in securities})
    group_sizes = defaultdict(int)
    for security in securities:
        group_sizes[security['issuer_id']] += 1
    support_counts = [1]
    for size in group_sizes.values():
        following = support_counts + [0]
        for i, count in enumerate(support_counts):
            following[i + 1] += count * size
        support_counts = following
    coverage, co_winners = [], []
    best = None
    for k in range(1, issuer_count + 1):
        reasons = analytic_k_status(k, policy)
        row = dict(k=k, analytic_infeasibility=reasons, support_proposals=0,
                   objective_calls=0, integer_proposals=0, feasible_integer_candidates=0,
                   status='PROVEN_INFEASIBLE_RISK' if reasons else 'UNSEARCHED_PENDING_BUDGET',
                   total_issuer_unique_compositions=str(support_counts[k]),
                   unproposed_compositions=str(support_counts[k]),
                   continuous_weight_space_exhausted=False, exhaustive_composition_search=False)
        coverage.append(row)
        if reasons:
            continue
        start_obj, start_integer = budget.objective_calls, budget.integer_proposals
        if budget.objective_calls >= global_objectives or budget.integer_proposals >= global_integers:
            continue
        for support in supports_for_k(securities, k, support_limit, rng):
            row['support_proposals'] += 1
            local_start = budget.objective_calls
            weights = [1 / k] * k
            best_continuous = None
            # Reserve half the objective budget for actual whole-share competition.
            for probe in range(max(1, per_support_objectives // 2)):
                if budget.objective_calls - local_start >= per_support_objectives or budget.objective_calls >= global_objectives:
                    break
                proposed = list(weights)
                if probe and k > 1:
                    a, b = rng.sample(range(k), 2)
                    transfer = rng.uniform(-0.15, 0.15)
                    proposed[a] += transfer
                    proposed[b] -= transfer
                if min(proposed) <= 0:
                    continue
                invest = (cash - buffer) / (1 + fee_bps / 10000)
                quantities = {sid: invest * weight / target_prices[sid] for sid, weight in zip(support, proposed)}
                candidate = evaluate_allocation(quantities=quantities, initial_prices=target_prices, returns=returns,
                    metadata=metadata, policy=policy, cash=cash, fee_bps=fee_bps, buffer=buffer, budget=budget,
                    enforce_risk=True, risk_scope=risk_scope)
                if candidate and candidate['feasible'] and (best_continuous is None or candidate['training_metrics']['cagr'] > best_continuous['training_metrics']['cagr']):
                    best_continuous = candidate
                    weights = proposed
            if best_continuous is None:
                continue
            base = {sid: math.floor(best_continuous['quantities'][sid]) for sid in support}
            local_integer_best = None
            for probe in range(per_support_integers):
                if (budget.objective_calls - local_start >= per_support_objectives or budget.objective_calls >= global_objectives
                        or budget.integer_proposals >= global_integers):
                    break
                budget.integer()
                q = dict(base)
                if probe and k > 1:
                    a, b = rng.sample(support, 2)
                    q[a] += 1
                    if probe % 3:
                        q[b] -= 1
                if min(q.values()) < 1:
                    continue
                candidate = evaluate_allocation(quantities=q, initial_prices=target_prices, returns=returns,
                    metadata=metadata, policy=policy, cash=cash, fee_bps=fee_bps, buffer=buffer, budget=budget,
                    enforce_risk=True, risk_scope=risk_scope)
                if candidate is None or not candidate['feasible']:
                    continue
                candidate.update(hypothetical_training_initial_economic_units={sid: q[sid] * target_prices[sid] / initial_prices[sid] for sid in support},
                                 target_reference_prices={sid: target_prices[sid] for sid in support},
                                 k=k, support_security_ids=list(support), tickers={sid: metadata[sid]['ticker'] for sid in support},
                                 issuers={sid: metadata[sid]['issuer_id'] for sid in support})
                row['feasible_integer_candidates'] += 1
                score = candidate['training_metrics']['cagr']
                if best is None or score > best:
                    best, co_winners = score, [candidate]
                elif score == best and not any(existing['quantities'] == q for existing in co_winners):
                    co_winners.append(candidate)
                if local_integer_best is None or score > local_integer_best:
                    local_integer_best = score
                    base = q
        row.update(objective_calls=budget.objective_calls-start_obj, integer_proposals=budget.integer_proposals-start_integer,
                   unproposed_compositions=str(support_counts[k]-row['support_proposals']),
                   global_budget_exhausted=budget.objective_calls >= global_objectives or budget.integer_proposals >= global_integers,
                   status='BOUNDED_SEARCHED_NOT_EXHAUSTIVE' if row['support_proposals'] else 'UNSEARCHED_PENDING_BUDGET')
    return dict(schema='RETURN_FIRST_BOUNDED_CONDITIONAL_TARGET_V1', cutoff=cutoff,
                status='BEST_FOUND_CONDITIONAL_NOT_QUALIFIED' if co_winners else 'NO_FEASIBLE_CANDIDATE_WITHIN_BUDGET',
                co_winners=co_winners, per_k_coverage=coverage,
                budget=dict(objective_calls=budget.objective_calls, integer_proposals=budget.integer_proposals,
                            risk_calls=budget.risk_calls, objective_limit=global_objectives, integer_limit=global_integers,
                            validation_io_and_risk_excluded_from_objective_budget=True, gradient_calls=0),
                conditional_security_count=len(securities), conditional_issuer_count=issuer_count,
                qualified_inventory=None, qualified_upper_bound=None, point_in_time_verified=False,
                current_account=None, old_book_plus_new_cash_joint_optimization_complete=False,
                training_rank_only=True, independent_historical_evaluation='PENDING_SEPARATE_RUN',
                future_one_year_oos='NOT_CONSUMED_NOT_MATURE', global_optimality_claimed=False,
                real_adoption_allowed=False, orders_created=False)
