# Isolated research fork; original SHA256 f813782ab166139c8d30b268a242fa05bd65ce76e9b9b20aa03a0beee2bd01d7
"""V2 bounded search with mandatory single-security coverage and per-k budgets.

No IO or prior holdings. Concentration is unrestricted, including one issuer.
All affordable cardinalities and all affordable single securities receive
mandatory evaluated seeds before cardinality-preserving local search. Exhausted neighborhoods do not establish a global optimum.
"""
from datetime import date
from fractions import Fraction
import hashlib
import math
from backtest.affordable_support_seeds import affordable_support_seeds
from backtest.log_concave_integer_search import maximize_log_concave_integer
from backtest.quantity_training_upper_bound import training_product_upper_bound, public_bound


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    _require(type(value) in (str, int, float, Fraction), 'Finite nonboolean number required')
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError, OverflowError) as error:
        raise ValueError('Finite rational number required') from error


def search_fresh_cash_quantities(*, prices, metadata, entered_cash, fee_bps,
                                 minimum_cash_buffer, training_scenarios,
                                 scenario_dates, decision_date,
                                 max_objective_evaluations, fixed_seed):
    """Maximize equal-scenario mean log terminal wealth, including residual cash.

Prices and gross relatives must share a caller-validated basis. Fees are charged
on the initial purchase only; no liquidation, dividends or reinvestment implied.
The score is a training scenario score, never a future-return estimate.
"""
    _require(type(prices) is dict and prices and type(metadata) is dict
             and set(prices) == set(metadata), 'Complete common SID domain required')
    _require(all(type(sid) is str and sid for sid in prices), 'Explicit SIDs required')
    marks = {sid: _number(value) for sid, value in prices.items()}
    _require(all(value > 0 for value in marks.values()), 'Positive prices required')
    _require(type(fixed_seed) is str and fixed_seed, 'Explicit deterministic seed required')
    _require(type(max_objective_evaluations) is int and max_objective_evaluations > 0,
             'Positive objective evaluation limit required')
    _require(type(decision_date) is str and date.fromisoformat(decision_date).isoformat() == decision_date,
             'Canonical decision date required')
    _require(type(training_scenarios) is list and training_scenarios
             and type(scenario_dates) is list and len(scenario_dates) == len(training_scenarios),
             'Nonempty common scenario dates required')
    _require(all(type(day) is str and date.fromisoformat(day).isoformat() == day
                 and day <= decision_date for day in scenario_dates)
             and scenario_dates == sorted(set(scenario_dates)), 'Unique mature ordered scenario dates required')
    scenarios = []
    for row in training_scenarios:
        _require(type(row) is dict and set(row) == set(marks), 'Missing scenarios cannot be filled')
        values = {sid: _number(value) for sid, value in row.items()}
        _require(all(value > 0 for value in values.values()), 'Positive gross relatives required')
        scenarios.append(values)
    groups = {}
    for sid, row in metadata.items():
        _require(type(row) is dict and all(type(row.get(key)) is str and row[key]
                                         for key in ('ticker', 'issuer_id')), 'Explicit ticker/issuer required')
        groups.setdefault(row['issuer_id'], []).append(sid)
    _require(len({row['ticker'] for row in metadata.values()}) == len(metadata), 'Unique tickers required')
    cash, fee, buffer = _number(entered_cash), _number(fee_bps) / 10000, _number(minimum_cash_buffer)
    _require(cash > 0 and 0 <= fee < 1 and buffer >= 0, 'Invalid cash, fee or buffer')
    units_cost = {sid: value * (1 + fee) for sid, value in marks.items()}
    order = sorted(marks, key=lambda sid: (hashlib.sha256((fixed_seed+'|'+sid).encode()).hexdigest(), sid))
    cheapest = sorted((min(sids, key=lambda sid: (marks[sid], sid)) for sids in groups.values()),
                      key=lambda sid: (marks[sid], sid))
    per_k, seeds = [], {}
    for k in range(1, len(groups)+1):
        lower = sum((units_cost[sid] for sid in cheapest[:k]), Fraction(0))
        affordable = lower <= cash-buffer
        per_k.append(dict(k=k, minimum_purchase_cost=str(lower),
                          structural_status='AFFORDABLE' if affordable else 'UNAFFORDABLE_CHEAPEST_ISSUER_BOUND',
                          initialized=False, visited_states=0, visited_supports=0,
                          return_rank_seed_status='NOT_ATTEMPTED',
                          search_scope='NOT_SEARCHED' if affordable else 'PROVEN_UNAFFORDABLE',
                          global_optimum_established=False))
        if affordable:
            seeds[k] = {sid: 1 for sid in cheapest[:k]}
    base = dict(research_only=True, objective='TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH',
                forecast_return=None, decision_date=decision_date, scenario_dates=list(scenario_dates),
                entered_cash=str(cash), fee_bps=str(fee*10000), minimum_cash_buffer=str(buffer),
                max_objective_evaluations=max_objective_evaluations, per_k=per_k,
                global_optimum_established=False, historical_performance_inherited=False,
                source_authenticated=False, initial_positions={}, orders_created=False,
                remaining_domain='ALL_UNVISITED_INTEGER_STATES_UNKNOWN',
                fee_scope='INITIAL_BUY_ONLY_NO_TERMINAL_LIQUIDATION')
    # Preflight exact unique mandatory seeds; never publish partial coverage.
    mandatory = {(): {}}
    for q in seeds.values():
        mandatory[tuple(sorted(q.items()))] = q
    single_security_seeds = {}
    for sid in order:
        maximum = int((cash-buffer)//units_cost[sid])
        if maximum < 1:
            continue
        single_security_seeds[sid] = sorted({1, maximum})
        for quantity in single_security_seeds[sid]:
            mandatory[((sid, quantity),)] = {sid: quantity}
    # Endpoints are already mandatory. Reserve a conservative bound on distinct
    # additional binary-search evaluations before doing any objective work.
    single_extra_bound = sum(min(max(0, values[-1]-2), 2*(values[-1]-1).bit_length())
                             for values in single_security_seeds.values())
    required_budget = len(mandatory)+single_extra_bound
    base.update(method_version='EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2',
                mandatory_evaluations=len(mandatory),
                required_evaluation_budget=required_budget,
                single_security_extra_evaluation_bound=single_extra_bound,
                single_security_seed_quantities=single_security_seeds,
                single_security_quantity_optimum_established=False,
                local_search_budget_by_k={})
    if max_objective_evaluations < required_budget:
        return dict(base, status='INSUFFICIENT_BUDGET_FOR_MANDATORY_COVERAGE',
                    objective_evaluations=0, selected=None)
    visited, supports, best_by_k, best = set(), {k: set() for k in seeds}, {}, None
    objective_products = {}
    # Research-only exact arithmetic acceleration. No proposal/budget changes.
    notional_denominator = math.lcm(*(value.denominator for value in marks.values()))
    notional_coefficients = {sid: value.numerator * (notional_denominator // value.denominator)
                             for sid, value in marks.items()}
    growth_rows = []
    for scenario in scenarios:
        coefficients = {sid: marks[sid] * (scenario[sid] - 1 - fee) / cash for sid in marks}
        denominator = math.lcm(*(value.denominator for value in coefficients.values()))
        integers = {sid: value.numerator * (denominator // value.denominator)
                    for sid, value in coefficients.items()}
        growth_rows.append((denominator, integers))

    def key(q):
        return tuple(sorted((sid, value) for sid, value in q.items() if value))

    def evaluate(q):
        nonlocal best
        q = dict(key(q))
        signature = key(q)
        if signature in visited:
            return None
        if any(type(value) is not int or value <= 0 for value in q.values()):
            return None
        if len({metadata[sid]['issuer_id'] for sid in q}) != len(q):
            return None
        notional = Fraction(sum(notional_coefficients[sid]*value for sid, value in q.items()), notional_denominator)
        residual = cash-notional*(1+fee)
        # A below-buffer input may retain all cash, but cannot open a stock basket.
        if q and residual < buffer:
            return None
        if residual < 0:
            return None
        growth = [Fraction(denominator + sum(integers[sid]*value for sid, value in q.items()), denominator)
                  for denominator, integers in growth_rows]
        product = math.prod(growth)
        score = sum(math.log(value.numerator)-math.log(value.denominator) for value in growth)/len(growth)
        record = dict(quantities=q, actual_k=len(q), notional=str(notional), fees=str(notional*fee),
                      residual_cash=str(residual), training_mean_net_log_wealth=score,
                      training_gross_growth_product=(str(product) if max(product.numerator.bit_length(), product.denominator.bit_length()) <= 4096 else None),
                      exact_product_comparison=True,
                      large_exact_product_serialization_omitted=max(product.numerator.bit_length(), product.denominator.bit_length()) > 4096,
                      actual_weights={sid: str(marks[sid]*value/cash) for sid, value in q.items()},
                      cash_fraction=str(residual/cash), issuer_unique=True,
                      budget_conservation_exact=notional+notional*fee+residual == cash)
        ranked = (product, -notional, signature)
        visited.add(signature)
        objective_products[signature] = product
        k = len(q)
        if k:
            row = per_k[k-1]
            row['visited_states'] += 1
            supports[k].add(tuple(q))
            row['visited_supports'] = len(supports[k])
            row['search_scope'] = 'VISITED_STATES_ONLY'
        if k not in best_by_k or ranked > best_by_k[k][0]:
            best_by_k[k] = (ranked, record)
        if best is None or ranked > best[0]:
            best = (ranked, record)
        return record

    def neighbors(q):
        spent = sum((units_cost[sid]*value for sid, value in q.items()), Fraction(0))
        spare = cash-buffer-spent
        for sid in order:
            current = q.get(sid, 0)
            for delta in (1, int(spare//units_cost[sid])):
                if delta > 0:
                    changed = dict(q); changed[sid] = current+delta
                    yield changed
            if current:
                for left in (current-1, 0):
                    changed = dict(q); changed[sid] = left
                    yield changed
        # Partial transfers and full substitutions include same-issuer class swaps.
        for sold in order:
            if sold not in q:
                continue
            for amount in sorted({1, q[sold]}):
                released = spare+amount*units_cost[sold]
                for bought in order:
                    if bought == sold:
                        continue
                    for quantity in sorted({1, int(released//units_cost[bought])}):
                        if quantity > 0:
                            changed = dict(q); changed[sold] -= amount
                            changed[bought] = changed.get(bought, 0)+quantity
                            yield changed

    for q in mandatory.values():
        evaluate(q)
    before_single_search = len(visited)
    single_optima = {}
    for sid, quantities in single_security_seeds.items():
        def objective(quantity):
            signature = ((sid, quantity),)
            if signature not in objective_products:
                evaluate({sid: quantity})
            return objective_products[signature]
        optimum = maximize_log_concave_integer(1, quantities[-1], objective)
        single_optima[sid] = dict(quantity=optimum, maximum_affordable=quantities[-1],
                                  scope='POSITIVE_SINGLE_SECURITY_INTEGER_QUANTITIES',
                                  proof='POSITIVE_AFFINE_SCENARIO_WEALTH_LOG_CONCAVITY',
                                  tie_break='LOWER_QUANTITY')
    single_evaluations = len(visited)-before_single_search
    assert single_evaluations <= single_extra_bound
    base.update(single_security_quantity_optimum_established=True,
                single_security_optima=single_optima,
                single_security_optimization_evaluations=single_evaluations)
    for k in seeds:
        per_k[k-1]['initialized'] = True
        per_k[k-1]['return_rank_seed_status'] = 'NOT_USED_V2'
    # Every feasible k gets an explicit nontransferable evaluation allowance.
    # Neighbor proposals stay within their lane, so cross-k moves cannot consume
    # another lane's allocation. Unused allowance is reported, not silently moved.
    remaining = max_objective_evaluations-len(visited)
    quotient, remainder = divmod(remaining, len(seeds)) if seeds else (0, 0)
    quotas = {k: quotient+(index < remainder) for index, k in enumerate(seeds)}
    used = {k: 0 for k in seeds}
    anchors = {k: key(best_by_k[k][1]['quantities']) for k in seeds}
    cursors = {k: iter(neighbors(dict(anchor))) for k, anchor in anchors.items()}
    support_cursors = {k: iter(affordable_support_seeds(
        ordered_sids=order, metadata=metadata, unit_costs=units_cost,
        spendable=cash-buffer, k=k)) for k in seeds}
    support_exhausted, local_exhausted = set(), set()
    support_emitted = {k: 0 for k in seeds}
    support_evaluations = {k: 0 for k in seeds}
    prefer_support = {k: True for k in seeds}
    active = set(seeds)
    while active:
        for k in sorted(active):
            if used[k] >= quotas[k]:
                active.remove(k)
                continue
            anchor = key(best_by_k[k][1]['quantities'])
            if anchors[k] != anchor:
                anchors[k] = anchor
                cursors[k] = iter(neighbors(dict(anchor)))
                local_exhausted.discard(k)
            # Alternate objective evaluations between new supports and local
            # refinement; duplicates never consume objective budget.
            modes = ('support', 'local') if prefer_support[k] else ('local', 'support')
            evaluated = False
            for mode in modes:
                done = support_exhausted if mode == 'support' else local_exhausted
                if k in done:
                    continue
                cursor = support_cursors[k] if mode == 'support' else cursors[k]
                for proposal in cursor:
                    if mode == 'support':
                        support_emitted[k] += 1
                    elif len(key(proposal)) != k:
                        continue
                    if evaluate(proposal) is not None:
                        used[k] += 1
                        support_evaluations[k] += mode == 'support'
                        prefer_support[k] = mode != 'support'
                        evaluated = True
                        break
                else:
                    done.add(k)
                if evaluated:
                    break
            if not evaluated:
                active.remove(k)
    base['local_search_budget_by_k'] = {
        str(k): dict(allocated=quotas[k], used=used[k], unused=quotas[k]-used[k],
                     support_seeds_emitted=support_emitted[k],
                     support_seed_objective_evaluations=support_evaluations[k],
                     support_enumeration_complete=k in support_exhausted,
                     local_neighborhood_exhausted=k in local_exhausted,
                     all_integer_quantities_enumerated=False,
                     stop_reason='SUPPORT_SEEDS_AND_LOCAL_NEIGHBORHOOD_EXHAUSTED'
                     if k in support_exhausted and k in local_exhausted else 'LANE_BUDGET_STOPPED')
        for k in seeds}
    base['all_affordable_single_security_supports_initialized'] = True
    bound = training_product_upper_bound(cash=cash, fee=fee, buffer=buffer,
                                         prices=marks, scenarios=scenarios,
                                         quantities=best[1]['quantities'])
    base['training_objective_bound'] = public_bound(bound)
    return dict(base, status='BUDGET_STOPPED' if len(visited) >= max_objective_evaluations else 'PER_K_SEARCH_STOPPED_WITH_UNUSED_BUDGET',
                objective_evaluations=len(visited), selected=best[1],
                best_by_k={str(k): value[1] for k, value in sorted(best_by_k.items())},
                tie_break='EXACT_GROWTH_PRODUCT_THEN_LOWER_NOTIONAL_THEN_LEXICOGRAPHIC_QUANTITIES',
                all_affordable_k_initialized=True)
